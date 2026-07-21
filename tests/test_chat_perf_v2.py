"""聊天每轮性能优化 (plan-chat-perf-v2) 单元测试。

覆盖：§1.1 工具池缓存 + 事件失效 + 自包含调用；§1.2 Catalog 瘦身；
§1.3 KB 前置门控；§2.1 Intent Router 三档；§2.2 按需 KB 工具；§2.3 top-k 剪枝。

全部离线运行（mock 掉 MCP 网络调用 / LLM），不依赖外部 provider / embedding。
DB 走 conftest 的临时 SQLite（绝不触碰真实 agent.db / ai_agent）。
"""

import pytest
from sqlalchemy import select

from app.agent import (
    Tier,
    _needs_knowledge_base,
    _route_intent,
    _prune_tools,
    ask_agent_sync,
)
from app.context_service import ContextService as _RealContextService
from app.core.database import SessionLocal
from app.mcp_tools import (
    build_mcp_langchain_tools,
    invalidate_tool_pool,
    _call_mcp_tool,
    get_mcp_tool_catalog,
)
from app.models import McpServer
from app.settings import get_settings


# ──────────────────────────────────────────────────────────────────────────
# §1.3 KB 前置门控
# ──────────────────────────────────────────────────────────────────────────

def test_needs_knowledge_base():
    # 过短
    assert _needs_knowledge_base("") is False
    assert _needs_knowledge_base("你好") is False  # len < 4
    # 含实体（我喜欢 X）
    assert _needs_knowledge_base("我喜欢蓝色") is True
    # 含实体（我的 X）
    assert _needs_knowledge_base("我的偏好是简体中文") is True
    # 显式召回意图
    assert _needs_knowledge_base("我记得我们之前讨论过这个") is True
    # 无实体/无召回意图（应跳过 KB）
    assert _needs_knowledge_base("今天天气怎么样") is False


# ──────────────────────────────────────────────────────────────────────────
# §2.1 Fast Intent Router
# ──────────────────────────────────────────────────────────────────────────

def test_route_intent_tiers():
    # T0 DIRECT：平凡问候，无 agent KB
    assert _route_intent("你好", get_settings(), agent_has_kb=False) == Tier.DIRECT
    assert _route_intent("在吗", get_settings(), agent_has_kb=False) == Tier.DIRECT
    assert _route_intent("谢谢", get_settings(), agent_has_kb=False) == Tier.DIRECT
    # 长问候不算 T0（仍含问候词但 >12 字）
    assert _route_intent("你好，帮我查一下北京天气", get_settings(), agent_has_kb=False) != Tier.DIRECT
    # T1 TOOLS：实时数据意图且无 KB 需求
    assert _route_intent("帮我查一下北京到上海的票价", get_settings(), agent_has_kb=False) == Tier.TOOLS
    # 有 KB 需求的实时语句 → FULL（不应误判为 TOOLS 而丢 KB）
    assert _route_intent("查一下我之前说的偏好", get_settings(), agent_has_kb=False) == Tier.FULL
    # agent 有强制 KB 绑定时，问候不短路为 T0（保留 RAG 上下文）
    assert _route_intent("你好", get_settings(), agent_has_kb=True) == Tier.FULL
    # 普通语句 → FULL（保守兜底）
    assert _route_intent("讲个笑话", get_settings(), agent_has_kb=False) == Tier.FULL


# ──────────────────────────────────────────────────────────────────────────
# §2.3 top-k 工具剪枝
# ──────────────────────────────────────────────────────────────────────────

class _FakeTool:
    def __init__(self, name, description=""):
        self.name = name
        self.description = description


def test_prune_tools_keeps_relevant():
    weather = _FakeTool("mcp_srv_weather", "查询天气和天气预报")
    db_tool = _FakeTool("mcp_srv_dbquery", "数据库查询工具")
    others = [_FakeTool(f"tool_{i}", f"无关工具描述 {i}") for i in range(10)]
    tools = [weather, db_tool] + others  # 12 个
    query = "查询北京天气"
    pruned = _prune_tools(tools, query, top_k=8)
    assert len(pruned) == 8
    # 相关工具应保留（描述与 query 有词重叠）
    names = {t.name for t in pruned}
    assert weather.name in names
    # 少于等于 top_k 时不剪枝
    assert _prune_tools(tools[:5], query, top_k=8) == tools[:5]


