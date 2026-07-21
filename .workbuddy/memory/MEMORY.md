# 项目长期记忆 — AI Agent Platform

> 维护规则：大改追加当日 `YYYY-MM-DD.md`；本文件只留跨会话有用的硬约束/坑/架构事实。详细历史见各 `YYYY-MM-DD.md`。

## 🎨 UI 设计交付记录
- **2026-07-21**: TapNow Canvas 同款 UI 设计图 (`tapnow-canvas-mockup.html`) — 高保真节点画布编辑器，含 12 种功能节点、贝塞尔连线、3D 相机立方体、灯光滑块、属性检查器、Agent 输入条。Playwright 验证通过（7 节点 / 8 连线 / 0 报错）。注意：app.tapnow.ai 画布需登录无法直接抓取，基于产品官网 + 评测还原。

## 🔴 最高优先级铁律（用户 2026-07-16 亲定，违反即事故）
1. **改动必须测试/回归通过才能回复**（硬性）：前端改动用真实浏览器(Playwright 无头)点一遍确认行为发生；后端改动用单元/接口级验证(真实 API + 真实 DB 状态核对)；存量代码改动须做回归(旧功能不破、旧数据不丢)；重启/迁移/删数据前先隔离环境验证再动生产。纯类型/编译错误修复以构建通过为准。
2. **绝不在测试/调试破坏真实用户数据**：禁止对真实用户数据做 DELETE/cleanup/drop/truncate；测试删除/重做只用隔离账号；清数据前先查 ID 确属测试数据；文件删除优先软删/回收站(`trash/` 前缀≥30天)，绝不硬删 DB+存储。
3. **修改 DB 数据时双重检查 SQLite + MySQL**：本地开发连接的是 SQLite(`agent.db`)，容器部署跑的是 MySQL。涉及写入/更新/重置密码等数据修改，必须**同时考虑两种数据库**（在两个端点都执行或确认行为一致），不能只在 SQLite 上改完就以为完成；也不能只通过 `docker exec` 连 MySQL 做 SQL 直改就忽略 SQLite 同步状态。违反=两套数据不一致，下次开发者查 SQLite 以为没改成功。
4. **删除功能安全底线**：`delete_task` 级联硬删不可逆；硬删须改软删，新增删除接口默认软删，确需硬删须双重确认+仅限本人+审计日志。

## 🔴 代码改动须兼容容器部署 SQL（MySQL）· 永久规则（2026-07-19 用户亲定）
> 任何 ORM 模型/字段改动都必须保证在真实 Docker+MySQL(`ai_agent`) 部署上能迁移运行，不能只在本地 SQLite `agent.db` 跑通就当完成。
- **加列铁律**：新增 NOT NULL 列必须带 `server_default`（Boolean 用 `"0"`），否则 MySQL 非空表 ALTER 失败→列加不上→seed/查询报 Unknown column→api 起不来。允许 NULL 的列也优先给 server_default。
- **TEXT 列禁带默认值**（MySQL8 报 1101）；VARCHAR 可带默认值。
- **双迁移路径**：①`core/database.py:_migrate_sqlite_columns` 只管本地 SQLite；②生产加列靠 api 容器启动 CMD `python -m app.db.init_db` 的 `sync_model_columns`(跨方言按 ORM 元数据补齐)。
- **验证必须进真实 MySQL**：改表结构走 `docker restart ai-agent-api` 触发迁移；**绝不在容器外脚本直连 SQLite 测**(连 agent.db 非 MySQL，假 404/种子不可见)。动手前先 `inspect` 真实 MySQL 现有列。
- 激活：api 容器 bind 挂载→后端改码 `docker restart ai-agent-api` 即生效无需 rebuild；web 容器只读挂载 `web/dist`→前端改完须 `vite build` 重生 dist。

## 🔵 产品定位（ADR-026）
「自托管小团队 AI 工作台」。三层：①底座层(Auth/Provider/Chat/KB/Memory，不再横向扩) ②扩展面层(MCP/Skill/Hook，管理员域) ③垂直应用层(电商套图等，开发重点)。技术栈维持 Web 不转桌面。

