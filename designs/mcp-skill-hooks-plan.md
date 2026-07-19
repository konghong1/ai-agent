# 计划书：MCP / Skill / Hook 扩展平台落地

> 配套文档：`designs/mcp-skill-hooks-architecture.md`（方案设计稿 + v2 决策落地）
> 状态：**全部完成** ✅（M1-M8 全部落地，含 Playwright 真机回归）
> 任务清单：#1 计划+设计 ✅ · #2 Phase0 基座 ✅ · #3 Phase1 远端MCP ✅ · #4 Phase2 Skill ✅ · #5 Phase3 Hook+沙箱 ✅ · #6 Web控制台 ✅ · #7 万级HA ✅ · #8 核对验证 ✅

---

## 一、6 项决策落地（你已确认）

| # | 你的决策 | 架构落地 |
|---|---|---|
| 1 | 混合部署 | 支持「私有化单租户」+「SaaS 多租户」；`DEPLOY_MODE=saas\|private` 开关控制隔离/配额策略 |
| 2 | MCP 先只做远端 | Phase 1 = SSE / Streamable-HTTP；stdio 字段保留但**本批不启用** |
| 3 | 允许自定义脚本，但须安全检查通过才能用 | 新增 **Security Gate**：用户 MCP/Skill/Hook 启用前过「静态扫描 + 策略校验 + 沙箱试跑」，不通过禁止 `enabled=true` |
| 4 | 万级并发、越高越好 | API 无状态水平扩容 + Execution Worker 池 + 任务队列 + 连接池 + 熔断，从 Phase 0 起内建 |
| 5 | 与现有 Chat 集成 | 扩展 `ContextService.build()` + `ask_agent` 工具循环（开关默认关，后向兼容） |
| 6 | Web 控制台本期必做 | 基于现有 `app` 下 mcp/skill 改造配置页（React19+antd） |

---

## 二、里程碑与任务拆解

- **M1 计划 + 设计方案**（#1）— ✅ 完成
- **M2 Phase 0 后端基座**（#2）— ✅ 完成：模型扩展 / 密钥库 / Hook 模型 / 审计 / 配置 API / Security Gate / 迁移
- **M3 Phase 1 远端 MCP**（#3）— ✅ 完成：JSON-RPC 客户端 + 连接池 + 熔断 + 并发限流 + Chat 集成
- **M4 Phase 2 Skill**（#4）— ✅ 完成：目录常驻 + 按需加载正文 + `use_skill` + 声明式 Hook 联动
- **M5 Phase 3 Hook + 沙箱**（#5）— ✅ 完成：7 生命周期事件 + 进程级沙箱 + 资源限制 + 禁网 + Security Gate 沙箱试跑
- **M6 Web 自助配置控制台**（#6）— ✅ 完成：MCP/Skill/Hook 三页 CRUD + 安全检测 + 启用流程（Playwright 真机回归通过）
- **M7 万级并发 HA**（#7）— ✅ 完成：API 无状态 + `/extensions/metrics` 可观测 + MCP 池熔断/并发限流 + 多副本扩容支持
- **M8 任务核对与回归验证**（#8）— ✅ 完成：46 后端单测全通 + Playwright E2E 全通 + 设计文档更新

---

## 三、本批交付范围（本回合）

1. 计划书（本文件）+ 修订设计方案（`architecture.md` 追加 v2 决策落地章节）。
2. **Phase 0 全量实现 + 单测**：
   - `app/core/crypto.py`：基于 `settings.secret_key` 的 Fernet 信封加密（用户密钥明文→密文落库）。
   - `McpServer` 模型扩展：`auth_type / api_key(加密) / headers(加密JSON) / tool_allowlist / timeout_ms / max_retries`。
   - 新增 `Hook` 模型（event / matcher / command / timeout_ms / on_error / enabled / secret_env）。
   - 新增 `ToolCallAudit` 模型（每工具/Hook 执行留痕，租户隔离）。
   - `app/security_gate.py`：MCP/Skill/Hook 启用前静态安全检查，返回 `{passed, errors, warnings}`。
   - 配置 API：Hook CRUD + McpServer 加密写入 + `/security-check` + `/enable`（走闸门）。
   - 迁移：`_migrate_sqlite_columns()` 补 ALTER + `docker/db/init.sql` 补列/表（遵循 MySQL TEXT 不加 default 铁律）。