# ──────────────────────────────────────────────────────────────────────────
# §1.1 工具池缓存 + 事件失效 + 自包含调用
# ──────────────────────────────────────────────────────────────────────────

FAKE_TOOLS = [{
    "name": "ping",
    "description": "ping the remote server",
    "inputSchema": {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]},
}]


@pytest.fixture
def fake_server():
    invalidate_tool_pool()  # 清空模块级缓存，保证测试隔离
    db = SessionLocal()
    # 临时 SQLite 跨测试共享：先清掉同 user 的旧行，避免唯一约束冲突。
    for old in db.scalars(select(McpServer).where(McpServer.user_id == 991)).all():
        db.delete(old)
    db.commit()
    srv = McpServer(
        user_id=991, name="fakesrv", transport="http", enabled=True,
        url="http://localhost:9999", tool_allowlist=[],
    )
    db.add(srv)
    db.commit()
    yield srv
    db.close()
    invalidate_tool_pool()


def test_tool_pool_cache_hit_and_invalidation(fake_server, monkeypatch):
    with monkeypatch.context() as m:
        m.setattr("app.mcp_tools.MCPConnectionManager.get_tools", lambda uid, srv: FAKE_TOOLS)
        t1 = build_mcp_langchain_tools(SessionLocal(), 991)
        t2 = build_mcp_langchain_tools(SessionLocal(), 991)
        # 命中缓存：返回同一 list 对象（零重建）
        assert t1 is t2
        assert len(t1) == 1
        # 事件失效后：返回新 list（重建）
        invalidate_tool_pool(991)
        t3 = build_mcp_langchain_tools(SessionLocal(), 991)
        assert t3 is not t1


def test_call_mcp_tool_self_contained(fake_server, monkeypatch):
    """缓存工具跨请求复用：调用时必须自开 session，不依赖请求作用域 db。"""
    sid = fake_server.id
    with monkeypatch.context() as m:
        m.setattr(
            "app.mcp_tools.MCPConnectionManager.call_tool",
            lambda uid, srv, name, args: ("pong", 5, None),
        )
        out = _call_mcp_tool(991, sid, "ping", {"q": "hi"})
        assert out == "pong"


def test_tool_pool_respects_config_hash_change(fake_server, monkeypatch):
    """配置变更（allowlist）导致 hash 不匹配 → 即使未显式失效也重建。"""
    with monkeypatch.context() as m:
        m.setattr("app.mcp_tools.MCPConnectionManager.get_tools", lambda uid, srv: FAKE_TOOLS)
        t1 = build_mcp_langchain_tools(SessionLocal(), 991)
        # 改变 allowlist（配置变更）
        db = SessionLocal()
        srv = db.get(McpServer, fake_server.id)
        srv.tool_allowlist = ["ping"]
        db.commit()
        db.close()
        t2 = build_mcp_langchain_tools(SessionLocal(), 991)
        assert t2 is not t1  # hash 不匹配 → 重建


# ──────────────────────────────────────────────────────────────────────────
# §1.2 Catalog 瘦身
# ──────────────────────────────────────────────────────────────────────────

def test_catalog_slim(fake_server, monkeypatch):
    long_desc = "x" * 200
    with monkeypatch.context() as m:
        m.setattr(
            "app.mcp_tools.MCPConnectionManager.get_tools",
            lambda uid, srv: [{"name": "ping", "description": long_desc}],
        )
        cat = get_mcp_tool_catalog(SessionLocal(), 991)
    assert "ping" in cat
    # 描述被截断到 60 字，不应包含完整 200 字
    assert long_desc not in cat
    # 最高优先级 TOOL USAGE RULE 保留
    assert "TOOL USAGE RULE" in cat