## 🔵 权限模型（RBAC v2 · 已全部落地验证 2026-07-19）
- **模型**：4 表 `Resource`(菜单/权限码/API 统一注册, parent_code 树形, is_system 受保护) / `Role`(全局角色不按团队细分, is_default 新用户自动授) / `RolePermission` / `UserRole`(team_id 恒 NULL)。
- **判定**：`can(user,perm,team_id,db)` 加性并集(角色∪个人∪团队 scope, 超管恒真, 无负权限)，禁止散落 `role==`/`is_superuser` 检查。
- **动态菜单**：`GET /api/system/menus` 由 Resource(type=menu) 驱动，前端 `BasicLayout` 拉接口渲染(保留静态 fallback)。系统管理父菜单(`admin.system.manage` 门控)收纳用户管理/资源管理/角色管理/团队管理员权限。
- **双权限源合并(Phase 4/ADR-031)**：`Resource(type='permission')` 为权限码唯一真源，`CATALOG` 常量种子化幂等 upsert 进 resources；已删 `permission_catalog` 表(残留 36 行孤儿，可后续手工清)。
- **两级委派**：系统超管→`team_admin_scopes`→`user_permissions`；团队入团审批流(join-requests/invites，approve→建成员+授 PERSONAL_DEFAULT 团队权限+写 approval_logs)。
- **账号**：admin@example.com/admin123 为超管(全库仅1)；konghong(kh1763751448@gmail.com)为团队管理员(29 码 scope=除 admin.* 外全部)。
- **锁定决策**：全局角色不按团队细分；"创作案例多团队使用"=内容分发(born-personal+显式 share)，推迟 Phase 5。
- 设计文档：`designs/plan-permission-rbac.md`、`designs/plan-permission-rbac-v2-system-module.md`(ADR-030)。

## 技术栈
后端 FastAPI+uvicorn(8010)+SQLAlchemy+SQLite(本地)/MySQL(Docker `ai_agent`)；前端 Vite+React19+TS(dev 5173)；Docker 栈 `http://localhost/`(web:80) 连 MySQL。AI: OpenAI-compatible(agnes-2.0-flash/image/video)；向量 ChromaDB；桶 `chat-uploads`/`ai-agent-minio`。

## 🔥 关键架构约束（硬坑）
- **时间戳必须带时区(输出 `Z`)**：DB 存朴素 UTC；不带 Z 浏览器 GMT+8 当本地→算成 8h 前。Pydantic `field_serializer` 输出 `...Z`；前端解析按 UTC；判超时优先 `updated_at`。
- **列表排序**：聊天会话列表按 `created_at.asc()`（最新排最下）。
- **端口一致**：.env/代理/启动均 8010。DB 驱动 `app/db_url.py:normalize_db_url()`；模型 `app/models.py`(MySQL 兼容)；Pydantic 响应新增列必须可空 `X | None = None`。
- **绝不在 startup 做阻塞/可能失败的网络调用**(pip/外部HTTP)→曾整挂；自愈放后台线程，subprocess env 剥离 `*_proxy` 走直连。
- **绝把请求作用域 ORM 传入后台/异步任务**：`get_db` 返回即 close 变 detached；主线程先取标量字段再闭包，后台线程新开 `SessionLocal()`。
- **Docker 前端白屏=nginx sendfile bug**：`docker/nginx.conf` `server` 块加 `sendfile off;`。
- **SQLite vs MySQL 测试陷阱**：容器外跑脚本连 SQLite 非 MySQL→种子数据 API 不可见假 404；须进 api 容器用 app sessionmaker 或走 API 端点。
- **🔥 响应模型漏字段会静默致残前端**：新增"用户标志类"字段须同步进 `UserRead`(/auth/me 曾漏 is_team_admin 致 Phase B 全失效，ADR-029)。任何"前端依赖后端字段"的改动，改完要查响应模型是否真正序列化该字段。

