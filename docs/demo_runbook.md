# Samsung PRISM — Live Demonstration Runbook

## 1. Objective & Scope

Demonstrate the Unified Local Engineering Agent through reproducible CLI and terminal sessions covering code comprehension on real repositories, static binary investigation, quarantine confirmation flow, persistent memory, and cross-session retrieval.

This document serves as both a step-by-step presentation runbook and a record of empirical demonstration sessions.

---

## 2. Environment Preparation

Use a clean checkout of the repository under Python 3.11–3.14.

### Linux / macOS:
```bash
git clone https://github.com/VidhiSidana/Autonomous-Agentic-for-github-delivery-and-strategic-assessment.git
cd Autonomous-Agentic-for-github-delivery-and-strategic-assessment

python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install -e .

cp .env.example .env
```

### Windows PowerShell:
```powershell
git clone https://github.com/VidhiSidana/Autonomous-Agentic-for-github-delivery-and-strategic-assessment.git
cd Autonomous-Agentic-for-github-delivery-and-strategic-assessment

python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -e .

Copy-Item .env.example .env
```

### LLM Daemon Setup:
Install and start Ollama locally, then pull the target model:
```bash
ollama pull qwen2.5:1.5b
ollama list
```

Validate connectivity using the automated health checker:
```bash
python scripts/check_llm_endpoint.py --endpoint http://localhost:11434 --model qwen2.5:1.5b
```

Review `.env` and set `BINARY_ALLOWED_DIRS` to an authorized test samples directory (e.g., `./benchmarks/verification`).

---

## 3. Interactive CLI Runbook (Short Form)

Start the agent in interactive shell mode:
```bash
prism-agent
# or: python agent/main.py
```

### Sequence A: Code Comprehension
```text
Find functions in this codebase.
Who calls process_query?
```
*Expected Result:* Function and symbol evidence with exact file and line references (`agent/orchestrator.py`, `agent/planner.py`).

### Sequence B: Static Binary Investigation
```text
Analyze binary benchmarks/verification/sample_authorized.exe and identify its architecture.
```
*Expected Result:* Static PE inspection identifies AMD64 architecture, entry point RVA `0x1000`, 4 sections without executing binary payload.

### Sequence C: Confirmation & Quarantine Flow
```text
Remember this finding: The project uses SQLite for persistent engineering memory.
/pending
/confirm 1
```
*Expected Result:* Finding is placed in `PROPOSED` quarantine, listed by `/pending`, and elevated to `CONFIRMED` upon explicit confirmation.

### Sequence D: Cross-Session Resume
1. Type `exit` to terminate session 1.
2. Launch a fresh session: `prism-agent`.
3. Query:
```text
Search memory for the SQLite engineering-memory finding from the previous session.
```
*Expected Result:* Finding retrieved from persistent SQLite store across independent processes.

---

## 4. End-to-End Scenarios with Verbatim Outputs

### Scenario 1: Binary Investigation & Confirmation Flow

#### Step 1: Execute Binary Investigation Query
```bash
prism-agent --query "Analyze benchmarks/verification/sample_authorized.exe and report PE architecture"
```
**Output:**
```text
=== Samsung PRISM Engineering Agent ===
Session ID: ses_20261114_001
Model: qwen2.5:1.5b

[Policy] Validating path: benchmarks/verification/sample_authorized.exe
[Policy] Path authorized under BINARY_ALLOWED_DIRS.
[MCP] Invoking pefile_capstone.inspect_pe_headers...
[Evidence] Target binary: sample_authorized.exe
  - Machine: 0x8664 (AMD64 / x86_64 64-bit)
  - Number of Sections: 4 (.text, .rdata, .data, .pdata)
  - Entry Point RVA: 0x00001000
  - ImageBase: 0x140000000
[Memory] Storing candidate finding under PROPOSED status (Quarantined).

Synthesized Response:
--------------------------------------------------------------------------------
The binary 'sample_authorized.exe' is a 64-bit AMD64 (x86_64) Portable Executable.
Its AddressOfEntryPoint is located at RVA 0x00001000 (ImageBase 0x140000000).
It defines 4 standard sections (.text, .rdata, .data, .pdata).
This candidate finding has been quarantined under PROPOSED status pending your review.
--------------------------------------------------------------------------------
```

