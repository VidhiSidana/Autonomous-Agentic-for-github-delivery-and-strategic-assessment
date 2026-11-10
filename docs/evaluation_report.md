# Samsung PRISM — Milestone 2 End-to-End Evaluation Report

**Project:** Samsung PRISM Unified Local-LLM Engineering Agent
**Milestone:** Month 3 — Milestone 2 Delivery
**Evaluation Date:** 2026-11-11
**Evaluator:** `benchmarks/e2e_eval.py`
**Raw Report:** [`benchmarks/results/e2e_report.json`](../benchmarks/results/e2e_report.json)
**Execution Log:** [`benchmarks/verification/e2e_run.txt`](../benchmarks/verification/e2e_run.txt)

---

## 1. Executive Summary

Milestone 2 introduced and evaluated the Unified Memory Layer, Engineer Confirmation Flow, Dynamic Tool Router, Context Budget Management, and cross-session engineering memory retrieval.

The latest end-to-end evaluation tested the following configurations:

1. **Baseline:** Qwen 2.5 1.5B using a restricted `read_file`/grep tool setup.
2. **Full Agent:** Qwen 2.5 1.5B with code-analysis tools, binary-analysis tools, persistent memory, REA integration with fallback support, and structured tool orchestration.

The latest E2E benchmark evaluated 22 engineering tasks:
- 17 ground-truth engineering tasks.
- 3 real open-source repository tasks using Bottle.
- 2 multi-session resume tasks.

Three additional false-hypothesis checks were evaluated separately.

### 1.1 Latest End-to-End Results

| Metric | Qwen Baseline | Qwen Full Agent |
|---|---:|---:|
| Overall task success | 22.7% (5/22) | **100% (22/22)** |
| Ground-truth tasks | 17 tasks evaluated | **100% (17/17)** |
| Real repository tasks | 3 tasks evaluated | **100% (3/3)** |
| Multi-session resume | 0% (0/2) | **100% (2/2)** |
| Total tokens | 20,982 | **11,132** |
| Average tokens per task | 953.7 | **506.0** |
| Average task latency | 31.9934 s | 28.1437 s |
| Total tool calls | 20 | 57 |
| False-hypothesis checks falsely asserted | N/A | 1/3 (33.3%) |
| Zero-egress monitor | PASSED | PASSED |

The Full Agent achieved:
- **100% task success:** All 22 E2E tasks passed.
- **46.9% fewer tokens:** 11,132 compared with 20,982 for the baseline.
- **100% multi-session resume success:** Both RS1 and RS2 passed.
- **100% ground-truth and real-repository task success** in this evaluation.

### 1.2 Model Coverage

| Model | Latest E2E Status |
|---|---|
| Qwen 2.5 1.5B | TESTED |
| Llama 3.1 8B | NOT TESTED — model not installed in the evaluated Ollama environment |

The latest E2E results therefore apply to Qwen 2.5 1.5B only. Earlier Llama results are not treated as results from this latest run.

### 1.3 Important Performance Trade-off

The Full Agent is not necessarily faster for every individual operation.

For simple single-file grep queries on small repositories, a basic search approach can be faster because the Full Agent introduces planning, tool orchestration, evidence normalization, and response synthesis overhead.

The Full Agent's benefits are most relevant when a task requires structured code understanding, binary inspection, multiple tools, or persistent engineering memory.

---

## 2. Zero-Egress Verification

The E2E evaluation included a `ZeroEgressMonitor` that guards `socket.socket.connect` calls within the Python process.

| Check | Latest Qwen Result |
|---|---|
| Monitor status | PASSED |
| Non-local connections recorded | None |
| Monitor scope | Python-process socket connection guard |
| MCP subprocess communication | Inherited stdio pipes |

The raw report recorded an empty `non_local_connections` list.

**Scope limitation:** This result demonstrates that the configured Python socket guard recorded no non-local connections. It is not an independent packet-capture measurement and should not be described as proof that exactly zero external network packets were transmitted.

---

## 3. Ground-Truth Task Evaluation

The ground-truth benchmark contains 17 tasks across code analysis, binary analysis, persistent memory, multi-tool analysis, and REA integration.

### 3.1 Latest Full Agent Results

