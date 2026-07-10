# 后端架构重构方案 · 可靠性与可扩展性设计

> 角色：后端架构师（Backend Architect）
> 目标：在现有 FastAPI + SQLAlchemy + SQLite/MySQL 单体基础上，重构为**可水平扩展、高可用、可观测、安全**的后端架构。
> 原则：**不推倒重来（no big-bang）**，按阶段渐进式迁移，每一步都可回滚、可验证。

---

## 1. 现状与痛点（Current State & Pain Points）

基于当前代码库与运维记录，现状如下：

| 维度 | 现状 | 风险 |
|------|------|------|
| **进程模型** | 单进程 `uvicorn :8010`，FastAPI 单体 | 无法水平扩展；单点故障 |
| **数据库** | 开发用 SQLite（文件锁），Docker 用 MySQL；三处 `create_engine` 经 `normalize_db_url` 注入驱动 | SQLite 不支持并发写，高负载下锁表/请求堆积 |
| **异步陷阱** | `async def` 端点内直接调用同步阻塞函数（`requests.post`、`llm.invoke`）会冻结事件循环 | 单条慢请求阻塞整个事件循环，吞吐骤降 |
| **重型任务** | 图片生成（超时 300s）、视频提交/轮询（120s/60s）在请求链路内联执行 | 请求长时间占用 worker，连接池耗尽，用户超时 |
| **缓存** | 无集中缓存；`getTypes/getShowcases/getTemplates` 等读多写少数据每次回源 DB | DB 读压力大，P95 延迟随流量上升 |
| **出网代理** | `app/http_client.py` 探测代理可达性，失败清除 env 走直连；LLM/worker 用 `proxy=None` | 进程级 hack，缺乏统一出口治理与熔断 |
| **可观测性** | 仅基础日志，无指标/链路追踪/健康检查 | 故障定位慢，无法量化 SLO |
| **安全** | `.env` 存密钥；`/api` 有 rate-limit；缺乏最小权限 DB 账号与密钥管理 | 密钥泄露面大，横向移动风险 |

**结论**：当前架构在「功能正确性」上可用，但在**扩展性、稳定性、可观测性**三个维度上都存在系统性短板。需要一次面向规模化的重构。

---

## 2. 目标架构总览（Target Architecture）

```
                        ┌─────────────────────────┐
                        │   Client (Web / Mobile)  │
                        └───────────┬─────────────┘
                                    │ HTTPS (TLS)
                        ┌───────────▼─────────────┐
                        │  API Gateway / LB         │  rate-limit · auth · TLS · WAF
                        │  (APISIX / Nginx / ALB)   │
                        └───────────┬─────────────┘
                  ┌─────────────────┼─────────────────┐
            ┌─────▼─────┐     ┌─────▼─────┐      ┌─────▼─────┐
            │ API Pod 1 │     │ API Pod 2 │ ...  │ API Pod N │   stateless FastAPI+uvicorn
            └─────┬─────┘     └─────┬─────┘      └─────┬─────┘
                  │                 │                  │
        ┌─────────▼─────────────────▼──────────────────▼─────────┐
        │  Shared Infrastructure                                   │
        │  • MySQL/PostgreSQL  (primary + read-replica, pooled)   │
        │  • Redis  (cache + task broker + 会话/限流计数)          │
        │  • MinIO  (object: chat-uploads / ai-agent-minio)       │
        │  • ChromaDB  (向量检索)                                 │
        │  • Task Queue (ARQ/Celery) → Media Worker Pool          │
        │  • Provider Egress Proxy  (统一出网 + 熔断 + 重试)       │
        └─────────────────────────────────────────────────────────┘
                  ▲  observability: structured logs + metrics + traces
```

**关键变化**：API 层变成**无状态、可水平复制**的 Pod；所有有状态/重型工作下沉到共享基础设施与异步 Worker；出网统一收口到 Egress Proxy。

---

## 3. 服务拆分策略（Service Decomposition）

不立即微服务化（组织与运维成本过高），而是**先模块化、后按需拆分**：

