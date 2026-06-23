from __future__ import annotations

import argparse

from app.agent import build_agent
from app.models import AgentConfig
from app.services import DEFAULT_SYSTEM_PROMPT
from app.settings import get_settings


def ask_cli_agent(message: str) -> str:
    settings = get_settings()
    agent_config = AgentConfig(
        id=0,
        user_id=0,
        name="CLI Agent",
        description="",
        system_prompt=DEFAULT_SYSTEM_PROMPT,
        model_name=settings.openai_model,
        temperature=0,
        enabled=True,
    )
    agent = build_agent(agent_config)
    result = agent.invoke({"messages": [{"role": "user", "content": message}]})
    return result["messages"][-1].content


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local LangChain agent.")
    parser.add_argument("message", nargs="*", help="Message to send to the agent.")
    args = parser.parse_args()

    if args.message:
        print(ask_cli_agent(" ".join(args.message)))
        return

    print("Local LangChain Agent. Type exit to quit.")
    while True:
        message = input("> ").strip()
        if message.lower() in {"exit", "quit"}:
            break
        if not message:
            continue
        print(ask_cli_agent(message))


if __name__ == "__main__":
    main()
