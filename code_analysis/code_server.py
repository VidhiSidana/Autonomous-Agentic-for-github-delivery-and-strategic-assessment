
import ast
from pathlib import Path
from mcp.server.mcpserver import MCPServer

mcp = MCPServer("Code Analysis Server")

# Folders that should not be scanned
IGNORED_DIRS = {
    ".venv",
    "venv",
    "__pycache__",
    ".git",
    "node_modules",
    "dist",
    "build"
}


def get_python_files(root):
    """Get Python files while skipping unnecessary folders."""

    for file_path in root.rglob("*.py"):

        # Skip files inside ignored folders
        if any(part in IGNORED_DIRS for part in file_path.parts):
            continue

        yield file_path


@mcp.tool()
def find_functions(directory: str) -> str:
    """Find Python functions and their file and line numbers."""

    root = Path(directory)

    if not root.exists():
        return f"Directory not found: {directory}"

    results = []

    for file_path in get_python_files(root):
        try:
            source = file_path.read_text(encoding="utf-8")
            tree = ast.parse(source)

            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    results.append(
                        f"Function: {node.name} | "
                        f"File: {file_path} | "
                        f"Line: {node.lineno}"
                    )

        except (SyntaxError, UnicodeDecodeError, OSError):
            continue

    if not results:
        return "No Python functions found."

    return "\n".join(results)


@mcp.tool()
def find_callers(directory: str, function_name: str) -> str:
    """Find Python function calls and their file and line numbers."""

    root = Path(directory)

    if not root.exists():
        return f"Directory not found: {directory}"

    results = []

    for file_path in get_python_files(root):
        try:
            source = file_path.read_text(encoding="utf-8")
            tree = ast.parse(source)

            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    called_function = None

                    if isinstance(node.func, ast.Name):
                        called_function = node.func.id

                    elif isinstance(node.func, ast.Attribute):
                        called_function = node.func.attr

                    if called_function == function_name:
                        results.append(
                            f"Function call: {function_name} | "
                            f"File: {file_path} | "
                            f"Line: {node.lineno}"
                        )

        except (SyntaxError, UnicodeDecodeError, OSError):
            continue

    if not results:
        return f"No callers found for '{function_name}'."

    return "\n".join(results)


@mcp.tool()
def find_module_relationships(directory: str, filename: str) -> str:
    """Find imported modules in a Python file."""

    root = Path(directory)

    if not root.exists():
        return f"Directory not found: {directory}"

    target_file = Path(filename)

    if not target_file.is_absolute():
        target_file = root / filename

    if not target_file.exists():
        return f"File not found: {target_file}"

    try:
        source = target_file.read_text(encoding="utf-8")
        tree = ast.parse(source)

    except (SyntaxError, UnicodeDecodeError, OSError) as error:
        return f"Unable to analyze file: {error}"

    imports = []

    for node in ast.walk(tree):

        if isinstance(node, ast.Import):

            for alias in node.names:
                imports.append(
                    f"Module: {alias.name} | Line: {node.lineno}"
                )

        elif isinstance(node, ast.ImportFrom):

            module_name = node.module or "relative import"

            imports.append(
                f"Module: {module_name} | Line: {node.lineno}"
            )

    if not imports:
        return f"No imports found in {target_file.name}."

    return (
        f"Module relationships for {target_file.name}:\n"
        + "\n".join(imports)
    )


if __name__ == "__main__":
    mcp.run()
