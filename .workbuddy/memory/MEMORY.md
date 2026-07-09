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

## 出网代理韧性层（app/http_client.py，2026-07-09 新增）
- **问题**：`docker-compose.yml` 注入 `HTTPS_PROXY=http://host.docker.internal:33210`。该代理是 WorkBuddy 沙箱代理，会随时拒绝连接（Errno 111）。`requests`/`httpx`/`openai` SDK 默认读该 env，代理挂掉 → 所有出网调用（`get_video_status` 轮询、`generate_image/video` 提交、CDN 下载、LLM 聊天）全部 `ProxyError` 硬失败，且视频轮询每 3s 刷屏。
- **修复**：`app/http_client.py` 两层防护：
  1. `ensure_proxy_strategy()` 模块导入时探测代理可达性；不可达则**清除本进程 `HTTPS_PROXY/HTTP_PROXY`**，让 requests/httpx/openai 自动走直连。幂等，2s 超时，失败不阻塞启动。
  2. `request_with_fallback(method,url,...)` / `download_bytes_with_fallback(url,...)` 每次出网调用带**直连兜底**（代理错误→重试直连），并有 30s "代理已宕"缓存，避免轮询反复打死代理。
- **接入点**：`media_retry.post_with_retry`、`media.py`/`media_new.py` 的 `get_video_status` 与 `_download_and_store`、`llm/openai_compat.py` 与 `llm/qwen.py` 的 `AsyncOpenAI(http_client=httpx.AsyncClient(proxy=None))`、`worker/media_worker.py` 的 `AsyncClient(proxy=None)`。
- **已验证**：本环境**宿主机可直接出网**（`curl https://apihub.agnes-ai.com` 返回 401，1.3s），代理 `33210` 当前拒绝连接 → 自动清 env 后直连成功。
- **运维开关**：设 `DISABLE_PROXY_AUTOFALLBACK=1` 可保留强制代理（仅在"只能走代理出网"的环境用）。若部署在仅代理可达的环境，需把 LLM/worker 的 `proxy=None` 去掉、并依赖代理可用。
