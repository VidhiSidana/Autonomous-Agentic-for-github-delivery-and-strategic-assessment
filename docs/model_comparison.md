# Samsung PRISM: Open-Weight Local Model Shortlist & Evaluation

## 1. Overview & Evaluation Scope
The **Samsung PRISM Unified Engineering Agent** is designed for on-premise, zero-cloud operation. In the Milestone 1 architecture, the system employs a hybrid design:
- **Integrated System Layer:** An algorithmic and rule-guided pipeline (`AgentPlanner` + `AgentOrchestrator`) that performs deterministic query categorization, path validation, and dynamic MCP argument-schema matching.
- **Local LLM Layer:** A local open-weight instruction model (interfaced via Ollama) responsible for synthesizing empirical tool evidence into grounded technical answers.
- **Autonomous LLM Calling:** An independent benchmark layer (`benchmarks/evaluate_models.py`) evaluating each model's direct ability to select tools and emit valid JSON argument schemas without planner assistance.

---

## 2. Evaluation Categories & Empirical Results

### Category A: Deterministic Planner Performance (Integrated System)
- **Scope:** Evaluated across the 14-task ground-truth benchmark suite (`benchmarks/datasets/milestone1_ground_truth.json`).
- **Mechanism:** Deterministic regex and Pydantic validation rules in `agent/planner.py`.
- **Accuracy:** **100.0%** (14/14 queries correctly routed to `CODE_ANALYSIS`, `BINARY_ANALYSIS`, `MEMORY`, or `MULTI_TOOL`).
- **Missing Argument Detection:** Successfully flagged missing target binary paths (Task B2) and triggered clarification prompts.

### Category B: Tool Execution Performance (Integrated System)
- **Scope:** Empirical tool execution against real MCP servers (`code_fallback`, `code_graph`, `binary`) and SQLite memory.
- **Execution Success Rate:** **100.0%** (14/14 benchmark tasks executed successfully without runtime exceptions).
- **Dynamic Schema Validation:** `AgentOrchestrator` validates all parameters against discovered tool schemas prior to invocation.
- **Multi-Tool Dispatch:** Verified dual-branch dispatch (Task MT1: simultaneous code symbol discovery and PE binary inspection).

### Category C: LLM Tool-Selection Performance (Direct LLM Calling)
- **Scope:** Direct zero-shot tool selection tested via `benchmarks/evaluate_models.py` across 14 varied queries without planner assistance.
- **Prompt Format:** Standardized system prompt providing tool definitions, few-shot caller/callee disambiguation, and requiring a single JSON response: `{"tool": "<name>", "arguments": {<args>}}`.
- **Results by Model Candidate:**
  - **Qwen 2.5 1.5B (`qwen2.5:1.5b`):**
    - Valid JSON Rate: **100.0%** (14/14 valid JSON responses)
    - Tool Selection Accuracy: **78.6%** (11/14 correct tool selections)
    - Observed Failure: Dispatched `analyze_binary` on T12 instead of requesting clarification for missing path; selected `none` on ambiguous T13/T14.
  - **Phi-3.5 Mini 3.8B (`phi3.5:latest`):**
    - Valid JSON Rate: **0.0%** (0/14 - emitted multi-paragraph markdown explanations and multiple JSON objects rather than a single JSON payload)
    - Tool Selection Accuracy: **0.0%** (0/14 under strict JSON response validation)
  - **Llama 3.1 8B (`llama3.1:8b`):**
    - Valid JSON Rate: **100.0%** (14/14 valid JSON responses)
    - Tool Selection Accuracy: **78.6%** (11/14 correct tool selections)
    - High-precision formatting with zero narrative drift.
  - **Mistral Nemo 12B (`mistral-nemo:12b`):** **NOT TESTED** (Model not installed in local Ollama daemon / RAM boundary).

