
import asyncio
import sys
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters


async def call_mcp_tool(tool_name, arguments, server="test"):
    """Connect to the selected MCP server and execute a tool."""

    project_root = Path(__file__).resolve().parent.parent

    if server == "code":
        server_path = (
            project_root / "code_analysis" / "code_server.py"
        )

    elif server == "binary":
        server_path = (
            project_root / "binary_analysis" / "binary_server.py"
        )

    elif server == "test":
        server_path = (
            project_root / "mcp_server" / "test_server.py"
        )

    else:
        raise ValueError(f"Unknown MCP server: {server}")

    server_params = StdioServerParameters(
        command=sys.executable,
        args=[str(server_path)]
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            result = await session.call_tool(
                tool_name,
                arguments=arguments
            )

            return result


async def main():
    print("Testing Binary Analysis MCP Server...")

    result = await call_mcp_tool(
        "analyze_binary",
        {
            "binary_path": "C:\\Windows\\System32\\notepad.exe"
        },
        server="binary"
    )

    print("\nBinary Analysis Result:")
    print(result)


if __name__ == "__main__":
    asyncio.run(main())


