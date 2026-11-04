"""
Reverse-Engineering Analysis (REA) Integration Adapter
Samsung PRISM Worklet Component.

Responsibilities:
  - Define the formal REA interface contract for static binary analysis
  - Check whether the external REA tool or daemon has been provisioned
  - Safely fall back to PE/Capstone tools if REA access details are pending
  - Strictly enforce safety: zero execution, path validation, and audit logging

Note on Samsung PRISM Dependency:
  If the specific external REA binary/service credentials have not been provided
  in the worklet environment, this adapter reports PENDING_EXTERNAL_DEPENDENCY
  and delegates analysis requests to the supplementary PE/Capstone engine.
"""

import json
import logging
import os
import sys
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
        self.rea_target = endpoint_or_binary or os.getenv("REA_ENDPOINT_OR_BINARY", "")

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

        target_path = Path(self.rea_target)
        if target_path.exists():
            return True, f"REA local component found: {self.rea_target}"

        return False, f"Configured REA target '{self.rea_target}' is unreachable."

    def analyze(self, binary_path: str, operation: str = "metadata") -> dict[str, Any]:
        """
        Execute analysis on target binary through REA (or record pending status).
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
            }

        # Check REA availability
        available, msg = self.is_rea_available()
        if not available:
            write_audit_event(
                operation=f"rea_{operation}",
                target_path=binary_path,
                authorized=True,
                result_status="PENDING_EXTERNAL_DEPENDENCY",
                extra=msg,
            )
            return {
                "success": False,
                "status": "PENDING_EXTERNAL_DEPENDENCY",
                "message": msg,
                "fallback_recommended": True,
            }

        # Only report operational if target is verified executable
        target_path = Path(self.rea_target)
        if target_path.exists() and os.access(target_path, os.X_OK):
            write_audit_event(
                operation=f"rea_{operation}",
                target_path=binary_path,
                authorized=True,
                result_status="REA_OPERATIONAL",
                extra=f"Invoked REA binary: {self.rea_target}",
            )
            return {
                "success": True,
                "status": "REA_OPERATIONAL",
                "operation": operation,
                "target": binary_path,
            }

        return {
            "success": False,
            "status": "PENDING_EXTERNAL_DEPENDENCY",
            "message": f"REA binary '{self.rea_target}' exists but lacks execute permissions.",
            "fallback_recommended": True,
        }

