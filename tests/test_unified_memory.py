
import tempfile
import unittest
from pathlib import Path

from memory.memory import EngineeringMemory


class TestUnifiedEngineeringMemory(unittest.TestCase):

    def setUp(self):
        # Create a separate temporary database for each test.
        self.temp_dir = tempfile.TemporaryDirectory()

        db_path = Path(self.temp_dir.name) / "test_memory.db"

        self.memory = EngineeringMemory(db_path=db_path)

    def tearDown(self):
        # Clean up the temporary database.
        self.temp_dir.cleanup()

    def test_save_and_retrieve_memory(self):
        result = self.memory.save_memory(
            title="Test function finding",
            content="process_query is defined in agent/main.py",
            category="technical_finding",
            verification_status="VERIFIED"
        )

        self.assertTrue(result["saved"])

        findings = self.memory.retrieve_memory()

        self.assertEqual(len(findings), 1)
        self.assertEqual(
            findings[0]["title"],
            "Test function finding"
        )

    def test_duplicate_memory_detection(self):
        self.memory.save_memory(
            title="Duplicate test",
            content="First finding"
        )

        result = self.memory.save_memory(
            title="Duplicate test",
            content="Second finding"
        )

        self.assertFalse(result["saved"])
        self.assertIn("duplicate_id", result)

    def test_search_memory(self):
        self.memory.save_memory(
            title="Authentication finding",
            content="Authentication uses a login handler."
        )

        results = self.memory.search_memory("Authentication")

        self.assertGreaterEqual(len(results), 1)

    def test_search_memory_filters_by_category(self):
        self.memory.save_memory(
            title="Binary metadata",
            content="sample_authorized.exe machine 0x8664",
            category="binary_finding",
            verification_status="VERIFIED",
        )
        self.memory.save_memory(
            title="Unrelated code result",
            content="sample_authorized.exe appears in a code search",
            category="technical_finding",
            verification_status="VERIFIED",
        )

        results = self.memory.search_memory(
            "sample_authorized.exe",
            category="binary_finding",
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["category"], "binary_finding")
        self.assertEqual(results[0]["title"], "Binary metadata")

    def test_verification_status(self):
        result = self.memory.save_memory(
            title="Possible bug",
            content="A possible issue was discovered.",
            verification_status="HYPOTHESIS"
        )

        memory_id = result["id"]

        self.memory.confirm_hypothesis(memory_id)

        finding = self.memory.get_memory_by_id(memory_id)

        self.assertEqual(
            finding["verification_status"],
            "VERIFIED"
        )

    def test_mark_memory_stale(self):
        result = self.memory.save_memory(
            title="Old finding",
            content="This finding may be outdated."
        )

        memory_id = result["id"]

        self.memory.mark_stale(memory_id)

        findings = self.memory.retrieve_memory()

        self.assertEqual(len(findings), 0)

    def test_persistence_across_instances(self):
        result = self.memory.save_memory(
            title="Persistent finding",
            content="This memory should survive reopening."
        )

        memory_id = result["id"]

        # Create another memory instance using the same database.
        second_memory = EngineeringMemory(
            db_path=self.memory.db_path
        )

        finding = second_memory.get_memory_by_id(memory_id)

        self.assertIsNotNone(finding)
        self.assertEqual(
            finding["title"],
            "Persistent finding"
        )


if __name__ == "__main__":
    unittest.main()
