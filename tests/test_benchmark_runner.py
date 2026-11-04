"""
tests/test_benchmark_runner.py

Validates that benchmarks/benchmark_runner.py is cleanly importable,
callable as a function, and returns the expected summary dictionary
without exiting the process or leaking connections.
"""

import asyncio
import tempfile
import unittest
from pathlib import Path

from benchmarks.benchmark_runner import run_benchmarks, run_cross_process_persistence_test


class TestBenchmarkRunner(unittest.TestCase):

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
        # Using a directory as db_path will cause SQLite / process to report failure cleanly
        with tempfile.TemporaryDirectory() as tmp_dir:
            bad_db = Path(tmp_dir)  # is a directory, not a file
            result = run_cross_process_persistence_test(bad_db)
            self.assertIsInstance(result, dict)
            self.assertFalse(result["success"])
            self.assertTrue(len(result["reasons"]) > 0)

    def test_run_benchmarks_returns_summary(self):
        """Verify run_benchmarks() returns the structured summary dict."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_dir = Path(tmp_dir)
            summary = asyncio.run(run_benchmarks(output_dir=out_dir))

            self.assertIsInstance(summary, dict)
            self.assertIn("total_tasks", summary)
            self.assertIn("passed_tasks", summary)
            self.assertIn("success_rate", summary)
            self.assertIn("results", summary)
            self.assertIn("cross_process_persistence", summary)

            self.assertEqual(summary["total_tasks"], 14)
            self.assertEqual(summary["passed_tasks"], 14)
            self.assertEqual(summary["success_rate"], "100.0%")
            self.assertTrue(summary["cross_process_persistence"]["success"])

            # Verify report file was written
            report_file = out_dir / "benchmark_report.json"
            self.assertTrue(report_file.exists())


if __name__ == "__main__":
    unittest.main()
