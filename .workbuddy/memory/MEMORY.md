# 项目长期记忆 — AI Agent Platform

## 技术栈
- 后端: FastAPI + uvicorn (端口 8010) + SQLAlchemy + SQLite
- 前端: Vite + React + TypeScript (端口 5173)
- AI: LangChain + OpenAI-compatible API (agnes-2.0-flash)
- 向量库: ChromaDB

## 架构注意事项
- **async/sync 混用是最大性能陷阱**: FastAPI 的 `async def` 端点中不能直接调用同步阻塞函数（如 `requests.post`、`llm.invoke`），会冻结事件循环。必须用 `asyncio.to_thread()` 包装。
- `chat_stream` 的 SSE `event_generator` 是 async def，里面的所有同步调用（ask_agent、_handle_video/image_generation）已用 asyncio.to_thread 修复。
- `watch_video_status` 已正确使用 asyncio.to_thread 轮询。
- 普通 `def` 端点 FastAPI 自动放线程池，无需手动处理。

## 端口配置
- .env PORT=8010, Vite 代理目标 127.0.0.1:8010, README 启动命令 --port 8010
- 三者必须一致，否则 ECONNREFUSED

## 日志
- 生产环境用 INFO 级别，openai/httpx 用 WARNING
- DEBUG 级别会产生海量日志，严重影响性能

## 数据库驱动（重要）
- `docker/.env` 默认 `DATABASE_URL=mysql://...`（无 driver），SQLAlchemy 默认走 `mysql+mysqldb`，需要未安装的 C 扩展 `MySQLdb`。
- 已装的是纯 Python 的 `pymysql`（见 `requirements.txt`）。统一用 `app/db_url.py: normalize_db_url()` 注入驱动：`mysql://` → `mysql+pymysql://`，`postgresql://` → `postgresql+psycopg2://`。
- 三处 `create_engine`（`app/core/database.py`、`app/db/__init__.py`、`app/worker/media_worker.py`）都已改用 normalize_db_url，勿改回裸 `DATABASE_URL`。
- **模型遮蔽坑**：`app/models.py` 是 MySQL 兼容模型（已改名前的 `app/models/` PG 包会遮蔽它）。`from app import models` 必须解析到 `app/models.py`，否则建表用 PG 类型（UUID/JSONB）在 MySQL 上失败。PG 模型现位于 `app/models_pg/`。
- 建表由 API 启动时的 `python -m app.db.init_db`（`create_tables()` + `seed_database()`，用 ORM）负责，不依赖 `docker/db/init_*.sql`。
- MySQL InnoDB 索引键上限 3072 字节：长 VARCHAR 唯一索引要用 `mysql_length` 前缀索引（如 `storage_path`）。

## 存储桶用途（重要区分）
- **用户自己上传的聊天参考图** → 独立桶 `chat-uploads`（`app/api.py:347` `CHAT_UPLOAD_BUCKET`，端点 `POST /api/chat/upload`）。返回 URL 带 `?bucket=chat-uploads`，由 `inline_reference_image()` 内联成 base64 再调远程模型（远程模型访问不到本地/私有地址，必须转 base64）。
- **AI 生成的图片/视频产物** → 默认桶 `ai-agent-minio`（走 `media_assets` 媒体生成流程），与 `chat-uploads` 严格分离。
- `app/storage/__init__.py` 新增 `get_storage_backend_for_bucket(bucket)`（按桶缓存 backend）与 `inline_reference_image(ref)`（by-key 代理 URL→对应桶取数据→base64；`data:` 与外部 `http(s)` 透传）。by-key 代理支持 `?bucket=`。
- `docker-compose.yml` 的 minio-init 已加建 `chat-uploads` 桶并设为 public（首次上传 `_ensure_bucket` 也会自动建）。

