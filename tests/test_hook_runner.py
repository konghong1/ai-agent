import os

os.environ["DATABASE_URL"] = "sqlite:////tmp/test_hook_runner.db"
os.environ["SECRET_KEY"] = "unit-test-secret"
os.environ["ENABLE_HOOKS"] = "true"

import unittest
import app.settings as _settings_mod

# 清空 lru_cache：同进程内其他测试模块可能已用默认 env 缓存了 Settings()，
# 导致本模块的 ENABLE_HOOKS 不生效。
_settings_mod.get_settings.cache_clear()

from app.core.database import SessionLocal, init_db
from app.models import User, Hook, ToolCallAudit
from app.hook_runner import run_hooks, first_blocking


class TestHookRunner(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        db = SessionLocal()
        u = db.query(User).filter_by(email="hookrt@x.com").first()
        if not u:
            u = User(email="hookrt@x.com", username="hookrt",
                     password_hash="x", role="user", enabled=True)
            db.add(u)
            db.commit()
            db.refresh(u)
        cls.user = u
        cls.user_id = u.id
        db.query(Hook).filter(Hook.user_id == u.id).delete()
        db.query(ToolCallAudit).filter(ToolCallAudit.user_id == u.id).delete()
        db.commit()
        db.close()

    def setUp(self):
        self.db = SessionLocal()
        # 每用例清空该用户 hook/audit
        self.db.query(Hook).filter(Hook.user_id == self.user_id).delete()
        self.db.query(ToolCallAudit).filter(ToolCallAudit.user_id == self.user_id).delete()
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def _add(self, **kw):
        kw.setdefault("command", "true")
        kw.setdefault("event", "PreToolUse")
        kw.setdefault("enabled", True)
        kw.setdefault("on_error", "block")
        h = Hook(user_id=self.user_id, **kw)
        self.db.add(h)
        self.db.commit()
        self.db.refresh(h)
        return h

    def test_approve_via_stdout_json(self):
        self._add(command='echo \'{"decision":"approve"}\'')
        outs = run_hooks("PreToolUse", self.user_id, self.db,
                         {"session_id": "s1", "tool_name": "x", "tool_args": {}})
        self.assertEqual(len(outs), 1)
        self.assertEqual(outs[0].decision, "approve")
        # 审计留痕
        self.assertEqual(self.db.query(ToolCallAudit).count(), 1)

    def test_block_on_nonzero_exit(self):
        self._add(command='exit 3', on_error="block")
        outs = run_hooks("PreToolUse", self.user_id, self.db,
                         {"session_id": "s1", "tool_name": "x", "tool_args": {}})
        self.assertTrue(first_blocking(outs))
        self.assertEqual(outs[0].decision, "block")

    def test_continue_on_error(self):
        self._add(command='exit 3', on_error="continue")
        outs = run_hooks("PreToolUse", self.user_id, self.db,
                         {"session_id": "s1", "tool_name": "x", "tool_args": {}})
        self.assertIsNone(first_blocking(outs))
        self.assertEqual(outs[0].decision, "approve")

    def test_modify_decision(self):
        self._add(command='echo \'{"decision":"modify","data":{"tool_args":{"a":1}}}\'')
        outs = run_hooks("PreToolUse", self.user_id, self.db,
                         {"session_id": "s1", "tool_name": "x", "tool_args": {}})
        self.assertEqual(outs[0].decision, "modify")
        self.assertEqual(outs[0].data.get("tool_args"), {"a": 1})

    def test_disabled_hook_skipped(self):
        self._add(enabled=False, command='echo \'{"decision":"approve"}\'')
        outs = run_hooks("PreToolUse", self.user_id, self.db,
                         {"session_id": "s1", "tool_name": "x", "tool_args": {}})
        self.assertEqual(outs, [])

    def test_matcher_filtering(self):
        self._add(matcher="foo_*", command='echo \'{"decision":"approve"}\'')
        self._add(matcher="bar_*", command='echo \'{"decision":"approve"}\'')
        # 仅 foo_* 命中
        outs = run_hooks("PreToolUse", self.user_id, self.db,
                         {"session_id": "s1", "tool_name": "foo_1", "tool_args": {}},
                         matcher="foo_1")
        self.assertEqual(len(outs), 1)

    def test_event_filtering(self):
        self._add(event="PostToolUse", command='echo \'{"decision":"approve"}\'')
        # PreToolUse 无 hook
        outs = run_hooks("PreToolUse", self.user_id, self.db,
                         {"session_id": "s1", "tool_name": "x", "tool_args": {}})
        self.assertEqual(outs, [])

    def test_secret_env_decrypted(self):
        # secret_env 经 encrypt_json 存储；钩子应能读到解密后的变量
        from app.core.crypto import encrypt_json
        h = Hook(user_id=self.user_id, event="PreToolUse",
                 command='test -n "$TOKEN" && echo \'{"decision":"approve"}\' || echo \'{"decision":"block"}\'',
                 enabled=True, on_error="block")
        h.secret_env = encrypt_json({"TOKEN": "abc123"})
        self.db.add(h)
        self.db.commit()
        outs = run_hooks("PreToolUse", self.user_id, self.db,
                         {"session_id": "s1", "tool_name": "x", "tool_args": {}})
        decisions = [o.decision for o in outs]
        self.assertIn("approve", decisions)


if __name__ == "__main__":
    unittest.main()