| 边界 | 当前 | 目标 |
|------|------|------|
| **API 网关层** | uvicorn 直出 | 前置 APISIX/Nginx：TLS 终止、全局 rate-limit、API 版本路由（`/api/v1`、`/api/v2`）、WAF |
| **核心 API 服务** | 单体（保持） | 拆为清晰的**领域模块**：auth / gallery / chat / media / provider。模块间通过内部接口而非跨进程调用，降低拆分阻力 |
| **媒体生成 Worker** | `media_worker.py`（已有雏形） | 升级为**任务队列驱动的 Worker Pool**（ARQ 基于 Redis，或 Celery），与 API 进程解耦 |
| **提供商出网服务** | 进程内 `app/http_client.py` | 抽成**Provider Egress Proxy**（独立 sidecar/服务），统一代理、熔断、重试、配额 |

**何时真正拆微服务**：当某一领域（如 media generation）的独立部署/扩缩容收益 > 运维成本时，再独立成服务。其余保持模块化单体。

---

## 4. 数据层（Data Layer）

1. **弃用 SQLite 生产化**：Docker 已用 MySQL；开发环境也统一到 MySQL/PostgreSQL，避免「开发能跑、生产锁表」的双标准。
2. **连接池 + 读副本**：
   - SQLAlchemy `pool_size`/`max_overflow` 配合 `pool_pre_ping`；前置 `pgbouncer`（PG）或 MySQL 连接池。
   - 读多写少接口（`getTypes/getShowcases/getTemplates/records`）路由到 **read-replica**。
3. **迁移工具**：引入 **Alembic**，替代当前 `create_all` + 手工 `inspector` ALTER。每次 schema 变更可回滚、可审查。
4. **CQRS-lite（按需）**：创作记录（`gallery_records`）写主库、读走副本/缓存；热点展示数据（套图案例、选项）走 Redis。
5. **索引治理**：按 `working_memory` 已记录的 MySQL InnoDB 3072 字节限制，长 `VARCHAR` 唯一索引统一用 `mysql_length` 前缀索引。

---

## 5. 缓存策略（Caching）

引入 **Redis**，分层缓存：

| 缓存对象 | 策略 | 失效 |
|----------|------|------|
| 类型/市场/输出选项 `getTypes` | 全局缓存，TTL 10min | 后台管理变更时主动失效 |
| 热门套图案例 `getShowcases` | 按分类缓存，TTL 5min | 新增/删除案例时失效 |
| 模板列表 `getTemplates` | 按 user 缓存，TTL 5min | 增删模板时失效 |
| 限流计数 / 会话 | Redis 原子计数 / 原生结构 | — |

**一致性原则**：缓存仅用于「读多写少、可容忍秒级延迟」的数据；写操作先落库再失效缓存，避免脏读。绝不缓存用户私密数据。

---

## 6. 异步任务与重型工作（Async & Heavy Work）

将媒体生成从「请求内联」迁移到**任务队列**：

```
POST /api/gallery/generate
   → 校验 + 写草稿状态 → 入队 (Redis) → 立即返回 task_id
   → Media Worker 异步执行：图片(≤300s)/视频(提交+轮询)
   → 进度/结果写库 + 推送 (WebSocket/SSE) 给前端
   → 前端轮询或订阅结果，无需长连接占用 API worker
```

- **收益**：API worker 数秒内释放，连接池不再被长任务占满；可独立扩缩 Worker 池（图片/视频任务可不同并发档位）。
- **韧性**：任务失败自动重试（指数退避）、死信队列、超时熔断；保留现有「SVG 离线降级」作为最终兜底，保证流程永不中断。
- **现有资产复用**：`media_worker.py`、`app/http_client.py` 的代理韧性逻辑直接迁移为 Worker 内部依赖。

---

## 7. 扩展性与高可用（Scalability & HA）

- **无状态 API**：移除任何进程内本地状态（会话/限流计数/缓存全部外置到 Redis），使 API Pod 可随意增删。
- **水平扩展**：`kubectl scale` 或 HPA 基于 CPU/请求延迟自动扩缩 API 与 Worker。
- **优雅停机**：uvicorn 启用 `graceful_timeout`，SIGTERM 时 drained 在途请求，K8s `preStop` 配合。
- **熔断与降级**：对外部 AI 提供商调用加**断路器**（如 `pybreaker`/十劫），失败率超阈值即短路返回降级结果，保护自身。
- **多副本 DB**：主从 + 定期备份（物理/逻辑）+ 演练恢复（RTO/RPO 目标写入 runbook）。

---

## 8. 安全防护（Security）

