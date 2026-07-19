import os
import pathlib
import tempfile

# 在导入 app 之前把数据库指向临时 sqlite，绝不触碰真实 agent.db / ai_agent.db。
_tmp = pathlib.Path(tempfile.mkdtemp(prefix="cs_test_")) / "test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}"
# 全局开关保持默认关闭；单元测试直接驱动 ContextService（不经 ask_agent）。
os.environ["ENABLE_CONTEXT_SERVICE"] = "false"
os.environ["ENABLE_RETRIEVAL_REFLEX"] = "false"
os.environ["ENABLE_MEMORY_RECALL"] = "false"

# 在导入 app 之前设置好 DATABASE_URL 后，立即建表（临时 sqlite，不碰真实数据）。
from app.core.database import init_db

init_db()