## 🔧 Docker 部署激活与迁移机制
- api 容器 bind 挂载 `C:\workspace\ai-agent → /app`(rw)，启动 CMD=`python -m app.db.init_db`→uvicorn。**后端改码 `docker restart ai-agent-api` 即生效无需 rebuild**；重启跑 `sync_model_columns` 给旧 MySQL 表补缺失列。
- web 容器只读挂载 `web/dist`：前端改完须 `vite build` 重生 dist，nginx 读盘即生效；必要时 `docker restart ai-agent-web`。
- admin 账号：重启后 `username=admin` 提拔超管，凭据对齐 `INIT_SUPERUSER_EMAIL/PASSWORD`(admin@example.com/admin123)。
- **🔥 整栈 docker 偶发重启**：若 api/web/worker 停在 `Created`，**先 `docker start ai-agent-api ai-agent-web` 再排查**，勿误判代码故障。MySQL 持久卷重启不丢数据；init_db 种子已随代码演进，重启不重建已删表。

## 出网代理韧性（app/http_client.py）
Docker 注入 `HTTPS_PROXY=host.docker.internal:33210`(可能不可达)；`ensure_proxy_strategy()` 探测不可达走直连；`request/download_with_fallback()` 每次直连兜底。设 `DISABLE_PROXY_AUTOFALLBACK=1` 保留强制代理。图片生成超时 300s/视频提交120s/轮询60s/下载120s。
- **🔥 代理的来历(2026-07-09 commit 7dd540d「新增商品」)**：为**电商套图媒体生成下载**加的——把外部 AI 生成的图/视频结果拉回容器存 MinIO(`media.py/media_new.py/media_retry.py/gallery_service.py` 调用 `request/download_bytes_with_fallback`)。**聊天并不需要代理、直连就行**，只是继承了整个容器注入的 `HTTPS_PROXY` 环境变量；`app/agent.py` 的 `_make_chat_http_client()` 只借 http_client 的 `_proxy_url/_proxy_reachable` 做 2s 探测，**没用 `request_with_fallback` 兜底**→代理 flaky 时聊天卡 60s+ 空白(2026-07-20 排查确认)。根因=代理时通时断 + 聊天路径无兜底。
- **✅ 已修复并验证(2026-07-20)**：`app/agent.py` 的 `_make_chat_http_client()` 改为**默认直连**(`httpx.Client(trust_env=False)` 无视注入代理)、`force_proxy=True` 才走代理兜底；`_create_llm_from_config(config, force_proxy=False)` 加 `max_retries=2` + `http_socket_options=()`；`ask_agent_stream_gen` 加 `_stream_once` 生成器 + `yield from`：流式异常→**先重试直连**、最后才试代理；空响应→**重试直连**(绝不碰死代理)。容器内实测：HTTPS_PROXY 仍注入且可达的最坏情况下，默认客户端 `trust_env=False`(直连)，流式 ~12s 稳定出内容。媒体生成路径零影响(独立 http_client)。`DISABLE_PROXY_AUTOFALLBACK=1` 强制代理语义保留。
- **🔥 聊天"慢"的第二个根因(2026-07-20 实测 konghong 发"查车次余票"确认)**：部署 `docker-compose.yml` 把 `ENABLE_CONTEXT_SERVICE/ENABLE_MCP_TOOLS/ENABLE_SKILL_TOOLS/ENABLE_HOOKS` **全设为 true** → `ask_agent_stream_gen` 里 `complex_path` 恒 True → **每条聊天(哪怕无 agent)都走重型非流式 `ask_agent`**(上下文检索 + 加载 MCP/Skill 工具 + 对实时问题调联网搜索工具 + 末次生成)，耗时 70–100s 且整段一次性返回(无 token 流式，前端空白屏)。对照：同 query 直连 `llm.stream` 仅 9–32s。这是**配置行为非代码 bug**；要简单聊天快需关部分开关回落轻量流式，但会失去联网/记忆能力。诊断埋点已清除、A+B 重试修复保留。

