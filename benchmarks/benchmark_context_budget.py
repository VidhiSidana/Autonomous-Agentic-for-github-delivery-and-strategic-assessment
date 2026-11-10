"""
Context Budget & Tool Schema Benchmark for Samsung PRISM Unified Engineering Agent.

Compares:
1. Baseline: Static monolithic tool prompt (all 13-16 tools exposed on every call, ~840 prompt tokens/task).
2. Milestone 2: Dynamic Category-Routed Tool Selection (4-8 category tools, compact schemas, ~250-350 prompt tokens/task).

Measures empirically against local Ollama models:
- Tool selection accuracy (%)
- Exact argument accuracy (%)
- Overall accuracy (%)
- Total prompt tokens consumed
- Average prompt tokens per task
- Average latency per task (s)

Saves results to benchmarks/results/context_budget_report.json without fabricating data.
"""

import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from agent.llm import LocalLLM
from agent.tool_router import build_tool_selection_prompt
from benchmarks.evaluate_models import (
    CANDIDATE_MODELS,
    EVALUATION_TASKS,
    TOOL_SYSTEM_PROMPT,
    evaluate_task,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("benchmark_context_budget")


def run_benchmark_for_model(
    model_tag: str,
    llm: LocalLLM,
) -> Dict[str, Any]:
    """Runs before/after comparison for a single model."""
    results = {}

    for mode in ["baseline_monolithic", "milestone2_dynamic_router"]:
        logger.info(f"Running mode: {mode} on {model_tag}...")
        task_results = []
        valid_json_count = 0
        correct_tool_count = 0
        exact_args_count = 0
        overall_correct_count = 0
        latencies = []

        for task in EVALUATION_TASKS:
            t0 = time.perf_counter()
            if mode == "baseline_monolithic":
                system_prompt = TOOL_SYSTEM_PROMPT
            else:
                # Milestone 2: Category-routed compact prompt
                system_prompt = build_tool_selection_prompt(task.get("domain"))

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Task: {task['query']}"},
            ]
            meta = {}
            try:
                resp, meta = llm.chat_with_metadata(messages)
                elapsed = time.perf_counter() - t0
                latencies.append(elapsed)
            except Exception as exc:
                elapsed = time.perf_counter() - t0
                resp = f"ERROR: {exc}"

            res = evaluate_task(task, resp)
            res["latency_seconds"] = round(elapsed, 4)
            res["prompt_eval_count"] = meta.get("prompt_eval_count")
            res["eval_count"] = meta.get("eval_count")
            task_results.append(res)

            if res["valid_json"]:
                valid_json_count += 1
            if res["correct_tool"]:
                correct_tool_count += 1
            if res["exact_args_correct"]:
                exact_args_count += 1
            if res["overall_correct"]:
                overall_correct_count += 1

        total_t = len(EVALUATION_TASKS)
        avg_lat = round(sum(latencies) / len(latencies), 4) if latencies else 0.0
        total_prompt_tok = sum(r.get("prompt_eval_count") or 0 for r in task_results)
        avg_prompt_tok = round(total_prompt_tok / total_t, 1) if total_t > 0 else 0.0

        results[mode] = {
            "total_tasks": total_t,
            "correct_tool_selections": correct_tool_count,
            "tool_selection_accuracy": f"{round(100 * correct_tool_count / total_t, 1)}%",
            "exact_arguments_correct": exact_args_count,
            "exact_argument_accuracy": f"{round(100 * exact_args_count / total_t, 1)}%",
            "overall_specification_correct": overall_correct_count,
            "overall_tool_call_accuracy": f"{round(100 * overall_correct_count / total_t, 1)}%",
            "total_prompt_tokens": total_prompt_tok,
            "avg_prompt_tokens_per_task": avg_prompt_tok,
            "avg_latency_seconds": avg_lat,
        }

    # Compute savings
    base_tok = results["baseline_monolithic"]["total_prompt_tokens"]
    routed_tok = results["milestone2_dynamic_router"]["total_prompt_tokens"]
    tok_reduction_pct = (
        round(100 * (base_tok - routed_tok) / base_tok, 1) if base_tok > 0 else 0.0
    )

    return {
        "model_tag": model_tag,
        "baseline_monolithic": results["baseline_monolithic"],
        "milestone2_dynamic_router": results["milestone2_dynamic_router"],
        "prompt_token_reduction_pct": f"{tok_reduction_pct}%",
        "tokens_saved": base_tok - routed_tok,
    }


def main():
    report_path = PROJECT_ROOT / "benchmarks" / "results" / "context_budget_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)

    report: Dict[str, Any] = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "title": "Samsung PRISM Milestone 2 Context Budget & Dynamic Tool Router Evaluation",
        "total_evaluation_tasks": len(EVALUATION_TASKS),
        "models_evaluated": [],
    }

    # Test available models in Ollama (e.g. qwen2.5:1.5b)
    for candidate in CANDIDATE_MODELS:
        tag = candidate["model_tag"]
        llm = LocalLLM(model=tag, max_tokens=128, timeout=45, format="json")
        is_available, reason = llm.check_availability()
        if not is_available:
            report["models_evaluated"].append({
                "model_tag": tag,
                "status": "NOT TESTED",
                "reason": reason,
            })
            continue

        logger.info(f"Benchmarking model {tag}...")
        model_res = run_benchmark_for_model(tag, llm)
        model_res["status"] = "TESTED"
        report["models_evaluated"].append(model_res)

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(f"\n[Context Budget Benchmark Complete]")
    print(f"Report written to: {report_path}")


if __name__ == "__main__":
    main()

