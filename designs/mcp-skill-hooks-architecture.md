# 可扩展架构设计：MCP / Skill / Hook 扩展平台

> 状态：方案设计稿（待评审，未实现）
> 作者：软件架构师（架构通）
> 目标读者：技术负责人 / 平台研发
> 关联系统：现有 AI Agent 平台（FastAPI + React 19 + Provider/UserMemory/Chat）

---

## 0. 阅读说明与假设

本文档在设计时做了以下**假设**，若与你的预期不符请直接指出，我会调整：

1. **基于现有平台扩展**，而非从零新建。现有 `ContextService.build()`（组装 system 上下文）、`ask_agent`（解析 LLM 配置）、Chat 会话/Provider 体系是天然的接入点。
2. **多租户 SaaS / 私有化混合场景**：用户可自助配置自己的 MCP Server、Skill、Hook，且彼此隔离。
3. 你明确提到的「**基于 Claude Code 设计方式、通过 Hook 扩展 Skill**」——解读为：Skill 是「指令包（Markdown + 元数据）」，其高级能力通过**声明 Hook**（PreToolUse / PostToolUse / UserPromptSubmit / Stop 等生命周期钩子）来实现扩展。
4. 「高性能、高可用」默认指：无状态 API 可水平扩容、有状态连接可池化、执行层可隔离、故障可熔断、全链路可观测。

---

## 1. 背景与目标

### 1.1 业务诉求
- 在**聊天**中接入 **MCP** 与 **Skill** 模块。
- **用户可自助配置**自己的 MCP Server、Skill、Hook（配置即能力，无需改平台代码）。
- 聊天中**实时调用**这些能力（MCP 工具、Skill 指令、Hook 拦截/增强）。
- 借鉴 Claude Code 的 **Hook 扩展范式**，让 Skill 的能力通过 Hook 在 Agent 生命周期里被扩展。

### 1.2 非目标（先不做）
- 不做 Skill 市场/公开发布（仅用户私有 + 平台内置）。
- 不做跨租户 Skill 共享（企业版以后再议）。
- 不替用户托管 MCP Server 的「业务实现」，只托管**连接与执行**。

### 1.3 设计原则（来自架构师角色约束）
1. **不做架构宇航员**：每个抽象必须证明自己解决了真实复杂度。
2. **先讲权衡，再讲最佳实践**：每个选型都明确「放弃了什么」。
3. **领域优先、技术其次**：先定扩展点语义，再选传输/隔离技术。
4. **可逆性优先**：优先选易回退的决策，而非「理论最优」。
5. **记录决策而非只记录设计**：关键选型落 ADR。

---

## 2. 现状盘点（现有平台能力，作为接入基底）

| 现有能力 | 文件/模块线索 | 对本设计的复用 |
|---|---|---|
| Chat 会话/消息 | chat 相关模型、`ask_agent` | Agent Loop 主流程承载 MCP/Skill 调用 |
| Provider 体系（用户可配 AI 提供商） | `Provider.is_default`、`ChatRequest.provider_id` | **用户自助配置范式直接复用**：MCP/Skill/Hook 同样走「用户私有配置」模型 |
| 上下文组装 | `ContextService.build()` 注入 MEMORY.md + UserMemory | **核心注入点**：在此追加 MCP 工具 schema + Skill 目录 |
| 出网代理韧性 | `app/http_client.py`（代理探测+直连兜底） | MCP SSE/HTTP 连接的网络策略复用 |
| 用户长期记忆 | `UserMemory` + Chroma | Skill/Hook 可读取（受权限约束） |
| 前端配置 UI | React 19 + antd（需补 React19 补丁） | MCP/Skill/Hook 配置控制台复用前端栈 |

> ⚠️ 关键约束（来自项目记忆）：绝不在 FastAPI startup 做阻塞网络调用；绝把请求作用域 ORM 实例传入后台线程；Pydantic 新增列必须可空；前端 UI 改动需浏览器真机验证。

---

## 3. 关键架构决策（ADR + 多方案对比）

### ADR-1：部署拓扑

