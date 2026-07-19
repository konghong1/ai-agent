"""Hook 运行时：在 Agent 生命周期事件上执行用户 Hook（沙箱隔离）。

生命周期事件（与 Claude Code 对齐）：
    SessionStart / UserPromptSubmit / PreToolUse / PostToolUse /
    Stop / SubagentStop / Notification

Hook 脚本通过 stdin 接收 JSON payload，stdout 输出 JSON 决策：
    {"decision": "approve"}                      # 放行（默认）
    {"decision": "block",  "reason": "..."}      # 阻止（如 PreToolUse 拦截工具调用）
    {"decision": "modify", "data":   {...}}      # 修改输入/输出，data 由调用方解释

安全：
    - 仅启用且通过安全闸门（enable_hooks=true 且 enable_security_gate 通过）的 Hook 才会执行。
    - 进程级沙箱：资源限制（CPU/内存/文件大小）、网络隔离（best-effort unshare -n）、
      环境变量最小化（仅注入白名单 + 用户非敏感变量 + 解密后的敏感变量）。
    - on_error 策略（block/continue）实现 fail-closed。
    - 每次执行写入 ToolCallAudit 留痕（租户隔离）。
"""
from __future__ import annotations

import fnmatch
import json
import logging
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.crypto import decrypt_json
from app.models import Hook, ToolCallAudit
from app.settings import get_settings

logger = logging.getLogger("app.hook_runner")


_ALLOWED_ENV_KEYS = ("PATH", "LANG", "LC_ALL", "HOME", "TMPDIR", "PYTHONPATH")


@dataclass
class HookOutcome:
    hook_id: int
    event: str
    decision: str = "approve"          # approve | block | modify
    reason: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    duration_ms: int = 0

    def to_dict(self) -> dict:
        return {
            "hook_id": self.hook_id,
            "event": self.event,
            "decision": self.decision,
            "reason": self.reason,
            "data": self.data,
            "error": self.error,
            "duration_ms": self.duration_ms,
        }


def _match(matcher: str, tool_name: str) -> bool:
    """matcher 支持 glob（如 'mcp_*'），空 matcher 匹配所有。"""
    if not matcher:
        return True
    return fnmatch.fnmatch(tool_name, matcher)


def _build_env(hook: Hook) -> dict:
    env: dict[str, str] = {}
    for k in _ALLOWED_ENV_KEYS:
        if k in os.environ:
            env[k] = os.environ[k]
    if isinstance(hook.env, dict):
        env.update({str(k): str(v) for k, v in hook.env.items()})
    try:
        sec = decrypt_json(hook.secret_env)
        if isinstance(sec, dict):
            env.update({str(k): str(v) for k, v in sec.items()})
    except Exception as e:  # 解密失败不应阻断整个会话
        logger.warning("Hook %s 解密 secret_env 失败: %s", hook.id, e)
    return env


def _preexec_fn(limits: dict):
    def _p() -> None:
        import resource

        if limits.get("cpu"):
            resource.setrlimit(resource.RLIMIT_CPU, (limits["cpu"], limits["cpu"]))
        if limits.get("mem"):
            resource.setrlimit(resource.RLIMIT_AS, (limits["mem"], limits["mem"]))
        if limits.get("fsize"):
            resource.setrlimit(resource.RLIMIT_FSIZE, (limits["fsize"], limits["fsize"]))
        try:
            os.nice(10)
        except Exception:
            pass

    return _p


