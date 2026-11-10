# Samsung PRISM — Milestone 2 End-to-End Evaluation Report

**Project:** Samsung PRISM Unified Local-LLM Engineering Agent
**Milestone:** Month 3 — Milestone 2 Delivery
**Evaluation Date:** 2026-11-10
**Evaluator:** `benchmarks/e2e_eval.py`
**Raw Report:** [`benchmarks/results/e2e_report.json`](../benchmarks/results/e2e_report.json)
**Execution Log:** [`benchmarks/verification/e2e_run.txt`](../benchmarks/verification/e2e_run.txt)

---

## 1. Executive Summary

Milestone 2 introduced and evaluated the Unified Memory Layer, Engineer Confirmation Flow, Dynamic Tool Router, and Context Budget Management.

The end-to-end evaluation compared two configurations:

1. **Baseline:** A local LLM using a restricted `read_file`/grep tool setup.
2. **Full Agent:** The Samsung PRISM agent using code-analysis tools, binary-analysis tools, persistent memory, REA integration with fallback support, and structured tool orchestration.

The evaluation covered 22 tasks per model:
- 17 ground-truth engineering tasks.
- 3 real open-source repository tasks using Bottle.
- 2 multi-session resume tasks.

Three additional false-hypothesis checks were evaluated separately.

### 1.1 End-to-End Model Comparison

| Metric | Qwen Baseline | Qwen Full Agent | Llama Baseline | Llama Full Agent |
|---|---:|---:|---:|---:|
| Overall task success | 31.8% (7/22) | **95.5% (21/22)** | 45.5% (10/22) | **95.5% (21/22)** |
| Ground-truth tasks | 41.2% (7/17) | **100% (17/17)** | 58.8% (10/17) | **100% (17/17)** |
| Real repository tasks | 0% (0/3) | **100% (3/3)** | 0% (0/3) | **100% (3/3)** |
| Multi-session resume | 0% (0/2) | **50% (1/2)** | 0% (0/2) | **50% (1/2)** |
| Total tokens | 26,091 | **17,443** | 41,282 | **12,108** |
| Average tokens per task | 1,186.0 | **792.9** | 1,876.5 | **550.4** |
| Average task latency | 2.4752 s | 4.526 s | 19.4326 s | 22.935 s |
| False-hypothesis checks falsely asserted | N/A | 1/3 | N/A | 1/3 |
| Zero-egress monitor | PASSED | PASSED | PASSED | PASSED |

The Full Agent reduced total token consumption by:
- **Qwen 2.5 1.5B:** 33.1%.
- **Llama 3.1 8B:** 70.7%.

The Full Agent achieved 21 successful tasks out of 22 for both models. The remaining failure was the first multi-session resume scenario (RS1).

### 1.2 Important Performance Trade-off

The Full Agent is not faster for every task.

For simple single-file grep queries on small repositories, a basic search approach can be faster (approximately 0.05–0.2 seconds in the evaluated scenario). The Full Agent introduces planning, tool orchestration, evidence normalization, and response synthesis overhead.

The agent's benefits are most relevant when a task requires structured code understanding, binary inspection, multiple tools, or persistent engineering memory.

---

## 2. Zero-Egress Verification

The E2E evaluation included a `ZeroEgressMonitor` that guards `socket.socket.connect` calls within the Python process.

### Recorded Results

| Check | Result |
|---|---|
| Qwen monitor status | PASSED |
| Llama monitor status | PASSED |
| Non-local connections recorded | None |
| Monitor scope | Python-process socket connection guard |
| MCP subprocess communication | Inherited stdio pipes |

The raw report recorded an empty `non_local_connections` list for both tested models.

**Scope limitation:** This result demonstrates that the configured Python socket guard recorded no non-local connections. It is not an independent packet-capture measurement and should not be described as proof that exactly zero external network packets were transmitted.

---

## 3. Ground-Truth Task Evaluation

The ground-truth benchmark contains 17 tasks across code analysis, binary analysis, persistent memory, multi-tool analysis, and REA integration.

### 3.1 Task-Level Results

