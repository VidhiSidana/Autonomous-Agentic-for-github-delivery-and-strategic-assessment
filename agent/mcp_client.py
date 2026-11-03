
import asyncio
from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters


class MCPClient:

    def __init__(self):
        self.session = None
        self.exit_stack = None

    async def connect_to_server(self, command, args):
        """
        Connect to an MCP server using stdio.
        """

        server_params = StdioServerParameters(
            command=command,
            args=args
        )

        self.exit_stack = stdio_client(server_params)

        read, write = await self.exit_stack.__aenter__()

        self.session = ClientSession(read, write)

        await self.session.__aenter__()

        await self.session.initialize()

        print("Connected to MCP server successfully!")

    async def list_tools(self):
        """
        Retrieve the available tools from the MCP server.
        """

        if self.session is None:
            print("Not connected to an MCP server.")
            return []

        result = await self.session.list_tools()

        print("\nAvailable MCP Tools:")

        for tool in result.tools:
            print(f"- {tool.name}: {tool.description}")

        return result.tools

    async def disconnect(self):
        """
        Disconnect from the MCP server.
        """

        if self.exit_stack is not None:
            await self.exit_stack.__aexit__(None, None, None)

        self.session = None
        self.exit_stack = None

        print("Disconnected from MCP server.")


if __name__ == "__main__":
    print("MCP Client module loaded successfully!")
