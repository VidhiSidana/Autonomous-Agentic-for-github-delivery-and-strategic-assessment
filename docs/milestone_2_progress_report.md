# Milestone 2 Completion Report

**Project Title:** Unified Local-LLM Engineering Agent for Strategic Code & Binary Assessment  
**Partner:** Samsung PRISM Worklet  
**Milestone:** Month 3 (Milestone 2 Delivery)  
**Report Date:** 2026-11-11  
**Repository Branch:** `main` (Milestone 2 hardening and validation merged from `milestone2-hardening`)  
**Final acceptance environment:** Windows PowerShell, Python 3.11 virtual environment, on `milestone2-hardening`.  

---

## 1. Executive Summary & Deliverables Status

Milestone 2 focuses on establishing the **Unified Memory Layer**, the **Engineer Confirmation Flow**, **Context Budget Management with Dynamic Tool Routing**, and **End-to-End Evaluation against the Baseline under Zero-Egress Network Isolation**.

All Milestone 2 components have been implemented and integrated. Current hardening-branch regression evidence is recorded below. Final acceptance remains conditional on rerunning the 17-task ground-truth benchmark on this branch; historical benchmark results are not substituted for that run.

| Deliverable | Description | Status | Evidence & Artifacts |
| :--- | :--- | :---: | :--- |
| **Task B1** | **Engineer Confirmation Flow**<br>Evidence grounding; lifecycle `PROPOSED` -> `CONFIRMED` / `REJECTED`; CLI commands (`/pending`, `/confirm`, `/reject`); provenance tracking (`evidence_refs`, timestamps, session ID, user); retrieval priority rules. | **DONE** | [`memory/memory.py`](../memory/memory.py)<br>[`agent/main.py`](../agent/main.py)<br>[`tests/test_confirmation_flow.py`](../tests/test_confirmation_flow.py) (5 tests passed) |
| **Task B2** | **Unified Memory Layer**<br>Automatic session hooks (`on_query`, `on_tool_result`, `on_session_end`); `session_events` audit table; curated Markdown memory in `memory/curated/` with frontmatter; two-way lossless sync; dual-layer deduplication (hash + Jaccard); stale detection; secret redaction; local LLM summarization with deterministic extractive fallback; resume digest. | **DONE** | [`memory/session_manager.py`](../memory/session_manager.py)<br>[`memory/curated_memory.py`](../memory/curated_memory.py)<br>[`tests/test_unified_memory_layer.py`](../tests/test_unified_memory_layer.py) (8 tests passed) |
| **Task B3** | **Context Budgets, Prompts & Tool Schemas**<br>Dynamic category tool router (`agent/tool_router.py`) with compact schemas (4-8 tools per category, REA compact subset); context budget manager (`agent/context_budget.py`) with priority compaction and audit logging; prompt guardrails (refusal on missing facts, rejection of false premises). | **DONE** | [`agent/tool_router.py`](../agent/tool_router.py)<br>[`agent/context_budget.py`](../agent/context_budget.py)<br>[`benchmarks/results/context_budget_report.json`](../benchmarks/results/context_budget_report.json)<br>[`tests/test_context_budget.py`](../tests/test_context_budget.py) (5 tests passed) |
| **Task B4** | **End-to-End Evaluation vs Baseline**<br>Evaluation framework (`benchmarks/e2e_eval.py`) comparing Baseline (LLM tool loop with grep/file read) vs Full Agent across 22 tasks (17 ground truth + 3 real code on Bottle + 2 multi-session resume) + 3 false-hypothesis tasks; Zero-Egress Network Isolation check (`ZeroEgressMonitor`). | **IMPLEMENTED; historical evaluation available** | [`benchmarks/e2e_eval.py`](../benchmarks/e2e_eval.py)<br>[`benchmarks/results/e2e_report.json`](../benchmarks/results/e2e_report.json)<br>[`benchmarks/verification/e2e_run.txt`](../benchmarks/verification/e2e_run.txt)<br>[`docs/evaluation_report.md`](evaluation_report.md) |
| **Task B5** | **Documentation & Verification Reconciliation**<br>Architecture diagram updated; completion report generated; README updated; test suite verified. | **DONE** | [`docs/architecture.md`](architecture.md)<br>[`README.md`](../README.md) |

---

## 2. Test Suite & Verification Results

### 2.1 Final Milestone 2 Hardening-Branch Validation (2026-11-11)

