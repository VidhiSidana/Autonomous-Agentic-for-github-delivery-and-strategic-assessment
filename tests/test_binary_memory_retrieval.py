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
                "Finding: Binary analysis succeeded.\n"
                "Source: binary.analyze_binary\n"
                "Details:\n"
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

    def test_cross_process_subprocess_binary_memory_recovery(self):
        """
        Step 2.4 regression test: Session 1 saves finding in SQLite, engineer confirms,
        and Session 2 in an independent subprocess recovers the finding.
        """
        import subprocess
        import sys
        from benchmarks.e2e_eval import score_ground_truth

        metadata = {
            "file_name": "sample_authorized.exe",
            "machine": "0x8664",
            "architecture": "AMD64",
            "entry_point_rva": "0x1000",
            "image_base": "0x140000000",
            "number_of_sections": 4,
            "sections": [{"name": ".text"}, {"name": ".rdata"}],
        }
        saved = self.memory.save_memory(
            title="Binary analysis via 'analyze_binary' succeeded.",
            content=(
                "Finding: Binary analysis succeeded.\n"
                "Source: binary.analyze_binary\n"
                "Details:\n" + json.dumps(metadata)
            ),
            category="binary_finding",
            verification_status="PROPOSED",
            source="binary.analyze_binary",
            session_id="session-1",
        )
        conf = self.memory.confirm_finding(saved["id"], confirmed_by="lead_engineer")
        self.assertTrue(conf["updated"])

        repo_root = Path(__file__).resolve().parent.parent
        db_file = str(Path(self.temp_dir.name) / "memory.db")
        code = f"""
import sys, json, asyncio
from pathlib import Path
sys.path.insert(0, {repr(str(repo_root))})
from memory.memory import EngineeringMemory
from memory.session_manager import SessionManager
from agent.orchestrator import AgentOrchestrator

async def run():
    db = Path({repr(db_file)})
    mem = EngineeringMemory(db_path=db)
    sm = SessionManager(db_path=db)
    sm.start_session()
    orch = AgentOrchestrator(memory=mem, session_manager=sm, default_repo_dir=Path({repr(str(repo_root))}))
    res = await orch.process_query("What binary architecture and entry point did we discover in the previous session?")
    await orch.close()
    out = {{
        "response": res.response_text,
        "evidence_count": len(res.evidence_bundle.items),
    }}
    print("SUBPROCESS_OUT:" + json.dumps(out))

asyncio.run(run())
"""
        proc = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(proc.returncode, 0, f"Subprocess failed:\nSTDOUT: {proc.stdout}\nSTDERR: {proc.stderr}")
        self.assertIn("SUBPROCESS_OUT:", proc.stdout)
        line = [ln for ln in proc.stdout.splitlines() if ln.startswith("SUBPROCESS_OUT:")][0]
        data = json.loads(line[len("SUBPROCESS_OUT:"):])
        self.assertTrue(data["evidence_count"] > 0)
        passed, reason = score_ground_truth("RS1", data["response"])
        self.assertTrue(passed, f"RS1 failed to pass ground truth scoring: {reason}")


if __name__ == "__main__":
    unittest.main()
