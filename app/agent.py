from __future__ import annotations

import json
import re

from fastapi import HTTPException
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langsmith import tracing_context
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AgentConfig, Message, Thread
from app.services import new_thread_id
from app.settings import get_settings
from app.tools import get_tools

_BLOCKS_RE = re.compile(r"<blocks>(.*?)</blocks>", re.DOTALL)


def _extract_blocks(text: str) -> tuple[str, dict]:
    blocks: dict | None = None
    text_result = text
    match = _BLOCKS_RE.search(text)
    if match:
        blocks_str = match.group(1)
        text_result = text[:match.start()] + text[match.end():]
        try:
            blocks = json.loads(blocks_str)
            if not isinstance(blocks, dict):
                blocks = None
        except (json.JSONDecodeError, ValueError):
            blocks = None
    return text_result.strip(), blocks or {}


def build_agent(agent_config: AgentConfig):
    settings = get_settings()
    llm = ChatOpenAI(
        model=agent_config.model_name or settings.openai_model,
        temperature=agent_config.temperature,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
    )
    return create_agent(
        model=llm,
        tools=get_tools(),
        system_prompt=agent_config.system_prompt,
        name=f"agent-{agent_config.id}",
    )


def _get_or_create_thread(db: Session, user_id: int, agent_id: int, message: str, thread_id: str | None) -> Thread:
    if thread_id:
        thread = db.scalar(select(Thread).where(Thread.id == thread_id, Thread.user_id == user_id, Thread.agent_id == agent_id))
        if not thread:
            raise HTTPException(status_code=404, detail="Thread not found.")
        return thread

    thread = Thread(id=new_thread_id(), user_id=user_id, agent_id=agent_id, title=message[:60] or "New chat")
    db.add(thread)
    db.flush()
    return thread


def ask_agent(db: Session, user_id: int, agent_id: int, message: str, thread_id: str | None = None) -> tuple[str, str, dict]:
    settings = get_settings()
    agent_config = db.scalar(select(AgentConfig).where(AgentConfig.id == agent_id, AgentConfig.user_id == user_id))
    if not agent_config:
        raise HTTPException(status_code=404, detail="Agent not found.")
    if not agent_config.enabled:
        raise HTTPException(status_code=400, detail="Agent is disabled.")

    thread = _get_or_create_thread(db, user_id, agent_id, message, thread_id)
    db.add(Message(thread_id=thread.id, role="user", content=message))
    db.flush()

    stored_messages = list(db.scalars(select(Message).where(Message.thread_id == thread.id).order_by(Message.created_at)))
    langchain_messages = [{"role": item.role, "content": item.content} for item in stored_messages if item.role in {"user", "assistant"}]

    agent = build_agent(agent_config)
    with tracing_context(
        enabled=True,
        project_name=settings.langsmith_project,
        tags=["local", "agent", "tool-calling", f"agent:{agent_config.id}"],
        metadata={"thread_id": thread.id, "user_id": user_id, "agent_id": agent_config.id},
    ):
        result = agent.invoke(
            {"messages": langchain_messages},
            config={
                "run_name": f"agent-{agent_config.id}",
                "tags": ["local", "agent", "tool-calling"],
                "metadata": {"thread_id": thread.id, "user_id": user_id, "agent_id": agent_config.id},
            },
        )
    answer_raw = result["messages"][-1].content
    answer_text, blocks = _extract_blocks(answer_raw)

    msg = Message(thread_id=thread.id, role="assistant", content=answer_text, extra={"blocks": blocks})
    db.add(msg)
    db.commit()
    return answer_text, thread.id, blocks