Final acceptance validation was completed on the `milestone2-hardening` branch
in the Windows Python 3.11 virtual environment.

| Validation area | Command / scope | Reported result |
|---|---|---:|
| Ground-truth benchmark | `python benchmarks/benchmark_runner.py` | **17/17 passed (100.0%)** |
| Complete unit-test discovery | `python -m unittest discover -s tests -p "test_*.py" -t .` | **114 tests; OK; 3 skipped** |
| Benchmark policy matcher regression | Two focused tests for case-insensitive policy matching and response-text matching | **2/2 passed** |
| Cross-process memory persistence | Included in the ground-truth benchmark report | **Passed; content, status, session, and record ID verified** |

The final benchmark report recorded `total_tasks: 17`,
`passed_tasks: 17`, and `success_rate: "100.0%"`. All benchmark task
categories passed: code analysis (C1-C4), binary analysis (B1-B6), memory
(M1-M3), multi-tool execution (MT1), and REA integration (REA1-REA3).

The complete unit-test discovery finished with `Ran 114 tests in 600.384s`
and `OK (skipped=3)`. There were no reported failures or errors. The three
skipped tests are reported separately and are not counted as passed tests.
The two focused policy-matcher regression tests also passed.

**Acceptance result:** The documented Milestone 2 benchmark and full
unit-test acceptance gates have both been satisfied on
`milestone2-hardening`.

### 2.2 Historical Milestone 2 Baseline Test Snapshot

The following counts and commands are retained from the original milestone
evaluation environment. They are not a fresh run of the current hardening
branch:

```bash
# Unit Test Discovery
PYTHONPATH=. python3 -m unittest discover -s tests -p "test_*.py" -t .
# Result: Ran 86 tests in 4.622s -> OK (skipped=1)

# Milestone 1 Benchmark Parity
PYTHONPATH=. python3 benchmarks/benchmark_runner.py
# Result: 17/17 Passed (100.0%)
```

### Historical Test Count Breakdown by Module

The module-level figures below are a historical inventory, not a single
consistent aggregate run. They are retained for coverage traceability and
must not be summed or treated as current-branch results.

| Test Module | Coverage Area | Test Count | Result |
| :--- | :--- | :---: | :---: |
| `tests/test_confirmation_flow.py` | Lifecycle `PROPOSED` -> `CONFIRMED`/`REJECTED`, provenance, priority ordering, evidence context | 5 | **PASS** |
| `tests/test_unified_memory_layer.py` | Session hooks, extractive/LLM summarization, Markdown sync, deduplication, stale detection, resume digest | 8 | **PASS** |
| `tests/test_context_budget.py` | Category tool routing, REA subset filtering, priority compaction, prompt guardrails | 5 | **PASS** |
| `tests/test_memory.py` | Core SQLite operations, migrations, CRUD | 6 | **PASS** |
| `tests/test_unified_memory.py` | Backward-compatible memory retrieval & hypothesis lifecycle | 6 | **PASS** |
| `tests/test_policy.py` | Path traversal, symlinks, directory allowlist, secret redaction, audit logging | 12 | **PASS** |
| `tests/test_planner.py` | Case-preservation on file paths & symbols, query categorization, parameter extraction | 14 | **PASS** |
| `tests/test_code_analysis.py` | Tree-sitter AST, function discovery, caller/callee tracing, outline | 6 | **PASS** |
| `tests/test_binary_analysis.py` | PE header parsing, Capstone disassembly, mocked REA adapter prerequisites | 8 | **PASS** |
| `tests/test_mcp_client.py` | Dynamic MCP tool discovery and schema validation | 7 | **PASS** |
| `tests/test_orchestrator.py` | Multi-tool orchestration, memory anchoring, verified finding auto-save | 4 | **PASS** |
| `tests/test_benchmark_runner.py` | PE fixture generation, cross-process persistence validation | 3 | **PASS** |
| `tests/test_module_imports.py` | Module imports across Python versions, SessionManager annotations, Python 3.11 check | 3 | **PASS** |

---

## 3. Context Budget & Dynamic Tool Router Evaluation

Empirically measured using `benchmarks/benchmark_context_budget.py` against candidate models running locally in Ollama:

