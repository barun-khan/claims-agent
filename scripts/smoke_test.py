"""Tool-calling smoke test.

Proves the model can call a local Python function as a tool, and shows us
where the framework records tool calls and token usage.
"""
import asyncio
import json
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


async def main():
    from agent_framework.foundry import FoundryChatClient
    from azure.identity.aio import DefaultAzureCredential

    from src.agents.tools import compute_settlement_tool

    policies = json.loads(Path("tools/policy_rules/policies.json").read_text())
    policy_id = next(iter(policies))
    print("using policy:", policy_id)
    print()

    async with DefaultAzureCredential() as cred:
        client = FoundryChatClient(credential=cred)
        agent = client.as_agent(
            name="tool-test",
            instructions="Use the settlement tool to answer. Report exactly what it returns.",
            tools=[compute_settlement_tool],
        )
        result = await agent.run(
            f"Policy {policy_id}, procedure PRC-1010, billed 15000, "
            f"service date 2024-06-14. What is the settlement?"
        )

    print("text:  ", result.text)
    print("usage: ", result.usage_details)
    print("value: ", result.value)
    print()
    print(f"messages ({len(result.messages)}):")
    for m in result.messages:
        contents = [type(c).__name__ for c in getattr(m, "contents", [])]
        print("  role:", getattr(m, "role", "?"), "| contents:", contents)


if __name__ == "__main__":
    asyncio.run(main())