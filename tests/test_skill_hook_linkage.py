import os
import unittest

os.environ["DATABASE_URL"] = "sqlite:////tmp/test_skill_hook.db"
os.environ["SECRET_KEY"] = "unit-test-secret"
os.environ["ENABLE_HOOKS"] = "true"

from app.core.database import SessionLocal, init_db
from app.models import User, Skill, Hook
from app.skill_runtime import sync_declared_hooks, apply_skill_enabled
from app.settings import get_settings
get_settings.cache_clear()


class TestSkillHookLinkage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        db = SessionLocal()
        u = db.query(User).filter_by(email="skillhook@x.com").first()
        if not u:
            u = User(email="skillhook@x.com", username="skillhook",
                     password_hash="x", role="user", enabled=True)
            db.add(u)
            db.commit()
            db.refresh(u)
        cls.user_id = u.id
        db.query(Hook).filter(Hook.user_id == u.id).delete()
        db.query(Skill).filter(Skill.user_id == u.id).delete()
        db.commit()
        db.close()

    def setUp(self):
        self.db = SessionLocal()
        self.u = self.db.query(User).filter_by(id=self.user_id).first()

    def tearDown(self):
        self.db.close()

    def _make_skill(self, name, declared):
        s = Skill(user_id=self.u.id, name=name, title=name, description="d",
                  source_type="inline", content="x", enabled=False, version=1,
                  declared_hooks=declared)
        self.db.add(s)
        self.db.commit()
        self.db.refresh(s)
        return s

    def test_enable_creates_declared_hooks(self):
        s = self._make_skill("hs1", {
            "PreToolUse": {"command": 'echo \'{"decision":"approve"}\''},
            "PostToolUse": {"command": 'echo \'{"decision":"approve"}\''}})
        linked = apply_skill_enabled(self.db, s, True)
        self.assertEqual(len(linked), 2)
        hooks = self.db.query(Hook).filter_by(skill_id=s.id).all()
        self.assertEqual(len(hooks), 2)
        self.assertTrue(all(h.enabled for h in hooks))
        self.assertEqual({h.event for h in hooks}, {"PreToolUse", "PostToolUse"})

    def test_disable_deactivates_hooks(self):
        s = self._make_skill("hs2", {
            "PreToolUse": {"command": 'echo \'{"decision":"approve"}\''}})
        apply_skill_enabled(self.db, s, True)
        apply_skill_enabled(self.db, s, False)
        hooks = self.db.query(Hook).filter_by(skill_id=s.id).all()
        self.assertEqual(len(hooks), 1)
        self.assertTrue(all(not h.enabled for h in hooks))

    def test_reenable_reactivates(self):
        s = self._make_skill("hs3", {
            "PreToolUse": {"command": 'echo \'{"decision":"approve"}\''}})
        apply_skill_enabled(self.db, s, True)
        apply_skill_enabled(self.db, s, False)
        apply_skill_enabled(self.db, s, True)
        hooks = self.db.query(Hook).filter_by(skill_id=s.id).all()
        self.assertTrue(all(h.enabled for h in hooks))

    def test_invalid_event_skipped(self):
        s = self._make_skill("hs4", {"NotAnEvent": {"command": 'echo x'}})
        linked = sync_declared_hooks(self.db, s)
        self.assertEqual(len(linked), 0)


if __name__ == "__main__":
    unittest.main()
