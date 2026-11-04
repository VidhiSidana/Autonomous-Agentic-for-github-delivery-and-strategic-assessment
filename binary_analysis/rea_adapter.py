"""
Reverse-Engineering Analysis (REA) Integration Adapter
Samsung PRISM Worklet Component.

Responsibilities:
  - Define the formal REA interface contract for static binary analysis.
  - Check whether the official REA tool/driver has been provisioned by Samsung PRISM.
  - Safely fall back to PE/Capstone tools if REA access details are pending.
  - Enforce zero execution of target code, path validation, and comprehensive audit logging.

Note on Samsung PRISM Dependency:
  Official Samsung REA interface specifications (HTTP/CLI/gRPC/MCP) and binaries have
  not yet been supplied by the worklet supervisor. This adapter avoids guessing arbitrary
  endpoints or CLI flags and explicitly reports PENDING_EXTERNAL_DEPENDENCY.
"""

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Callable, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from agent.policy import authorize_binary_path, write_audit_event

logger = logging.getLogger(__name__)


class REAAdapter:
    """
    Adapter for the Samsung PRISM Reverse-Engineering Analysis (REA) component.
    """

    def __init__(
        self,
        custom_runner: Optional[Callable[[str, str], dict[str, Any]]] = None,
    ) -> None:
        self.custom_runner = custom_runner

    def is_rea_available(self) -> tuple[bool, str]:
        """
        Check if the official REA service or runner is verified and accessible.
        Never assumes unverified HTTP endpoints or CLI flags without official specifications.
        """
        if self.custom_runner is not None and callable(self.custom_runner):
            return True, "Verified REA execution runner configured and accessible."

        return False, (
            "Official Samsung PRISM Reverse-Engineering Analysis (REA) interface specifications "
            "and binaries have not yet been provisioned by the project supervisor. "
            "Supplementary static analysis (pefile/Capstone) remains active as fallback."
        )

    def analyze(self, binary_path: str, operation: str = "metadata") -> dict[str, Any]:
        """
        Execute analysis on target binary through REA (or record pending status).
        Never reports REA_OPERATIONAL without a verified successful real analysis response.
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
        if not available or self.custom_runner is None:
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

        # Genuine execution through verified runner
        try:
            result = self.custom_runner(str(target_file), operation)
            if isinstance(result, dict) and result.get("success", False):
                write_audit_event(
                    operation=f"rea_{operation}",
                    target_path=str(target_file),
                    authorized=True,
                    result_status="REA_OPERATIONAL",
                    extra="Executed official REA runner with verified results",
                )
                return {
                    "success": True,
                    "status": "REA_OPERATIONAL",
                    "operation": operation,
                    "target": str(target_file),
                    "results": result.get("data", result),
                    "active_engine": "REA",
                }
            else:
                err_msg = str(result.get("error", "REA runner returned unsuccessful status") if isinstance(result, dict) else "Invalid runner output")
                write_audit_event(
                    operation=f"rea_{operation}",
                    target_path=str(target_file),
                    authorized=True,
                    result_status="FAILED",
                    extra=err_msg,
                )
                return {
                    "success": False,
                    "status": "FAILED",
                    "error": err_msg,
                    "fallback_recommended": True,
                }
        except Exception as exc:
            write_audit_event(
                operation=f"rea_{operation}",
                target_path=str(target_file),
                authorized=True,
                result_status="FAILED",
                extra=f"REA invocation exception: {exc}",
            )
            return {
                "success": False,
                "status": "FAILED",
                "error": str(exc),
                "fallback_recommended": True,
            }
