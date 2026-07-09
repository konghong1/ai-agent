"""
Media Service — Unified handler for image/video generation + storage.

Pipeline:
1. Generate via AI provider (Agnes AI, OpenAI, etc.)
2. Download media from provider's CDN URL
3. Store in MinIO/object storage
4. Register in MediaAsset table
5. Return internal URL for frontend display

This decouples the frontend from external CDN dependencies.
All media URLs are now internal (/api/media/assets/{id} or /media-assets/...).
"""
from __future__ import annotations

import mimetypes
import io
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import requests

from app.http_client import download_bytes_with_fallback, request_with_fallback
from app.media_retry import post_with_retry, clean_provider_error
from app.storage import StorageBackend, create_storage_backend, get_storage_backend

logger = logging.getLogger(__name__)


def _api_base(base_url: str, path: str) -> str:
    """Normalize base URL, stripping /v1 if present."""
    base = base_url.rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    return f"{base}{path}"


def _is_agnes(base_url: str) -> bool:
    """Detect whether the provider is Agnes AI based on URL."""
    return "agnes" in base_url.lower()


# ───────────────────────────────────────────────────────────────────
# Storage Backend Singleton (lazy-initialized from env)
# ───────────────────────────────────────────────────────────────────

# NOTE: get_storage_backend() now lives in app.storage (single source of
# truth, defaults to the MinIO backend). Imported above.

# ───────────────────────────────────────────────────────────────────
# Media Pipeline Service
# ───────────────────────────────────────────────────────────────────


