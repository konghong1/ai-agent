from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
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
    _ensure_pillow()
    _start_gallery_worker()
    _start_memory_enricher()


def _start_gallery_worker() -> None:
    """幂等启动电商套图后台生成 worker（含孤儿恢复）。

    必须在 api 进程启动时主动拉起，而非仅依赖「用户创建新任务」时的懒启动——
    否则 api 重启后若短期内无人创建套图任务，worker 线程与孤儿恢复永不运行，
    历史 running 任务会永久卡在「创作中」。仅启线程 + 查本地 DB，无任何网络调用，
    符合 startup 不阻塞/不联网的硬约束。
    """
    try:
        from app import gallery_worker
        gallery_worker.start_worker()
    except Exception as e:
        logger.error("startup: 启动 gallery worker 失败: %s", e)


def _start_memory_enricher() -> None:
    """幂等启动记忆富集后台线程（P6）。

    仅启线程，在线程内才连 DB；startup 不联网、不阻塞。默认 enable_memory_enricher
    关；开启后周期性去重/矛盾检测/显著性衰减/会话摘要 Promotion，失败不影响主服务。
    """
    try:
        from app.memory import MemoryEnricher
        from app.settings import get_settings

        if not getattr(get_settings(), "enable_memory_enricher", False):
            logger.info("startup: MemoryEnricher 未启用（enable_memory_enricher=false）")
            return
        interval = getattr(get_settings(), "memory_enricher_interval_seconds", 3600)
        MemoryEnricher.start(interval_seconds=interval)
        logger.info("startup: MemoryEnricher 已启动（间隔 %ss）", interval)
    except Exception as e:
        logger.error("startup: 启动 MemoryEnricher 失败: %s", e)


def _ensure_pillow() -> None:
    """幂等自愈：确保 Pillow 可用（规格参数图叠加尺码表/标注需要）。

    镜像若基于「把 Pillow 加入 requirements 之前」的旧构建，运行时缺 PIL 会
    导致 spec 类型整单失败。此处启动时探测，缺失则在【后台线程】自动安装，
    **绝不阻塞 uvicorn 启动**——即使 PyPI 不可达或安装缓慢，API 也照常起来，
    仅 spec 类生成短暂不可用，直到安装完成。已安装则直接跳过（不触碰网络）。
    """
    try:
        import PIL  # noqa: F401
        return
    except ImportError:
        pass
    try:
        logger.warning("startup: 未检测到 Pillow，后台自动安装（规格参数图叠加需要）")
        t = threading.Thread(
            target=_install_pillow_bg,
            name="pillow-selfheal",
            daemon=True,
        )
        t.start()
    except Exception as e:
        logger.error("startup: 启动 Pillow 自愈线程失败: %s", e)


def _install_pillow_bg() -> None:
    # 容器内默认 http_proxy 指向 127.0.0.1:33210（容器内不可达），会令 pip 永远
    # 连不上 PyPI。剥离代理相关环境变量，走直连安装，才能真装上。
    env = {k: v for k, v in os.environ.items() if not k.lower().endswith("_proxy")}
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--no-cache-dir", "Pillow>=10.0.0"],
            check=True,
            capture_output=True,
            text=True,
            timeout=300,
            env=env,
        )
        logger.info("startup: Pillow 已自动安装（规格参数图可用）")
    except Exception as e:
        logger.error("startup: 自动安装 Pillow 失败（规格参数图将不可用）: %s", e)


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
