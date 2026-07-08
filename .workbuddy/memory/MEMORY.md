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
- 代理端口 `33210` 取自主机 `HTTPS_PROXY`（WorkBuddy 沙箱代理），随会话/环境变化；若代理失效，设了 `HTTPS_PROXY` 的请求会直连失败（不会自动回退直连），属已知脆弱点。当前会话内代理稳定。
- **图片生成超时坑（已修）**：`MediaService.generate_image`（`app/media.py:109` 与 `app/media_new.py:102`）原 `timeout=120`。带参考图（img2img）的生成本身就慢（实测小图 30–48s，真实大图更久），偶发超过 120s → `Read timed out. (read timeout=120)`。已把图片生成超时提到 **300s**，视频提交 30→120、视频轮询 15→60、下载 60→120。
- 验证：完整链路（上传参考图 → `POST /api/chat` provider_id=2 `agnes-image-2.0-flash`）返回 200，约 52s（走代理）；裸 `MediaService.generate_image` 约 28–31s。图片模型归属 `provider_id=2`（user_id=2），admin(user_id=1) 走该路由会因 `provider.user_id==current_user.id` 不成立而落到聊天路径——这是正常的模型归属设计，不是 bug。
