"""
Multi-server MCP Client for the Samsung PRISM Unified Engineering Agent.

Improvements over the original single-function call_mcp_tool():
  - Supports multiple named MCP servers defined in config/mcp_servers.json
  - Persistent sessions per server (not a new subprocess per call)
  - Dynamic tool discovery on first connection
  - Correct MCP v2.3.0 result API (result.content[0].text)
  - Proper error handling and timeout support
  - Consistent ToolResult return type
  - Clean connect / call_tool / disconnect lifecycle
"""

import asyncio
import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

# Allow running standalone
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import MCP_CONFIG_PATH, PROJECT_ROOT

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class ToolResult:
    """
    Normalised result from an MCP tool call.

    Attributes
    ----------
    success : bool
        True if the tool returned a result without error.
    text : str
        The combined text from all TextContent blocks.
    is_error : bool
        True if the MCP server set the is_error flag.
    raw : Any
        The raw CallToolResult object for advanced inspection.
    error_message : str
        Human-readable error description (empty on success).
    """
    success: bool = False
    text: str = ""
    is_error: bool = False
    raw: Any = None
    error_message: str = ""


# ---------------------------------------------------------------------------
# Server config loading
# ---------------------------------------------------------------------------

def _load_server_configs() -> dict[str, dict]:
    """
    Load MCP server definitions from config/mcp_servers.json.
    Returns a dict keyed by logical server name.
    """
    config_path = MCP_CONFIG_PATH
    if not config_path.exists():
        logger.warning("MCP config not found at %s", config_path)
        return {}

    with open(config_path, encoding="utf-8") as fh:
        data = json.load(fh)

    return {
        name: cfg
        for name, cfg in data.get("servers", {}).items()
        if cfg.get("enabled", True)
    }


def _build_server_params(config: dict) -> StdioServerParameters:
    """
    Build StdioServerParameters from a server config dict.
    Replaces ${PYTHON} with sys.executable.
    """
    command = config["command"]
    if command == "${PYTHON}":
        command = sys.executable

    args = [
        str(PROJECT_ROOT / arg) if not Path(arg).is_absolute() else arg
        for arg in config.get("args", [])
    ]

    return StdioServerParameters(command=command, args=args)


# ---------------------------------------------------------------------------
# Client implementation
# ---------------------------------------------------------------------------

