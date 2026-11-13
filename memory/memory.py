"""
Improved Engineering Memory for the Samsung PRISM Unified Engineering Agent.

Improvements over the original:
  - Upgraded SQLite schema with category, verification_status, source,
    session_id, confidence, project, updated_at, is_stale fields
  - Non-destructive migration: existing rows are preserved
  - Full CRUD: save, retrieve, search, update, delete
  - Verification status: VERIFIED | HYPOTHESIS | REJECTED | NEEDS_REVIEW
  - Secret redaction via policy module
  - Basic duplicate detection (title match)
  - Session-aware queries
"""

import logging
import sqlite3
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import MEMORY_DB_PATH

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Verification status constants
# ---------------------------------------------------------------------------
STATUS_VERIFIED     = "VERIFIED"
STATUS_CONFIRMED    = "CONFIRMED"
STATUS_PROPOSED     = "PROPOSED"
STATUS_HYPOTHESIS   = "HYPOTHESIS"
STATUS_NEEDS_REVIEW = "NEEDS_REVIEW"
STATUS_REJECTED     = "REJECTED"
VALID_STATUSES = {
    STATUS_VERIFIED,
    STATUS_CONFIRMED,
    STATUS_PROPOSED,
    STATUS_HYPOTHESIS,
    STATUS_NEEDS_REVIEW,
    STATUS_REJECTED,
}
FACT_STATUSES = {STATUS_VERIFIED, STATUS_CONFIRMED}

# ---------------------------------------------------------------------------
# Memory categories
# ---------------------------------------------------------------------------
CATEGORIES = {
    "project_fact",
    "architecture_decision",
    "technical_finding",
    "bug_fix",
    "code_relationship",
    "binary_finding",
    "engineering_decision",
    "hypothesis",
    "session_summary",
    "known_limitation",
    "general",
}


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


