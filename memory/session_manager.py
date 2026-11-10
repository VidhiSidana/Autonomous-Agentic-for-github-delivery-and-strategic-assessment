"""
Session Manager for the Samsung PRISM Unified Engineering Agent.

Manages engineering work sessions:
  - Generates unique session IDs
  - Tracks session start/end times
  - Links memory entries to sessions
  - Hooks for automatic session capture:
      on_query, on_tool_result, on_session_end
  - Session summarization via local Ollama LLM with deterministic extractive fallback
  - Context-budgeted session resume digest
  - Stores compact event logs in session_events table
"""

import json
import logging
import sqlite3
import sys
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import MEMORY_DB_PATH, SESSION_PREFIX
from agent.policy import redact_secrets

logger = logging.getLogger(__name__)


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


class SessionManager:
    """
    Manages session lifecycle, audit hooks, and summaries.
    Sessions and event logs are stored in SQLite.
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
                    query_count INTEGER DEFAULT 0,
                    summary_mode TEXT DEFAULT '',
                    latency_s   REAL DEFAULT 0.0,
                    token_count INTEGER DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS session_events (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id  TEXT NOT NULL,
                    event_type  TEXT NOT NULL,
                    payload     TEXT NOT NULL,
                    timestamp   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # Non-destructive migrations for existing sessions table
            existing = {
                row[1]
                for row in conn.execute("PRAGMA table_info(sessions)")
            }
            migrations = {
                "summary_mode": "TEXT DEFAULT ''",
                "latency_s": "REAL DEFAULT 0.0",
                "token_count": "INTEGER DEFAULT 0",
            }
            for col, definition in migrations.items():
                if col not in existing:
                    conn.execute(f"ALTER TABLE sessions ADD COLUMN {col} {definition}")

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

    def end_session(
        self,
        summary: str = "",
        summary_mode: str = "",
        latency_s: float = 0.0,
        token_count: int = 0,
    ) -> Optional[str]:
        """
        Mark the current session as ended and save an optional summary.
        Returns the session ID or None if no session is active.
        """
        if not self._current_session_id:
            return None
        clean_summary = redact_secrets(summary)
        with self._connection() as conn:
            conn.execute(
                """
                UPDATE sessions
                SET ended_at = ?, summary = ?, summary_mode = ?, latency_s = ?, token_count = ?
                WHERE id = ?
                """,
                (_now_utc(), clean_summary, summary_mode, latency_s, token_count, self._current_session_id),
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
    # Automatic session capture hooks (TASK B2)
    # ------------------------------------------------------------------

    def on_query(
        self,
        session_id: str,
        query: str,
        intent: str = "",
    ) -> dict[str, Any]:
        """
        Automatic hook called when a user query is received.
        Records query and intent with secret redaction.
        """
        clean_query = redact_secrets(query)
        clean_intent = redact_secrets(intent)
        payload = json.dumps({
            "event": "on_query",
            "query": clean_query,
            "intent": clean_intent,
            "timestamp": _now_utc(),
        })
        with self._connection() as conn:
            conn.execute(
                "INSERT INTO session_events (session_id, event_type, payload) VALUES (?, 'query', ?)",
                (session_id, payload),
            )
            conn.execute(
                "UPDATE sessions SET query_count = query_count + 1 WHERE id = ?",
                (session_id,),
            )
        return {"session_id": session_id, "event": "query", "query": clean_query}

    def on_tool_result(
        self,
        session_id: str,
        tool_name: str,
        args: dict[str, Any],
        success: bool,
        evidence_refs: str = "",
        token_count: int = 0,
        result_summary: str = "",
    ) -> dict[str, Any]:
        """
        Automatic hook called when a tool invocation finishes.
        Records tool call arguments, success status, and evidence references.
        """
        # Redact secrets from arguments and summary
        clean_args = {k: redact_secrets(str(v)) for k, v in args.items()}
        clean_refs = redact_secrets(evidence_refs)
        clean_summary = redact_secrets(result_summary)

        payload = json.dumps({
            "event": "on_tool_result",
            "tool_name": tool_name,
            "args": clean_args,
            "success": success,
            "evidence_refs": clean_refs,
            "token_count": token_count,
            "result_summary": clean_summary,
            "timestamp": _now_utc(),
        })
        with self._connection() as conn:
            conn.execute(
                "INSERT INTO session_events (session_id, event_type, payload) VALUES (?, 'tool_result', ?)",
                (session_id, payload),
            )
        return {
            "session_id": session_id,
            "tool_name": tool_name,
            "success": success,
            "token_count": token_count,
        }

    def on_session_end(
        self,
        session_id: Optional[str] = None,
        summary: str = "",
        llm: Optional[Any] = None,
    ) -> dict[str, Any]:
        """
        Automatic hook called when a session finishes.
        Summarizes session findings:
          1. Uses local Ollama model if available.
          2. Otherwise uses deterministic extractive summarizer labelled 'extractive (LLM unavailable)'.
        Records summarization latency and token count.
        """
        target_id = session_id or self._current_session_id
        if not target_id:
            return {"error": "No active session to end"}

        events = self.get_session_events(target_id)
        queries: list[str] = []
        tools: list[str] = []
        for row in events:
            ev_type = row["event_type"]
            try:
                data = json.loads(row["payload"])
                if ev_type == "query":
                    queries.append(data.get("query", ""))
                elif ev_type == "tool_result":
                    t_name = data.get("tool_name", "tool")
                    t_args = data.get("args", {})
                    arg_str = ", ".join(f"{k}={v}" for k, v in list(t_args.items())[:2])
                    tools.append(f"{t_name}({arg_str})")
            except Exception:
                pass

        t0 = time.perf_counter()
        final_summary = summary
        mode = "provided"

        if not final_summary:
            # Attempt local LLM summarization
            llm_available = False
            if llm is not None:
                try:
                    avail, _ = llm.check_availability()
                    llm_available = bool(avail)
                except Exception:
                    llm_available = False

            if llm_available and llm is not None:
                try:
                    prompt = (
                        f"Summarize the following engineering session succinctly:\n"
                        f"Queries: {', '.join(queries[:5])}\n"
                        f"Tools invoked: {', '.join(tools[:8])}\n"
                        "Provide a 1-2 sentence technical summary of actions taken and findings."
                    )
                    final_summary = llm.chat(
                        messages=[{"role": "user", "content": prompt}],
                        system_prompt="You are an engineering assistant summarizing technical activity.",
                    ).strip()
                    mode = "llm"
                except Exception as exc:
                    logger.warning("LLM summarization failed: %s; falling back to extractive", exc)
                    llm_available = False

            if not llm_available or not final_summary:
                # Deterministic extractive summarizer
                mode = "extractive (LLM unavailable)"
                q_text = f"Queries ({len(queries)}): {'; '.join(queries[:3])}" if queries else "No queries executed"
                t_text = f"Tools ({len(tools)}): {'; '.join(tools[:5])}" if tools else "No tools called"
                final_summary = f"[{mode}] Session {target_id}. {q_text}. {t_text}."

        latency_s = round(time.perf_counter() - t0, 6)
        token_count = max(1, int(len(final_summary.split()) * 1.3))

        clean_summary = redact_secrets(final_summary)

        # Record session_end event
        payload = json.dumps({
            "event": "on_session_end",
            "summary": clean_summary,
            "mode": mode,
            "latency_s": latency_s,
            "token_count": token_count,
            "timestamp": _now_utc(),
        })
        with self._connection() as conn:
            conn.execute(
                "INSERT INTO session_events (session_id, event_type, payload) VALUES (?, 'session_end', ?)",
                (target_id, payload),
            )

        # Update sessions record
        self.end_session(
            summary=clean_summary,
            summary_mode=mode,
            latency_s=latency_s,
            token_count=token_count,
        )

        return {
            "session_id": target_id,
            "summary": clean_summary,
            "mode": mode,
            "latency_s": latency_s,
            "token_count": token_count,
        }

    # ------------------------------------------------------------------
    # Session queries and resume digest (TASK B2)
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

    def get_session_events(self, session_id: str) -> list[sqlite3.Row]:
        """Fetch all audit events for a session, ordered chronologically."""
        with self._connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM session_events WHERE session_id = ? ORDER BY id ASC",
                (session_id,),
            )
            return cursor.fetchall()

    def get_resume_digest(
        self,
        session_id: Optional[str] = None,
        max_tokens: int = 500,
    ) -> str:
        """
        Digest previous session's summary and confirmed findings into context budget.
        Truncates strictly within max_tokens budget (approx 4 chars per token).
        """
        max_chars = max_tokens * 4
        with self._connection() as conn:
            if session_id:
                sess_row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
            else:
                sess_row = conn.execute(
                    "SELECT * FROM sessions WHERE ended_at IS NOT NULL ORDER BY started_at DESC LIMIT 1"
                ).fetchone()

            if not sess_row:
                return "=== RESUMED SESSION: None (no previous sessions recorded) ==="

            target_sess = dict(sess_row)
            t_id = target_sess["id"]
            summary = target_sess.get("summary") or "(no summary recorded)"

            # Also pull confirmed/verified findings linked to this session
            findings_rows = conn.execute(
                """
                SELECT id, title, verification_status, evidence_refs
                FROM findings
                WHERE session_id = ? AND verification_status IN ('CONFIRMED', 'VERIFIED') AND is_stale = 0
                ORDER BY id ASC
                """,
                (t_id,),
            ).fetchall()

        digest_lines = [
            f"=== RESUMED SESSION DIGEST: {t_id} ===",
            f"Previous Summary: {summary}",
        ]
        if findings_rows:
            digest_lines.append("Confirmed Findings from Resumed Session:")
            for f in findings_rows:
                f_dict = dict(f)
                digest_lines.append(
                    f"  - [{f_dict['verification_status']} #{f_dict['id']}] {f_dict['title']} (refs: {f_dict.get('evidence_refs', 'none')})"
                )
        digest_lines.append("=== END RESUMED DIGEST ===")

        full_digest = "\n".join(digest_lines)
        if len(full_digest) > max_chars:
            full_digest = full_digest[: max_chars - 20] + "\n...[truncated]"
        return full_digest
