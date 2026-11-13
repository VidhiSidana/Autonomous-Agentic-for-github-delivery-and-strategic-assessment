"""
Tests for AgentOrchestrator and end-to-end routing.
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from agent.evidence import EvidenceBundle
from agent.orchestrator import AgentOrchestrator
from agent.planner import AgentPlanner, QueryCategory, QueryPlan
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

    async def test_binary_path_override_resolves_clarification(self):
        """A supplied CLI path override must clear stale planner clarification."""
        binary_path = str(
            Path(self.temp_dir.name) / "sample_authorized.exe"
        )

        with patch.object(
            self.orchestrator,
            "_handle_binary_analysis",
            new_callable=AsyncMock,
        ) as mock_binary, patch.object(
            self.orchestrator,
            "_generate_response",
            new_callable=AsyncMock,
            return_value="Static binary analysis response.",
        ):
            result = await self.orchestrator.process_query(
                "Disassemble this binary executable.",
                overrides={"binary_path": binary_path},
            )

        self.assertEqual(result.category, "binary_analysis")
        self.assertFalse(result.clarification_needed)
        self.assertIsNone(result.clarification_question)
        self.assertEqual(result.plan.binary_path, binary_path)
        mock_binary.assert_awaited_once()

    async def test_unauthorized_binary_path_is_rejected_before_mcp_call(self):
        """A denied binary path must never reach an MCP analysis tool."""
        plan = QueryPlan(
            category=QueryCategory.BINARY_ANALYSIS,
            raw_query="Disassemble an unauthorized executable",
            binary_path=str(Path(self.temp_dir.name) / "outside" / "sample.exe"),
            binary_operation="disassemble",
        )
        bundle = EvidenceBundle(query=plan.raw_query)

        with patch(
            "agent.orchestrator.authorize_binary_path",
            return_value=(False, "Path is outside configured allowlist."),
        ), patch.object(
            self.orchestrator.mcp,
            "call_tool",
            new_callable=AsyncMock,
        ) as mock_call:
            await self.orchestrator._handle_binary_analysis(plan, bundle)

        mock_call.assert_not_awaited()
        self.assertTrue(
            any(
                "denied by policy" in limitation.lower()
                for limitation in bundle.limitations
            ),
            bundle.limitations,
        )

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


    async def test_file_outline_and_source_snippet_use_code_graph(self):
        """A file explanation retrieves its outline and source snippets."""
        import json
        from agent.mcp_client import ToolResult

        repo = Path(self.temp_dir.name)
        source_file = repo / "agent" / "sample.py"
        source_file.parent.mkdir(parents=True)
        source_file.write_text(
            "class SampleService:\n    def run(self):\n        return True\n",
            encoding="utf-8",
        )

        tools = {
            "get_file_outline": {
                "description": "Get symbols and outline for a source file",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "project": {"type": "string"},
                        "file_path": {"type": "string"},
                        "format": {"type": "string"},
                    },
                    "required": ["project", "file_path"],
                },
            },
            "get_code_snippet": {
                "description": "Retrieve source code for a qualified symbol",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "project": {"type": "string"},
                        "qualified_name": {"type": "string"},
                        "source_mode": {"type": "string"},
                        "member_limit": {"type": "integer"},
                        "max_output_tokens": {"type": "integer"},
                    },
                    "required": ["project", "qualified_name"],
                },
            },
        }

        outline_text = json.dumps({
            "file_path": "agent/sample.py",
            "cols": ["name", "label", "lines", "qn"],
            "rows": [
                [
                    "SampleService",
                    "Class",
                    "1-3",
                    "agent.sample.SampleService",
                ]
            ],
            "total": 1,
            "returned": 1,
        })

        snippet_text = json.dumps({
            "qualified_name": "agent.sample.SampleService",
            "code": "class SampleService:\n    def run(self):\n        return True",
        })

        calls = []

        async def fake_call_tool(server, name, args, session_id):
            calls.append((server, name, args))

            if name == "get_file_outline":
                return ToolResult(success=True, text=outline_text)

            if name == "get_code_snippet":
                return ToolResult(success=True, text=snippet_text)

            self.fail(f"Unexpected MCP tool call: {name}")

        plan = QueryPlan(
            category=QueryCategory.CODE_ANALYSIS,
            raw_query="Explain the responsibilities in agent/sample.py",
            file_path="agent/sample.py",
            repository_path=str(repo),
        )
        bundle = EvidenceBundle(query=plan.raw_query)

        with patch.object(
            self.orchestrator,
            "_resolve_code_graph_project",
            new_callable=AsyncMock,
            return_value="test-project",
        ), patch.object(
            self.orchestrator.mcp,
            "list_tools_with_schemas",
            new_callable=AsyncMock,
            return_value=tools,
        ), patch.object(
            self.orchestrator.mcp,
            "call_tool",
            new_callable=AsyncMock,
            side_effect=fake_call_tool,
        ):
            await self.orchestrator._handle_code_analysis(plan, bundle)

        called_names = [call[1] for call in calls]

        self.assertIn("get_file_outline", called_names)
        self.assertIn("get_code_snippet", called_names)

        verified_items = [
            item for item in bundle.items
            if item.kind.value == "VERIFIED"
        ]

        self.assertTrue(
            any(item.tool_name == "get_file_outline" for item in verified_items)
        )
        self.assertTrue(
            any(item.tool_name == "get_code_snippet" for item in verified_items)
        )

        snippet_call = next(
            call for call in calls
            if call[1] == "get_code_snippet"
        )
        self.assertEqual(
            snippet_call[2]["qualified_name"],
            "agent.sample.SampleService",
        )

    async def test_file_retrieval_rejects_path_outside_repository(self):
        """A traversal path must never reach Code Graph file tools."""
        repo = Path(self.temp_dir.name)

        tools = {
            "get_file_outline": {
                "description": "Get symbols and outline for a source file",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "project": {"type": "string"},
                        "file_path": {"type": "string"},
                        "format": {"type": "string"},
                    },
                    "required": ["project", "file_path"],
                },
            },
            "get_code_snippet": {
                "description": "Retrieve source code for a qualified symbol",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "project": {"type": "string"},
                        "qualified_name": {"type": "string"},
                    },
                    "required": ["project", "qualified_name"],
                },
            },
        }

        plan = QueryPlan(
            category=QueryCategory.CODE_ANALYSIS,
            raw_query="Show the outline and source for ../outside.py",
            file_path="../outside.py",
            repository_path=str(repo),
        )
        bundle = EvidenceBundle(query=plan.raw_query)

        with patch.object(
            self.orchestrator,
            "_resolve_code_graph_project",
            new_callable=AsyncMock,
            return_value="test-project",
        ), patch.object(
            self.orchestrator.mcp,
            "list_tools_with_schemas",
            new_callable=AsyncMock,
            return_value=tools,
        ), patch.object(
            self.orchestrator.mcp,
            "call_tool",
            new_callable=AsyncMock,
        ) as mock_call:
            await self.orchestrator._handle_code_analysis(plan, bundle)

        file_tool_calls = [
            call for call in mock_call.await_args_list
            if call.args[1] in ("get_file_outline", "get_code_snippet")
        ]

        self.assertEqual(file_tool_calls, [])
        self.assertTrue(
            any(
                "file retrieval rejected" in limitation.lower()
                for limitation in bundle.limitations
            ),
            bundle.limitations,
        )

if __name__ == "__main__":
    unittest.main()