class EngineeringMemory:
    """
    Persistent engineering memory backed by SQLite.

    All public methods are synchronous and safe to call from both
    sync and async contexts (they do not use async I/O).
    """

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = db_path or MEMORY_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    @contextmanager
    def _connection(self):
        """
        Open a SQLite connection, manage its transaction,
        and always close it to prevent database locks.
        """
        conn = self._connect()

        try:
            with conn:
                yield conn
        finally:
            conn.close()
    # ------------------------------------------------------------------
    # Schema initialisation and migration
    # ------------------------------------------------------------------

    def _init_schema(self) -> None:
        """
        Create the findings table if it does not exist, then run
        non-destructive column migrations for the upgraded schema.
        Existing data is never deleted.
        """
        with self._connection() as conn:
            # Create table with full schema
            conn.execute("""
                CREATE TABLE IF NOT EXISTS findings (
                    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                    title               TEXT    NOT NULL,
                    content             TEXT    NOT NULL,
                    category            TEXT    NOT NULL DEFAULT 'general',
                    verification_status TEXT    NOT NULL DEFAULT 'VERIFIED',
                    source              TEXT    DEFAULT '',
                    project             TEXT    DEFAULT '',
                    session_id          TEXT    DEFAULT '',
                    confidence          REAL    DEFAULT 1.0,
                    is_stale            INTEGER DEFAULT 0,
                    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_reviewed_at    TIMESTAMP DEFAULT NULL,
                    evidence_refs       TEXT    DEFAULT '',
                    confirmed_by        TEXT    DEFAULT '',
                    confirmed_at        TIMESTAMP DEFAULT NULL,
                    rejection_reason    TEXT    DEFAULT ''
                )
            """)

            # Non-destructive migration: add columns that may be missing
            # from databases created with previous schemas
            existing = {
                row[1]
                for row in conn.execute("PRAGMA table_info(findings)")
            }
            migrations = {
                "category":            "TEXT NOT NULL DEFAULT 'general'",
                "verification_status": "TEXT NOT NULL DEFAULT 'VERIFIED'",
                "source":              "TEXT DEFAULT ''",
                "project":             "TEXT DEFAULT ''",
                "session_id":          "TEXT DEFAULT ''",
                "confidence":          "REAL DEFAULT 1.0",
                "is_stale":            "INTEGER DEFAULT 0",
                "updated_at":          "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
                "last_reviewed_at":    "TIMESTAMP DEFAULT NULL",
                "evidence_refs":       "TEXT DEFAULT ''",
                "confirmed_by":        "TEXT DEFAULT ''",
                "confirmed_at":        "TIMESTAMP DEFAULT NULL",
                "rejection_reason":    "TEXT DEFAULT ''",
            }
            for col, definition in migrations.items():
                if col not in existing:
                    conn.execute(
                        f"ALTER TABLE findings ADD COLUMN {col} {definition}"
                    )
                    logger.debug("Migrated: added column '%s' to findings.", col)

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def save_memory(
        self,
        title: str,
        content: str,
        category: str = "general",
        verification_status: str = STATUS_VERIFIED,
        source: str = "",
        project: str = "",
        session_id: str = "",
        confidence: float = 1.0,
        evidence_refs: str = "",
        confirmed_by: str = "",
        confirmed_at: Optional[str] = None,
        rejection_reason: str = "",
    ) -> dict[str, Any]:
        """
        Save a new engineering memory entry.

        Returns a dict with the new row's id and status message.
        """
        from agent.policy import redact_secrets
        title = redact_secrets(title)
        content = redact_secrets(content)
        evidence_refs = redact_secrets(evidence_refs)
        rejection_reason = redact_secrets(rejection_reason)

        if verification_status not in VALID_STATUSES:
            verification_status = STATUS_NEEDS_REVIEW

        if category not in CATEGORIES:
            category = "general"

        # Basic duplicate check (same title + same content)
        duplicate = self._find_duplicate(title, content)
        if duplicate:
            return {
                "saved": False,
                "message": (
                    f"Duplicate detected: a similar finding already exists "
                    f"(id={duplicate['id']}, title='{duplicate['title']}'). "
                    "Use update_memory() to modify it, or choose a different title."
                ),
                "duplicate_id": duplicate["id"],
            }

        now = _now_utc()
        with self._connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO findings
                    (title, content, category, verification_status,
                     source, project, session_id, confidence,
                     created_at, updated_at, evidence_refs, confirmed_by,
                     confirmed_at, rejection_reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (title, content, category, verification_status,
                 source, project, session_id, confidence, now, now,
                 evidence_refs, confirmed_by, confirmed_at, rejection_reason),
            )
            new_id = cursor.lastrowid

        return {
            "saved": True,
            "id": new_id,
            "message": f"Memory saved (id={new_id}, status={verification_status}).",
        }

    def propose_finding(
        self,
        title: str,
        content: str,
        category: str = "hypothesis",
        evidence_refs: str = "",
        source: str = "",
        project: str = "",
        session_id: str = "",
        confidence: float = 0.5,
    ) -> dict[str, Any]:
        """
        Propose an unverified hypothesis or finding awaiting engineer confirmation.
        Status is strictly PROPOSED; it is never retrieved as an established fact.
        """
        return self.save_memory(
            title=title,
            content=content,
            category=category,
            verification_status=STATUS_PROPOSED,
            source=source,
            project=project,
            session_id=session_id,
            confidence=confidence,
            evidence_refs=evidence_refs,
        )

    def confirm_finding(
        self,
        memory_id: int,
        confirmed_by: str = "engineer",
        target_status: str = STATUS_CONFIRMED,
    ) -> dict[str, Any]:
        """
        Promote only a PROPOSED or HYPOTHESIS finding to CONFIRMED/VERIFIED.
        Rejected findings cannot be silently resurrected by confirmation.
        """
        allowed_targets = {STATUS_CONFIRMED, STATUS_VERIFIED}
        if target_status not in allowed_targets:
            return {
                "updated": False,
                "message": (
                    f"Invalid confirmation target '{target_status}'. "
                    f"Allowed: {sorted(allowed_targets)}."
                ),
            }

        now = _now_utc()
        with self._connection() as conn:
            cursor = conn.execute(
                """
                UPDATE findings
                SET verification_status = ?, confirmed_by = ?, confirmed_at = ?, updated_at = ?
                WHERE id = ? AND verification_status IN (?, ?)
                """,
                (
                    target_status,
                    confirmed_by,
                    now,
                    now,
                    memory_id,
                    STATUS_PROPOSED,
                    STATUS_HYPOTHESIS,
                ),
            )
            if cursor.rowcount == 0:
                existing = conn.execute(
                    "SELECT verification_status FROM findings WHERE id = ?",
                    (memory_id,),
                ).fetchone()
                if existing is None:
                    message = f"No memory found with id={memory_id}."
                else:
                    message = (
                        f"Finding id={memory_id} cannot be confirmed from "
                        f"status '{existing['verification_status']}'. "
                        "Only PROPOSED or HYPOTHESIS findings can be confirmed."
                    )
                return {"updated": False, "message": message}

        return {
            "updated": True,
            "id": memory_id,
            "status": target_status,
            "confirmed_by": confirmed_by,
            "confirmed_at": now,
            "message": f"Finding id={memory_id} confirmed by {confirmed_by} (promoted to {target_status}).",
        }

    def reject_finding(
        self,
        memory_id: int,
        reason: str = "",
        rejected_by: str = "engineer",
    ) -> dict[str, Any]:
        """
        Rejects a finding and records the engineer's rationale and timestamp.
        Excluded from all fact retrievals.
        """
        from agent.policy import redact_secrets
        now = _now_utc()
        clean_reason = redact_secrets(reason)
        with self._connection() as conn:
            cursor = conn.execute(
                """
                UPDATE findings
                SET verification_status = ?, rejection_reason = ?, confirmed_by = ?, confirmed_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (STATUS_REJECTED, clean_reason, rejected_by, now, now, memory_id),
            )
            if cursor.rowcount == 0:
                return {"updated": False, "message": f"No memory found with id={memory_id}."}
        return {
            "updated": True,
            "id": memory_id,
            "status": STATUS_REJECTED,
            "rejection_reason": clean_reason,
            "message": f"Finding id={memory_id} rejected by {rejected_by} (reason: {clean_reason or 'none provided'}).",
        }

    def get_pending_proposals(self, session_id: Optional[str] = None) -> list[sqlite3.Row]:
        """List findings awaiting engineer confirmation (PROPOSED status)."""
        conditions = ["verification_status = 'PROPOSED'", "is_stale = 0"]
        params: list[Any] = []
        if session_id:
            conditions.append("session_id = ?")
            params.append(session_id)
        where = f"WHERE {' AND '.join(conditions)}"
        with self._connection() as conn:
            cursor = conn.execute(
                f"SELECT * FROM findings {where} ORDER BY id ASC",
                params,
            )
            return cursor.fetchall()

    # Backward-compatible alias used by the original agent
    def save_finding(self, title: str, content: str) -> str:
        result = self.save_memory(title, content)
        return result["message"]

    # ------------------------------------------------------------------
    # Retrieve
    # ------------------------------------------------------------------

    def retrieve_memory(
        self,
        limit: int = 50,
        category: Optional[str] = None,
        verification_status: Optional[str] = None,
        session_id: Optional[str] = None,
        include_stale: bool = False,
        include_proposed: bool = False,
        category: Optional[str] = None,
    ) -> list[sqlite3.Row]:
        """
        Retrieve memory entries, ordered by confirmation priority (CONFIRMED/VERIFIED first),
        then newest first. By default, PROPOSED and REJECTED items are excluded from fact retrieval.
        """
        conditions: list[str] = []
        params: list[Any] = []

        if not include_stale:
            conditions.append("is_stale = 0")
        if category:
            conditions.append("category = ?")
            params.append(category)
        if verification_status:
            conditions.append("verification_status = ?")
            params.append(verification_status)
        elif not include_proposed:
            conditions.append("verification_status NOT IN ('PROPOSED', 'REJECTED')")

        if session_id:
            conditions.append("session_id = ?")
            params.append(session_id)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        order_clause = (
            "ORDER BY CASE verification_status "
            "WHEN 'CONFIRMED' THEN 1 "
            "WHEN 'VERIFIED' THEN 2 "
            "WHEN 'HYPOTHESIS' THEN 3 "
            "ELSE 4 END, id DESC"
        )
        params.append(limit)

        with self._connection() as conn:
            cursor = conn.execute(
                f"SELECT * FROM findings {where} {order_clause} LIMIT ?",
                params,
            )
            return cursor.fetchall()

    def get_memory_by_id(self, memory_id: int) -> Optional[sqlite3.Row]:
        """Fetch a single memory finding by exact primary key."""
        with self._connection() as conn:
            cursor = conn.execute("SELECT * FROM findings WHERE id = ? LIMIT 1", (memory_id,))
            return cursor.fetchone()

    # Backward-compatible alias
    def retrieve_findings(self) -> list[sqlite3.Row]:
        return self.retrieve_memory()

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search_memory(
        self,
        keyword: str,
        verification_status: Optional[str] = None,
        include_proposed: bool = False,
    ) -> list[sqlite3.Row]:
        """
        Search findings by keyword in title and content.
        Matches exact phrase or individual search terms (OR logic across terms).
        Optionally filter by verification status. By default excludes PROPOSED and REJECTED.
        """
        # Split into individual search terms of length >= 3
        words = [w.strip() for w in keyword.split() if len(w.strip()) >= 3]
        if not words:
            words = [keyword.strip()] if keyword.strip() else []

        if not words:
            return []

        term_clauses = []
        params: list[Any] = []
        for w in words:
            term_clauses.append("(title LIKE ? OR content LIKE ?)")
            params.extend([f"%{w}%", f"%{w}%"])

        where = f"WHERE ({' OR '.join(term_clauses)})"
        if verification_status:
            where += " AND verification_status = ?"
            params.append(verification_status)
        elif not include_proposed:
            where += " AND verification_status NOT IN ('PROPOSED', 'REJECTED')"

        if category:
            where += " AND category = ?"
            params.append(category)

        order_clause = (
            "ORDER BY CASE verification_status "
            "WHEN 'CONFIRMED' THEN 1 "
            "WHEN 'VERIFIED' THEN 2 "
            "WHEN 'HYPOTHESIS' THEN 3 "
            "ELSE 4 END, id DESC"
        )

        with self._connection() as conn:
            cursor = conn.execute(
                f"SELECT * FROM findings {where} {order_clause}",
                params,
            )
            return cursor.fetchall()

    # Backward-compatible alias
    def search_findings(self, keyword: str) -> list[sqlite3.Row]:
        return self.search_memory(keyword)

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update_memory(
        self,
        memory_id: int,
        title: Optional[str] = None,
        content: Optional[str] = None,
        category: Optional[str] = None,
        verification_status: Optional[str] = None,
        source: Optional[str] = None,
        confidence: Optional[float] = None,
    ) -> dict[str, Any]:
        """Update fields of an existing memory entry."""
        from agent.policy import redact_secrets

        updates: list[str] = []
        params: list[Any] = []

        if title is not None:
            updates.append("title = ?"); params.append(title)
        if content is not None:
            updates.append("content = ?"); params.append(redact_secrets(content))
        if category is not None:
            updates.append("category = ?"); params.append(category)
        if verification_status is not None:
            if verification_status not in VALID_STATUSES:
                return {"updated": False, "message": f"Invalid status: {verification_status}"}
            updates.append("verification_status = ?"); params.append(verification_status)
        if source is not None:
            updates.append("source = ?"); params.append(source)
        if confidence is not None:
            updates.append("confidence = ?"); params.append(confidence)

        if not updates:
            return {"updated": False, "message": "No fields provided to update."}

        updates.append("updated_at = ?")
        params.append(_now_utc())
        params.append(memory_id)

        with self._connection() as conn:
            cursor = conn.execute(
                f"UPDATE findings SET {', '.join(updates)} WHERE id = ?",
                params,
            )
            if cursor.rowcount == 0:
                return {"updated": False, "message": f"No memory found with id={memory_id}."}

        return {"updated": True, "message": f"Memory id={memory_id} updated."}

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete_memory(self, memory_id: int) -> dict[str, Any]:
        """Permanently delete a memory entry by id."""
        with self._connection() as conn:
            cursor = conn.execute(
                "DELETE FROM findings WHERE id = ?", (memory_id,)
            )
            if cursor.rowcount == 0:
                return {"deleted": False, "message": f"No memory found with id={memory_id}."}
        return {"deleted": True, "message": f"Memory id={memory_id} deleted."}

    # ------------------------------------------------------------------
    # Duplicate detection
    # ------------------------------------------------------------------

    def _find_duplicate(
        self, title: str, content: str
    ) -> Optional[sqlite3.Row]:
        """Return an existing row if title matches (case-insensitive)."""
        with self._connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM findings WHERE lower(title) = lower(?) LIMIT 1",
                (title,),
            )
            return cursor.fetchone()

    # ------------------------------------------------------------------
    # Mark stale
    # ------------------------------------------------------------------

    def mark_stale(self, memory_id: int) -> dict[str, Any]:
        """Mark a memory entry as stale (outdated)."""
        with self._connection() as conn:
            cursor = conn.execute(
                "UPDATE findings SET is_stale = 1, updated_at = ? WHERE id = ?",
                (_now_utc(), memory_id),
            )
            if cursor.rowcount == 0:
                return {"updated": False, "message": f"No memory found with id={memory_id}."}
        return {"updated": True, "message": f"Memory id={memory_id} marked stale."}

    # ------------------------------------------------------------------
    # Hypothesis confirmation / rejection
    # ------------------------------------------------------------------

    def confirm_hypothesis(
        self,
        memory_id: int,
        confirmed_by: str = "engineer",
        target_status: str = STATUS_VERIFIED,
    ) -> dict[str, Any]:
        """
        Promote a HYPOTHESIS to VERIFIED (or CONFIRMED) — requires explicit engineer action.
        Never called automatically.
        """
        return self.confirm_finding(memory_id, confirmed_by=confirmed_by, target_status=target_status)

    def reject_hypothesis(
        self,
        memory_id: int,
        reason: str = "",
        rejected_by: str = "engineer",
    ) -> dict[str, Any]:
        """Mark a hypothesis as REJECTED with reason and timestamp."""
        return self.reject_finding(memory_id, reason=reason, rejected_by=rejected_by)

    # ------------------------------------------------------------------
    # Curated Memory & Deduplication Proxies (TASK B2)
    # ------------------------------------------------------------------

    def export_curated_memory(self, curated_dir: Optional[Path] = None) -> list[Path]:
        from memory.curated_memory import CuratedMemoryManager
        mgr = CuratedMemoryManager(memory=self, curated_dir=curated_dir)
        return mgr.export_curated_memory()

    def import_curated_memory(self, curated_dir: Optional[Path] = None) -> dict[str, int]:
        from memory.curated_memory import CuratedMemoryManager
        mgr = CuratedMemoryManager(memory=self, curated_dir=curated_dir)
        return mgr.import_curated_memory()

    def check_duplicate(self, title: str, content: str, jaccard_threshold: float = 0.8) -> Optional[dict[str, Any]]:
        from memory.curated_memory import CuratedMemoryManager
        mgr = CuratedMemoryManager(memory=self)
        return mgr.check_duplicate(title, content, jaccard_threshold=jaccard_threshold)

    def detect_stale_findings(self, project_root: Optional[Path] = None) -> list[dict[str, Any]]:
        from memory.curated_memory import CuratedMemoryManager
        mgr = CuratedMemoryManager(memory=self, project_root=project_root)
        return mgr.detect_stale_findings()


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    mem = EngineeringMemory()

    print("Saving test memory...")
    r = mem.save_memory(
        title="Authentication handler location",
        content="Authentication is handled by auth_service.py in the services/ directory.",
        category="technical_finding",
        verification_status=STATUS_VERIFIED,
        source="manual inspection",
    )
    print(r)

    print("\nSearching for 'auth'...")
    results = mem.search_memory("auth")
    for row in results:
        print(dict(row))
