"""
Tests for MCPClientManager.
"""

import unittest
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


if __name__ == "__main__":
    unittest.main()

