import os

os.environ["DATABASE_URL"] = "sqlite:////tmp/test_agent_ext.db"
os.environ["SECRET_KEY"] = "unit-test-secret"
os.environ["ENABLE_MCP_TOOLS"] = "true"
os.environ["ENABLE_SKILL_TOOLS"] = "true"
os.environ["ENABLE_HOOKS"] = "true"

import unittest
import app.settings as _settings_mod

_settings_mod.get_settings.cache_clear()

from langchain_core.messages import AIMessage
from app.core.database import SessionLocal, init_db
from app.models import User, Skill, Hook, ToolCallAudit
from app.agent import ask_agent


class _FakeLLM:
    """模拟 LLM：第 1 次返回 use_skill 工具调用，第 2 次返回最终答案。"""
    def __init__(self):
        self.calls = 0

    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        self.calls += 1
        if self.calls == 1:
            return AIMessage(content="", tool_calls=[
                {"name": "use_skill", "args": {"skill_name": "pdf"}, "id": "c1"}
            ])
        return AIMessage(content="FINAL_DONE")


class TestAgentExtensions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        db = SessionLocal()
        u = db.query(User).filter_by(email="agentext@x.com").first()
        if not u:
            u = User(email="agentext@x.com", username="agentext",
                     password_hash="x", role="user", enabled=True)
            db.add(u)
            db.commit()
            db.refresh(u)
        cls.user_id = u.id
        db.query(Skill).filter(Skill.user_id == u.id).delete()
        db.query(Hook).filter(Hook.user_id == u.id).delete()
        db.query(ToolCallAudit).filter(ToolCallAudit.user_id == u.id).delete()
        # 启用技能（含正文）
        db.add(Skill(user_id=u.id, name="pdf", title="PDF 处理",
                     description="处理PDF", content="步骤：1.上传 2.解析",
                     trigger_words=["pdf"], enabled=True, version=1))
        # PreToolUse Hook（放行）
        db.add(Hook(user_id=u.id, event="PreToolUse",
                    command='echo \'{"decision":"approve"}\'',
                    matcher="use_skill", enabled=True, on_error="block"))
        db.commit()
        db.close()
        cls._orig_llm = __import__("app.agent", fromlist=["_create_llm_from_config"])._create_llm_from_config

    @classmethod
    def tearDownClass(cls):
        import app.agent as _a
        _a._create_llm_from_config = cls._orig_llm

    def setUp(self):
        import app.agent as _a
        self._a = _a
        self._a._create_llm_from_config = lambda *a, **k: _FakeLLM()

    def tearDown(self):
        self._a._create_llm_from_config = self._orig_llm

    def test_ask_agent_runs_skill_and_hooks(self):
        db = SessionLocal()
        # 清空该用户审计，便于断言
        db.query(ToolCallAudit).filter(ToolCallAudit.user_id == self.user_id).delete()
        db.commit()
        answer, thread_id, blocks = ask_agent(
            db=db, user_id=self.user_id, agent_id=None,
            message="帮我处理 pdf 文档",
        )
        db.commit()
        # 1) 最终答案来自假 LLM 第二次调用
        self.assertIn("FINAL_DONE", answer)
        # 2) Hook 实际执行（PreToolUse 写入审计）
        audits = db.query(ToolCallAudit).filter(
            ToolCallAudit.user_id == self.user_id, ToolCallAudit.tool_type == "hook"
        ).all()
        self.assertTrue(audits, "PreToolUse Hook 应已执行并留痕")
        self.assertEqual(audits[0].hook_decision, "approve")
        db.close()


if __name__ == "__main__":
    unittest.main()
