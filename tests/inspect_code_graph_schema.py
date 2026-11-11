import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    params = StdioServerParameters(command="codebase-memory-mcp", args=[], env=None)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
            for tool in result.tools:
                if tool.name in ("index_repository", "index_status", "list_projects"):
                    print(f"\n{tool.name}")
                    print(tool.input_schema)

asyncio.run(main())
