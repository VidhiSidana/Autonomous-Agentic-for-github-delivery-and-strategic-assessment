"""
Evidence aggregation module for the Samsung PRISM Unified Engineering Agent.

This module normalises raw tool results into structured evidence items and
produces evidence-grounded prompts for the local LLM.

The LLM is NEVER asked to invent file paths, function names, line numbers,
addresses, or graph relationships. It only explains or summarises evidence
that the tools have actually returned.
"""

import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ---------------------------------------------------------------------------
# Evidence classification
# ---------------------------------------------------------------------------

class EvidenceKind(str, Enum):
    VERIFIED    = "VERIFIED"      # confirmed by a tool or verified memory
    HYPOTHESIS  = "HYPOTHESIS"    # inferred or unverified
    LIMITATION  = "LIMITATION"    # known gap in coverage
    SOURCE_REF  = "SOURCE_REF"    # citation (file, line, function, address)


@dataclass
class EvidenceItem:
    """A single piece of evidence from one tool or memory source."""
    kind: EvidenceKind
    source: str                   # e.g. "code_fallback.find_callers"
    summary: str                  # human-readable summary
    detail: str = ""              # processed tool output or extended detail
    raw_output: str = ""          # exact raw tool response for traceability
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    function_name: Optional[str] = None
    binary_address: Optional[str] = None
    tool_name: Optional[str] = None
    server_name: Optional[str] = None


@dataclass
class EvidenceBundle:
    """
    Aggregated evidence from one or more tool calls for a single query.
    """
    query: str
    items: list[EvidenceItem] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)

    def add(self, item: EvidenceItem) -> None:
        self.items.append(item)

    def add_limitation(self, text: str) -> None:
        self.limitations.append(text)

    @property
    def has_verified(self) -> bool:
        return any(i.kind == EvidenceKind.VERIFIED for i in self.items)

    @property
    def verified_items(self) -> list[EvidenceItem]:
        return [i for i in self.items if i.kind == EvidenceKind.VERIFIED]

    @property
    def hypothesis_items(self) -> list[EvidenceItem]:
        return [i for i in self.items if i.kind == EvidenceKind.HYPOTHESIS]

    def to_llm_context(self) -> str:
        """
        Format the evidence bundle as a structured context block for the LLM.
        The LLM receives this as part of its system/user prompt.
        """
        lines: list[str] = []
        lines.append("=== EVIDENCE FROM ANALYSIS TOOLS ===\n")

        if not self.items and not self.limitations:
            lines.append("No tool results available. Do not invent information.\n")
        else:
            for i, item in enumerate(self.items, start=1):
                if item.kind == EvidenceKind.HYPOTHESIS:
                    lines.append(f"[{item.kind.value} #{i} - UNVERIFIED HYPOTHESIS, NOT AN ESTABLISHED FACT]")
                else:
                    lines.append(f"[{item.kind.value} #{i}]")
                lines.append(f"Source : {item.source}")
                if item.file_path:
                    loc = item.file_path
                    if item.line_number:
                        loc += f":{item.line_number}"
                    lines.append(f"Location: {loc}")
                if item.function_name:
                    lines.append(f"Symbol : {item.function_name}")
                if item.binary_address:
                    lines.append(f"Address: {item.binary_address}")
                lines.append(f"Summary: {item.summary}")
                if item.detail:
                    lines.append(f"Detail :\n{item.detail[:2000]}")  # cap size
                lines.append("")

        if self.limitations:
            lines.append("=== KNOWN LIMITATIONS ===")
            for lim in self.limitations:
                lines.append(f"  - {lim}")
            lines.append("")

        lines.append("=== END OF EVIDENCE ===")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool result normalisation helpers
# ---------------------------------------------------------------------------

def normalise_code_result(
    tool_name: str,
    server_name: str,
    text: str,
    is_error: bool,
) -> EvidenceItem:
    """
    Convert a raw code-analysis tool result into an EvidenceItem.
    Extracts verified file paths, line numbers, and symbol names safely.
    Preserves exact raw tool response for traceability.
    """
    import re
    import json

    if is_error or not text.strip():
        return EvidenceItem(
            kind=EvidenceKind.LIMITATION,
            source=f"{server_name}.{tool_name}",
            summary=f"Tool '{tool_name}' returned no results or an error.",
            detail=text,
            raw_output=text,
            tool_name=tool_name,
            server_name=server_name,
        )

    item = EvidenceItem(
        kind=EvidenceKind.VERIFIED,
        source=f"{server_name}.{tool_name}",
        summary=f"Code analysis via '{tool_name}' succeeded.",
        detail=text,
        raw_output=text,
        tool_name=tool_name,
        server_name=server_name,
    )

    try:
        data = json.loads(text)
        if isinstance(data, dict):
            if "items" in data and isinstance(data["items"], list) and data["items"]:
                first = data["items"][0]
                if isinstance(first, dict):
                    item.file_path = first.get("file") or first.get("call_site_file")
                    item.line_number = first.get("line") or first.get("call_site_line")
                    item.function_name = first.get("name") or first.get("caller")
            elif "target_file" in data:
                item.file_path = str(data.get("target_file"))
            elif "file" in data:
                item.file_path = str(data.get("file"))
    except Exception:
        # If text is not JSON, check for structured table/BM25 output
        match = re.search(r"\b([\w./\-]+\.py)\s+(\d+)", text)
        if match:
            item.file_path = match.group(1)
            try:
                item.line_number = int(match.group(2))
            except ValueError:
                pass

    return item