- **密钥管理**：`.env` → 环境变量由 **Secret Manager / K8s Secret** 注入，禁止明文入库；提供 `.env.example` 占位。
- **最小权限**：DB 账号按服务拆分（API 只读副本账号、写账号分离），`chat-uploads` 与 `ai-agent-minio` 桶策略隔离（已部分实现）。
- **传输安全**：全链路 HTTPS/TLS；MinIO 访问走内网或签名 URL，不暴露永久密钥。
- **认证授权**：JWT 短期令牌 + 刷新令牌；`/api` 全局 rate-limit（保留并加强，按 IP+用户多维限流）。
- **输入校验**：Pydantic 严格 schema（已有基础），文件上传限制类型/大小（前端已限制 ≤10MB，后端补强制校验）。

---

## 9. 可观测性（Observability）

- **日志**：结构化 JSON 日志（级别按需；生产 INFO，避免 DEBUG 海量刷屏——见 `working_memory` 性能提示），请求 ID 贯穿全链路。
- **指标**：Prometheus 暴露 QPS、P95/P99 延迟、错误率、DB 连接池占用、队列积压、Worker 利用率。
- **链路追踪**：OpenTelemetry 接入，跨 API→Worker→Provider 调用链可视化。
- **健康检查**：`/healthz`（存活）、`/readyz`（依赖就绪：DB/Redis/MinIO），供 LB 与 K8s 探针。
- **告警**：基于指标设 SLO 告警（如 P95>200ms、错误率>1%、队列积压>阈值）。

---

## 10. 出网代理韧性（Egress Resilience）

将 `app/http_client.py` 的「探测+直连兜底」逻辑**标准化为基础设施能力**：

- 抽成独立 **Provider Egress Proxy**（或统一的 HTTP client 中间件），配置驱动（开关、超时、重试、熔断）。
- 运维开关 `DISABLE_PROXY_AUTOFALLBACK` 保留，仅用于「只能走代理出网」的封闭环境。
- 所有出网调用（LLM 聊天、图片/视频生成、CDN 下载）统一经由该层，避免每处重复实现。

---

## 11. 渐进式迁移路线（Phased Migration）

| 阶段 | 目标 | 交付物 | 风险 |
|------|------|--------|------|
| **P0 止血** | 修复异步阻塞、统一 DB 驱动、出网韧性 | `asyncio.to_thread` 化同步调用；MySQL 全环境统一；代理层固化 | 低 |
| **P1 缓存+队列** | 引入 Redis 缓存热点读；媒体生成入队 | 缓存层、ARQ/Celery Worker、生成接口改为异步返回 | 中 |
| **P2 无状态化+扩展** | API 无状态、多副本、网关前置 | K8s 部署、HPA、APISIX/Nginx、健康检查 | 中 |
| **P3 可观测+安全** | 日志/指标/追踪、密钥管理、最小权限 | OTel+Prometheus、Secret Manager、DB 账号拆分 | 低 |
| **P4 数据层强化** | 读副本、Alembic、备份演练 | 副本路由、迁移脚本、runbook | 中 |

每阶段独立上线、可回滚；P0→P1 即可显著改善稳定性，不必等到全部完成。

---

## 12. 成功指标（Success Metrics）

- API P95 延迟 < 200ms（读接口），写接口 < 400ms
- 系统可用性 ≥ 99.9%（多副本 + 优雅停机）
- DB 查询平均 < 100ms（索引 + 副本 + 缓存）
- 安全审计零高危漏洞
- 峰值流量 10x 常态时，API/Worker 自动扩缩，错误率不上升
- 媒体生成不再占用 API worker，长任务成功率与可观测性显著提升

---

## 13. 风险与对策

| 风险 | 对策 |
|------|------|
| SQLite→MySQL 双标准导致环境差异 | P0 即统一，开发环境也跑 MySQL（可用 Docker Compose 一键起） |
| 缓存与 DB 不一致 | 写后失效策略 + TTL 兜底，不缓存私密数据 |
| 队列引入复杂度 | 先用 ARQ（轻量、基于 Redis），避免 Celery 重运维，按需升级 |
| 微服务拆分过早 | 坚持模块化单体，仅在明确收益时拆分 media 服务 |
| 代理环境差异（直连/代理） | 出网层配置驱动，保留兜底开关，部署文档明确环境假设 |

---

**架构师建议**：当前最该先做的是 **P0（异步阻塞修复 + DB 统一 + 出网韧性固化）** 与 **P1（Redis 缓存 + 媒体生成异步化）**——这两项投入小、收益大，直接解决「扩展性/稳定性」的核心痛点，且完全不破坏现有功能。其余阶段按业务节奏推进。