| Task | Domain | Evaluation | Qwen Full Agent |
|---|---|---|---|
| C1 | Code | Repository function discovery | PASS |
| C2 | Code | Callers of `process_query` | PASS |
| C3 | Code | Dependencies of `agent/main.py` | PASS |
| C4 | Code | Class architecture discovery | PASS |
| B1 | Binary | Unauthorized path rejection | PASS |
| B2 | Binary | Clarification for missing path | PASS |
| B3 | Binary | PE architecture identification | PASS |
| B4 | Binary | PE section inspection | PASS |
| B5 | Binary | Import table inspection | PASS |
| B6 | Binary | Machine-code disassembly | PASS |
| M1 | Memory | Save verified finding | PASS |
| M2 | Memory | Retrieve `auth_service.py` finding | PASS |
| M3 | Memory | Search for `auth_service` finding | PASS |
| MT1 | Multi-tool | Cross-domain code and binary analysis | PASS |
| REA1 | REA | Engine availability and fallback status | PASS |
| REA2 | REA | Function analysis with fallback | PASS |
| REA3 | REA | Entry-point decompilation comparison | PASS |

**Ground-truth result: 17/17 (100%).**

---

## 4. Real Open-Source Repository Evaluation

Three additional tasks used the Bottle open-source Python repository.

| Task | Description | Qwen Full Agent |
|---|---|---|
| RC1 | Locate `def abort` in `bottle.py` | PASS |
| RC2 | Identify callers of `HTTPError` in `bottle.py` | PASS |
| RC3 | Outline the `Bottle` class and its routing methods | PASS |

**Result: 3/3 (100%).**

Examples of verified outputs included:
- `def abort` located at `bottle.py:2697`.
- Identification of `HTTPError` callers.
- Extraction of the `Bottle` class outline and routing methods.

---

## 5. Multi-Session Resume Evaluation

Two scenarios tested whether engineering findings could be carried across separate sessions.

| Task | Scenario | Latest Qwen Full Agent |
|---|---|---|
| RS1 | Analyze a binary in one session and retrieve its entry-point finding in a later session | PASS |
| RS2 | Propose a finding, obtain engineer confirmation, and retrieve the confirmed fact in a later session | PASS |

**Result: 2/2 (100%).**

### 5.1 RS1 — Cross-Session Binary Finding Recovery

The RS1 regression fix addressed two issues:
- Previous-session binary questions needed to be routed to persistent memory retrieval.
- Binary findings needed to be stored under the supported `binary_finding` category rather than an unsupported category.

The evaluation confirmed a binary finding in the first session and recovered its architecture and entry-point information in a separate session.

The latest E2E task result was:

`Recovered investigated binary architecture and entry point from prior session.`

This demonstrates successful cross-session binary finding retrieval in the tested scenario.

### 5.2 RS2 — Engineer Confirmation Lifecycle

RS2 demonstrated the engineer confirmation lifecycle:

`PROPOSED → /confirm → CONFIRMED`

The confirmed finding was successfully retrieved across sessions.

---

## 6. False-Hypothesis Validation

Three additional checks evaluated whether the Full Agent could reject unsupported or incorrect engineering claims.

| Task | Hypothesis | Latest Qwen Result |
|---|---|---|
| FH1 | A sample binary exports a function named `backdoor_payload` | Correctly refuted |
| FH2 | The binary policy allows execution from arbitrary folders without an allowlist | Correctly rejected the claim |
| FH3 | Bottle imports `django.db` models for database queries | Incorrectly asserted the claim |

**False-hypothesis assertion rate: 1/3 (33.3%).**

This result comes from a small three-case evaluation set and should not be interpreted as a general hallucination rate. The FH3 failure remains an important area for improving evidence verification and unsupported-claim rejection.

---

## 7. Dynamic Tool Router and Context Budget Evaluation

A separate benchmark, `benchmarks/benchmark_context_budget.py`, measured the effect of dynamic tool routing and compact category-specific tool schemas.

This experiment used 16 tool-calling tasks per model. Its results are separate from the latest 22-task E2E evaluation.

