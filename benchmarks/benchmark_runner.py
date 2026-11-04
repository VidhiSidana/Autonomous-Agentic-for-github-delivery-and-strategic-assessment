"""
Benchmark Runner for Samsung PRISM Unified Engineering Agent.
Evaluates agent on Milestone 1 Ground Truth tasks and records execution metrics.
"""

import asyncio
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from agent.orchestrator import AgentOrchestrator
from memory.memory import EngineeringMemory
from memory.session_manager import SessionManager

logger = logging.getLogger(__name__)


async def run_benchmarks(
    dataset_path: Path,
    output_dir: Path,
) -> dict:
    """
    Run ground-truth tasks and record performance metrics.
    """
    with open(dataset_path, "r", encoding="utf-8") as f:
        suite = json.load(f)

    # Use a dedicated benchmark test database
    output_dir.mkdir(parents=True, exist_ok=True)
    bench_db = output_dir / "benchmark_test_memory.db"
    if bench_db.exists():
        bench_db.unlink()

    memory = EngineeringMemory(db_path=bench_db)
    session_mgr = SessionManager(db_path=bench_db)
    orchestrator = AgentOrchestrator(
        memory=memory,
        session_manager=session_mgr,
        default_repo_dir=PROJECT_ROOT,
    )

    results = []
    passed_count = 0
    total_count = len(suite["tasks"])

    print(f"\nRunning {total_count} benchmark tasks from {dataset_path.name}...\n")

    for task in suite["tasks"]:
        task_id = task["id"]
        query = task["query"]
        expected_cat = task.get("expected_category")

        start_time = time.perf_counter()
        try:
            orch_result = await orchestrator.process_query(query)
            elapsed = time.perf_counter() - start_time

            # Validate against ground-truth criteria
            passed = True
            reasons = []

            if expected_cat and orch_result.category != expected_cat:
                passed = False
                reasons.append(f"Expected category {expected_cat}, got {orch_result.category}")

            if task.get("clarification_needed") and not orch_result.clarification_needed:
                passed = False
                reasons.append("Expected clarification_needed=True, got False")

            if task.get("expected_verification_status"):
                status = orch_result.plan.memory_verification_status
                if status != task["expected_verification_status"]:
                    passed = False
                    reasons.append(f"Expected status {task['expected_verification_status']}, got {status}")

            if task.get("expected_content_match"):
                found_match = any(
                    task["expected_content_match"] in it.detail
                    for it in orch_result.evidence_bundle.items
                )
                if not found_match:
                    passed = False
                    reasons.append(f"Expected content match '{task['expected_content_match']}' not found in evidence")

            if passed:
                passed_count += 1
                status_str = "PASS"
            else:
                status_str = f"FAIL ({'; '.join(reasons)})"

            print(f"[{status_str}] Task {task_id}: {task['description']} ({elapsed:.3f}s)")

            results.append({
                "task_id": task_id,
                "category": orch_result.category,
                "description": task["description"],
                "passed": passed,
                "elapsed_seconds": round(elapsed, 4),
                "evidence_count": len(orch_result.evidence_bundle.items),
                "limitations_count": len(orch_result.evidence_bundle.limitations),
                "reasons": reasons,
            })

        except Exception as exc:
            elapsed = time.perf_counter() - start_time
            print(f"[ERROR] Task {task_id}: {exc}")
            results.append({
                "task_id": task_id,
                "passed": False,
                "error": str(exc),
                "elapsed_seconds": round(elapsed, 4),
            })

    await orchestrator.close()

    summary = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "suite_name": suite["benchmark_suite"],
        "total_tasks": total_count,
        "passed_tasks": passed_count,
        "success_rate": f"{(passed_count / total_count) * 100:.1f}%",
        "average_elapsed_seconds": round(
            sum(r["elapsed_seconds"] for r in results) / total_count, 4
        ),
        "results": results,
    }

    report_path = output_dir / "benchmark_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"\n==========================================")
    print(f" Benchmark Summary: {passed_count}/{total_count} Passed ({summary['success_rate']})")
    print(f" Report saved: {report_path}")
    print(f"==========================================\n")

    return summary


if __name__ == "__main__":
    dataset = PROJECT_ROOT / "benchmarks" / "datasets" / "milestone1_ground_truth.json"
    out_dir = PROJECT_ROOT / "benchmarks" / "results"
    asyncio.run(run_benchmarks(dataset, out_dir))

