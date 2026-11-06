"""
Tests for code_analysis.code_server tools.
"""

import json
import tempfile
import unittest
from pathlib import Path

from code_analysis.code_server import (
    find_callees,
    find_callers,
    find_change_impact,
    find_classes,
    find_functions,
    find_module_relationships,
)


class TestCodeAnalysisAST(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo_dir = Path(self.temp_dir.name)

        # Create a sample Python module
        sample_code = """
import os
import sys
from pathlib import Path

class DataProcessor:
    def process_records(self, records):
        return [self.transform(r) for r in records]

    def transform(self, item):
        return str(item).upper()

def calculate_checksum(data):
    return hash(data)

def run_pipeline():
    dp = DataProcessor()
    data = dp.process_records(["alpha", "beta"])
    return calculate_checksum(data)
"""
        (self.repo_dir / "pipeline.py").write_text(sample_code, encoding="utf-8")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_find_functions(self):
        raw = find_functions(str(self.repo_dir))
        data = json.loads(raw)
        self.assertIn("items", data)
        names = [f["name"] for f in data["items"]]
        self.assertIn("calculate_checksum", names)
        self.assertIn("run_pipeline", names)

    def test_find_classes(self):
        raw = find_classes(str(self.repo_dir))
        data = json.loads(raw)
        self.assertEqual(len(data["items"]), 1)
        cls_info = data["items"][0]
        self.assertEqual(cls_info["name"], "DataProcessor")
        method_names = [m["name"] for m in cls_info["methods"]]
        self.assertIn("process_records", method_names)
        self.assertIn("transform", method_names)

    def test_find_callers(self):
        raw = find_callers(str(self.repo_dir), "calculate_checksum")
        data = json.loads(raw)
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["items"][0]["caller"], "run_pipeline")

    def test_find_callees(self):
        raw = find_callees(str(self.repo_dir), "run_pipeline")
        data = json.loads(raw)
        callee_names = [c["callee"] for c in data["items"]]
        self.assertIn("DataProcessor", callee_names)
        self.assertIn("calculate_checksum", callee_names)

    def test_find_module_relationships(self):
        raw = find_module_relationships(str(self.repo_dir), "pipeline.py")
        data = json.loads(raw)
        mods = [m["module"] for m in data["items"]]
        self.assertIn("os", mods)
        self.assertIn("sys", mods)
        self.assertIn("pathlib", mods)

    def test_find_change_impact(self):
        raw = find_change_impact(str(self.repo_dir), "calculate_checksum")
        data = json.loads(raw)
        self.assertIn("run_pipeline", data["direct_callers"])


if __name__ == "__main__":
    unittest.main()

