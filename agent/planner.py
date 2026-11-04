"""
Structured Query Planner for the Samsung PRISM Unified Engineering Agent.

Improvements over the original keyword-only router:
  - Returns a validated Pydantic QueryPlan (not a bare string)
  - Supports MULTI_TOOL category for cross-cutting queries
  - Extracts parameters from the query text
  - Requests clarification when essential parameters are missing
  - Preserves all original keyword logic as a foundation
"""

import re
import sys
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

# Allow running standalone
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ---------------------------------------------------------------------------
# Query categories
# ---------------------------------------------------------------------------

class QueryCategory(str, Enum):
    CODE_ANALYSIS   = "code_analysis"
    BINARY_ANALYSIS = "binary_analysis"
    MEMORY          = "memory"
    GENERAL         = "general"
    MULTI_TOOL      = "multi_tool"
    CLARIFY         = "clarify"      # planner needs more info before routing


# ---------------------------------------------------------------------------
# Structured plan
# ---------------------------------------------------------------------------

class QueryPlan(BaseModel):
    """
    The structured output of the planner.
    All fields except *category* and *raw_query* are optional — the
    orchestrator must validate required fields before calling tools.
    """
    category: QueryCategory
    raw_query: str

    # Code-analysis parameters
    function_name: Optional[str] = Field(
        default=None,
        description="Name of the function to search for or analyse.",
    )
    file_path: Optional[str] = Field(
        default=None,
        description="Relative or absolute path to a source file.",
    )
    repository_path: Optional[str] = Field(
        default=None,
        description="Root directory of the repository to analyse.",
    )
    module_name: Optional[str] = Field(
        default=None,
        description="Python module or package name.",
    )

    # Binary-analysis parameters
    binary_path: Optional[str] = Field(
        default=None,
        description="Path to the binary file to analyse.",
    )
    binary_operation: Optional[str] = Field(
        default=None,
        description="Specific binary operation: metadata|functions|disassemble|strings|imports.",
    )

    # Memory parameters
    memory_keywords: list[str] = Field(
        default_factory=list,
        description="Keywords to search in engineering memory.",
    )
    memory_operation: Optional[str] = Field(
        default=None,
        description="Memory operation: save|search|retrieve|update.",
    )
    memory_title: Optional[str] = Field(
        default=None,
        description="Title for a new memory entry.",
    )
    memory_content: Optional[str] = Field(
        default=None,
        description="Content body for a new memory entry.",
    )
    memory_category: Optional[str] = Field(
        default=None,
        description="Category for a new memory entry.",
    )
    memory_verification_status: Optional[str] = Field(
        default=None,
        description="Verification status: VERIFIED|HYPOTHESIS|NEEDS_REVIEW.",
    )

    # Clarification
    clarification_needed: bool = False
    clarification_question: Optional[str] = Field(
        default=None,
        description="Question to ask the user to resolve ambiguity.",
    )

    # Multi-tool sub-plans
    sub_categories: list[str] = Field(
        default_factory=list,
        description="For MULTI_TOOL: list of involved category names.",
    )


# ---------------------------------------------------------------------------
# Keyword lists
# ---------------------------------------------------------------------------

_MEMORY_KEYWORDS: list[str] = [
    "remember", "save finding", "save memory", "store finding",
    "retrieve", "recall", "show memory", "list memory",
    "search finding", "search memory", "what did we", "what do we know",
    "previous session", "last session", "engineering memory",
    "finding", "findings",
]

_BINARY_KEYWORDS: list[str] = [
    "binary", "executable", "exe", "dll", "elf",
    "disassembly", "disassemble", "decompile", "decompilation",
    "assembly", "reverse engineering", "reverse-engineering",
    "pe file", "pe binary", "binary analysis", "analyze binary",
    "analyse binary", "binary function", "binary functions",
    "exported function", "entry point",
]

_CODE_KEYWORDS: list[str] = [
    "source code", "code analysis", "find function", "function",
    "functions", "caller", "callers", "calls", "who calls", "called by",
    "callee", "callees", "module", "modules", "python file", "codebase",
    "import", "imports", "dependency", "dependencies", "depend",
    "class", "classes", "method", "methods", "repository", "repo",
    "change impact", "impact of", "file depends",
]

_MULTI_TOOL_PATTERNS: list[str] = [
    "and", "also", "compare", "both", "cross-reference",
    "find.*and.*analyz", "code.*binary", "binary.*code",
    "codebase.*executable", "source.*binary",
]

# Operation sub-keywords
_BINARY_OPERATIONS: dict[str, str] = {
    "disassemble": "disassemble",
    "disassembly": "disassemble",
    "assembly": "disassemble",
    "instruction": "disassemble",
    "decompile": "disassemble",
    "export": "functions",
    "function": "functions",
    "functions": "functions",
    "metadata": "metadata",
    "architecture": "metadata",
    "section": "metadata",
    "header": "metadata",
    "string": "strings",
    "strings": "strings",
    "import": "imports",
    "imports": "imports",
}

