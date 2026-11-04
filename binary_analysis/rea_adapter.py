"""
Reverse-Engineering Analysis (REA) Integration Adapter
Samsung PRISM Worklet Component.

Responsibilities:
  - Define the formal REA interface contract for static binary analysis
  - Check whether the external REA tool or daemon has been provisioned
  - Safely fall back to PE/Capstone tools if REA access details are pending
  - Strictly enforce safety: zero execution of target code, path validation, and audit logging

Note on Samsung PRISM Dependency:
  If the specific external REA binary/service credentials have not been provided
  in the worklet environment, this adapter reports PENDING_EXTERNAL_DEPENDENCY
  and delegates analysis requests to the supplementary PE/Capstone engine.
"""

import json
import logging
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from agent.policy import authorize_binary_path, write_audit_event

logger = logging.getLogger(__name__)


class REAAdapter:
    """
    Adapter for the Samsung PRISM Reverse-Engineering Analysis (REA) component.
    """

    def __init__(self, endpoint_or_binary: Optional[str] = None) -> None:
        self.rea_target = endpoint_or_binary or os.getenv("REA_ENDPOINT_OR_BINARY", "").strip()

    def is_rea_available(self) -> tuple[bool, str]:
        """
        Check if the official REA service or binary is configured and accessible.
        """
        if not self.rea_target:
            return False, (
                "REA component not configured (REA_ENDPOINT_OR_BINARY environment variable not set). "
                "Samsung PRISM worklet supervisor must supply REA access specifications. "
                "Supplementary static analysis (pefile/Capstone) remains active as fallback."
            )

        if self.rea_target.startswith("http://") or self.rea_target.startswith("https://"):
            try:
                req = urllib.request.Request(f"{self.rea_target.rstrip('/')}/health", method="GET")
                with urllib.request.urlopen(req, timeout=3) as resp:
                    if resp.status == 200:
                        return True, f"REA daemon operational at {self.rea_target}"
            except Exception as e:
                return False, f"Configured REA daemon endpoint '{self.rea_target}' is unreachable: {e}"

        target_path = Path(self.rea_target)
        if target_path.exists():
            if os.access(target_path, os.X_OK) and target_path.is_file():
                return True, f"REA local executable component verified at {self.rea_target}"
            return False, f"REA target '{self.rea_target}' exists but is not an executable file."

        return False, f"Configured REA target '{self.rea_target}' does not exist."

    def analyze(self, binary_path: str, operation: str = "metadata") -> dict[str, Any]:
        """
        Execute analysis on target binary through REA (or record pending status).
        Never reports REA_OPERATIONAL unless the actual REA tool executes and returns valid analysis results.
        """
        # Safety gate 1: Path authorization
        authorized, reason = authorize_binary_path(binary_path)
        if not authorized:
            write_audit_event(
                operation=f"rea_{operation}",
                target_path=binary_path,
                authorized=False,
                result_status="DENIED",
                extra=reason,
            )
            return {
                "success": False,
                "status": "DENIED",
                "error": "Access Denied by Policy",
                "details": reason,
                "target": binary_path,
            }

        # Safety gate 2: File existence
        target_file = Path(binary_path).resolve()
        if not target_file.is_file():
            write_audit_event(
                operation=f"rea_{operation}",
                target_path=str(target_file),
                authorized=True,
                result_status="FILE_NOT_FOUND",
                extra="Target binary file does not exist",
            )
            return {
                "success": False,
                "status": "FILE_NOT_FOUND",
                "error": f"Binary file not found: {binary_path}",
                "target": str(target_file),
            }

        # Check REA availability
        available, msg = self.is_rea_available()
        if not available:
            write_audit_event(
                operation=f"rea_{operation}",
                target_path=str(target_file),
                authorized=True,
                result_status="PENDING_EXTERNAL_DEPENDENCY",
                extra=msg,
            )
            return {
                "success": False,
                "status": "PENDING_EXTERNAL_DEPENDENCY",
                "message": msg,
                "fallback_recommended": True,
                "target": str(target_file),
            }

        # Actual execution via HTTP daemon or external binary
        if self.rea_target.startswith("http://") or self.rea_target.startswith("https://"):
            try:
                url = f"{self.rea_target.rstrip('/')}/analyze"
                payload = json.dumps({"target": str(target_file), "operation": operation}).encode("utf-8")
                req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=20) as resp:
                    resp_data = json.loads(resp.read().decode("utf-8"))
                    write_audit_event(
                        operation=f"rea_{operation}",
                        target_path=str(target_file),
                        authorized=True,
                        result_status="REA_OPERATIONAL",
                        extra=f"REA HTTP daemon returned status: {resp.status}",
                    )
                    return {
                        "success": True,
                        "status": "REA_OPERATIONAL",
                        "operation": operation,
                        "target": str(target_file),
                        "results": resp_data,
                        "active_engine": "REA",
                    }
            except Exception as e:
                write_audit_event(
                    operation=f"rea_{operation}",
                    target_path=str(target_file),
                    authorized=True,
                    result_status="FAILED",
                    extra=f"REA daemon call failed: {e}",
                )
                return {
                    "success": False,
                    "status": "FAILED",
                    "error": str(e),
                    "fallback_recommended": True,
                }

        # External binary execution
        target_path = Path(self.rea_target)
        try:
            cmd = [str(target_path), "--operation", operation, "--file", str(target_file), "--format", "json"]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
            if proc.returncode == 0:
                try:
                    parsed = json.loads(proc.stdout)
                    write_audit_event(
                        operation=f"rea_{operation}",
                        target_path=str(target_file),
                        authorized=True,
                        result_status="REA_OPERATIONAL",
                        extra=f"Executed REA binary: {self.rea_target}",
                    )
                    return {
                        "success": True,
                        "status": "REA_OPERATIONAL",
                        "operation": operation,
                        "target": str(target_file),
                        "results": parsed,
                        "active_engine": "REA",
                    }
                except json.JSONDecodeError as jde:
                    write_audit_event(
                        operation=f"rea_{operation}",
                        target_path=str(target_file),
                        authorized=True,
                        result_status="FAILED",
                        extra=f"REA produced invalid JSON: {jde}",
                    )
                    return {
                        "success": False,
                        "status": "FAILED",
                        "error": f"REA output parsing failed: {jde}",
                        "raw_output": proc.stdout[:500],
                        "fallback_recommended": True,
                    }
            else:
                write_audit_event(
                    operation=f"rea_{operation}",
                    target_path=str(target_file),
                    authorized=True,
                    result_status="FAILED",
                    extra=f"REA exit code {proc.returncode}: {proc.stderr[:100]}",
                )
                return {
                    "success": False,
                    "status": "FAILED",
                    "error": proc.stderr or f"REA exited with code {proc.returncode}",
                    "fallback_recommended": True,
                }
        except Exception as exc:
            write_audit_event(
                operation=f"rea_{operation}",
                target_path=str(target_file),
                authorized=True,
                result_status="FAILED",
                extra=f"Subprocess invocation exception: {exc}",
            )
            return {
                "success": False,
                "status": "FAILED",
                "error": str(exc),
                "fallback_recommended": True,
            }
