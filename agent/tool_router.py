"""
Dynamic Tool Router for the Samsung PRISM Unified Engineering Agent.

Provides:
  - Category-relevant tool filtering (4-8 tools per category instead of all tools)
  - REA tool filtering: exposes a compact subset (binary_overview, analyze_function,
    batch_decompile, build_call_path) + pefile/Capstone tools
  - Compact tool schemas optimized for small context windows (Qwen 1.5B, Phi-3.5)
"""

from typing import Any, Optional


# Canonical compact tool schemas grouped by category
ROUTER_TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    # ------------------------------------------------------------------
    # Code Analysis Tools (4-5 tools)
    # ------------------------------------------------------------------
    "find_functions": {
        "name": "find_functions",
        "description": "Find or list function and method definitions across the codebase.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Optional function name filter."},
            },
            "required": [],
        },
        "category": "code_analysis",
    },
    "find_callers": {
        "name": "find_callers",
        "description": "Trace incoming calls to target function across the codebase.",
        "parameters": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Exact name of target function."},
            },
            "required": ["target"],
        },
        "category": "code_analysis",
    },
    "find_callees": {
        "name": "find_callees",
        "description": "Trace outgoing calls made by target function.",
        "parameters": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Exact name of target function."},
            },
            "required": ["target"],
        },
        "category": "code_analysis",
    },
    "get_file_outline": {
        "name": "get_file_outline",
        "description": "Get class, method, and function declarations in a file.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Relative file path."},
            },
            "required": ["file_path"],
        },
        "category": "code_analysis",
    },

    # ------------------------------------------------------------------
    # Binary Analysis Tools (Compact REA + pefile/Capstone subset: 7 tools)
    # ------------------------------------------------------------------
    "analyze_binary": {
        "name": "analyze_binary",
        "description": "Inspect PE binary metadata, architecture, and section headers.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Authorized binary file path."},
            },
            "required": ["file_path"],
        },
        "category": "binary_analysis",
    },
    "disassemble_binary": {
        "name": "disassemble_binary",
        "description": "Disassemble machine code instructions from binary entry point.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Authorized binary file path."},
                "offset": {"type": "integer", "description": "Optional disassembly offset."},
            },
            "required": ["file_path"],
        },
        "category": "binary_analysis",
    },
    "find_binary_imports": {
        "name": "find_binary_imports",
        "description": "Extract imported DLLs and imported API symbols from PE binary.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Authorized binary file path."},
            },
            "required": ["file_path"],
        },
        "category": "binary_analysis",
    },
    "binary_overview": {
        "name": "binary_overview",
        "description": "High-level structural summary of binary in REA reverse-engineering engine.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Authorized binary file path."},
            },
            "required": ["file_path"],
        },
        "category": "binary_analysis",
    },
    "analyze_function": {
        "name": "analyze_function",
        "description": "Analyze and decompile a specific function address or symbol in REA.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Authorized binary file path."},
                "function_name": {"type": "string", "description": "Function symbol or address."},
            },
            "required": ["file_path"],
        },
        "category": "binary_analysis",
    },
    "batch_decompile": {
        "name": "batch_decompile",
        "description": "Batch decompile multiple functions in binary via REA.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Authorized binary file path."},
            },
            "required": ["file_path"],
        },
        "category": "binary_analysis",
    },
    "build_call_path": {
        "name": "build_call_path",
        "description": "Construct call graph paths between functions in binary via REA.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Authorized binary file path."},
                "from_fn": {"type": "string", "description": "Starting function."},
                "to_fn": {"type": "string", "description": "Destination function."},
            },
            "required": ["file_path"],
        },
        "category": "binary_analysis",
    },
    "open_binary": {
        "name": "open_binary",
        "description": "Open binary in REA reverse engineering engine.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Authorized binary file path."},
            },
            "required": ["path"],
        },
        "category": "binary_analysis",
    },
    "query_rea_status": {
        "name": "query_rea_status",
        "description": "Query REA engine status and availability for a binary.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Authorized binary file path."},
            },
            "required": ["file_path"],
        },
        "category": "binary_analysis",
    },

    # ------------------------------------------------------------------
    # Memory Tools (2-3 tools)
    # ------------------------------------------------------------------
    "save_finding": {
        "name": "save_finding",
        "description": "Store verified technical finding or confirmed hypothesis into memory.",
        "parameters": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Finding description."},
                "title": {"type": "string", "description": "Optional title."},
            },
            "required": ["content"],
        },
        "category": "memory",
    },
    "search_memory": {
        "name": "search_memory",
        "description": "Search persistent engineering memory by keyword or phrase.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Keywords to search."},
            },
            "required": ["query"],
        },
        "category": "memory",
    },

    # ------------------------------------------------------------------
    # Clarification / Fallback Tools
    # ------------------------------------------------------------------
    "request_clarification": {
        "name": "request_clarification",
        "description": "Ask user for missing required parameter (e.g. file_path or target function).",
        "parameters": {
            "type": "object",
            "properties": {
                "missing_parameter": {"type": "string", "description": "Name of missing parameter."},
            },
            "required": ["missing_parameter"],
        },
        "category": "clarification",
    },
}


def get_tools_for_category(
    category: Optional[str] = None,
    include_clarification: bool = True,
) -> list[dict[str, Any]]:
    """
    Return a curated, compact list of 4-8 tools relevant to the category.
    If category is None or multi-tool, returns the compact set across domains.
    """
    cat = (category or "").lower()
    selected: list[dict[str, Any]] = []

    for tool_name, info in ROUTER_TOOL_SCHEMAS.items():
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
        else:
            # Default or multi-tool: include core subset
            if tool_name in (
                "find_functions",
                "find_callers",
                "get_file_outline",
                "analyze_binary",
                "disassemble_binary",
                "binary_overview",
                "save_finding",
                "search_memory",
            ):
                selected.append(info)

    if include_clarification and "request_clarification" in ROUTER_TOOL_SCHEMAS:
        clar = ROUTER_TOOL_SCHEMAS["request_clarification"]
        if clar not in selected:
            selected.append(clar)

    return selected


def build_tool_selection_prompt(
    category: Optional[str] = None,
    compact: bool = True,
) -> str:
    """
    Build a dynamic tool selection prompt exposing ONLY category-relevant tools.
    Reduces tool list token footprint from ~70k tokens (full REA) to < 500 tokens.
    """
    tools = get_tools_for_category(category)
    tool_lines = []
    allowed_names = []

    for i, t in enumerate(tools, 1):
        name = t["name"]
        desc = t["description"]
        req = t["parameters"].get("required", [])
        req_str = f" [Required: {', '.join(req)}]" if req else " [No required args]"
        tool_lines.append(f"{i}. {name}: {desc}{req_str}")
        allowed_names.append(name)

    allowed_str = ", ".join(allowed_names)
    prompt = (
        f"You are an automated tool selector for the Samsung PRISM Engineering Assistant.\n\n"
        f"CRITICAL INSTRUCTION - ALLOWED TOOLS LIST:\n"
        f"You must ONLY select from the following {len(tools)} exact tool names:\n"
        + "\n".join(tool_lines) +
        f"\n\nIf the query cannot be fulfilled or is unsupported, output: {{\"tool\": \"none\", \"arguments\": {{}}}}\n"
        f"If an essential parameter (like a binary or file path) is missing, select 'request_clarification'.\n"
        f"Always return valid JSON: {{\"tool\": \"<tool_name>\", \"arguments\": {{...}}}}"
    )
    return prompt