_MEMORY_OPERATIONS: dict[str, str] = {
    "remember": "save",
    "save": "save",
    "store": "save",
    "retrieve": "retrieve",
    "recall": "retrieve",
    "list memory": "retrieve",
    "show memory": "retrieve",
    "search": "search",
    "what did we": "search",
    "what do we know": "search",
}

_VERIFICATION_STATUS: dict[str, str] = {
    "verified": "VERIFIED",
    "confirmed": "VERIFIED",
    "this is verified": "VERIFIED",
    "hypothesis": "HYPOTHESIS",
    "unverified": "HYPOTHESIS",
    "needs review": "NEEDS_REVIEW",
}


# ---------------------------------------------------------------------------
# Parameter extractors
# ---------------------------------------------------------------------------

def _extract_function_name(query: str) -> Optional[str]:
    """Extract a function name from patterns like 'callers of foo' or 'find foo function'."""
    patterns = [
        r"callers?\s+of\s+[`'\"]?(\w+)[`'\"]?",
        r"calls?\s+[`'\"]?(\w+)[`'\"]?",
        r"who calls?\s+[`'\"]?(\w+)[`'\"]?",
        r"called by\s+[`'\"]?(\w+)[`'\"]?",
        r"find\s+[`'\"]?(\w+)[`'\"]?\s+function",
        r"function\s+[`'\"]?(\w+)[`'\"]?",
        r"callees?\s+of\s+[`'\"]?(\w+)[`'\"]?",
        r"calls\s+made by\s+[`'\"]?(\w+)[`'\"]?",
    ]
    for pat in patterns:
        m = re.search(pat, query, re.IGNORECASE)
        if m:
            return m.group(1)
    return None


def _extract_file_path(query: str) -> Optional[str]:
    """Extract a file path from the query."""
    patterns = [
        r"[`'\"]([^`'\"]+\.py)[`'\"]",   # quoted .py path
        r"(\S+\.py)\b",                    # bare .py path
        r"[`'\"]([^`'\"]+\.(js|ts|c|cpp|h|java|go|rs))[`'\"]",
        r"(?:file|in|from)\s+(\S+\.\w{1,5})\b",
    ]
    for pat in patterns:
        m = re.search(pat, query, re.IGNORECASE)
        if m:
            return m.group(1)
    return None


def _extract_binary_path(query: str) -> Optional[str]:
    """Extract a binary file path from the query."""
    # 1. Quoted paths or paths with binary extensions
    patterns = [
        r"[`'\"]([^`'\"]+\.(exe|dll|elf|so|bin|out))[`'\"]",
        r"(\S+\.(exe|dll|elf|so|bin|out))\b",
        r"[`'\"]([^`'\"]+/[^`'\"]+)[`'\"]",
        r"[`'\"]([^`'\"]+\\[^`'\"]+)[`'\"]",
    ]
    for pat in patterns:
        m = re.search(pat, query, re.IGNORECASE)
        if m:
            return m.group(1).rstrip(".,;:!?'\"")

    # 2. Check for explicit path after "binary/file/analyse/analyze"
    generic_words = {
        "file", "binary", "executable", "path", "instructions", "code",
        "functions", "architecture", "sections", "strings", "imports",
        "sample", "target", "this", "the", "that", "it",
    }
    m = re.search(r"(?:binary|file|analyse|analyze)\s+[`'\"]?([^\s`'\"]+)[`'\"]?", query, re.IGNORECASE)
    if m:
        candidate = m.group(1).strip().rstrip(".,;:!?'\"")
        if candidate.lower() not in generic_words:
            # Must look like an actual filename or path
            if "/" in candidate or "\\" in candidate:
                return candidate
            if "." in candidate:
                ext = candidate.rsplit(".", 1)[-1].lower()
                if ext in ("exe", "dll", "elf", "so", "bin", "out", "obj", "o"):
                    return candidate

    return None


def _extract_memory_keywords(query: str, operation: str) -> list[str]:
    """Extract search terms for memory queries."""
    if operation not in ("search", "retrieve"):
        return []
    # Remove common command words to get meaningful keywords
    stop_words = {
        "search", "find", "retrieve", "recall", "memory", "finding",
        "what", "did", "we", "do", "know", "about", "previous", "session",
        "the", "a", "an", "in", "for", "of",
    }
    words = re.findall(r"\w+", query.lower())
    return [w for w in words if w not in stop_words and len(w) > 2]


def _extract_binary_operation(query: str) -> str:
    """Determine the specific binary operation requested."""
    q = query.lower()
    for keyword, operation in _BINARY_OPERATIONS.items():
        if keyword in q:
            return operation
    return "metadata"  # default


