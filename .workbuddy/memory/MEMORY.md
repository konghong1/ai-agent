# 项目长期记忆 — AI Agent Platform（精简合并版）

> 维护规则：大改追加当日 `YYYY-MM-DD.md`；本文件只留跨会话有用的硬约束/坑/架构事实。详细历史见各 `YYYY-MM-DD.md`。

## 🔴 最高优先级铁律（用户 2026-07-16 亲定，违反即事故）
1. **改动必须测试/回归通过才能回复**（硬性）：前端改动用真实浏览器(Playwright 无头)点一遍确认行为发生；后端改动用单元/接口级验证(真实 API + 真实 DB 状态核对)；存量代码改动须做回归(旧功能不破、旧数据不丢)；重启/迁移/删数据前先隔离环境验证再动生产。
2. **绝不在测试/调试破坏真实用户数据**：禁止对真实用户数据做 DELETE/cleanup/drop/truncate；测试删除/重做只用隔离账号；清数据前先查 ID 确属测试数据；文件删除优先软删/回收站(`trash/` 前缀≥30天)，绝不硬删 DB+存储。
3. **删除功能安全底线**：`delete_task` 级联硬删 GalleryRecord+MinIO+本地+GalleryTask 行不可逆；硬删须改软删，新增删除接口默认软删，确需硬删须双重确认+仅限本人+审计日志。

## 🔴 代码改动须兼容容器部署 SQL（MySQL）· 永久规则（2026-07-19 用户亲定）
> 核心原则：**任何 ORM 模型/字段改动，都必须保证在真实 Docker+MySQL(`ai_agent`) 部署上也能迁移与运行，不能只在本地 SQLite `agent.db` 跑通就当完成。** 线上跑的是 MySQL，不是 SQLite。
- **加列铁律**：新增模型列若 `NOT NULL` 必须带 `server_default`（Boolean 用 `server_default="0"`），否则 `sync_model_columns` 在 MySQL 非空表上 `ALTER ... ADD NOT NULL` 失败→列加不上→seed/查询报 `Unknown column`→api 起不来。允许 NULL 的列也优先给 server_default。
- **TEXT 列禁带默认值**（MySQL8 报 1101）；VARCHAR 可带默认值。
- **双迁移路径认知**：①`core/database.py:_migrate_sqlite_columns` 只管本地 SQLite，生产 MySQL 不走它；②生产加列靠 api 容器启动 CMD `python -m app.db.init_db` 的 `sync_model_columns`（跨方言、按 ORM 元数据自动补齐）。改模型后确认它能被覆盖。
- **验证必须进真实 MySQL**：改完表结构走 `docker restart ai-agent-api` 触发迁移，或先用 `ALTER ADD`+`DROP` 在真实 MySQL 预验证可还原；**绝不在容器外脚本直连 SQLite 测**（会连到 `agent.db` 而非 MySQL，假 404/种子不可见）。
- **动手前先只读探查**：涉及表结构改动时，先 `inspect` 真实 MySQL 现有列，确认缺失项与冲突，再改代码。
- 激活代价最小化：api 容器 bind 挂载→后端改码 `docker restart ai-agent-api` 即生效无需 rebuild；web 容器只读挂载 `web/dist`→前端改完须 `vite build` 重生 dist。

## 🔵 产品定位（ADR-026 · 生效）
- 收窄为「自托管小团队 AI 工作台」，非通用 AI 平台。三层：①底座层(Auth/Provider/Chat/KB/Memory，不再横向扩) ②扩展面层(MCP/Skill/Hook，管理员域，降级"高级设置") ③垂直应用层(电商套图等，开发重点)。
- 技术栈维持 Web 不转桌面；HA/万级并发标记过早优化(metrics 留观测)；重心=套图做深+扩展面试新垂直应用。

