import os

os.environ["DATABASE_URL"] = "sqlite:////tmp/test_skill_runtime.db"
os.environ["SECRET_KEY"] = "unit-test-secret"

import unittest
from app.core.database import SessionLocal, init_db
from app.models import User, Skill
from app.skill_runtime import get_skill_catalog, load_skill_content, build_use_skill_tool


class TestSkillRuntime(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        db = SessionLocal()
        u = db.query(User).filter_by(email="skillrt@x.com").first()
        if not u:
            u = User(email="skillrt@x.com", username="skillrt",
                     password_hash="x", role="user", enabled=True)
            db.add(u)
            db.commit()
            db.refresh(u)
        cls.user = u
        cls.user_id = u.id
        # 清理旧测试数据
        db.query(Skill).filter(Skill.user_id == u.id).delete()
        db.commit()
        # 启用技能
        db.add(Skill(user_id=u.id, name="pdf", title="PDF 处理",
                     description="处理 PDF 文档", content="步骤：1.读取 2.解析",
                     trigger_words=["pdf", "文档"], enabled=True, version=1))
        # 禁用技能（不应出现在目录）
        db.add(Skill(user_id=u.id, name="off", title="离线",
                     description="x", content="secret", enabled=False, version=1))
        db.commit()
        db.close()

    def setUp(self):
        self.db = SessionLocal()

    def tearDown(self):
        self.db.close()

    def test_catalog_only_enabled(self):
        cat = get_skill_catalog(self.db, self.user_id)
        self.assertIn("pdf", cat)
        self.assertIn("触发词", cat)
        self.assertNotIn("secret", cat)  # 禁用技能内容不出现
        self.assertNotIn("off", cat)     # 禁用技能不进目录

    def test_load_content(self):
        self.assertIn("步骤", load_skill_content(self.db, self.user_id, "pdf"))
        self.assertIn("未找到", load_skill_content(self.db, self.user_id, "nope"))

    def test_use_skill_tool(self):
        tool = build_use_skill_tool(self.db, self.user_id)
        self.assertIsNotNone(tool)
        self.assertEqual(tool.name, "use_skill")
        out = tool.func(skill_name="pdf")
        self.assertIn("步骤", out)

    def test_use_skill_tool_none_when_empty(self):
        # 用独立用户（无技能）验证返回 None
        db = SessionLocal()
        u2 = db.query(User).filter_by(email="skillrt2@x.com").first()
        if not u2:
            u2 = User(email="skillrt2@x.com", username="skillrt2",
                      password_hash="x", role="user", enabled=True)
            db.add(u2)
            db.commit()
            db.refresh(u2)
        self.assertIsNone(build_use_skill_tool(db, u2.id))
        db.close()


if __name__ == "__main__":
    unittest.main()
