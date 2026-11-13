"""
Dynamic Tool Router for the Samsung PRISM Unified Engineering Agent.

Provides:
  - Category-relevant tool filtering (4-8 tools per category instead of all tools)
  - REA tool filtering: exposes a compact subset (binary_overview, open_binary,
    query_rea_status) + pefile/Capstone tools
  - Compact tool schemas and category few-shot examples for small models (Qwen 1.5B, Phi-3.5)
  - Runtime filtering helper to restrict available MCP tools to category allowlists
"""

from typing import Any, Optional


ROUTER_TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    # ------------------------------------------------------------------
    # Code Analysis Tools (4 tools)
    # ------------------------------------------------------------------
    "find_functions": {
        "name": "find_functions",
        "spec": "find_functions(): Find function definitions in codebase. Arguments: {}",
        "example": '{"tool": "find_functions", "arguments": {}}',
        "category": "code_analysis",
    },
    "find_callers": {
        "name": "find_callers",
        "spec": 'find_callers(target: str): Find callers that invoke target function. Arguments: {"target": "<func_name>"}',
        "example": 'Who calls process_query? -> {"tool": "find_callers", "arguments": {"target": "process_query"}}',
        "category": "code_analysis",
    },
    "find_callees": {
        "name": "find_callees",
        "spec": 'find_callees(target: str): Find calls made by function. Arguments: {"target": "<func_name>"}',
        "example": 'Calls in dispatch? -> {"tool": "find_callees", "arguments": {"target": "dispatch"}}',
        "category": "code_analysis",
    },
    "get_file_outline": {
        "name": "get_file_outline",
        "spec": 'get_file_outline(file_path: str): Symbols in a file. Arguments: {"file_path": "<path>"}',
        "example": 'Outline in agent.py -> {"tool": "get_file_outline", "arguments": {"file_path": "agent.py"}}',
        "category": "code_analysis",
    },

    # ------------------------------------------------------------------
    # Binary Analysis Tools (7 tools)
    # ------------------------------------------------------------------
    "analyze_binary": {
        "name": "analyze_binary",
        "spec": 'analyze_binary(file_path: str): Inspect PE headers and architecture. Arguments: {"file_path": "<path>"}',
        "example": 'Inspect sample.exe -> {"tool": "analyze_binary", "arguments": {"file_path": "sample.exe"}}',
        "category": "binary_analysis",
    },
    "disassemble_binary": {
        "name": "disassemble_binary",
        "spec": 'disassemble_binary(file_path: str): Disassemble machine instructions. Arguments: {"file_path": "<path>"}',
        "example": 'Disassemble sample.exe -> {"tool": "disassemble_binary", "arguments": {"file_path": "sample.exe"}}',
        "category": "binary_analysis",
    },
    "find_binary_imports": {
        "name": "find_binary_imports",
        "spec": 'find_binary_imports(file_path: str): List imported DLLs and symbols. Arguments: {"file_path": "<path>"}',
        "example": 'Imports of sample.exe -> {"tool": "find_binary_imports", "arguments": {"file_path": "sample.exe"}}',
        "category": "binary_analysis",
    },
    "binary_overview": {
        "name": "binary_overview",
        "spec": 'binary_overview(file_path: str): REA structural overview of binary. Arguments: {"file_path": "<path>"}',
        "example": 'Overview of sample.exe -> {"tool": "binary_overview", "arguments": {"file_path": "sample.exe"}}',
        "category": "binary_analysis",
    },
    "batch_decompile": {
        "name": "batch_decompile",
        "spec": 'batch_decompile(file_path: str): REA batch decompile functions. Arguments: {"file_path": "<path>"}',
        "example": 'Batch decompile sample.exe -> {"tool": "batch_decompile", "arguments": {"file_path": "sample.exe"}}',
        "category": "binary_analysis",
    },
    "open_binary": {
        "name": "open_binary",
        "spec": 'open_binary(path: str): Open local binary in REA for reverse engineering. Arguments: {"path": "<file_path>"}',
        "example": 'Open binary sample.exe in REA -> {"tool": "open_binary", "arguments": {"path": "sample.exe"}}',
        "category": "binary_analysis",
    },
    "query_rea_status": {
        "name": "query_rea_status",
        "spec": 'query_rea_status(file_path: str): Query REA engine status and availability. Arguments: {"file_path": "<file_path>"}',
        "example": 'Query REA status for sample.exe -> {"tool": "query_rea_status", "arguments": {"file_path": "sample.exe"}}',
        "category": "binary_analysis",
    },

    # ------------------------------------------------------------------
    # Memory Tools (2 tools)
    # ------------------------------------------------------------------
    "save_finding": {
        "name": "save_finding",
        "spec": 'save_finding(content: str): Persist an engineering finding to memory. Arguments: {"content": "<text>"}',
        "example": 'Remember finding: WAL enabled -> {"tool": "save_finding", "arguments": {"content": "WAL enabled"}}',
        "category": "memory",
    },
    "search_memory": {
        "name": "search_memory",
        "spec": 'search_memory(query: str): Search past engineering findings. Arguments: {"query": "<search_term>"}',
        "example": 'Search memory for WAL -> {"tool": "search_memory", "arguments": {"query": "WAL"}}',
        "category": "memory",
    },

    # ------------------------------------------------------------------
    # Clarification & Fallback
    # ------------------------------------------------------------------
    "request_clarification": {
        "name": "request_clarification",
        "spec": 'request_clarification(missing_parameter: str): Use when essential parameter is missing. Arguments: {"missing_parameter": "<name>"}',
        "example": 'Disassemble this -> {"tool": "request_clarification", "arguments": {"missing_parameter": "file_path"}}',
        "category": "clarification",
    },
    "none": {
        "name": "none",
        "spec": 'none(): Use when no tool matches request. Arguments: {}',
        "example": 'Compile C code -> {"tool": "none", "arguments": {}}',
        "category": "unsupported",
    },
}


