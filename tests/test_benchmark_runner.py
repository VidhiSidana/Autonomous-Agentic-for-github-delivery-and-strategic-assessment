
"""
tests/test_benchmark_runner.py

Validates that benchmarks/benchmark_runner.py is cleanly importable,
callable as a function, and returns the expected summary dictionary
without exiting the process or leaking connections.
"""

import asyncio
import tempfile
import os
import unittest
from pathlib import Path

from benchmarks.benchmark_runner import (
    run_benchmarks,
    run_cross_process_persistence_test,
    _contains_expected_policy_result,
)


class TestBenchmarkRunner(unittest.TestCase):

    def test_policy_result_matching_is_case_insensitive(self):
        """Policy wording such as 'Access denied' must satisfy 'Denied'."""
        class Evidence:
            detail = "Access denied: path is outside the approved directory."
            summary = "Binary analysis denied by policy."

        self.assertTrue(
            _contains_expected_policy_result(
                "Denied", [Evidence()], "The requested operation was blocked."
            )
        )

    def test_policy_result_matching_checks_response_text(self):
        """Policy outcomes may be surfaced in the user-facing response."""
        self.assertTrue(
            _contains_expected_policy_result(
                "Denied", [], "Access denied by security policy."
            )
        )

    def test_cross_process_persistence_isolated(self):
        """Verify cross-process persistence works cleanly on a temporary DB."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_db = Path(tmp_dir) / "test_cross_proc.db"
            result = run_cross_process_persistence_test(temp_db)

            self.assertTrue(result["success"])
            self.assertEqual(result["process_a_exit"], 0)
            self.assertEqual(result["process_b_exit"], 0)
            self.assertIsNotNone(result.get("record_id"))
            self.assertIsNotNone(result.get("session_id"))
            self.assertTrue(result.get("id_matched"))
            self.assertTrue(result.get("session_verified"))
            self.assertTrue(result["content_verified"])
            self.assertTrue(result["status_verified"])

    def test_cross_process_persistence_handles_subprocess_failure_cleanly(self):
        """Verify subprocess failure does not raise an unhandled exception."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            bad_db = Path(tmp_dir)
            result = run_cross_process_persistence_test(bad_db)

            self.assertIsInstance(result, dict)
            self.assertFalse(result["success"])
            self.assertTrue(len(result["reasons"]) > 0)

    @unittest.skipUnless(
        os.getenv("RUN_FULL_BENCHMARK") == "1",
        "Full benchmark integration test; set RUN_FULL_BENCHMARK=1 to run."
    )
    def test_run_benchmarks_returns_summary(self):
        """Verify the complete benchmark suite and report."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_dir = Path(tmp_dir)
            summary = asyncio.run(run_benchmarks(output_dir=out_dir))

            self.assertIsInstance(summary, dict)
            self.assertEqual(summary["total_tasks"], 17)
            self.assertEqual(summary["passed_tasks"], 17)
            self.assertEqual(summary["success_rate"], "100.0%")
            self.assertTrue(summary["cross_process_persistence"]["success"])

            report_file = out_dir / "benchmark_report.json"
            self.assertTrue(report_file.exists())


if __name__ == "__main__":
    unittest.main()
