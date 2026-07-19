"""Skill 运行时：目录注入 + use_skill 按需加载。

设计（对齐 Claude Code 的 Skill 机制）：
    - 技能目录（名称/标题/描述/触发词）常驻 system 上下文，让模型知道「有哪些技能可用」。
    - 技能完整正文（可能很长）不进上下文，模型判断需要时再调用 use_skill 工具按名加载，
      避免上下文膨胀。
    - 用户可直接配置现存的 Skill（inline content 或 repo path）。

安全：仅加载 enabled 的技能；use_skill 只读取当前用户自己的技能（租户隔离）。
"""
from __future__ import annotations

import logging

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Skill, Hook


logger = logging.getLogger("app.skill_runtime")


def get_skill_catalog(db: Session, user_id: int) -> str:
    """生成注入 system 上下文的技能目录（不含正文）。无技能返回空串。"""
    skills = db.scalars(
        select(Skill).where(Skill.user_id == user_id, Skill.enabled.is_(True))
    ).all()
    if not skills:
        return ""
    lines = [
        "你可以通过以下 use_skill 工具按需加载用户配置的技能（仅在判断任务匹配时调用，"
        "避免一次性加载全部正文导致上下文膨胀）："
    ]
    for s in skills:
        triggers = ", ".join(s.trigger_words or [])
        t = f"（触发词：{triggers}）" if triggers else ""
        lines.append(f"- {s.name}: {s.title} — {s.description} {t}")
    return "\n".join(lines)


def load_skill_content(db: Session, user_id: int, name: str) -> str:
    """按名加载技能完整正文（供 use_skill 工具调用）。"""
    s = db.scalar(
        select(Skill).where(
            Skill.user_id == user_id, Skill.name == name, Skill.enabled.is_(True)
        )
    )
    if not s:
        return f"[error] 未找到已启用的技能: {name}"
    return s.content or f"[error] 技能 {name} 内容为空"


class _UseSkillArgs(BaseModel):
    skill_name: str = Field(..., description="要加载的技能名称（来自技能目录）")


def build_use_skill_tool(db: Session, user_id: int) -> StructuredTool | None:
    """构建 use_skill 工具；无可用技能返回 None。"""
    has = db.scalar(
        select(Skill.id).where(Skill.user_id == user_id, Skill.enabled.is_(True)).limit(1)
    )
    if not has:
        return None

    def _use(skill_name: str) -> str:
        return load_skill_content(db, user_id, skill_name)

    return StructuredTool(
        name="use_skill",
        description=(
            "加载用户配置的某个技能（Skill）的完整指令内容。当你判断当前任务匹配技能目录中的"
            "某一项时调用，获取其详细操作方法后再继续。"
        ),
        args_schema=_UseSkillArgs,
        func=_use,
    )


# 声明式 Hook 的结构：declared_hooks 为 {event: {command, matcher?, on_error?, timeout_ms?, env?}}
_ALLOWED_DECL_EVENTS = {
    "SessionStart", "UserPromptSubmit", "PreToolUse",
    "PostToolUse", "Stop", "SubagentStop", "Notification",
}


def sync_declared_hooks(db: Session, skill: Skill) -> list[Hook]:
    """将技能的 declared_hooks 同步为真实 Hook 行（经 skill_id 关联）。

    - 启用技能时：为每个声明的事件创建/更新对应 Hook，并随技能一并启用。
    - 停用技能时：将其关联 Hook 全部置为 disabled（不再参与生命周期执行）。
    返回受影响的 Hook 列表。
    """
    declared = skill.declared_hooks or {}
    if not isinstance(declared, dict):
        declared = {}

    affected: list[Hook] = []
    existing = {
        h.event: h
        for h in db.scalars(select(Hook).where(Hook.skill_id == skill.id)).all()
    }

    if not skill.enabled:
        # 停用：禁用所有关联 Hook
        for h in existing.values():
            h.enabled = False
            affected.append(h)
        db.flush()
        return affected

    for event, spec in declared.items():
        if event not in _ALLOWED_DECL_EVENTS:
            logger.warning("技能 %s 声明了非法 hook event: %s，已跳过", skill.id, event)
            continue
        if not isinstance(spec, dict):
            spec = {"command": str(spec)}
        command = (spec.get("command") or "").strip()
        if not command:
            continue
        hook = existing.get(event)
        if hook is None:
            hook = Hook(user_id=skill.user_id, skill_id=skill.id, event=event)
            db.add(hook)
        hook.command = command
        hook.matcher = spec.get("matcher", "") or ""
        hook.on_error = spec.get("on_error", "block") or "block"
        hook.timeout_ms = int(spec.get("timeout_ms", 30000) or 30000)
        if isinstance(spec.get("env"), dict):
            hook.env = spec["env"]
        hook.enabled = True  # 随技能启用
        affected.append(hook)

    db.flush()
    return affected


def apply_skill_enabled(db: Session, skill: Skill, enabled: bool) -> list[Hook]:
    """统一处理技能启用/停用：更新 enabled 并同步声明式 Hook。"""
    skill.enabled = enabled
    return sync_declared_hooks(db, skill)
