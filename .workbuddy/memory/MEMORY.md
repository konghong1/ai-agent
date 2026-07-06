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