class MediaService:
    """Handles the full media lifecycle: generate → download → store → serve."""

    # ── Image Generation ──────────────────────────────────────────

    @staticmethod
    def generate_image(
        provider_base_url: str,
        provider_api_key: str,
        model_name: str,
        prompt: str,
        size: str = "1024x768",
        n: int = 1,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Generate image via provider API and store in object storage.
        
        Returns {
            "status": "completed",
            "data": [{"url": "/media-assets/images/xxx.png", "mime_type": "image/png"}],
            "error": null
        }
        """
        url = _api_base(provider_base_url, "/v1/images/generations")

        payload: dict[str, Any] = {
            "model": model_name,
            "prompt": prompt,
            "size": size,
            "n": n,
        }

        if _is_agnes(provider_base_url):
            payload["extra_body"] = {"response_format": "url"}

        payload.update(kwargs)

        logger.info("Image generate: model=%s", model_name)

        outcome = post_with_retry(
            url,
            payload,
            headers={"Authorization": f"Bearer {provider_api_key}"},
            timeout=300,
            what="Image",
            logger=logger,
        )
        if not outcome["ok"]:
            error_detail = clean_provider_error(outcome["text"], outcome["exception"])
            logger.error(
                "Image generation failed after %d attempt(s): %s",
                outcome["attempts"], error_detail,
            )
            return {"error": error_detail, "data": [], "attempts": outcome["attempts"]}

        api_result = outcome["json"]

        # Download and store each image
        stored_images = []
        for img_data in api_result.get("data", []):
            image_url = img_data.get("url")
            if not image_url:
                continue
            
            stored = MediaService._download_and_store(
                url=image_url,
                media_type="image",
                content_type=img_data.get("b64_json"),
            )
            stored_images.append(stored)

        return {
            "status": "completed",
            "data": stored_images,
            "error": None,
        }

    # ── Video Generation (async) ───────────────────────────────────

    @staticmethod
    def generate_video(
        provider_base_url: str,
        provider_api_key: str,
        model_name: str,
        prompt: str,
        width: int = 1152,
        height: int = 768,
        num_frames: int = 121,
        frame_rate: int = 24,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Submit video generation task and return task_id for polling.
        
        Returns {
            "id": "task_xxx",
            "status": "queued",
            "video_id": "video_xxx"  # for later status polling
        }
        """
        url = _api_base(provider_base_url, "/v1/videos")

        payload: dict[str, Any] = {
            "model": model_name,
            "prompt": prompt,
            "height": height,
            "width": width,
            "num_frames": num_frames,
            "frame_rate": frame_rate,
        }
        payload.update(kwargs)

        logger.info("Video generate: model=%s", model_name)

        outcome = post_with_retry(
            url,
            payload,
            headers={"Authorization": f"Bearer {provider_api_key}"},
            timeout=120,
            what="Video",
            logger=logger,
        )
        if outcome["ok"]:
            return outcome["json"]
        error_detail = clean_provider_error(outcome["text"], outcome["exception"])
        logger.error(
            "Video generation failed after %d attempt(s): %s",
            outcome["attempts"], error_detail,
        )
        return {"error": error_detail, "attempts": outcome["attempts"]}

    # ── Video Status Polling + Auto-Store ────────────────────────────

    @staticmethod
    def get_video_status(
        provider_base_url: str,
        provider_api_key: str,
        task_id: str,
    ) -> dict[str, Any]:
        """Poll video status via provider API and auto-store if completed.
        
        Returns normalized status dict with video_url stored locally.
        """
        url = _api_base(provider_base_url, f"/v1/videos/{task_id}")

        logger.info("Video status check: task_id=%s", task_id)

        try:
            resp = request_with_fallback(
                "GET",
                url,
                headers={"Authorization": f"Bearer {provider_api_key}"},
                timeout=60,
            )
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()

            # Normalize status
            status = data.get("status", "processing")
            
            # If completed, download and store the video
            if status in ("completed", "succeeded"):
                video_url = data.get("remixed_from_video_id") or data.get("video_url") or ""
                if video_url and not video_url.startswith("/"):
                    stored = MediaService._download_and_store(
                        url=video_url,
                        media_type="video",
                    )
                    data["stored_video_url"] = stored["url"]
                    logger.info("Video stored: %s → %s", task_id, stored["url"])

            return data

        except requests.RequestException as exc:
            logger.error("Video status check failed: %s", exc)
            return {"error": str(exc)}

    # ── Internal Helpers ────────────────────────────────────────────

    @staticmethod
    def _download_and_store(
        url: str,
        media_type: str = "image",
        content_type: str | None = None,
    ) -> dict[str, Any]:
        """Download media from external URL and store in object storage.
        
        Args:
            url: External CDN URL (Agnes AI, etc.)
            media_type: "image" or "video"
            content_type: MIME type hint
        
        Returns:
            {
                "url": "/media-assets/images/xxx.png",
                "object_key": "images/2026/07/05/xxx.png",
                "mime_type": "image/png",
                "file_size": 123456
            }
        """
        # Download from external CDN — resilient to proxy failure.
        try:
            file_bytes, _detected_ct = download_bytes_with_fallback(url, timeout=120)
        except Exception as exc:
            logger.error("Failed to download %s: %s", url[:80], exc)
            return {"url": url, "object_key": "", "mime_type": "", "file_size": 0}

        # Detect MIME type
        mime_type = content_type or requests.utils.guess_type(url)[0] or "application/octet-stream"

        # Generate object key
        ext = mimetypes.guess_extension(mime_type.split("/")[1], strict=False) or ".bin"
        file_uuid = str(uuid.uuid4())
        object_key = f"{media_type}s/{datetime.now().strftime('%Y/%m/%d')}_{file_uuid}{ext}"

        # Store in object storage
        try:
            storage = get_storage_backend()
            info = storage.put(
                file_bytes=file_bytes,
                object_key=object_key,
                mime_type=mime_type,
            )
            internal_url = info.get("url", object_key)

            return {
                "url": internal_url,
                "object_key": object_key,
                "mime_type": mime_type,
                "file_size": len(file_bytes),
            }
        except Exception as exc:
            logger.error("Failed to store %s: %s", object_key, exc)
            return {"url": url, "object_key": "", "mime_type": "", "file_size": 0}

