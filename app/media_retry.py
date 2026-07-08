"""Shared retry/backoff for provider media calls (image/video).

AgnesAI's gateway occasionally returns transient upstream errors such as
``code: do_request_failed`` ("upstream error: do request failed"), 5xx
responses, or connection resets. These are almost always intermittent — a
short exponential-backoff retry recovers the request without the user ever
seeing a hard failure.

Permanent client errors (e.g. 400 ``UnsupportedParamsError``) are detected
and NOT retried, so we don't waste latency on requests that will never
succeed.
"""
from __future__ import annotations

import json
import time
from typing import Any

import requests

# Transient conditions we are willing to retry.
_MAX_RETRIES = 3
_BACKOFF_SECONDS = (4, 8, 16)


def is_transient_response(resp: "requests.Response") -> bool:
    """Decide whether an HTTP error response is worth retrying.

    Order matters: a permanent model/config error may arrive with a 5xx
    status (e.g. AgnesAI returns 503 ``model_not_found``), so we parse the
    error body FIRST and reject known-permanent codes before the generic
    ``>= 500 -> retry`` rule would treat them as transient.
    """
    code = ""
    msg = ""
    try:
        body = resp.json()
        err = body.get("error") if isinstance(body, dict) else None
        if isinstance(err, dict):
            code = str(err.get("code") or "").lower()
            msg = str(err.get("message") or "").lower()
    except Exception:
        pass
    # Permanent model/config errors: retrying will never succeed, so stop
    # immediately and surface a clean error instead of burning 3 backoffs.
    if "model_not_found" in code or "model_not_found" in msg or "no available channel" in msg:
        return False
    if resp.status_code >= 500:
        return True
    if resp.status_code == 429:  # rate limited -> back off and retry
        return True
    # AgnesAI upstream backend failures
    if "do_request_failed" in code:
        return True
    if "upstream" in code or "upstream" in msg or "do request failed" in msg:
        return True
    return False


def clean_provider_error(text: str | None, exc_str: str | None) -> str:
    """Turn a raw provider error body into a display-friendly message.

    Keeps the upstream ``message`` (and any request id inside it) so the user
    can report it, but drops the noisy JSON envelope.
    """
    if text:
        try:
            body = json.loads(text)
            err = body.get("error") if isinstance(body, dict) else None
            if isinstance(err, dict) and err.get("message"):
                return str(err["message"])
        except Exception:
            pass
        if text.strip():
            return text.strip()
    return exc_str or "unknown upstream error"


def post_with_retry(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    timeout: float,
    *,
    what: str = "media",
    logger: Any = None,
) -> dict[str, Any]:
    """POST JSON with exponential backoff for transient upstream failures.

    Returns a dict with one of:
      - ``{"ok": True, "json": <parsed response>, "attempts": <int>}`` on success
      - ``{"ok": False, "status": <int|None>, "text": <str>,
         "exception": <str|None>, "attempts": <int>}`` on failure
    """
    log = logger or __import__("logging").getLogger(__name__)
    last_exc: Exception | None = None
    last_status: int | None = None
    last_text = ""
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
            if resp.status_code < 400:
                return {"ok": True, "json": resp.json(), "attempts": attempt}
            last_status = resp.status_code
            last_text = resp.text[:500]
            if not is_transient_response(resp):
                # Permanent (e.g. 400 UnsupportedParamsError): stop early.
                log.warning(
                    "%s gen permanent error (HTTP %s): %s",
                    what, resp.status_code, last_text[:200],
                )
                return {
                    "ok": False, "status": last_status, "text": last_text,
                    "exception": None, "attempts": attempt,
                }
            log.warning(
                "%s gen transient upstream error (attempt %d/%d): HTTP %s %s",
                what, attempt, _MAX_RETRIES, resp.status_code, last_text[:200],
            )
        except requests.RequestException as exc:
            last_exc = exc
            last_status = None
            log.warning(
                "%s gen request error (attempt %d/%d): %s",
                what, attempt, _MAX_RETRIES, exc,
            )
        if attempt < _MAX_RETRIES:
            time.sleep(_BACKOFF_SECONDS[min(attempt - 1, len(_BACKOFF_SECONDS) - 1)])
    return {
        "ok": False, "status": last_status, "text": last_text,
        "exception": (str(last_exc) if last_exc else None),
        "attempts": _MAX_RETRIES,
    }