def _extract_memory_operation(query: str) -> str:
    """Determine the specific memory operation."""
    q = query.lower()
    for keyword, operation in _MEMORY_OPERATIONS.items():
        if keyword in q:
            return operation
    return "retrieve"


def _extract_verification_status(query: str) -> Optional[str]:
    """Extract verification status from memory save commands."""
    q = query.lower()
    for keyword, status in _VERIFICATION_STATUS.items():
        if keyword in q:
            return status
    return None


def _is_multi_tool(query: str, has_code: bool, has_binary: bool) -> bool:
    """Return True if the query explicitly involves both code and binary analysis."""
    if not (has_code and has_binary):
        return False
    q = query.lower()
    # Explicit cross-domain indicators
    return any(re.search(pat, q) for pat in _MULTI_TOOL_PATTERNS)


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------

class AgentPlanner:
    """
    Classifies a user query and extracts parameters into a QueryPlan.

    Usage::

        planner = AgentPlanner()
        plan = planner.plan(user_input)
        if plan.clarification_needed:
            # ask plan.clarification_question
        elif plan.category == QueryCategory.CODE_ANALYSIS:
            # proceed with plan.function_name, plan.file_path, etc.
    """

    def plan(self, user_input: str) -> QueryPlan:
        """
        Parse *user_input* and return a structured QueryPlan.
        """
        q = user_input.lower()

        # -----------------------------------------------------------------
        # Detect which broad categories apply
        # -----------------------------------------------------------------
        has_memory = any(kw in q for kw in _MEMORY_KEYWORDS)
        has_binary = any(kw in q for kw in _BINARY_KEYWORDS)
        has_code   = any(kw in q for kw in _CODE_KEYWORDS)

        # -----------------------------------------------------------------
        # Memory — highest priority (memory commands rarely mix with tools)
        # -----------------------------------------------------------------
        if has_memory and not (has_code or has_binary):
            memory_op = _extract_memory_operation(q)
            kws = _extract_memory_keywords(q, memory_op)
            return QueryPlan(
                category=QueryCategory.MEMORY,
                raw_query=user_input,
                memory_operation=memory_op,
                memory_keywords=kws,
                memory_verification_status=_extract_verification_status(q),
            )

        # -----------------------------------------------------------------
        # Multi-tool: query spans both code and binary domains
        # -----------------------------------------------------------------
        if _is_multi_tool(q, has_code, has_binary):
            return QueryPlan(
                category=QueryCategory.MULTI_TOOL,
                raw_query=user_input,
                function_name=_extract_function_name(q),
                file_path=_extract_file_path(q),
                binary_path=_extract_binary_path(q),
                binary_operation=_extract_binary_operation(q),
                sub_categories=[
                    QueryCategory.CODE_ANALYSIS.value,
                    QueryCategory.BINARY_ANALYSIS.value,
                ],
            )

        # -----------------------------------------------------------------
        # Binary analysis
        # -----------------------------------------------------------------
        if has_binary and not has_code:
            binary_path = _extract_binary_path(q)
            return QueryPlan(
                category=QueryCategory.BINARY_ANALYSIS,
                raw_query=user_input,
                binary_path=binary_path,
                binary_operation=_extract_binary_operation(q),
                clarification_needed=binary_path is None,
                clarification_question=(
                    "Please provide the path to the binary file you want to analyse."
                    if binary_path is None else None
                ),
            )

        # -----------------------------------------------------------------
        # Code analysis
        # -----------------------------------------------------------------
        if has_code:
            fn_name = _extract_function_name(q)
            file_path = _extract_file_path(q)
            return QueryPlan(
                category=QueryCategory.CODE_ANALYSIS,
                raw_query=user_input,
                function_name=fn_name,
                file_path=file_path,
            )

        # -----------------------------------------------------------------
        # General — no specific tool detected
        # -----------------------------------------------------------------
        return QueryPlan(
            category=QueryCategory.GENERAL,
            raw_query=user_input,
        )


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    planner = AgentPlanner()
    test_queries = [
        "Find all callers of process_data in this repository.",
        "Analyse this authorised executable and identify its architecture.",
        "What did we discover about authentication in the previous session?",
        "Find the authentication implementation in the codebase and compare it with the binary.",
        "Explain what a mutex is.",
        "Remember this finding: auth is handled in auth_service.py. This is verified.",
        "Who calls authenticate_user?",
        "Search memory for database findings.",
    ]
    for q in test_queries:
        plan = planner.plan(q)
        print(f"\nQuery  : {q}")
        print(f"Category: {plan.category.value}")
        if plan.function_name:
            print(f"Function: {plan.function_name}")
        if plan.binary_path:
            print(f"Binary  : {plan.binary_path}")
        if plan.memory_operation:
            print(f"Mem-op  : {plan.memory_operation}")
        if plan.clarification_needed:
            print(f"Need clarification: {plan.clarification_question}")