| Task | Domain | Evaluation | Qwen Baseline | Llama Baseline | Qwen Full Agent | Llama Full Agent |
|---|---|---|---|---|---|---|
| C1 | Code | Repository function discovery | FAIL | FAIL | PASS | PASS |
| C2 | Code | Callers of `process_query` | FAIL | PASS | PASS | PASS |
| C3 | Code | Dependencies of `agent/main.py` | FAIL | FAIL | PASS | PASS |
| C4 | Code | Class architecture discovery | FAIL | PASS | PASS | PASS |
| B1 | Binary | Unauthorized path rejection | PASS | PASS | PASS | PASS |
| B2 | Binary | Clarification for missing path | PASS | FAIL | PASS | PASS |
| B3 | Binary | PE architecture identification | FAIL | FAIL | PASS | PASS |
| B4 | Binary | PE section inspection | FAIL | FAIL | PASS | PASS |
| B5 | Binary | Import table inspection | PASS | PASS | PASS | PASS |
| B6 | Binary | Machine-code disassembly | PASS | PASS | PASS | PASS |
| M1 | Memory | Save verified finding | PASS | PASS | PASS | PASS |
| M2 | Memory | Retrieve `auth_service.py` finding | FAIL | FAIL | PASS | PASS |
| M3 | Memory | Search for `auth_service` finding | FAIL | PASS | PASS | PASS |
| MT1 | Multi-tool | Cross-domain code and binary analysis | PASS | PASS | PASS | PASS |
| REA1 | REA | Engine availability and fallback status | FAIL | PASS | PASS | PASS |
| REA2 | REA | Function analysis with fallback | PASS | PASS | PASS | PASS |
| REA3 | REA | Entry-point decompilation comparison | FAIL | FAIL | PASS | PASS |

**Ground-truth results:**
- Qwen baseline: 7/17 (41.2%).
- Llama baseline: 10/17 (58.8%).
- Qwen Full Agent: 17/17 (100%).
- Llama Full Agent: 17/17 (100%).

---

## 4. Real Open-Source Repository Evaluation

Three additional tasks used the Bottle open-source Python repository.

| Task | Description | Qwen Baseline | Llama Baseline | Qwen Full Agent | Llama Full Agent |
|---|---|---|---|---|---|
| RC1 | Locate `def abort` in `bottle.py` | FAIL | FAIL | PASS | PASS |
| RC2 | Identify callers of `HTTPError` in `bottle.py` | FAIL | FAIL | PASS | PASS |
| RC3 | Outline the `Bottle` class and its routing methods | FAIL | FAIL | PASS | PASS |

The Full Agent achieved 3/3 successful tasks for both models.

Examples of verified outputs included:
- `def abort` located at `bottle.py:2697`.
- Identification of `HTTPError` callers.
- Extraction of the `Bottle` class outline and routing methods.

---

## 5. Multi-Session Resume Evaluation

Two scenarios tested whether engineering findings could be carried across separate sessions.

| Task | Scenario | Qwen Full Agent | Llama Full Agent |
|---|---|---|---|
| RS1 | Analyze a binary in one session and retrieve its entry-point finding in a later session | FAIL | FAIL |
| RS2 | Propose a finding, obtain engineer confirmation, and retrieve the confirmed fact in a later session | PASS | PASS |

**Result: 1/2 (50%) for both models.**

RS2 demonstrated the engineer confirmation lifecycle:

`PROPOSED → /confirm → CONFIRMED`

The confirmed finding was successfully retrieved across sessions.

RS1 did not recover the binary finding from the previous session. This remains an area for improvement in persistent memory and resume-digest retrieval.

---

## 6. False-Hypothesis Validation

Three additional checks evaluated whether the Full Agent could reject unsupported or incorrect engineering claims.

| Task | Hypothesis | Qwen Result | Llama Result |
|---|---|---|---|
| FH1 | A sample binary exports a function named `backdoor_payload` | Correctly refuted | Correctly refuted |
| FH2 | The binary policy allows execution from arbitrary folders without an allowlist | Correctly rejected the claim | Correctly rejected the claim |
| FH3 | Bottle imports `django.db` models for database queries | Incorrectly asserted the claim | Incorrectly asserted the claim |

Both models correctly handled two of the three checks.

**False-hypothesis assertion rate: 1/3 (33.3%) per model.**

This is a result from a small, three-case evaluation set. It should not be interpreted as a general hallucination rate.

---

## 7. Dynamic Tool Router and Context Budget Evaluation

