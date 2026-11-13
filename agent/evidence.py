
"""
Evidence aggregation module for the Samsung PRISM Unified Engineering Agent.

Normalises raw tool results into structured evidence items and produces
evidence-grounded prompts for the local LLM.

The LLM must not invent file paths, function names, line numbers,
addresses, or graph relationships.
"""

import sys
import json
import re

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ---------------------------------------------------------------------------
# Evidence classification
# ---------------------------------------------------------------------------

class EvidenceKind(str, Enum):
    VERIFIED = "VERIFIED"
    HYPOTHESIS = "HYPOTHESIS"
    LIMITATION = "LIMITATION"
    SOURCE_REF = "SOURCE_REF"


@dataclass
class EvidenceItem:
    """A single piece of evidence from one tool or memory source."""

    kind: EvidenceKind
    source: str
    summary: str
    detail: str = ""
    raw_output: str = ""
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    function_name: Optional[str] = None
    binary_address: Optional[str] = None
    tool_name: Optional[str] = None
    server_name: Optional[str] = None


@dataclass
class EvidenceBundle:
    """Aggregated evidence from one or more tool calls for a query."""

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
        return [
            i for i in self.items
            if i.kind == EvidenceKind.VERIFIED
        ]

    @property
    def hypothesis_items(self) -> list[EvidenceItem]:
        return [
            i for i in self.items
            if i.kind == EvidenceKind.HYPOTHESIS
        ]

    def to_llm_context(self) -> str:
        """Format evidence into a structured context block."""

        lines: list[str] = []
        lines.append("=== EVIDENCE FROM ANALYSIS TOOLS ===\n")

        if not self.items and not self.limitations:
            lines.append(
                "No tool results available. Do not invent information.\n"
            )
        else:
            for i, item in enumerate(self.items, start=1):

                if item.kind == EvidenceKind.HYPOTHESIS:
                    lines.append(
                        f"[{item.kind.value} #{i} - "
                        "UNVERIFIED HYPOTHESIS, NOT AN ESTABLISHED FACT]"
                    )
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
                    lines.append(f"Detail :\n{item.detail[:2000]}")

                lines.append("")

        if self.limitations:
            lines.append("=== KNOWN LIMITATIONS ===")
            for limitation in self.limitations:
                lines.append(f"  - {limitation}")
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

    Supports:
    - Regular code-analysis results
    - Code Graph search_graph responses
    - Code Graph trace_path caller/callee responses

    Preserves the original raw tool response.
    """

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

        if not isinstance(data, dict):
            return item

        # ---------------------------------------------------------------
        # Standard code-analysis metadata
        # ---------------------------------------------------------------

        if (
            "items" in data
            and isinstance(data["items"], list)
            and data["items"]
        ):
            first = data["items"][0]

            if isinstance(first, dict):
                item.file_path = (
                    first.get("file")
                    or first.get("call_site_file")
                )

                item.line_number = (
                    first.get("line")
                    or first.get("call_site_line")
                )

                item.function_name = (
                    first.get("name")
                    or first.get("caller")
                )

        elif "target_file" in data:
            item.file_path = str(data.get("target_file"))

        elif "file" in data:
            item.file_path = str(data.get("file"))

        # ---------------------------------------------------------------
        # Code Graph trace_path response
        # ---------------------------------------------------------------

        trace_key = None

        if isinstance(data.get("callers"), dict):
            trace_key = "callers"

        elif isinstance(data.get("callees"), dict):
            trace_key = "callees"

        if trace_key:

            trace_data = data[trace_key]
            groups = trace_data.get("groups", [])

            # Keep unique (hop, qualified_name) pairs.
            entries: list[tuple[str, str]] = []
            seen_entries: set[tuple[str, str]] = set()

            for group in groups:

                if not isinstance(group, dict):
                    continue

                qn_prefix = str(
                    group.get("qn_prefix", "")
                ).strip(".")

                for row in group.get("rows", []):

                    if (
                        not isinstance(row, (list, tuple))
                        or not row
                    ):
                        continue

                    name = str(row[0])

                    qualified_name = (
                        f"{qn_prefix}.{name}"
                        if qn_prefix
                        else name
                    )

                    hop = (
                        str(row[1])
                        if len(row) > 1
                        else "unknown"
                    )

                    entry = (hop, qualified_name)

                    if entry not in seen_entries:
                        entries.append(entry)
                        seen_entries.add(entry)

            # Preserve the graph's reported total.
            total = data.get(
                f"{trace_key}_total",
                len(entries),
            )

            relation = data.get(
                f"{trace_key}_total_relation",
                "eq",
            )

            item.function_name = (
                str(data.get("function") or "") or None
            )

            # Separate direct and indirect relationships.
            # Separate direct, indirect, and unknown-hop relationships.
            direct = list(dict.fromkeys(
                name
                for hop, name in entries
                if hop == "1"
            ))

            indirect = list(dict.fromkeys(
                name
                for hop, name in entries
                if hop.isdigit() and int(hop) >= 2
            ))

            unknown_hop = list(dict.fromkeys(
                name
                for hop, name in entries
                if not hop.isdigit() or int(hop) < 1
            ))

            lines = [
                (
                    "Code Graph trace result for: "
                    f"{item.function_name or 'unknown function'}"
                ),
                f"Relationship: {trace_key}",
                f"Reported total: {total} ({relation})",
                "",
                "Direct relationships (hop 1):",
            ]

            if direct:
                lines.extend(
                    f"- {name}" for name in direct
                )
            else:
                lines.append("- None reported")

            lines.append("")
            lines.append(
                "Indirect relationships (hop 2 or greater):"
            )

            if indirect:
                lines.extend(
                    f"- {name}" for name in indirect
                )
            else:
                lines.append("- None reported")
            if unknown_hop:
                lines.append("")
                lines.append("Relationships with unknown hop depth:")
                lines.extend(
                    f"- {name}" for name in unknown_hop
                )
            if not entries:
                lines.append("")

            if isinstance(total, int) and total == 0 and relation == "eq":
                lines.append(
                    f"No {trace_key} were returned. "
                    "The graph reported an exact zero result."
                )
            elif isinstance(total, int) and total > 0:
                item.kind = EvidenceKind.LIMITATION
                item.summary = (
                    f"Code Graph reported {total} {trace_key}, "
                    "but returned no relationship entries."
                )
                lines.append(
                    "Incomplete graph response: the reported total "
                    "is positive, but no relationship entries were returned."
                )
            else:
                item.kind = EvidenceKind.LIMITATION
                item.summary = (
                    f"Code Graph returned no usable {trace_key} evidence."
                )
                lines.append(
                    "The graph returned no usable relationship entries."
                )

            item.summary = (
                f"Code Graph reported {total} {trace_key} "
                f"for {item.function_name or 'the requested function'}."
            )

            item.detail = "\n".join(lines)

        # ---------------------------------------------------------------
        # Code Graph search_graph response
        # ---------------------------------------------------------------

        elif isinstance(data.get("groups"), list):

            symbols = []

            for group in data["groups"]:

                if not isinstance(group, dict):
                    continue

                qn_prefix = str(
                    group.get("qn_prefix", "")
                ).strip(".")

                file_path = group.get("file")

                for row in group.get("rows", []):

                    if (
                        not isinstance(row, (list, tuple))
                        or not row
                    ):
                        continue

                    name = str(row[0])

                    qualified_name = (
                        f"{qn_prefix}.{name}"
                        if qn_prefix
                        else name
                    )

                    symbols.append(qualified_name)

                    if not item.function_name:
                        item.function_name = name

                    if file_path and not item.file_path:
                        item.file_path = file_path

                    if len(row) > 2 and not item.line_number:
                        line_range = str(row[2])

                        try:
                            item.line_number = int(
                                line_range.split("-", 1)[0]
                            )
                        except (ValueError, TypeError):
                            pass

            if symbols:
                item.summary = (
                    f"Code Graph found {len(symbols)} matching "
                    "symbol result(s)."
                )

                item.detail = (
                    "Matching qualified symbols:\n"
                    + "\n".join(
                        f"- {symbol}" for symbol in symbols
                    )
                )

    except (json.JSONDecodeError, TypeError, ValueError):
        # If text is not JSON, check for structured table/BM25 output.
        match = re.search(
            r"\b([\w./\-]+\.py)\s+(\d+)",
            text,
        )

        if match:
            item.file_path = match.group(1)

            try:
                item.line_number = int(match.group(2))
            except ValueError:
                pass

    return item


# ---------------------------------------------------------------------------
# Binary analysis result normalisation
# ---------------------------------------------------------------------------

def normalise_binary_result(
    tool_name: str,
    server_name: str,
    text: str,
    is_error: bool,
) -> EvidenceItem:
    """
    Convert a raw binary-analysis result into an EvidenceItem.

    Extracts entry points, sections, architecture, and file paths.
    """

    if is_error or not text.strip():
        return EvidenceItem(
            kind=EvidenceKind.LIMITATION,
            source=f"{server_name}.{tool_name}",
            summary=(
                f"Binary tool '{tool_name}' returned no results or an error."
            ),
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
                item.binary_address = str(
                    data["entry_point_rva"]
                )

            elif data.get("entry_point"):
                item.binary_address = str(
                    data["entry_point"]
                )

            elif data.get("disassembly_base"):
                item.binary_address = str(
                    data["disassembly_base"]
                )

            exported = data.get("exported_functions")

            if isinstance(exported, list) and exported:
                if isinstance(exported[0], dict):
                    item.function_name = exported[0].get("name")

    except (json.JSONDecodeError, TypeError, ValueError):
        pass

    return item


# ---------------------------------------------------------------------------
# Persistent engineering memory result normalisation
# ---------------------------------------------------------------------------

def normalise_memory_result(
    items: list[Any],
    keyword: str = "",
) -> list[EvidenceItem]:
    """
    Convert memory rows into EvidenceItems.

    Supports sqlite3.Row, dictionaries, and tuples.
    Excludes proposed and rejected findings.
    """

    evidence: list[EvidenceItem] = []

    for raw_row in items:

        if hasattr(raw_row, "keys"):

            row = dict(raw_row)

            mem_id = row.get("id", "?")
            title = row.get("title", "(no title)")
            content = row.get("content", "")
            created = row.get("created_at", "")
            category = row.get("category", "")
            status = row.get(
                "verification_status",
                "VERIFIED",
            )

        elif isinstance(raw_row, (list, tuple)):

            mem_id = (
                raw_row[0] if len(raw_row) > 0 else "?"
            )

            title = (
                raw_row[1] if len(raw_row) > 1 else "(no title)"
            )

            content = (
                raw_row[2] if len(raw_row) > 2 else ""
            )

            created = (
                raw_row[3] if len(raw_row) > 3 else ""
            )

            category = (
                raw_row[4] if len(raw_row) > 4 else ""
            )

            status = (
                raw_row[5] if len(raw_row) > 5 else "VERIFIED"
            )

        else:
            continue

        status = str(status).upper()

        if status in ("PROPOSED", "REJECTED"):
            continue

        if status in ("VERIFIED", "CONFIRMED"):
            kind = EvidenceKind.VERIFIED

        elif status == "HYPOTHESIS":
            kind = EvidenceKind.HYPOTHESIS

        else:
            kind = EvidenceKind.LIMITATION

        evidence.append(
            EvidenceItem(
                kind=kind,
                source=f"engineering_memory[id={mem_id}]",
                summary=f"[{status}] {title}",
                detail=(
                    f"Memory record ID: {mem_id}\n"
                    f"{content}\n"
                    f"(Saved: {created}, Category: {category})"
                ),
                tool_name="memory",
                server_name="memory",
            )
        )

    return evidence


# ---------------------------------------------------------------------------
# Grounded LLM prompt generation
# ---------------------------------------------------------------------------

def build_llm_prompt(
    bundle: EvidenceBundle,
    system_prompt: str = "",
) -> tuple[str, str]:
    """
    Build a system prompt and user message from verified evidence.

    The LLM is instructed to explain the evidence without inventing facts.
    """

    system = system_prompt or (
        "You are a Unified Engineering Agent for the Samsung PRISM project. "
        "You have access to real tool results shown below. "
        "Base your answer ONLY on the provided evidence. "
        "If a fact is not in the evidence, say so explicitly. "
        "Do not invent file paths, function names, line numbers, "
        "addresses, or relationships. "
        "For caller/callee questions, distinguish direct relationships "
        "(hop 1) from indirect relationships (hop 2 or greater). "
        "Do not repeat duplicate function names. "
        "Do not confuse separate functions merely because they share "
        "the same short name. "
        "For persistent-memory questions, copy memory record IDs and "
        "stored numeric or hexadecimal values exactly from the evidence. "
        "Never invent or substitute a memory record ID. "
        "If a requested field is absent, say it is not present. "
        "Label answer sections as FINDINGS, LIMITATIONS, and SOURCES."
    )

    user_message = (
        f"User query: {bundle.query}\n\n"
        f"{bundle.to_llm_context()}\n\n"
        "Based on the evidence above, answer the query. "
        "Be specific about what the tools found and what they did not cover. "
        "For caller questions, prioritize direct callers and identify "
        "the exact qualified target function."
    )

    return system, user_message
