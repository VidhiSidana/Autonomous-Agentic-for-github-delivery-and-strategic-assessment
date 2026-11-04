"""
Comprehensive Model Evaluation Suite for Samsung PRISM Unified Engineering Agent.

Evaluates open-weight candidate models against Ollama for:
1. Model Availability Verification (Ollama API /api/tags)
2. Direct LLM Tool-Selection Accuracy (intent classification across 14 varied queries)
3. LLM Argument-Generation Accuracy (presence of required arguments & exact key-value match)
4. Overall Tool-Call Specification Correctness (tool correct AND exact arguments correct)
5. Evidence-Grounded Answer Synthesis (factual extraction, architecture, entry point, section size, contradiction checks)

Models Evaluated:
- Qwen 2.5 1.5B (Active Baseline Default: qwen2.5:1.5b)
- Phi-3.5 Mini 3.8B (Shortlisted Profile: phi3.5:latest)
- Mistral Nemo 12B (Shortlisted Profile: mistral-nemo:12b)

If a model is not installed/reachable in Ollama, it is accurately recorded as
NOT TESTED / UNAVAILABLE without fabricating synthetic results.
"""

import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from agent.llm import LocalLLM

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("evaluate_models")

CANDIDATE_MODELS = [
    {
        "model_tag": "qwen2.5:1.5b",
        "family": "Qwen 2.5",
        "parameters": "1.54B",
        "quantization": "Q4_K_M",
        "target_tier": "Tier 1 (Fast / Edge Baseline)",
        "min_ram_gb": 4,
    },
    {
        "model_tag": "phi3.5:latest",
        "family": "Phi-3.5 Mini",
        "parameters": "3.82B",
        "quantization": "Q4_K_M",
        "target_tier": "Tier 2 (Balanced / Daily Engineer)",
        "min_ram_gb": 8,
    },
    {
        "model_tag": "mistral-nemo:12b",
        "family": "Mistral Nemo",
        "parameters": "12.2B",
        "quantization": "Q4_K_M",
        "target_tier": "Tier 3 (Power / Reverse Engineering)",
        "min_ram_gb": 16,
    },
]

# 14 Diverse, representative tool selection and argument evaluation tasks
EVALUATION_TASKS = [
    {
        "task_id": "T01_FUNC_DISCOVERY",
        "domain": "code_analysis",
        "query": "Find all function definitions across the entire codebase",
        "expected_tool": "find_functions",
        "required_args": [],
        "expected_args": {},
    },
    {
        "task_id": "T02_CALLERS_PROCESS_QUERY",
        "domain": "code_analysis",
        "query": "Who calls the function process_query in this repository?",
        "expected_tool": "find_callers",
        "required_args": ["target"],
        "expected_args": {"target": "process_query"},
    },
    {
        "task_id": "T03_CALLERS_CALCULATE_HASH",
        "domain": "code_analysis",
        "query": "Find all callers of the function calculate_checksum",
        "expected_tool": "find_callers",
        "required_args": ["target"],
        "expected_args": {"target": "calculate_checksum"},
    },
    {
        "task_id": "T04_CALLEES_DISPATCH",
        "domain": "code_analysis",
        "query": "Which functions does dispatch_request call?",
        "expected_tool": "find_callees",
        "required_args": ["target"],
        "expected_args": {"target": "dispatch_request"},
    },
    {
        "task_id": "T05_FILE_OUTLINE",
        "domain": "code_analysis",
        "query": "Show me the class and method declarations in agent/orchestrator.py",
        "expected_tool": "get_file_outline",
        "required_args": ["file_path"],
        "expected_args": {"file_path": "agent/orchestrator.py"},
    },
    {
        "task_id": "T06_BIN_ANALYZE_SAMPLE",
        "domain": "binary_analysis",
        "query": "Analyse binary sample_authorized.exe and report its PE architecture and headers",
        "expected_tool": "analyze_binary",
        "required_args": ["file_path"],
        "expected_args": {"file_path": "sample_authorized.exe"},
    },
    {
        "task_id": "T07_BIN_ANALYZE_APP",
        "domain": "binary_analysis",
        "query": "Inspect the PE header and section count of release_build.exe",
        "expected_tool": "analyze_binary",
        "required_args": ["file_path"],
        "expected_args": {"file_path": "release_build.exe"},
    },
    {
        "task_id": "T08_BIN_DISASM_ENTRY",
        "domain": "binary_analysis",
        "query": "Disassemble the machine code instructions of binary sample_authorized.exe",
        "expected_tool": "disassemble_binary",
        "required_args": ["file_path"],
        "expected_args": {"file_path": "sample_authorized.exe"},
    },
    {
        "task_id": "T09_BIN_IMPORTS",
        "domain": "binary_analysis",
        "query": "List all imported DLLs and API functions for sample_authorized.exe",
        "expected_tool": "find_binary_imports",
        "required_args": ["file_path"],
        "expected_args": {"file_path": "sample_authorized.exe"},
    },
    {
        "task_id": "T10_MEMORY_SAVE",
        "domain": "memory",
        "query": "Remember this engineering finding: SQLite WAL mode improves concurrency",
        "expected_tool": "save_finding",
        "required_args": ["content"],
        "expected_args": {"content": "SQLite WAL mode improves concurrency"},
    },
    {
        "task_id": "T11_MEMORY_SEARCH",
        "domain": "memory",
        "query": "Search persistent memory for findings related to WAL mode",
        "expected_tool": "search_memory",
        "required_args": ["query"],
        "expected_args": {"query": "WAL mode"},
    },
    {
        "task_id": "T12_MISSING_ARGS",
        "domain": "binary_analysis",
        "query": "Analyse binary and tell me if it is 64-bit",
        "expected_tool": "analyze_binary",
        "required_args": ["file_path"],
        # Model should either output empty file_path, omit it, or output clarification
        "expected_args": {"file_path": ""},
    },
    {
        "task_id": "T13_INVALID_REQUEST",
        "domain": "unsupported",
        "query": "Compile the C source code into a native executable",
        "expected_tool": "none",
        "required_args": [],
        "expected_args": {},
    },
    {
        "task_id": "T14_AMBIGUOUS_REQUEST",
        "domain": "unsupported",
        "query": "Please investigate the thing and tell me what it does",
        "expected_tool": "none",
        "required_args": [],
        "expected_args": {},
    },
]

