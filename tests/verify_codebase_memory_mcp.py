"""
Live verification script for codebase-memory-mcp integration.
Connects to the real codebase-memory-mcp server, inspects actual tools & schemas,
indexes the repository, and executes symbol search and call-path tracing.
"""

import asyncio
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from agent.mcp_client import MCPClientManager


async def verify_codebase_memory_mcp():
    print("=" * 70)
    print(" 1. CONNECTING TO REAL codebase-memory-mcp SERVER OVER STDIO")
    print("=" * 70)

    manager = MCPClientManager()
    session = await manager._ensure_connected("code_graph")
    print("[+] Successfully connected to codebase-memory-mcp session.")

    # 1. Discover tools dynamically
    tools_res = await session.list_tools()
    print(f"\n[+] Discovered {len(tools_res.tools)} tools on live server:")
    for tool in tools_res.tools:
        required = tool.inputSchema.get("required", []) if isinstance(tool.inputSchema, dict) else []
        print(f"  * {tool.name}")
        print(f"    - Description: {tool.description.splitlines()[0][:85]}...")
        print(f"    - Required args: {required}")

    print("\n" + "=" * 70)
    print(" 2. REPOSITORY INDEXING")
    print("=" * 70)
    repo_path = str(PROJECT_ROOT)
    idx_res = await manager.call_tool("code_graph", "index_repository", {"repo_path": repo_path})
    print(f"index_repository success: {idx_res.success}")
    print("index_repository raw output:")
    print(idx_res.text)

    # Parse project name
    project_name = None
    try:
        data = json.loads(idx_res.text)
        project_name = data.get("project")
    except Exception:
        # Fallback to list_projects
        lp = await manager.call_tool("code_graph", "list_projects", {})
        for line in lp.text.splitlines():
            if repo_path in line or "Users-" in line:
                project_name = line.strip().split()[0]
                break

    print(f"\n[+] Active project identifier: {project_name}")
    if not project_name:
        print("[-] Failed to retrieve project identifier.")
        await manager.close_all()
        return

    print("\n" + "=" * 70)
    print(" 3. SYMBOL SEARCH (search_graph)")
    print("=" * 70)
    search_res = await manager.call_tool("code_graph", "search_graph", {
        "project": project_name,
        "query": "validate_payment",
    })
    print(f"search_graph success: {search_res.success}")
    print("search_graph output:")
    print(search_res.text)

    # Extract first qualified name
    first_qn = None
    for line in search_res.text.splitlines():
        parts = line.strip().split()
        if len(parts) >= 2 and parts[1] in ("Function", "Method"):
            first_qn = parts[0]
            break

    print(f"[+] Target Qualified Name: {first_qn}")

    print("\n" + "=" * 70)
    print(" 4. INBOUND CALLER TRACING (trace_path inbound)")
    print("=" * 70)
    trace_in = await manager.call_tool("code_graph", "trace_path", {
        "project": project_name,
        "function_name": first_qn or "validate_payment",
        "direction": "inbound",
        "include_tests": True,
    })
    print(f"trace_path (inbound) success: {trace_in.success}")
    print("trace_path (inbound) output:")
    print(trace_in.text)

    print("\n" + "=" * 70)
    print(" 5. OUTBOUND CALLEE TRACING (trace_path outbound)")
    print("=" * 70)
    trace_out = await manager.call_tool("code_graph", "trace_path", {
        "project": project_name,
        "function_name": first_qn or "validate_payment",
        "direction": "outbound",
        "include_tests": True,
    })
    print(f"trace_path (outbound) success: {trace_out.success}")
    print("trace_path (outbound) output:")
    print(trace_out.text)

    print("\n" + "=" * 70)
    print(" 6. REPOSITORY ARCHITECTURE SUMMARY (get_architecture)")
    print("=" * 70)
    arch_res = await manager.call_tool("code_graph", "get_architecture", {
        "project": project_name,
    })
    print(f"get_architecture success: {arch_res.success}")
    print("get_architecture output (first 500 chars):")
    print(arch_res.text[:500] + ("..." if len(arch_res.text) > 500 else ""))

    await manager.close_all()
    print("\n[+] Verification completed cleanly.")


if __name__ == "__main__":
    asyncio.run(verify_codebase_memory_mcp())

