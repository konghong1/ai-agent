"""
Media Generation Service — handles image and video generation
for AI providers that support non-chat model types.

Supported endpoints (per OpenAI-compatible conventions):
- Image: POST {base_url}/images/generations
- Video: POST {base_url}/videos

Note: base_url may or may not include /v1 suffix — we normalise it.
"""

from __future__ import annotations

import logging
import mimetypes
import uuid
from datetime import datetime
from typing import Any

import base64
import requests

from app.models import Provider

logger = logging.getLogger(__name__)

# Cache so a completed video is uploaded to object storage only once,
# even if the status endpoint is polled multiple times.
_video_store_cache: dict[str, str] = {}


def _api_base(base_url: str, path: str) -> str:
    """Build a full API URL, stripping any trailing /v1 from base_url first."""
    base = base_url.rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    return f"{base}{path}"


class MediaService:
    """Unified media (image + video) generation service.

    Routes to the correct provider endpoint based on media type.
    Each provider may have slight differences in request/response format;
    this service normalises them.
    """

    # ── Image Generation ──────────────────────────────────────────

    @staticmethod
    def generate_image(
        provider: Provider,
        model_name: str,
        prompt: str,
        size: str = "1024x768",
        n: int = 1,
        reference_images: list[str] | None = None,
        tags: list[str] | None = None,
        seed: int | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Call the provider's image generation endpoint.

        Returns a dict with at least {"data": [{"url": "..."}]} on success,
        or {"error": "..."}  on failure.

        When ``reference_images`` are supplied the call becomes image-to-image
        (图生图): the references are passed as ``extra_body.image`` (and, for
        Agnes Image 2.0-Flash, tagged with ``["img2img"]``).
        """
        url = _api_base(provider.base_url, "/v1/images/generations")

        payload: dict[str, Any] = {
            "model": model_name,
            "prompt": prompt,
            "size": size,
            "n": n,
        }
        if seed is not None:
            payload["seed"] = seed
        payload.update(kwargs)

        extra_body: dict[str, Any] = {}
        if _is_agnes(provider.base_url):
            extra_body["response_format"] = "url"

        refs = _normalize_reference_images(reference_images)
        if refs:
            extra_body["image"] = refs
            tag_list = list(tags or [])
            if "img2img" not in tag_list and "agnes-image-2.0" in (model_name or "").lower():
                tag_list.append("img2img")
            if tag_list:
                extra_body["tags"] = tag_list
            # Non-Agnes OpenAI-compatible providers expect the image at the
            # top level rather than inside extra_body.
            if not _is_agnes(provider.base_url):
                payload["image"] = refs[0] if len(refs) == 1 else refs

        if extra_body:
            payload["extra_body"] = extra_body

        logger.info("Image generate: provider=%s model=%s url=%s refs=%d", provider.name, model_name, url, len(refs))

        try:
            resp = requests.post(
                url,
                json=payload,
                headers={"Authorization": f"Bearer {provider.api_key}"},
                timeout=120,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            logger.error("Image generation failed: %s", exc)
            error_detail = str(exc)
            if hasattr(exc, "response") and exc.response is not None:
                try:
                    error_detail = exc.response.text[:500]
                except Exception:
                    pass
            return {"error": error_detail, "data": []}

    # ── Video Generation (async) ───────────────────────────────────

    @staticmethod
    def generate_video(
        provider: Provider,
        model_name: str,
        prompt: str,
        width: int = 1152,
        height: int = 768,
        num_frames: int = 121,
        frame_rate: int = 24,
        reference_images: list[str] | None = None,
        mode: str | None = None,
        negative_prompt: str | None = None,
        seed: int | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Submit a video generation task (typically async).

        Returns the provider's raw response which usually contains
        {"id": "task_xxx", "status": "queued"} or similar.

        When ``reference_images`` are supplied the call becomes
        image-to-video (图生视频): the first reference is sent as the
        ``image`` field; multiple references are sent for keyframe mode.
        """
        url = _api_base(provider.base_url, "/v1/videos")

        payload: dict[str, Any] = {
            "model": model_name,
            "prompt": prompt,
            "height": height,
            "width": width,
            "num_frames": num_frames,
            "frame_rate": frame_rate,
        }
        if mode:
            payload["mode"] = mode
        if negative_prompt:
            payload["negative_prompt"] = negative_prompt
        if seed is not None:
            payload["seed"] = seed
        payload.update(kwargs)

        refs = _normalize_reference_images(reference_images)
        if refs:
            if _is_agnes(provider.base_url):
                # Agnes video i2v mirrors the image img2img convention:
                # the reference image(s) go inside extra_body.image as a LIST
                # (a top-level `image` string is rejected with 400).
                payload.setdefault("extra_body", {})
                payload["extra_body"]["image"] = refs
                if len(refs) > 1 or mode == "keyframes":
                    payload["extra_body"]["mode"] = "keyframes"
            else:
                # Non-Agnes OpenAI-compatible providers: top-level image field.
                payload["image"] = refs[0] if len(refs) == 1 else refs
                if len(refs) > 1 or mode == "keyframes":
                    payload.setdefault("extra_body", {})
                    payload["extra_body"]["image"] = refs
                    payload["extra_body"]["mode"] = "keyframes"

        logger.info("Video generate: provider=%s model=%s url=%s refs=%d", provider.name, model_name, url, len(refs))

        try:
            resp = requests.post(
                url,
                json=payload,
                headers={"Authorization": f"Bearer {provider.api_key}"},
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            logger.error("Video generation failed: %s", exc)
            error_detail = str(exc)
            if hasattr(exc, "response") and exc.response is not None:
                try:
                    error_detail = exc.response.text[:500]
                except Exception:
                    pass
            return {"error": error_detail}

    # ── Video Status Polling ───────────────────────────────────────

    @staticmethod
    def get_video_status(
        provider: Provider,
        task_id: str,
        video_id: str | None = None,
    ) -> dict[str, Any]:
        """Poll the status of a video generation task using the standard
        OpenAI-compatible API endpoint.

        Always uses ``GET {base_url}/v1/videos/{task_id}`` regardless of
        whether a ``video_id`` is provided, because the legacy
        ``/agnesapi`` endpoint has been deprecated by Agnes AI and
        returns 404 for encoded video IDs.

        Normalises provider-specific field names (e.g. Agnes's
        ``remixed_from_video_id``) into ``video_url``.
        """
        url = _api_base(provider.base_url, f"/v1/videos/{task_id}")

        logger.info("Video status check: provider=%s task_id=%s", provider.name, task_id)

        try:
            resp = requests.get(
                url,
                headers={"Authorization": f"Bearer {provider.api_key}"},
                timeout=15,
            )
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()

            # ── Normalise response ─────────────────────────────────
            # Agnes AI returns the video URL in "remixed_from_video_id"
            # or "video_url"; prefer the URL-looking field.
            if "video_url" not in data:
                for candidate in ("remixed_from_video_id", "output", "url"):
                    if data.get(candidate):
                        data["video_url"] = data[candidate]
                        break

            # ── Persist completed video to object storage (MinIO) ──
            # The provider only returns a temporary/external CDN URL.
            # We download it once and re-host it in our own bucket so the
            # asset survives and is served through our authenticated proxy.
            status = (data.get("status") or data.get("state") or "").lower().strip()
            if status in ("completed", "succeeded", "done", "success", "finished", "ready"):
                raw_url = (
                    data.get("video_url")
                    or data.get("output")
                    or data.get("url")
                    or ""
                )
                # Only download real http(s) URLs (skip bare video IDs).
                if raw_url.startswith("http") and task_id not in _video_store_cache:
                    stored = MediaService._download_and_store(
                        raw_url, "video", user_id=getattr(provider, "user_id", None)
                    )
                    if stored.get("object_key"):
                        _video_store_cache[task_id] = stored["object_key"]
                        # Serve through our backend proxy (works whether or
                        # not MinIO is publicly readable, and is browser-safe).
                        data["stored_video_url"] = stored["url"]
                        data["object_key"] = stored["object_key"]
                        data["video_url"] = stored["url"]
                        logger.info(
                            "Video uploaded to object storage: task=%s key=%s",
                            task_id, stored["object_key"],
                        )
                elif task_id in _video_store_cache:
                    # Already uploaded in a previous poll — reuse it.
                    key = _video_store_cache[task_id]
                    data["object_key"] = key
                    data["video_url"] = f"/api/media/assets/by-key/{key}"

            return data
        except requests.RequestException as exc:
            logger.error("Video status check failed: %s", exc)
            error_detail = str(exc)
            if hasattr(exc, "response") and exc.response is not None:
                try:
                    error_detail = exc.response.text[:500]
                except Exception:
                    pass
            return {"error": error_detail}

    # ── Internal Helpers ──────────────────────────────────────────

    @staticmethod
    def _download_and_store(
        url: str,
        media_type: str = "video",
        content_type: str | None = None,
        user_id: int | str | None = None,
    ) -> dict[str, Any]:
        """Download media from an external URL and store it in object
        storage (MinIO), returning an internal proxy URL.

        Object layout in the bucket::

            {media_type}s/{user_id}/{yyyy}/{mm}/{dd}/{uuid}.{ext}

        e.g. ``videos/7/2026/07/07/9f3c…mp4``. Returns a dict with at least
        ``url`` (a relative ``/api/media/assets/by-key/<key>`` path served by
        the backend) and ``object_key`` so the asset can be streamed back
        through our authenticated proxy regardless of MinIO's public-read
        setting.
        """
        # Download from the external CDN (backend reaches it, browser may not).
        try:
            import httpx

            resp = httpx.get(url, timeout=60, follow_redirects=True)
            resp.raise_for_status()
            file_bytes = resp.content
            detected_ct = resp.headers.get("content-type")
        except Exception as exc:  # pragma: no cover - network best-effort
            logger.warning("Failed to download %s: %s", url[:80], exc)
            try:
                resp = requests.get(url, timeout=60)
                resp.raise_for_status()
                file_bytes = resp.content
                detected_ct = resp.headers.get("content-type")
            except Exception as exc2:
                logger.error("Fallback download also failed: %s", exc2)
                return {"url": url, "object_key": "", "mime_type": "", "file_size": 0}

        # Derive a reliable MIME type (ignore non-MIME hints such as b64_json).
        mime_type = (
            (content_type if content_type and "/" in content_type else None)
            or detected_ct
            or mimetypes.guess_type(url)[0]
            or "application/octet-stream"
        )
        ext = mimetypes.guess_extension(mime_type, strict=False) or (
            ".mp4" if media_type == "video" else ".bin"
        )

        owner = str(user_id) if user_id else "anonymous"
        date_dir = datetime.now().strftime("%Y/%m/%d")
        object_key = f"{media_type}s/{owner}/{date_dir}/{uuid.uuid4().hex}{ext}"

        try:
            from app.storage import get_storage_backend

            storage = get_storage_backend()
            info = storage.put(
                file_bytes=file_bytes,
                object_key=object_key,
                mime_type=mime_type,
            )
            proxy_url = f"/api/media/assets/by-key/{object_key}"
            logger.info("Stored %s (%d bytes) -> %s", media_type, len(file_bytes), object_key)
            return {
                "url": proxy_url,
                "object_key": object_key,
                "mime_type": mime_type,
                "file_size": len(file_bytes),
                "storage_url": info.get("url", object_key),
            }
        except Exception as exc:
            logger.error("Failed to store %s in object storage: %s", object_key, exc)
            return {"url": url, "object_key": "", "mime_type": mime_type, "file_size": len(file_bytes)}


# ── Helpers ────────────────────────────────────────────────────────

def _is_agnes(base_url: str) -> bool:
    """Detect whether the provider is Agnes AI based on URL."""
    return "agnes" in base_url.lower()


def _normalize_reference_images(refs: list[str] | None, storage=None) -> list[str]:
    """Normalise reference-image references into provider-friendly forms.

    - ``data:`` URL  -> kept as-is (most reliable for img2img/i2v).
    - Internal by-key proxy URL (``/api/media/assets/by-key/<key>``) ->
      downloaded via object storage and inlined as a base64 data URL,
      because the provider cannot reach our private proxy.
    - External ``http(s)`` URL -> kept as-is (provider fetches directly).

    Returns a list of strings; capped at 8 references.
    """
    if not refs:
        return []
    out: list[str] = []
    for ref in refs[:8]:
        if not isinstance(ref, str):
            continue
        if ref.startswith("data:"):
            out.append(ref)
            continue
        if "/api/media/assets/by-key/" in ref:
            try:
                key = ref.split("/api/media/assets/by-key/", 1)[1].split("?")[0]
                if storage is None:
                    from app.storage import get_storage_backend
                    storage = get_storage_backend()
                raw = storage.get(key)
                if raw:
                    mt = mimetypes.guess_type(key)[0] or "image/png"
                    out.append(f"data:{mt};base64,{base64.b64encode(raw).decode()}")
                    continue
            except Exception as exc:
                logger.warning("Failed to inline by-key reference %s: %s", ref, exc)
        out.append(ref)
    return out
