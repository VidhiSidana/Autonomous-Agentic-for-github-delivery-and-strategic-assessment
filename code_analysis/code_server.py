"""
Improved Code Analysis MCP Server for the Samsung PRISM Unified Engineering Agent.

This server uses Python AST for code analysis (fallback role).
It is NOT a full code knowledge graph. For complete graph analysis,
use the codebase-memory-mcp server (config/mcp_servers.json: code_graph).

Capabilities (AST-based):
  - Function and async function discovery
  - Class and method discovery
  - Caller identification (which call sites invoke a function)
  - Callee identification (what does a function call)
  - Module import analysis
  - Basic change-impact traversal
  - Structured JSON output

Known limitations:
  - Dynamic imports cannot be detected
  - Reflection and runtime-generated calls are not visible
  - Cross-language relationships are not supported
  - Ambiguous attribute calls (a.foo() where type of 'a' is unknown) are not resolved
  - Results are file-scoped, not project-wide semantic analysis
"""

import ast
import json
import sys
from pathlib import Path

from mcp.server.mcpserver import MCPServer

mcp = MCPServer("Code Analysis Fallback Server")

# ---------------------------------------------------------------------------
# Directory exclusions
# ---------------------------------------------------------------------------
IGNORED_DIRS = {
    ".venv", "venv", "__pycache__", ".git",
    "node_modules", "dist", "build", ".mypy_cache",
    ".pytest_cache", ".tox", "eggs", ".eggs",
}


def _get_python_files(root: Path):
    """Yield Python files, skipping ignored directories."""
    for file_path in root.rglob("*.py"):
        if any(part in IGNORED_DIRS for part in file_path.parts):
            continue
        yield file_path


