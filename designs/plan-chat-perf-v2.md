# 聊天每轮加载性能优化 · 设计实现方案（v2）

> 状态：设计稿（待评审）　|　日期：2026-07-20　|　作者：AI Agent Platform
> 关联：P0+P1+P2 流式/缓存/并行优化（已上线）、`learn-claude-code` harness 模式（s07/s02/s06/s08/s19）

---

## 1. 背景与问题

当前部署把 `ENABLE_CONTEXT_SERVICE / ENABLE_MCP_TOOLS / ENABLE_SKILL_TOOLS / ENABLE_HOOKS` **四个开关全开**，导致 `agent.py` 里 `complex_path`（`agent.py` 约 811 行）**静态恒真**——**每一轮聊天（哪怕只是「你好」）都无条件走完整重型路径**。

经代码核对的真实每轮成本（`app/agent.py` build 段 + `app/context_service.py` + `app/mcp_tools.py`）：

| 阶段 | 代码位置 | 每轮代价 | 是否必要 |
|------|----------|----------|----------|
| 上下文装配 | `ContextService.build()` (`context_service.py:108`) | 工作区记忆(文件读) + 核心记忆(DB) + 用户画像(DB) + **`retrieval_reflex`(正则抽实体 + 扫 500 行 `UserMemory`)** + **`semantic_recall`(`MemoryStore().query()` = embedding + Chroma 向量检索，即「知识库」)** + 会话摘要(DB) + 超额时 `summarizer`(LLM) | 仅部分轮需要 |
| 工具目录 | `get_mcp_tool_catalog()` (`mcp_tools.py:124`) | 拼巨大 catalog 文本块（prompt token 开销） | 可瘦身 |
| 工具构建 | `build_mcp_langchain_tools()` (`mcp_tools.py:57`) | **为每个 enabled server 的每个工具重建 `StructuredTool` 对象**（含 pydantic `args_schema` 构造、闭包） | 可缓存 |
| 绑定+推理 | `llm.bind_tools(tools)` | 工具清单越大 → 选择越差、首 token 越慢 | 可剪枝 |

**核心痛点（用户原话）**：
1. 「工具 + 上下文」每轮全量重载太耗时间。
2. 应先**识别是否需要知识库**，才去走 `ContextService` 检索。
3. 参考 `learn-claude-code`，把性能做到极致，**每轮都是最优路径**。

---

## 2. 目标

- **平凡轮极速**：闲聊/简单问答从 70–104s 级重型路径降到 <2s 直答。
- **知识库按需**：KB 检索（embedding + Chroma）从「每轮必做」变为「仅 ~30% 轮、且只针对本条 query」。
- **工具零重建**：`StructuredTool` 构建一次、缓存复用；MCP 配置变更**事件失效**（而非 IDLE_TTL 时间过期）。
- **零能力回归**：默认走保守路由（不确定时保持完整路径），不丢工具/不丢记忆。
- **可灰度**：每根优化都可独立开关，出问题一键回退到当前 `complex_path`。

---

## 3. 设计原则（对标 `learn-claude-code`）

| 来源章节 | 原则 | 在本方案映射 |
|----------|------|--------------|
| **s07 Skill Loading** | *Load knowledge on demand, not upfront — list first, expand when needed* | KB 检索改为 `retrieve_knowledge` 按需工具；前置门控跳过无谓检索 |
| **s02 Tool Use** | *Adding a tool = adding one handler; the loop stays untouched; register into dispatch map* | 工具池常驻缓存 + top-k 剪枝，主循环不变 |
| **s19 MCP Plugin** | *Plug in more via MCP — connect external tools into the same tool pool* | 工具池按 `(user, 配置 hash)` 缓存，MCP 增删改事件失效 |
| **s06 Subagent** | *Big tasks split small; each subtask gets clean context* | （远期）多工具研究型 query 派发子代理，隔离上下文 |
| **s08 Context Compact** | *Context always fills up — have a way to make room* | 现有 `ContextService` 压缩保留并增强 |

---

## 4. 总体架构（对应三张设计图）