def get_tools_for_category(
    category: Optional[str] = None,
    include_fallback: bool = True,
) -> list[dict[str, Any]]:
    """
    Return category-specific tools (4-8 tools).
    Always includes clarification and none fallback if requested.
    """
    cat = (category or "").lower()
    selected: list[dict[str, Any]] = []

    for name, info in ROUTER_TOOL_SCHEMAS.items():
        tool_cat = info.get("category", "")
        if cat in ("code", "code_analysis"):
            if tool_cat == "code_analysis":
                selected.append(info)
        elif cat in ("binary", "binary_analysis"):
            if tool_cat == "binary_analysis":
                selected.append(info)
        elif cat in ("memory", "persistent_memory"):
            if tool_cat == "memory":
                selected.append(info)
        elif cat in ("clarification", "unsupported"):
            if tool_cat in ("clarification", "unsupported"):
                selected.append(info)
        else:
            # Default cross-domain subset
            if name in (
                "find_functions",
                "find_callers",
                "get_file_outline",
                "analyze_binary",
                "disassemble_binary",
                "save_finding",
                "search_memory",
            ):
                selected.append(info)

    if include_fallback:
        if ROUTER_TOOL_SCHEMAS["request_clarification"] not in selected:
            selected.append(ROUTER_TOOL_SCHEMAS["request_clarification"])
        if ROUTER_TOOL_SCHEMAS["none"] not in selected:
            selected.append(ROUTER_TOOL_SCHEMAS["none"])

    return selected


def build_tool_selection_prompt(
    category: Optional[str] = None,
) -> str:
    """
    Build a dynamic tool selection prompt with exact argument specifications and
    compact few-shot examples for the category.
    """
    tools = get_tools_for_category(category)
    tool_names = [t["name"] for t in tools]

    lines = [
        "Select ONLY from allowed tools:",
        ", ".join(tool_names),
        "\nTool Specifications & Examples:",
    ]
    for t in tools:
        lines.append(f"- {t['spec']}")
        if "example" in t and t["example"]:
            lines.append(f"  Ex: {t['example']}")

    lines.append(
        '\nRespond ONLY with a single JSON object: {"tool": "<name>", "arguments": {<args>}}'
    )
    return "\n".join(lines)


def filter_available_tools_for_category(
    category: str,
    available_tools: dict[str, Any],
) -> dict[str, Any]:
    """
    Runtime filter: restricts an MCP server's exposed tools (which may contain 17-229 tools)
    to the active category subset to keep the prompt budget low.
    """
    allowed_names = set(t["name"] for t in get_tools_for_category(category))

    # Code Graph MCP tools used by the code-analysis orchestrator.
    # Keep these separate from the compact AST planner tool list.
    if category == "code_analysis":
        allowed_names.update({
            "search_graph",
            "trace_path",
            "get_architecture",
            "get_file_outline",
            "get_code_snippet",
        })

    # Also allow standard prefix matches (e.g. ast_, code_).
        # Allow exact names and server-prefixed versions of allowed tools.
        # Allow exact names and server-prefixed versions of allowed tools.
        # Allow exact names and server-prefixed versions of allowed tools.
        # Allow exact names and server-prefixed versions of allowed tools.
    filtered = {}

    for tool_name, schema in available_tools.items():
        if tool_name in allowed_names:
            filtered[tool_name] = schema
            continue

        if any(
            tool_name.endswith("_" + name)
            for name in allowed_names
        ):
            filtered[tool_name] = schema

    # Fail closed: never expose every server tool when no category match exists.
    return filtered