def _enclosing_function(node: ast.AST, tree: ast.AST) -> str:
    """Find the name of the function/method that contains *node*."""
    # Build a parent map
    parent_map: dict[int, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parent_map[id(child)] = parent

    current = parent_map.get(id(node))
    while current is not None:
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return current.name
        current = parent_map.get(id(current))
    return "<module>"


def _parse_file(file_path: Path) -> tuple[str, ast.AST | None]:
    """Return (source, tree) or (source, None) on parse failure."""
    try:
        source = file_path.read_text(encoding="utf-8")
        return source, ast.parse(source)
    except (SyntaxError, UnicodeDecodeError, OSError):
        return "", None


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def find_functions(directory: str) -> str:
    """
    Find all Python functions and async functions in the directory.
    Returns structured JSON with file paths, line numbers, and class context.

    LIMITATION: AST-based; dynamic definitions are not detected.
    """
    root = Path(directory)
    if not root.exists():
        return json.dumps({"error": f"Directory not found: {directory}"})

    results: list[dict] = []

    for file_path in _get_python_files(root):
        _, tree = _parse_file(file_path)
        if tree is None:
            continue

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Determine if inside a class
                is_async = isinstance(node, ast.AsyncFunctionDef)
                results.append({
                    "name": node.name,
                    "file": str(file_path),
                    "line": node.lineno,
                    "end_line": getattr(node, "end_lineno", node.lineno),
                    "is_async": is_async,
                    "type": "function",
                })

    if not results:
        return json.dumps({
            "result": "No Python functions found.",
            "count": 0,
            "items": [],
        })

    return json.dumps({
        "result": f"Found {len(results)} function(s).",
        "count": len(results),
        "items": results,
        "limitation": (
            "AST analysis only. Dynamic definitions, decorators that "
            "rename functions, and exec()-generated code are not captured."
        ),
    }, indent=2)


@mcp.tool()
def find_classes(directory: str) -> str:
    """
    Find all Python classes and their methods in the directory.
    Returns structured JSON.

    LIMITATION: AST-based; dynamic class creation (type()) is not detected.
    """
    root = Path(directory)
    if not root.exists():
        return json.dumps({"error": f"Directory not found: {directory}"})

    results: list[dict] = []

    for file_path in _get_python_files(root):
        _, tree = _parse_file(file_path)
        if tree is None:
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                methods = [
                    {
                        "name": m.name,
                        "line": m.lineno,
                        "end_line": getattr(m, "end_lineno", m.lineno),
                        "is_async": isinstance(m, ast.AsyncFunctionDef),
                    }
                    for m in ast.walk(node)
                    if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and m is not node  # exclude self
                ]
                bases = [
                    ast.unparse(b) if hasattr(ast, "unparse") else "?"
                    for b in node.bases
                ]
                results.append({
                    "name": node.name,
                    "file": str(file_path),
                    "line": node.lineno,
                    "end_line": getattr(node, "end_lineno", node.lineno),
                    "bases": bases,
                    "methods": methods,
                    "type": "class",
                })

    return json.dumps({
        "result": f"Found {len(results)} class(es).",
        "count": len(results),
        "items": results,
    }, indent=2)


@mcp.tool()
def find_callers(directory: str, function_name: str) -> str:
    """
    Find all call sites that invoke *function_name* in the directory.
    Returns structured JSON with the caller function and location.

    LIMITATION: Matches by name only. If two functions share the same name
    in different modules, both are reported. Dynamic dispatch is not detected.
    """
    root = Path(directory)
    if not root.exists():
        return json.dumps({"error": f"Directory not found: {directory}"})

    results: list[dict] = []

    for file_path in _get_python_files(root):
        source, tree = _parse_file(file_path)
        if tree is None:
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                called = None
                if isinstance(node.func, ast.Name):
                    called = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    called = node.func.attr

                if called == function_name:
                    enclosing = _enclosing_function(node, tree)
                    results.append({
                        "callee": function_name,
                        "caller": enclosing,
                        "file": str(file_path),
                        "line": node.lineno,
                        "relationship": "calls",
                    })

    if not results:
        return json.dumps({
            "result": f"No callers found for '{function_name}'.",
            "count": 0,
            "items": [],
        })

    return json.dumps({
        "result": f"Found {len(results)} call site(s) for '{function_name}'.",
        "count": len(results),
        "items": results,
        "limitation": "Name-based matching only; attribute calls matched by method name.",
    }, indent=2)


@mcp.tool()
def find_callees(directory: str, function_name: str) -> str:
    """
    Find all functions called BY *function_name* in the directory.
    Returns structured JSON with callee names and locations.

    LIMITATION: AST-based; dynamic dispatch, closures, and lambdas may be missed.
    """
    root = Path(directory)
    if not root.exists():
        return json.dumps({"error": f"Directory not found: {directory}"})

    results: list[dict] = []

    for file_path in _get_python_files(root):
        _, tree = _parse_file(file_path)
        if tree is None:
            continue

        # Find the target function's AST node
        for node in ast.walk(tree):
            if (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == function_name
            ):
                # Walk calls within this function
                for call in ast.walk(node):
                    if isinstance(call, ast.Call):
                        callee_name = None
                        if isinstance(call.func, ast.Name):
                            callee_name = call.func.id
                        elif isinstance(call.func, ast.Attribute):
                            callee_name = call.func.attr

                        if callee_name:
                            results.append({
                                "caller": function_name,
                                "callee": callee_name,
                                "file": str(file_path),
                                "line": call.lineno,
                                "relationship": "calls",
                            })

    if not results:
        return json.dumps({
            "result": f"No callees found for '{function_name}'.",
            "count": 0,
            "items": [],
        })

    return json.dumps({
        "result": f"Found {len(results)} callee(s) for '{function_name}'.",
        "count": len(results),
        "items": results,
        "limitation": "AST-based; dynamic calls not detected.",
    }, indent=2)


@mcp.tool()
def find_module_relationships(directory: str, filename: str) -> str:
    """
    Find all imports in a Python file and their line numbers.
    Returns structured JSON.
    """
    root = Path(directory)
    if not root.exists():
        return json.dumps({"error": f"Directory not found: {directory}"})

    target = Path(filename)
    if not target.is_absolute():
        target = root / filename

    if not target.exists():
        return json.dumps({"error": f"File not found: {target}"})

    _, tree = _parse_file(target)
    if tree is None:
        return json.dumps({"error": f"Cannot parse file: {target}"})

    imports: list[dict] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append({
                    "module": alias.name,
                    "alias": alias.asname,
                    "type": "import",
                    "line": node.lineno,
                })
        elif isinstance(node, ast.ImportFrom):
            module_name = node.module or "(relative)"
            names = [a.name for a in node.names]
            imports.append({
                "module": module_name,
                "names": names,
                "level": node.level,  # dots for relative imports
                "type": "from_import",
                "line": node.lineno,
            })

    return json.dumps({
        "result": f"Found {len(imports)} import(s) in '{target.name}'.",
        "file": str(target),
        "count": len(imports),
        "items": imports,
    }, indent=2)


@mcp.tool()
def find_change_impact(directory: str, function_name: str) -> str:
    """
    Identify functions that may be affected if *function_name* changes.
    Traverses one level of caller relationships.

    Returns a list of direct callers and their callers (2-hop impact).

    LIMITATION: Limited to 2-hop AST traversal. No semantic analysis.
    """
    root = Path(directory)
    if not root.exists():
        return json.dumps({"error": f"Directory not found: {directory}"})

    # Level 1: direct callers
    direct_callers: set[str] = set()
    caller_details: list[dict] = []

    for file_path in _get_python_files(root):
        _, tree = _parse_file(file_path)
        if tree is None:
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                called = None
                if isinstance(node.func, ast.Name):
                    called = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    called = node.func.attr

                if called == function_name:
                    enclosing = _enclosing_function(node, tree)
                    direct_callers.add(enclosing)
                    caller_details.append({
                        "caller": enclosing,
                        "file": str(file_path),
                        "line": node.lineno,
                        "hop": 1,
                    })

    # Level 2: who calls the direct callers
    for caller_fn in list(direct_callers):
        for file_path in _get_python_files(root):
            _, tree = _parse_file(file_path)
            if tree is None:
                continue

            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    called = None
                    if isinstance(node.func, ast.Name):
                        called = node.func.id
                    elif isinstance(node.func, ast.Attribute):
                        called = node.func.attr

                    if called == caller_fn:
                        enclosing = _enclosing_function(node, tree)
                        caller_details.append({
                            "caller": enclosing,
                            "calls": caller_fn,
                            "file": str(file_path),
                            "line": node.lineno,
                            "hop": 2,
                        })

    return json.dumps({
        "result": (
            f"Change-impact analysis for '{function_name}': "
            f"{len(direct_callers)} direct caller(s) found."
        ),
        "function": function_name,
        "direct_callers": list(direct_callers),
        "impact_chain": caller_details,
        "limitation": (
            "2-hop AST traversal only. Dynamic dispatch, indirect "
            "calls, and cross-language impacts are not covered."
        ),
    }, indent=2)


if __name__ == "__main__":
    mcp.run()