```
用户消息
   │
   ▼
┌─────────────────────────────┐
│  Fast Intent Router (<50ms)  │  规则 + 可选轻量分类
└─────────────────────────────┘
   ├─ T0 直答 ──────► llm.stream() 仅此（无 KB · 无工具）       目标 <2s
   ├─ T1 工具 ──────► 绑定[缓存+剪枝]工具，跳过 KB 检索          实时数据
   └─ T2 全量 ──────► 模型按需 retrieve_knowledge(query) + 工具   知识+上下文
        │
        ├─ Tool Pool（构建一次，key=(user_id, 配置 hash)，MCP 变更事件失效）
        └─ KB 检索→按需工具（非前置必做）
```

- **图1 现状**：每轮全价链路（问题）。
- **图2 优化架构**：意图路由 + 按需知识库 + 工具池缓存。
- **图3 KB 门控**：先判定「需不需要」，再去检索。

---

## 5. 详细实现

### 阶段 1（低风险 · 立竿见影）— 推荐先上车

#### 1.1 工具池缓存 + 事件失效（`app/mcp_tools.py`）

新增模块级缓存，避免每轮重建 `StructuredTool`：

```python
# app/mcp_tools.py
import hashlib, threading

_TOOL_POOL: dict[int, tuple[str, list[StructuredTool]]] = {}
_POOL_LOCK = threading.Lock()

def _servers_config_hash(db, user_id: int) -> str:
    servers = get_enabled_remote_servers(db, user_id)
    payload = "|".join(
        f"{s.id}:{s.name}:{','.join(sorted(s.tool_allowlist or []))}:{s.enabled}"
        for s in servers
    )
    return hashlib.md5(payload.encode()).hexdigest()

def build_mcp_langchain_tools(db, user_id: int, _force: bool = False) -> list[StructuredTool]:
    cfg_hash = _servers_config_hash(db, user_id)
    with _POOL_LOCK:
        cached = _TOOL_POOL.get(user_id)
        if cached and not _force and cached[0] == cfg_hash:
            return cached[1]          # 复用，零重建
    tools = _build_tools_impl(db, user_id)   # 现有并行拉取+构造逻辑
    with _POOL_LOCK:
        _TOOL_POOL[user_id] = (cfg_hash, tools)
    return tools

def invalidate_tool_pool(user_id: int | None = None) -> None:
    """MCP server 增删改后调用：清缓存，下一轮聊天重建。"""
    with _POOL_LOCK:
        if user_id is None:
            _TOOL_POOL.clear()
        else:
            _TOOL_POOL.pop(user_id, None)
```

> `StructuredTool` 无状态（`_run` 闭包仅捕获 `server_id/tname`，调用时按需从 DB 取 server），跨轮复用安全。多 uvicorn worker 时各进程独立缓存，失效在同进程触发，足够；多 worker 共享缓存列为远期（Redis）。

**事件失效接入**（`app/api.py` MCP server CRUD 端点 POST/PATCH/DELETE 提交后）：

```python
from app.mcp_tools import invalidate_tool_pool
# 在 create/update/delete MCP server 成功 commit 后：
invalidate_tool_pool(user_id)
```

> 可选预热：`app/db/init_db.py` 启动后对每个活跃用户惰性预热（首轮聊天时建，后续命中即可），不强依赖。

#### 1.2 Catalog 瘦身（`app/mcp_tools.py` `get_mcp_tool_catalog`）

将「逐工具全量描述」改为「名称 + 一句话用途」索引，保留最高优先级规则（「可用 MCP 工具回答时必须调用」）：

```python
def get_mcp_tool_catalog(db, user_id: int) -> str:
    lines = []
    for server in get_enabled_remote_servers(db, user_id):
        try:
            tools = MCPConnectionManager.get_tools(user_id, server)
        except Exception:
            continue
        allow = server.tool_allowlist or []
        for t in tools:
            name = t.get("name")
            if allow and name not in allow:
                continue
            purpose = (t.get("description") or "")[:60].replace("\n", " ")
            lines.append(f"- {server.name}.{name}: {purpose}")
    if not lines:
        return ""
    return ("Available MCP tools (call to get live data; do NOT answer from memory):\n"
            + "\n".join(lines))
```

#### 1.3 KB 前置门控（规则版，零能力损失）（`app/agent.py` + `context_service.py`）

在 `ContextService.build()` 之前用**极廉价的规则**判定本轮是否需要知识库，**不需要则完全跳过** `semantic_recall` / `retrieval_reflex`：