## 🔥 LLM 模型解析来源（2026-07-17 用户纠正）
聊天模型来自「AI 提供商模块」非全局 settings 兜底。`ChatRequest` 带 `provider_id`+`model_name`；未带取用户默认提供商(`Provider.is_default && enabled`)的 `is_default_chat` 模型。`settings.openai_model` 仅 `_resolve_llm_config` 第4步兜底。

## 用户协作偏好
- 不凭空臆想需求；数据隔离硬约束(每用户只用自己配置资源)。
- **🔥 前端 UI 修改必须浏览器预览验证后才能回复**(含 CSS/视觉)。
- **需求理解偏差教训**：UI 元素摆哪有歧义先确认布局再动手，错位置按钮要撤掉而非叠加。
- **浏览器真机回归(Playwright 坑)**：受管 Node `C:/Users/Administrator/.workbuddy/binaries/node/versions/22.22.2/node.exe` + workspace playwright；chromium `C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1228`；启动 `--no-sandbox`。**zustand persist 坑**：持久化 `agent-auth` 只存 token+user 不存 isAuthenticated，刷新回退 false→被守卫踢回 /login，故测试须走真实 UI 登录。拿 token：`POST /api/auth/login {"email":"admin@example.com","password":"admin123"}`。antd 表格内按钮匹配用 `row.locator('button:has-text("审批")')`；Modal footer 按钮用 `.ant-modal-content .ant-btn-primary`。

## 前端架构坑（React19+antd）🔥
- **致命坑**：`react@19`+`antd@5` 未装 `@ant-design/v5-patch-for-react-19` 时，antd 静态 `message.xxx`/`Modal.confirm` 静默失效。修复：`web/src/main.tsx` **第一行** import(须在 import antd 前)。
- MemoryPanel accept/reject 模式：toast 失败绝不阻塞列表刷新——「先 await api → 失败 return → 无条件 load() → 再 message.success(外层 try/catch)」。Toast 位置 `global-theme.css` 加 `.ant-message{top:8px!important}` 兜底。

## 电商套图
- 提示词引擎数据驱动 `Resolver→CopyPolicy→Assembler→Linter`，事实源 `gallery_config.py`+`gallery_prompt.py`。双语 `build_prompt_bilingual()`→`{prompt:中文展示, prompt_en:英文生成}`，英文版零中文。
- **🔥 agnes-2.0-flash 带思维链推理**：`max_tokens` 太小思考占满→content 空→误判降级。`AI_PROMPT_MAX_TOKENS`≥4096，空/失败重试 6144/8192，绝写死小值。
- **规格参数图中文乱码=方案A**：扩散模型写汉字必乱码→图像模型只出无文字视觉，中文由 `app/spec_overlay.py` 用 CJK 字体(`app/assets/fonts/simhei.ttf`，回退 NotoSansCJK)叠加。
- 生成图存储 MinIO(`ai-agent-minio`)→`gallery/results/{uuid}{ext}`；页面走同源 `/api/gallery/files/{key}`(先 MinIO 后本地回退)。
- **🔴 删除任务硬约束**：进行中(pending/running)禁止删→400；卡死(running 且 created>30min)例外。删除同步删 MinIO+本地+级联 GalleryRecord；前端按钮常可点，活跃任务点选 `message.warning` 不弹框。
- **🔥 gallery worker 必须在 startup 启动**；孤儿恢复 `_recover_orphans` 判定 `running AND updated_at < PROCESS_START-120s`；resume 须跳过 chat 提示词生成；worker `ThreadPoolExecutor(max_workers=2)`。
- **上游 agnes 不稳定**：chat 偶卡/image 间歇 SSLEOFError+queue-full 503；chat `max_retries=1`+resume 绕过+并发+`media_retry`；个别图 failed 用户点「重做」绕过。
- **🔥 agnes 流式行为**：agnes-2.0-flash 将整个回答在一个 SSE delta 里一次性返回(非逐 token)，首响应延迟 ~16s。后端 `llm.stream()` 不产出增量 token；**前端打字机动画(24ms interval)是"字一个一个跳"效果唯一来源**。测试聊天流式须等 ≥16s。
- **聊天切页持久化**：`useChatStore`(zustand) byThread 内存缓存 + `fetchLatest` DB 重载 + `active-chat-thread` localStorage → remount 时 hydrate(cache→DB)。已验证 SPA 切换+全页 reload 均不丢消息。
- **CSS 双文件陷阱**：`.pr-*`/`.plan-row`/`.prompt-badge` 只在 `web/src/styles/gallery-design-system.css`(App.tsx 全局导入生效)改；`gallery.css` 不再重复定义。

