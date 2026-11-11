import asyncio
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    repo = str(Path.cwd().resolve())
    params = StdioServerParameters(command="codebase-memory-mcp", args=[], env=None)

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            print("Repository:", repo)
            print("Starting full persistent Code Graph indexing...")

            result = await session.call_tool("index_repository", {
                "repo_path": repo,
                "mode": "full",
                "persistence": True,
                "async": True
            })

            for item in result.content:
                if hasattr(item, "text"):
                    print(item.text)

            print("\nChecking indexing progress...")

            for attempt in range(120):
                await asyncio.sleep(5)
                status = await session.call_tool("index_repository", {
                    "repo_path": repo,
                    "status": True
                })

                output = "\n".join(
                    item.text for item in status.content if hasattr(item, "text")
                )
                print(output)

                lowered = output.lower()
                if any(word in lowered for word in ("succeeded", "failed", "cancelled")):
                    break
            else:
                print("Polling limit reached. Indexing may still be running.")

asyncio.run(main())