def _run_one(hook: Hook, payload: dict, settings, *, probe: bool = False) -> HookOutcome:
    start = time.time()
    outcome = HookOutcome(hook_id=hook.id, event=hook.event)
    try:
        env = _build_env(hook)

        # 输入体积上限：防超大 payload 撑爆子进程 stdin（万级并发下关键）。
        raw = json.dumps(payload, ensure_ascii=False)
        if len(raw.encode("utf-8")) > settings.hook_sandbox_max_input_bytes:
            raw = json.dumps({"_truncated": True, "event": hook.event}, ensure_ascii=False)
        stdin_data = raw.encode("utf-8")

        timeout = max(1.0, (hook.timeout_ms or 30000) / 1000.0)
        if probe:
            timeout = max(1.0, settings.hook_sandbox_probe_timeout_ms / 1000.0)
        limits = {
            "cpu": settings.hook_sandbox_cpu_secs,
            "mem": settings.hook_sandbox_mem_bytes,
            "fsize": settings.hook_sandbox_fsize_bytes,
        }
        cwd = settings.hook_sandbox_cwd
        if not cwd or not os.path.isdir(cwd):
            cwd = tempfile.gettempdir()

        mode = (settings.hook_sandbox_mode or "process").lower()
        if mode == "disabled":
            # 信任模式：不加资源/网络限制（仅超时），用于内部可信钩子。
            limits = {}
            use_network_block = False
        elif mode == "container":
            # 容器/gVisor 隔离尚未实现，告警回退 process。
            logger.warning("Hook %s 配置了 container 沙箱（未实现），回退 process", hook.id)
            use_network_block = settings.hook_sandbox_network_block
        else:  # process（默认）
            use_network_block = settings.hook_sandbox_network_block

        def _spawn(cmd):
            return subprocess.run(
                cmd,
                input=stdin_data,
                capture_output=True,
                env=env,
                timeout=timeout,
                preexec_fn=_preexec_fn(limits) if limits else None,
                cwd=cwd,
            )

        def _is_unshare_error(proc) -> bool:
            # unshare 自身未能建立隔离命名空间（如权限不足），应回退非隔离执行，
            # 而不是把这次失败当成 Hook 业务逻辑失败。
            return proc.returncode != 0 and b"unshare" in (proc.stderr or b"")

        cmd_str = hook.command
        if use_network_block and shutil.which("unshare"):
            try:
                proc = _spawn(["unshare", "-n", "sh", "-c", cmd_str])
                if _is_unshare_error(proc):
                    logger.warning("Hook %s 网络隔离不可用，回退非隔离执行", hook.id)
                    proc = _spawn(["sh", "-c", cmd_str])
            except (FileNotFoundError, PermissionError, OSError) as e:
                logger.warning("Hook %s 沙箱不可用(%s)，回退非隔离执行", hook.id, e)
                proc = _spawn(["sh", "-c", cmd_str])
        else:
            proc = _spawn(["sh", "-c", cmd_str])

        outcome.duration_ms = int((time.time() - start) * 1000)

        # 输出体积上限：只读取前 N 字节，避免恶意/异常输出撑爆内存。
        out_bytes = (proc.stdout or b"")[: settings.hook_sandbox_max_output_bytes]
        err_bytes = (proc.stderr or b"")[:500]

        if proc.returncode != 0:
            outcome.error = f"exit={proc.returncode} {err_bytes.decode('utf-8','replace')}".strip()
            outcome.decision = "block" if hook.on_error == "block" else "approve"
            outcome.reason = outcome.error
            return outcome

        out = out_bytes.decode("utf-8", "replace").strip()
        if out:
            try:
                parsed = json.loads(out)
                d = (parsed.get("decision") or "approve").lower()
                if d in ("approve", "block", "modify"):
                    outcome.decision = d
                outcome.reason = str(parsed.get("reason", ""))
                if isinstance(parsed.get("data"), dict):
                    outcome.data = parsed["data"]
                elif parsed.get("data") is not None:
                    outcome.data = {"value": parsed["data"]}
            except json.JSONDecodeError:
                outcome.decision = "approve"
                outcome.reason = "hook 输出非 JSON，按 approve 处理"
        return outcome
    except subprocess.TimeoutExpired:
        outcome.duration_ms = int((time.time() - start) * 1000)
        outcome.error = f"timeout after {timeout}s"
        outcome.decision = "block" if hook.on_error == "block" else "approve"
        outcome.reason = outcome.error
        return outcome
    except Exception as e:  # noqa: BLE001
        outcome.duration_ms = int((time.time() - start) * 1000)
        outcome.error = f"exec error: {e}"
        outcome.decision = "block" if hook.on_error == "block" else "approve"
        outcome.reason = outcome.error
        return outcome


def sandbox_probe(hook: Hook, settings) -> HookOutcome:
    """在真实沙箱内用探针 payload 跑一次 Hook，验证可产出合法决策 JSON。

    用于安全闸门 dry-run：无法正常运行的 Hook 不应被启用。
    """
    probe_payload = {
        "event": hook.event,
        "probe": True,
        "session_id": "security-gate-probe",
        "tool_name": "probe",
        "tool_args": {},
    }
    return _run_one(hook, probe_payload, settings, probe=True)


def _write_audit(db: Session, hook: Hook, payload: dict, outcome: HookOutcome) -> None:
    try:
        status = "blocked" if outcome.decision == "block" else ("error" if outcome.error else "ok")
        db.add(
            ToolCallAudit(
                user_id=hook.user_id,
                session_id=str(payload.get("session_id", "")),
                tool_type="hook",
                target=f"{hook.event}:{hook.id}",
                tool_name=hook.event,
                duration_ms=outcome.duration_ms,
                status=status,
                hook_decision=outcome.decision,
                error=outcome.error,
            )
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("Hook 审计写入失败: %s", e)


def run_hooks(
    event: str,
    user_id: int,
    db: Session,
    payload: dict,
    matcher: str | None = None,
) -> list[HookOutcome]:
    """执行某生命周期事件下、当前用户已启用且匹配 matcher 的全部 Hook。

    返回结果列表；调用方据 decision 决定放行/拦截/修改。
    """
    settings = get_settings()
    if not settings.enable_hooks:
        return []
    hooks = db.scalars(
        select(Hook).where(Hook.user_id == user_id, Hook.event == event, Hook.enabled.is_(True))
    ).all()
    if not hooks:
        return []
    outcomes: list[HookOutcome] = []
    for hook in hooks:
        if matcher is not None and not _match(hook.matcher or "", matcher):
            continue
        outcome = _run_one(hook, payload, settings)
        outcomes.append(outcome)
        _write_audit(db, hook, payload, outcome)
    db.commit()
    return outcomes


def first_blocking(outcomes: list[HookOutcome]) -> HookOutcome | None:
    """返回第一个 decision=block 的结果（如有）。"""
    for o in outcomes:
        if o.decision == "block":
            return o
    return None