## 外部网络 / 代理（重要运维坑）
- 外网 AI 服务（`apihub.agnes-ai.com` 等）建议走代理出网。**已修复注入**：`docker-compose.yml` 的 `api` 与 `worker` 服务现在注入 `HTTPS_PROXY`/`HTTP_PROXY`，且因容器内 `127.0.0.1` 指容器自身，必须改用 `host.docker.internal:33210` 并加 `extra_hosts: - "host.docker.internal:host-gateway"`。`NO_PROXY` 含 `localhost,127.0.0.1,::1,minio,mysql,ai-agent-minio,ai-agent-mysql`（MinIO raw socket + minio client 忽略代理，但显式排除以防万一；已验证注入代理后 MinIO 仍可达）。
- 代理端口 `33210` 取自主机 `HTTPS_PROXY`（WorkBuddy 沙箱代理），随会话/环境变化，**可能随时拒绝连接（Errno 111）**。原脆弱点（设了 `HTTPS_PROXY` 的请求在代理失效时不自动回退直连）**已修复**：见 `app/http_client.py` 代理韧性层（2026-07-09）。
- **图片生成超时坑（已修）**：`MediaService.generate_image`（`app/media.py:109` 与 `app/media_new.py:102`）原 `timeout=120`。带参考图（img2img）的生成本身就慢（实测小图 30–48s，真实大图更久），偶发超过 120s → `Read timed out. (read timeout=120)`。已把图片生成超时提到 **300s**，视频提交 30→120、视频轮询 15→60、下载 60→120。
- 验证：完整链路（上传参考图 → `POST /api/chat` provider_id=2 `agnes-image-2.0-flash`）返回 200，约 52s（走代理）；裸 `MediaService.generate_image` 约 28–31s。图片模型归属 `provider_id=2`（user_id=2），admin(user_id=1) 走该路由会因 `provider.user_id==current_user.id` 不成立而落到聊天路径——这是正常的模型归属设计，不是 bug。

## 用户协作偏好（重要）
- **不要凭空臆想需求**：用户明确反对我自作主张加「兜底 / 共享 / 自动降级」等跨用户逻辑（例：图片模型缺失时让普通用户自动用 admin 的模型）。需求不清楚就先问，按用户原话实现，不替用户做产品决策。
- **数据隔离是硬约束**：每个用户只能用自己配置的资源（AI 提供商模型等），绝不能拿其他用户的配置来兜底或共享。无资源时如实为空并引导用户去对应配置页，而不是静默借用他人资源。
- 修改后端代码后，必须提醒用户**重启 FastAPI 服务并刷新浏览器（Ctrl+F5）**才能生效。

## Pydantic 响应 schema 与数据库可空列（重要编码规范 / 易错陷阱）
- **新增数据库列并在 Pydantic 响应 schema 暴露时，该字段必须声明为可空（`X | None = None`），绝不能声明为必填 `X`**。
- 根因：对已存在数据的表做 `ALTER TABLE ADD COLUMN` 时，**存量旧行该列是 NULL**（不会回填）。FastAPI 响应校验用 Pydantic 序列化 ORM 对象，若响应 schema 写 `product_image: str = ""`，遇到 NULL 会抛 `fastapi.exceptions.ResponseValidationError: Input should be a valid string (input: None)`（典型报错位置：`('response','plan_items',N,'product_image')`）。
- 正确写法（本项目统一用 PEP 604，无需 import Optional）：`product_image: str | None = None`。
- 注意 `from __future__ import annotations` 的影响：若响应 schema 用 `Optional[X]` 写法，**必须 `from typing import Optional`**，否则 Pydantic 在 `model_rebuild()` 时报 `name 'Optional' is not defined` / `TypeAdapter is not fully defined`。本项目所有 schema 文件都带该 future import，统一用 `X | None` 写法最稳妥。
- 排查此类报错的固定流程：① 在 Pydantic 校验报错里定位 `loc`（哪个字段、哪个元素）；② 确认该字段在响应 schema 是否必填；③ 确认 DB 存量行该列是否可能为 NULL（ALTER 加的列必为 NULL）；④ 把响应 schema 字段改为可空。

