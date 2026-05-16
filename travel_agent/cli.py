import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from travel_agent.config import Config, ConfigError, setup_logging
from travel_agent.setup import build_agent


async def main() -> int:
    setup_logging()
    try:
        Config.validate()
    except ConfigError as e:
        print(f"Configuration error: {e}")
        return 1

    agent = build_agent()
    if agent is None:
        print("Failed to build agent (no LLM key?). See logs.")
        return 1

    print("Travel Agent ready. Type 'quit' to exit.")
    while True:
        try:
            user_input = input("\nYou: ")
        except KeyboardInterrupt:
            break
        if user_input.lower() in ("quit", "exit"):
            break
        async for event in agent.run_generator(user_input):
            kind = event["type"]
            if kind == "message":
                print(f"Agent: {event['content']}")
            elif kind == "tool_call":
                print(f"-> {event['name']}({event['arguments']})")
            elif kind == "tool_result":
                print(f"<- {event['content']}")
            elif kind == "error":
                print(f"!! {event['content']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
