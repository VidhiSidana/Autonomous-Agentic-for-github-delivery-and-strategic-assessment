"""
Tests for AgentOrchestrator and end-to-end routing.
"""

import tempfile
import unittest
from pathlib import Path

from agent.orchestrator import AgentOrchestrator
from memory.memory import EngineeringMemory
from memory.session_manager import SessionManager


class TestOrchestrator(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_agent.db"
        self.memory = EngineeringMemory(db_path=self.db_path)
        self.session_mgr = SessionManager(db_path=self.db_path)
        self.orchestrator = AgentOrchestrator(
            memory=self.memory,
            session_manager=self.session_mgr,
            default_repo_dir=Path(__file__).resolve().parent.parent,
        )

    async def asyncTearDown(self):
        await self.orchestrator.close()
        self.temp_dir.cleanup()

    async def test_code_analysis_routing_and_evidence(self):
        result = await self.orchestrator.process_query("Find all callers of process_query")
        self.assertEqual(result.category, "code_analysis")
        self.assertTrue(len(result.evidence_bundle.items) > 0)
        item = result.evidence_bundle.items[0]
        self.assertIn(item.tool_name, ("find_callers", "search_graph", "trace_path (inbound)"))

    async def test_memory_save_and_retrieve_flow(self):
        # 1. Save memory
        res1 = await self.orchestrator.process_query(
            "Remember this finding: authentication is handled in auth_service.py. This is verified."
        )
        self.assertEqual(res1.category, "memory")
        self.assertTrue(len(self.memory.retrieve_memory()) > 0)

        # 2. Search/Retrieve memory
        res2 = await self.orchestrator.process_query(
            "What did we discover about authentication in previous session?"
        )
        self.assertEqual(res2.category, "memory")
        self.assertTrue(len(res2.evidence_bundle.items) > 0)
        self.assertIn("auth_service.py", res2.evidence_bundle.items[0].detail)

    async def test_binary_analysis_clarification_on_missing_path(self):
        result = await self.orchestrator.process_query("Disassemble this binary executable.")
        self.assertEqual(result.category, "binary_analysis")
        self.assertTrue(result.clarification_needed)
        self.assertIn("path to the binary", result.clarification_question.lower())


if __name__ == "__main__":
    unittest.main()

