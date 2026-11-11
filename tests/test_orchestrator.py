"""
Tests for AgentOrchestrator and end-to-end routing.
"""

import tempfile
import unittest
from pathlib import Path

from agent.orchestrator import AgentOrchestrator
from agent.planner import AgentPlanner
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

    def test_architecture_tool_does_not_preempt_function_inventory(self):
        plan = AgentPlanner().plan("Find functions in this codebase")
        self.assertFalse(
            self.orchestrator._should_use_architecture_tool(
                plan, plan.raw_query.lower()
            )
        )

    def test_architecture_tool_does_not_preempt_module_dependencies(self):
        plan = AgentPlanner().plan(
            "Which modules does agent/main.py depend on?"
        )
        self.assertEqual(plan.file_path, "agent/main.py")
        self.assertFalse(
            self.orchestrator._should_use_architecture_tool(
                plan, plan.raw_query.lower()
            )
        )

    async def test_function_inventory_uses_ast_fallback(self):
        result = await self.orchestrator.process_query(
            "Find functions in this codebase"
        )
        self.assertEqual(result.category, "code_analysis")
        self.assertTrue(
            any(
                "find_functions" in (item.tool_name or "")
                for item in result.evidence_bundle.items
            ),
            [
                (item.tool_name, item.source, item.summary)
                for item in result.evidence_bundle.items
            ],
        )

    async def test_module_dependencies_use_ast_fallback(self):
        result = await self.orchestrator.process_query(
            "Which modules does agent/main.py depend on?"
        )
        self.assertEqual(result.category, "code_analysis")
        self.assertTrue(
            any(
                "find_module_relationships" in (item.tool_name or "")
                for item in result.evidence_bundle.items
            ),
            [
                (item.tool_name, item.source, item.summary)
                for item in result.evidence_bundle.items
            ],
        )

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

    async def test_unlabelled_memory_save_requires_confirmation(self):
        result = await self.orchestrator.process_query(
            "Remember this finding: the payment service may use a retry queue."
        )
        self.assertEqual(result.category, "memory")

        facts = self.memory.retrieve_memory()
        proposals = self.memory.get_pending_proposals()

        self.assertEqual(len(facts), 0)
        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0]["verification_status"], "PROPOSED")

    async def test_binary_analysis_clarification_on_missing_path(self):
        result = await self.orchestrator.process_query("Disassemble this binary executable.")
        self.assertEqual(result.category, "binary_analysis")
        self.assertTrue(result.clarification_needed)
        self.assertIn("path to the binary", result.clarification_question.lower())

    def test_dynamic_tool_matching_and_schema_validation(self):
        """Verify dynamic tool intent matching and argument validation."""
        mock_tools = {
            "search_graph": {
                "description": "Find symbols via BM25 query, regex name/qn filters, or semantic_query",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "project": {"type": "string"},
                        "query": {"type": "string"},
                    },
                    "required": ["project"],
                },
            },
            "trace_path": {
                "description": "Trace callers/callees, data flow, or cross-service paths.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "project": {"type": "string"},
                        "function_name": {"type": "string"},
                        "direction": {"type": "string"},
                    },
                    "required": ["project", "function_name"],
                },
            },
        }

        # 1. Test tool matching by intent
        matched_search = self.orchestrator._find_compatible_tool(mock_tools, "symbol_search")
        self.assertIsNotNone(matched_search)
        self.assertEqual(matched_search[0], "search_graph")

        matched_trace = self.orchestrator._find_compatible_tool(mock_tools, "trace_callers")
        self.assertIsNotNone(matched_trace)
        self.assertEqual(matched_trace[0], "trace_path")

        # 2. Test argument construction and validation
        valid, args, err = self.orchestrator._build_and_validate_tool_args(
            tool_name="trace_path",
            schema=mock_tools["trace_path"]["inputSchema"],
            project_name="my_proj",
            symbol_or_query="my_fn",
            direction="inbound",
        )
        self.assertTrue(valid)
        self.assertEqual(args["project"], "my_proj")
        self.assertEqual(args["function_name"], "my_fn")
        self.assertEqual(args["direction"], "inbound")

        # 3. Test missing required argument detection
        invalid, _, err_msg = self.orchestrator._build_and_validate_tool_args(
            tool_name="trace_path",
            schema=mock_tools["trace_path"]["inputSchema"],
            project_name="my_proj",
            symbol_or_query=None,  # missing required function_name
        )
        self.assertFalse(invalid)
        self.assertIn("missing required", err_msg.lower())


if __name__ == "__main__":
    unittest.main()

