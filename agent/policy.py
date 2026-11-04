"""
Policy and audit module for the Samsung PRISM Unified Engineering Agent.

Responsibilities:
  - Binary analysis path authorization (allowlist-based)
  - Path traversal prevention
  - Audit logging for sensitive operations
  - Secret redaction helpers

No binary outside an approved directory may be analysed.
No binary is ever executed.
"""

import csv
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Secret patterns to redact from logs and stored text
# ---------------------------------------------------------------------------
_SECRET_PATTERNS: list[str] = [
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "private_key",
    "client_secret",
    "access_key",
    "auth_token",
]


def redact_secrets(text: str) -> str:
    """
    Redact lines or values that appear to contain sensitive information.
    This is a heuristic filter — it is not a substitute for proper secret
    management. Returns the redacted text.
    """
    if not isinstance(text, str):
        return text

    lines = text.splitlines()
    redacted = []

    for line in lines:
        lower = line.lower()
        if any(pattern in lower for pattern in _SECRET_PATTERNS):
            # Redact the value portion (after '=' or ':') if present
            for sep in ("=", ":"):
                if sep in line:
                    key, _, _ = line.partition(sep)
                    redacted.append(f"{key}{sep}[REDACTED]")
                    break
            else:
                redacted.append("[REDACTED LINE]")
        else:
            redacted.append(line)

    return "\n".join(redacted)


# ---------------------------------------------------------------------------
# Binary path authorization
# ---------------------------------------------------------------------------

def _get_allowed_dirs() -> list[Path]:
    """
    Load the binary allowlist from configuration and environment.
    Falls back to an empty list (deny all) if not configured.
    Returns resolved absolute Path objects.
    """
    import config.settings
    dirs = [Path(d).resolve() for d in config.settings.BINARY_ALLOWED_DIRS]

    env_raw = os.getenv("BINARY_ALLOWED_DIRS", "")
    if env_raw:
        for d in env_raw.split(","):
            if d.strip():
                p = Path(d.strip()).resolve()
                if p not in dirs:
                    dirs.append(p)
    return dirs


def authorize_binary_path(binary_path: str) -> tuple[bool, str]:
    """
    Validate that *binary_path* is inside an approved directory.

    Returns (is_authorized: bool, message: str).

    Security Checks:
      1. Path must be non-empty.
      2. Path traversal sequences ('..') are strictly rejected.
      3. Resolved canonical paths are used to prevent symlink escapes.
      4. Containment uses canonical hierarchy and filesystem-level inode checks
         (os.path.samefile) rather than unsafe string-prefix operations.
      5. Sibling directories with matching prefixes (e.g. /dir_sibling) are rejected.
    """
    if not binary_path or not binary_path.strip():
        return False, "Binary path is empty."

    raw = binary_path.strip()

    # Reject obvious traversal attempts early
    try:
        raw_parts = Path(raw).parts
        if any(p == ".." for p in raw_parts) or ".." in raw:
            return False, "Path traversal sequences ('..') are not permitted."
    except Exception as exc:
        return False, f"Invalid path structure: {exc}"

    try:
        resolved = Path(raw).resolve()
    except (OSError, ValueError) as exc:
        return False, f"Invalid path: {exc}"

    allowed_dirs = _get_allowed_dirs()

    if not allowed_dirs:
        return False, (
            "No binary analysis directories are configured. "
            "Set BINARY_ALLOWED_DIRS in your .env file to a comma-separated "
            "list of permitted directories."
        )

    for allowed in allowed_dirs:
        allowed_res = allowed.resolve()

        # Check 1: Canonical pathlib containment
        try:
            resolved.relative_to(allowed_res)
            return True, f"Authorized: path is within '{allowed_res}'."
        except ValueError:
            pass

        # Check 2: Filesystem-aware directory identity via os.path.samefile.
        # Walks parent hierarchy to verify if any parent physically matches allowed_res.
        # This handles case-preserving filesystems without unsafe prefix strings.
        if allowed_res.exists():
            for parent in (resolved, *resolved.parents):
                if parent.exists():
                    try:
                        if os.path.samefile(parent, allowed_res):
                            return True, f"Authorized: path is within '{allowed_res}'."
                    except OSError:
                        pass

    readable_dirs = ", ".join(str(d) for d in allowed_dirs)
    return False, (
        f"Access denied. '{resolved}' is not within any approved directory. "
        f"Approved: {readable_dirs}"
    )


# ---------------------------------------------------------------------------
# Audit logging
# ---------------------------------------------------------------------------

def _get_audit_log_path() -> Path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from config.settings import BINARY_AUDIT_LOG
    return BINARY_AUDIT_LOG


def write_audit_event(
    operation: str,
    target_path: str,
    authorized: bool,
    result_status: str,
    session_id: str = "",
    extra: str = "",
) -> None:
    """
    Append a structured audit record for a binary-analysis request.

    Fields written (CSV):
      timestamp_utc, session_id, operation, target_path,
      authorized, result_status, extra
    """
    audit_path = _get_audit_log_path()

    # Ensure parent directory exists
    audit_path.parent.mkdir(parents=True, exist_ok=True)

    write_header = not audit_path.exists() or audit_path.stat().st_size == 0

    try:
        with open(audit_path, "a", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            if write_header:
                writer.writerow([
                    "timestamp_utc",
                    "session_id",
                    "operation",
                    "target_path",
                    "authorized",
                    "result_status",
                    "extra",
                ])
            writer.writerow([
                datetime.now(timezone.utc).isoformat(),
                session_id or "unknown",
                operation,
                # Do NOT log the full binary content — only the path
                str(target_path),
                "yes" if authorized else "no",
                result_status,
                redact_secrets(extra)[:256],  # cap extra info length
            ])
    except OSError as exc:
        logger.error("Failed to write audit event: %s", exc)

