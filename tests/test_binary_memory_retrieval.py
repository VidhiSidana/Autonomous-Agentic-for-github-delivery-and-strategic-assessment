import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from agent.evidence import EvidenceBundle
from agent.orchestrator import AgentOrchestrator
from memory.memory import EngineeringMemory


class TestBinaryMemoryRetrieval(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.memory = EngineeringMemory(
            db_path=Path(self.temp_dir.name) / "memory.db"
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_executable_lookup_returns_only_matching_binary_record_and_id(self):
        metadata = {
            "file_name": "sample_authorized.exe",
            "machine": "0x8664",
            "architecture": "IMAGE_FILE_MACHINE_AMD64 (x64 64-bit)",
            "entry_point_rva": "0x1000",
            "image_base": "0x140000000",
            "number_of_sections": 1,
            "sections": [{"name": ".text"}],
        }
        saved = self.memory.save_memory(
            title="Binary analysis via 'analyze_binary' succeeded.",
            content="Details:\\n" + json.dumps(metadata),
            category="binary_finding",
            verification_status="VERIFIED",
            source="binary.analyze_binary",
            session_id="previous-session",
        )
        self.memory.save_memory(
            title="Unrelated code search",
            content="sample_authorized.exe appeared in a code graph query",
            category="technical_finding",
            verification_status="VERIFIED",
        )

        orchestrator = AgentOrchestrator.__new__(AgentOrchestrator)
        orchestrator.memory = self.memory
        plan = SimpleNamespace(
            memory_operation="retrieve",
            raw_query=(
                "Retrieve previous verified memory for "
                "sample_authorized.exe and report exact fields."
            ),
        )
        bundle = EvidenceBundle(query=plan.raw_query)

        asyncio.run(
            orchestrator._handle_memory(
                plan, bundle, session_id="new-session"
            )
        )

        self.assertEqual(len(bundle.items), 1)
        item = bundle.items[0]
        self.assertEqual(
            item.source,
            f"engineering_memory[id={saved['id']}]",
        )
        self.assertIn(
            f"Memory record ID: {saved['id']}",
            item.detail,
        )
        self.assertIn('"image_base": "0x140000000"', item.detail)
        self.assertIn('"machine": "0x8664"', item.detail)
        self.assertNotIn("Unrelated code search", item.detail)


if __name__ == "__main__":
    unittest.main()
