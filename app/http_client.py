"""Resilient outbound HTTP for the agent backend.

Background
----------
The deployment injects ``HTTPS_PROXY`` / ``HTTP_PROXY`` (a host-side sandbox
proxy at ``host.docker.internal:33210``) so the container can reach external
AI services. That proxy is *optional infrastructure*: when it is unreachable
(e.g. the sandbox proxy is not running) every external call fails hard with a
``ProxyError`` and there is no recovery — image/video generation and the video
status poll all break, and the 3-second poll loop hammers the dead proxy.

This module makes egress resilient with two layers:

1. ``ensure_proxy_strategy()`` — run once at import. Probes the configured
   proxy; if it cannot be reached it **clears the proxy env vars for this
   process** so that ``requests``, ``httpx`` and the ``openai`` SDK all
   transparently fall back to a direct connection. No per-call plumbing needed
   for libraries we do not wrap directly (e.g. the LLM client).
2. ``request_with_fallback`` / ``download_bytes_with_fallback`` — a per-call
   safety net for the calls we DO wrap: if a proxy error slips through (proxy
   died after startup) the call is retried over a direct connection. A short
   "proxy down" cache avoids re-probing a dead proxy on every call (important
   for the 3-second video status poll).

Set ``DISABLE_PROXY_AUTOFALLBACK=1`` in the environment to keep the proxy
mandatory (no auto-clear) — only do this in a deployment where direct egress
is genuinely blocked and the proxy is guaranteed available.
"""
from __future__ import annotations

import logging
import os
import socket
import time
from typing import Any
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

_NO_PROXY = {"http": None, "https": None}
_PROXY_DOWN_TTL = 30.0  # remember a dead proxy for 30s before re-probing
_proxy_down_until = 0.0
_strategy_resolved = False


def _proxy_url() -> str | None:
    return os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")


def _proxy_host_port() -> tuple[str, int] | None:
    url = _proxy_url()
    if not url:
        return None
    parsed = urlparse(url)
    host = parsed.hostname
    if not host:
        return None
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return host, port


def _proxy_reachable(timeout: float = 2.0) -> bool:
    hp = _proxy_host_port()
    if not hp:
        return False
    try:
        with socket.create_connection(hp, timeout=timeout):
            return True
    except OSError:
        return False


def ensure_proxy_strategy() -> None:
    """Probe the configured proxy once. If it is unreachable, clear the proxy
    env vars for this process so every HTTP library falls back to direct egress.

    Idempotent: only runs once per process. A ``DISABLE_PROXY_AUTOFALLBACK``
    env var skips the auto-clear (keeps the proxy mandatory).
    """
    global _strategy_resolved
    if _strategy_resolved:
        return
    _strategy_resolved = True

    if os.environ.get("DISABLE_PROXY_AUTOFALLBACK"):
        return
    if not _proxy_url():
        return

    if _proxy_reachable():
        logger.info("Egress proxy %s reachable — using it for outbound calls", _proxy_url())
        return

    # Proxy is configured but unreachable: drop it so outbound calls go direct.
    proxy = _proxy_url()
    for var in ("HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "http_proxy"):
        os.environ.pop(var, None)
    logger.warning(
        "Egress proxy %s unreachable — cleared proxy env; outbound calls will use direct connection",
        proxy,
    )


def _proxy_down_cached() -> bool:
    return time.monotonic() < _proxy_down_until


def _mark_proxy_down() -> None:
    global _proxy_down_until
    _proxy_down_until = time.monotonic() + _PROXY_DOWN_TTL
    logger.warning("Outbound proxy unreachable; using direct connection for ~%.0fs", _PROXY_DOWN_TTL)


def _is_proxy_error(exc: Exception) -> bool:
    from requests.exceptions import ProxyError

    if isinstance(exc, ProxyError):
        return True
    proxy = _proxy_url() or ""
    if proxy:
        host = urlparse(proxy).hostname or ""
        if host and host in str(exc):
            return True
    return False


def request_with_fallback(method: str, url: str, **kwargs: Any) -> "requests.Response":
    """``requests.request`` with automatic direct-connection fallback when the
    configured proxy is unreachable.

    Returns a ``requests.Response`` on success. Only re-raises on non-proxy
    errors so callers can keep calling ``raise_for_status()`` / ``.json()``.
    """
    if not _proxy_url() or _proxy_down_cached():
        return requests.request(method, url, proxies=_NO_PROXY, **kwargs)
    try:
        return requests.request(method, url, **kwargs)
    except Exception as exc:
        if _is_proxy_error(exc):
            _mark_proxy_down()
            logger.warning("Retrying %s %s without proxy", method, url)
            return requests.request(method, url, proxies=_NO_PROXY, **kwargs)
        raise


def download_bytes_with_fallback(url: str, *, timeout: float = 120) -> tuple[bytes, str | None]:
    """Download binary content, retrying without proxy if the proxy fails.

    Returns ``(content_bytes, content_type)``. Raises the last seen exception
    on final failure. Tries, in order: httpx via env proxy -> httpx direct ->
    requests direct.
    """
    import httpx

    last_exc: Exception | None = None

    if _proxy_url() and not _proxy_down_cached():
        try:
            resp = httpx.get(url, timeout=timeout, follow_redirects=True)
            resp.raise_for_status()
            return resp.content, resp.headers.get("content-type")
        except Exception as exc:
            last_exc = exc
            if _is_proxy_error(exc):
                _mark_proxy_down()
                logger.warning("Download proxy error; retrying %s without proxy", url)
            # fall through to the direct attempt below

    # Direct attempt via httpx (bypass env proxy explicitly).
    try:
        resp = httpx.get(url, timeout=timeout, follow_redirects=True, proxy=None)
        resp.raise_for_status()
        return resp.content, resp.headers.get("content-type")
    except Exception as exc:
        last_exc = exc

    # Final fallback via requests (also direct).
    try:
        resp = request_with_fallback("GET", url, timeout=timeout)
        resp.raise_for_status()
        return resp.content, resp.headers.get("content-type")
    except Exception as exc:
        last_exc = exc

    raise last_exc or RuntimeError("download failed")


# Run the one-time proxy probe when this module is first imported (covers both
# the api and worker processes, since both import this module via media.py).
try:
    ensure_proxy_strategy()
except Exception:  # never block import / startup on a probe failure
    pass
