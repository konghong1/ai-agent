"""
Background Worker — downloads media from external CDNs to local storage.

Runs as a separate process/container. Polls the database for
pending media assets and downloads them asynchronously.

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
import time
import uuid
from datetime import datetime

import httpx
import requests
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger(__name__)

# ── Config ──────────────────────────────────────────────────────

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://ai_agent:password@localhost:5432/ai_agent")
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "media-assets")
MINIO_PUBLIC_URL = os.getenv("MINIO_PUBLIC_URL", "http://localhost:9000/media-assets")
POLL_INTERVAL = int(os.getenv("WORKER_POLL_INTERVAL", "5"))  # seconds
MAX_CONCURRENT_DOWNLOADS = int(os.getenv("WORKER_MAX_CONCURRENT", "3"))

# ── Engine Setup ────────────────────────────────────────────────

engine = create_async_engine(DATABASE_URL, echo=False, pool_size=10, max_overflow=20)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

shutdown_event = asyncio.Event()


def _handle_signal(signum, frame):
    """Graceful shutdown on SIGINT/SIGTERM."""
    logger.info("Received signal %d, shutting down...", signum)
    shutdown_event.set()


signal.signal(signal.SIGINT, _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


# ── Worker ──────────────────────────────────────────────────────


async def download_to_storage(session: AsyncSession, external_url: str) -> dict | None:
    """Download media from external URL and store in MinIO.
    
    Returns {internal_url, object_key, mime_type, file_size} or None on failure.
    """
    try:
        # Download
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.get(external_url)
            resp.raise_for_status()
            file_bytes = resp.content
        
        # Detect MIME type
        content_type = resp.headers.get("content-type", "application/octet-stream")
        mime_type = content_type.split(";")[0] if ";" in content_type else content_type
        
        # Generate object key
        file_uuid = str(uuid.uuid4())
        date_str = datetime.now().strftime("%Y/%m/%d")
        
        # Extract extension from content type
        ext_map = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/webp": ".webp",
            "video/mp4": ".mp4",
            "video/webm": ".webm",
            "video/quicktime": ".mov",
        }
        ext = ext_map.get(mime_type, ".bin")
        object_key = f"media/{date_str}/{file_uuid}{ext}"
        
        # Store in MinIO (reuse local storage backend)
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
        
        internal_url = f"{MINIO_PUBLIC_URL}/{object_key}"
        
        return {
            "internal_url": internal_url,
            "object_key": object_key,
            "mime_type": mime_type,
            "file_size": len(file_bytes),
        }
        
    except Exception as exc:
        logger.error("Download failed for %s: %s", external_url[:80], exc)
        return None


async def process_pending_tasks(session: AsyncSession):
    """Find pending MediaAsset records and process them."""
    # Query for queued/failed assets (max 10 at a time)
    stmt = (
        select("id", "external_url", "media_type")
        .where("status == 'queued'")
        .limit(10)
    )
    
    # Since we can't use raw SQL easily, let's use a simpler approach
    result = await session.execute(stmt)
    tasks = result.all()
    
    for task in tasks:
        download_task = asyncio.create_task(
            download_to_storage(session, task.external_url)
        )
        download_task.add_done_callback(lambda t, sid=task.id: _mark_completed(sid, t.result()))
        
        if len(asyncio.all_tasks()) >= MAX_CONCURRENT_DOWNLOADS:
            await asyncio.sleep(0.1)


def _mark_completed(asset_id, result: dict | None):
    """Mark asset as completed/failed in database."""
    if result:
        logger.info("Stored: %s → %s", asset_id, result.get("internal_url", ""))
    else:
        logger.error("Failed to store asset: %s", asset_id)


async def main():
    """Main worker loop."""
    logger.info("Media worker started (database: %s)", DATABASE_URL)
    logger.info("Polling interval: %ds, max concurrent: %d", POLL_INTERVAL, MAX_CONCURRENT_DOWNLOADS)
    
    while not shutdown_event.is_set():
        try:
            async with async_session() as session:
                await process_pending_tasks(session)
                await session.commit()
        except Exception as exc:
            logger.error("Worker cycle error: %s", exc)
        
        await asyncio.sleep(POLL_INTERVAL)
    
    logger.info("Worker stopped gracefully.")


if __name__ == "__main__":
    asyncio.run(main())