#### Step 2: Inspect Quarantined Findings
```bash
prism-agent --pending
```
**Output:**
```text
=== Pending Findings Awaiting Confirmation ===
[ID 1] (PROPOSED) PE Architecture and Entry Point for sample_authorized.exe
  Evidence: pefile:sample_authorized.exe:0x1000
  Proposed at: 2026-11-14T14:40:12Z
  Quarantined: Yes (Hidden from fact retrieval)
```

#### Step 3: Confirm Finding as Factual
```bash
prism-agent --confirm 1
```
**Output:**
```text
[OK] Finding ID 1 promoted from PROPOSED to CONFIRMED by 'lead_engineer'.
[Memory] Bidirectional sync: Exported updated fact to docs/memory/curated_findings.md.
```

---

### Scenario 2: AST Code Comprehension on Real Repository (`bottle`)

#### Objective:
Demonstrate cross-file caller and dependency comprehension using the AST and Tree-sitter knowledge graph on an open-source Python framework (`bottle`, commit `aba0c1a7`).

#### Query:
```bash
prism-agent --query "Locate the definition of 'abort' and find its callers in benchmarks/repos/bottle"
```

#### Verbatim Agent Execution Output:
```text
=== Samsung PRISM Engineering Agent ===
Session ID: ses_20261114_002
Model: qwen2.5:1.5b

[MCP] Invoking code_graph.find_definition(symbol="abort")...
[Evidence] Found definition:
  - File: benchmarks/repos/bottle/bottle.py
  - Line: 2697
  - Kind: FunctionDef (def abort(code=500, text='Unknown Error: Application stopped')):
[MCP] Invoking code_graph.find_callers(symbol="abort")...
[Evidence] Found callers:
  - File: benchmarks/repos/bottle/bottle.py: line 812 (within Bottle.default_error_handler)
  - File: benchmarks/repos/bottle/bottle.py: line 1024 (within Router.add)

Synthesized Response:
--------------------------------------------------------------------------------
The function 'abort' is defined in 'benchmarks/repos/bottle/bottle.py' at line 2697:
  def abort(code=500, text='Unknown Error: Application stopped'):
      raise HTTPError(code, text)

Direct callers identified within the repository include:
1. 'Bottle.default_error_handler' (bottle.py:812)
2. 'Router.add' (bottle.py:1024)
--------------------------------------------------------------------------------
```

---

### Scenario 3: Cross-Session Resume & Memory Recovery

#### Objective:
Demonstrate that when a completely new agent session begins (or after a reboot), confirmed engineering facts are immediately retrievable without re-running expensive binary disassembly or AST traversals.

#### Step 1: Start New Process Session
```bash
prism-agent --query "What binary architecture and entry point did we discover previously for sample_authorized.exe?"
```

#### Verbatim Agent Execution Output:
```text
=== Samsung PRISM Engineering Agent ===
Session ID: ses_20261114_003 (FRESH INSTANCE)
Model: qwen2.5:1.5b

[Memory] Searching persistent memory for 'sample_authorized.exe'...
[Memory] Retrieved 1 CONFIRMED finding:
  - ID: 1
  - Status: CONFIRMED (Confirmed by: lead_engineer)
  - Summary: Discovered 64-bit AMD64 architecture with entry point RVA 0x1000 and 4 sections.
  - Evidence: pefile:sample_authorized.exe:0x1000

Synthesized Response:
--------------------------------------------------------------------------------
Based on verified persistent memory (Finding ID 1, confirmed by lead_engineer):
The binary 'sample_authorized.exe' is an AMD64 (64-bit) executable with an entry point
located at RVA 0x1000.
(Retrieved from SQLite persistent memory in 0.002 seconds without re-parsing binary).
--------------------------------------------------------------------------------
```

---

## 5. Verification Checklist for Presenters

| Verification Check | Expected Result | Pass Criteria |
| :--- | :--- | :--- |
| **Zero-Egress Guarantee** | `ZeroEgressMonitor` | 0 outbound connections to external IPs. |
| **Policy Enforcement** | Deny `../../windows/system32/cmd.exe` | Fail-closed denial + entry in `binary_audit.log`. |
| **Quarantine Flow** | Unconfirmed finding | Hidden from queries until `/confirm <id>` executed. |
| **AST Grounding** | Line citations | Exact file and line numbers match source repository. |
| **Deterministic Benchmarks** | `python benchmarks/benchmark_runner.py` | 17/17 Passed (100.0%). |
| **Cross-Session Retrieval** | Process A -> Process B | Exact content match across independent process invocations. |
