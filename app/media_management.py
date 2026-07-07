"""
Media Management API — admin/owner view over the ``media_assets`` table.

All endpoints are authenticated. A non-admin user only sees/deletes their own
assets; an admin (``role == "admin"``) sees the whole library.

Every asset carries a ``proxy_url`` pointing at our internal
``/api/media/assets/by-key/{key}`` endpoint, so the frontend never needs to
know MinIO internals.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.deps import get_current_user
from app.models import MediaAsset, User
from app.storage import get_storage_backend

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/media/manage", tags=["media-management"])

PROXY_PREFIX = "/api/media/assets/by-key/"


class BulkDeleteRequest(BaseModel):
    ids: list[str]


def _is_admin(user: User) -> bool:
    return getattr(user, "role", None) == "admin"


def _asset_to_dict(asset: MediaAsset, username: Optional[str]) -> dict[str, Any]:
    return {
        "id": asset.id,
        "user_id": asset.user_id,
        "username": username,
        "media_type": asset.media_type,
        "object_key": asset.object_key,
        "proxy_url": PROXY_PREFIX + asset.object_key,
        "mime_type": asset.mime_type,
        "file_size": asset.file_size,
        "status": asset.status,
        "created_at": asset.created_at.isoformat() if asset.created_at else None,
        "message_id": asset.message_id,
    }


@router.get("/list")
def list_media(
    media_type: Optional[str] = Query(None, pattern="^(image|video)$"),
    q: Optional[str] = Query(None, description="search object_key / mime_type"),
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
    sort: str = Query("created_at", pattern="^(created_at|file_size)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Paginated list of hosted media assets.

    Filters: ``media_type`` (image|video), free-text ``q`` (key/mime), and
    ownership (admin sees all, others see own). Returns ``proxy_url`` for
    direct frontend rendering.
    """
    stmt = select(MediaAsset)
    if not _is_admin(current_user):
        stmt = stmt.where(MediaAsset.user_id == current_user.id)
    if media_type:
        stmt = stmt.where(MediaAsset.media_type == media_type)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            MediaAsset.object_key.like(like) | MediaAsset.mime_type.like(like)
        )

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    sort_col = getattr(MediaAsset, sort)
    stmt = stmt.order_by(sort_col.desc() if order == "desc" else sort_col.asc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)

    rows = db.scalars(stmt).all()

    # Resolve usernames in a single query.
    user_ids = {r.user_id for r in rows if r.user_id}
    usernames: dict[int, str] = {}
    if user_ids:
        users = db.scalars(select(User).where(User.id.in_(user_ids))).all()
        usernames = {u.id: u.username for u in users}

    items = [_asset_to_dict(r, usernames.get(r.user_id)) for r in rows]
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/stats")
def media_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Aggregate stats: total assets, total bytes, and a per-type breakdown."""
    stmt = select(MediaAsset)
    if not _is_admin(current_user):
        stmt = stmt.where(MediaAsset.user_id == current_user.id)
    rows = db.scalars(stmt).all()

    by_type: dict[str, dict[str, int]] = {
        "image": {"count": 0, "bytes": 0},
        "video": {"count": 0, "bytes": 0},
    }
    total = 0
    total_bytes = 0
    for r in rows:
        bucket = by_type.get(r.media_type, by_type["image"])
        bucket["count"] += 1
        bucket["bytes"] += r.file_size or 0
        total += 1
        total_bytes += r.file_size or 0

    return {
        "total": total,
        "total_bytes": total_bytes,
        "by_type": by_type,
    }


@router.delete("/{asset_id}")
def delete_media(
    asset_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a single asset: removes the object from MinIO and the DB row."""
    asset = db.get(MediaAsset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Media asset not found.")
    if not _is_admin(current_user) and asset.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not allowed to delete this asset.")

    # Best-effort removal from object storage.
    try:
        storage = get_storage_backend()
        if storage.exists(asset.object_key):
            storage.delete(asset.object_key)
    except Exception as exc:
        logger.warning("MinIO delete failed for %s: %s", asset.object_key, exc)

    db.delete(asset)
    db.commit()
    return {"ok": True, "id": asset_id}


@router.delete("/bulk")
def bulk_delete_media(
    payload: BulkDeleteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete multiple assets by id. Ownership is enforced per-row."""
    if not payload.ids:
        return {"ok": True, "deleted": 0}

    deleted = 0
    storage = get_storage_backend()
    for asset_id in payload.ids:
        asset = db.get(MediaAsset, asset_id)
        if not asset:
            continue
        if not _is_admin(current_user) and asset.user_id != current_user.id:
            continue
        try:
            if storage.exists(asset.object_key):
                storage.delete(asset.object_key)
        except Exception as exc:
            logger.warning("MinIO delete failed for %s: %s", asset.object_key, exc)
        db.delete(asset)
        deleted += 1

    db.commit()
    return {"ok": True, "deleted": deleted}