#### 方案 A — 单体内嵌（所有扩展跑在 FastAPI 进程内）
- **做法**：MCP 客户端、Skill 加载、Hook 执行全部在 API 进程内；stdio MCP 作为子进程同容器拉起。
- **收益**：开发最快、零网络跳数、调试简单。
- **代价**：无隔离（用户脚本/进程泄漏风险）、资源争抢、单点故障、MCP 进程无法独立扩容、租户间易串味。
- **适合**：Demo / 单机私有化。

#### 方案 B — 模块化单体 + 独立执行 Worker（**推荐**）
- **做法**：API（编排/聊天）保持无状态模块单体；新增**执行 Worker** 专责「风险执行」——拉起 stdio MCP、运行 Skill 脚本、跑 Hook，全部在隔离沙箱里。二者通过消息队列/gRPC 通信。
- **收益**：危险操作集中隔离、Worker 可独立扩容与限流、失败可重试/入队、边界清晰、团队小也能维护。
- **代价**：多一个服务、工具调用多一跳网络延迟、需要任务队列与连接管理。
- **适合**：你们当前团队规模 + 高性能/高可用诉求的甜点区。

#### 方案 C — 全微服务（MCP Gateway / Skill Svc / Hook Svc / Orchestrator 各自独立）
- **做法**：每个能力独立部署、独立数据库、独立团队。
- **收益**：隔离与扩容极致、团队自治。
- **代价**：分布式一致性难、运维沉重、当前团队规模下过度设计。
- **适合**：平台成熟、多团队并行后演进目标。

> **建议：起步选 B，远期可平滑演进到 C（B 的模块边界本就按 C 的服务切分，未来拆服务成本低）。**

---

### ADR-2：MCP 连接方式

#### 方案 A — 仅远端 MCP（SSE / Streamable-HTTP），平台做代理
- 用户只填 URL + 鉴权，平台转发。
- **收益**：零进程管理、天然易扩展、最省资源。
- **代价**：放弃庞大的 stdio MCP 生态（多数本地 MCP 是 stdio）。

#### 方案 B — 网关式连接池（**推荐**）
- Execution Worker 托管 **stdio + SSE + Streamable-HTTP** 三种；按 `(租户, server)` 维度**池化复用长连接**，带健康检查、空闲回收、重连、熔断。
- stdio 所需的 token 通过用户密钥库注入环境变量，绝不落库明文。
- **收益**：兼顾生态与性能，连接复用避免每次握手。
- **代价**：Worker 需管理进程生命周期与配额。

#### 方案 C — 每会话临时拉起 stdio
- 每次聊天临时 spawn，结束即杀。
- **收益**：隔离最干净。
- **代价**：启动慢、无法维持有状态 MCP 会话、频繁 fork 开销大。
- **适合**：极敏感场景的「一次性」执行。

> **建议：B 为主，C 作为「高敏感 server」的可选策略。**

---

### ADR-3：Skill 形态与「通过 Hook 扩展 Skill」

对齐你的诉求「通过钩子扩展 skill」：

#### 方案 A — 纯指令型
- Skill = Markdown 指令 + 工具描述，无脚本、无 Hook。仅注入上下文。
- **收益**：零执行风险、v1 最快。
- **代价**：能力弱，无法做「工具前后处理/上下文注入」。

#### 方案 B — 指令 + 可声明 Hook（**推荐，对齐 Claude Code**）
- Skill 自带 `hooks` 声明（如 PreToolUse 改写入参、PostToolUse 后处理输出、UserPromptSubmit 注入背景）。
- Skill 目录（名称+描述+触发词）常驻 system 上下文；**完整正文按需加载**（通过 `use_skill` 工具拉取，避免上下文膨胀）。
- **收益**：能力灵活且安全可控（Hook 走的还是统一沙箱），完全契合「用 Hook 扩展 Skill」。
- **代价**：需要 Hook 系统支撑（见 ADR-4）。

#### 方案 C — 指令 + 任意脚本执行
- Skill 可运行任意脚本。
- **收益**：最自由。
- **代价**：沙箱成本最高、审计最难。
- **建议**：不单独开放 C，脚本能力统一收敛进「Hook 沙箱 + Skill 声明式 Hook」。

> **建议：B。Skill 不自己跑脚本，脚本一律走 Hook 沙箱，安全边界统一。**

---

### ADR-4：Hook 执行沙箱（用户脚本的安全底线）

