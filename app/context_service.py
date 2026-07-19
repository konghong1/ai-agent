from __future__ import annotations

"""统一上下文与长期记忆子系统（ADR-021 / 022 / 023）。

设计目标（详见 designs/final-unified-context-memory-architecture.md）：
在一个「模型窗口 − 预留回复」的统一预算下装配：
    [system + pinned] + [记忆召回: Retrieval Reflex 指针 + 语义回忆]
    + [会话摘要] + [最近 K 轮原样] + [当前轮]

关键约束（来自项目铁律）：
- 所有改动默认关闭（settings 开关），开启前不影响现有行为。
- Message 原始行永不删除：压缩只改变「喂给 LLM 的视图」，清空 summary 即恢复。
- 分词中文-aware（替换 services.py 旧 len//3.5 对中文低估 ~5× 的启发式）。
- Retrieval Reflex 零 LLM、确定性、fail-open、有上限（gbrain 思路）。
- 压缩 summarizer 以可注入 Callable 形式传入，便于测试与替换模型。
"""

import logging
import os
import re
from dataclasses import dataclass
from typing import Callable, Optional

from sqlalchemy import or_, select

from app.memory import MemoryStore
from app.models import Message, ThreadContextState, UserMemory
from app.settings import get_settings

logger = logging.getLogger(__name__)


# 已知模型的上下文窗口（token）。未知模型回退到 settings.context_service_model_window。
_MODEL_WINDOWS: dict[str, int] = {
    "gpt-4o": 128_000, "gpt-4o-mini": 128_000, "gpt-4-turbo": 128_000,
    "gpt-3.5-turbo": 16_385, "o1": 200_000, "o3": 200_000,
    "claude-3-5-sonnet": 200_000, "claude-3-opus": 200_000, "claude-3-haiku": 200_000,
    "deepseek-chat": 64_000, "deepseek-reasoner": 64_000,
    "qwen-max": 32_000, "qwen-plus": 131_072, "qwen-turbo": 131_072,
    "gemini-1.5-pro": 2_000_000, "gemini-2.0-flash": 1_000_000,
    "agnes-2.0-flash": 128_000, "agnes-image-2": 128_000, "agnes-video-v2.0": 128_000,
}

# 零 LLM 实体抽取（precision-biased，v1）：只匹配高置信偏好/实体短语，避免噪声。
_ENTITY_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"我喜欢\s*([^\s，。,.\n]{1,24})"),
    re.compile(r"我的\s*([^\s，。,.\n]{1,24})"),
    re.compile(r"记住[:：]\s*(.+)"),
    re.compile(r"@([A-Za-z][\w\-]{1,30})"),
]


