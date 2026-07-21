# 聊天每轮性能优化（plan-chat-perf-v2）— 实施与验证报告

> 基于设计方案 `designs/plan-chat-perf-v2.md`，为聊天链路做「每轮最优路径」重构。
> 目标：平凡轮极速、知识库按需、工具零重建、零能力回归、可灰度、可一键回退。

---

## 1. 改动清单

| 模块 | 文件 | 内容 |
|------|------|------|
| 开关 | `app/settings.py` | 新增 6 个开关 |
| 工具池 | `app/mcp_tools.py` | §1.1 缓存+事件失效；§1.2 Catalog 瘦身；工具闭包自开 session |
| 路由/门控 | `app/agent.py` | §1.3 KB 门控；§2.1 Intent Router；§2.2 按需 KB 工具；§2.3 top-k 剪枝 |
| 失效接线 | `app/api.py` | MCP server 增删改后调用 `invalidate_tool_pool` |
| 部署 | `docker-compose.yml` | 暴露 6 个开关（带默认） |

### 新增开关（关 → 回退当前 `complex_path`，零能力回归）
- `ENABLE_TOOL_POOL`（默认 **true**）
- `ENABLE_KB_GATE`（默认 **true**）
- `ENABLE_INTENT_ROUTER`（默认 **true**）
- `ENABLE_TOOL_PRUNE`（默认 **true**）+ `TOOL_PRUNE_TOP_K`（默认 8）
- `ENABLE_ONDEMAND_KB`（默认 **false**，激进项，需配合 `ENABLE_MEMORY_RECALL` 才生效）

---

## 2. 关键设计决策（含两个实测修正）

1. **工具池跨请求安全**：原 `build_mcp_langchain_tools` 的闭包捕获请求作用域 `db`；缓存后跨请求复用会因会话关闭而失败。改为 `_call_mcp_tool()` 每次调用**自开 `SessionLocal`** 取 server，工具可安全缓存复用。
2. **Intent Router T0 收紧**：初版 T0 用「含问候词 + 长度≤12」判定，导致「你好，帮我查天气」被误判 T0（漏调工具）。修正为「整句仅问候」正则 `^[\s\W]*(问候词)[\s\W]*$` 且**排除任何实时意图**，并保留 `agent_has_kb` 时不短路（避免跳过 RAG）。
3. **top-k 剪枝中文失效修复**：原设计按 `[\w\u4e00-\u9fff]+` 切词，中文无空格会整句塌成一个 token → 重叠恒为 0、剪枝无效。改为**中文按字级重叠**（`_tokens()`：拉丁词 + 独立 CJK 字），剪枝对中文真正生效。

---

## 3. 各阶段收益映射

- **§1.1 工具池缓存**：每轮不再重建 `StructuredTool`（含 pydantic args_schema 构造）。首轮 MISS 后命中缓存，零重建；MCP 配置变更经 `invalidate_tool_pool` 事件失效（非时间过期）。
- **§1.2 Catalog 瘦身**：MCP 目录由「逐工具全量描述」改为「名称 + 60 字用途」，保留最高优先级 TOOL USAGE RULE，显著降低 system prompt token。
- **§1.3 KB 前置门控**：无实体/召回意图的平凡轮跳过 `semantic_recall`(embedding+Chroma) 与 `retrieval_reflex`(500 行扫描)，仅保留需要时检索 → 零能力损失。
- **§2.1 Intent Router**：T0 纯问候 → 极简直答（<2s 路径，跳过 ContextService/工具）；T1 实时意图 → 仅工具、跳过 KB；T2 全量兜底。默认保守（不确定→FULL）。
- **§2.2 按需 KB**：开启后关闭「自动」语义回忆，改由模型按需调用 `retrieve_knowledge` 工具，KB 检索从「每轮必做」变「按需触发」（最大收益项）。
- **§2.3 top-k 剪枝**：`bind_tools` 前仅绑定最相关 top-k 工具，提升首 token 速度与选择准确率（不影响缓存）。

---

## 4. 验证结果

### 单元测试（离线，不依赖 LLM/网络）
- `tests/test_chat_perf_v2.py`：**10/10 通过**。
  - `_needs_knowledge_base` / `_route_intent`（T0/T1/T2）/ `_prune_tools`（含中文字级重叠）
  - 工具池 命中/失效/配置 hash 变更重建、自包含调用 `_call_mcp_tool`
  - Catalog 瘦身截断校验
  - `ask_agent` 内 KB 门控（平凡轮跳过 recall / 含实体放行）、按需 KB 工具注入

### 回归
- 相关既有套件 `test_context_service` / `test_agent_extensions` / `test_mcp_breaker` / `test_mcp_client`：**15/16 通过**。
- 唯一失败 `test_agent_extensions.py::test_ask_agent_runs_skill_and_hooks` 为**预先存在**（其假 LLM 缺 `.stream`，原始代码同样报 `AttributeError`）— 与本改动无关（已用 `git stash` 在原始代码复现确认）。

### 真实容器（真实 MySQL + 真实 API）
- `docker restart ai-agent-api`：**干净启动**，`Application startup complete`，MySQL 初始化成功，无 import/traceback。
- `POST /api/chat`（平凡「你好」）：**HTTP 200**，返回正确回答（完整 `ask_agent` 路径，KB 门控+工具池生效）。
- `POST /api/chat-stream`：
  - 平凡「你好」→ **HTTP 200**，流式返回（T0 直答，耗时较同步全路径显著下降）。
  - 实时「查一下北京到上海的天气」→ **HTTP 200**，日志确认 `intent router: tier=tools skip_kb=True`；且 `tool pool HIT user_id=1`（缓存命中，零重建）。

---

## 5. 回滚与灰度
任一开关置 `false` 即回到当前已验证的 `complex_path` 行为，无需代码回退：
- 仅聊天变慢 → 关 `ENABLE_INTENT_ROUTER` / `ENABLE_TOOL_POOL` / `ENABLE_TOOL_PRUNE` / `ENABLE_KB_GATE`。
- 记忆召回行为变化 → 关 `ENABLE_ONDEMAND_KB`（恢复每轮自动语义回忆）。
- 变更方式：`docker/.env` 设对应变量 → `docker restart ai-agent-api`。

---

## 6. 后续建议
- 若开启 `ENABLE_MEMORY_RECALL`，建议同步开启 `ENABLE_ONDEMAND_KB` 以获得「KB 仅 ~30% 轮」的收益（并在 system 中观察 `retrieve_knowledge` 调用率）。
- 多 api worker 部署时，工具池为进程内缓存，失效在同进程触发；如需跨进程一致可后续接入 Redis（文档已标注为远期）。
