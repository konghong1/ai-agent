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
from typing import Any

import requests

from app.models import Provider

logger = logging.getLogger(__name__)


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
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Call the provider's image generation endpoint.

        Returns a dict with at least {"data": [{"url": "..."}]} on success,
        or {"error": "..."}  on failure.
        """
        url = _api_base(provider.base_url, "/v1/images/generations")

        payload: dict[str, Any] = {
            "model": model_name,
            "prompt": prompt,
            "size": size,
            "n": n,
        }

        # Agnes AI requires response_format inside extra_body
        if _is_agnes(provider.base_url):
            payload["extra_body"] = {"response_format": "url"}

        payload.update(kwargs)

        logger.info("Image generate: provider=%s model=%s url=%s", provider.name, model_name, url)

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
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Submit a video generation task (typically async).

        Returns the provider's raw response which usually contains
        {"id": "task_xxx", "status": "queued"} or similar.
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
        payload.update(kwargs)

        logger.info("Video generate: provider=%s model=%s url=%s", provider.name, model_name, url)

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


# ── Helpers ────────────────────────────────────────────────────────

def _is_agnes(base_url: str) -> bool:
    """Detect whether the provider is Agnes AI based on URL."""
    return "agnes" in base_url.lower()
