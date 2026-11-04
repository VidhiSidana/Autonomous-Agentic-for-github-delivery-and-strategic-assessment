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


if __name__ == "__main__":
    unittest.main()