| Candidate Model | Baseline Monolithic Prompt Tokens | Dynamic Router Prompt Tokens | Token Reduction (%) | Monolithic Tool Acc. | Dynamic Router Tool Acc. | Monolithic Latency | Dynamic Router Latency |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Qwen 2.5 1.5B** | 13,472 | **7,299** | **-45.8%** (6,173 tokens saved) | 81.2% (13/16) | **87.5% (14/16)** (+6.3%) | 0.433s | **0.395s** (-8.8%) |
| **Phi-3.5 Mini 3.8B** | 16,399 | **8,945** | **-45.5%** (7,454 tokens saved) | 81.2% (13/16) | **87.5% (14/16)** (+6.3%) | 1.120s | **1.059s** (-5.4%) |
| **Llama 3.1 8B** | 13,423 | **7,330** | **-45.4%** (6,093 tokens saved) | 81.2% (13/16) | **93.8% (15/16)** (+12.6%) | 1.716s | **1.658s** (-3.4%) |
| **Mistral Nemo 12B** | *NOT TESTED* | *NOT TESTED* | *NOT TESTED* | N/A | *NOT TESTED* | N/A | *Not installed in local Ollama* |

---

## 4. End-to-End Evaluation Summary (Baseline vs Full Agent)

Empirically measured using `benchmarks/e2e_eval.py` across 22 tasks:

| Evaluation Dimension | Baseline (LLM with Grep / Read File) | Full Agent (Milestone 2) | Advantage |
| :--- | :---: | :---: | :--- |
| **Overall Success Rate** | **31.8%** (7/22) | **95.5%** (21/22) | **+63.7% Absolute Success Rate** |
| **Ground-Truth Tasks (17)** | 41.2% (7/17) | **100.0%** (17/17) | Parity with Milestone 1 ground-truth suite |
| **Real Code Tasks (3 on Bottle)** | 0.0% (0/3) | **100.0%** (3/3) | Located def abort:2697, HTTPError callers, class Bottle |
| **Multi-Session Resume (2)** | 0.0% (0/2) | **50.0%** (1/2) | Confirmed findings promoted and recalled across sessions |
| **Zero-Egress Isolation** | N/A | **PASSED (0 non-local connections)** | 100% on-premise, zero cloud egress |
| **False-Hypothesis Rate** | N/A | **33.3%** (1/3 asserted) | 2/3 speculative hypotheses correctly refuted |
| **Total Tokens Consumed** | 26,091 tokens | **17,443 tokens** | **-33.1% Token Savings** via context budgeting |

> **Where Agent is NOT better:** For simple single-file grep queries on small repositories, the baseline is faster (latency ~0.05s-0.2s) because the full agent incurs planning, evidence normalization, and structured synthesis overhead. Baseline also consumes zero LLM prompt tokens when regex matches immediately without multi-turn LLM reasoning.

---

## 5. Verification Commands

Any reviewer or engineer can independently replicate all results using the exact commands below:

```bash
# 1. Run the complete unit-test discovery on the current branch
python -m unittest discover -s tests -p "test_*.py" -t .

# 2. Run the 17 ground-truth benchmark tasks (requires local Ollama and configured MCP tools)
python benchmarks/benchmark_runner.py

# 3. Run the Context Budget & Dynamic Tool Router benchmark
PYTHONPATH=. python3 benchmarks/benchmark_context_budget.py

# 4. Run the End-to-End Evaluation & Zero-Egress suite
PYTHONPATH=. python3 benchmarks/e2e_eval.py
```


## 6. Final Milestone 2 Acceptance

**ACCEPTANCE GATES: PASSED**

**Implementation:** The Milestone 2 feature set is implemented, integrated,
documented, and covered by regression tests.

**Final acceptance evidence on `milestone2-hardening` (2026-11-11):**

1. `python benchmarks/benchmark_runner.py` — **17/17 tasks passed (100.0%)**.
2. `python -m unittest discover -s tests -p "test_*.py" -t .` —
   **114 tests ran; OK (skipped=3)**, with no failures or errors.
3. Policy matcher regression tests — **2/2 passed**.
4. Cross-process persistence — **passed**, with record identity, content,
   verification status, and session association checked.

**Final status: Milestone 2 implementation and acceptance validation complete
on `milestone2-hardening`, and the validated work has since been merged into
`main` (merge commit `4f68c46b20fca07da09df9ef12664eaef23f5155`).** The
acceptance tests were executed on `milestone2-hardening` before the merge;
GitHub `main` now contains that validated implementation. Historical
evaluation figures elsewhere in this report remain explicitly identified as
historical and are not substituted for the current-branch acceptance results.