## 🔵 权限模型（两级委派 · 最细粒度 · 数据驱动）
- **完整设计**：`designs/plan-permission-rbac.md`（取代 ADR-027 简化角色基线）。权限以 `permission_code` 为原子单位，目录统一注册于 `resources(type='permission')`(由 `CATALOG` 常量种子化、可扩展，ADR-031)；**两级委派** 系统超管→`team_admin_scopes`→`user_permissions`(单一真源，取代 TeamMember.permissions JSON)；`can(user,perm,team_id,db)` 唯一判定入口，禁止散落 `role==`/`is_superuser` 检查。菜单按 permission_code 渲染(`BasicLayout` 用 `/api/me/permissions` 过滤)。
- **Phase A 已落地并验证(2026-07-19)**：4 表 + `User.is_team_admin` + join/invite 审计列(均 MySQL 兼容)；`permissions.py` 含目录常量+种子+`can()`+`get_team_admin_scope`+`ensure_personal_defaults`+`backfill_base_permissions`；`api.py` 含 `/permissions/catalog`、`/me/permissions`、`/admin/team-admins`、`/teams/{id}/members/{uid}/permissions`、`/teams`、`/teams/{id}/members`；前端 `BasicLayout` 权限菜单化 + 超管「团队管理员权限」页 + 团队管理员「团队/成员权限」页。委派链实测通过。konghong(kh1763751448@gmail.com)现为团队管理员(29 码 scope=除 admin.* 外全部)，admin@example.com 为超管。
- **Phase B 已落地并验证(2026-07-19)**：团队入团审批流——自申请 `POST /teams/{id}/join-requests`→pending，管理员 review(approve→建成员+授 PERSONAL_DEFAULT 团队权限+写 approval_logs / reject→仅写日志)；邀请 `POST /teams/{id}/invites`→pending，用户 `respond`(accept→建成员+授团队权限+写日志)。新增 4 权限码(providers.view/manage、prompt.view/manage)，修复 hook.view 遗漏，`/providers`+`/prompt-templates` 菜单纳入权限门控，PERSONAL_DEFAULT 含 team.view，is_system 维持仅 admin.* 三项。前端 Teams.tsx 完整选项卡(团队空间/发现团队/我的申请/我的邀请+待审/邀请管理)。后端全链路+前端 Playwright 真机验证通过。
- **ADR-028（已落地）**：单登录 + `is_superuser` 超管；`require_superuser` 守卫；`promote|demote` 接口。
- **RBAC v2 系统管理模块（Phase 0-3 已落地并真机验证 2026-07-19）**：新增 4 表 `Resource`(菜单/权限码/API 统一注册, `parent_code` 树形, `is_system` 受保护) / `Role`(全局角色不按团队细分, `is_default` 新用户自动授) / `RolePermission` / `UserRole`(team_id 恒 NULL)；`can()` 改为**加性并集**(角色∪个人∪团队 scope, 超管恒真, 无负权限)。动态菜单：`GET /api/system/menus` 由 Resource(type=menu) 驱动，前端 `BasicLayout` 拉接口渲染(保留静态 fallback)。系统管理父菜单(`admin.system.manage` 门控)收纳：用户管理(移入+角色分配抽屉)/资源管理/角色管理/团队管理员权限。后端 `app/api.py` 管 `CRUD /system/resources|/system/roles|/system/roles/{id}/permissions|/users/{id}/roles`；前端 `ResourceManage`/`RoleManage`/`UserManagement` 抽屉。设计 `designs/plan-permission-rbac-v2-system-module.md`(ADR-030)。
- **锁定决策（用户 2026-07-19 亲定）**：按动态菜单实现；**全局角色不按团队细分**；"创作案例发布给多团队使用"=内容分发(解法② born-personal+显式 share)，非数据归属，推迟到 Phase 5。
- **Phase 4 双权限源合并（已落地并真机验证 2026-07-19）**：删除 `permission_catalog` 表/模型/种子，`Resource(type='permission')` 成为权限码**唯一真源**（`CATALOG` 常量退化为种子定义，重启幂等 upsert 进 resources）；`Resource` 新增可空 `description` 列（种子与 ResourceCreate/Update 均携带）；运行时（catalog API/角色授权校验/团队管理员 scope 校验/超管全集/`/api/system/menus`）全部改查 resources。ADR-031。后端 15/15 + 前端 7/7 PASS。`permission_catalog` 表沦为孤儿表（残留 36 行，无代码引用，可后续手工清）。

## 技术栈
- 后端 FastAPI+uvicorn(8010)+SQLAlchemy+SQLite(本地)/MySQL(Docker `ai_agent`)；前端 Vite+React19+TS(dev 5173)；Docker 栈 `http://localhost/`(web:80) 连 MySQL。
- AI: OpenAI-compatible，agnes-2.0-flash/agnes-image-2.x/agnes-video-v2.0；向量 ChromaDB；桶 `chat-uploads`/`ai-agent-minio`。

