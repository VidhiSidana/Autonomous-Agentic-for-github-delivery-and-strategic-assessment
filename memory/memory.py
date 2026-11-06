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
STATUS_HYPOTHESIS   = "HYPOTHESIS"
STATUS_REJECTED     = "REJECTED"
STATUS_NEEDS_REVIEW = "NEEDS_REVIEW"
VALID_STATUSES = {STATUS_VERIFIED, STATUS_HYPOTHESIS, STATUS_REJECTED, STATUS_NEEDS_REVIEW}

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
                    last_reviewed_at    TIMESTAMP DEFAULT NULL
                )
            """)

            # Non-destructive migration: add columns that may be missing
            # from databases created with the original 4-column schema
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
    ) -> dict[str, Any]:
        """
        Save a new engineering memory entry.

        Returns a dict with the new row's id and status message.
        """
        # Import here to avoid circular imports
        from agent.policy import redact_secrets
        content = redact_secrets(content)

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
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (title, content, category, verification_status,
                 source, project, session_id, confidence, now, now),
            )
            new_id = cursor.lastrowid

        return {
            "saved": True,
            "id": new_id,
            "message": f"Memory saved (id={new_id}, status={verification_status}).",
        }

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
    ) -> list[sqlite3.Row]:
        """
        Retrieve memory entries, newest first, with optional filters.
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
        if session_id:
            conditions.append("session_id = ?")
            params.append(session_id)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)

        with self._connection() as conn:
            cursor = conn.execute(
                f"SELECT * FROM findings {where} ORDER BY id DESC LIMIT ?",
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
    ) -> list[sqlite3.Row]:
        """
        Search findings by keyword in title and content.
        Matches exact phrase or individual search terms (OR logic across terms).
        Optionally filter by verification status.
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

        with self._connection() as conn:
            cursor = conn.execute(
                f"SELECT * FROM findings {where} ORDER BY id DESC",
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

    def confirm_hypothesis(self, memory_id: int) -> dict[str, Any]:
        """
        Promote a HYPOTHESIS to VERIFIED — requires explicit engineer action.
        Never called automatically.
        """
        return self.update_memory(memory_id, verification_status=STATUS_VERIFIED)

    def reject_hypothesis(self, memory_id: int) -> dict[str, Any]:
        """Mark a hypothesis as REJECTED."""
        return self.update_memory(memory_id, verification_status=STATUS_REJECTED)


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
