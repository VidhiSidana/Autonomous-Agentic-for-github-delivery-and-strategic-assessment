"""
Tests for AgentPlanner (Samsung PRISM Unified Engineering Agent).
"""

import unittest
from agent.planner import AgentPlanner, QueryCategory


class TestAgentPlanner(unittest.TestCase):

    def setUp(self):
        self.planner = AgentPlanner()

    def test_code_analysis_callers(self):
        plan = self.planner.plan("Find all callers of process_data in this repository.")
        self.assertEqual(plan.category, QueryCategory.CODE_ANALYSIS)
        self.assertEqual(plan.function_name, "process_data")

    def test_code_analysis_callees(self):
        plan = self.planner.plan("What functions are called by authenticate_user?")
        self.assertEqual(plan.category, QueryCategory.CODE_ANALYSIS)
        self.assertEqual(plan.function_name, "authenticate_user")

    def test_code_analysis_file_imports(self):
        plan = self.planner.plan("Which modules does agent/main.py depend on?")
        self.assertEqual(plan.category, QueryCategory.CODE_ANALYSIS)
        self.assertIn("main.py", plan.file_path or "")

    def test_binary_analysis_with_path(self):
        plan = self.planner.plan("Analyse binary sample.exe and identify its architecture.")
        self.assertEqual(plan.category, QueryCategory.BINARY_ANALYSIS)
        self.assertIn("sample.exe", plan.binary_path or "")
        self.assertFalse(plan.clarification_needed)

    def test_binary_analysis_missing_path_needs_clarification(self):
        plan = self.planner.plan("Disassemble this binary executable.")
        self.assertEqual(plan.category, QueryCategory.BINARY_ANALYSIS)
        self.assertTrue(plan.clarification_needed)
        self.assertIsNotNone(plan.clarification_question)

    def test_memory_save(self):
        plan = self.planner.plan("Remember this finding: auth is verified in auth.py. This is verified.")
        self.assertEqual(plan.category, QueryCategory.MEMORY)
        self.assertEqual(plan.memory_operation, "save")
        self.assertEqual(plan.memory_verification_status, "VERIFIED")

    def test_memory_search(self):
        plan = self.planner.plan("Search memory for sqlite performance findings.")
        self.assertEqual(plan.category, QueryCategory.MEMORY)
        self.assertEqual(plan.memory_operation, "search")
        self.assertTrue(len(plan.memory_keywords) > 0)

    def test_memory_retrieve(self):
        plan = self.planner.plan("Retrieve previous engineering findings.")
        self.assertEqual(plan.category, QueryCategory.MEMORY)
        self.assertEqual(plan.memory_operation, "retrieve")

    def test_multi_tool_routing(self):
        plan = self.planner.plan(
            "Find the authentication function in the codebase and compare with related binary functionality in app.exe"
        )
        self.assertEqual(plan.category, QueryCategory.MULTI_TOOL)
        self.assertIn("code_analysis", plan.sub_categories)
        self.assertIn("binary_analysis", plan.sub_categories)

    def test_general_query(self):
        plan = self.planner.plan("Explain what an MCP server is.")
        self.assertEqual(plan.category, QueryCategory.GENERAL)

    def test_case_preservation_binary_path(self):
        # Case preservation for binary paths on case-sensitive filesystems
        plan = self.planner.plan('Analyse binary "/Tmp/MyProj/Sample_Authorized.EXE" and identify its architecture.')
        self.assertEqual(plan.category, QueryCategory.BINARY_ANALYSIS)
        self.assertEqual(plan.binary_path, "/Tmp/MyProj/Sample_Authorized.EXE")

        plan_unquoted = self.planner.plan("Analyse binary /Tmp/MyProj/Sample_Authorized.EXE and identify its architecture.")
        self.assertEqual(plan_unquoted.binary_path, "/Tmp/MyProj/Sample_Authorized.EXE")

    def test_case_preservation_function_name(self):
        # Dotted CamelCase and mixed-case symbol names
        plan = self.planner.plan("Who calls UnifiedEngineeringAgent.process_query?")
        self.assertEqual(plan.category, QueryCategory.CODE_ANALYSIS)
        self.assertEqual(plan.function_name, "UnifiedEngineeringAgent.process_query")

    def test_case_preservation_file_path(self):
        plan = self.planner.plan("Which modules does Agent/MainModule.PY depend on?")
        self.assertEqual(plan.category, QueryCategory.CODE_ANALYSIS)
        self.assertEqual(plan.file_path, "Agent/MainModule.PY")


if __name__ == "__main__":
    unittest.main()

