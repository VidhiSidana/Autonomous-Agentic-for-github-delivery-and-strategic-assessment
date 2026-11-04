"""
Tests for binary_analysis.binary_server tools.
"""

import json
import tempfile
import unittest
from pathlib import Path

from binary_analysis.binary_server import (
    analyze_binary,
    disassemble_binary,
    extract_binary_strings,
    find_binary_functions,
    find_binary_imports,
)


class TestBinaryAnalysisServer(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.bin_dir = Path(self.temp_dir.name).resolve()

        # Allow this directory for tests
        import config.settings
        self.orig_allowed = config.settings.BINARY_ALLOWED_DIRS
        config.settings.BINARY_ALLOWED_DIRS = [self.bin_dir]

    def tearDown(self):
        import config.settings
        config.settings.BINARY_ALLOWED_DIRS = self.orig_allowed
        self.temp_dir.cleanup()

    def test_reject_unauthorized_directory(self):
        raw = analyze_binary("/unauthorized/path/malware.exe")
        data = json.loads(raw)
        self.assertIn("error", data)
        self.assertIn("Denied", data["error"])

    def test_missing_file_within_allowed_dir(self):
        missing = self.bin_dir / "non_existent.exe"
        raw = analyze_binary(str(missing))
        data = json.loads(raw)
        self.assertIn("error", data)
        self.assertIn("not found", data["error"].lower())

    def test_invalid_pe_format(self):
        fake_binary = self.bin_dir / "dummy.exe"
        fake_binary.write_text("THIS IS NOT A PE BINARY", encoding="utf-8")

        raw = analyze_binary(str(fake_binary))
        data = json.loads(raw)
        self.assertIn("error", data)
        self.assertIn("Invalid or unsupported", data["error"])

    def test_extract_strings_from_sample(self):
        sample = self.bin_dir / "sample.bin"
        sample.write_bytes(b"\x00\x01\x02HelloPRISMAgent\x00\x00Version1.0.0\x00\xFF")

        raw = extract_binary_strings(str(sample), min_length=4)
        data = json.loads(raw)
        self.assertIn("strings", data)
        self.assertIn("HelloPRISMAgent", data["strings"])

    def test_query_rea_status_default(self):
        from binary_analysis.binary_server import query_rea_status
        raw = query_rea_status()
        data = json.loads(raw)
        self.assertIn("status", data)
        self.assertEqual(data["status"], "PENDING_EXTERNAL_DEPENDENCY")
        self.assertFalse(data["rea_configured"])
        self.assertTrue(data["zero_execution_guarantee"])

    def test_rea_adapter_live_invocation(self):
        import stat
        from binary_analysis.rea_adapter import REAAdapter

        # Create mock target binary
        sample_bin = self.bin_dir / "target.exe"
        sample_bin.write_bytes(b"MZ\x90\x00fake")

        # 1. Create a mock REA executable that returns valid JSON analysis
        mock_rea = self.bin_dir / "mock_rea.sh"
        mock_rea.write_text('#!/bin/sh\necho \'{"engine":"MockREA","decompiled_symbols":["sym_main","sym_auth"]}\'', encoding="utf-8")
        mock_rea.chmod(mock_rea.stat().st_mode | stat.S_IEXEC)

        adapter = REAAdapter(endpoint_or_binary=str(mock_rea))
        res = adapter.analyze(str(sample_bin), operation="metadata")
        self.assertTrue(res["success"])
        self.assertEqual(res["status"], "REA_OPERATIONAL")
        self.assertEqual(res["results"]["engine"], "MockREA")
        self.assertEqual(res["active_engine"], "REA")

        # 2. When mock REA fails
        failing_rea = self.bin_dir / "failing_rea.sh"
        failing_rea.write_text('#!/bin/sh\n>&2 echo "REA Internal Decompiler Crash"\nexit 1', encoding="utf-8")
        failing_rea.chmod(failing_rea.stat().st_mode | stat.S_IEXEC)

        adapter_fail = REAAdapter(endpoint_or_binary=str(failing_rea))
        res_fail = adapter_fail.analyze(str(sample_bin), operation="metadata")
        self.assertFalse(res_fail["success"])
        self.assertEqual(res_fail["status"], "FAILED")
        self.assertTrue(res_fail["fallback_recommended"])

    def test_failure_paths_audit_logging(self):
        from agent.policy import _get_audit_log_path
        audit_file = _get_audit_log_path()

        # Trigger denied request
        analyze_binary("/unauthorized/test.exe")

        # Trigger malformed PE
        fake_binary = self.bin_dir / "malformed.exe"
        fake_binary.write_text("NOT_A_PE", encoding="utf-8")
        find_binary_functions(str(fake_binary))
        find_binary_imports(str(fake_binary))
        disassemble_binary(str(fake_binary))

        if audit_file.exists():
            log_content = audit_file.read_text(encoding="utf-8")
            self.assertIn("DENIED", log_content)
            self.assertIn("INVALID_PE", log_content)


if __name__ == "__main__":
    unittest.main()
