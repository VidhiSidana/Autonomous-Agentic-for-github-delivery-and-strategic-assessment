"""
Tests for Task B2: Unified Memory Layer.
Covers:
  - Automatic session capture hooks (on_query, on_tool_result, on_session_end)
  - Local LLM summarization + deterministic extractive fallback with latency/tokens
  - Curated memory Markdown export and two-way lossless sync
  - Secret redaction across write paths
  - Dual-layer deduplication (normalised text hash + word Jaccard similarity)
  - Stale detection for deleted/missing files
  - Session resume digest with context budget constraint
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from memory.curated_memory import (
    CuratedMemoryManager,
    compute_jaccard_similarity,
    compute_normalised_hash,
)
from memory.memory import (
    EngineeringMemory,
    STATUS_CONFIRMED,
    STATUS_VERIFIED,
)
from memory.session_manager import SessionManager


class TestUnifiedMemoryLayer(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.db_path = self.temp_path / "test_unified.db"
        self.curated_dir = self.temp_path / "curated"
        self.curated_dir.mkdir(parents=True, exist_ok=True)
        self.project_root = self.temp_path / "project"
        self.project_root.mkdir(parents=True, exist_ok=True)

        self.memory = EngineeringMemory(db_path=self.db_path)
        self.session_mgr = SessionManager(db_path=self.db_path)
        self.curated_mgr = CuratedMemoryManager(
            memory=self.memory,
            curated_dir=self.curated_dir,
            project_root=self.project_root,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    # ------------------------------------------------------------------
    # 1. Automatic Session Capture Hooks
    # ------------------------------------------------------------------

    def test_session_hooks_and_event_stream(self):
        sess_id = self.session_mgr.start_session()
        self.assertIsNotNone(sess_id)

        # Hook: on_query with secret redaction
        q_res = self.session_mgr.on_query(
            session_id=sess_id,
            query="Find auth_token password: secret123 in services",
            intent="symbol_search",
        )
        self.assertNotIn("secret123", q_res["query"])
        self.assertIn("[REDACTED]", q_res["query"])

        # Hook: on_tool_result
        t_res = self.session_mgr.on_tool_result(
            session_id=sess_id,
            tool_name="ast_search",
            args={"query": "api_key = 12345"},
            success=True,
            evidence_refs="ast_search:services/auth.py:42",
            token_count=120,
            result_summary="Discovered auth handler in services/auth.py",
        )
        self.assertEqual(t_res["tool_name"], "ast_search")
        self.assertEqual(t_res["token_count"], 120)

        # Check recorded session events
        events = self.session_mgr.get_session_events(sess_id)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["event_type"], "query")
        self.assertEqual(events[1]["event_type"], "tool_result")
        self.assertNotIn("12345", events[1]["payload"])

    # ------------------------------------------------------------------
    # 2. Local Summarization (LLM + Extractive Fallback)
    # ------------------------------------------------------------------

    def test_session_end_with_extractive_fallback(self):
        sess_id = self.session_mgr.start_session()
        self.session_mgr.on_query(sess_id, "Where is the payment router?", intent="code_search")
        self.session_mgr.on_tool_result(
            sess_id,
            tool_name="code_graph",
            args={"symbol": "PaymentRouter"},
            success=True,
            evidence_refs="code_graph:routers/pay.py:10",
        )

        # Simulate LLM unavailable
        res = self.session_mgr.on_session_end(session_id=sess_id, llm=None)
        self.assertEqual(res["mode"], "extractive (LLM unavailable)")
        self.assertIn("PaymentRouter", res["summary"])
        self.assertGreaterEqual(res["latency_s"], 0.0)
        self.assertGreater(res["token_count"], 0)

        # Verify persisted in sessions table
        sess_row = self.session_mgr.get_session(sess_id)
        self.assertEqual(sess_row["summary_mode"], "extractive (LLM unavailable)")
        self.assertIn("PaymentRouter", sess_row["summary"])

    def test_session_end_with_mock_llm(self):
        sess_id = self.session_mgr.start_session()
        self.session_mgr.on_query(sess_id, "Inspect entry point")

        mock_llm = MagicMock()
        mock_llm.check_availability.return_value = (True, "Ready")
        mock_llm.chat.return_value = "Identified entry point at main.py:10."

        res = self.session_mgr.on_session_end(session_id=sess_id, llm=mock_llm)
        self.assertEqual(res["mode"], "llm")
        self.assertEqual(res["summary"], "Identified entry point at main.py:10.")
        self.assertGreater(res["token_count"], 0)

    # ------------------------------------------------------------------
    # 3. Curated Memory Markdown Two-Way Sync
    # ------------------------------------------------------------------

    def test_curated_markdown_export_and_import(self):
        # Save a confirmed finding in SQLite
        save_res = self.memory.save_memory(
            title="Database Connection Pool",
            content="Pool max connections set to 20 in config/db.py.",
            category="architecture",
            verification_status=STATUS_CONFIRMED,
            evidence_refs="read_file:config/db.py:15",
            confirmed_by="alice",
        )
        finding_id = save_res["id"]

        # Export to Markdown
        files = self.curated_mgr.export_curated_memory()
        self.assertEqual(len(files), 1)
        exported_file = files[0]
        self.assertTrue(exported_file.exists())

        md_content = exported_file.read_text(encoding="utf-8")
        self.assertIn(f"id: {finding_id}", md_content)
        self.assertIn("confirmed_by: alice", md_content)
        self.assertIn("Pool max connections set to 20", md_content)

        # Engineer edits Markdown file directly on disk
        updated_md = md_content.replace("Pool max connections set to 20", "Pool max connections increased to 50")
        exported_file.write_text(updated_md, encoding="utf-8")

        # Import edited Markdown back to SQLite
        import_stats = self.curated_mgr.import_curated_memory()
        self.assertEqual(import_stats["updated"], 1)

        # Verify SQLite row was updated losslessly
        row = self.memory.get_memory_by_id(finding_id)
        self.assertIn("increased to 50", row["content"])

    def test_curated_markdown_import_new_file(self):
        # Create a brand new curated markdown file
        new_md = (
            "---\n"
            "title: 'Worker thread count'\n"
            "category: 'concurrency'\n"
            "status: 'CONFIRMED'\n"
            "evidence_refs: 'code:workers.py:5'\n"
            "confirmed_by: 'bob'\n"
            "---\n\n"
            "Worker pool is initialized with 4 concurrent threads.\n"
        )
        md_path = self.curated_dir / "worker_threads.md"
        md_path.write_text(new_md, encoding="utf-8")

        stats = self.curated_mgr.import_curated_memory()
        self.assertEqual(stats["imported"], 1)

        search_res = self.memory.search_memory("concurrent threads")
        self.assertEqual(len(search_res), 1)
        self.assertEqual(search_res[0]["title"], "Worker thread count")
        self.assertEqual(search_res[0]["confirmed_by"], "bob")

    # ------------------------------------------------------------------
    # 4. Dual-Layer Deduplication
    # ------------------------------------------------------------------

    def test_dual_layer_deduplication(self):
        self.memory.save_memory(
            title="Crypto signature verification",
            content="Verifies Ed25519 signature of incoming packets before dispatch.",
            verification_status=STATUS_VERIFIED,
        )

        # Exact normalised hash match
        dup1 = self.curated_mgr.check_duplicate(
            title="crypto signature verification",
            content="Verifies Ed25519 signature of incoming packets before dispatch",
        )
        self.assertIsNotNone(dup1)
        self.assertEqual(dup1["layer"], "sqlite")

        # High Jaccard similarity match (>= 0.8)
        dup2 = self.curated_mgr.check_duplicate(
            title="Crypto signature verification",
            content="Verifies Ed25519 signature of incoming packets before dispatch protocol.",
            jaccard_threshold=0.8,
        )
        self.assertIsNotNone(dup2)
        self.assertTrue(dup2["reason"].startswith("jaccard_"))

        # Distinct finding (no duplicate)
        non_dup = self.curated_mgr.check_duplicate(
            title="HTML Template Renderer",
            content="Jinja template engine renders views.",
        )
        self.assertIsNone(non_dup)

    # ------------------------------------------------------------------
    # 5. Stale Detection
    # ------------------------------------------------------------------

    def test_stale_detection_for_missing_file(self):
        # Create an existing file
        existing_file = self.project_root / "existing_module.py"
        existing_file.write_text("def ping(): pass\n")

        # Save finding referencing the existing file
        self.memory.save_memory(
            title="Module Ping",
            content=f"File: {existing_file}\nPing is defined.",
            evidence_refs=f"ast:{existing_file}:1",
            verification_status=STATUS_CONFIRMED,
        )

        # Save finding referencing a non-existent file
        deleted_file = self.project_root / "deleted_module.py"
        res_del = self.memory.save_memory(
            title="Deleted Module",
            content=f"File: {deleted_file}\nModule was removed.",
            evidence_refs=f"ast:{deleted_file}:1",
            verification_status=STATUS_CONFIRMED,
        )
        del_id = res_del["id"]

        stale_list = self.curated_mgr.detect_stale_findings()
        self.assertEqual(len(stale_list), 1)
        self.assertEqual(stale_list[0]["id"], del_id)

        # Verify it was marked stale in SQLite
        row = self.memory.get_memory_by_id(del_id)
        self.assertEqual(row["is_stale"], 1)

    # ------------------------------------------------------------------
    # 6. Session Resume Digest
    # ------------------------------------------------------------------

    def test_session_resume_digest_budget(self):
        sess_id = self.session_mgr.start_session()
        self.session_mgr.on_query(sess_id, "Query 1")
        self.session_mgr.on_session_end(sess_id, summary="Completed architectural analysis of auth pipeline.")

        # Save confirmed finding for this session
        self.memory.save_memory(
            title="Auth Pipeline Structure",
            content="JWT validation precedes token authorization.",
            verification_status=STATUS_CONFIRMED,
            evidence_refs="ast:auth.py:20",
            session_id=sess_id,
        )

        digest = self.session_mgr.get_resume_digest(session_id=sess_id, max_tokens=200)
        self.assertIn("RESUMED SESSION DIGEST", digest)
        self.assertIn("Completed architectural analysis", digest)
        self.assertIn("Auth Pipeline Structure", digest)
        self.assertLessEqual(len(digest), 200 * 4)


if __name__ == "__main__":
    unittest.main()
