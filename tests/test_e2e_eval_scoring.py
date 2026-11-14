"""
Unit tests for deterministic ground truth scoring in benchmarks/e2e_eval.py.
Validates both:
1. Tightened scoring for C1, MT1, REA1-REA3 ensuring vague/generic answers fail.
2. Negation-aware false-hypothesis benchmark scoring ensuring explicit negations are not scored as false assertions.
"""

import unittest
from benchmarks.e2e_eval import score_ground_truth


class TestFalseHypothesisScoring(unittest.TestCase):
    """Regression tests for negation-aware false-hypothesis benchmark scoring."""

    def test_fh3_explicit_negation_is_not_scored_as_false_assertion(self):
        passed, reason = score_ground_truth(
            "FH3",
            "Bottle does not use Django and does not import django.db.",
        )
        self.assertTrue(passed, reason)

    def test_fh3_affirmative_django_claim_is_rejected(self):
        passed, reason = score_ground_truth(
            "FH3",
            "Bottle uses Django and imports django.db models.",
        )
        self.assertFalse(passed)
        self.assertIn("Falsely asserted", reason)

    def test_fh1_negated_export_claim_is_not_scored_as_affirmative(self):
        passed, reason = score_ground_truth(
            "FH1",
            "The binary does not contain backdoor_payload exists as an export.",
        )
        self.assertTrue(passed, reason)

    def test_fh2_unrestricted_access_claim_is_rejected(self):
        passed, reason = score_ground_truth(
            "FH2",
            "The policy provides unrestricted access to every binary path.",
        )
        self.assertFalse(passed)
        self.assertIn("Falsely affirmed", reason)


