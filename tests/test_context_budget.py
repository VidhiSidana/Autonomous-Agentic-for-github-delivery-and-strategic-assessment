"""
Tests for Task B3: Context Budgets, Prompts, and Tool Schemas.
Covers:
  - Dynamic tool routing by category (4-8 tools per category)
  - REA compact tool subset filtering
  - Context budget management and priority compaction
  - Dropped component audit logging
  - Prompt guardrails (evidence reliance, missing evidence refusal, false-premise rejection)
"""

import unittest
from agent.context_budget import ContextBudgetManager, MODEL_BUDGETS, estimate_tokens
from agent.evidence import EvidenceBundle, EvidenceItem, EvidenceKind
from agent.tool_router import (
    ROUTER_TOOL_SCHEMAS,
    build_tool_selection_prompt,
    get_tools_for_category,
)


class TestContextBudgetAndToolRouter(unittest.TestCase):
    # ------------------------------------------------------------------
    # Tool Router Tests
    # ------------------------------------------------------------------

    def test_category_tool_filtering(self):
        # Code analysis category should only return code tools + clarification (<= 6 tools)
        code_tools = get_tools_for_category("code_analysis")
        tool_names = [t["name"] for t in code_tools]
        self.assertLessEqual(len(code_tools), 6)
        self.assertIn("find_functions", tool_names)
        self.assertIn("find_callers", tool_names)
        self.assertIn("get_file_outline", tool_names)
        self.assertNotIn("analyze_binary", tool_names)
        self.assertNotIn("search_memory", tool_names)

        # Binary analysis category: compact REA + pefile tools (<= 10 tools)
        bin_tools = get_tools_for_category("binary_analysis")
        bin_names = [t["name"] for t in bin_tools]
        self.assertLessEqual(len(bin_tools), 10)
        self.assertIn("analyze_binary", bin_names)
        self.assertIn("disassemble_binary", bin_names)
        self.assertIn("binary_overview", bin_names)
        self.assertIn("batch_decompile", bin_names)
        self.assertNotIn("find_callers", bin_names)

        # Memory category: memory tools only
        mem_tools = get_tools_for_category("memory")
        mem_names = [t["name"] for t in mem_tools]
        self.assertLessEqual(len(mem_tools), 4)
        self.assertIn("save_finding", mem_names)
        self.assertIn("search_memory", mem_names)
        self.assertNotIn("analyze_binary", mem_names)

    def test_compact_tool_selection_prompt(self):
        code_prompt = build_tool_selection_prompt("code_analysis")
        self.assertIn("find_functions", code_prompt)
        self.assertIn("find_callers", code_prompt)
        self.assertNotIn("disassemble_binary", code_prompt)
        # Verify compact prompt is under 350 tokens (far smaller than ~840 monolithic)
        self.assertLess(estimate_tokens(code_prompt), 350)

    # ------------------------------------------------------------------
    # Context Budget & Compaction Tests
    # ------------------------------------------------------------------

    def test_model_budgets_defined(self):
        self.assertIn("qwen2.5:1.5b", MODEL_BUDGETS)
        self.assertIn("phi3.5:latest", MODEL_BUDGETS)
        self.assertIn("llama3.1:8b", MODEL_BUDGETS)
        self.assertLess(
            MODEL_BUDGETS["qwen2.5:1.5b"]["context_window"],
            MODEL_BUDGETS["phi3.5:latest"]["context_window"],
        )

    def test_priority_compaction_truncates_long_detail_and_logs(self):
        mgr = ContextBudgetManager("qwen2.5:1.5b")
        bundle = EvidenceBundle(query="Examine binary sections")

        # Add a verified item with massive tool output (5000 characters)
        huge_detail = "SECTION_HEADER .text 0x1000\n" * 200
        bundle.add(EvidenceItem(
            kind=EvidenceKind.VERIFIED,
            source="pefile.analyze_binary",
            summary="PE binary header inspected",
            file_path="sample.exe",
            line_number=1,
            detail=huge_detail,
            tool_name="analyze_binary",
        ))

        compacted_text, dropped_log = mgr.compact_evidence_bundle(bundle)
        self.assertTrue(len(dropped_log) > 0)
        self.assertIn("Truncated detail", dropped_log[0])
        # Preserves essential location and summary
        self.assertIn("sample.exe:1", compacted_text)
        self.assertIn("PE binary header inspected", compacted_text)
        # Much shorter than raw 5000 chars
        self.assertLess(len(compacted_text), 2000)

    def test_guardrails_in_grounded_prompts(self):
        mgr = ContextBudgetManager("qwen2.5:1.5b")
        bundle = EvidenceBundle(query="Check for vulnerabilities")
        ctx = mgr.build_grounded_prompts("Check for vulnerabilities", bundle)

        # Rule 1: strict evidence reliance
        self.assertIn("Base your answer ONLY on the provided evidence", ctx.system_prompt)
        # Rule 2: refusal on missing evidence
        self.assertIn("INSUFFICIENT EVIDENCE", ctx.system_prompt)
        # Rule 3: reject false premises
        self.assertIn("reject the false premise", ctx.system_prompt)


if __name__ == "__main__":
    unittest.main()

