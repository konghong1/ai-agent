from __future__ import annotations

import argparse

from app.agent import ask_agent


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local LangChain agent.")
    parser.add_argument("message", nargs="*", help="Message to send to the agent.")
    args = parser.parse_args()

    if args.message:
        print(ask_agent(" ".join(args.message)))
        return

    print("Local LangChain Agent. Type exit to quit.")
    while True:
        message = input("> ").strip()
        if message.lower() in {"exit", "quit"}:
            break
        if not message:
            continue
        print(ask_agent(message))


if __name__ == "__main__":
    main()
