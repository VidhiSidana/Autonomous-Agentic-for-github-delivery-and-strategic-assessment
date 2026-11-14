# Samsung PRISM — Milestone 2 End-to-End Evaluation Report

**Project:** Samsung PRISM Unified Local-LLM Engineering Agent  
**Milestone:** Month 3 — Milestone 2 Delivery & Month 4 Closure  
**Evaluation Date:** 2026-11-14  
**Evaluator:** `benchmarks/e2e_eval.py`  
**Raw Report:** [`benchmarks/results/e2e_report.json`](../benchmarks/results/e2e_report.json)  
**Execution Log:** [`benchmarks/verification/e2e_run.txt`](../benchmarks/verification/e2e_run.txt)  

---

## Evaluation Artifact Reconciliation

Historical benchmarks ran single-model evaluations on individual dates (e.g. 2026-11-10 UTC). The current evaluation artifact (`benchmarks/results/e2e_report.json`) reflects the complete, verified multi-model execution run across all three shortlisted local models (`qwen2.5:1.5b`, `phi3.5:latest`, and `llama3.1:8b`) on the reference hardware under tightened, deterministic ground-truth scoring.

The false-hypothesis scorer has been updated to distinguish explicit negation from affirmative claims via `_contains_unnegated_claim()`. This ensures that correct negative findings (e.g. "Bottle does not use Django") are correctly scored as refutations rather than false assertions.

---

## 1. Executive Summary

Milestone 2 introduced the **Unified Memory Layer**, the **Engineer Confirmation Flow**, the **Dynamic Tool Router**, and **Context Budget Management**. To validate these additions against empirical engineering requirements, an end-to-end (E2E) evaluation framework was executed comparing:

1. **Baseline Configuration**: A representative plain file-read and regex grep approach with zero code knowledge graph, zero binary parsing capability, and zero persistent memory.
2. **Full Agent Configuration**: The Samsung PRISM Unified Agent utilizing Tree-sitter Code Graph, pefile/Capstone/REA binary tools, SQLite + Curated Markdown unified memory, engineer confirmation flow, category tool routing, and context budgeting.

### Key Measured Outcomes

#### Multi-Model Comparison Table (End-to-End Evaluation)

| Metric | Qwen 2.5 1.5B (Baseline) | Qwen 2.5 1.5B (Full Agent) | Phi-3.5 Mini (Baseline) | Phi-3.5 Mini (Full Agent) | Llama 3.1 8B (Baseline) | Llama 3.1 8B (Full Agent) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Overall Task Success Rate** | 27.3% (6/22) | **90.9% (20/22)** | 36.4% (8/22) | **90.9% (20/22)** | 31.8% (7/22) | **90.9% (20/22)** |
| **Ground-Truth Tasks (17)** | 35.3% (6/17) | **100.0% (17/17)** | 47.1% (8/17) | **100.0% (17/17)** | 41.2% (7/17) | **100.0% (17/17)** |
| **Real Code Tasks (3 on Bottle)** | 0.0% (0/3) | **100.0% (3/3)** | 0.0% (0/3) | **100.0% (3/3)** | 0.0% (0/3) | **100.0% (3/3)** |
| **Multi-Session Resume (2)** | 0.0% (0/2) | **50.0% (1/2)** | 0.0% (0/2) | **50.0% (1/2)** | 0.0% (0/2) | **50.0% (1/2)** |
| **Total Tokens Consumed** | 25,272 tok | **18,518 tok (-26.7%)** | 38,927 tok | **20,738 tok (-46.7%)** | 40,528 tok | **6,319 tok (-84.4%)** |
| **Avg Tokens / Task** | 1,148.7 tok | **841.7 tok** | 1,769.4 tok | **942.6 tok** | 1,842.2 tok | **287.2 tok** |
| **Average Task Latency** | 2.82s | **3.24s** | 21.68s | **18.37s (-15.3%)** | 21.13s | **24.66s** |
| **False-Hypothesis Rate** | N/A | **33.3% (1/3)** | N/A | **33.3% (1/3)** | N/A | **33.3% (1/3)** |
| **Zero-Egress Check** | PASSED | **PASSED** | PASSED | **PASSED** | PASSED | **PASSED** |

---

## 2. Zero-Egress Security Verification

To guarantee that proprietary enterprise source code and binary assets never leak to public cloud infrastructure, all test runs executed under an active socket-level interceptor (`ZeroEgressMonitor` in `benchmarks/e2e_eval.py`).

- **Validation Scope**: Monkeys patches Python's `socket.socket.connect` to log and block any destination IP outside of loopback (`127.0.0.1`, `::1`) or private local networks.
- **Measured Result**: **0 outbound connections** detected across all 22 tasks and all 3 model evaluation suites.
- **Subprocess Isolation Notice**: Interceptor operates within the Python agent process. External CLI commands (such as `git` or `npx rea`) are gated by `agent/policy.py` path allowlists and local stdio pipes.

---

## 3. Real-Repository Ground Truth Evaluation (Bottle Framework)

To evaluate real-world engineering utility beyond synthetic micro-benchmarks, tasks RC1–RC3 targeted a clone of the real-world Python web framework `bottle` (commit `aba0c1a7`):

1. **RC1 (Function Definition & Exact Line Citation)**: Located `def abort(code=500, text=...)` at line 2697 raising `HTTPError`.
   - *Baseline*: Failed (plain grep returned multiple unranked occurrences).
   - *Full Agent*: Passed on all 3 models with exact line citations.
