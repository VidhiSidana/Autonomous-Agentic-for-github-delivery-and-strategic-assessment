"""
Tests for EngineeringMemory and SessionManager (Samsung PRISM).
"""

import tempfile
import unittest
from pathlib import Path

from memory.memory import EngineeringMemory, STATUS_HYPOTHESIS, STATUS_VERIFIED
from memory.session_manager import SessionManager


class TestEngineeringMemory(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_memory.db"
        self.memory = EngineeringMemory(db_path=self.db_path)
        self.session_mgr = SessionManager(db_path=self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_save_and_retrieve_memory(self):
        res = self.memory.save_memory(
            title="Database index optimization",
            content="Added B-tree index on findings(created_at) for faster queries.",
            category="technical_finding",
            verification_status=STATUS_VERIFIED,
            source="benchmark evaluation",
        )
        self.assertTrue(res["saved"])
        self.assertIn("id", res)

        retrieved = self.memory.retrieve_memory()
        self.assertEqual(len(retrieved), 1)
        row = dict(retrieved[0])
        self.assertEqual(row["title"], "Database index optimization")
        self.assertEqual(row["verification_status"], STATUS_VERIFIED)

    def test_search_memory(self):
        self.memory.save_memory(title="PE Section Analysis", content="Sections have high entropy.")
        self.memory.save_memory(title="Python AST Callers", content="Recursive AST walker implemented.")

        matches = self.memory.search_memory("entropy")
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["title"], "PE Section Analysis")

    def test_duplicate_detection(self):
        res1 = self.memory.save_memory(title="Unique Symbol", content="Details A")
        self.assertTrue(res1["saved"])

        res2 = self.memory.save_memory(title="Unique Symbol", content="Details B")
        self.assertFalse(res2["saved"])
        self.assertIn("Duplicate detected", res2["message"])

    def test_update_and_delete_memory(self):
        res = self.memory.save_memory(title="Draft Finding", content="Initial draft", verification_status=STATUS_HYPOTHESIS)
        mem_id = res["id"]

        # Update
        up_res = self.memory.update_memory(mem_id, content="Updated verified content", verification_status=STATUS_VERIFIED)
        self.assertTrue(up_res["updated"])

        item = self.memory.retrieve_memory()[0]
        self.assertEqual(item["content"], "Updated verified content")
        self.assertEqual(item["verification_status"], STATUS_VERIFIED)

        # Delete
        del_res = self.memory.delete_memory(mem_id)
        self.assertTrue(del_res["deleted"])
        self.assertEqual(len(self.memory.retrieve_memory()), 0)

    def test_secret_redaction_on_save(self):
        self.memory.save_memory(
            title="API Config",
            content="api_key = secret_token_12345\nuser=developer",
        )
        saved = self.memory.retrieve_memory()[0]
        self.assertNotIn("secret_token_12345", saved["content"])
        self.assertIn("[REDACTED]", saved["content"])

    def test_session_manager(self):
        session_id = self.session_mgr.start_session()
        self.assertTrue(session_id.startswith("session_"))
        self.assertEqual(self.session_mgr.current_session_id, session_id)

        self.session_mgr.increment_query_count()
        ended_id = self.session_mgr.end_session("Test session summary")
        self.assertEqual(ended_id, session_id)
        self.assertIsNone(self.session_mgr.current_session_id)

        session_record = self.session_mgr.get_session(session_id)
        self.assertIsNotNone(session_record)
        self.assertEqual(session_record["query_count"], 1)


if __name__ == "__main__":
    unittest.main()