A separate benchmark, `benchmarks/benchmark_context_budget.py`, measured the effect of dynamic tool routing and compact category-specific tool schemas.

This evaluation used 16 tool-calling tasks per model. Its results are separate from the 22-task E2E evaluation.

| Model | Monolithic Prompt Tokens | Dynamic Router Tokens | Token Reduction | Monolithic Accuracy | Router Accuracy | Monolithic Latency | Router Latency |
|---|---:|---:|---:|---:|---:|---:|---:|
| Qwen 2.5 1.5B | 13,472 | 7,299 | **45.8%** | 81.2% (13/16) | **87.5% (14/16)** | 0.433 s | 0.395 s |
| Phi-3.5 Mini | 16,399 | 8,945 | **45.5%** | 81.2% (13/16) | **87.5% (14/16)** | 1.120 s | 1.059 s |
| Llama 3.1 8B | 13,423 | 7,330 | **45.4%** | 81.2% (13/16) | **93.8% (15/16)** | 1.716 s | 1.658 s |
| Mistral Nemo 12B | Not tested | Not tested | N/A | N/A | N/A | N/A | Not installed in the evaluated environment |

### 7.1 Key Findings

1. **Reduced prompt size:** Dynamic routing reduced prompt tokens by approximately 45.4–45.8% across the three tested models.
2. **Improved tool-call accuracy:** The router improved measured accuracy for all three models in this benchmark.
3. **Lower measured latency:** Average tool-selection latency decreased by approximately 3.4–8.8%.
4. **Model coverage:** Mistral Nemo 12B was not installed and was not evaluated.

The accuracy values above refer to tool-call accuracy on the 16-task context-budget benchmark, not the separate E2E task-success rate.

---

## 8. Overall Assessment

The evaluation provides evidence that the Full Agent improves performance over the restricted baseline for the tested engineering tasks.

### Demonstrated Strengths

- Repository function discovery and caller analysis.
- Module dependency and class-structure inspection.
- PE metadata, section, and import analysis.
- Machine-code disassembly.
- Persistent engineering finding storage and retrieval.
- Cross-domain code and binary tool execution.
- Engineer-confirmed memory retrieval across sessions.
- Reduced tool-schema prompt size through dynamic routing.

### Remaining Limitations

- One of two multi-session resume scenarios failed.
- One of three false-hypothesis checks produced an incorrect assertion.
- Simple grep operations can be faster with a lightweight baseline.
- MCP asynchronous session-cleanup warnings have appeared during some test scenarios and require further investigation.
- Zero-egress verification is limited to the scope of the implemented Python socket guard.
- Performance measurements are specific to the evaluated models, environment, and task set.

---

## 9. Future Scope

1. Improve local LLM response speed and tool-call reliability.
2. Investigate MCP asynchronous session lifecycle and cleanup.
3. Improve cross-session binary finding retrieval.
4. Strengthen evidence verification and confidence scoring.
5. Expand false-hypothesis testing with a larger evaluation set.
6. Improve memory retrieval and ranking.
7. Expand binary-analysis capabilities and REA integration.
8. Evaluate additional local models.
9. Benchmark against larger and more diverse engineering repositories.
10. Improve robustness of multi-tool workflows.

---

## 10. Conclusion

The Milestone 2 evaluation demonstrates that the Samsung PRISM Unified Engineering Agent can combine local language models, specialized code and binary analysis tools, dynamic tool routing, and persistent engineering memory into a unified engineering workflow.

In the evaluated 22-task E2E benchmark, both Qwen 2.5 1.5B and Llama 3.1 8B achieved 21/22 successful tasks with the Full Agent configuration, compared with 7/22 and 10/22 respectively for the baseline configurations.

The results also demonstrate meaningful prompt-token reductions from dynamic tool routing. At the same time, the failed resume scenario, false-hypothesis result, latency trade-offs, and verification scope identify concrete areas for continued improvement.

These findings are specific to the reported benchmark tasks and evaluation environment.

---

**Project:** Samsung PRISM — Unified Local-LLM Engineering Agent
**Evaluation Artifacts:** `benchmarks/results/e2e_report.json`, `benchmarks/verification/e2e_run.txt`
**Primary Language:** Python
**LLM Runtime:** Ollama
**Tool Integration Protocol:** Model Context Protocol (MCP)