```python
# app/agent.py，位于 enable_context_service 分支内、构造 BuildOptions 之前
_need_kb = _needs_knowledge_base(message)   # 复用 context_service._extract_entities 思路

opts = BuildOptions(
    ...
    enable_reflex=getattr(settings, "enable_retrieval_reflex", False) and _need_kb,
    enable_memory_recall=getattr(settings, "enable_memory_recall", False) and _need_kb,
    enable_rrf=getattr(settings, "enable_rrf", False) and _need_kb,
    ...
)

def _needs_knowledge_base(text: str) -> bool:
    """保守判定：仅当消息含可匹配记忆的实体/召回意图时才检索。"""
    if not text or len(text.strip()) < 4:
        return False
    # 复用 context_service 的实体抽取（纯正则，无 embedding）
    from app.context_service import ContextService
    if ContextService._extract_entities(text):
        return True
    # 显式召回意图词
    if re.search(r"(我记得|之前|上次|我们讨论过|你说过|我的偏好|我的设置)", text):
        return True
    return False
```

> 安全边界：仅「无实体且无召回意图」的平凡轮被跳过，**绝不**在存在潜在记忆匹配时跳检索 → 能力零损失。这一步省掉的是 embedding + Chroma 向量检索（真实知识库开销）与 500 行记忆扫描。

---

### 阶段 2（激进 · 极致性能）

#### 2.1 Fast Intent Router 三档分流（`app/agent.py` 新增 `_route_intent`）

在主流程 `_resolve_llm_config` **之前**插入路由，按最小必要路径分发：

```python
class Tier:
    DIRECT = "direct"   # T0
    TOOLS  = "tools"    # T1
    FULL   = "full"     # T2

def _route_intent(message: str, settings) -> str:
    t = message.strip()
    # T0：纯闲聊/致谢/短句，且无任何工具触发词 → 直答
    if len(t) <= 12 and re.fullmatch(r"[\s\w\W]*(你好|hi|hello|谢谢|感谢|好的|ok|👋|在吗)[\s\w\W]*", t, re.I):
        return Tier.DIRECT
    # T1：含实时数据意图（车次/余票/天气/搜索/查…）但非知识召回 → 仅工具
    if re.search(r"(车次|余票|天气|汇率|搜索|查询|查一下|帮我查)", t) and not _needs_knowledge_base(t):
        return Tier.TOOLS
    # 默认保持 FULL（保守，不丢能力）
    return Tier.FULL
```

`ask_agent` 据此早分支：
- **T0 DIRECT**：只用极简 system prompt + `llm.stream()`，**不**构建 `ContextService`、**不**绑定工具（目标 <2s）。
- **T1 TOOLS**：绑定[缓存+剪枝]工具（`build_mcp_langchain_tools` 命中阶段1缓存），**跳过** KB 检索。
- **T2 FULL**：走完整装配 + 按需 KB 工具（见 2.2）。

#### 2.2 `retrieve_knowledge` 按需工具（`app/context_service.py` + `app/mcp_tools.py` 或 `agent.py`）

把**自动前置**的 `semantic_recall`/`reflex` 改为模型**按需调用**的工具（s07 模式），从「每轮必做」彻底变为「按需触发」：

```python
def _make_retrieve_knowledge_tool(db, user_id: int) -> StructuredTool:
    def _run(query: str) -> str:
        cs = ContextService(db)
        hits = cs._semantic_recall(user_id, query, k=settings.context_service_recall_k)
        reflex = cs._retrieval_reflex(user_id, query, cap=settings.context_service_reflex_cap)
        merged = (reflex or []) + [h.get("content", "") for h in hits]
        return "\n".join(merged) if merged else "（知识库无相关记忆）"
    return StructuredTool(
        name="retrieve_knowledge",
        description="当用户问题需要调用历史记忆/个人偏好/过往讨论时使用；输入检索语句，返回相关记忆。",
        args_schema=_build_args_model({"query": "string"}),
        func=_run,
    )
```

- `ContextService.build()` 中 `enable_memory_recall`/`enable_reflex` **默认关闭自动检索**，改为由工具触发。
- system prompt 增加指示：「若回答需要历史记忆或个人偏好，先调用 `retrieve_knowledge`」。
- 保留 `retrieval_reflex`（无 embedding，纯正则+DB 扫描）作为**常驻轻量层**以防模型漏调用；重活（embedding/Chroma）只在工具被调用时发生。