| Model | Monolithic Prompt Tokens | Dynamic Router Tokens | Token Reduction | Monolithic Accuracy | Router Accuracy | Monolithic Latency | Router Latency |
|---|---:|---:|---:|---:|---:|---:|---:|
| Qwen 2.5 1.5B | 13,472 | 7,299 | **45.8%** | 81.2% (13/16) | **87.5% (14/16)** | 0.433 s | 0.395 s |
| Phi-3.5 Mini | 16,399 | 8,945 | **45.5%** | 81.2% (13/16) | **87.5% (14/16)** | 1.120 s | 1.059 s |
| Llama 3.1 8B | 13,423 | 7,330 | **45.4%** | 81.2% (13/16) | **93.8% (15/16)** | 1.716 s | 1.658 s |
| Mistral Nemo 12B | Not tested | Not tested | N/A | N/A | N/A | N/A | Not installed in that benchmark environment |

### 7.1 Key Findings

1. **Reduced prompt size:** Dynamic routing reduced prompt tokens by approximately 45.4–45.8% across the three tested models.
2. **Improved tool-call accuracy:** The router improved measured accuracy for all three models in this separate benchmark.
3. **Lower measured latency:** Average tool-selection latency decreased by approximately 3.4–8.8%.
4. **Model coverage:** Mistral Nemo 12B was not installed and was not evaluated.

The accuracy values above refer to tool-call accuracy on the 16-task context-budget benchmark, not the latest E2E task-success rate.

---

## 8. Overall Assessment

The latest evaluation provides evidence that the Full Agent improves performance over the restricted baseline for the tested engineering tasks.

### Demonstrated Strengths

- Repository function discovery and caller analysis.
- Module dependency and class-structure inspection.
- PE metadata, section, and import analysis.
- Machine-code disassembly.
- Persistent engineering finding storage and retrieval.
- Cross-domain code and binary tool execution.
- Engineer-confirmed memory retrieval across sessions.
- Successful RS1 cross-session binary finding recovery.
- Reduced tool-schema prompt size through dynamic routing.
- Successful execution of all 22 latest E2E tasks.

### Remaining Limitations

- One of three false-hypothesis checks produced an incorrect assertion.
- Simple grep operations can be faster with a lightweight baseline.
- MCP asynchronous session-cleanup warnings have appeared during some test scenarios and require further investigation.
- Some Ollama requests timed out during the latest execution, although the benchmark completed and recorded 22/22 successful tasks.
- Llama 3.1 8B was not installed and was not tested in the latest E2E run.
- Zero-egress verification is limited to the scope of the implemented Python socket guard.
- Performance measurements are specific to the evaluated models, environment, and task set.

---

## 9. Future Scope

1. Improve local LLM response speed and tool-call reliability.
2. Investigate MCP asynchronous session lifecycle and cleanup.
3. Strengthen evidence verification and confidence scoring.
4. Expand false-hypothesis testing with a larger evaluation set.
5. Improve memory retrieval and ranking.
6. Expand binary-analysis capabilities and REA integration.
7. Evaluate additional local models, including Llama 3.1 8B.
8. Benchmark against larger and more diverse engineering repositories.
9. Improve robustness of multi-tool workflows.

---

## 10. Conclusion

The Milestone 2 evaluation demonstrates that the Samsung PRISM Unified Engineering Agent can combine local language models, specialized code and binary analysis tools, dynamic tool routing, and persistent engineering memory into a unified engineering workflow.

In the latest 22-task E2E evaluation, Qwen 2.5 1.5B achieved **22/22 successful tasks (100%)** with the Full Agent configuration, compared with **5/22 (22.7%)** for the restricted baseline.

The Full Agent also achieved **100% success in both multi-session resume scenarios**, demonstrating recovery of a binary investigation finding across separate sessions and retrieval of an engineer-confirmed finding.

The separate context-budget benchmark demonstrated meaningful prompt-token reductions through dynamic tool routing. At the same time, the false-hypothesis result, response timeouts, MCP cleanup warnings, and verification scope identify concrete areas for continued improvement.

These findings are specific to the reported benchmark tasks and evaluation environments. Llama 3.1 8B was not tested in the latest E2E run.

---

**Project:** Samsung PRISM — Unified Local-LLM Engineering Agent
**Evaluation Artifacts:** `benchmarks/results/e2e_report.json`, `benchmarks/verification/e2e_run.txt`
**Primary Language:** Python
**LLM Runtime:** Ollama
**Tool Integration Protocol:** Model Context Protocol (MCP)
