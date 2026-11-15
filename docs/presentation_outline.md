> [!IMPORTANT]
> **Presentation status correction (2026-11-15):** Slide 12's historical “Milestone 2 Status: 100% COMPLETE” wording must not be used as an unconditional final-closure claim. The latest committed E2E evidence is 20/22 (90.9%) for each of three models, with MT1 and RS1 failing and 1/3 false-hypothesis assertions incorrect. The 17/17 ground-truth benchmark remains a separate passing result. Final demo evidence, Windows/Python 3.11 clean-install verification, internal Samsung deployment validation and reviewer sign-off are still pending. Update Slide 12 to say “Core implementation and deterministic benchmark complete; final E2E hardening and operational closure pending.” See [final closure status](final_closure_status.md).

---

# Samsung PRISM: Unified Local-LLM Engineering Agent
## Final Presentation & Technical Milestone 2 Closure Outline

---

### Slide 1: Title & Executive Summary
- **Title**: Samsung PRISM — Unified Local-LLM Engineering Agent
- **Subtitle**: On-Premise Autonomous Agent for Code Comprehension, Binary Investigation, and Persistent Memory
- **Target Deliverable**: Milestone 2 Completion & Final Technical Closure
- **Presenter**: Samsung PRISM Engineering Agent Development Team
- **Core Value Proposition**: A 100% local, zero-egress engineering assistant that unifies AST code comprehension, static binary analysis, and verified cross-session memory on commodity hardware.

---

### Slide 2: The Engineering Problem & Enterprise Requirements
- **Fragmented Context**: Engineers constantly switch between static disassemblers (IDA, Ghidra), source code explorers (grep, ctags), and ad-hoc scratchpads.
- **Strict IP Protection (Zero-Egress)**: Proprietary source code and proprietary firmware/binaries must **never** leave internal enterprise firewalls. Cloud LLMs (OpenAI, Anthropic) are strictly prohibited.
- **Small-Model Hallucinations**: Sub-8B parameter models easily hallucinate tool parameters, invent nonexistent files/functions, and lose context in deep call trees.
- **Goal**: Ground every answer in empirical, machine-verifiable evidence.

---

### Slide 3: Unified Agent Architecture & Data Flow
- **Four Core Subsystems**:
  1. **Planner & Orchestrator**: Translates developer intent into typed execution plans.
  2. **Model Context Protocol (MCP) Clients**: Standardized `stdio` interfaces for code graphs and binary disassemblers.
  3. **Unified Persistent Memory**: SQLite database with bidirectional Markdown sync, deduplication, and stale detection.
  4. **Evidence Aggregation & Synthesis**: Grounds local LLM output in `VERIFIED` facts while flagging `HYPOTHESIS` items.
- **Security Interceptor**: Policy enforcement gate ensures fail-closed path allowlisting and append-only audit logging.

---

### Slide 4: Unified Memory Layer & Engineer Confirmation Flow
- **Factual Memory vs. Speculative Hypotheses**:
  - LLM speculations are quarantined as `PROPOSED`.
  - Engineer promotes with `/confirm <id>` or dismisses with `/reject <id>`.
  - Only `CONFIRMED` findings become established knowledge across future sessions.
- **Bidirectional Curation**:
  - Automatically exports findings to human-readable Markdown (`docs/memory/`).
  - Edits made by engineers in Markdown are losslessly synced back to SQLite.
- **Safety Features**: Automated secret redaction (API keys, credentials) and file-staleness detection.

---

### Slide 5: Binary Reverse Engineering & REA Integration
- **Reverse Engineer Anything (REA)**:
  - Open-source (`github.com/morluto/rea`), local-first MCP server exposing 229 reverse engineering tools.
  - Native decompilation bridges to Ghidra/Hopper/IDA.
- **Resilient Fallback Architecture**:
  - Agent queries environment prerequisites (Node >= 22.23.4, Java 17+, Ghidra).
  - If prerequisites are missing or uninstalled, gracefully routes to local `pefile` + `Capstone` disassembler.
- **Policy Enforcement**:
  - Denies path traversals (`..`), unauthorized directory escapes, and symlink redirects.
  - 100% fail-closed static inspection with zero code execution.

---

### Slide 6: Dynamic Tool Routing & Context Budget Tuning
- **The Context Dilemma**: Monolithic tool schemas consume ~842 tokens per turn, overwhelming small models (Qwen 1.5B has a 4K token window).
- **Dynamic Tool Router (`agent/tool_router.py`)**:
  - Routes only category-relevant tools (4–8 tools) per turn based on user intent.
  - Reduces tool prompt overhead by **64.2%** (from ~842 tokens to ~301 tokens).