## 出网代理韧性层（app/http_client.py，2026-07-09 新增）
- **问题**：`docker-compose.yml` 注入 `HTTPS_PROXY=http://host.docker.internal:33210`。该代理是 WorkBuddy 沙箱代理，会随时拒绝连接（Errno 111）。`requests`/`httpx`/`openai` SDK 默认读该 env，代理挂掉 → 所有出网调用（`get_video_status` 轮询、`generate_image/video` 提交、CDN 下载、LLM 聊天）全部 `ProxyError` 硬失败，且视频轮询每 3s 刷屏。
- **修复**：`app/http_client.py` 两层防护：
  1. `ensure_proxy_strategy()` 模块导入时探测代理可达性；不可达则**清除本进程 `HTTPS_PROXY/HTTP_PROXY`**，让 requests/httpx/openai 自动走直连。幂等，2s 超时，失败不阻塞启动。
  2. `request_with_fallback(method,url,...)` / `download_bytes_with_fallback(url,...)` 每次出网调用带**直连兜底**（代理错误→重试直连），并有 30s "代理已宕"缓存，避免轮询反复打死代理。
- **接入点**：`media_retry.post_with_retry`、`media.py`/`media_new.py` 的 `get_video_status` 与 `_download_and_store`、`llm/openai_compat.py` 与 `llm/qwen.py` 的 `AsyncOpenAI(http_client=httpx.AsyncClient(proxy=None))`、`worker/media_worker.py` 的 `AsyncClient(proxy=None)`。
- **已验证**：本环境**宿主机可直接出网**（`curl https://apihub.agnes-ai.com` 返回 401，1.3s），代理 `33210` 当前拒绝连接 → 自动清 env 后直连成功。
- **运维开关**：设 `DISABLE_PROXY_AUTOFALLBACK=1` 可保留强制代理（仅在"只能走代理出网"的环境用）。若部署在仅代理可达的环境，需把 LLM/worker 的 `proxy=None` 去掉、并依赖代理可用。

## 电商套图 · 提示词生成引擎（2026-07-11 重构）
- **根因**：旧 `app/gallery_service._build_prompt` 是字符串拼接，导致「允许文字/禁止文字」自相矛盾、抽象风格词未量化、缺中东市场与平台适配、禁止项散落。
- **新架构**（数据驱动 + 分层组装 + 单一事实源）：新增 `app/gallery_prompt.py` 流水线 `Resolver → CopyPolicy → Assembler → Linter`；`app/gallery_config.py` 新增纯数据档案 `MARKET_PROFILES`（中东/北美/欧洲/日韩/东南亚/拉美/全球）、`PLATFORM_PROFILES`（淘宝/天猫/亚马逊/京东/抖音/拼多多/小红书）、`STYLE_VOCAB`（抽象风格词→量化视觉指令）、`COPY_ALLOWED_TYPES={"promo","usp"}`、`TYPE_LAYOUT`（19 类型各自版式/构图指令，V3 新增）。
- **人物判定规则（V3，重要）**：`_wants_human(type_id, personal)` 决定画面是否出现人物——`试穿/代言/买家秀` 强制人物；其余类型默认无人物，仅当填了人物信号字段（人种肤色/性别物种/年龄维度/身型身材/穿着风格/动作姿态/表情神态）才出现人物。**纯产品类型(白底图/细节图/多角度等)绝不被塞人物**。非人物场景用 `_to_product_composition()` 净化构图措辞。改 `STYLE_VOCAB`/`TYPE_LAYOUT` 等纯代码字段**无需动 `gallery_configs` 库缓存**（引擎直接 import 代码常量）。
- **主体一致性锚定（V4，重要）**：`_subject_fidelity_block(cfg)` 在 M1 标题行紧后、有参考图(`has_reference`)时注入最强约束——"参考图即本图要展示的商品本体，外观/版型/轮廓/颜色/材质/图案纹理/logo/结构比例逐处一致，不得改变/重新设计/替换；允许变化的仅限拍摄角度/视距/背景与场景/构图方式/光影氛围与道具搭配"。人物类型锚定"模特所展示商品须与参考图逐处一致，人物仅作载体"。M6 `has_reference` 追加禁止改变商品外观/版型/颜色/图案/logo、禁止用近似款替代。直接解决"生成图与产品图不一致"。纯代码改动，重启容器即生效。
- **商品颜色防重新染色（V4.5，重要）**：V4 后仍出现"形状一致但颜色被改"。根因是 M4 注入的中东 `palette` 自带"任选其一作为服装主色"诱导从句，覆盖了锚定的"颜色一致"。修复：`_subject_fidelity_block` 两分支追加总闸——"配色类描述仅作用于背景与场景氛围，商品颜色须以参考图为准"；M4 有参考图时改为「背景配色参考」并用 `palette.split("（任选其一作为服装主色")[0]` 摘掉该诱导从句。无参考图仍走原「配色参考」分支（此时配色用于定商品主色，正确）。