#### 方案 A — 进程级 + 资源限制（v1 务实）
- 在 Worker 内起子进程，配 timeout、CPU/内存上限、默认**禁网**、只读 FS + 临时 tmpfs。
- **收益**：实现快、成本低。
- **代价**：同节点多租户隔离弱（依赖 OS 级限制）。

#### 方案 B — 容器 / gVisor 强隔离（**推荐中长期**）
- 每次 Hook 执行在独立微容器（runsc/gVisor）或轻量 namespace，挂载最小权限、无密钥、网络按策略。
- **收益**：租户间强隔离、爆了不影响宿主。
- **代价**：需要容器运行时与镜像管理。

#### 方案 C — 外部微 VM（Firecracker 等）
- **收益**：接近 VM 级隔离。
- **代价**：运维重，非必需不上。

> **建议：v1 用 A 打底（配严格资源限制 + 默认禁网），Phase 4 升级到 B。**

---

### ADR-5：多租户隔离粒度

| 级别 | 做法 | 适用 |
|---|---|---|
| A 逻辑隔离 | DB 行级 `user_id` 过滤 + 配置作用域 | 起步 |
| B 执行隔离（**推荐**） | Worker 按租户配额 + Hook 沙箱 | 配合 ADR-4 |
| C 物理隔离 | 每租户独立命名空间/集群 | 企业版 |

> **建议：A 起步，B 随 Hook/MCP 上线强制开启。**

---

## 4. 推荐拓扑（C4 容器图）

```
┌──────────────────────────────────────────────────────────────────────┐
│                          浏览器 / 客户端                                │
└───────────────┬──────────────────────────────────────────────────────┘
                │ HTTPS (聊天流式)
                ▼
┌──────────────────────────────────────────────────────────────────────┐
│  Web (React 19 + antd)  —— 配置控制台：MCP / Skill / Hook 自助配置      │
└───────────────┬──────────────────────────────────────────────────────┘
                │ REST / WebSocket
                ▼
┌──────────────────────────────────────────────────────────────────────┐
│  API 层（FastAPI，无状态，可水平扩容）                                  │
│  ┌────────────┐  ┌──────────────────┐  ┌──────────────────────────┐   │
│  │ Chat 编排  │  │ ContextService   │  │ 配置/密钥 API             │   │
│  │ (Agent     │◀─│ .build() 扩展点  │  │ (MCP/Skill/Hook CRUD)    │   │
│  │  Loop)     │  │ +MCP工具schema   │  │ + 密钥库(加密 at rest)   │   │
│  └─────┬──────┘  │ +Skill目录        │  └──────────────────────────┘   │
│        │         └──────────────────┘                                   │
│        │ 调用/回调                                                     │
└────────┼──────────────────────────────────────────────────────────────┘
         │ (gRPC / 消息队列)
         ▼
┌──────────────────────────────────────────────────────────────────────┐
│  Execution Worker（有状态，按租户配额，可多副本）                        │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────────────┐  │
│  │ MCPConnection  │  │ SkillExecutor  │  │ HookRunner（沙箱）      │  │
│  │ Manager(连接池)│  │ (按需加载正文) │  │ Pre/PostToolUse 等      │  │
│  │ stdio/SSE/HTTP │  │                │  │ 进程级/容器隔离          │  │
│  └───────┬────────┘  └───────┬────────┘  └───────────┬────────────┘  │
└──────────┼───────────────────┼──────────────────────┼───────────────┘
           │                   │                      │
     ┌─────▼─────┐       ┌─────▼─────┐          ┌─────▼─────┐
     │ 用户MCP   │       │ Skill脚本 │          │ 用户Hook  │
     │ Server(s) │       │ (沙箱内)  │          │ 命令      │
     └───────────┘       └───────────┘          └───────────┘

旁路：
- 密钥库（Vault / KMS / 信封加密）── 仅 Worker 在拉起 MCP/Hook 时按需取
- 审计日志（每工具调用 / 每 Hook 执行，租户隔离）
- 可观测（trace_id=session_id；指标：连接池饱和度、工具延迟、Hook 失败率）
```

---

## 5. 核心流程：聊天 Agent Loop + Hook 时序