- **Context Budget Manager (`agent/context_budget.py`)**:
  - Enforces priority compaction: System instructions > Verified evidence > Memory findings > History turns.
  - Truncates verbose disassembly listings while preserving critical entry points and symbol RVAs.

---

### Slide 7: Ground Truth Benchmark Suite (17 Tasks)
- **Deterministic Evaluation**:
  - 17 tasks with hand-verified ground truth in `benchmarks/milestone1_ground_truth.json`.
  - Covers: Code discovery (C1-C4), Binary inspection (B1-B6), Memory persistence (M1-M3), Multi-tool integration (MT1), and REA fallback (REA1-REA3).
- **Results**:
  - **Pass Rate: 17/17 Passed (100.0%)**
  - **Execution Time**: ~1.9 seconds total suite execution time.
  - Zero test flakes, zero external network dependencies.

---

### Slide 8: Real-World E2E Evaluation vs. Baseline
- **Evaluation Environment**:
  - Tested on `bottle` open-source repository (commit `aba0c1a7`, 4,000+ LoR).
  - Baseline: Plain LLM tool loop with `read_file` and `grep_search` only.
  - Full Agent: AST graph + PE/Capstone/REA + Memory + Tool Router.
- **Key Empirical Results (Tested across Qwen 2.5 1.5B, Phi-3.5 Mini, and Llama 3.1 8B)**:
  - **Baseline Success Rate**: 27.3% – 36.4%
  - **Full Agent Success Rate**: **90.9% (20/22 tasks) across all 3 models**
  - **Token Efficiency**: Full Agent reduced total token consumption by **26.7% to 84.4%** due to structured graph lookups instead of whole-file grep dumps.
  - **Zero-Egress Check**: 100% Passed (0 non-local connections).

---

### Slide 9: Model Comparison & Sizing (Qwen vs. Phi vs. Llama)
- **Empirical Sizing on Apple M4 (16 GB Unified Memory)**:
  - **`qwen2.5:1.5b` (Recommended Default)**:
    - Latency: ~3.2s/turn. Low memory footprint (~1.0 GB VRAM).
    - Strict JSON adherence and tool calling; ideal for real-time interactive engineering queries.
  - **`phi3.5:latest` (Reasoning Alternative)**:
    - Strong analytical reasoning; full agent latency 18.37s (faster than baseline 21.68s); capped at 512 tokens.
  - **`llama3.1:8b` (Complex Synthesis)**:
    - Exceptional token compression (6,319 tokens vs 40,528 baseline); ~24.6s turn latency.

---

### Slide 10: Zero-Egress Network Isolation Verification
- **Audit Methodology**:
  - Runtime socket hook (`ZeroEgressMonitor`) traps every call to `socket.socket.connect`.
  - Verifies that target IP is `127.0.0.1` or UNIX domain socket.
- **Result**:
  - **0 Non-Local Connections Detected** across hundreds of benchmark queries and E2E evaluation tasks.
  - Guaranteed IP protection for proprietary Samsung code and binary targets.

---

### Slide 11: Production Packaging & Developer Ergonomics
- **Standard Packaging**:
  - `pyproject.toml` configuration with console entry point `prism-agent`.
  - Supports Python 3.11, 3.12, 3.13, and 3.14.
- **One-Command Setup**:
  - `scripts/setup.sh` (macOS/Linux) and `scripts/setup.ps1` (Windows).
  - Clean-environment validation script (`scripts/clean_env_check.py`) runs 94 unit tests, 17 benchmarks, and persistence check in an isolated venv.
- **VS Code Integration**:
  - Pre-configured `.vscode/tasks.json` for one-click testing, health checking, and CLI debugging.

---

### Slide 12: Summary & Strategic Next Steps
- **Milestone 2 Status**: **100% COMPLETE**.
  - Unified memory, confirmation flow, context budgets, tool routing, REA fallback, and multi-model evaluations fully verified.
- **Strategic Next Steps (Milestone 3 / Enterprise Rollout)**:
  1. Deploy internal vLLM inference node on Samsung private GPU cluster.
  2. Install Node 22.23+ and Ghidra on target machines to unlock native REA deep decompilation.
  3. Expand code knowledge graph to C/C++ and Rust ASTs via Tree-sitter.