def estimate_tokens(text: str) -> int:
    """中文-aware token 估算。

    优先 tiktoken cl100k_base（精确）；缺失/离线时回退启发式：
    CJK 字符约 1 token/字，其余约 1 token/4 字符（对中文不再低估 ~5×）。
    """
    if not text:
        return 0
    try:
        import tiktoken

        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        cjk = sum(1 for c in text if "一" <= c <= "鿿")
        other = len(text) - cjk
        return cjk + max(1, other // 4)


def model_window(model_name: Optional[str]) -> int:
    """返回模型上下文窗口 token 数；未知模型用 settings 兜底值。"""
    settings = get_settings()
    if model_name:
        lowered = model_name.lower()
        for key, win in _MODEL_WINDOWS.items():
            if key.lower() in lowered:
                return win
    return settings.context_service_model_window


@dataclass
class BuildOptions:
    """ContextService.build 的可选参数。"""

    recent_turns: int = 10
    reserved_reply_ratio: float = 0.25
    reflex_cap: int = 6
    summarizer: Optional[Callable[[str], str]] = None
    enable_reflex: bool = False
    enable_memory_recall: bool = False
    enable_gap_analysis: bool = False
    enable_rrf: bool = False
    recall_k: int = 4


class ContextService:
    """统一上下文装配器。无网络调用；summarizer 由调用方注入。"""

    def __init__(self, db, store=None):
        self.db = db
        self.store = store

    # ------------------------------------------------------------------
    # 对外入口
    # ------------------------------------------------------------------
    def build(
        self,
        thread,
        user_id: int,
        current_text: str,
        system_prompt: str,
        opts: BuildOptions,
        model_name: Optional[str] = None,
    ) -> list[dict]:
        """返回装配好的消息列表（dict: {role, content}），供调用方转 LC 消息。"""
        settings = get_settings()
        window = model_window(model_name)
        budget = int(window * (1 - opts.reserved_reply_ratio))

        # 1) pinned system（常驻，不可压缩）
        messages: list[dict] = [{"role": "system", "content": system_prompt or ""}]
        used = estimate_tokens(system_prompt or "")

        # 2) 记忆召回（gbrain: brain-first + Retrieval Reflex + 语义回忆）
        mem_parts: list[str] = []
        # 2-pre) Workspace Memory Bridge (ADR-024)：项目级策展记忆常驻注入，
        #        跨会话生效，优先级最高（置于记忆块最前）。
        if getattr(settings, "enable_workspace_memory", False):
            ws = self._workspace_memory()
            if ws:
                mem_parts.append(ws)
        # 2a) L0 身份常驻（不依赖当前轮文本，始终注入，capped）
        core = self._core_memory(user_id)
        if core:
            mem_parts.append(core)
        # 2a-2) 用户长期画像（ADR-025 Tier1）：跨会话无条件常驻注入，
        #       与当前消息内容无关，保证新会话任意首句都能带上用户偏好/事实。
        if getattr(settings, "enable_user_profile_memory", False):
            prof = self._user_profile_memory(user_id)
            if prof:
                mem_parts.append(prof)

        reflex_pts: list[str] = []
        if opts.enable_reflex:
            reflex_pts = self._retrieval_reflex(user_id, current_text, opts.reflex_cap)
        recall_hits: list[dict] = []
        if opts.enable_memory_recall:
            recall_hits = self._semantic_recall(user_id, current_text, opts.recall_k)

        if opts.enable_rrf and (reflex_pts or recall_hits):
            fused = self._rrf_fuse(reflex_pts, recall_hits, opts.reflex_cap)
            if fused:
                mem_parts.append(fused)
        else:
            if reflex_pts:
                mem_parts.append("用户记忆（精简指针，非全文）：\n" + "\n".join(reflex_pts))
            if recall_hits:
                mem_parts.append("相关长期记忆：\n" + "\n".join(h["content"] for h in recall_hits))

        # 2b) Gap analysis（P7，可选）：召回不足时诚实告知模型「无已知偏好」
        if opts.enable_gap_analysis:
            gap = self._gap_note(current_text, reflex_pts, recall_hits)
            if gap:
                mem_parts.append(gap)

        if mem_parts:
            mem_block = "\n\n".join(mem_parts)
            messages.append({"role": "system", "content": mem_block})
            used += estimate_tokens(mem_block)

        # 3) 会话内摘要（先前压缩结果）
        state = self._get_state(thread.id)
        if state and state.summary:
            summary_block = f"[早期对话摘要]\n{state.summary}"
            messages.append({"role": "system", "content": summary_block})
            used += estimate_tokens(summary_block)

        # 4) 最近 K 轮原样 + 5) 窗口外旧轮按需压缩
        stored = list(self.db.scalars(
            select(Message).where(Message.thread_id == thread.id).order_by(Message.created_at)
        ))
        conv = [m for m in stored if m.role in ("user", "assistant")]
        recent = conv[-opts.recent_turns:] if opts.recent_turns > 0 else conv
        recent_ids = {m.id for m in recent}
        older = [m for m in conv if m.id not in recent_ids]

        recent_tokens = sum(estimate_tokens(m.content) for m in recent)
        older_tokens = sum(estimate_tokens(m.content) for m in older)

        if older and used + recent_tokens + older_tokens > budget:
            # 增量压缩：只折叠「上次压缩点之后、本次窗口之外」的旧轮
            new_older = [m for m in older if (state is None or state.last_compacted_msg_id is None or m.id > state.last_compacted_msg_id)]
            to_summarize = "\n".join(f"{m.role}: {m.content}" for m in new_older) or \
                           "\n".join(f"{m.role}: {m.content}" for m in older)
            new_summary: Optional[str] = None
            if opts.summarizer:
                try:
                    new_summary = opts.summarizer(to_summarize)
                except Exception as exc:  # 降级：滑动窗口丢弃，绝不阻塞用户
                    logger.warning("Compaction summarizer failed; sliding-window fallback: %s", exc)
                    new_summary = None
            if new_summary:
                merged = f"{state.summary}\n{new_summary}" if (state and state.summary) else new_summary
                self._save_state(thread.id, user_id, merged, older[-1].id)
                messages = self._replace_summary(messages, merged)
            else:
                # 滑动窗口降级：直接丢弃旧轮，仅保留最近 K 轮
                older = []
                logger.info("Sliding-window fallback: dropped %d older turns (no summarizer).", len(older))

        out = list(messages)
        for m in recent:
            out.append({"role": m.role, "content": m.content})
        return out

    # ------------------------------------------------------------------
    # Workspace Memory Bridge (ADR-024)
    # ------------------------------------------------------------------
    def _workspace_memory(self) -> str:
        """读取项目级长期记忆文件 (.workbuddy/memory/MEMORY.md) 并注入上下文。

        该文件由 AI 编码会话在开发过程中策展，沉淀项目铁律 / 技术栈 /
        架构约束 / 用户偏好等高价值信息。失败静默返回空串，绝不阻塞聊天主链路。

        决策（ADR-024）：
        - 只读不写：不与 UserMemory 表耦合，保持人工策展质量。
        - token 上限：超预算时按字符比例截断，保留文件头部（铁律在开头）。
        - 容错：文件缺失 / 读失败 / 未启用开关 → 返回空串。
        """
        try:
            settings = get_settings()
            path = getattr(settings, "workspace_memory_path", "")
            if not path or not os.path.exists(path):
                return ""
            with open(path, "r", encoding="utf-8") as f:
                content = f.read().strip()
            if not content:
                return ""
            header = "【项目长期记忆（来自 .workbuddy/memory/MEMORY.md，跨会话常驻）】\n"
            block = header + content
            est = estimate_tokens(block)
            max_tok = getattr(settings, "workspace_memory_max_tokens", 6000)
            if est > max_tok:
                # 中文约 1 token/字；按比例截断，保留开头（铁律/技术栈在文件头部）。
                max_chars = int(max_tok * 0.7)
                truncated = content[:max_chars]
                block = header + truncated + "\n\n[注：项目记忆超长已截断，完整内容见 MEMORY.md]"
            return block
        except Exception as exc:
            logger.warning("Workspace memory load skipped: %s", exc)
            return ""

    # ------------------------------------------------------------------
    # L0 身份常驻记忆（不依赖当前轮文本，始终注入）
    # ------------------------------------------------------------------
    def _core_memory(self, user_id: int) -> str:
        try:
            mems = self.db.scalars(
                select(UserMemory)
                .where(UserMemory.user_id == user_id, UserMemory.status == "active",
                       UserMemory.layer == 0)
                .order_by(UserMemory.importance.desc())
                .limit(10)
            ).all()
        except Exception:
            return ""
        if not mems:
            return ""
        lines = [f"[身份] {m.key}: {(m.value or '')[:120]}" for m in mems]
        return "用户身份（常驻）：\n" + "\n".join(lines)

    # ------------------------------------------------------------------
    # 用户长期画像（ADR-025 Tier1，跨会话无条件常驻）
    # ------------------------------------------------------------------
    def _user_profile_memory(self, user_id: int) -> str:
        """跨会话常驻用户画像（Tier1, ADR-025）。

        与当前轮消息内容**无关**，无条件加载该用户 `status='active'` 且
        `layer >= 1`（偏好/事实/纠正）的记忆，按 importance 降序，token 上限截断，
        作为 system 记忆块注入。保证新会话任意首句都能带上长期记忆。

        设计取舍（见 ADR-025）：
        - 确定性、零 LLM、不依赖触发词或 embedding，跨会话召回 100% 生效。
        - 预算感知：token 上限 + 条数上限，绝不挤占对话与回复窗口。
        - 容错：DB 异常 → 返回空串，绝不阻塞聊天主链路（与 _core_memory 一致）。
        - 多租户：已按 user_id 隔离，无跨用户泄漏风险。
        """
        try:
            settings = get_settings()
            cap_tokens = getattr(settings, "user_profile_max_tokens", 2000)
            cap_count = getattr(settings, "user_profile_count_cap", 30)
            mems = self.db.scalars(
                select(UserMemory)
                .where(
                    UserMemory.user_id == user_id,
                    UserMemory.status == "active",
                    UserMemory.layer >= 1,
                    UserMemory.mem_type.in_(["preference", "fact", "correction"]),
                )
                .order_by(UserMemory.importance.desc())
                .limit(cap_count)
            ).all()
            if not mems:
                return ""
            lines: list[str] = []
            used = 0
            for m in mems:
                val = (m.value or "")[:200]
                line = f"- {m.key or '(未命名)'}：{val}"
                t = estimate_tokens(line)
                if used + t > cap_tokens:
                    break
                lines.append(line)
                used += t
            if not lines:
                return ""
            return "用户长期偏好与事实（跨会话常驻，无需重复提及即生效）：\n" + "\n".join(lines)
        except Exception as exc:
            logger.warning("user profile memory load skipped: %s", exc)
            return ""

    # ------------------------------------------------------------------
    # Retrieval Reflex（gbrain，零 LLM 确定性指针层）
    # ------------------------------------------------------------------
    def _retrieval_reflex(self, user_id: int, text: str, cap: int) -> list[str]:
        if not text:
            return []
        cands = self._extract_entities(text)
        if not cands:
            return []
        # 拉取该用户全部 active 记忆（v1 规模可控；规模化后改用倒排/embedding 预筛）。
        mems = self.db.scalars(
            select(UserMemory)
            .where(UserMemory.user_id == user_id, UserMemory.status == "active")
            .order_by(UserMemory.importance.desc())
            .limit(500)
        ).all()
        if not mems:
            return []

        pointers: list[str] = []
        used_mems: set[int] = set()
        for ent in cands:
            if len(pointers) >= cap:
                break
            for mem in mems:
                if mem.id in used_mems:
                    continue
                if self._matches(mem, ent):
                    synopsis = (mem.value or "")[:120]
                    pointers.append(f"[记忆] {mem.key}: {synopsis}")
                    used_mems.add(mem.id)
                    break
        return pointers

    @staticmethod
    def _extract_entities(text: str) -> list[str]:
        out: list[str] = []
        for pat in _ENTITY_PATTERNS:
            for mt in pat.finditer(text):
                ent = (mt.group(1) if mt.lastindex else mt.group(0)).strip()
                if ent:
                    out.append(ent)
        # 去重保序
        seen: set[str] = set()
        return [e for e in out if not (e in seen or seen.add(e))]

    @staticmethod
    def _bigrams(s: str) -> set[str]:
        s = re.sub(r"\s+", "", s)
        if len(s) <= 1:
            return {s}
        return {s[i:i + 2] for i in range(len(s) - 1)}

    @staticmethod
    def _matches(mem: "UserMemory", ent: str) -> bool:
        """确定性匹配：ASCII handle 用包含；中文用字符 bigram 重叠（不要求连续子串）。"""
        key = mem.key or ""
        val = mem.value or ""
        if re.fullmatch(r"[A-Za-z0-9_\-]+", ent):
            e = ent.lower()
            return e in key.lower() or e in val.lower()
        eb = ContextService._bigrams(ent)
        mb = ContextService._bigrams(key) | ContextService._bigrams(val)
        return bool(eb & mb)

    # ------------------------------------------------------------------
    # 语义回忆（Chroma 每用户集合，真实实现；默认关，fail-open）
    # ------------------------------------------------------------------
    def _semantic_recall(self, user_id: int, text: str, k: int) -> list[dict]:
        try:
            store = self.store or MemoryStore()
            hits = store.query(user_id, text, k=k)
            return hits
        except Exception as exc:
            logger.warning("Semantic recall skipped (disabled or unavailable): %s", exc)
            return []

    # ------------------------------------------------------------------
    # P7: RRF 融合（Reflex 指针 + Chroma 结果统一打分）& Gap analysis
    # ------------------------------------------------------------------
    def _rrf_fuse(self, reflex_pts: list[str], recall_hits: list[dict], cap: int) -> str:
        k = 60  # RRF 常数
        scored: list[tuple[str, float]] = []
        for rank, p in enumerate(reflex_pts):
            # Reflex 是确定性高精度层，权重略高（乘 1.5）
            scored.append((p, 1.5 * (1.0 / (k + rank + 1))))
        for rank, h in enumerate(recall_hits):
            content = h.get("content", "")
            if content:
                scored.append((f"[记忆] {content}", 1.0 / (k + rank + 1)))
        scored.sort(key=lambda x: -x[1])
        lines = [s for s, _ in scored[:cap]]
        return "用户记忆（融合检索，非全文）：\n" + "\n".join(lines) if lines else ""

    def _gap_note(self, text: str, reflex_pts: list[str], recall_hits: list[dict]) -> str:
        """召回不足时，诚实告诉模型：对当前提及的实体无已知记忆（防幻觉）。"""
        if reflex_pts or recall_hits:
            return ""
        cands = self._extract_entities(text)
        if not cands:
            return ""
        topics = "、".join(cands[:3])
        return f"[注] 当前记忆库对「{topics}」无已知用户偏好或事实，请按通用最佳方式回应，不要臆测用户习惯。"

    # ------------------------------------------------------------------
    # 诊断预览（供 E2E 验证，无需 LLM）
    # ------------------------------------------------------------------
    def preview_memory(self, user_id: int, text: str, opts: BuildOptions) -> dict:
        """返回各记忆块文本，便于端到端验证注入是否正确（不消耗 LLM）。"""
        out: dict[str, str] = {}
        pts: list[str] = []
        hits: list[dict] = []
        core = self._core_memory(user_id)
        if core:
            out["core"] = core
        if opts.enable_reflex:
            pts = self._retrieval_reflex(user_id, text, opts.reflex_cap)
            if pts:
                out["reflex"] = "用户记忆（精简指针，非全文）：\n" + "\n".join(pts)
        if opts.enable_memory_recall:
            hits = self._semantic_recall(user_id, text, opts.recall_k)
            if hits:
                out["recall"] = "相关长期记忆：\n" + "\n".join(h["content"] for h in hits)
        if opts.enable_gap_analysis:
            gap = self._gap_note(text, pts, hits)
            if gap:
                out["gap"] = gap
        return out

    # ------------------------------------------------------------------
    # 状态读写（ThreadContextState，独立表，可逆）
    # ------------------------------------------------------------------
    def _get_state(self, thread_id: str) -> Optional[ThreadContextState]:
        return self.db.scalar(
            select(ThreadContextState).where(ThreadContextState.thread_id == thread_id)
        )

    def _save_state(self, thread_id: str, user_id: int, summary: str, last_compacted_msg_id: int) -> None:
        state = self._get_state(thread_id)
        if state is None:
            state = ThreadContextState(thread_id=thread_id, user_id=user_id)
            self.db.add(state)
        state.summary = summary
        state.last_compacted_msg_id = last_compacted_msg_id
        self.db.flush()

    @staticmethod
    def _replace_summary(messages: list[dict], merged: str) -> list[dict]:
        out: list[dict] = []
        replaced = False
        for m in messages:
            if m.get("role") == "system" and str(m.get("content", "")).startswith("[早期对话摘要]"):
                if not replaced:
                    out.append({"role": "system", "content": f"[早期对话摘要]\n{merged}"})
                    replaced = True
                # 跳过旧摘要，避免重复
            else:
                out.append(m)
        if not replaced:
            out.append({"role": "system", "content": f"[早期对话摘要]\n{merged}"})
        return out
