"""
Background Worker — downloads media from external CDNs to local storage.

Uses synchronous SQLAlchemy engine because MySQL async drivers (aiomysql/asyncmy)
are not installed. Polls the database for pending media assets and downloads them.

Usage:
    python -m app.worker.media_worker

Or via Docker:
    docker compose up worker
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
import uuid
from datetime import datetime

import httpx
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.db_url import normalize_db_url

logger = logging.getLogger(__name__)


def _parse_db_type(url: str) -> str:
    """Extract database type from URL."""
    if "mysql" in url:
        return "MySQL"
    elif "postgresql" in url:
        return "PostgreSQL"
    elif "sqlite" in url:
        return "SQLite"
    return "Unknown"


# ── Config ──────────────────────────────────────────────────────

DATABASE_URL = normalize_db_url()
if not DATABASE_URL:
    logger.error("DATABASE_URL environment variable is not set!")
    sys.exit(1)

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "ai-agent-minio")
MINIO_PUBLIC_URL = os.getenv("MINIO_PUBLIC_URL", "http://localhost:9000/ai-agent-minio")
POLL_INTERVAL = int(os.getenv("WORKER_POLL_INTERVAL", "5"))  # seconds

# ── Sync Engine Setup ──────────────────────────────────────────

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
logger.info("Worker connected to database: %s", _parse_db_type(DATABASE_URL))

shutdown_event = asyncio.Event()


def _handle_signal(signum, frame):
    """Graceful shutdown on SIGINT/SIGTERM."""
    logger.info("Received signal %d, shutting down...", signum)
    shutdown_event.set()


signal.signal(signal.SIGINT, _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


# ── Worker ──────────────────────────────────────────────────────


def download_to_storage(internal_url: str) -> dict | None:
    """Download media from internal URL and store in MinIO.

    Returns {internal_url, object_key, mime_type, file_size} or None on failure.
    Runs in a thread to avoid blocking the async event loop.
    """
    try:
        async def _download():
            # proxy=None: bypass the (optional, sometimes unreachable) egress
            # proxy and use direct egress, which works in this deployment.
            async with httpx.AsyncClient(timeout=60, proxy=None) as client:
                resp = await client.get(internal_url)
                resp.raise_for_status()
                return resp.content, resp.headers.get("content-type", "application/octet-stream")

        file_bytes, content_type = asyncio.run(_download())
        mime_type = content_type.split(";")[0] if ";" in content_type else content_type

        file_uuid = str(uuid.uuid4())
        date_str = datetime.now().strftime("%Y/%m/%d")
        ext_map = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/webp": ".webp",
            "video/mp4": ".mp4",
            "video/webm": ".webm",
            "video/quicktime": ".mov",
        }
        ext = ext_map.get(mime_type, ".bin")
        object_key = f"videos/{date_str}/{file_uuid}{ext}"

        from app.storage import create_storage_backend
        storage = create_storage_backend(
            backend_type="minio",
            endpoint=MINIO_ENDPOINT,
            access_key=MINIO_ACCESS_KEY,
            secret_key=MINIO_SECRET_KEY,
            bucket=MINIO_BUCKET,
            public_url=MINIO_PUBLIC_URL,
            use_ssl=False,
        )

        storage.put(
            file_bytes=file_bytes,
            object_key=object_key,
            mime_type=mime_type,
        )

        result_internal_url = f"{MINIO_PUBLIC_URL}/{object_key}"

        return {
            "internal_url": result_internal_url,
            "object_key": object_key,
            "mime_type": mime_type,
            "file_size": len(file_bytes),
        }

    except Exception as exc:
        logger.error("Download failed for %s: %s", internal_url[:80], exc)
        return None


def update_task_status(session: Session, task_id, status: str, error_msg: str | None = None):
    """Update MediaAsset status in database using raw SQL."""
    try:
        if status == "completed":
            session.execute(
                text("UPDATE media_assets SET status = 'completed', updated_at = CURRENT_TIMESTAMP WHERE id = :id"),
                {"id": task_id}
            )
        else:
            session.execute(
                text("UPDATE media_assets SET status = 'failed', error_message = :msg, updated_at = CURRENT_TIMESTAMP WHERE id = :id"),
                {"msg": error_msg, "id": task_id}
            )
        session.commit()
    except Exception as e:
        logger.error("Failed to update task %s status: %s", task_id, e)
        session.rollback()


def process_pending_tasks():
    """Find pending MediaAsset records and process them synchronously."""
    with engine.connect() as conn:
        # Query for queued assets (use raw SQL since MediaAsset model needs async)
        result = conn.execute(text(
            "SELECT id, internal_url FROM media_assets WHERE status = 'queued' LIMIT 10"
        ))
        rows = result.fetchall()

    if not rows:
        return

    session = Session(engine)
    try:
        for row in rows:
            task_id = row[0]
            internal_url = row[1]

            if not internal_url:
                continue

            logger.info("Processing task %s: %s", task_id, internal_url[:80])
            result = download_to_storage(internal_url)

            if result:
                update_task_status(session, task_id, "completed")
            else:
                update_task_status(session, task_id, "failed", "Download/storage failed")

            session.flush()
    finally:
        session.close()


async def main():
    """Main worker loop."""
    logger.info("Media worker started (database: %s)", _parse_db_type(DATABASE_URL))
    logger.info("Polling interval: %ds", POLL_INTERVAL)

    while not shutdown_event.is_set():
        try:
            await asyncio.to_thread(process_pending_tasks)
        except Exception as exc:
            logger.error("Worker cycle error: %s", exc)

        await asyncio.sleep(POLL_INTERVAL)

    logger.info("Worker stopped gracefully.")


if __name__ == "__main__":
    asyncio.run(main())
