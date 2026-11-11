"""
Tests for MCPClientManager.
"""

import unittest
from unittest.mock import AsyncMock, patch

from agent.mcp_client import MCPClientManager

class TestMCPClient(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.manager = MCPClientManager()

    async def asyncTearDown(self):
        await self.manager.close_all()

    async def test_available_servers(self):
        servers = self.manager.available_servers()
        self.assertIn("test", servers)
        self.assertIn("code_fallback", servers)
        self.assertIn("binary", servers)

    async def test_call_test_server_tool(self):
        result = await self.manager.call_tool("test", "get_project_info")
        self.assertTrue(result.success)
        self.assertIn("Unified Engineering Agent", result.text)

    async def test_call_addition_tool(self):
        result = await self.manager.call_tool("test", "add_numbers", {"a": 15, "b": 27})
        self.assertTrue(result.success)
        self.assertIn("42", result.text)

    async def test_list_tools_with_schemas(self):
        schemas = await self.manager.list_tools_with_schemas("test")
        self.assertIn("add_numbers", schemas)
        add_schema = schemas["add_numbers"]
        self.assertIn("inputSchema", add_schema)
        self.assertIn("properties", add_schema["inputSchema"])
        self.assertIn("a", add_schema["inputSchema"]["properties"])
        self.assertIn("b", add_schema["inputSchema"]["properties"])

    async def test_argument_validation_missing_required(self):
        # Tool 'add_numbers' requires 'a' and 'b'
        await self.manager.list_tools_with_schemas("test")
        result = await self.manager.call_tool("test", "add_numbers", {"a": 10})
        self.assertFalse(result.success)
        self.assertTrue(result.is_error)
        self.assertIn("Dynamic schema validation failed", result.error_message)
        self.assertIn("Missing required parameter 'b'", result.error_message)

    async def test_argument_validation_wrong_type(self):
        # 'a' must be integer
        await self.manager.list_tools_with_schemas("test")
        result = await self.manager.call_tool("test", "add_numbers", {"a": "not_an_int", "b": 20})
        self.assertFalse(result.success)
        self.assertTrue(result.is_error)
        self.assertIn("must be integer", result.error_message)

    async def test_verify_all_configured_servers_independently(self):
        # 1. Test server
        t_res = await self.manager.call_tool("test", "get_project_info")
        self.assertTrue(t_res.success)

        # 2. Code fallback server
        c_res = await self.manager.call_tool("code_fallback", "find_functions", {"directory": "."})
        self.assertTrue(c_res.success)
        self.assertIn("find_functions", c_res.text)

        # 3. Binary analysis server (query status/disassembly rejection)
        b_res = await self.manager.call_tool("binary", "analyze_binary", {"binary_path": "/invalid/path.exe"})
        self.assertFalse(b_res.success)
        self.assertTrue(b_res.is_error)
        self.assertIn("denied by policy", b_res.error_message.lower())

    async def test_binary_call_without_path_is_rejected_before_connection(self):
        with patch.object(
            self.manager,
            "_ensure_connected",
            new_callable=AsyncMock,
        ) as mock_connect:

            result = await self.manager.call_tool(
                "binary",
                "analyze_binary",
                {},
            )

        self.assertFalse(result.success)
        self.assertTrue(result.is_error)
        self.assertIn("binary_path is required", result.error_message)
        mock_connect.assert_not_awaited()

    async def test_unauthorized_binary_path_is_rejected_before_connection(self):
        with patch.object(
            self.manager,
            "_ensure_connected",
            new_callable=AsyncMock,
        ) as mock_connect:

            result = await self.manager.call_tool(
                "binary",
                "analyze_binary",
                {"binary_path": "/invalid/path.exe"},
            )

        self.assertFalse(result.success)
        self.assertTrue(result.is_error)
        self.assertIn("denied by policy", result.error_message.lower())
        mock_connect.assert_not_awaited()

    async def test_unauthorized_rea_call_is_rejected_before_connection(self):
        with patch(
            "agent.mcp_client.authorize_rea_tool_call",
            return_value=(False, "Access Denied by Policy: test rejection"),
        ):
            with patch.object(
                self.manager,
                "_ensure_connected",
                new_callable=AsyncMock,
            ) as mock_connect:

                result = await self.manager.call_tool(
                    "rea",
                    "decompile",
                    {"binary_path": "/invalid/sample.exe"},
                )

        self.assertFalse(result.success)
        self.assertTrue(result.is_error)
        self.assertIn("Access Denied", result.error_message)
        mock_connect.assert_not_awaited()
if __name__ == "__main__":
    unittest.main()