def normalise_binary_result(
    tool_name: str,
    server_name: str,
    text: str,
    is_error: bool,
) -> EvidenceItem:
    """
    Convert a raw binary-analysis tool result into an EvidenceItem.
    Extracts entry point, sections, architecture, and file paths safely.
    Preserves raw response for traceability.
    """
    import json

    if is_error or not text.strip():
        return EvidenceItem(
            kind=EvidenceKind.LIMITATION,
            source=f"{server_name}.{tool_name}",
            summary=f"Binary tool '{tool_name}' returned no results or an error.",
            detail=text,
            raw_output=text,
            tool_name=tool_name,
            server_name=server_name,
        )

    item = EvidenceItem(
        kind=EvidenceKind.VERIFIED,
        source=f"{server_name}.{tool_name}",
        summary=f"Binary analysis via '{tool_name}' succeeded.",
        detail=text,
        raw_output=text,
        tool_name=tool_name,
        server_name=server_name,
    )

    try:
        data = json.loads(text)
        if isinstance(data, dict):
            if data.get("file_path"):
                item.file_path = str(data["file_path"])
            elif data.get("file"):
                item.file_path = str(data["file"])

            if data.get("entry_point_rva"):
                item.binary_address = str(data["entry_point_rva"])
            elif data.get("entry_point"):
                item.binary_address = str(data["entry_point"])
            elif data.get("disassembly_base"):
                item.binary_address = str(data["disassembly_base"])

            if data.get("exported_functions") and isinstance(data["exported_functions"], list):
                if len(data["exported_functions"]) > 0 and isinstance(data["exported_functions"][0], dict):
                    item.function_name = data["exported_functions"][0].get("name")
    except Exception:
        pass

    return item


def normalise_memory_result(
    items: list[Any],   # list of memory row tuples, sqlite3.Row, or dicts
    keyword: str = "",
) -> list[EvidenceItem]:
    """
    Convert memory results into EvidenceItems.
    Each memory row becomes a separate item with its verification status.
    """
    evidence: list[EvidenceItem] = []
    for raw_row in items:
        # Convert sqlite3.Row or Mapping to dict
        if hasattr(raw_row, "keys"):
            row = dict(raw_row)
            mem_id = row.get("id", "?")
            title = row.get("title", "(no title)")
            content = row.get("content", "")
            created = row.get("created_at", "")
            category = row.get("category", "")
            status = row.get("verification_status", "VERIFIED")
        elif isinstance(raw_row, (list, tuple)):
            mem_id = raw_row[0] if len(raw_row) > 0 else "?"
            title = raw_row[1] if len(raw_row) > 1 else "(no title)"
            content = raw_row[2] if len(raw_row) > 2 else ""
            created = raw_row[3] if len(raw_row) > 3 else ""
            category = raw_row[4] if len(raw_row) > 4 else ""
            status = raw_row[5] if len(raw_row) > 5 else "VERIFIED"
        else:
            continue

        # Exclude PROPOSED and REJECTED findings from being treated as established facts
        if status.upper() in ("PROPOSED", "REJECTED"):
            continue

        kind = (
            EvidenceKind.VERIFIED
            if status.upper() in ("VERIFIED", "CONFIRMED")
            else EvidenceKind.HYPOTHESIS
            if status.upper() == "HYPOTHESIS"
            else EvidenceKind.LIMITATION
        )

        evidence.append(EvidenceItem(
            kind=kind,
            source=f"engineering_memory[id={mem_id}]",
            summary=f"[{status}] {title}",
            detail=f"{content}\n(Saved: {created}, Category: {category})",
            tool_name="memory",
            server_name="memory",
        ))
    return evidence


def build_llm_prompt(
    bundle: EvidenceBundle,
    system_prompt: str = "",
) -> tuple[str, str]:
    """
    Build a (system_prompt, user_message) pair for the LLM.

    The user message includes the original query and all evidence.
    The LLM is explicitly instructed not to invent information.
    """
    system = system_prompt or (
        "You are a Unified Engineering Agent for the Samsung PRISM project. "
        "You have access to real tool results shown below. "
        "Base your answer ONLY on the provided evidence. "
        "If a fact is not in the evidence, say so explicitly. "
        "Do not invent file paths, function names, line numbers, addresses, or relationships. "
        "Label your answer sections as: FINDINGS, LIMITATIONS, and SOURCES."
    )

    user_message = (
        f"User query: {bundle.query}\n\n"
        f"{bundle.to_llm_context()}\n\n"
        "Based on the evidence above, answer the query. "
        "Be specific about what the tools found and what they did not cover."
    )

    return system, user_message

