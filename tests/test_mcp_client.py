import os

os.environ["DATABASE_URL"] = "sqlite:////tmp/test_mcp_unit.db"
os.environ["SECRET_KEY"] = "unit-test-secret"

import httpx
import json
import unittest

from app.core.database import SessionLocal, init_db
from app.core.security import hash_password
from app.models import McpServer, User
from app.mcp_client import MCPConnectionManager, RemoteMCPClient
from app.mcp_tools import build_mcp_langchain_tools, get_enabled_remote_servers


def _fake_handler(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content)
    method = body.get("method")
    rpc_id = body.get("id")
    if method == "initialize":
        result = {"protocolVersion": "2024-11-05", "capabilities": {}, "serverInfo": {"name": "fake", "version": "1"}}
    elif method == "tools/list":
        result = {
            "tools": [
                {
                    "name": "add",
                    "description": "add two numbers",
                    "inputSchema": {
                        "type": "object",
                        "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
                        "required": ["a", "b"],
                    },
                }
            ]
        }
    elif method == "tools/call":
        params = body.get("params", {})
        name = params.get("name")
        args = params.get("arguments", {})
        if name == "add":
            result = {"content": [{"type": "text", "text": str(args["a"] + args["b"])}], "isError": False}
        else:
            result = {"content": [{"type": "text", "text": "unknown"}], "isError": True}
    else:
        result = {}
    return httpx.Response(200, json={"jsonrpc": "2.0", "id": rpc_id, "result": result})


class TestMCPClient(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls._orig = httpx.Client
        # 用 MockTransport（同步 handler）替代真实网络，隔离稳定
        def _fake_client(*a, **k):
            return cls._orig(transport=httpx.MockTransport(_fake_handler))

        httpx.Client = _fake_client

        db = SessionLocal()
        u = db.query(User).filter_by(email="mcpunit@x.com").first()
        if not u:
            u = User(
                email="mcpunit@x.com",
                username="mcpunit",
                password_hash=hash_password("x"),
                role="user",
                enabled=True,
            )
            db.add(u)
            db.commit()
            db.refresh(u)
        cls.user_id = u.id
        srv = db.query(McpServer).filter_by(user_id=u.id, name="fake").first()
        if not srv:
            srv = McpServer(
                user_id=u.id,
                name="fake",
                transport="http",
                url="http://test/",
                enabled=True,
                auth_type="none",
                api_key="",
                headers="",
                tool_allowlist=[],
            )
            db.add(srv)
            db.commit()
            db.refresh(srv)
        cls.server_id = srv.id
        cls.db = db

    @classmethod
    def tearDownClass(cls):
        httpx.Client = cls._orig

    def test_client_roundtrip(self):
        c = RemoteMCPClient("http://test/")
        c.initialize()
        tools = c.list_tools()
        self.assertEqual(tools[0]["name"], "add")
        self.assertEqual(c.call_tool("add", {"a": 2, "b": 3}), "5")

    def test_sse_parse(self):
        sse = 'event: message\ndata: {"jsonrpc":"2.0","id":"1","result":{"x":1}}\n\n'
        obj = RemoteMCPClient._parse_sse(sse, "1")
        self.assertEqual(obj.get("result"), {"x": 1})

    def test_build_tools(self):
        servers = get_enabled_remote_servers(self.db, self.user_id)
        self.assertEqual(len(servers), 1)
        tools = build_mcp_langchain_tools(self.db, self.user_id)
        self.assertEqual(len(tools), 1)
        t = tools[0]
        self.assertEqual(t.name, "mcp_fake_add")
        self.assertEqual(t.func(a=4, b=6), "10")

    def test_manager_call(self):
        srv = self.db.get(McpServer, self.server_id)
        res, _dur, err = MCPConnectionManager.call_tool(self.user_id, srv, "add", {"a": 1, "b": 1})
        self.assertEqual(res, "2")
        self.assertIsNone(err)


if __name__ == "__main__":
    unittest.main()
