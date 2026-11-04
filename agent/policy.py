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

    Checks:
      1. Path must be non-empty.
      2. Path must resolve to a real file (no symlink escapes).
      3. Path must be within one of the configured allowed directories.
      4. No path traversal sequences allowed in the raw string.

    If BINARY_ALLOWED_DIRS is empty, the function denies all paths and
    instructs the user to configure the allowlist.
    """
    if not binary_path or not binary_path.strip():
        return False, "Binary path is empty."

    # Reject obvious traversal attempts early
    raw = binary_path.strip()
    if ".." in raw:
        return False, "Path traversal sequences ('..') are not permitted."

    try:
        resolved = Path(raw).resolve(strict=False)
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
        try:
            resolved.relative_to(allowed)
            return True, f"Authorized: path is within '{allowed}'."
        except ValueError:
            pass

        # Handle case-insensitive filesystems (such as macOS APFS / Windows NTFS)
        res_str = str(resolved).lower()
        all_str = str(allowed).lower().rstrip(os.sep) + os.sep
        if res_str.startswith(all_str) or res_str == str(allowed).lower():
            return True, f"Authorized: path is within '{allowed}'."

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

