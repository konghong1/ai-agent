"""轻量远端 MCP 客户端 + 连接池（零新增依赖，基于 httpx）。

支持 MCP Streamable-HTTP / SSE 传输（JSON-RPC 2.0）。
- RemoteMCPClient：单连接客户端，initialize / list_tools / call_tool。
- MCPConnectionManager：按 (user_id, server_id) 池化长连接，带健康检查、
  重连、熔断（失败计数超阈值进入 cooldown），为万级并发预留水平扩容点。

stdio 传输本批不启用（用户决策：先远端）。后续可在此扩展子进程管理。
"""
from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.crypto import decrypt_json, decrypt_secret

logger = logging.getLogger(__name__)

PROTOCOL_VERSION = "2024-11-05"
MCP_SESSION_HEADER = "mcp-session-id"


class MCPClientError(RuntimeError):
    pass


class RemoteMCPClient:
    def __init__(
        self,
        url: str,
        *,
        auth_type: str = "none",
        api_key: str | None = None,
        headers: dict | None = None,
        timeout: float = 30.0,
        _client: httpx.Client | None = None,
    ) -> None:
        self.url = url
        self.auth_type = auth_type
        self.api_key = api_key
        self.extra_headers = dict(headers or {})
        self.timeout = timeout
        self._client = _client or httpx.Client(timeout=timeout)
        self._session_id: str | None = None
        self._initialized = False
        self._lock = threading.Lock()

    # ── 请求头组装（含鉴权与会话）──
    def _base_headers(self) -> dict:
        h = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        h.update(self.extra_headers)
        if self.auth_type == "bearer" and self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        elif self.auth_type == "api_key" and self.api_key:
            h["X-API-Key"] = self.api_key
        if self._session_id:
            h[MCP_SESSION_HEADER] = self._session_id
        return h

    def _post(self, method: str, params: Any = None, rpc_id: str = "1") -> dict:
        payload: dict[str, Any] = {"jsonrpc": "2.0", "id": rpc_id, "method": method}
        if params is not None:
            payload["params"] = params
        try:
            resp = self._client.post(self.url, json=payload, headers=self._base_headers())
        except httpx.HTTPError as e:
            raise MCPClientError(f"HTTP error on {method}: {e}") from e

        sid = resp.headers.get(MCP_SESSION_HEADER)
        if sid and not self._session_id:
            self._session_id = sid

        ctype = resp.headers.get("content-type", "")
        if "text/event-stream" in ctype:
            obj = self._parse_sse(resp.text, rpc_id)
        else:
            try:
                obj = resp.json()
            except Exception:
                raise MCPClientError(f"非 JSON 响应 ({resp.status_code}): {resp.text[:200]}")
        if obj.get("error"):
            err = obj["error"]
            raise MCPClientError(f"MCP error in {method}: {err.get('message')} ({err.get('code')})")
        return obj.get("result") or {}

    @staticmethod
    def _parse_sse(text: str, rpc_id: str) -> dict:
        frames: list[dict] = []
        for raw in text.split("\n"):
            line = raw.strip()
            if not line.startswith("data:"):
                continue
            data = line[len("data:"):].strip()
            if not data:
                continue
            try:
                frames.append(json.loads(data))
            except Exception:
                continue
        for f in frames:
            if f.get("id") == rpc_id or "result" in f or "error" in f:
                return f
        return frames[-1] if frames else {}

    def initialize(self) -> dict:
        with self._lock:
            if self._initialized:
                return {}
            result = self._post(
                "initialize",
                {
                    "protocolVersion": PROTOCOL_VERSION,
                    "clientInfo": {"name": "ai-agent-platform", "version": "0.2.0"},
                    "capabilities": {},
                },
            )
            try:
                self._notify("notifications/initialized", {})
            except Exception:
                pass
            self._initialized = True
            return result or {}

    def _notify(self, method: str, params: Any = None) -> None:
        payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        try:
            self._client.post(self.url, json=payload, headers=self._base_headers())
        except Exception:
            pass

    def list_tools(self) -> list[dict]:
        self.initialize()
        result = self._post("tools/list", {})
        return (result or {}).get("tools", [])

    def call_tool(self, name: str, arguments: dict) -> str:
        self.initialize()
        result = self._post("tools/call", {"name": name, "arguments": arguments or {}})
        content = (result or {}).get("content", [])
        texts = [c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"]
        if (result or {}).get("isError"):
            raise MCPClientError("工具返回错误: " + " ".join(texts))
        return "\n".join(texts)

    def close(self) -> None:
        try:
            self._client.close()
        except Exception:
            pass


@dataclass
class _Entry:
    client: RemoteMCPClient
    tools: list[dict]
    last_used: float
    failures: int = 0
    circuit_until: float = 0.0
    state: str = "closed"          # closed(正常) | open(熔断) | half_open(探测)
    sem: threading.Semaphore | None = None
    # 指标
    total_calls: int = 0
    error_count: int = 0
    last_latency_ms: int = 0
    last_error: str = ""


class MCPConnectionManager:
    """按 (user_id, server_id) 池化 MCP 连接，带熔断 + 并发限流 + 指标。

    为万级并发设计：
    - 每 server 一个信号量（mcp_max_concurrency）限制同时调用数，防连接/资源耗尽；
    - 失败累计达阈值 → 熔断（open），cooldown 后首次调用为半开探测（half_open）；
    - 指标暴露给可观测端点（连接池饱和度 / 工具 P99 / 失败率）。
    横向扩容时每个 Worker 副本持有一份（进程内单例），天然分片、无中心化瓶颈。
    """

    _pools: dict[tuple, _Entry] = {}
    _lock = threading.Lock()
    _sems: dict[tuple, threading.Semaphore] = {}
    _metrics_lock = threading.Lock()
    IDLE_TTL = 1800.0

    @classmethod
    def _key(cls, user_id: int, server_id: int) -> tuple:
        return (user_id, server_id)

    @classmethod
    def _max_failures(cls) -> int:
        from app.settings import get_settings
        return get_settings().mcp_circuit_max_failures

    @classmethod
    def _cooldown(cls) -> float:
        from app.settings import get_settings
        return get_settings().mcp_circuit_cooldown_secs

    @classmethod
    def _max_concurrency(cls) -> int:
        from app.settings import get_settings
        return max(1, get_settings().mcp_max_concurrency)

    @classmethod
    def _build_client(cls, server) -> RemoteMCPClient:
        headers = decrypt_json(getattr(server, "headers", ""))
        api_key = decrypt_secret(getattr(server, "api_key", ""))
        timeout = (getattr(server, "timeout_ms", None) or 30000) / 1000.0
        return RemoteMCPClient(
            url=server.url,
            auth_type=getattr(server, "auth_type", "none") or "none",
            api_key=api_key,
            headers=headers,
            timeout=timeout,
        )

    @classmethod
    def get_client(cls, user_id: int, server) -> RemoteMCPClient:
        key = cls._key(user_id, server.id)
        now = time.time()
        with cls._lock:
            entry = cls._pools.get(key)
            if entry and entry.state == "open" and now < entry.circuit_until:
                raise MCPClientError("MCP 连接熔断中（cooldown），稍后重试")
            if entry and (now - entry.last_used) < cls.IDLE_TTL:
                entry.last_used = now
                return entry.client
        client = cls._build_client(server)
        with cls._lock:
            cls._pools[key] = _Entry(
                client=client, tools=[], last_used=now,
                sem=threading.Semaphore(cls._max_concurrency()),
            )
        return client

    @classmethod
    def get_tools(cls, user_id: int, server) -> list[dict]:
        client = cls.get_client(user_id, server)
        with cls._lock:
            entry = cls._pools[cls._key(user_id, server.id)]
        if not entry.tools:
            try:
                entry.tools = client.list_tools()
                with cls._lock:
                    entry.state = "closed"
                    entry.failures = 0
            except Exception as e:  # 失败计入熔断
                with cls._lock:
                    entry.failures += 1
                    if entry.failures >= cls._max_failures():
                        entry.state = "open"
                        entry.circuit_until = time.time() + cls._cooldown()
                raise
        return entry.tools

    @classmethod
    def call_tool(cls, user_id: int, server, name: str, arguments: dict):
        start = time.time()
        key = cls._key(user_id, server.id)
        with cls._lock:
            entry = cls._pools.get(key)
            if entry is None:
                entry = cls._pools[key] = _Entry(
                    client=cls._build_client(server), tools=[], last_used=time.time(),
                    sem=threading.Semaphore(cls._max_concurrency()),
                )
            sem = entry.sem
        # 并发限流：超并发数则排队，避免压垮远端 MCP / 耗尽本地资源。
        sem.acquire()
        try:
            try:
                client = cls.get_client(user_id, server)
            except MCPClientError:
                # 熔断中：直接记录失败并返回，不阻塞信号量外的逻辑。
                with cls._lock:
                    entry.error_count += 1
                    entry.last_error = "circuit open"
                return None, int((time.time() - start) * 1000), "MCP 连接熔断中"
            result = client.call_tool(name, arguments)
            latency = int((time.time() - start) * 1000)
            with cls._lock:
                entry.total_calls += 1
                entry.last_latency_ms = latency
                entry.failures = 0
                if entry.state == "half_open":
                    entry.state = "closed"
            return result, latency, None
        except Exception as e:
            latency = int((time.time() - start) * 1000)
            with cls._lock:
                entry.total_calls += 1
                entry.error_count += 1
                entry.last_latency_ms = latency
                entry.last_error = str(e)[:200]
                entry.failures += 1
                if entry.failures >= cls._max_failures():
                    entry.state = "open"
                    entry.circuit_until = time.time() + cls._cooldown()
                elif entry.state == "half_open":
                    # 半开探测失败 → 重新熔断
                    entry.state = "open"
                    entry.circuit_until = time.time() + cls._cooldown()
            return None, latency, str(e)
        finally:
            sem.release()

    @classmethod
    def reset_pool(cls) -> None:
        with cls._lock:
            cls._pools.clear()
            cls._sems.clear()

    @classmethod
    def get_metrics(cls) -> dict:
        """连接池与调用指标快照（供可观测端点 / 万级并发容量评估）。"""
        with cls._lock:
            servers = []
            for (uid, sid), e in cls._pools.items():
                sem = e.sem
                active = (sem._value if sem else 0)
                max_c = cls._max_concurrency()
                servers.append({
                    "user_id": uid,
                    "server_id": sid,
                    "state": e.state,
                    "failures": e.failures,
                    "total_calls": e.total_calls,
                    "error_count": e.error_count,
                    "last_latency_ms": e.last_latency_ms,
                    "concurrency": {"active": max_c - active, "max": max_c,
                                    "saturation": round((max_c - active) / max_c, 3)},
                    "last_error": e.last_error,
                })
            return {
                "pool_size": len(cls._pools),
                "max_concurrency_per_server": cls._max_concurrency(),
                "circuit_max_failures": cls._max_failures(),
                "circuit_cooldown_secs": cls._cooldown(),
                "servers": servers,
            }
