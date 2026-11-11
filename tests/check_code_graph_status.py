import asyncio
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    params = StdioServerParameters(
        command="codebase-memory-mcp",
        args=[],
        env=None
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("index_repository", {
                "repo_path": str(Path.cwd().resolve()),
                "status": True
            })
            for item in result.content:
                if hasattr(item, "text"):
                    print(item.text)

asyncio.run(main())
