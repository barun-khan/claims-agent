"""Minimal connectivity check. Proves auth, endpoint, and deployment name
are correct before any agent code exists."""
import asyncio, os
from dotenv import load_dotenv

load_dotenv()


async def main():
    from agent_framework.foundry import FoundryChatClient
    from azure.identity.aio import DefaultAzureCredential

    print("endpoint:  ", os.environ["FOUNDRY_PROJECT_ENDPOINT"])
    print("deployment:", os.environ["FOUNDRY_MODEL"])
    print()

    async with DefaultAzureCredential() as cred:
        client = FoundryChatClient(credential=cred)
        agent = client.as_agent(
            name="smoke-test",
            instructions="Reply with exactly one word.",
        )
        result = await agent.run("Say the word: connected")
        print("response:", result)


if __name__ == "__main__":
    asyncio.run(main())
