# Samsung PRISM — Internal Local LLM Deployment Guide

## 1. Overview & Scope

The Samsung PRISM Unified Engineering Agent is designed from first principles to operate **strictly on-premise without external network egress**. All LLM inference is performed locally via Ollama or routed to internal enterprise model servers (Ollama, vLLM, llama.cpp, or TGI).

> [!IMPORTANT]
> **Zero-Egress Security Policy:** At no time does the agent transmit source code, binary payloads, findings, or developer queries to external cloud endpoints (e.g. OpenAI, Anthropic, Google Cloud). All network calls are strictly restricted to localhost (`127.0.0.1`, `::1`) or internal RFC 1918 private IP addresses.

---

## 2. Supported Deployment Topologies

### Topology A: Local Single-Workstation (Default / Verified)
- **Host:** Developer laptop or engineering workstation (e.g., Apple Silicon M-series, Linux x86_64 workstation with NVIDIA GPU, Windows 11 workstation).
- **Model Server:** Local Ollama daemon listening on `http://127.0.0.1:11434`.
- **Model Files:** Stored locally in `~/.ollama/models`.
- **Status:** **VERIFIED** and operational in the test harness.

### Topology B: Air-Gapped Engineering Enclave (Air-Gapped Lab)
- **Host:** Air-gapped workstation or compute blade with physical network isolation.
- **Model Weights:** Provisioned via internal enterprise artifact mirror or secure USB transfer.
- **Model Server:** Local vLLM or Ollama instance bound to `127.0.0.1`.
- **Status:** **MANUAL** (requires physical deployment per laboratory security protocols).

### Topology C: Internal Enterprise Inference Cluster (Dedicated GPU Pool)
- **Host:** Secure internal Kubernetes / OpenShift cluster hosting vLLM or Ollama instances behind an internal corporate gateway.
- **Endpoint:** Internal DNS or RFC 1918 private IP (e.g., `http://10.240.x.x:8000/v1` or `http://prism-llm.internal.samsung.com:11434`).
- **Authentication:** Internal mTLS or bearer token header configured in `.env`.
- **Status:** **MANUAL** (requires internal enterprise credentials and deployment approval).

---

## 3. Hardware Requirements & Sizing

| Workstation / Server Class | Minimum RAM / VRAM | Recommended Models | Expected Latency (Per Turn) |
| :--- | :--- | :--- | :--- |
| **Standard Laptop (e.g., Apple M4 16GB)** | 16 GB Unified Memory | `qwen2.5:1.5b` (Default) <br> `phi3.5:latest` | ~0.5s – 3.2s |
| **Heavy Engineering Workstation** | 32 GB – 64 GB RAM | `llama3.1:8b` (Q4_K_M) | ~2.0s – 5.0s |
| **Dedicated Enterprise Inference Node** | 1x NVIDIA A10G / L40 / A100 | `llama3.1:8b` (FP16/AWQ) <br> `mistral-nemo:12b` | ~0.3s – 1.0s |

---

## 4. Configuration & Environment Setup

Create a local environment file from the template:

### Windows PowerShell:
```powershell
Copy-Item .env.example .env
notepad .env
```

### Linux / macOS:
```bash
cp .env.example .env
nano .env
```

Set the inference endpoint variables:
```ini
# Target model tag
OLLAMA_MODEL="qwen2.5:1.5b"

# Inference endpoint (must be loopback or RFC1918 private IP)
OLLAMA_BASE_URL="http://127.0.0.1:11434"

# Optional token generation cap (prevents run-away loops on small models)
OLLAMA_MAX_TOKENS=512

# Request timeout in seconds
OLLAMA_TIMEOUT=120

# Inference temperature
OLLAMA_TEMPERATURE=0.1
```

For a managed internal endpoint, replace the base URL and model tag with the exact values provided by the platform administrator.

---

## 5. Automated Healthcheck & Zero-Egress Verification

Use `scripts/check_llm_endpoint.py` to validate endpoint health and security compliance prior to running agent sessions:

```bash
python scripts/check_llm_endpoint.py --endpoint http://localhost:11434 --model qwen2.5:1.5b
```

### Automated Verification Steps Performed:
1. **Zero-Egress Host Validation:** Resolves hostname and verifies target is loopback (`127.0.0.1`, `::1`) or private RFC 1918 address (`10.x.x.x`, `172.16-31.x.x`, `192.168.x.x`). Fails closed if a public internet IP is detected.
2. **Endpoint Health & Tags:** Queries `/api/tags` and verifies response within timeout.
3. **Model Verification:** Confirms requested model is loaded in memory or on disk.
4. **End-to-End Generation Test:** Executes a test generation (`num_predict: 16`) and measures actual round-trip latency.

---

## 6. Deployment Verification Status

| Step | Validation Method | Measured Status | Notes |
| :--- | :--- | :--- | :--- |
| **Local Ollama Daemon** | `scripts/check_llm_endpoint.py` | **VERIFIED** | Verified with `qwen2.5:1.5b`, `phi3.5:latest`, and `llama3.1:8b`. |
| **Socket Egress Monitor** | `ZeroEgressMonitor` in `benchmarks/e2e_eval.py` | **VERIFIED** | Intercepts `socket.connect`; 0 non-local connections detected across all evaluation tasks. |
| **Enterprise GPU Cluster Deployment** | Internal cluster provisioning | **MANUAL** | Pending physical integration into Samsung on-premise infrastructure. |