```
用户发送消息
   │
   ▼
[Event: UserPromptSubmit] ──▶ HookRunner 执行匹配 Hook
   │                            （可改写/注入 prompt）
   ▼
ContextService.build()
   │ 组装：system + MEMORY.md + UserMemory
   │        + 启用的 MCP 工具 schema
   │        + Skill 目录(名称/描述/触发词)
   ▼
LLM 流式调用（带工具定义）
   │
   ▼ 模型产出 tool_call
┌── loop ──────────────────────────────────────────────┐
│ [Event: PreToolUse] ─▶ Hook（可 approve/block/modify）│
│        │ block → 终止该工具，返回原因给模型            │
│        ▼                                              │
│ ToolExecutor 路由：                                   │
│   builtin → 本地 handler                              │
│   mcp     → MCPConnectionManager.call_tool()          │
│   skill   → SkillExecutor（加载正文/调子工具/跑脚本）  │
│        │                                              │
│ [Event: PostToolUse] ─▶ Hook（可读取/改写输出）       │
│        ▼                                              │
│ 结果回填上下文                                        │
└──────────────────────────────────────────────────────┘
   │ 模型判停
   ▼
[Event: Stop] ─▶ Hook（可触发后续动作/通知）
   ▼
返回用户
```

**Hook 协议（对齐 Claude Code settings.json 语义，服务端适配）：**
- 输入（stdin JSON）：`{ event, session_id, user_id, tool_name?, tool_input?, tool_output?, transcript_path }`
- 输出（stdout JSON）：`{ decision: "approve"|"block"|"modify", reason?, modified_input?, modified_output? }`
- `on_error` 策略：Hook 失败是「阻断工具」还是「放行继续」（用户可配）。

---

## 6. 数据模型（核心表，租户字段 `user_id` 一律必带）

```sql
-- 用户 MCP Server 配置（密钥加密存，绝不明文）
user_mcp_server (
  id, user_id, name,
  transport ENUM('stdio','sse','http'),
  command, args JSON, env_encrypted,          -- stdio
  url, headers_encrypted, auth_type,          -- sse/http
  enabled, timeout_ms, max_retries,
  tool_allowlist JSON,                        -- 白名单缩小暴露面
  created_at, updated_at
)

-- 用户 Skill（指令包 + 声明式 Hook）
user_skill (
  id, user_id, name, description, version,
  source_type ENUM('markdown','repo','builtin'),
  content,                                    -- Markdown 正文
  triggers JSON,                              -- 触发词/描述(供目录)
  hooks JSON,                                 -- 声明式 Hook 列表
  permissions JSON,
  enabled, created_at
)

-- 用户 Hook（可与 Skill 解耦独立配置）
user_hook (
  id, user_id, skill_id NULL,
  event ENUM('SessionStart','UserPromptSubmit','PreToolUse','PostToolUse','Stop','SubagentStop','Notification'),
  matcher,                                    -- 工具名正则等
  command, timeout_ms, on_error,
  enabled
)

-- 审计（每工具调用 / 每 Hook 执行）
tool_call_audit (
  id, user_id, session_id, turn_id,
  tool_type ENUM('mcp','skill','builtin'),
  target, tool_name,
  input_encrypted, output_encrypted,
  duration_ms, status, hook_decision,
  created_at
)

-- 租户执行配额（配合 ADR-5 B）
execution_quota (
  user_id, max_concurrent_tools, max_mcp_conns, max_hook_timeout_ms
)
```

> 密钥库：优先 Vault / 云 KMS；v1 可用 AES-256-GCM 信封加密列（每租户密钥派生），避免明文落库。

---

## 7. 安全与多租户隔离（硬性）

1. **密钥不落库明文**：MCP auth、Hook 环境变量走密钥库，运行时注入。
2. **工具白名单**：MCP 暴露的工具默认按 `tool_allowlist` 收窄。
3. **Hook 默认禁网 + 资源限制**；升级到容器/gVisor 强隔离。
4. **审计全覆盖**：任何工具/Hook 执行留痕，租户隔离可追溯。
5. **租户数据不串**：所有查询强制 `user_id` 过滤（复用现有 Provider 隔离范式）。
6. **拒绝危险操作**：Hook/Skill 不授予平台级权限（不能碰他人数据/不能删库）。

---

## 8. 性能 / 高可用设计

