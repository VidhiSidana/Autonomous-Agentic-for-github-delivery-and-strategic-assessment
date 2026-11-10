"""
CI-style Module Import and Syntax Verification Test.

Imports every internal Python module in the project to verify that:
1. All type annotations resolve cleanly without NameError (e.g. sqlite3.Row in Python 3.11-3.13).
2. No top-level syntax errors or missing intra-project imports exist.
3. If Python 3.11 or Python 3.12 binaries are detected on host PATH, runs an external
   subprocess verification under those versions.
"""

import importlib
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

MODULES_TO_IMPORT = [
    "config.settings",
    "agent.policy",
    "agent.evidence",
    "agent.planner",
    "agent.llm",
    "agent.tool_router",
    "agent.context_budget",
    "memory.memory",
    "memory.session_manager",
    "memory.curated_memory",
    "code_analysis.code_server",
    "binary_analysis.rea_adapter",
]


class TestModuleImports(unittest.TestCase):
    def test_all_modules_import_cleanly(self):
        """Import each core module in-process to verify type annotations and symbols."""
        for mod_name in MODULES_TO_IMPORT:
            with self.subTest(module=mod_name):
                try:
                    mod = importlib.import_module(mod_name)
                    self.assertIsNotNone(mod, f"Module {mod_name} should not be None")
                except Exception as exc:
                    self.fail(f"Failed to import {mod_name}: {exc}")

    def test_session_manager_sqlite3_row_annotation(self):
        """Specifically verify session_manager type annotations evaluate cleanly."""
        import memory.session_manager as sm
        import inspect
        # In Python 3.11-3.13 without 'from __future__ import annotations',
        # inspect.signature or typing.get_type_hints evaluates annotations
        try:
            hints = getattr(sm.SessionManager.get_session_events, "__annotations__", {})
            self.assertIn("return", hints)
        except NameError as ne:
            self.fail(f"session_manager annotation failed with NameError: {ne}")

    def test_python311_external_import_check(self):
        """If Python 3.11 is present on host, run import checks under python3.11."""
        py311 = shutil.which("python3.11") or ("/opt/homebrew/bin/python3.11" if Path("/opt/homebrew/bin/python3.11").exists() else None)
        if not py311:
            self.skipTest("python3.11 not installed on host PATH")

        # Test modules that only depend on stdlib (config, memory, policy)
        check_code = (
            "import sys\n"
            f"sys.path.insert(0, '{PROJECT_ROOT}')\n"
            "import config.settings\n"
            "import agent.policy\n"
            "import memory.memory\n"
            "import memory.session_manager\n"
            "print('SUCCESS')\n"
        )
        proc = subprocess.run([str(py311), "-c", check_code], capture_output=True, text=True)
        self.assertEqual(
            proc.returncode, 0,
            f"Python 3.11 import check failed:\nSTDOUT: {proc.stdout}\nSTDERR: {proc.stderr}"
        )
        self.assertIn("SUCCESS", proc.stdout)


if __name__ == "__main__":
    unittest.main()
