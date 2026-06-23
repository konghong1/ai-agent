from __future__ import annotations

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.models import AgentConfig, User
from app.settings import get_settings


DEFAULT_SYSTEM_PROMPT = """You are a practical AI agent.
You can answer normally and call tools when they help.
You must call current_time for questions about the current time.
You must call calculator for arithmetic instead of calculating mentally.
Use workspace tools only for files inside this project.
When a tool result is enough, summarize it clearly in Chinese unless the user asks for another language.

CHOICE INTERACTION:
When you want the user to make a selection, output your response text followed by a <blocks> tag containing a JSON object with a choices array:
<blocks>{"choices": [{"label": "A. ???", "value": "A"}, {"label": "B. ???", "value": "B"}, {"label": "C. ???", "value": "C"}]}</blocks>

The text before <blocks> will be shown as regular message content. The choices will render as clickable buttons. When the user clicks a button, their selection (the value) will be sent as their message. Use labels that are clear and descriptive.
"""


def create_default_agent(db: Session, user_id: int) -> AgentConfig:
    settings = get_settings()
    agent = AgentConfig(
        user_id=user_id,
        name="Default Agent",
        description="默认本地 Agent，包含时间、计算器和工作区文件工具。",
        system_prompt=DEFAULT_SYSTEM_PROMPT,
        model_name=settings.openai_model,
        temperature=0,
        enabled=True,
    )
    db.add(agent)
    return agent


def create_user(db: Session, email: str, username: str, password: str) -> User:
    user = User(email=email.lower(), username=username, password_hash=hash_password(password))
    db.add(user)
    db.flush()
    create_default_agent(db, user.id)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    user = db.scalar(select(User).where(User.email == email.lower()))
    if not user or not verify_password(password, user.password_hash):
        return None
    return user


def new_thread_id() -> str:
    return f"thread-{uuid4().hex[:12]}"