## 🔥 关键架构约束（硬坑）
- **时间戳必须带时区(输出 `Z`)**：DB 存朴素 UTC；不带 Z 浏览器 GMT+8 当本地→算成 8h 前。Pydantic `field_serializer` 输出 `...Z`；前端解析按 UTC，绝不直接 `new Date(naiveUtc)`；判超时优先 `updated_at`。
- **列表排序**须按用户需求确认：聊天会话列表按 `created_at.asc()`（最新排最下）。
- **端口一致**：.env/代理/启动均 8010。DB 驱动 `app/db_url.py: normalize_db_url()`；模型 `app/models.py`(MySQL 兼容)；Pydantic 响应新增列必须可空 `X | None = None`。
- **绝不在 startup 做阻塞/可能失败的网络调用**(pip/外部HTTP)→曾整挂；自愈放后台线程，subprocess env 剥离 `*_proxy` 走直连。
- **绝把请求作用域 ORM 传入后台/异步任务**：`get_db` 返回即 close 变 detached；主线程先取标量字段再闭包，后台线程新开 `SessionLocal()`。
- **Docker 前端白屏=nginx sendfile bug**：`docker/nginx.conf` `server` 块加 `sendfile off;`。
- **SQLite vs MySQL 测试陷阱**：容器外跑脚本连 SQLite 非 MySQL→种子数据 API 不可见假 404；须进 api 容器用 app sessionmaker 或走 API 端点。
- **🔥 响应模型漏字段会静默致残前端**：`/auth/me` 的 `UserRead` 曾漏 `is_team_admin` → 前端 `canManage=is_superuser||is_team_admin` 对真实团队管理员恒 false，Phase B 团队管理员标签/审批/邀请全失效。新增"用户标志类"字段须同步进 `UserRead`（已修 ADR-029）。同理任何"前端依赖后端字段"的改动，改完要查响应模型是否真正序列化该字段。

## 🔧 Docker 部署激活与迁移机制（硬事实）
- **api 容器 bind 挂载 `C:\workspace\ai-agent → /app`(rw)**，启动 CMD=`python -m app.db.init_db`(CLI，含 `sync_model_columns` 跨方言加列+seed)→uvicorn。**后端改代码只需 `docker restart ai-agent-api` 即生效，无需 rebuild 镜像**；重启会跑 `sync_model_columns` 给旧 MySQL 表补缺失列。
- **web 容器只读挂载 `web/dist`**：前端改完须 `vite build`(即 `node node_modules/vite/bin/vite.js build`) 重生 dist，nginx 读盘即生效；必要时 `docker restart ai-agent-web`。
- **admin 引导账号已对齐**：重启后 `username=admin` 被提拔为超管，凭据对齐到 `INIT_SUPERUSER_EMAIL/PASSWORD`(默认 `admin@example.com`/`admin123`)。真实 MySQL 现为 `admin@example.com`/`admin123` 超管(2026-07-19 验证：登录200+is_superuser=true，全库仅1超管)。
- **🔥 整栈 docker 偶发重启运维提醒**：本机 docker 栈（ai-agent-api/web/worker/minio/mysql）曾被宿主/daemon 整体重启过一次，api/web/worker 会停在 `Created` 未运行、MySQL/MinIO 才起来数秒。若发现 api 不在 `Up` 状态，**先 `docker start ai-agent-api ai-agent-web` 再排查**，勿误判代码故障。MySQL 用持久卷，重启不丢数据；且 `init_db` 种子已随代码演进（如已移除 `seed_permission_catalog`），重启不会重建已删表。

## 出网代理韧性（app/http_client.py）
Docker 注入 `HTTPS_PROXY=host.docker.internal:33210`(可能不可达)；`ensure_proxy_strategy()` 探测不可达走直连；`request/download_with_fallback()` 每次直连兜底。设 `DISABLE_PROXY_AUTOFALLBACK=1` 保留强制代理。图片生成超时 300s/视频提交120s/轮询60s/下载120s。

## 🔥 LLM 模型解析来源（2026-07-17 用户纠正）
- 聊天模型来自「AI 提供商模块」非全局 settings 兜底。`ChatRequest` 带 `provider_id`+`model_name`；未带取用户默认提供商(`Provider.is_default && enabled`)的 `is_default_chat` 模型。`settings.openai_model` 仅 `_resolve_llm_config` 第4步兜底。

## 用户协作偏好（重要）
- 不凭空臆想需求；数据隔离硬约束(每用户只用自己配置资源)。
- **🔥 前端 UI 修改必须浏览器预览验证后才能回复**(含 CSS/视觉)。
- **需求理解偏差教训**：UI 元素摆哪有歧义先确认布局再动手，错位置按钮要撤掉而非叠加。
- **浏览器真机回归工作流(Playwright 关键坑)**：
  - 受管 Node `C:/Users/Administrator/.workbuddy/binaries/node/versions/22.22.2/node.exe` + workspace playwright(`C:/Users/Administrator/.workbuddy/binaries/node/workspace/node_modules`)；chromium `C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1228`；启动 `--no-sandbox`。
  - **zustand persist 注入 localStorage 的坑**：持久化 `agent-auth` 时**只存 `state.token`+`state.user`，不存 `isAuthenticated`**，刷新后该字段回退 false → 被守卫踢回 `/login`。故测试必须走真实 UI 登录（而非注入 localStorage 免登录）。
  - 拿 token：admin 登录 `POST /api/auth/login {"email":"admin@example.com","password":"admin123"}`。
  - antd 表格内按钮匹配用 `row.locator('button:has-text("审批")')` 而非 getByRole；Modal footer 按钮用 `.ant-modal-content .ant-btn-primary` 或 getByRole 更稳。

