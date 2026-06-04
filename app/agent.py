from __future__ import annotations

from uuid import uuid4

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langsmith import tracing_context

from app.settings import get_settings
from app.tools import get_tools


SYSTEM_PROMPT = """You are a practical local AI agent.
You can answer normally and call tools when they help.
You must call current_time for questions about the current time.
You must call calculator for arithmetic instead of calculating mentally.
Use the workspace tools only for files inside this project.
When a tool result is enough, summarize it clearly in Chinese unless the user asks for another language.
"""


def build_agent():
    settings = get_settings()
    llm = ChatOpenAI(
        model=settings.openai_model,
        temperature=0,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
    )
    return create_agent(
        model=llm,
        tools=get_tools(),
        system_prompt=SYSTEM_PROMPT,
        name="local-langchain-agent",
    )


def ask_agent(message: str, thread_id: str | None = None) -> str:
    settings = get_settings()
    agent = build_agent()
    thread_id = thread_id or f"local-{uuid4()}"
    with tracing_context(
        enabled=True,
        project_name=settings.langsmith_project,
        tags=["local", "agent", "tool-calling"],
        metadata={"thread_id": thread_id},
    ):
        result = agent.invoke(
            {"messages": [{"role": "user", "content": message}]},
            config={
                "run_name": "local-langchain-agent",
                "tags": ["local", "agent", "tool-calling"],
                "metadata": {"thread_id": thread_id},
            },
        )
    return result["messages"][-1].content