# ──────────────────────────────────────────────────────────────────────────
# §1.3 + §2.2 集成：ask_agent 内的 KB 门控 / 按需工具接线
# （mock LLM + ContextService，离线验证 BuildOptions 与工具注入）
# ──────────────────────────────────────────────────────────────────────────

class _FakeResp:
    content = "hi there"
    tool_calls = []


class _FakeLLM:
    def stream(self, msgs):
        yield type("C", (), {"content": "hi "})()
        yield type("C", (), {"content": "there"})()

    def invoke(self, msgs):
        return _FakeResp()

    def bind_tools(self, tools):
        return self


class _FakeCS:
    # KB 门控用到 ContextService._extract_entities（纯正则），委托给真实实现。
    _extract_entities = staticmethod(_RealContextService._extract_entities)

    def __init__(self, db):
        self.db = db

    def build(self, thread, user_id, current_text, system_prompt, opts, model_name=None):
        _FakeCS.last_opts = opts
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": current_text},
        ]


def _install_ask_agent_mocks(monkeypatch):
    monkeypatch.setattr("app.agent._create_llm_from_config", lambda *a, **k: _FakeLLM())
    monkeypatch.setattr(
        "app.agent._resolve_llm_config",
        lambda **k: type("C", (), {"model_name": "x", "provider_type": "openai"})(),
    )
    monkeypatch.setattr("app.context_service.ContextService", _FakeCS)


def test_ask_agent_kb_gate_skips_recall_for_trivial(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "enable_context_service", True)
    monkeypatch.setattr(settings, "enable_kb_gate", True)
    monkeypatch.setattr(settings, "enable_memory_recall", True)
    monkeypatch.setattr(settings, "enable_ondemand_kb", False)
    monkeypatch.setattr(settings, "enable_mcp_tools", False)
    monkeypatch.setattr(settings, "enable_skill_tools", False)
    _install_ask_agent_mocks(monkeypatch)

    db = SessionLocal()
    try:
        ask_agent_sync(db, user_id=1, agent_id=None, message="你好")
    finally:
        db.close()
    # 平凡轮：KB 门控应跳过自动语义回忆
    assert _FakeCS.last_opts.enable_memory_recall is False


def test_ask_agent_kb_gate_allows_recall_when_entity(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "enable_context_service", True)
    monkeypatch.setattr(settings, "enable_kb_gate", True)
    monkeypatch.setattr(settings, "enable_memory_recall", True)
    monkeypatch.setattr(settings, "enable_ondemand_kb", False)
    monkeypatch.setattr(settings, "enable_mcp_tools", False)
    monkeypatch.setattr(settings, "enable_skill_tools", False)
    _install_ask_agent_mocks(monkeypatch)

    db = SessionLocal()
    try:
        ask_agent_sync(db, user_id=1, agent_id=None, message="我喜欢蓝色")
    finally:
        db.close()
    # 含实体：门控放行，自动语义回忆开启
    assert _FakeCS.last_opts.enable_memory_recall is True


def test_ask_agent_ondemand_kb_tool_injected(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "enable_context_service", True)
    monkeypatch.setattr(settings, "enable_kb_gate", True)
    monkeypatch.setattr(settings, "enable_memory_recall", True)
    monkeypatch.setattr(settings, "enable_ondemand_kb", True)
    monkeypatch.setattr(settings, "enable_mcp_tools", False)
    monkeypatch.setattr(settings, "enable_skill_tools", False)
    _install_ask_agent_mocks(monkeypatch)

    requested = {}
    import app.agent as agent_mod

    def _fake_make(db, user_id, settings_):
        requested["called"] = True
        return _FakeTool("retrieve_knowledge", "kb")

    monkeypatch.setattr(agent_mod, "_make_retrieve_knowledge_tool", _fake_make)

    db = SessionLocal()
    try:
        ask_agent_sync(db, user_id=1, agent_id=None, message="你好")
    finally:
        db.close()
    # 开启 ondemand_kb：应请求注入 retrieve_knowledge 工具（替代自动回忆）
    assert requested.get("called") is True
