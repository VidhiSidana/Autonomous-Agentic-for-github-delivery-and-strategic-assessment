"""
Benchmark Runner for Samsung PRISM Unified Engineering Agent.
Evaluates agent on Milestone 1 Ground Truth tasks and records execution metrics.
"""

import asyncio
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_DATASET_PATH = PROJECT_ROOT / "benchmarks" / "datasets" / "milestone1_ground_truth.json"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "benchmarks" / "results"

import config.settings
from agent.orchestrator import AgentOrchestrator
from agent.evidence import EvidenceKind
from memory.memory import EngineeringMemory
from memory.session_manager import SessionManager

logger = logging.getLogger(__name__)


def create_sample_pe_binary(target_path: Path) -> Path:
    """
    Generate a valid minimal AMD64 Windows PE binary with a .text section
    containing NOP and RET machine instructions for safe static analysis.
    """
    dos_header = b"MZ" + b"\x00" * 58 + (0x40).to_bytes(4, "little")
    pe_sig = b"PE\x00\x00"
    coff_header = (
        (0x8664).to_bytes(2, "little") + (1).to_bytes(2, "little") +
        (0).to_bytes(4, "little") + (0).to_bytes(4, "little") +
        (0).to_bytes(4, "little") + (240).to_bytes(2, "little") +
        (0x0022).to_bytes(2, "little")
    )
    opt_header = (
        (0x020B).to_bytes(2, "little") + b"\x0e\x00" + (512).to_bytes(4, "little") +
        (0).to_bytes(4, "little") + (0).to_bytes(4, "little") +
        (0x1000).to_bytes(4, "little") + (0x1000).to_bytes(4, "little") +
        (0x140000000).to_bytes(8, "little") + (0x1000).to_bytes(4, "little") +
        (0x200).to_bytes(4, "little") + (6).to_bytes(2, "little") + (0).to_bytes(2, "little") +
        (0).to_bytes(4, "little") + (6).to_bytes(2, "little") + (0).to_bytes(2, "little") +
        (0).to_bytes(4, "little") + (0x3000).to_bytes(4, "little") + (0x400).to_bytes(4, "little") +
        (0).to_bytes(4, "little") + (3).to_bytes(2, "little") + (0x8160).to_bytes(2, "little") +
        (0x100000).to_bytes(8, "little") + (0x1000).to_bytes(8, "little") +
        (0x100000).to_bytes(8, "little") + (0x1000).to_bytes(8, "little") +
        (0).to_bytes(4, "little") + (16).to_bytes(4, "little") + b"\x00" * (16 * 8)
    )
    sec_header = (
        b".text\x00\x00\x00" + (0x200).to_bytes(4, "little") + (0x1000).to_bytes(4, "little") +
        (0x200).to_bytes(4, "little") + (0x400).to_bytes(4, "little") +
        (0).to_bytes(4, "little") + (0).to_bytes(4, "little") +
        (0).to_bytes(2, "little") + (0).to_bytes(2, "little") +
        (0x60000020).to_bytes(4, "little")
    )
    header_bytes = dos_header + pe_sig + coff_header + opt_header + sec_header
    padding = b"\x00" * (0x400 - len(header_bytes))
    code_bytes = b"\x90\x90\x90\xc3" + b"\x00" * (0x200 - 4)
    pe_data = header_bytes + padding + code_bytes
    target_path.write_bytes(pe_data)
    return target_path


def run_cross_process_persistence_test(db_path: Path) -> dict[str, Any]:
    """
    Genuine cross-process persistence verification:
    1. Subprocess A saves a verified finding into SQLite and terminates.
    2. Subprocess B starts independently, searches the same database, and terminates.
    3. Verifies that content and verification status match across separate OS processes.
    """
    code_a = f"""
import sys
from pathlib import Path
sys.path.insert(0, {repr(str(PROJECT_ROOT))})
from memory.memory import EngineeringMemory
from memory.session_manager import SessionManager

db = Path({repr(str(db_path))})
mem = EngineeringMemory(db_path=db)
sm = SessionManager(db_path=db)
sid = sm.start_session()
res = mem.save_memory(
    title="Cross-Process Persistence Finding",
    content="authentication is handled in auth_service.py",
    category="architecture",
    verification_status="VERIFIED",
    session_id=sid,
)
print("PROCESS_A_SAVED_ID:" + str(res.get("id")))
"""
    proc_a = subprocess.run(
        [sys.executable, "-c", code_a],
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )

    code_b = f"""
import sys, json
from pathlib import Path
sys.path.insert(0, {repr(str(PROJECT_ROOT))})
from memory.memory import EngineeringMemory

db = Path({repr(str(db_path))})
mem = EngineeringMemory(db_path=db)
rows = mem.search_memory("authentication auth_service.py")
results = [dict(r) for r in rows]
print("PROCESS_B_RETRIEVED:" + json.dumps(results))
"""
    proc_b = subprocess.run(
        [sys.executable, "-c", code_b],
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )

    retrieved_data = []
    for line in proc_b.stdout.splitlines():
        if line.startswith("PROCESS_B_RETRIEVED:"):
            retrieved_data = json.loads(line.replace("PROCESS_B_RETRIEVED:", "", 1))
            break

    content_verified = False
    status_verified = False
    for item in retrieved_data:
        if "auth_service.py" in item.get("content", ""):
            content_verified = True
            if item.get("verification_status") == "VERIFIED":
                status_verified = True
                break

    return {
        "success": content_verified and status_verified,
        "process_a_exit": proc_a.returncode,
        "process_b_exit": proc_b.returncode,
        "items_retrieved": len(retrieved_data),
        "content_verified": content_verified,
        "status_verified": status_verified,
    }