### Category D: LLM Argument-Generation Performance (Direct LLM Calling)
- **Scope:** Measuring whether required arguments are present and whether exact argument values match ground truth via strict normalized equality.
- **Results by Model Candidate:**
  - **Qwen 2.5 1.5B (`qwen2.5:1.5b`):**
    - Required Arguments Present: **92.9%** (13/14 tasks)
    - Exact Argument Correctness: **78.6%** (11/14 tasks matched expected argument values under strict normalized equality)
    - Overall Tool-Call Accuracy (Tool Correct AND Exact Args Correct): **78.6%** (11/14 tasks)
  - **Phi-3.5 Mini 3.8B (`phi3.5:latest`):**
    - Required Arguments Present: **21.4%** (3/14 tasks)
    - Exact Argument Correctness: **0.0%** (0/14 tasks due to failure to output single clean JSON object)
    - Overall Tool-Call Accuracy: **0.0%** (0/14 tasks)
  - **Llama 3.1 8B (`llama3.1:8b`):**
    - Required Arguments Present: **92.9%** (13/14 tasks)
    - Exact Argument Correctness: **78.6%** (11/14 tasks matched expected argument values under strict normalized equality)
    - Overall Tool-Call Accuracy: **78.6%** (11/14 tasks)
  - **Mistral Nemo 12B (`mistral-nemo:12b`):** **NOT TESTED** (Model not installed).

### Category E: Evidence-Grounded Synthesis (Direct LLM Calling)
- **Scope:** Evaluated across 3 distinct test cases testing factual extraction, resistance to hallucination on missing facts, and rejection of false premises.
- **Test Cases:**
  1. `SYNTH_01_COMPLETE_PE`: Complete PE evidence (architecture, entry point, section count, text size).
  2. `SYNTH_02_MISSING_EVIDENCE`: Query asks for compiler version/language absent from evidence.
  3. `SYNTH_03_CONTRADICTORY_EVIDENCE`: Query introduces a false premise ("Confirm whether binary is a 32-bit ARM binary").
- **Results Summary:**
  - **Qwen 2.5 1.5B (`qwen2.5:1.5b`):**
    - Multi-Case Synthesis Score: **33.3%** (1/3 cases passed under strict verification).
    - Passed Case 1 (factual extraction); failed Case 2 and 3 due to speculation and false-premise acquiescence.
  - **Phi-3.5 Mini 3.8B (`phi3.5:latest`):**
    - Multi-Case Synthesis Score: **66.7%** (2/3 cases passed under strict verification).
    - Passed Case 1 and Case 3 (correctly rejected the 32-bit ARM false premise); speculated on Case 2.
  - **Llama 3.1 8B (`llama3.1:8b`):**
    - Multi-Case Synthesis Score: **66.7%** (2/3 cases passed under strict verification).
    - Passed Case 1 (100% factual accuracy) and Case 3 (firmly rejected the false premise); failed Case 2.
  - **Mistral Nemo 12B (`mistral-nemo:12b`):** **NOT TESTED** (Model not installed).

### Category F: Latency Disambiguation & Token Consumption
- **Deterministic Pipeline Latency (Source of Truth: `benchmarks/results/benchmark_report.json`):**
  - Average Task Latency: **0.0639 seconds** (63.9 ms per task)
  - Total Suite Execution (including independent subprocess persistence tests): **~1.20 seconds**
- **LLM Direct Inference Latency & Tokens (Source of Truth: `benchmarks/results/model_evaluation_report.json`):**
  - **Qwen 2.5 1.5B:**
    - Average Tool-Calling Latency: **0.5922s** per query
    - Token Usage: 7,164 prompt tokens, 253 generated tokens (avg **18.1 tokens/task**)
    - Average Synthesis Latency: **2.5317s**
  - **Phi-3.5 Mini 3.8B:**
    - Average Tool-Calling Latency: **4.7689s** per query
    - Token Usage: 8,629 prompt tokens, 1,327 generated tokens (avg **94.8 tokens/task**)
    - Average Synthesis Latency: **6.5975s**
  - **Llama 3.1 8B:**
    - Average Tool-Calling Latency: **3.0293s** per query
    - Token Usage: 7,191 prompt tokens, 289 generated tokens (avg **20.6 tokens/task**)
    - Average Synthesis Latency: **9.3838s**
  - **Mistral Nemo 12B:** **NOT TESTED**

