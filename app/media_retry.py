"""Shared retry/backoff for provider media calls (image/video).

AgnesAI's gateway occasionally returns transient upstream errors such as
``code: do_request_failed`` ("upstream error: do request failed"), 5xx
responses, or connection resets. These are almost always intermittent — a
short exponential-backoff retry recovers the request without the user ever
seeing a hard failure.

Permanent client errors (e.g. 400 ``UnsupportedParamsError``) are detected
and NOT retried, so we don't waste latency on requests that will never
succeed.

A special case is the server-side **backpressure** signal ``image queue is
full, please retry later`` (HTTP 503 with ``code: do_request_failed``). This
is NOT a quick blip — the upstream image queue is capacity-saturated and needs
much longer to drain than the generic 4-16s backoff. So it gets its own, far
more patient retry schedule (more attempts + longer sleeps) to ride out brief
saturation windows, instead of burning 3 short retries and failing anyway.
"""
from __future__ import annotations

import json
import time
from typing import Any

import requests

from app.http_client import request_with_fallback

# Generic transient conditions: short backoff, few retries.
_MAX_RETRIES = 3
_BACKOFF_SECONDS = (4, 8, 16)

# Server-side backpressure ("queue is full"): be patient — the queue needs
# time to drain. More attempts + longer sleeps so brief saturation windows
# can be ridden out instead of failing instantly.
_QUEUE_FULL_MAX_RETRIES = 5
_QUEUE_FULL_BACKOFF = (10, 20, 30, 45, 60)


def classify_response(resp: "requests.Response") -> str:
    """Classify an HTTP error response.

    Returns one of:
      - ``"permanent"``   -> do not retry (wasted latency)
      - ``"queue_full"``  -> upstream capacity backpressure; use the patient
                             long-backoff schedule
      - ``"transient"``   -> ordinary intermittent failure; short backoff

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
    # immediately and surface a clean error instead of burning backoffs.
    if "model_not_found" in code or "model_not_found" in msg or "no available channel" in msg:
        return "permanent"
    # Server-side capacity backpressure — ride it out with a long backoff.
    if "queue is full" in msg:
        return "queue_full"
    # Generic transient conditions below.
    if resp.status_code >= 500:
        return "transient"
    if resp.status_code == 429:  # rate limited -> back off and retry
        return "transient"
    # AgnesAI upstream backend failures
    if "do_request_failed" in code:
        return "transient"
    if "upstream" in code or "upstream" in msg or "do request failed" in msg:
        return "transient"
    return "permanent"


# Thin backward-compatible wrapper for any external callers.
def is_transient_response(resp: "requests.Response") -> bool:
    return classify_response(resp) != "permanent"


def clean_provider_error(text: str | None, exc_str: str | None) -> str:
    """Turn a raw provider error body into a display-friendly message.

    Keeps the upstream ``message`` (so the user can report it) but drops the
    noisy JSON envelope. ``queue is full`` gets a localized, action-oriented
    hint instead of the raw English backpressure text.
    """
    if text:
        try:
            body = json.loads(text)
            err = body.get("error") if isinstance(body, dict) else None
            if isinstance(err, dict) and err.get("message"):
                msg = str(err["message"])
                if "queue is full" in msg.lower():
                    return "图像服务当前繁忙（队列已满），请稍等片刻后重试"
                return msg
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
    """POST JSON with adaptive backoff for transient upstream failures.

    The retry schedule adapts at runtime: the moment a ``queue is full``
    backpressure response is seen, the schedule switches to the longer, more
    patient one (and the attempt budget grows) so brief saturation windows
    can be ridden out.

    Returns a dict with one of:
      - ``{"ok": True, "json": <parsed response>, "attempts": <int>,
         "queue_full": <bool>}`` on success
      - ``{"ok": False, "status": <int|None>, "text": <str>,
         "exception": <str|None>, "attempts": <int>,
         "queue_full": <bool>}`` on failure
    """
    log = logger or __import__("logging").getLogger(__name__)

    last_exc: Exception | None = None
    last_status: int | None = None
    last_text = ""

    backoff_seq = _BACKOFF_SECONDS
    max_retries = _MAX_RETRIES
    queue_full_seen = False
    attempt = 0

    while attempt < max_retries:
        attempt += 1
        try:
            resp = request_with_fallback(
                "POST", url, json=payload, headers=headers, timeout=timeout
            )
            if resp.status_code < 400:
                return {
                    "ok": True, "json": resp.json(),
                    "attempts": attempt, "queue_full": queue_full_seen,
                }
            last_status = resp.status_code
            last_text = resp.text[:500]
            cls = classify_response(resp)
            if cls == "permanent":
                # Permanent (e.g. 400 UnsupportedParamsError): stop early.
                log.warning(
                    "%s gen permanent error (HTTP %s): %s",
                    what, resp.status_code, last_text[:200],
                )
                return {
                    "ok": False, "status": last_status, "text": last_text,
                    "exception": None, "attempts": attempt,
                    "queue_full": False,
                }
            if cls == "queue_full":
                # Switch to the patient schedule for the rest of the run.
                if not queue_full_seen:
                    queue_full_seen = True
                    backoff_seq = _QUEUE_FULL_BACKOFF
                    max_retries = _QUEUE_FULL_MAX_RETRIES
            log.warning(
                "%s gen transient upstream error (attempt %d/%d%s): HTTP %s %s",
                what, attempt, max_retries,
                ", queue-full" if cls == "queue_full" else "",
                resp.status_code, last_text[:200],
            )
        except requests.RequestException as exc:
            last_exc = exc
            last_status = None
            log.warning(
                "%s gen request error (attempt %d/%d): %s",
                what, attempt, max_retries, exc,
            )
        if attempt < max_retries:
            sleep_s = backoff_seq[min(attempt - 1, len(backoff_seq) - 1)]
            time.sleep(sleep_s)
    return {
        "ok": False, "status": last_status, "text": last_text,
        "exception": (str(last_exc) if last_exc else None),
        "attempts": attempt, "queue_full": queue_full_seen,
    }