2. **RC2 (Caller & Raiser Identification)**: Identified callers and error-raising call sites across the framework (e.g. lines 812, 1024, 2699).
   - *Baseline*: Failed to trace call hierarchy.
   - *Full Agent*: Passed on all 3 models.
3. **RC3 (Class Architecture Outline)**: Outlined class `Bottle`, routing decorators (`route`, `get`, `post`), and sub-router dispatching.
   - *Baseline*: Failed to synthesize structured architectural overview.
   - *Full Agent*: Passed on all 3 models.

---

## 4. Cross-Session Memory & Confirmation Lifecycle

The evaluation tested cross-session persistence across independent Python processes:
- **RS1 (Binary Memory Recovery)**: Session 1 performed PE inspection and saved findings to persistent SQLite memory. Session 2 (spawned as a fresh process) queried memory for previous binary architecture details.
- **RS2 (Engineer Confirmation Lifecycle)**: Finding initially quarantined under `PROPOSED` status. Lead engineer confirmed finding via confirmation hook. Session 2 retrieved the verified fact without re-running binary disassemblers.

---

## 5. False-Hypothesis Validation

Three targeted queries evaluated whether the agent could refute speculative, incorrect, or deceptive claims:

| Task ID | Speculative Premise | Expected Decision | Result |
| :--- | :--- | :--- | :--- |
| **FH1** | Non-existent `backdoor_payload` export | Refute presence | **Refuted Correctly** |
| **FH2** | Policy allows arbitrary folder execution | Refute and confirm allowlist | **Refuted Correctly** |
| **FH3** | Bottle uses Django ORM models | Refute Django dependency | **Falsely Asserted** (1/3 failure) |

**False-Hypothesis Rate**: 33.3% (1/3 falsely asserted, 2/3 correctly refuted).

---

## 6. Dynamic Tool Router and Context Budget Evaluation

A dedicated benchmark (`benchmarks/benchmark_context_budget.py`) measured the impact of dynamic tool routing and category-specific compact schemas:

| Model | Monolithic Prompt Tokens | Dynamic Router Tokens | Token Reduction | Monolithic Accuracy | Router Accuracy |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Qwen 2.5 1.5B** | 13,472 | 7,299 | **45.8%** | 81.2% (13/16) | **87.5% (14/16)** |
| **Phi-3.5 Mini** | 16,399 | 8,945 | **45.5%** | 81.2% (13/16) | **87.5% (14/16)** |
| **Llama 3.1 8B** | 13,423 | 7,330 | **45.4%** | 81.2% (13/16) | **93.8% (15/16)** |
| **Mistral Nemo 12B** | Not tested | Not tested | N/A | N/A | N/A |

---

## 7. Where the Full Agent is NOT Better (Honest Trade-offs)

1. **Single-File Exact Keyword Grep**: For trivial search queries on small codebases (e.g. searching for a literal constant in a 50-line file), plain grep is faster (~0.01s vs ~2-3s) because the full agent incurs planning, tool-dispatch, and synthesis latency.
2. **First-Turn Turnaround**: The full agent introduces initial schema parsing and prompt preparation overhead.

---

## 8. Final Model Recommendation & Hardware Sizing

### Reference Hardware Specification:
- **CPU / SoC:** Apple M4 (10 execution cores: 4 performance + 6 efficiency)
- **RAM / VRAM:** 16.0 GB Unified Memory (17,179,869,184 bytes)
- **OS:** macOS Darwin (arm64)
- **Inference Runtime:** Local Ollama daemon (`http://127.0.0.1:11434`)

### Model Trade-off Analysis:

| Model Candidate | Parameter Size | Quantization | RAM / VRAM Footprint | Avg Turn Latency | Strengths | Known Weaknesses & Mitigations | Recommendation Status |
| :--- | :---: | :---: | :---: | :---: | :--- | :--- | :---: |
| **`qwen2.5:1.5b`** | 1.5B | Q4_K_M | ~1.0 GB | **3.24s** | Fast interactive responsiveness, strict JSON format adherence, reliable tool calling with compact schemas | Small context window (4K); mitigated by priority compaction and dynamic tool routing | **PRIMARY DEFAULT** |
| **`llama3.1:8b`** | 8.0B | Q4_K_M | ~5.0 GB | **24.66s** | Exceptional synthesis nuance, deep architectural comprehension, 128K native context | Higher latency on standard laptop hardware; ~7x slower turn time than Qwen | **ANALYTICAL FALLBACK** |
| **`phi3.5:latest`** | 3.8B | Q4_0 | ~2.2 GB | **18.37s** | High reasoning capability, compact footprint | Prone to repetitive text generation unless `OLLAMA_MAX_TOKENS=512` is capped; occasional HTTP 500 under heavy prompts | **SECONDARY / EXPERIMENTAL** |
| **`mistral-nemo:12b`**| 12.2B | Q4_K_M | ~7.5 GB | N/A | High reasoning capability | Exceeds comfortable headroom on 16GB laptops running IDE and disassemblers | **NOT TESTED (Cluster only)** |

### Final Architecture Decisions:
1. **Default Deployment Model**: Pin `OLLAMA_MODEL="qwen2.5:1.5b"` as the default model in `config/settings.py`. Provides rapid ~3-second query turnaround for day-to-day code navigation and binary inspection on 16GB laptops.
2. **Analytical Fallback**: Support switching to `llama3.1:8b` via `--model llama3.1:8b` for deep architectural refactoring or multi-module impact assessments where latency is secondary to synthesis breadth.