### Category G: Hardware Requirements & Resource Footprint
- **Test Host:** macOS Darwin (Apple Silicon arm64, 16 GB Unified RAM).
- **Evaluated Profiles:**
  - **Qwen 2.5 1.5B:** Active footprint ~986 MB disk, ~1.1 GB RAM. Operates comfortably on 4 GB+ RAM machines without GPU acceleration.
  - **Phi-3.5 Mini 3.8B:** Footprint ~2.2 GB disk, ~2.8 GB RAM. Requires 8 GB+ RAM.
  - **Llama 3.1 8B:** Footprint ~4.9 GB disk, ~5.8 GB RAM. Requires 16 GB+ RAM for stable local execution.
  - **Mistral Nemo 12B:** Footprint ~7.3 GB disk, ~8.5 GB RAM. Target 16 GB+ / dedicated GPU profile. (**NOT TESTED**).

---

## 3. Comprehensive Model Comparison Matrix

| Evaluation Dimension | **Qwen 2.5 (1.5B)** *(Active Baseline)* | **Phi-3.5 Mini (3.8B)** *(Shortlisted)* | **Llama 3.1 (8B)** *(Power Tier)* | **Mistral Nemo (12B)** *(High-Capacity)* |
| :--- | :--- | :--- | :--- | :--- |
| **Model Creator** | Alibaba Cloud | Microsoft | Meta | Mistral AI / NVIDIA |
| **Exact Ollama Tag** | `qwen2.5:1.5b` | `phi3.5:latest` | `llama3.1:8b` | `mistral-nemo:12b` |
| **Quantization & Format** | `Q4_K_M` (GGUF) | `Q4_K_M` (GGUF) | `Q4_K_M` (GGUF) | `Q4_K_M` (GGUF) |
| **Parameter Count** | 1.54 Billion | 3.82 Billion | 8.03 Billion | 12.2 Billion |
| **Model Size on Disk** | 986 MB | 2.2 GB | 4.9 GB | ~7.3 GB |
| **Context Window** | 32k tokens | 128k tokens | 128k tokens | 128k tokens |
| **Local Ollama Status** | **TESTED & VERIFIED** | **TESTED & VERIFIED** | **TESTED & VERIFIED** | **NOT TESTED** |
| **A. Planner Routing Accuracy** | **100.0%** (Deterministic) | **100.0%** (Deterministic) | **100.0%** (Deterministic) | **100.0%** (Deterministic) |
| **B. Tool Execution Success** | **100.0%** (Deterministic) | **100.0%** (Deterministic) | **100.0%** (Deterministic) | **100.0%** (Deterministic) |
| **C. LLM Tool Selection Accuracy** | **78.6%** (11/14 tasks) | **0.0%** (Verbose output) | **78.6%** (11/14 tasks) | **NOT TESTED** |
| **D. LLM Exact Argument Accuracy** | **78.6%** (11/14 tasks) | **0.0%** (Verbose output) | **78.6%** (11/14 tasks) | **NOT TESTED** |
| **D. Overall Tool-Call Accuracy** | **78.6%** (Tool + Args) | **0.0%** (Verbose output) | **78.6%** (Tool + Args) | **NOT TESTED** |
| **E. Multi-Case Synthesis Score** | **33.3%** (1/3 passed) | **66.7%** (2/3 passed) | **66.7%** (2/3 passed) | **NOT TESTED** |
| **F. Deterministic Pipeline Latency**| **0.0639s** average | **0.0639s** average | **0.0639s** average | **0.0639s** average |
| **F. LLM Tool Selection Latency** | **0.5922s** per query | **4.7689s** per query | **3.0293s** per query | **NOT TESTED** |
| **F. LLM Synthesis Latency** | **2.5317s** per case | **6.5975s** per case | **9.3838s** per case | **NOT TESTED** |
| **F. Avg Generated Tokens/Task** | **18.1 tokens** | **94.8 tokens** | **20.6 tokens** | **NOT TESTED** |
| **G. Minimum Hardware Profile** | 4 GB RAM (CPU-capable) | 8 GB RAM / Apple Silicon | 16 GB RAM / Apple Silicon | 16 GB RAM / 12 GB GPU VRAM |

---

## 4. Strengths, Weaknesses, and Failure Analysis