TOOL_SYSTEM_PROMPT = """You are an automated tool selector for the Samsung PRISM Engineering Assistant.
Available Tools:
- find_functions(): Discover function definitions in codebase. Arguments: {}
- find_callers(target: str): Find functions that call the target. Arguments: {"target": "<func_name>"}
- find_callees(target: str): Find functions called by target. Arguments: {"target": "<func_name>"}
- get_file_outline(file_path: str): Get classes and methods in a file. Arguments: {"file_path": "<path>"}
- analyze_binary(file_path: str): Inspect PE headers and architecture. Arguments: {"file_path": "<path>"}
- disassemble_binary(file_path: str): Disassemble machine code instructions. Arguments: {"file_path": "<path>"}
- find_binary_imports(file_path: str): List imported DLLs and API functions. Arguments: {"file_path": "<path>"}
- save_finding(content: str): Persist an engineering finding to memory. Arguments: {"content": "<finding_text>"}
- search_memory(query: str): Search past engineering findings. Arguments: {"query": "<search_term>"}
- none(): Use when no tool matches the request, or when the request is invalid/ambiguous. Arguments: {}

You must respond ONLY with a single valid JSON object in this exact format:
{"tool": "<tool_name>", "arguments": {<key_value_pairs>}}
Do not write explanations, markdown fences, or text outside the JSON object."""


SYNTHESIS_EVAL_PROMPT = {
    "system": (
        "You are an on-premise Samsung PRISM engineering assistant. "
        "Answer the user query strictly and factually using ONLY the provided empirical tool evidence. "
        "Do not invent facts, hypothesize, or mention unverified information."
    ),
    "user_query": "What is the architecture, entry point, section count, and text section size of sample_authorized.exe?",
    "evidence_context": (
        "Empirical Evidence from Static Analysis:\n"
        "- File Path: sample_authorized.exe\n"
        "- Architecture: 0x8664 (IMAGE_FILE_MACHINE_AMD64 / x64 64-bit)\n"
        "- Section Count: 1 (.text)\n"
        "- Section .text: VirtualAddress 0x1000, Size 512 bytes, Characteristics 0x60000020\n"
        "- Entry Point RVA: 0x1000 (ImageBase 0x140000000 -> Physical Address 0x140001000)\n"
        "- Image Base: 0x140000000\n"
    ),
    "factual_checks": {
        "architecture_facts": ["0x8664", "amd64", "x64", "64-bit"],
        "entry_point_facts": ["0x1000", "0x140001000"],
        "section_count_facts": ["1", "single section", "one section"],
        "section_size_facts": ["512"],
        "forbidden_contradictions": ["32-bit", "arm", "arm64", "i386", "0x400000", "elf", "mach-o"],
    },
}


