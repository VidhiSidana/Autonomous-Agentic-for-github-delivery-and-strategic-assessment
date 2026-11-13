import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from agent.evidence import EvidenceBundle, normalise_memory_result
from agent.orchestrator import AgentOrchestrator
from agent.planner import QueryCategory, QueryPlan
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


    def test_verified_binary_memory_response_preserves_exact_metadata(self):
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
            title="Verified binary metadata",
            content=(
                "Finding: Binary analysis succeeded.\\n"
                "Source: binary.analyze_binary\\n"
                "Details:\\n"
                + json.dumps(metadata, indent=2)
            ),
            category="binary_finding",
            verification_status="VERIFIED",
            source="binary.analyze_binary",
            session_id="previous-session",
        )

        rows = self.memory.search_memory(
            "sample_authorized.exe",
            category="binary_finding",
        )
        bundle = EvidenceBundle(query="Retrieve binary memory")
        for item in normalise_memory_result(rows):
            bundle.add(item)

        query = (
            "Retrieve the verified persistent memory findings for "
            "sample_authorized.exe from the previous session. Report "
            "the machine type, architecture, entry point RVA, image "
            "base, section count, section name, and source memory "
            "record ID. Only use retrieved memory."
        )
        plan = QueryPlan(
            category=QueryCategory.MEMORY,
            raw_query=query,
            memory_operation="retrieve",
        )
        orchestrator = AgentOrchestrator.__new__(AgentOrchestrator)

        response = asyncio.run(
            orchestrator._generate_response(query, plan, bundle)
        )

        self.assertIn(f"Memory record ID: {saved['id']}", response)
        self.assertIn("Machine type: 0x8664", response)
        self.assertIn(
            "Architecture: IMAGE_FILE_MACHINE_AMD64 (x64 64-bit)",
            response,
        )
        self.assertIn("Entry point RVA: 0x1000", response)
        self.assertIn("Image base: 0x140000000", response)
        self.assertIn("Section count: 1", response)
        self.assertIn("Section name(s): .text", response)
        self.assertIn("Verification status: VERIFIED", response)



if __name__ == "__main__":
    unittest.main()
