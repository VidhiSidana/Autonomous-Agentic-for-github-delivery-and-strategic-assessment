#!/usr/bin/env bash
# ==============================================================================
# Samsung PRISM Unified Engineering Agent - macOS / Linux Setup Script
# ==============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "=== Samsung PRISM Engineering Agent Setup ==="
echo "Project Directory: ${PROJECT_ROOT}"

# 1. Check Python version (>= 3.11 required)
PYTHON_BIN=""
for cmd in python3.14 python3.13 python3.12 python3.11 python3; do
    if command -v "$cmd" >/dev/null 2>&1; then
        VER=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
        MAJOR=$("$cmd" -c "import sys; print(sys.version_info.major)")
        MINOR=$("$cmd" -c "import sys; print(sys.version_info.minor)")
        if [ "$MAJOR" -eq 3 ] && [ "$MINOR" -ge 11 ]; then
            PYTHON_BIN="$cmd"
            echo "[OK] Found compatible Python: $cmd (v$VER)"
            break
        fi
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    echo "[ERROR] Python 3.11 or higher is required. Please install Python 3.11, 3.12, 3.13, or 3.14."
    exit 1
fi

# 2. Virtual Environment Setup
VENV_DIR="${PROJECT_ROOT}/.venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment at ${VENV_DIR}..."
    "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

# Activate venv
# shellcheck source=/dev/null
source "${VENV_DIR}/bin/activate"
echo "[OK] Virtual environment activated: $(python -V)"

# 3. Install Package and Dependencies
echo "Installing package in editable mode..."
pip install --upgrade pip
pip install -e "${PROJECT_ROOT}"

# 4. Smoke Test CLI Entry Point
echo "Verifying 'prism-agent' CLI entry point..."
prism-agent --version || python -m agent.main --version
echo "[OK] CLI entry point verified successfully."

# 5. Check Local LLM (Ollama)
echo "Checking Ollama daemon..."
if curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
    echo "[OK] Ollama is active on http://localhost:11434"
else
    echo "[WARNING] Ollama daemon is not responding on http://localhost:11434."
    echo "          Start Ollama with: ollama serve"
fi

# 6. Check REA / Reverse Engineering Prerequisites
echo "Checking REA (Reverse Engineer Anything) prerequisites..."
if command -v node >/dev/null 2>&1; then
    NODE_VER=$(node -v)
    echo "  Node.js: $NODE_VER"
else
    echo "  Node.js: Not found"
fi

if command -v ghidra >/dev/null 2>&1 || [ -n "$GHIDRA_INSTALL_DIR" ]; then
    echo "  Ghidra: Installed"
else
    echo "  Ghidra: Not installed (agent will use verified pefile + Capstone fallback)"
fi

echo ""
echo "=== Setup Complete! ==="
echo "To activate the environment:"
echo "  source ${VENV_DIR}/bin/activate"
echo "To run tests:"
echo "  python -m unittest discover -s tests -p 'test_*.py' -t ."
echo "To run the agent:"
echo "  prism-agent --help"