def _normalize_str(val: Any) -> str:
    if val is None:
        return ""
    s = str(val).strip().lower()
    # Normalize Windows/POSIX slashes
    s = s.replace("\\", "/")
    # Extract basename if path
    if "/" in s:
        s = Path(s).name
    return s


def evaluate_task(task: Dict[str, Any], raw_response: str) -> Dict[str, Any]:
    """
    Evaluates a single task across 5 distinct dimensions:
    1. valid_json
    2. correct_tool
    3. required_args_present
    4. exact_args_correct
    5. overall_correct
    """
    # 1. Valid JSON check
    json_match = re.search(r"\{.*\}", raw_response, re.DOTALL)
    valid_json = False
    parsed_json: Dict[str, Any] = {}
    if json_match:
        try:
            parsed_json = json.loads(json_match.group(0))
            valid_json = isinstance(parsed_json, dict)
        except Exception:
            valid_json = False

    selected_tool = str(parsed_json.get("tool", "")).strip().lower()
    if selected_tool.endswith("()"):
        selected_tool = selected_tool[:-2].strip()
    expected_tool = task["expected_tool"].lower()
    emitted_args = parsed_json.get("arguments", {})
    if not isinstance(emitted_args, dict):
        emitted_args = {}

    # 2. Correct Tool Selection
    correct_tool = (selected_tool == expected_tool)

    # 3. Required Arguments Present
    req_args = task.get("required_args", [])
    if req_args:
        required_present = all(
            k in emitted_args and emitted_args[k] is not None and str(emitted_args[k]).strip() != ""
            for k in req_args
        )
    else:
        required_present = True

    # 4. Exact Argument Correctness
    expected_args = task.get("expected_args", {})
    exact_correct = True
    failure_reasons = []

    if not correct_tool:
        exact_correct = False
        failure_reasons.append(f"Tool mismatch: expected '{expected_tool}', got '{selected_tool}'")
    else:
        if not expected_args:
            # If no args expected, an empty dict is correct
            if emitted_args:
                # If non-empty, check if extra unexpected arguments were provided
                exact_correct = False
                failure_reasons.append(f"Expected empty arguments, got {list(emitted_args.keys())}")
        else:
            for k, expected_v in expected_args.items():
                if k not in emitted_args:
                    exact_correct = False
                    failure_reasons.append(f"Missing expected argument '{k}'")
                    continue
                actual_v = emitted_args[k]
                norm_actual = _normalize_str(actual_v)
                norm_expected = _normalize_str(expected_v)

                # Special handling for missing args task (T12)
                if task["task_id"] == "T12_MISSING_ARGS":
                    if norm_actual == "" or norm_actual is None:
                        # Correctly identified empty or missing file
                        pass
                    else:
                        # Emitted a hallucinated or dummy file path
                        exact_correct = False
                        failure_reasons.append(f"Expected empty/omitted arg for missing path, got '{actual_v}'")
                elif norm_expected in norm_actual or norm_actual == norm_expected:
                    # Match
                    pass
                else:
                    exact_correct = False
                    failure_reasons.append(
                        f"Argument '{k}' value mismatch: expected '{expected_v}', got '{actual_v}'"
                    )

    # 5. Overall Correctness: Tool correct AND exact arguments correct
    overall_correct = correct_tool and exact_correct

    return {
        "task_id": task["task_id"],
        "domain": task["domain"],
        "query": task["query"],
        "expected_tool": task["expected_tool"],
        "selected_tool": selected_tool,
        "expected_arguments": task.get("expected_args", {}),
        "emitted_arguments": emitted_args,
        "valid_json": valid_json,
        "correct_tool": correct_tool,
        "required_args_present": required_present,
        "exact_args_correct": exact_correct,
        "overall_correct": overall_correct,
        "failure_reasons": failure_reasons,
        "raw_response_snippet": raw_response[:180].replace("\n", " "),
    }