## 电商套图 · 环境双栈（2026-07-11 排查结论，重要）
- **现象**：用户报"生成的图片看不到了"。排查确认**非代码 bug**，是运行实例/数据不一致。
- **两套实例**：
  - Docker 正确栈（推荐）：`docker` 启动后 api/worker/web/mysql/minio 全 Up。`ai-agent-web` 映射宿主 **80**（`http://localhost/`），内部走容器网络连 `ai-agent-api`（连 MySQL `ai_agent`，`provider_models`=**5** 个图片模型，**能真实出图**）。生成图落挂载的 `uploads/gallery/results/`，回显经 `ai-agent-api` 的 `/api/gallery/files/`。
  - 本地误用栈：若另起本地 `uvicorn`（连 `.env` 的 `sqlite:///.../ai_agent.db`），它占宿主 **8010**；vite dev(`5173`) 的 proxy 指向 `127.0.0.1:8010` → 命中它。`ai_agent.db` 的 `provider_models`=**0**，所有生成走离线降级只留 `*.svg` 占位（能显示但非真图），看着像"图没了"。
- **判别**：`SELECT count(*) FROM provider_models` 在 `ai_agent.db`=0、`ai_agent`(mysql)=5；curl 文件端点返回的内容源自哪个库的 records 即命中哪个实例。
- **用户入口**：看/生成真实图 → 用 **http://localhost/**（docker web）。用 vite 开发前需先停掉占 8010 的本地 uvicorn，否则 docker api 的 8010 映射被它抢、vite 永远连无模型实例。
- **与重构关系**：`gallery_prompt.py` 提示词重构只动 prompt 文本，与图片看不到无关；图片存储/回显/前端渲染链路未改动。
- **CopyPolicy 唯一事实源**：只有它决定「允许文字/零文字」。海报(promo)/卖点图(usp)允许按类型放少量版面文案；其余类型（含 hero）一律零文字，卖点仅以视觉元素体现。彻底消灭历史矛盾。
- **市场/平台自动映射**：`target_market`/`ecommerce_platform` 选了即自动注入对应视觉档案（主体/肤色/色调/背景/规避项 + 构图/占比/画质/禁忌），前端无需改字段。
- **Linter 红线**：生成期检测「零文字约束 + 允许文字约束」并存即抛异常，并断言策略一致性（零文字类型必含绝对禁止文字约束；允许文字类型必含许可约束）。`tests/test_gallery_prompt.py` 6 项单测全覆盖（含 19 类全遍历无矛盾）。
- `gallery_service._build_prompt` 现为**薄委派**（`return gallery_prompt.build_prompt(project, item, model_name=...)`），签名不变，旧调用方（如 `run_gallery_task`）零改动。
- 验证：`py_compile` 通过；`python tests/test_gallery_prompt.py` 全绿；对比文档 `overview_prompt_refactor.md`。

## Agent 产物输出目录约定（重要，2026-07-11 起）
- **所有"我（Senior Developer）生成的文件"必须归入 `ai/agent-output/`**，按性质分子目录，禁止散落项目根目录：
  - `ai/agent-output/overviews/` → 任务总结/概览类 markdown（overview*.md）
  - `ai/agent-output/verify-shots/` → 验证/截图 PNG（含浏览器验证截图）
  - `ai/agent-output/logs/` → 构建/运行日志（web_build*.log 等）
  - 其它性质产物在 `ai/agent-output/` 下按需增设子目录。
- **不可移动/勿动**：`agent.db`/`.env` 引用的运行中 SQLite、`ai_agent.db` 等运行时数据；项目文档（PRD/FDD/README/AGENTS/TASKS/MEDIA_MINIO_FIX）；`designs/`、`疑问/`、根目录 Python 工具脚本（_build_*.py 等）。
- 若 overview 内引用图片，用相对路径 `../verify-shots/xxx.png`（overviews 与 verify-shots 同属 `ai/agent-output/` 下的兄弟目录）。
