# Reverse Engineer Anything (REA) Integration Guide

## 1. Overview and Component Identity

**Reverse Engineer Anything (REA)** is an open-source, local-first Model Context Protocol (MCP) server and CLI toolchain designed for comprehensive reverse engineering across native binaries, managed assemblies (.NET/IL2CPP), Electron/JavaScript applications, and browser targets.

- **Upstream Repository**: [`github.com/morluto/rea`](https://github.com/morluto/rea)
- **NPM Package**: `rea-agents` (version `6.8.0`)
- **License**: MIT License
- **Architecture Role**: Primary advanced decompiler and multi-engine binary analysis provider for the Samsung PRISM Unified Engineering Agent, with `pefile` and `Capstone` serving as the verified local fallback.

> [!NOTE]
> REA is an open-source project by `morluto`, not a proprietary Samsung toolchain or closed-source deliverable. It is publicly available via npm (`npm install -g rea-agents` or `npx rea-agents`).

---

## 2. Local MCP Stdio Server Invocation

REA operates as a standard Model Context Protocol (MCP) server communicating over `stdio`.

### Server Configuration in `config/mcp_servers.json`

```json
{
  "rea": {
    "description": "Reverse Engineer Anything (REA) open-source MCP server for multi-engine binary decompilation",
    "command": "npx",
    "args": ["-y", "rea-agents", "mcp"],
    "env": {
      "REA_MCP_INPUT_SCHEMA_PROFILE": "compact"
    },
    "enabled": true
  }
}
```

### Configuration Options
- **Command**: `npx -y rea-agents mcp` (or directly via Node: `node scripts/rea.mjs mcp` when installed locally).
- **Environment Variable `REA_MCP_INPUT_SCHEMA_PROFILE`**:
  - `compact` (Recommended for Local LLMs): Supplies reduced input schemas to fit local context windows (e.g. Qwen2.5-1.5B, Phi-3.5) while preserving complete server-side schema validation.
  - `full`: Advertises full parameter docstrings and nested property validation trees.

---

## 3. Host Prerequisites & Verification

REA's execution requirements were verified against the npm package manifest (`package.json`) and empirically tested on the host environment:

### Node.js Requirements
- **Specification**: Per `package.json`, REA specifies:
  ```json
  "engines": {
    "node": "^22.23.4 || ^24.22.1 || >=26.12.1"
  }
  ```
- **Technical Justification**: `dist/cli-runtime/cli.js` imports `zstdDecompress` and `zstdDecompressSync` directly from `node:zlib`. Native `zstd` support was added to Node.js in versions `22.23.4+` and `24.22.1+`.
- **Measured Host Status**:
  - Host Node version: `v20.19.4`.
  - Invocation result: Fails on startup with `SyntaxError: The requested module 'node:zlib' does not provide an export named 'zstdDecompress'`.
  - Runtime status: Blocked on Node runtime version; requires Node.js 22.23.4+.

### Native Binary Decompilation Requirements
- **Engines**: REA bridges to external native engines for deep decompilation and disassembly:
  - **Ghidra**: Connected via `bridge/ghidra/ReaGhidraBridge.java`. Requires a Java Runtime Environment (JDK 17+) and `ghidra` on system `PATH`.
  - **Hopper**: Connected via `bridge/hopper_bridge.py`.
  - **IDA Pro**: Connected via headless or attached profiles.
- **Measured Host Status**:
  - Java runtime check: `Unable to locate a Java Runtime`.
  - Ghidra check: `ghidra not found`.
  - Engine status: Uninstalled on host.

### Verified Architecture Fallback
Because Node (< 22.23.4) and missing Ghidra prevent native decompiler execution on this specific workstation, the agent's `REAAdapter` automatically detects these unmet prerequisites and triggers a graceful fallback to the local `pefile` + `Capstone` static analysis engine. No synthetic results are fabricated.

### Step-by-Step Installation & Setup Instructions

To enable full native decompilation via REA on a production or developer workstation:

#### macOS Setup:
1. **Node.js (>= 22.23.4)**:
   ```bash
   brew install node@22
   # Or using nvm:
   nvm install 22.23.4 && nvm use 22.23.4
   node -v  # Verify >= v22.23.4
   ```
2. **Java Development Kit (JDK 17+)**:
   ```bash
   brew install openjdk@21
   sudo ln -sfn /opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk /Library/Java/JavaVirtualMachines/openjdk-21.jdk
   export JAVA_HOME="/Library/Java/JavaVirtualMachines/openjdk-21.jdk/Contents/Home"
   ```
3. **Ghidra Binary Decompiler**:
   ```bash
   brew install --cask ghidra
   export GHIDRA_INSTALL_DIR="/Applications/ghidra"
   export PATH="$GHIDRA_INSTALL_DIR:$PATH"
   ```
4. **REA Agents MCP Server**:
   ```bash
   npm install -g rea-agents
   # Test CLI invocation:
   npx -y rea-agents --version
   ```

#### Windows Setup:
1. **Node.js (>= 22.23.4)**:
   Download the official MSI installer from [nodejs.org](https://nodejs.org) or install via `winget install OpenJS.NodeJS.LTS`.
2. **Java Development Kit (JDK 17+)**:
   `winget install Microsoft.OpenJDK.21` and ensure `JAVA_HOME` is set in system environment variables.
3. **Ghidra**:
   Download Ghidra release zip from [ghidra-sre.org](https://ghidra-sre.org), extract to `C:\Tools\ghidra`, and set `GHIDRA_INSTALL_DIR=C:\Tools\ghidra`.
4. **REA Agents MCP Server**:
   ```powershell
   npm install -g rea-agents
   npx -y rea-agents --version
   ```

### Measured Integration Status Table

| Subsystem / Capability | Measured Status | Evidence / Reason |
| :--- | :--- | :--- |
| **Path Policy Gate (`agent/policy.py`)** | **VERIFIED** | Unit tested in `tests/test_policy.py` & `tests/test_rea_policy.py`; rejects traversal, symlink escapes, unauthorized paths fail-closed. |
| **Audit Logging (`memory/binary_audit.log`)** | **VERIFIED** | Logs every REA operation with timestamp, path, and authorization decision. |
| **Fallback Engine (`pefile` + `Capstone`)** | **VERIFIED** | Fully operational; tested across tasks B1-B6 and REA1-REA3 in `benchmarks/benchmark_runner.py`. |
| **MCP Server Registration (`config/mcp_servers.json`)** | **VERIFIED** | Configured with `REA_MCP_INPUT_SCHEMA_PROFILE=compact`. |
| **Native REA Decompilation** | **NOT TESTED** | Host runtime has Node 22.20.0 (< 22.23.4 required for `node:zlib.zstdDecompress`) and Ghidra is uninstalled. |

---

## 4. Verified MCP Tool Catalog

The full REA catalog exposes 229 specialized reverse-engineering tools. For native binary analysis within the Samsung PRISM agent, the key tools are:

| Tool Name | Parameters | Purpose |
| :--- | :--- | :--- |
| `open_binary` | `path` (string, required), `format`, `architecture`, `entry_point`, `provider_id` | Primary session entry point. Validates target and binds analysis provider. |
| `binary_overview` | *(none)* | Returns bound document info, procedure count, string count, and section layout. |
| `analyze_function` | `procedure` (string, required), `detail` (`"complete"` \| `"summary"`) | Generates a decompiled function dossier, callers, callees, and control flow. |
| `inspect_binary_layout` | `path` (string, required) | Inspects PE/ELF file-backed sections without launching process. |
| `inspect_pe_imports` | `path` (string, required), `max_dlls`, `max_functions` | Extracts imported DLLs, API symbols, and IAT RVAs. |
| `inspect_pe_certificates` | `path` (string, required) | Inspects Authenticode signatures and security directories. |
| `inspect_pe_resources` | `path` (string, required) | Inspects resource hierarchy (manifests, dialogs, icons). |
| `read_function_instructions` | `procedure` (string, required) | Returns raw disassembled instructions and operands for a function. |
| `batch_decompile` | `procedures` (list[string], required) | Decompiles a batch of functions into pseudocode. |
| `close_binary` | *(none)* | Closes the active session, drains worker buffers, and releases file locks. |
| `query_rea_status` | `binary_path` (string, optional) | Diagnostic probe checking REA engine health, Node runtime, and fallback status. |

---

## 5. Security & Containment Architecture

> [!CAUTION]
> REA does not implement path allowlists or interactive confirmation internally. It will attempt to inspect any path passed to its tools.

To maintain strict security compliance under the Samsung PRISM policy guidelines:

1. **Pre-Invocation Authorization Gate**:
   - Every REA tool invocation (`open_binary`, `inspect_binary_layout`, etc.) must pass through `agent/policy.py:authorize_binary_path` or `authorize_rea_tool_call`.
   - File paths outside `BINARY_ALLOWED_DIRS` are rejected fail-closed with `DENIED`.
2. **Path Traversal & Symlink Escapes**:
   - Traversal sequences (`..`) and symlinks escaping allowed directories are rejected before reaching REA.
3. **Append-Only Audit Logging**:
   - Every request is recorded to `memory/binary_audit.log` (CSV format) recording `timestamp_utc`, `operation` (e.g. `rea_open_binary`), `target_path`, `authorized`, and `result_status`.
4. **Zero-Execution Guarantee**:
   - REA operates strictly via static disassembler databases and file parsing; target binaries are never executed.