def evaluate_synthesis(raw_response: str) -> Dict[str, Any]:
    """
    Evaluates evidence-grounded answer synthesis against factual checks and contradictions.
    """
    resp_lower = raw_response.lower()
    checks = SYNTHESIS_EVAL_PROMPT["factual_checks"]

    # Factual checks
    arch_match = any(fact.lower() in resp_lower for fact in checks["architecture_facts"])
    entry_match = any(fact.lower() in resp_lower for fact in checks["entry_point_facts"])
    section_count_match = any(fact.lower() in resp_lower for fact in checks["section_count_facts"])
    section_size_match = any(fact.lower() in resp_lower for fact in checks["section_size_facts"])

    # Contradiction checks
    contradictions_found = [
        bad for bad in checks["forbidden_contradictions"]
        if bad.lower() in resp_lower
    ]
    no_contradictions = (len(contradictions_found) == 0)

    # Passed criteria
    passed_criteria = sum([
        arch_match,
        entry_match,
        section_count_match,
        section_size_match,
        no_contradictions,
    ])
    total_criteria = 5
    factual_score = f"{(passed_criteria / total_criteria) * 100:.1f}%"

    return {
        "evaluation_type": "Structured factual & keyword verification check",
        "total_criteria": total_criteria,
        "passed_criteria": passed_criteria,
        "factual_accuracy_score": factual_score,
        "architecture_verified": arch_match,
        "entry_point_verified": entry_match,
        "section_count_verified": section_count_match,
        "section_size_verified": section_size_match,
        "no_contradictions_verified": no_contradictions,
        "contradictions_found": contradictions_found,
        "raw_model_response": raw_response,
    }


def run_model_evaluation() -> Dict[str, Any]:
    """Run the complete model evaluation suite."""
    report: Dict[str, Any] = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "suite_name": "Samsung PRISM Milestone 1 Genuine Model Evaluation",
        "evaluator_version": "v15",
        "host_environment": {
            "platform": sys.platform,
            "python_version": sys.version.split()[0],
        },
        "total_task_count": len(EVALUATION_TASKS),
        "models": [],
    }

    logger.info(f"Starting V15 Model Evaluation Suite across {len(EVALUATION_TASKS)} tasks...")

    for candidate in CANDIDATE_MODELS:
        tag = candidate["model_tag"]
        logger.info(f"Assessing model candidate: {tag} ({candidate['family']})")

        llm = LocalLLM(model=tag)
        is_available, avail_msg = llm.check_availability()

        model_entry: Dict[str, Any] = {
            "model_tag": tag,
            "family": candidate["family"],
            "parameters": candidate["parameters"],
            "quantization": candidate["quantization"],
            "target_tier": candidate["target_tier"],
            "min_ram_gb": candidate["min_ram_gb"],
            "available_in_ollama": is_available,
            "status_message": avail_msg,
        }

        if not is_available:
            logger.warning(f"Model '{tag}' unavailable: {avail_msg}")
            model_entry["evaluation_status"] = "NOT TESTED"
            model_entry["reason"] = "Model not pulled in local Ollama daemon or host RAM constrained."
            report["models"].append(model_entry)
            continue

        logger.info(f"Model '{tag}' is available. Executing empirical evaluation...")
        model_entry["evaluation_status"] = "TESTED"

        # 1. Tool Selection & Argument Generation across 14 tasks
        task_results = []
        valid_json_count = 0
        correct_tool_count = 0
        req_args_present_count = 0
        exact_args_correct_count = 0
        overall_correct_count = 0
        latencies = []

        for task in EVALUATION_TASKS:
            t0 = time.perf_counter()
            messages = [
                {"role": "system", "content": TOOL_SYSTEM_PROMPT},
                {"role": "user", "content": f"Task: {task['query']}"},
            ]
            try:
                resp = llm.chat(messages)
                elapsed = time.perf_counter() - t0
                latencies.append(elapsed)
            except Exception as exc:
                elapsed = time.perf_counter() - t0
                resp = f"ERROR: {exc}"

            res = evaluate_task(task, resp)
            res["latency_seconds"] = round(elapsed, 4)
            task_results.append(res)

            if res["valid_json"]:
                valid_json_count += 1
            if res["correct_tool"]:
                correct_tool_count += 1
            if res["required_args_present"]:
                req_args_present_count += 1
            if res["exact_args_correct"]:
                exact_args_correct_count += 1
            if res["overall_correct"]:
                overall_correct_count += 1

        total_t = len(EVALUATION_TASKS)
        avg_lat = round(sum(latencies) / len(latencies), 4) if latencies else 0.0

        model_entry["tool_calling_evaluation"] = {
            "total_tasks": total_t,
            "valid_json_responses": valid_json_count,
            "valid_json_rate": f"{(valid_json_count / total_t) * 100:.1f}%",
            "correct_tool_selections": correct_tool_count,
            "tool_selection_accuracy": f"{(correct_tool_count / total_t) * 100:.1f}%",
            "required_args_present": req_args_present_count,
            "required_args_rate": f"{(req_args_present_count / total_t) * 100:.1f}%",
            "exact_arguments_correct": exact_args_correct_count,
            "exact_argument_accuracy": f"{(exact_args_correct_count / total_t) * 100:.1f}%",
            "overall_specification_correct": overall_correct_count,
            "overall_tool_call_accuracy": f"{(overall_correct_count / total_t) * 100:.1f}%",
            "average_tool_selection_latency_seconds": avg_lat,
            "task_breakdown": task_results,
        }

        # 2. Evidence-Grounded Synthesis Evaluation
        logger.info(f"Evaluating evidence synthesis for '{tag}'...")
        synthesis_messages = [
            {"role": "system", "content": SYNTHESIS_EVAL_PROMPT["system"]},
            {
                "role": "user",
                "content": (
                    f"{SYNTHESIS_EVAL_PROMPT['user_query']}\n\n"
                    f"{SYNTHESIS_EVAL_PROMPT['evidence_context']}"
                ),
            },
        ]
        t0 = time.perf_counter()
        try:
            synth_resp = llm.chat(synthesis_messages)
            synth_elapsed = time.perf_counter() - t0
        except Exception as exc:
            synth_resp = f"ERROR: {exc}"
            synth_elapsed = 0.0

        synthesis_analysis = evaluate_synthesis(synth_resp)
        synthesis_analysis["latency_seconds"] = round(synth_elapsed, 4)
        model_entry["evidence_synthesis_evaluation"] = synthesis_analysis

        report["models"].append(model_entry)

    # Save to benchmarks/results/model_evaluation_report.json
    results_dir = PROJECT_ROOT / "benchmarks" / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    report_file = results_dir / "model_evaluation_report.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    logger.info(f"Saved evaluation report to {report_file}")
    return report


