"""安全闸门（Security Gate）。

用户配置的 MCP / Skill / Hook 在 *启用*（enabled=true）前必须先通过本闸门：
- 静态/策略校验（URL 协议、必填密钥、危险命令模式、事件合法性等）。
- 返回 SecurityReport；errors 非空则禁止启用。

注意：本模块只做静态策略校验。Phase 3 的「沙箱试跑」将在此处追加动态校验钩子。
"""
from __future__ import annotations

from pydantic import BaseModel


class SecurityReport(BaseModel):
    passed: bool = True
    errors: list[str] = []
    warnings: list[str] = []

    def add_error(self, msg: str) -> None:
        self.errors.append(msg)
        self.passed = False

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)

    def to_dict(self) -> dict:
        return self.model_dump()


_ALLOWED_HOOK_EVENTS = {
    "SessionStart",
    "UserPromptSubmit",
    "PreToolUse",
    "PostToolUse",
    "Stop",
    "SubagentStop",
    "Notification",
}

# 明确禁止的 Hook 命令危险模式（仅覆盖高置信度破坏性行为）。
_FORBIDDEN_HOOK_PATTERNS = [
    "rm -rf /",
    "mkfs",
    "dd if=",
    "curl ",
    "wget ",
    "sudo ",
]


def check_mcp_server(obj) -> SecurityReport:
    r = SecurityReport()
    transport = getattr(obj, "transport", "stdio")
    if transport in ("sse", "http"):
        url = getattr(obj, "url", "") or ""
        if not url:
            r.add_error("远端 MCP 必须配置 url")
        else:
            scheme = url.split("://", 1)[0].lower() if "://" in url else ""
            if scheme not in ("http", "https"):
                r.add_error(f"远端 MCP url 协议不被允许: '{scheme or 'unknown'}://'（仅允许 http/https）")
            elif scheme == "http":
                r.add_warning("远端 MCP url 为非加密 http，存在中间人风险")
        auth = getattr(obj, "auth_type", "none")
        if auth in ("bearer", "api_key") and not getattr(obj, "api_key", ""):
            r.add_error(f"auth_type={auth} 需要 api_key，但未提供")
    elif transport == "stdio":
        cmd = getattr(obj, "command", "") or ""
        if not cmd:
            r.add_error("stdio MCP 必须配置 command")
        if any(ch in cmd for ch in [";", "&&", "|", "$", "`"]):
            r.add_warning("command 含 shell 元字符，存在命令注入风险")
    else:
        r.add_error(f"未知 transport: {transport}")
    allow = getattr(obj, "tool_allowlist", None)
    if allow is not None and not isinstance(allow, list):
        r.add_error("tool_allowlist 必须是列表")
    return r


def check_skill(obj) -> SecurityReport:
    r = SecurityReport()
    source_type = getattr(obj, "source_type", "local")
    path = getattr(obj, "path", "") or ""
    if source_type == "repo":
        if path and not (
            path.startswith("https://")
            or path.startswith("git@")
            or path.endswith(".git")
        ):
            r.add_warning("skill repo 路径异常，建议为 https/git 仓库")
        if ".." in path or path.startswith("/"):
            r.add_error("skill path 试图逃出沙箱")
    return r


def check_hook(obj) -> SecurityReport:
    r = SecurityReport()
    cmd = getattr(obj, "command", "") or ""
    if not cmd.strip():
        r.add_error("hook command 不能为空")
    low = cmd.lower()
    for pat in _FORBIDDEN_HOOK_PATTERNS:
        if pat in low:
            r.add_error(f"hook command 含禁止模式: '{pat.strip()}'")
    ev = getattr(obj, "event", "PreToolUse")
    if ev not in _ALLOWED_HOOK_EVENTS:
        r.add_error(f"未知 hook event: {ev}")
    to = getattr(obj, "timeout_ms", 30000) or 30000
    if not (500 <= to <= 600000):
        r.add_warning("hook timeout 超出建议范围 (500-600000ms)")
    # 沙箱试跑：静态校验通过后，在真实沙箱内跑一次探针，确认能产出合法决策 JSON。
    if r.passed and getattr(obj, "id", None) is not None:
        try:
            from app.hook_runner import sandbox_probe
            from app.settings import get_settings

            outcome = sandbox_probe(obj, get_settings())
            if outcome.error:
                r.add_error(f"沙箱试跑失败（Hook 无法正常运行，禁止启用）: {outcome.error[:200]}")
        except Exception as e:  # noqa: BLE001
            r.add_error(f"沙箱试跑异常: {e}")
    return r


def run_security_gate(entity_type: str, obj) -> SecurityReport:
    if entity_type == "mcp":
        return check_mcp_server(obj)
    if entity_type == "skill":
        return check_skill(obj)
    if entity_type == "hook":
        return check_hook(obj)
    r = SecurityReport()
    r.add_warning(f"未知实体类型: {entity_type}")
    return r
