"""
Central configuration for the Samsung PRISM Unified Engineering Agent.

Loads settings from environment variables (and an optional .env file).
All modules import from here — no hardcoded values in business logic.
"""

import os
from pathlib import Path

# Try to load .env file if python-dotenv is available
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(dotenv_path=_env_path, override=False)
except ImportError:
    pass  # python-dotenv not installed; rely on actual environment variables

# ----------------------------------------------------------
# Project root (absolute, so imports work from any CWD)
# ----------------------------------------------------------
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent

# ----------------------------------------------------------
# Local LLM (Ollama)
# ----------------------------------------------------------
OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "qwen2.5:1.5b")
OLLAMA_TIMEOUT: int = int(os.getenv("OLLAMA_TIMEOUT", "120"))
OLLAMA_TEMPERATURE: float = float(os.getenv("OLLAMA_TEMPERATURE", "0.1"))
OLLAMA_MAX_TOKENS: int = int(os.getenv("OLLAMA_MAX_TOKENS", "0"))

# ----------------------------------------------------------
# MCP servers
# ----------------------------------------------------------
MCP_CONFIG_PATH: Path = PROJECT_ROOT / os.getenv(
    "MCP_CONFIG_PATH", "config/mcp_servers.json"
)

# ----------------------------------------------------------
# Binary analysis security
# ----------------------------------------------------------
_raw_allowed = os.getenv("BINARY_ALLOWED_DIRS", "")
BINARY_ALLOWED_DIRS: list[Path] = (
    [Path(d.strip()).resolve() for d in _raw_allowed.split(",") if d.strip()]
    if _raw_allowed
    else []
)
BINARY_AUDIT_LOG: Path = PROJECT_ROOT / os.getenv(
    "BINARY_AUDIT_LOG", "memory/binary_audit.log"
)

# ----------------------------------------------------------
# Memory
# ----------------------------------------------------------
MEMORY_DB_PATH: Path = PROJECT_ROOT / os.getenv(
    "MEMORY_DB_PATH", "memory/engineering_memory.db"
)
MEMORY_MARKDOWN_DIR: Path = PROJECT_ROOT / os.getenv(
    "MEMORY_MARKDOWN_DIR", "memory/markdown_store"
)

# ----------------------------------------------------------
# Agent
# ----------------------------------------------------------
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
SESSION_PREFIX: str = os.getenv("SESSION_PREFIX", "session")

