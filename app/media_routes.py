"""
Public Media Routes — no authentication required.

These endpoints serve media assets directly from MinIO/object storage.
Since all media is now stored internally, no external CDN proxying is needed.

Endpoints:
- GET /api/media/assets/{asset_id} — Get media by database ID
- GET /api/media/assets/by-key/{object_key} — Get media by storage key
- GET /media-assets/{path:path} — Direct MinIO proxy (no auth)
"""
from __future__ import annotations

import logging
import mimetypes
import urllib.parse
from pathlib import PurePosixPath
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import MediaAsset
from app.storage import create_storage_backend, get_storage_backend

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/media", tags=["media"])


# ───────────────────────────────────────────────────────────────
# Public media serving (no auth required)
# ───────────────────────────────────────────────────────────────


@router.get("/assets/{asset_id}")
def get_media_asset(
    asset_id: str,
    db: Session = Depends(get_db),
):
    """Serve a media asset by its database ID.
    
    This is the primary way for the frontend to access media —
    it resolves the asset from the database and streams it from MinIO.
    """
    stmt = select(MediaAsset).where(MediaAsset.id == asset_id)
    asset = db.scalar(stmt)
    
    if not asset:
        raise HTTPException(status_code=404, detail="Media asset not found")
    
    if asset.status != "completed":
        raise HTTPException(status_code=403, detail="Media asset not ready")
    
    # Stream from storage backend
    storage = get_storage_backend()
    
    # Get the file content
    file_bytes = storage.get(asset.object_key)
    if not file_bytes:
        # Fallback: try to get from internal URL
        if asset.internal_url:
            raise HTTPException(status_code=503, detail="Media storage unavailable")
        raise HTTPException(status_code=404, detail="Media file not found in storage")
    
    # Stream response with proper headers
    return Response(
        content=file_bytes,
        media_type=asset.mime_type or "application/octet-stream",
        headers={
            "Cache-Control": "public, max-age=86400",
            "Accept-Ranges": "bytes",
            "Content-Length": str(len(file_bytes)),
        },
    )


@router.get("/assets/by-key/{object_key:path}")
def get_media_by_key(
    object_key: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """Serve a media asset directly by its storage object key.

    Useful for direct access without database lookup. Returns a proper
    content-type (derived from the object key) and supports HTTP Range
    requests so videos can be seeked in the browser.
    """
    # URL decode the key
    object_key = urllib.parse.unquote(object_key)

    # Check if exists in storage
    storage = get_storage_backend()
    if not storage.exists(object_key):
        raise HTTPException(status_code=404, detail="Media not found")

    # Stream the file
    file_bytes = storage.get(object_key)
    if not file_bytes:
        raise HTTPException(status_code=503, detail="Media unavailable")

    # Derive a sensible content-type from the key extension.
    content_type, _ = mimetypes.guess_type(object_key)
    if not content_type:
        content_type = "application/octet-stream"

    headers = {
        "Cache-Control": "public, max-age=86400",
        "Accept-Ranges": "bytes",
        "Content-Type": content_type,
    }

    # Support Range requests for video seeking.
    range_header = request.headers.get("range")
    if range_header:
        try:
            unit, _, rng = range_header.strip().partition("=")
            if unit.lower() == "bytes" and rng:
                start_str, _, end_str = rng.partition("-")
                start = int(start_str) if start_str else 0
                end = int(end_str) if end_str else len(file_bytes) - 1
                end = min(end, len(file_bytes) - 1)
                if start <= end < len(file_bytes):
                    chunk = file_bytes[start : end + 1]
                    headers["Content-Range"] = f"bytes {start}-{end}/{len(file_bytes)}"
                    headers["Content-Length"] = str(len(chunk))
                    return Response(
                        content=chunk,
                        status_code=206,
                        media_type=content_type,
                        headers=headers,
                    )
        except (ValueError, IndexError):
            # Malformed Range — fall through and serve the whole file.
            pass

    headers["Content-Length"] = str(len(file_bytes))
    return Response(
        content=file_bytes,
        media_type=content_type,
        headers=headers,
    )


# ───────────────────────────────────────────────────────────────
# Legacy proxy (deprecated, kept for backward compatibility)
# ───────────────────────────────────────────────────────────────

@router.get("/legacy/proxy")
def proxy_external_media(
    url: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """LEGACY: Proxy external CDN media through backend.
    
    DEPRECATED: Use /api/media/assets/{id} instead.
    Kept for backward compatibility with existing media URLs.
    """
    from urllib.parse import unquote, urlparse
    
    target_url = unquote(url)
    parsed = urlparse(target_url)
    
    # Allow known external domains (safety check)
    ALLOWED_DOMAINS = {
        "platform-outputs.agnes-ai.space",
    }
    
    if parsed.hostname not in ALLOWED_DOMAINS:
        raise HTTPException(status_code=403, detail="Domain not allowed")
    
    # Forward Range header for video seeking
    range_header = request.headers.get("range")
    headers = {}
    if range_header:
        headers["Range"] = range_header
    
    try:
        import requests as _requests
        resp = _requests.get(target_url, stream=True, timeout=30, headers=headers)
        resp.raise_for_status()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch media: {exc}")
    
    content_type = resp.headers.get("content-type", "application/octet-stream")
    
    def stream_content():
        try:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    yield chunk
        finally:
            resp.close()
    
    return StreamingResponse(
        stream_content(),
        media_type=content_type,
        headers={
            "Cache-Control": "public, max-age=3600",
            "Accept-Ranges": "bytes",
        },
    )