## 前端架构坑（React19+antd）🔥
- **致命坑**：`react@19`+`antd@5` 未装 `@ant-design/v5-patch-for-react-19` 时，antd 静态 `message.xxx`/`Modal.confirm` 静默失效。修复：在 `web/src/main.tsx` **第一行** import(须在 import antd 前)。
- MemoryPanel accept/reject 修复模式：toast 失败绝不阻塞列表刷新——「先 await api → 失败 return → 无条件 load() → 再 message.success(外层 try/catch)」。Toast 位置 `global-theme.css` 加 `.ant-message{top:8px!important}` 兜底。

## 电商套图（合并精简）
- 提示词引擎数据驱动 `Resolver→CopyPolicy→Assembler→Linter`，事实源 `gallery_config.py`+`gallery_prompt.py`。双语 `build_prompt_bilingual()`→`{prompt:中文展示, prompt_en:英文生成}`(生成送 `prompt_en`)，英文版零中文。
- **🔥 agnes-2.0-flash 带思维链推理**：`max_tokens` 太小思考占满→`content` 空→误判降级。规则 `AI_PROMPT_MAX_TOKENS`≥4096，空/失败重试 6144/8192，绝写死小值。
- **规格参数图中文乱码=方案A**：扩散模型写汉字必乱码→图像模型只出无文字视觉，中文由 `app/spec_overlay.py` 用 CJK 字体(`app/assets/fonts/simhei.ttf`，回退 NotoSansCJK)叠加。
- 生成图存储 MinIO(`ai-agent-minio`)→`gallery/results/{uuid}{ext}`；页面走同源 `/api/gallery/files/{key}`(先 MinIO 后本地回退)。
- **🔴 删除任务硬约束**：进行中(pending/running)禁止删→`delete_task` raise ValueError→路由400；卡死(running 且 created>30min)例外。删除用 antd `Modal.confirm`(须 React19 补丁)→同步删 MinIO+本地+级联 GalleryRecord；前端按钮常可点，活跃任务点选 `message.warning` 不弹框。
- **🔥 gallery worker 必须在 startup 启动**；孤儿恢复 `_recover_orphans` 判定 `running AND updated_at < PROCESS_START-120s`；resume 必须跳过 chat 提示词生成；worker `ThreadPoolExecutor(max_workers=2)`。
- **上游 agnes 不稳定**：chat 偶卡/image 间歇 `SSLEOFError`+`queue-full` 503；代码侧 chat `max_retries=1`+resume 绕过+并发+`media_retry`；个别图仍可能 failed(用户点「重做」绕过)。
- **🔥 agnes 流式行为（2026-07-19 发现）**：agnes-2.0-flash 将**整个回答在一个 SSE delta 里一次性返回**（非逐 token），首响应延迟 ~16s（新旧线程均如此，是提供商家固有时延）。因此后端 `llm.stream()` 不产出增量 token；**前端打字机动画(`typewriterTick` 24ms interval)是"字一个一个跳"效果的唯一来源**。测试聊天流式须等 ≥16s 才能看到内容。
- **聊天切页记录持久化**：`useChatStore`(zustand 模块级) byThread 内存缓存 + `fetchLatest` DB 重载 + `active-chat-thread` localStorage → remount 时 hydrate(cache→DB)。已验证 SPA 切换+全页 reload 均不丢消息。
- **CSS 双文件陷阱**：`.pr-*`/`.plan-row`/`.prompt-badge` 只在 `web/src/styles/gallery-design-system.css`(App.tsx 全局导入生效)改；`gallery.css` 不再重复定义。

## 跨会话记忆（ADR-024 生效 / ADR-025 Tier1 生效）
- `ContextService.build()` 读本 MEMORY.md 作 system 块注入(开关 `ENABLE_WORKSPACE_MEMORY=true`)。改记忆系统新开关须 docker-compose.yml api `environment` 显式注入(compose 优先级>根.env)。
- 用户级偏好跨会话召回：`_user_profile_memory(user_id)` 无条件加载 `UserMemory` 中 `active`+`layer>=1` 偏好/事实；Tier2 语义回忆待配 embedding。

## 通用
- 生成文件归 `ai/agent-output/`：`overviews/` `verify-shots/` `logs/`。
- 不可移动：`agent.db`/`.env`/运行时SQLite；文档(PRD/FDD/README/AGENTS/TASKS)；`designs/`、`疑问/`。
