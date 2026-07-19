import json
import os
import unittest

os.environ["DATABASE_URL"] = "sqlite:////tmp/test_sandbox.db"
os.environ["SECRET_KEY"] = "unit-test-secret"
os.environ["ENABLE_HOOKS"] = "true"
os.environ["HOOK_SANDBOX_MAX_OUTPUT_BYTES"] = "1024"
os.environ["HOOK_SANDBOX_MODE"] = "process"

from app.core.database import SessionLocal, init_db
from app.models import User, Hook
from app.hook_runner import _run_one, sandbox_probe
from app.settings import get_settings
get_settings.cache_clear()  # 重新读取本模块设置的 env（lru_cache 可能已被其他模块预热）


class TestSandbox(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        db = SessionLocal()
        u = db.query(User).filter_by(email="sandbox@x.com").first()
        if not u:
            u = User(email="sandbox@x.com", username="sandbox",
                     password_hash="x", role="user", enabled=True)
            db.add(u)
            db.commit()
            db.refresh(u)
        cls.user_id = u.id
        db.query(Hook).filter(Hook.user_id == u.id).delete()
        db.commit()
        db.close()

    def _hook(self, **kw):
        base = dict(user_id=self.user_id, event="PreToolUse", command="true",
                    enabled=True, on_error="block")
        base.update(kw)
        return Hook(**base)

    def test_input_truncated_no_crash(self):
        settings = get_settings()
        # 超大 payload 被截断，钩子仍能运行（不崩）
        h = self._hook(command='echo \'{"decision":"approve"}\'')
        big = {"event": "PreToolUse", "huge": "x" * (10 ** 7)}
        out = _run_one(h, big, settings)
        self.assertIn(out.decision, ("approve", "block"))

    def test_output_cap(self):
        settings = get_settings()
        # 输出远超 1KB 上限 → 截断，不崩，决策按 approve
        h = self._hook(command='head -c 200000 /dev/zero | tr "\\0" "A"; echo \'{"decision":"approve"}\'')
        out = _run_one(h, {"event": "PreToolUse"}, settings)
        self.assertEqual(out.decision, "approve")

    def test_mode_disabled_runs(self):
        settings = get_settings()
        settings.hook_sandbox_mode = "disabled"
        h = self._hook(command='echo \'{"decision":"approve"}\'')
        out = _run_one(h, {"event": "PreToolUse"}, settings)
        self.assertEqual(out.decision, "approve")
        settings.hook_sandbox_mode = "process"

    def test_probe_returns_decision(self):
        settings = get_settings()
        h = self._hook(command='echo \'{"decision":"approve"}\'')
        out = sandbox_probe(h, settings)
        self.assertEqual(out.decision, "approve")
        self.assertEqual(out.error, "")

    def test_probe_failure_reported(self):
        settings = get_settings()
        # 命令会非零退出 → 探针报错（供安全闸门拦截）
        h = self._hook(command="exit 3")
        out = sandbox_probe(h, settings)
        self.assertTrue(out.error)
        self.assertEqual(out.decision, "block")


if __name__ == "__main__":
    unittest.main()