3. **Phase 1 远端 MCP 全量实现 + 单测**：
   - `app/mcp_client.py`：`RemoteMCPClient`（JSON-RPC over Streamable-HTTP/SSE，零新增依赖）+ `MCPConnectionManager`（按 `(user_id, server_id)` 池化、健康检查、重连、熔断）。
   - `app/mcp_tools.py`：`get_mcp_tool_schemas()`（注入系统提示）+ `build_mcp_langchain_tools()`（LangChain Tool 封装）。
   - `ask_agent` 增加**受开关保护的工具循环**（bind_tools → 执行 → 回填 ToolMessage，最多 N 轮），默认关、回归不影响现有行为。

---

## 四、风险与对策

- **存量密钥明文**：现有 `Provider.api_key` 明文存储，本期只对新加密通道负责，存量不回填（文档标注，后续专项）。
- **聊天工具循环改动**：用 `settings.enable_mcp_tools` 默认关，关时 `ask_agent` 行为完全不变；开时仅在用户有启用 MCP 时进入循环。
- **万级并发**：连接池/队列为架构预留，压测与多副本在 M7 专项，本批不做破坏性扩容。
- **Mixin 约束**：所有新增 Pydantic 响应字段可空（`X | None = None`），新增 DB 列可空，避免破坏旧数据/接口。

---

## 五、验证门禁（铁律）

- 单测（`test_crypto` / `test_security_gate` / `test_config_api` / `test_mcp_client`）在 **Docker api 容器**内跑通（继承容器 MySQL `DATABASE_URL`）。
- MySQL 迁移在 Docker 验证（TEXT 列不加 default，新增列可空）。
- 任何会重启/迁移/删数据的改动：先在测试环境验证，再动生产数据。
- 前端（M6）改动须 Playwright 无头浏览器真机回归。

---

## 六、最终交付汇总（M1-M8 全部完成）

### 后端（46 单测全通）
| 模块 | 文件 | 测试数 | 状态 |
|------|------|--------|------|
| 密钥加密 | `app/core/crypto.py` | 3 | ✅ |
| 安全闸门 | `app/security_gate.py` | 10 | ✅ |
| MCP 客户端 | `app/mcp_client.py` | 4 | ✅ |
| MCP 熔断+并发 | `app/mcp_client.py` (MCPConnectionManager) | 4 | ✅ |
| 配置 API | `app/api.py` (config endpoints) | 3 | ✅ |
| Skill 运行时 | `app/skill_runtime.py` | 4 | ✅ |
| Skill-Hook 联动 | `app/skill_runtime.py` (sync_declared_hooks) | 4 | ✅ |
| Hook 运行时 | `app/hook_runner.py` | 8 | ✅ |
| 沙箱策略 | `app/hook_runner.py` (sandbox_probe) | 5 | ✅ |
| Chat 集成 | `app/agent.py` (ask_agent extensions) | 1 | ✅ |

### 前端（Playwright E2E 全通 — 10/10 检查项）
| 页面 | 路由 | 验证流程 | 状态 |
|------|------|----------|------|
| MCP 管理 | `/mcp-servers` | 新建→安全检测(file://拦截)→合法创建→检测通过→启用 | ✅ |
| Skill 管理 | `/skills` | 新建→安全检测→启用（联动 Hook） | ✅ |
| Hook 管理 | `/hooks` | 新建→安全检测(含沙箱试跑)→启用 | ✅ |

### HA 可观测
- `GET /api/extensions/metrics`：返回 MCP 池状态/熔断器/并发饱和度、Hook 审计统计、已启用资源计数
- API 无状态：JWT 认证、MySQL 持久化、MinIO 存储 — 可 `docker compose up --scale api=N` 水平扩容
- MCP 连接池按副本分片：每副本独立池/熔断/并发信号量