async def run_benchmarks(
    dataset_path: Path = DEFAULT_DATASET_PATH,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> dict[str, Any]:
    """
    Run ground-truth tasks and record performance metrics.
    Returns the complete summary dictionary and saves benchmark_report.json.
    """
    with open(dataset_path, "r", encoding="utf-8") as f:
        suite = json.load(f)

    # Use a dedicated benchmark test database
    output_dir.mkdir(parents=True, exist_ok=True)
    bench_db = output_dir / "benchmark_test_memory.db"
    if bench_db.exists():
        try:
            bench_db.unlink()
        except Exception:
            pass

    # Create authorized sample binary for MT1 multi-tool testing
    sample_bin = output_dir.resolve() / "sample_authorized.exe"
    create_sample_pe_binary(sample_bin)

    # Authorize benchmark output directory
    orig_allowed_config = list(config.settings.BINARY_ALLOWED_DIRS)
    orig_allowed_env = os.environ.get("BINARY_ALLOWED_DIRS", "")
    resolved_out = output_dir.resolve()
    if resolved_out not in config.settings.BINARY_ALLOWED_DIRS:
        config.settings.BINARY_ALLOWED_DIRS.append(resolved_out)
    os.environ["BINARY_ALLOWED_DIRS"] = f"{resolved_out},{orig_allowed_env}".rstrip(",")

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
    cross_proc_report: Optional[dict[str, Any]] = None

    print(f"\nRunning {total_count} benchmark tasks from {dataset_path.name}...\n")

    try:
        for task in suite["tasks"]:
            task_id = task["id"]
            query = task["query"]
            expected_cat = task.get("expected_category")

            # For M2, execute real cross-process persistence test
            if task_id == "M2":
                cross_proc_report = run_cross_process_persistence_test(bench_db)
                session_mgr.start_session()

            # For MT1, ensure query targets the verified authorized binary
            if task_id == "MT1":
                query = f'Find functions in codebase and inspect binary "{sample_bin}"'

            start_time = time.perf_counter()
            try:
                orch_result = await orchestrator.process_query(query)
                elapsed = time.perf_counter() - start_time

                passed = True
                reasons = []

                if expected_cat and orch_result.category != expected_cat:
                    passed = False
                    reasons.append(f"Expected category {expected_cat}, got {orch_result.category}")

                if task.get("expected_symbol"):
                    exp_sym = task["expected_symbol"]
                    found_sym = (
                        orch_result.plan.function_name == exp_sym
                        or any(exp_sym in (it.function_name or "") or exp_sym in (it.detail or "") for it in orch_result.evidence_bundle.items)
                    )
                    if not found_sym:
                        passed = False
                        reasons.append(f"Expected symbol '{exp_sym}' not found in plan or evidence")

                if task.get("expected_file"):
                    exp_file = task["expected_file"]
                    found_file = (
                        orch_result.plan.file_path == exp_file
                        or any(exp_file in (it.file_path or "") or exp_file in (it.detail or "") for it in orch_result.evidence_bundle.items)
                    )
                    if not found_file:
                        passed = False
                        reasons.append(f"Expected file '{exp_file}' not found in plan or evidence")

                if task.get("expected_operation"):
                    exp_op = task["expected_operation"]
                    actual_op = orch_result.plan.memory_operation
                    if actual_op != exp_op:
                        passed = False
                        reasons.append(f"Expected memory operation '{exp_op}', got '{actual_op}'")

                if task.get("clarification_needed") and not orch_result.clarification_needed:
                    passed = False
                    reasons.append("Expected clarification_needed=True, got False")

                if task.get("expected_policy_result"):
                    pol_target = task.get("expected_policy_result")
                    found_policy = any(pol_target in it.detail or pol_target in it.summary for it in orch_result.evidence_bundle.items) or pol_target in orch_result.response_text
                    if not found_policy:
                        passed = False
                        reasons.append(f"Expected policy result '{pol_target}' not found")

                if task.get("sub_categories"):
                    for sub in task["sub_categories"]:
                        if sub not in orch_result.plan.sub_categories:
                            passed = False
                            reasons.append(f"Expected sub-category '{sub}' not in plan")

                # Multi-tool dual-branch execution validation (neither can be policy denial)
                multi_tool_details = {}
                if task_id == "MT1" or task.get("category") == "multi_tool":
                    code_ev = [
                        it for it in orch_result.evidence_bundle.items
                        if ("code" in it.source.lower() or "find_" in (it.tool_name or "") or "graph" in it.source.lower())
                        and it.kind == EvidenceKind.VERIFIED
                    ]
                    binary_ev = [
                        it for it in orch_result.evidence_bundle.items
                        if ("binary" in it.source.lower() or "pe" in it.source.lower() or "capstone" in it.source.lower())
                        and it.kind == EvidenceKind.VERIFIED
                        and "denied" not in it.summary.lower()
                        and "denied" not in it.detail.lower()
                    ]
                    if not (code_ev and binary_ev):
                        passed = False
                        reasons.append(f"Multi-tool execution failed: code_verified={bool(code_ev)}, binary_verified={bool(binary_ev)}")
                    else:
                        multi_tool_details = {
                            "code_branch": {"tool": code_ev[0].tool_name, "success": True, "source": code_ev[0].source},
                            "binary_branch": {"tool": binary_ev[0].tool_name, "success": True, "source": binary_ev[0].source, "file": binary_ev[0].file_path},
                        }

                if task_id == "M2" and cross_proc_report and not cross_proc_report.get("success"):
                    passed = False
                    reasons.append("Cross-process persistence verification failed between Subprocess A and B")

                if task.get("expected_tool"):
                    exp_tool = task["expected_tool"]
                    matching_terms = [exp_tool] if isinstance(exp_tool, str) else list(exp_tool)
                    if exp_tool in ("caller", "find_callers"):
                        matching_terms.extend(["trace_path", "find_callers", "caller"])
                    tool_matched = any(
                        any(term in it.source or (it.tool_name and term in it.tool_name) for term in matching_terms)
                        for it in orch_result.evidence_bundle.items
                    )
                    if not tool_matched:
                        passed = False
                        reasons.append(f"Expected tool invocation matching '{exp_tool}' not found in evidence items")

                if not task.get("clarification_needed") and not task.get("expected_policy_result"):
                    has_payload = any(len(it.detail or "") > 0 for it in orch_result.evidence_bundle.items)
                    if not has_payload:
                        passed = False
                        reasons.append("Tool execution produced no detailed payload content")

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

                task_record = {
                    "task_id": task_id,
                    "category": orch_result.category,
                    "description": task["description"],
                    "passed": passed,
                    "elapsed_seconds": round(elapsed, 4),
                    "evidence_count": len(orch_result.evidence_bundle.items),
                    "limitations_count": len(orch_result.evidence_bundle.limitations),
                    "reasons": reasons,
                }
                if multi_tool_details:
                    task_record["multi_tool_execution"] = multi_tool_details
                results.append(task_record)

            except Exception as exc:
                elapsed = time.perf_counter() - start_time
                print(f"[FAIL] Task {task_id}: Exception: {exc}")
                results.append({
                    "task_id": task_id,
                    "passed": False,
                    "error": str(exc),
                    "elapsed_seconds": round(elapsed, 4),
                    "reasons": [f"Execution exception: {exc}"],
                })

    finally:
        # Clean shutdown of all MCP sessions and resources
        try:
            await orchestrator.close()
        except Exception as e:
            logger.debug("Orchestrator cleanup warning: %s", e)
        config.settings.BINARY_ALLOWED_DIRS = orig_allowed_config
        if orig_allowed_env:
            os.environ["BINARY_ALLOWED_DIRS"] = orig_allowed_env
        else:
            os.environ.pop("BINARY_ALLOWED_DIRS", None)

    summary = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "suite_name": suite["benchmark_suite"],
        "total_tasks": total_count,
        "passed_tasks": passed_count,
        "success_rate": f"{(passed_count / total_count) * 100:.1f}%",
        "average_elapsed_seconds": round(
            sum(r["elapsed_seconds"] for r in results) / total_count, 4
        ),
        "cross_process_persistence": cross_proc_report,
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