## 跨会话记忆（ADR-024/ADR-025 Tier1）
`ContextService.build()` 读本 MEMORY.md 作 system 块注入(开关 `ENABLE_WORKSPACE_MEMORY=true`)。改记忆系统新开关须 docker-compose.yml api `environment` 显式注入(compose 优先级>根.env)。用户级偏好：`_user_profile_memory(user_id)` 无条件加载 `UserMemory` 中 active+layer>=1 偏好/事实；Tier2 语义回忆待配 embedding。

## 聊天每轮性能优化（plan-chat-perf-v2 · 2026-07-21 实施）
设计稿 `designs/plan-chat-perf-v2.md`。全部按文档落地，每根优化独立开关（关→回退 complex_path，零能力回归）。
- **开关（app/settings.py + docker-compose.yml）**：`ENABLE_TOOL_POOL`(默认true)、`ENABLE_KB_GATE`(默认true)、`ENABLE_INTENT_ROUTER`(默认true)、`ENABLE_ONDEMAND_KB`(默认false，激进项)、`ENABLE_TOOL_PRUNE`(默认true)+`TOOL_PRUNE_TOP_K`(默认8)。
- **§1.1 工具池缓存**（`app/mcp_tools.py`）：`_TOOL_POOL` 按 user_id 缓存 StructuredTool，配置 hash 校验 + `invalidate_tool_pool()` 事件失效（MCP CRUD 端点已接线）；工具闭包改自开 SessionLocal（`_call_mcp_tool`），跨请求复用安全。
- **§1.2 Catalog 瘦身**：`get_mcp_tool_catalog` 仅列「名称+60字用途」，保留 TOOL USAGE RULE。
- **§1.3 KB 前置门控**（`agent.py`）：`_needs_knowledge_base()` 用纯正则实体+召回意图词，平凡轮跳过 semantic_recall/reflex。
- **§2.1 Intent Router**（`ask_agent_stream_gen`）：T0 纯问候→直答(<2s 路径)；T1 实时意图→仅工具(skip_kb)；T2 全量。T0 须整句仅问候（正则 `^[\s\W]*(问候)[\s\W]*$`）且排除实时意图+agent 无 KB 绑定，避免误判漏工具。
- **§2.2 按需 KB 工具** `retrieve_knowledge`：开启 `ENABLE_ONDEMAND_KB` 时关自动语义回忆，改由模型按需调用（仅 enable_context_service 时注入）。
- **§2.3 top-k 剪枝** `_prune_tools`：中文按字级重叠（无空格须按字切），仅绑最相关 top-k，不影响缓存。
- **验证**：10/10 单测 `tests/test_chat_perf_v2.py` 通过；容器重启干净（MySQL OK）；`/chat` 200、`/chat-stream` 流式 200，日志见 `intent router: tier=...` 与 `tool pool HIT/MISS`。注：`test_agent_extensions.py::test_ask_agent_runs_skill_and_hooks` 为**预先存在失败**（假 LLM 无 `.stream`），与本改动无关。

## 通用
- 生成文件归 `ai/agent-output/`：`overviews/` `verify-shots/` `logs/`。
- 不可移动：`agent.db`/`.env`/运行时SQLite；文档(PRD/FDD/README/AGENTS/TASKS)；`designs/`、`疑问/`。