class TestE2EEvalScoring(unittest.TestCase):
    """Test suite ensuring exact ground-truth scoring without false passes on generic words."""

    # -------------------------------------------------------------------------
    # Task C1: Function discovery
    # -------------------------------------------------------------------------
    def test_c1_generic_words_fail(self):
        """Vague responses without repository file associations must fail."""
        vague_cases = [
            "We have some functions and classes in our python code.",
            "I plan to execute_query on the main branch soon.",
            "Found functions: func1, func2, test_all.",
            "There is a main function and a plan function in the repo.",
        ]
        for resp in vague_cases:
            passed, reason = score_ground_truth("C1", resp)
            self.assertFalse(passed, f"Expected fail for '{resp}', got pass: {reason}")

    def test_c1_exact_facts_pass(self):
        """Responses with specific repository functions and file associations must pass."""
        good_cases = [
            "Found functions: agent/orchestrator.py defines process_query (line 45), agent/planner.py defines plan (line 20).",
            "Discovered functions: process_query in orchestrator.py, authorize_binary_path in policy.py.",
            "Discovered repository functions: def main() in agent/main.py, def plan() in agent/planner.py.",
        ]
        for resp in good_cases:
            passed, reason = score_ground_truth("C1", resp)
            self.assertTrue(passed, f"Expected pass for '{resp}', got fail: {reason}")

    # -------------------------------------------------------------------------
    # Task MT1: Multi-tool cross-domain query
    # -------------------------------------------------------------------------
    def test_mt1_generic_words_fail(self):
        """Responses matching only generic substrings (pe, function, code, class) must fail."""
        vague_cases = [
            "pe function code class",
            "This code has a class and a function, and we checked a binary pe header.",
            "The binary has AMD64 architecture and .text section.",  # missing code fact
            "Function process_query in agent/orchestrator.py was found.",  # missing binary fact
            "Function main in main.py, binary is a pe file.",  # missing AMD64 and .text
        ]
        for resp in vague_cases:
            passed, reason = score_ground_truth("MT1", resp)
            self.assertFalse(passed, f"Expected fail for '{resp}', got pass: {reason}")

    def test_mt1_exact_facts_pass(self):
        """Responses with both a code fact (function+file) and binary facts (AMD64 + .text) must pass."""
        good_cases = [
            "Code analysis found process_query in agent/orchestrator.py. Binary analysis verified AMD64 architecture and .text section.",
            "Authentication logic located in agent/policy.py (authorize_binary_path). Target executable app.exe has x64 machine type and .text section at RVA 0x1000.",
        ]
        for resp in good_cases:
            passed, reason = score_ground_truth("MT1", resp)
            self.assertTrue(passed, f"Expected pass for '{resp}', got fail: {reason}")

    # -------------------------------------------------------------------------
    # Task REA1: REA status and fallback
    # -------------------------------------------------------------------------
    def test_rea1_generic_words_fail(self):
        """Responses mentioning only the word 'rea' or 'fallback' must fail."""
        vague_cases = [
            "rea fallback",
            "We used the rea tool with fallback support.",
            "Checked rea status for the binary.",
        ]
        for resp in vague_cases:
            passed, reason = score_ground_truth("REA1", resp)
            self.assertFalse(passed, f"Expected fail for '{resp}', got pass: {reason}")

    def test_rea1_exact_facts_pass(self):
        """Responses with verified engine status (OPERATIONAL/PREREQUISITE_BLOCKED) and tool diagnostics must pass."""
        good_cases = [
            '{"status": "PREREQUISITE_BLOCKED", "message": "Node >= 22.23.4 and Ghidra required", "fallback_engine": "pefile/Capstone static fallback", "zero_execution_guarantee": true}',
            "REA status is OPERATIONAL, fallback_engine is pefile/Capstone static fallback on AMD64 binary.",
        ]
        for resp in good_cases:
            passed, reason = score_ground_truth("REA1", resp)
            self.assertTrue(passed, f"Expected pass for '{resp}', got fail: {reason}")

    # -------------------------------------------------------------------------
    # Task REA2: REA function analysis with fallback
    # -------------------------------------------------------------------------
    def test_rea2_generic_words_fail(self):
        """Responses mentioning generic 'function export rea' without engine status or export facts must fail."""
        vague_cases = [
            "rea function export",
            "Analyzed functions using rea fallback.",
            "Exported functions were checked.",
        ]
        for resp in vague_cases:
            passed, reason = score_ground_truth("REA2", resp)
            self.assertFalse(passed, f"Expected fail for '{resp}', got pass: {reason}")

    def test_rea2_exact_facts_pass(self):
        """Responses reporting verified engine and export table facts must pass."""
        good_cases = [
            '{"active_engine": "pefile static export fallback", "exported_functions": [], "note": "no export table found"}',
            "Function analysis used pefile fallback, verified 0 exported_functions (no export table directory_entry_export).",
            "Engine status OPERATIONAL: exported_functions listed with address_rva and ordinal.",
        ]
        for resp in good_cases:
            passed, reason = score_ground_truth("REA2", resp)
            self.assertTrue(passed, f"Expected pass for '{resp}', got fail: {reason}")

    # -------------------------------------------------------------------------
    # Task REA3: REA decompilation with fallback
    # -------------------------------------------------------------------------
    def test_rea3_generic_words_fail(self):
        """Responses with 'rea decompile fallback' without engine status or actual instructions must fail."""
        vague_cases = [
            "rea decompile fallback",
            "Disassembled the entry point with capstone fallback.",
            "Decompilation finished successfully.",
        ]
        for resp in vague_cases:
            passed, reason = score_ground_truth("REA3", resp)
            self.assertFalse(passed, f"Expected fail for '{resp}', got fail: {reason}")

    def test_rea3_exact_facts_pass(self):
        """Responses with verified engine status and disassembled machine instructions must pass."""
        good_cases = [
            '{"active_engine": "Capstone static disassembly fallback", "entry_point": "0x1000", "instructions": [{"mnemonic": "nop", "address": "0x1000"}]}',
            "Disassembly using Capstone static disassembly fallback at 0x1000: instructions nop, ret.",
            "Engine OPERATIONAL: disassembled entry point with instruction mov, sub, ret.",
        ]
        for resp in good_cases:
            passed, reason = score_ground_truth("REA3", resp)
            self.assertTrue(passed, f"Expected pass for '{resp}', got fail: {reason}")


if __name__ == "__main__":
    unittest.main()
