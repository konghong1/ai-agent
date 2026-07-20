"""把用户启用的远端 MCP 工具，封装成聊天可调用能力。

- get_enabled_remote_servers: 取该用户已启用且 transport in {sse,http} 的 MCP。
- build_mcp_langchain_tools: 为每个 MCP 工具生成 LangChain StructuredTool，
  名称前缀 mcp_{server}_{tool}，参数由 inputSchema 动态建模。
- get_mcp_tool_catalog: 生成「可用 MCP 工具」文本，注入系统提示（避免把完整 schema 塞满上下文）。
"""
from __future__ import annotations

import logging
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field as PydanticField, create_model
from sqlalchemy import select

from app.mcp_client import MCPConnectionManager, MCPClientError
from app.models import McpServer

logger = logging.getLogger(__name__)


def _json_type_to_python(t: str) -> Any:
    return {
        "string": str,
        "number": float,
        "integer": int,
        "boolean": bool,
        "array": list,
        "object": dict,
    }.get(t, Any)


def _build_args_model(schema: dict) -> type[BaseModel]:
    props = schema.get("properties", {})
    required = set(schema.get("required", []))
    fields: dict[str, Any] = {}
    for name, spec in props.items():
        py_type = _json_type_to_python(spec.get("type", "string"))
        default = ... if name in required else None
        fields[name] = (py_type, PydanticField(default=default, description=spec.get("description", "")))
    return create_model("MCPToolArgs", **fields)


def get_enabled_remote_servers(db, user_id: int) -> list[McpServer]:
    return list(
        db.scalars(
            select(McpServer).where(
                McpServer.user_id == user_id,
                McpServer.enabled == True,
                McpServer.transport.in_(["sse", "http"]),
            )
        )
    )


def build_mcp_langchain_tools(db, user_id: int) -> list[StructuredTool]:
    tools: list[StructuredTool] = []
    for server in get_enabled_remote_servers(db, user_id):
        try:
            mcp_tools = MCPConnectionManager.get_tools(user_id, server)
        except Exception as e:
            logger.warning("MCP list_tools failed server=%s: %s", server.name, e)
            continue
        allow = server.tool_allowlist or []
        for t in mcp_tools:
            tname = t.get("name")
            if not tname:
                continue
            if allow and tname not in allow:
                continue

            def _make(server_id: int = server.id, tname: str = tname):
                def _run(**kwargs):
                    srv = db.get(McpServer, server_id)
                    if srv is None:
                        return "[error] MCP server not found"
                    res, _dur, err = MCPConnectionManager.call_tool(user_id, srv, tname, kwargs)
                    if err:
                        return f"[MCP error] {err}"
                    return res or ""

                return _run

            try:
                args_model = _build_args_model(t.get("inputSchema", {}))
            except Exception as e:
                logger.warning("build args model failed tool=%s: %s", tname, e)
                continue
            tool_name = f"mcp_{server.name}_{tname}".replace("-", "_").replace(" ", "_")
            lc_tool = StructuredTool(
                name=tool_name,
                description=(t.get("description") or f"MCP tool {tname} from {server.name}")[:1000],
                args_schema=args_model,
                func=_make(),
            )
            tools.append(lc_tool)
    return tools


def get_mcp_tool_catalog(db, user_id: int) -> str:
    lines: list[str] = []
    for server in get_enabled_remote_servers(db, user_id):
        try:
            mcp_tools = MCPConnectionManager.get_tools(user_id, server)
        except Exception:
            continue
        allow = server.tool_allowlist or []
        names = [t.get("name") for t in mcp_tools if (not allow or t.get("name") in allow)]
        if names:
            lines.append(f"- MCP server '{server.name}': tools {', '.join(names)}")
    if not lines:
        return ""
    return (
        "Available MCP tools (remote, live data):\n"
        + "\n".join(lines)
        + "\n\n[TOOL USAGE RULE — highest priority / 最高优先级]\n"
        "If the user's request can be answered using one of the MCP tools listed above, you "
        "MUST call that tool to retrieve live data. 如果用户的问题可以由上述 MCP 工具回答，你必须调用对应"
        "工具获取实时数据。\n"
        "Do NOT answer from prior knowledge. 不要凭记忆回答。\n"
        "Do NOT respond with only a <blocks> choice stub such as 'search KB vs direct answer'. "
        "绝不只返回一个选项桩（如“搜索知识库 / 直接回答”），而必须调用工具或给出实质性回答。\n"
        "If unsure which tool to use, pick the one whose description best matches the request "
        "and call it."
    )
