
from mcp.server.mcpserver import MCPServer

# Create an MCP server
mcp = MCPServer("Engineering Test Server")


@mcp.tool()
def get_project_info() -> str:
    """Return basic information about the engineering agent project."""
    return (
        "Project: Unified Engineering Agent\n"
        "Purpose: Code comprehension, binary investigation, "
        "and persistent engineering memory."
    )


@mcp.tool()
def add_numbers(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b


if __name__ == "__main__":
    mcp.run()
