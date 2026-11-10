"""
Tests for Task B1: Engineer-confirmation (verification) flow.
Covers lifecycle states (PROPOSED -> CONFIRMED / REJECTED), provenance tracking,
retrieval priority, and evidence context formatting.
"""

import tempfile
import unittest
from pathlib import Path

from agent.evidence import EvidenceBundle, EvidenceItem, EvidenceKind, normalise_memory_result
from memory.memory import (
    EngineeringMemory,
    STATUS_CONFIRMED,
    STATUS_HYPOTHESIS,
    STATUS_PROPOSED,
    STATUS_REJECTED,
    STATUS_VERIFIED,
)


class TestConfirmationFlow(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_confirmation.db"
        self.memory = EngineeringMemory(db_path=self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_propose_finding_lifecycle_and_exclusion(self):
        # 1. Propose an unverified hypothesis
        prop_res = self.memory.propose_finding(
            title="Candidate memory leak in socket pool",
            content="Socket buffer might not be cleared on disconnect.",
            category="hypothesis",
            evidence_refs="code_analysis:pool.py:42",
            source="llm_hypothesis",
            session_id="session-test-001",
        )
        self.assertTrue(prop_res["saved"])
        mem_id = prop_res["id"]

        # Verify it appears in pending proposals
        pending = self.memory.get_pending_proposals()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["id"], mem_id)
        self.assertEqual(pending[0]["verification_status"], STATUS_PROPOSED)
        self.assertEqual(pending[0]["evidence_refs"], "code_analysis:pool.py:42")

        # Verify it is NEVER retrieved as an established fact in default retrieve
        facts = self.memory.retrieve_memory()
        self.assertEqual(len(facts), 0, "PROPOSED finding must not appear in default retrieve_memory")

        # Verify it is NEVER retrieved in default search
        search_res = self.memory.search_memory("socket pool")
        self.assertEqual(len(search_res), 0, "PROPOSED finding must not appear in default search_memory")

    def test_confirm_finding_promotes_to_confirmed_with_metadata(self):
        # Propose finding
        prop = self.memory.propose_finding(
            title="Confirmed function target",
            content="Target function process_query routes input.",
            evidence_refs="ast_search:agent/main.py:98",
        )
        mem_id = prop["id"]

        # Confirm finding
        conf_res = self.memory.confirm_finding(mem_id, confirmed_by="lead_engineer")
        self.assertTrue(conf_res["updated"])
        self.assertEqual(conf_res["status"], STATUS_CONFIRMED)
        self.assertEqual(conf_res["confirmed_by"], "lead_engineer")
        self.assertIsNotNone(conf_res["confirmed_at"])

        # Check DB row
        row = self.memory.get_memory_by_id(mem_id)
        self.assertEqual(row["verification_status"], STATUS_CONFIRMED)
        self.assertEqual(row["confirmed_by"], "lead_engineer")
        self.assertTrue(bool(row["confirmed_at"]))
        self.assertEqual(row["evidence_refs"], "ast_search:agent/main.py:98")

        # Now it is retrievable as a fact
        retrieved = self.memory.retrieve_memory()
        self.assertEqual(len(retrieved), 1)
        self.assertEqual(retrieved[0]["id"], mem_id)

        # Pending proposals is now empty
        pending = self.memory.get_pending_proposals()
        self.assertEqual(len(pending), 0)

    def test_reject_finding_sets_reason_and_excludes_from_facts(self):
        prop = self.memory.propose_finding(
            title="False lead on memory corruption",
            content="Suspected buffer overflow at 0x401000.",
            evidence_refs="disassemble:sample.exe:0x401000",
        )
        mem_id = prop["id"]

        rej_res = self.memory.reject_finding(
            mem_id,
            reason="Static bounds check proved safe by compiler stack canary.",
            rejected_by="security_reviewer",
        )
        self.assertTrue(rej_res["updated"])
        self.assertEqual(rej_res["status"], STATUS_REJECTED)

        row = self.memory.get_memory_by_id(mem_id)
        self.assertEqual(row["verification_status"], STATUS_REJECTED)
        self.assertIn("canary", row["rejection_reason"])
        self.assertEqual(row["confirmed_by"], "security_reviewer")

        # Excluded from facts
        self.assertEqual(len(self.memory.retrieve_memory()), 0)
        self.assertEqual(len(self.memory.search_memory("buffer overflow")), 0)
        self.assertEqual(len(self.memory.get_pending_proposals()), 0)

    def test_retrieval_priority_ordering(self):
        # Save a HYPOTHESIS
        self.memory.save_memory(
            title="Hypothesis Finding",
            content="May be related to network lag.",
            verification_status=STATUS_HYPOTHESIS,
        )
        # Save a VERIFIED finding
        self.memory.save_memory(
            title="Verified Finding",
            content="Definite match in auth module.",
            verification_status=STATUS_VERIFIED,
        )
        # Save a CONFIRMED finding
        self.memory.save_memory(
            title="Confirmed Finding",
            content="Confirmed bug location.",
            verification_status=STATUS_CONFIRMED,
        )
        # Save a PROPOSED finding (should be excluded)
        self.memory.propose_finding(
            title="Proposed Finding",
            content="Unconfirmed conjecture.",
        )

        results = self.memory.retrieve_memory()
        self.assertEqual(len(results), 3)
        # Priority: CONFIRMED (1), VERIFIED (2), HYPOTHESIS (3)
        self.assertEqual(results[0]["verification_status"], STATUS_CONFIRMED)
        self.assertEqual(results[1]["verification_status"], STATUS_VERIFIED)
        self.assertEqual(results[2]["verification_status"], STATUS_HYPOTHESIS)

    def test_evidence_normalisation_and_context(self):
        # Mock memory rows
        rows = [
            {
                "id": 1,
                "title": "Confirmed Fact",
                "content": "Line 42 has the root cause.",
                "verification_status": STATUS_CONFIRMED,
                "created_at": "2026-11-10",
                "category": "finding",
            },
            {
                "id": 2,
                "title": "Unverified Guess",
                "content": "Might be a race condition.",
                "verification_status": STATUS_HYPOTHESIS,
                "created_at": "2026-11-10",
                "category": "hypothesis",
            },
            {
                "id": 3,
                "title": "Rejected Idea",
                "content": "Not a memory leak.",
                "verification_status": STATUS_REJECTED,
                "created_at": "2026-11-10",
                "category": "hypothesis",
            },
            {
                "id": 4,
                "title": "Pending Proposal",
                "content": "Awaiting review.",
                "verification_status": STATUS_PROPOSED,
                "created_at": "2026-11-10",
                "category": "hypothesis",
            },
        ]
        norm = normalise_memory_result(rows)
        # Only row 1 (CONFIRMED) and row 2 (HYPOTHESIS) should be included
        self.assertEqual(len(norm), 2)
        self.assertEqual(norm[0].kind, EvidenceKind.VERIFIED)
        self.assertEqual(norm[1].kind, EvidenceKind.HYPOTHESIS)

        bundle = EvidenceBundle(query="Why did the service crash?")
        for item in norm:
            bundle.add(item)

        llm_ctx = bundle.to_llm_context()
        self.assertIn("UNVERIFIED HYPOTHESIS, NOT AN ESTABLISHED FACT", llm_ctx)
        self.assertIn("Confirmed Fact", llm_ctx)
        self.assertNotIn("Rejected Idea", llm_ctx)
        self.assertNotIn("Pending Proposal", llm_ctx)


if __name__ == "__main__":
    unittest.main()

