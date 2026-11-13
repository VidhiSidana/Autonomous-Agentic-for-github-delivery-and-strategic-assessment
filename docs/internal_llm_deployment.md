# Samsung PRISM — Internal Local LLM Deployment Guide

## 1. Purpose and supported deployment mode

The Unified Engineering Agent uses a configurable Ollama endpoint for local LLM inference. The current configuration defaults to:

- Base URL: `http://localhost:11434`
- Model: `qwen2.5:1.5b`
- Timeout: `120` seconds
- Temperature: `0.1`

The implementation is configured around the Ollama API. An organisation-managed endpoint must therefore expose the Ollama API routes and response format expected by the project's LLM client. A generic OpenAI-compatible endpoint is not automatically interchangeable; adapter work and testing would be required if the target service exposes a different API.

## 2. Deployment topology

Recommended logical topology:

```text
Developer workstation / approved internal host
  ├── Unified Engineering Agent (Python 3.11)
  │     ├── Planner and Orchestrator
  │     ├── MCP tool servers (local stdio processes)
  │     ├── SQLite engineering memory (local disk)
  │     └── Ollama API client
  │              |
  │              v
  └── Approved internal Ollama endpoint
          └── Approved local/open-weight model
```

Keep source repositories, binary samples, SQLite memory and audit logs within approved organisational boundaries. The host firewall/network policy should restrict endpoint access to approved clients and prevent unintended public exposure.

## 3. Configure the endpoint

Create a local environment file from the template:

Windows PowerShell:

```powershell
Copy-Item .env.example .env
notepad .env
```

Linux/macOS:

```bash
cp .env.example .env
# Edit .env with the approved local configuration
```

Set the values to those supplied by the internal platform administrator:

```ini
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:1.5b
OLLAMA_TIMEOUT=120
OLLAMA_TEMPERATURE=0.1
OLLAMA_MAX_TOKENS=0
```

For a managed internal endpoint, replace the base URL and model tag with the exact values provided by the administrator. Do not guess endpoint paths, model aliases or authentication settings. The current template does not document a dedicated API-key variable; if the internal service requires authentication, verify the client's supported authentication mechanism before deployment rather than placing credentials in source code.

## 4. Install the agent

Requirements:

- Python 3.11 or compatible supported version.
- Git.
- Network access to the approved internal Ollama endpoint.
- Required MCP executables and runtime dependencies enabled in `config/mcp_servers.json`.
- Approved local storage for SQLite memory, curated Markdown and audit logs.

Windows PowerShell:

```powershell
git clone https://github.com/VidhiSidana/Autonomous-Agentic-for-github-delivery-and-strategic-assessment.git
cd Autonomous-Agentic-for-github-delivery-and-strategic-assessment
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Linux/macOS:

```bash
git clone https://github.com/VidhiSidana/Autonomous-Agentic-for-github-delivery-and-strategic-assessment.git
cd Autonomous-Agentic-for-github-delivery-and-strategic-assessment
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env
```

Review `config/mcp_servers.json`. The code graph server and REA integration may require separately installed executables/runtimes; the Python requirements file alone does not install every external MCP server.

## 5. Validate endpoint connectivity

For a local Ollama installation:

```powershell
ollama list
ollama run qwen2.5:1.5b "Reply with the word READY."
```

For a managed endpoint, use the health-check procedure approved by the endpoint administrator. Confirm that:
1. The hostname resolves only within the intended network.
2. The endpoint is reachable from the agent host.
3. The configured model tag exists.
4. The model can return a simple response.
5. Access logs and network controls meet organisational policy.

Do not use public model endpoints for proprietary source code or binary findings unless explicitly approved by the organisation.

## 6. Configure binary-analysis boundaries

Set `BINARY_ALLOWED_DIRS` to approved sample directories only. Example:

```ini
BINARY_ALLOWED_DIRS=C:\\PRISM\\authorised_samples
```

The policy is deny-by-default when no allowed directory is configured. Do not set the allowlist to an entire drive or broad user profile. Binary analysis is intended to be static; the target binary is not to be executed by the agent.

## 7. Data handling and operational security

- Keep `.env`, credentials, tokens, proprietary binaries and private logs out of Git.
- Restrict filesystem permissions on `memory/engineering_memory.db`, curated memory and audit logs.
- Back up SQLite memory only under the organisation's approved retention policy.
- Treat stored engineering findings as potentially sensitive source-derived data.
- Use firewall rules to restrict the Ollama endpoint to approved hosts.
- Do not describe the application-level socket monitor as proof of host-wide air-gapping. Host firewall or network isolation controls are a separate deployment responsibility.
- Review binary authorization and audit logs periodically.

## 8. Launch and smoke test

Activate the environment and run:

```powershell
python agent/main.py
```

Perform a simple code query and a memory retrieval query. Then exit with `exit` and verify the clean shutdown message.

Run the automated test suite:

```powershell
python -m unittest discover -s tests -p "test_*.py" -t .
```

Run the ground-truth benchmark when the required fixtures, local model and MCP tools are available:

```powershell
python benchmarks/benchmark_runner.py
```

Record the actual date, commit SHA, model tag, endpoint type, test results and any skipped tests in the deployment acceptance record.

## 9. Deployment acceptance record

| Item | Value to be completed by deployment owner |
|---|---|
| Environment / host | |
| Repository commit SHA | |
| Python version | |
| Ollama version | |
| Internal endpoint identifier (no secret) | |
| Model tag | |
| Binary allowlist path | |
| MCP dependencies verified | |
| Smoke test | |
| Test suite result | |
| Network/security approval reference | |
| Deployment owner and date | |

**Important:** This guide describes the current Ollama-based integration. Validate the target organisation's endpoint contract, authentication, TLS, firewall and data-handling requirements before connecting production or proprietary workloads.
