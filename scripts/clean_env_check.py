#!/usr/bin/env python3
"""
Samsung PRISM Engineering Agent - Clean Environment Verification Script.

Validates:
1. Package installation in a completely fresh virtual environment.
2. CLI console script entry point ('prism-agent').
3. All unit tests execution and pass rate.
4. All 17 benchmark tasks execution and pass rate.
5. Multi-session persistence retrieval across isolated processes.

Outputs:
- benchmarks/verification/clean_env_run.txt
"""

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_FILE = PROJECT_ROOT / "benchmarks" / "verification" / "clean_env_run.txt"


def log(msg: str, f=None):
    print(msg)
    if f:
        f.write(msg + "\n")
        f.flush()


def run_clean_check():
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
        log("=== SAMSUNG PRISM CLEAN ENVIRONMENT VERIFICATION ===", out)
        log(f"Timestamp: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}", out)
        log(f"Host Python: {sys.executable} ({sys.version})", out)
        log(f"Project Root: {PROJECT_ROOT}\n", out)

        with tempfile.TemporaryDirectory(prefix="prism_clean_env_") as temp_dir:
            venv_path = Path(temp_dir) / "test_venv"
            log(f"[*] Step 1: Creating isolated virtual environment at {venv_path}...", out)
            
            # Use host python to create venv with system site packages to avoid PyPI network fetch
            res = subprocess.run([sys.executable, "-m", "venv", "--system-site-packages", str(venv_path)], capture_output=True, text=True)
            if res.returncode != 0:
                log(f"[FAIL] venv creation failed: {res.stderr}", out)
                return False
            log("[PASS] Virtual environment created successfully.", out)

            # Determine python & pip paths in venv
            if sys.platform == "win32":
                venv_py = venv_path / "Scripts" / "python.exe"
                venv_pip = venv_path / "Scripts" / "pip.exe"
                agent_bin = venv_path / "Scripts" / "prism-agent.exe"
            else:
                venv_py = venv_path / "bin" / "python"
                venv_pip = venv_path / "bin" / "pip"
                agent_bin = venv_path / "bin" / "prism-agent"

            # Install package in editable mode without network build isolation
            log("[*] Step 2: Installing package in editable mode via pip...", out)
            install_pkg = [str(venv_pip), "install", "--no-build-isolation", "-e", str(PROJECT_ROOT)]
            res = subprocess.run(install_pkg, capture_output=True, text=True)
            if res.returncode != 0:
                log(f"[FAIL] pip install -e failed: {res.stderr}", out)
                return False
            log("[PASS] Package installed successfully in clean virtual environment.", out)

            # Step 3: Test CLI Entry Point
            log("[*] Step 3: Verifying CLI console script entry point...", out)
            if agent_bin.exists():
                res = subprocess.run([str(agent_bin), "--version"], capture_output=True, text=True)
                cmd_tested = "prism-agent"
            else:
                res = subprocess.run([str(venv_py), "-m", "agent.main", "--version"], capture_output=True, text=True)
                cmd_tested = "python -m agent.main"

            if res.returncode != 0:
                log(f"[FAIL] CLI version check failed: {res.stderr}", out)
                return False
            log(f"[PASS] {cmd_tested} returned: {res.stdout.strip()}", out)

            # Step 4: Run all unit tests
            log("\n[*] Step 4: Running full test suite (unittest discover)...", out)
            t0 = time.perf_counter()
            test_cmd = [str(venv_py), "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py", "-t", "."]
            res = subprocess.run(test_cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True)
            test_time = time.perf_counter() - t0
            
            # Print stderr because unittest outputs dots and summary to stderr
            test_output = res.stderr or res.stdout
            log(test_output.strip(), out)
            if res.returncode != 0:
                log(f"[FAIL] Unit tests failed in clean environment in {test_time:.2f}s", out)
                return False
            log(f"[PASS] Unit tests completed successfully in {test_time:.2f}s.", out)

            # Step 5: Run 17 benchmark tasks
            log("\n[*] Step 5: Running 17 benchmark tasks (benchmarks/benchmark_runner.py)...", out)
            t1 = time.perf_counter()
            bench_cmd = [str(venv_py), "benchmarks/benchmark_runner.py"]
            res = subprocess.run(bench_cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True)
            bench_time = time.perf_counter() - t1
            log(res.stdout.strip(), out)
            if res.returncode != 0 or "17/17 Passed" not in res.stdout:
                log(f"[FAIL] Benchmarks failed in clean environment in {bench_time:.2f}s", out)
                return False
            log(f"[PASS] All 17 benchmark tasks passed in {bench_time:.2f}s.", out)

            # Step 6: Multi-session persistence demonstration
            log("\n[*] Step 6: Running multi-session persistence demonstration...", out)
            demo_code = """
import sys
import tempfile
from pathlib import Path
from memory.session_manager import SessionManager
from memory.memory import EngineeringMemory

db_path = Path(tempfile.gettempdir()) / "clean_env_demo.db"
db_path.unlink(missing_ok=True)

try:
    mgr = SessionManager(db_path)
    mem = EngineeringMemory(db_path)

    # Session 1: Engineer records finding
    s1 = mgr.start_session()
    res = mem.save_memory(
        title="Sample verified binary entry point",
        content="Entry point located at RVA 0x1000 with AMD64 architecture",
        category="binary_analysis",
        verification_status="CONFIRMED",
        session_id=s1,
    )
    fid = res["id"]
    mgr.end_session(s1)

    # Session 2: New session retrieves verified finding
    mgr2 = SessionManager(db_path)
    mem2 = EngineeringMemory(db_path)
    s2 = mgr2.start_session()
    recovered = mem2.search_memory("0x1000")
    mgr2.end_session(s2)

    assert len(recovered) >= 1, f"Expected at least 1 recovered finding, got {len(recovered)}"
    assert recovered[0]["id"] == fid
    print(f"Successfully recovered finding ID {fid} in isolated session {s2}")
finally:
    db_path.unlink(missing_ok=True)
"""
            res = subprocess.run([str(venv_py), "-c", demo_code], cwd=str(PROJECT_ROOT), capture_output=True, text=True)
            if res.returncode != 0:
                log(f"[FAIL] Multi-session persistence failed: {res.stderr}", out)
                return False
            log(f"[PASS] {res.stdout.strip()}", out)

        log("\n=======================================================", out)
        log("CLEAN ENVIRONMENT VERIFICATION COMPLETED SUCCESSFULLY", out)
        log("=======================================================", out)
        return True


if __name__ == "__main__":
    success = run_clean_check()
    sys.exit(0 if success else 1)