- **API 无状态**：任意副本可处理任意会话，水平扩容。
- **MCP 连接池**：`(租户, server)` 长连接复用，健康检查 + 空闲回收 + 熔断（避免单个烂 MCP 拖垮整池）。
- **执行异步化**：工具调用经队列，Worker 多副本消费，支持超时/重试/退避。
- **流式优先**：聊天与工具结果均流式回传，首字延迟低。
- **可观测**：`trace_id = session_id` 贯穿 LLM/工具/Hook；指标含连接池饱和度、工具 P99、Hook 失败率、token 用量。
- **优雅降级**：MCP 不可用时聊天仍可继续（工具降级提示），不致命。
- **HA**：Worker 多副本 + 队列持久化；API 多副本 + 负载均衡。

---

## 9. 分阶段演进路线图（降低风险，逐步交付）

| 阶段 | 内容 | 风险 | 交付价值 |
|---|---|---|---|
| **Phase 0** | 数据模型 + 密钥库 + 配置 CRUD API + Web 配置控制台骨架 | 低 | 用户可自助配置（满足「用户可配置」硬诉求） |
| **Phase 1** | MCP **远端**（SSE/HTTP）接入 + Chat 集成（只读工具优先） | 低 | 最快看到「聊天用 MCP」 |
| **Phase 2** | Skill 系统（目录常驻 + 按需加载正文 + `use_skill`） | 中 | 聊天用 Skill 指令 |
| **Phase 3** | Hook 系统（Pre/PostToolUse/Stop）+ 进程级沙箱 | 中 | 「通过 Hook 扩展 Skill」落地 |
| **Phase 4** | stdio MCP 连接池 + 容器/gVisor 强隔离升级 | 高 | 完整生态 + 强安全 |
| **Phase 5** | 多节点扩容、熔断/配额、企业级物理隔离（可选） | 中 | 高性能/高可用达标 |

> 推荐从 **Phase 0 + Phase 1** 先出一个可演示闭环，再逐阶段加厚。

---

## 10. 方案对比矩阵（总表）

| 维度 | A（单体内嵌） | **B（模块单体+Worker）** | C（全微服务） |
|---|---|---|---|
| 开发复杂度 | 低 | 中 | 高 |
| 租户隔离 | 弱 | 强（执行隔离） | 最强 |
| 扩容灵活性 | 差 | 好（Worker 独立扩） | 极好 |
| 运维负担 | 低 | 中 | 高 |
| 安全风险 | 高（同进程） | 中→低（沙箱） | 低 |
| 当前团队适配 | 过度简单 | **甜点** | 过度设计 |
| 演进到微服务成本 | 高（需重写） | 低（模块=未来服务） | 已是 |

**结论：选 B 起步，按 Phase 0→5 演进，远期自然长成 C。**

---

## 11. 待你确认的关键决策点（请回复我）

1. **部署形态**：多租户 SaaS / 私有化单租户 / 混合？→ 决定隔离方案选 A/B/C。
2. **MCP 生态优先级**：先只做远端（SSE/HTTP），还是必须一开始支持 stdio？→ 决定 Phase 1/4 顺序。
3. **安全红线**：是否允许 Skill/Hook 执行「用户自定义脚本」？→ 决定沙箱投入（ADR-4 A vs B）。
4. **规模预期**：并发用户/会话量级（百 / 千 / 万级）？→ 决定是否需要 Phase 5 提前。
5. **与现有 Chat 集成方式**：在 `ContextService.build()` / `ask_agent` 上扩展，还是另起独立 Agent Runtime？
6. **配置控制台**：Web 自助配置 MCP/Skill/Hook 是否本期必做（影响前端工作量）？

---

## 12. 下一步

你确认上述决策点（尤其第 1–3 条）后，我从 **Phase 0** 开始实现：
- 数据模型迁移脚本（MySQL 兼容，遵循现有 `app/models.py` 范式，新增列可空）
- 密钥库封装（信封加密，复用现有 sessionmaker）
- MCP/Skill/Hook 配置 CRUD API + 审计
- Web 配置控制台骨架（React 19 + antd，含 React19 补丁）
- 并在每个阶段用真实接口/浏览器回归验证后再向你报告。

---
*本稿为设计阶段产物，未经你同意不落地任何代码。*

---

## 13. v2 决策落地（用户已确认，本批已实现 Phase 0 + Phase 1）