#### 2.3 top-k 工具相关性剪枝（`app/agent.py` 绑定前）

`bind_tools` 前用 query 对工具描述做轻量匹配，仅绑定最相关 top-k（默认 8），既省 token 又提升选择准确率：

```python
def _prune_tools(tools, query: str, top_k: int = 8) -> list:
    if len(tools) <= top_k:
        return tools
    scored = []
    q = set(re.findall(r"[\w\u4e00-\u9fff]+", query.lower()))
    for t in tools:
        desc = (t.description or "").lower()
        overlap = len(q & set(re.findall(r"[\w\u4e00-\u9fff]+", desc)))
        scored.append((overlap, t.name.count("_"), t))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [t for _, _, t in scored[:top_k]]
```

> 剪枝仅影响 `bind_tools` 传入列表，**不改** Tool Pool 缓存本身；若模型需要未绑定工具，可保留一个 `list_all_tools` 兜底（远期）。

---

## 6. 风险与回滚

| 风险 | 影响 | 缓解 / 回滚 |
|------|------|-------------|
| 路由误判（把需要工具的轮判成 T0） | 漏调用工具/KB | 路由**默认保守**（不确定→FULL）；每根优化独立开关（如 `ENABLE_INTENT_ROUTER`、`ENABLE_KB_GATE`、`ENABLE_TOOL_POOL`），关闭即回退当前 `complex_path` |
| KB 按需后模型漏调 `retrieve_knowledge` | 偶发丢上下文 | 保留 `retrieval_reflex` 常驻轻量层 + system prompt 强提示；监控命中率 |
| 工具池缓存与配置漂移 | 用到旧工具定义 | 事件失效接入 MCP CRUD；配置 hash 不匹配即重建 |
| 多 worker 缓存不一致 | 某进程未失效 | 单 api 容器单进程为主；多 worker 共享缓存列为远期 |

**回滚总闸**：任一开关置 false 即回到当前已验证的 `complex_path` 行为，无需代码回退。

---

## 7. 验证方案

1. **KB 门控命中率**：在 `_needs_knowledge_base` 与 `retrieve_knowledge._run` 加计数日志，跑 20 条混合 query（闲聊/数据查询/记忆召回），确认平凡轮 `semantic_recall` 调用数 ≈ 0。
2. **工具池**：首轮聊天后 `build_mcp_langchain_tools` 应命中缓存（加 `_cache_hit` 日志）；新增一个 MCP 工具 → 下一轮聊天**立即**可用（验证事件失效），日志无每轮 handshake。
3. **端到端延迟**：用 konghong 账号（`kh1763751448@gmail.com`）跑 SSE 测试，对比优化前（70–104s 空白）→ 优化后平凡轮 <2s、数据轮有状态提示+逐字流式（沿用既有 `sse_test` 脚本思路）。
4. **回归**：非流式 `/chat`（`ask_agent_sync`）、同步调用方、api 日志无 traceback/500。
5. **能力不降**：构造「我记得之前说过…」类 query，确认仍能召回记忆（门控放行 + 按需工具命中）。

---

## 8. 预期收益

| 指标 | 优化前 | 阶段1后 | 阶段2后 |
|------|--------|---------|---------|
| 平凡轮首 token | 70–104s（整段空白） | <2s（直答/跳过KB） | <2s（T0 直答） |
| KB 检索（embedding+Chroma） | 每轮 1 次 | 仅无实体轮跳过 ≈ 0 次 | 仅模型判定需要时 ≈ 30% 轮 |
| 工具重建 | 每轮 N 个 StructuredTool | 0 次（缓存命中） | 0 次（缓存命中）+ top-k 剪枝 |
| 工具 prompt token | 全量 catalog + 全工具 | catalog 瘦身 | 再 + top-k 剪枝 |

---

## 9. 实施顺序建议

1. 先落**阶段 1**（1.1 工具池缓存+事件失效 / 1.2 catalog 瘦身 / 1.3 KB 前置门控）——零新依赖、风险最低、立刻可感变快。
2. 验证稳定后，再评估**阶段 2**（2.1 路由分流 / 2.2 按需 KB 工具 / 2.3 top-k 剪枝），其中 2.2 为最大收益项。
3. 每根优化带独立开关，可灰度、可一键回退。
