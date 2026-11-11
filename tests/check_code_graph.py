import asyncio
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
            result = await session.list_tools()
            print("SERVER STARTED SUCCESSFULLY")
            print("AVAILABLE TOOLS:")
            for tool in result.tools:
                print("-", tool.name, ":", tool.description)

asyncio.run(main())