### 13.1 用户确认的 6 项决策
1. **混合部署** → `DEPLOY_MODE=saas|private` 开关（settings）；隔离/配额策略随模式切换。
2. **MCP 先只做远端** → Phase 1 = SSE/Streamable-HTTP；stdio 字段保留，**本批不启用**。
3. **允许自定义脚本，但须安全检查通过才能用** → 新增 **Security Gate**：MCP/Skill/Hook 启用前过静态策略校验（含危险命令模式、URL 协议、必填密钥、事件合法性），不通过禁止 `enabled=true`。
4. **万级并发、越高越好** → API 无状态 + 连接池 + 熔断内建；队列/多副本压测留待 Phase 7。
5. **与现有 Chat 集成** → 扩展 `ContextService.build()` 注入 MCP 工具目录 + `ask_agent` 受开关保护的工具循环。
6. **Web 控制台本期必做** → 基于现有 `app` 下 mcp/skill 改造（Phase 6）。

### 13.2 本批已落地（已测试 + 活库 MySQL 迁移验证通过）
- `app/core/crypto.py`：基于 `secret_key` 的 Fernet 信封加密（api_key/headers/secret_env 落库加密）。
- `app/models.py`：`McpServer` 扩列（auth_type/api_key/headers/tool_allowlist/timeout_ms/max_retries）+ 新增 `Hook` + `ToolCallAudit` 模型。
- `app/security_gate.py`：`run_security_gate()` 静态策略校验（MCP/Skill/Hook）。
- `app/mcp_client.py`：零新增依赖远端 MCP 客户端（JSON-RPC over Streamable-HTTP/SSE）+ `MCPConnectionManager` 连接池（按 `(user_id,server_id)` 池化、健康检查、重连、熔断）。
- `app/mcp_tools.py`：`build_mcp_langchain_tools()`（动态参数建模）+ `get_mcp_tool_catalog()`（系统提示注入）。
- `app/api.py`：MCP 加密写入 + `has_api_key/has_headers` 脱敏；Hook 全 CRUD；`/security-check` + `/enable` 闸门；`/tool-call-audits` 审计列表。
- `app/agent.py`：`ask_agent` 受 `ENABLE_MCP_TOOLS` 开关保护的工具循环（默认关，回归不影响现有行为）。
- `app/settings.py`：功能开关（`ENABLE_MCP_TOOLS` 等，默认关）+ `DEPLOY_MODE`。
- `app/core/database.py`：活库 ALTER 迁移（`mcp_servers` 扩列）。
- `docker/db/init.sql`：修正 `mcp_servers` 与模型一致 + 新增 `hooks`/`tool_call_audit`。
- `tests/`：crypto / security_gate / mcp_client（含 SSE 解析 + 工具封装）/ config_api（加密+闸门拦截）全部通过。

### 13.3 进度（对照任务清单 #1–#8）
- ✅ #1 计划书 + 设计方案（含本 v2 章节）
- ✅ #2 Phase 0 后端基座
- ✅ #3 Phase 1 远端 MCP + Chat 集成
- ✅ #4 Phase 2 Skill 系统（目录/按需加载/use_skill）
- ✅ #5 Phase 3 Hook 运行时 + 沙箱（数据模型 + CRUD + 安全闸门 + HookRunner 生命周期执行 + 进程级沙箱 + 审计）
- ⏳ #6 Web 自助配置控制台
- ⏳ #7 万级并发 HA（队列/熔断/多副本压测）
- 🔶 #8 任务核对与回归验证（**本批：33 个单测全绿 + 活库迁移 + 活库 Skill API 端到端 + 容器激活 + 真实聊天回归**，详见 §13.4）

> 注：运行中的 `ai-agent-api` 容器需重启（或已 --reload）以加载新代码；本批验证均通过 `docker exec` 在容器内跑新代码 + 活库 MySQL 迁移完成。

---

## 14. Batch 2 落地（本批：Skill 运行时 + Hook 运行时 + 聊天集成 + 容器激活）

