"""
Session Manager for the Samsung PRISM Unified Engineering Agent.

Manages engineering work sessions:
  - Generates unique session IDs
  - Tracks session start/end times
  - Links memory entries to sessions
  - Stores compact session summaries
"""

import sys
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import MEMORY_DB_PATH, SESSION_PREFIX


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


class SessionManager:
    """
    Manages session lifecycle and summaries.
    Sessions are lightweight records stored in the same SQLite database
    as engineering memory, in a separate 'sessions' table.
    """

    def __init__(self, db_path: Optional[Path] = None) -> None:
        import sqlite3
        self._db_path = db_path or MEMORY_DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._current_session_id: Optional[str] = None
        self._init_schema()

    def _connect(self):
        import sqlite3
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn
    from contextlib import contextmanager
    @contextmanager
    def _connection(self):
        conn = self._connect()
        try:
            with conn:
                yield conn
        finally:
            conn.close()
    def _init_schema(self) -> None:
        with self._connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id          TEXT PRIMARY KEY,
                    started_at  TIMESTAMP NOT NULL,
                    ended_at    TIMESTAMP DEFAULT NULL,
                    summary     TEXT DEFAULT '',
                    query_count INTEGER DEFAULT 0
                )
            """)

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    def start_session(self) -> str:
        """
        Start a new session and return its ID.
        The ID is used to link memory entries to this session.
        """
        session_id = f"{SESSION_PREFIX}_{uuid.uuid4().hex[:8]}"
        with self._connection() as conn:
            conn.execute(
                "INSERT INTO sessions (id, started_at) VALUES (?, ?)",
                (session_id, _now_utc()),
            )
        self._current_session_id = session_id
        return session_id

    def end_session(self, summary: str = "") -> Optional[str]:
        """
        Mark the current session as ended and save an optional summary.
        Returns the session ID or None if no session is active.
        """
        if not self._current_session_id:
            return None
        with self._connection() as conn:
            conn.execute(
                "UPDATE sessions SET ended_at = ?, summary = ? WHERE id = ?",
                (_now_utc(), summary, self._current_session_id),
            )
        ended_id = self._current_session_id
        self._current_session_id = None
        return ended_id

    def increment_query_count(self) -> None:
        """Increment the query counter for the current session."""
        if not self._current_session_id:
            return
        with self._connection() as conn:
            conn.execute(
                "UPDATE sessions SET query_count = query_count + 1 WHERE id = ?",
                (self._current_session_id,),
            )

    @property
    def current_session_id(self) -> Optional[str]:
        return self._current_session_id

    # ------------------------------------------------------------------
    # Session queries
    # ------------------------------------------------------------------

    def list_sessions(self, limit: int = 20) -> list:
        with self._connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM sessions ORDER BY started_at DESC LIMIT ?",
                (limit,),
            )
            return cursor.fetchall()

    def get_session(self, session_id: str) -> Optional[object]:
        with self._connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM sessions WHERE id = ?", (session_id,)
            )
            return cursor.fetchone()

