from __future__ import annotations

import logging
import traceback

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import router
from app.media_routes import router as media_router
from app.media_management import router as media_manage_router
from app.gallery_routes import router as gallery_router
from app.core.database import engine, init_db

# ── Suppress noisy loggers ───────────────────────────────────────
# watchfiles prints "N change(s) detected" at INFO level on every
# file write inside the watched dir (agent.db, uploads/, chroma_db/,
# vector_db/, …).  Bump it to WARNING so the console stays clean.
logging.getLogger("watchfiles.main").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

app = FastAPI(title="Configurable AI Agent Platform", version="0.2.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(media_router)
app.include_router(media_manage_router)
app.include_router(gallery_router)


@app.on_event("startup")
def startup() -> None:
    init_db()
    _ensure_gallery_showcase_payload_column()


def _ensure_gallery_showcase_payload_column() -> None:
    """幂等自愈：确保 gallery_showcases 含 payload 列（发布参数存储）。

    仅在列缺失时执行一次 ALTER（不写 server_default，兼容 MySQL 对
    TEXT/JSON 列不带默认值的约束）。列已存在则直接跳过。避免 Docker/MySQL
    环境重启因缺少该列而崩溃。
    """
    try:
        from sqlalchemy import inspect, text

        insp = inspect(engine)
        cols = {c["name"] for c in insp.get_columns("gallery_showcases")}
        if "payload" in cols:
            return
        col_type = "JSON NULL" if engine.dialect.name == "mysql" else "TEXT"
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE gallery_showcases ADD COLUMN payload {col_type}"))
        logger.info("startup: 已为 gallery_showcases 增加 payload 列（%s）", col_type)
    except Exception as e:
        logger.warning("startup: 确保 gallery_showcases.payload 列失败（可忽略，已在迁移脚本中处理）: %s", e)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch all unhandled exceptions and return a clean JSON 500 response
    instead of a bare traceback. This ensures the frontend always gets a
    parseable error message it can display in a popup."""
    logger.error("Unhandled exception on %s %s: %s\n%s", request.method, request.url.path, exc, traceback.format_exc())
    return JSONResponse(
        status_code=500,
        content={"detail": f"服务器内部错误: {type(exc).__name__}: {exc}"},
    )