if __name__ == "__main__":
    rep = run_model_evaluation()
    print("\n" + "=" * 65)
    print(" V15 GENUINE MODEL EVALUATION SUMMARY")
    print("=" * 65)
    for m in rep["models"]:
        tag = m["model_tag"]
        status = m.get("evaluation_status", "UNKNOWN")
        print(f"Model: {tag} ({m['family']}) -> {status}")
        if status == "TESTED":
            tc = m["tool_calling_evaluation"]
            sy = m["evidence_synthesis_evaluation"]
            print(f"  - Valid JSON Rate:             {tc['valid_json_rate']} ({tc['valid_json_responses']}/{tc['total_tasks']})")
            print(f"  - Tool Selection Accuracy:     {tc['tool_selection_accuracy']} ({tc['correct_tool_selections']}/{tc['total_tasks']})")
            print(f"  - Required Arguments Present:  {tc['required_args_rate']} ({tc['required_args_present']}/{tc['total_tasks']})")
            print(f"  - Exact Argument Accuracy:     {tc['exact_argument_accuracy']} ({tc['exact_arguments_correct']}/{tc['total_tasks']})")
            print(f"  - Overall Tool-Call Accuracy:  {tc['overall_tool_call_accuracy']} ({tc['overall_specification_correct']}/{tc['total_tasks']})")
            print(f"  - Avg Tool-Call Latency:       {tc['average_tool_selection_latency_seconds']}s")
            print(f"  - Evidence Synthesis Score:    {sy['factual_accuracy_score']} ({sy['passed_criteria']}/{sy['total_criteria']} criteria)")
            print(f"  - Synthesis Latency:           {sy['latency_seconds']}s")
        else:
            print(f"  - Reason: {m.get('reason')}")
    print("=" * 65)