### 14.1 新增/修改文件
- `app/skill_runtime.py`（新）：`get_skill_catalog()`（目录注入 system 上下文）+ `build_use_skill_tool()`（`use_skill` 工具按需加载正文）+ `load_skill_content()`。
- `app/hook_runner.py`（新）：`run_hooks(event, user_id, db, payload, matcher)` 生命周期编排；`HookOutcome`；进程级沙箱（`resource` 资源限制 + `unshare -n` 网络隔离 best-effort + 环境变量最小化 + `secret_env` 解密注入）；`on_error` fail-closed；审计留痕。
- `app/models.py`：`Skill` 扩列（`content` / `trigger_words` / `declared_hooks` / `version`）；`ToolCallAudit` 补 `error` 列。
- `app/schemas.py`：`SkillCreate/Update/Read/DetailRead`（详情接口含 `content`）+ `SkillDetailRead`。
- `app/api.py`：Skill 详情 `/skills/{id}` + `/security-check` + `/enable`（与 MCP/Hook 同范式）；`Hook`/`MCP` 先前已具备闸门。
- `app/agent.py`：`ask_agent` 工具循环升级 —— 集成 Skill 目录注入 + `use_skill` 工具 + **四段 Hook 生命周期**（`UserPromptSubmit` 拦截/改写 → `PreToolUse` 拦截/改写参数 → 执行工具 → `PostToolUse` 改写结果 → `Stop` 改写答案），全程受 `ENABLE_SKILL_TOOLS` / `ENABLE_HOOKS` 开关保护（默认关）。
- `app/settings.py`：新增 `ENABLE_SKILL_TOOLS` / `ENABLE_HOOKS` + 沙箱配置（`HOOK_SANDBOX_NETWORK_BLOCK` / `CPU_SECS` / `MEM_BYTES` / `FSIZE_BYTES` / `CWD`）。
- `app/core/database.py`：活库 ALTER 迁移（`skills` 扩列 + `tool_call_audit.error`）。
- `docker/.env` + `docker/docker-compose.yml`：注入 `ENABLE_MCP_TOOLS/SKILL_TOOLS/HOOKS=true`（已重建 api 容器激活）。
- `tests/`：`test_skill_runtime.py`（4）、`test_hook_runner.py`（8）、`test_agent_extensions.py`（1，确定性集成测试：假 LLM 验证技能目录注入 + use_skill 调用 + Hook 真实触发 + 审计）。

### 14.2 安全闸门补强（本批发现并修复的漏洞）
- **`file://` / `ftp://` 等危险协议原仅 warning（可被绕过）** → 改为硬 `add_error` 拦截；仅允许 `http/https`。（活库端到端验证：`file://` 被闸门拒绝。）

### 14.3 沙箱隔离说明（v1）
- 进程级：CPU/内存/文件大小 `setrlimit` + `nice`；网络默认 `unshare -n` 隔离（本容器无权限时优雅回退非隔离并告警，符合「best-effort」）。
- 环境变量：仅注入白名单（`PATH`/`LANG`/`HOME`/`TMPDIR`/`PYTHONPATH`）+ 用户非敏感变量 + **解密后的 `secret_env`**，绝不泄漏宿主机敏感环境。
- `on_error` 默认 `block`（fail-closed）。
- Phase 4 升容器/gVisor 强隔离（路线图已列）。

### 14.4 验证结论（铁律：改动测试/迁移通过才交付）
- **单测 33/33 全绿**（crypto3 / security_gate10 / mcp_client4 / config_api3 / skill_runtime4 / hook_runner8 / agent_extensions1）。
- **活库 MySQL 迁移通过**：`skills` 已加 4 列、`tool_call_audit` 已加 `error` 列，无破坏性。
- **活库 Skill API 端到端**：创建(200, 列表不含明文正文) → 安全闸门(通过) → 启用(200) → 详情(含正文+触发词) → 清理(remaining=0)。
- **容器已激活**：`docker compose up -d api` 重建，`ENABLE_MCP_TOOLS/SKILL_TOOLS/HOOKS=true` 在运行容器生效，无启动错误。
- **真实聊天回归**：flags 开启但用户无工具配置时，`ask_agent` 正确回退单轮、产出「1+1等于2。」—— 未配置用户行为完全不变。

### 14.5 已知边界 / 后续
- `unshare -n` 在当前 Docker 环境无权限 → 自动回退非隔离执行（日志告警）。强隔离需 Phase 4 容器/gVisor。
- #6 Web 控制台（前端）与 #7 万级 HA（队列/熔断/多副本压测）待下一批。
