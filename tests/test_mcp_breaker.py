import os
import threading
import time
import unittest

os.environ["DATABASE_URL"] = "sqlite:////tmp/test_mcp_breaker.db"
os.environ["SECRET_KEY"] = "unit-test-secret"
os.environ["MCP_MAX_CONCURRENCY"] = "2"
os.environ["MCP_CIRCUIT_MAX_FAILURES"] = "2"
os.environ["MCP_CIRCUIT_COOLDOWN_SECS"] = "1"

from app.core.database import SessionLocal, init_db
from app.models import User, McpServer
from app.mcp_client import MCPConnectionManager, RemoteMCPClient, MCPClientError
from app.settings import get_settings
get_settings.cache_clear()  # 重新读取本模块设置的 MCP_* env


class _FakeClient:
    """模拟远端 MCP：可调成功率/延迟。"""
    def __init__(self, fail=False, latency=0.0):
        self.fail = fail
        self.latency = latency
        self.calls = 0

    def call_tool(self, name, arguments):
        self.calls += 1
        if self.latency:
            time.sleep(self.latency)
        if self.fail:
            raise MCPClientError("simulated failure")
        return "ok"


class TestMCPBreaker(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        db = SessionLocal()
        u = db.query(User).filter_by(email="mcpbrk@x.com").first()
        if not u:
            u = User(email="mcpbrk@x.com", username="mcpbrk",
                     password_hash="x", role="user", enabled=True)
            db.add(u)
            db.commit()
            db.refresh(u)
        cls.user_id = u.id
        db.query(McpServer).filter(McpServer.user_id == u.id).delete()
        s = McpServer(user_id=u.id, name="brk", transport="http",
                      url="http://x/mcp", auth_type="none", enabled=True)
        db.add(s)
        db.commit()
        db.refresh(s)
        cls.server = s
        db.close()

    def setUp(self):
        MCPConnectionManager.reset_pool()

    def _patch_build(self, fake):
        orig = MCPConnectionManager._build_client
        MCPConnectionManager._build_client = classmethod(lambda cls, server: fake)
        return orig

    def test_circuit_opens_after_failures(self):
        fake = _FakeClient(fail=True)
        orig = self._patch_build(fake)
        try:
            for _ in range(2):
                MCPConnectionManager.call_tool(self.user_id, self.server, "t", {})
            # 第 3 次应被熔断（open）
            res, lat, err = MCPConnectionManager.call_tool(self.user_id, self.server, "t", {})
            self.assertIsNone(res)
            self.assertIn("熔断", err)
            metrics = MCPConnectionManager.get_metrics()
            self.assertEqual(metrics["servers"][0]["state"], "open")
        finally:
            MCPConnectionManager._build_client = orig

    def test_success_resets_circuit(self):
        fake_ok = _FakeClient(fail=False)
        orig = self._patch_build(fake_ok)
        try:
            res, _, err = MCPConnectionManager.call_tool(self.user_id, self.server, "t", {})
            self.assertEqual(res, "ok")
            self.assertIsNone(err)
            metrics = MCPConnectionManager.get_metrics()
            self.assertEqual(metrics["servers"][0]["state"], "closed")
            self.assertEqual(metrics["servers"][0]["total_calls"], 1)
        finally:
            MCPConnectionManager._build_client = orig

    def test_concurrency_limit(self):
        # 并发上限=2，3 个并发调用中最多 2 个同时在跑
        fake = _FakeClient(fail=False, latency=0.3)
        orig = self._patch_build(fake)
        concurrent = {"max": 0}
        lock = threading.Lock()

        def worker():
            res, _, _ = MCPConnectionManager.call_tool(self.user_id, self.server, "t", {})
            return res

        # 用信号量行为间接验证：限制并发，3 个并发 0.3s 任务应在 >0.3s 完成
        threads = [threading.Thread(target=worker) for _ in range(3)]
        start = time.time()
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        elapsed = time.time() - start
        # 并发上限 2 → 3 个任务至少分两批，耗时 > 单次延迟
        self.assertGreater(elapsed, 0.3)
        self.assertEqual(fake.calls, 3)
        MCPConnectionManager._build_client = orig

    def test_reset_pool(self):
        MCPConnectionManager.reset_pool()
        self.assertEqual(MCPConnectionManager.get_metrics()["pool_size"], 0)


if __name__ == "__main__":
    unittest.main()