class MCPClientManager:
    """
    Manages persistent MCP sessions for multiple named servers.

    Usage (async)::

        manager = MCPClientManager()
        result = await manager.call_tool("code_fallback", "find_functions",
                                         {"directory": "/path/to/repo"})
        tools = await manager.list_tools("code_fallback")

    Sessions are opened on first use and re-used for subsequent calls.
    Call close_all() when finished.
    """

    def __init__(self) -> None:
        self._configs: dict[str, dict] = _load_server_configs()
        # Active sessions: server_name → (exit_stack_cm, session)
        self._sessions: dict[str, tuple[Any, ClientSession]] = {}
        self._tool_cache: dict[str, list[str]] = {}  # server → list of tool names

    def available_servers(self) -> list[str]:
        """Return names of all configured and enabled servers."""
        return list(self._configs.keys())

    async def _ensure_connected(self, server_name: str) -> ClientSession:
        """
        Return an open ClientSession for *server_name*, opening one if needed.
        Raises ValueError for unknown servers.
        Raises RuntimeError if the connection fails.
        """
        if server_name in self._sessions:
            return self._sessions[server_name][1]

        if server_name not in self._configs:
            raise ValueError(
                f"Unknown MCP server '{server_name}'. "
                f"Available: {list(self._configs.keys())}"
            )

        config = self._configs[server_name]
        try:
            params = _build_server_params(config)
        except Exception as exc:
            raise RuntimeError(
                f"Cannot build server params for '{server_name}': {exc}"
            ) from exc

        logger.info("Connecting to MCP server '%s'...", server_name)
        try:
            # stdio_client is an async context manager — we enter it and keep it open
            cm = stdio_client(params)
            read, write = await cm.__aenter__()
            session = ClientSession(read, write)
            await session.__aenter__()
            await session.initialize()
            self._sessions[server_name] = (cm, session)
            logger.info("Connected to MCP server '%s'.", server_name)
            return session
        except Exception as exc:
            raise RuntimeError(
                f"Failed to connect to MCP server '{server_name}': {exc}"
            ) from exc

    async def list_tools(self, server_name: str) -> list[str]:
        """
        Discover and return tool names available on *server_name*.
        Results are cached after the first call.
        """
        if server_name in self._tool_cache:
            return self._tool_cache[server_name]

        session = await self._ensure_connected(server_name)
        result = await session.list_tools()
        names = [t.name for t in result.tools]
        self._tool_cache[server_name] = names
        logger.debug("Tools on '%s': %s", server_name, names)
        return names

    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: Optional[dict] = None,
    ) -> ToolResult:
        """
        Call *tool_name* on *server_name* with *arguments*.

        Returns a ToolResult. Never raises — errors are captured in the result.
        """
        arguments = arguments or {}

        try:
            session = await self._ensure_connected(server_name)
        except (ValueError, RuntimeError) as exc:
            return ToolResult(
                success=False,
                error_message=str(exc),
            )

        try:
            raw = await session.call_tool(tool_name, arguments=arguments)
        except Exception as exc:
            return ToolResult(
                success=False,
                error_message=f"MCP tool call failed: {exc}",
            )

        # Extract text from content blocks (MCP v2.3.0 API)
        texts: list[str] = []
        for block in (raw.content or []):
            if hasattr(block, "text"):
                texts.append(block.text)

        combined_text = "\n".join(texts)
        is_error = bool(getattr(raw, "is_error", False))

        return ToolResult(
            success=not is_error,
            text=combined_text,
            is_error=is_error,
            raw=raw,
            error_message=combined_text if is_error else "",
        )

    async def disconnect(self, server_name: str) -> None:
        """Close the session for a specific server."""
        if server_name not in self._sessions:
            return
        cm, session = self._sessions.pop(server_name)
        try:
            await session.__aexit__(None, None, None)
            await cm.__aexit__(None, None, None)
            logger.info("Disconnected from MCP server '%s'.", server_name)
        except BaseException as exc:
            logger.debug("Clean shutdown notice from '%s': %s", server_name, exc)
        self._tool_cache.pop(server_name, None)

    async def close_all(self) -> None:
        """Close all open MCP sessions."""
        for name in list(self._sessions.keys()):
            await self.disconnect(name)


# ---------------------------------------------------------------------------
# Legacy compatibility shim
# ---------------------------------------------------------------------------
# The original agent/main.py called: asyncio.run(call_mcp_tool(..., server=...))
# We keep a thin shim so old call sites work during the transition.

async def call_mcp_tool(
    tool_name: str,
    arguments: dict,
    server: str = "test",
) -> ToolResult:
    """
    Legacy shim: open a one-shot MCP session, call a tool, close it.
    New code should use MCPClientManager directly.
    """
    # Map legacy server names → new names
    _legacy_map: dict[str, str] = {
        "test":   "test",
        "code":   "code_fallback",
        "binary": "binary",
    }
    resolved = _legacy_map.get(server, server)
    manager = MCPClientManager()
    try:
        result = await manager.call_tool(resolved, tool_name, arguments)
        return result
    finally:
        await manager.close_all()


# ---------------------------------------------------------------------------
# Standalone smoke test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    async def _smoke_test():
        manager = MCPClientManager()
        print("Configured servers:", manager.available_servers())

        for srv in ["test", "code_fallback"]:
            if srv not in manager.available_servers():
                print(f"Server '{srv}' not configured — skipping.")
                continue
            try:
                tools = await manager.list_tools(srv)
                print(f"\nServer '{srv}' tools: {tools}")
            except RuntimeError as e:
                print(f"Cannot connect to '{srv}': {e}")

        await manager.close_all()

    asyncio.run(_smoke_test())