### Candidate 1: Qwen 2.5 1.5B (Active Baseline Default)
- **Strengths:**
  - Extremely lightweight memory footprint (986 MB disk, ~1.1 GB RAM active).
  - Fast inference: **0.59s tool selection**, **2.53s synthesis**.
  - 100% valid JSON generation rate with concise argument output (avg 18.1 tokens/task).
  - Reliable factual extraction when complete empirical evidence is present.
- **Weaknesses:**
  - Vulnerable to false-premise sycophancy and speculation on unprovided parameters (synthesis score: 33.3%).
- **Verdict:** **Retained as default lightweight baseline** for Milestone 1. Guarded by the deterministic orchestrator and `EvidenceBundle` limitation checks.

### Candidate 2: Phi-3.5 Mini 3.8B (Tested Alternative)
- **Strengths:**
  - Solid reasoning in evidence synthesis (66.7% score), correctly rejecting false premises (Case 3).
  - Moderate RAM consumption (~2.8 GB RAM).
- **Weaknesses:**
  - Conversational verbosity: Failed strict zero-shot single-JSON tool-call formatting (0% valid JSON), outputting conversational explanations and duplicate JSON blocks.
  - Slower inference (**4.77s tool-call latency**, **6.60s synthesis latency**) due to high generated token count (94.8 tokens/task).
- **Verdict:** **Candidate for long-context analysis (128k)**, but requires explicit constrained-grammar decoding (e.g. GBNF / JSON mode) to avoid conversational drift.

### Candidate 3: Llama 3.1 8B (Power Tier Baseline)
- **Strengths:**
  - Top-tier formatting adherence (100% valid JSON rate, avg 20.6 tokens/task).
  - Matches Qwen 2.5 on tool selection and argument generation (**78.6%** accuracy) without planner guidance.
  - Superior evidence synthesis (**66.7%** passed), firmly refuting contradictory premises without hallucinating.
- **Weaknesses:**
  - Higher resource utilization (~5.8 GB active RAM) and higher latency (**3.03s tool call**, **9.38s synthesis** on CPU/Unified Memory).
- **Verdict:** **Recommended model for high-fidelity technical synthesis** on developer workstations with 16 GB RAM.

### Candidate 4: Mistral Nemo 12B (Extended Power Profile)
- **Status:** **NOT TESTED** in local Ollama daemon.
- **Reason:** Model footprint (~7.3 GB disk, ~8.5–10 GB active RAM) risks system memory saturation alongside development IDEs and local databases on a 16 GB workstation. Left unbenchmarked to avoid synthetic figures.

---

## 5. Recommended Model Strategy (Accuracy vs Latency vs RAM)

Based strictly on the measured empirical data:

1. **Default Production Baseline — `qwen2.5:1.5b` (Tier 1):**
   - **When to use:** Daily interactive development, resource-constrained laptops (4–8 GB RAM), or CI/CD automated test harnesses where low latency (<0.6s) is critical.
   - **Mitigation:** The agent's deterministic planner and orchestrator bypass LLM limitations by validating arguments against MCP schemas and flagging missing facts before query generation.

2. **High-Fidelity Engineering Analysis — `llama3.1:8b` (Tier 2/3):**
   - **When to use:** Deep binary reverse engineering, complex multi-hop code comprehension, and final report synthesis where accuracy on ambiguous evidence is paramount.
   - **Trade-off:** 5.1x higher tool-calling latency (3.03s vs 0.59s) and 3.7x higher synthesis latency (9.38s vs 2.53s), requiring a 16 GB RAM host.

3. **Hybrid Agent Recommendation:**
   - Run the **deterministic planner + MCP tool execution** (latency: **0.0639s**, 100% accuracy) for all query routing and evidence gathering.
   - Dispatch the aggregated `EvidenceBundle` to **`qwen2.5:1.5b`** for rapid factual summaries, or optionally to **`llama3.1:8b`** when complex multi-hypothesis reasoning is requested.

---

## 6. Reproducible Model Evaluation Commands

To run the genuine model evaluation suite against local Ollama:
```bash
python3 benchmarks/evaluate_models.py
```
- Detailed evaluation results are saved to: `benchmarks/results/model_evaluation_report.json`.
- Raw terminal execution logs are preserved in: `benchmarks/verification/model_evaluation_run.txt`.
