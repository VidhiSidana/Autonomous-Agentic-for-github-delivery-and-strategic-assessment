"""
Live verification script for codebase-memory-mcp integration.
Connects to the real codebase-memory-mcp server, inspects actual tools & schemas dynamically,
indexes the repository, and executes symbol search, caller tracing, callee exploration,
and architecture queries with dynamic schema validation.
"""

import asyncio
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from agent.mcp_client import MCPClientManager


async def verify_codebase_memory_mcp():
    print("=" * 70, flush=True)
    print(" 1. CONNECTING TO REAL codebase-memory-mcp SERVER OVER STDIO", flush=True)
    print("=" * 70, flush=True)

    manager = MCPClientManager()
    session = await manager._ensure_connected("code_graph")
    print("[+] Successfully connected to codebase-memory-mcp session.", flush=True)

    # 1. Discover tools and schemas dynamically
    schemas = await manager.list_tools_with_schemas("code_graph")
    print(f"\n[+] Discovered {len(schemas)} tools on live server:", flush=True)
    for name, s in schemas.items():
        desc = s.get("description", "").splitlines()[0][:70] if s.get("description") else "No description"
        req = s.get("inputSchema", {}).get("required", [])
        print(f"  * {name}", flush=True)
        print(f"    - Description: {desc}...", flush=True)
        print(f"    - Required args: {req}", flush=True)

    print("\n" + "=" * 70, flush=True)
    print(" 2. REPOSITORY INDEXING (index_repository)", flush=True)
    print("=" * 70, flush=True)
    repo_path = str(PROJECT_ROOT)
    idx_res = await manager.call_tool("code_graph", "index_repository", {"repo_path": repo_path})
    print(f"index_repository success: {idx_res.success}", flush=True)
    print("index_repository raw output:", flush=True)
    print(idx_res.text, flush=True)

    # Parse project name
    project_name = None
    try:
        data = json.loads(idx_res.text)
        project_name = data.get("project")
    except Exception:
        # Fallback to list_projects
        lp = await manager.call_tool("code_graph", "list_projects", {})
        for line in lp.text.splitlines():
            if repo_path in line or "Autonomous-Agentic" in line or "samsung" in line:
                project_name = line.strip().split()[0]
                break

    print(f"\n[+] Active project identifier: {project_name}", flush=True)
    if not project_name:
        # Fallback to listing projects
        lp_res = await manager.call_tool("code_graph", "list_projects", {})
        print("list_projects output:\n", lp_res.text, flush=True)
        for line in lp_res.text.splitlines():
            parts = line.strip().split()
            if parts and not parts[0].startswith("projects:") and not parts[0].startswith("total:"):
                project_name = parts[0]
                break

    if not project_name:
        print("[-] Failed to retrieve project identifier.", flush=True)
        await manager.close_all()
        return

    print("\n" + "=" * 70, flush=True)
    print(" 3. SYMBOL SEARCH (search_graph)", flush=True)
    print("=" * 70, flush=True)
    search_res = await manager.call_tool("code_graph", "search_graph", {
        "project": project_name,
        "query": "process_query",
    })
    print(f"search_graph success: {search_res.success}", flush=True)
    print("search_graph output:", flush=True)
    print(search_res.text, flush=True)

    # Extract first qualified name for process_query
    first_qn = None
    for line in search_res.text.splitlines():
        parts = line.strip().split()
        if len(parts) >= 2 and parts[1] in ("Function", "Method"):
            first_qn = parts[0]
            break

    print(f"[+] Target Qualified Name for Caller Tracing: {first_qn}", flush=True)

    print("\n" + "=" * 70, flush=True)
    print(" 4. INBOUND CALLER TRACING (trace_path inbound)", flush=True)
    print("=" * 70, flush=True)
    trace_in = await manager.call_tool("code_graph", "trace_path", {
        "project": project_name,
        "function_name": first_qn or "agent.orchestrator.AgentOrchestrator.process_query",
        "direction": "inbound",
        "include_tests": True,
    })
    print(f"trace_path (inbound) success: {trace_in.success}", flush=True)
    print("trace_path (inbound) output:", flush=True)
    print(trace_in.text, flush=True)

    print("\n" + "=" * 70, flush=True)
    print(" 5. OUTBOUND CALLEE TRACING (trace_path outbound)", flush=True)
    print("=" * 70, flush=True)
    trace_out = await manager.call_tool("code_graph", "trace_path", {
        "project": project_name,
        "function_name": first_qn or "agent.orchestrator.AgentOrchestrator.process_query",
        "direction": "outbound",
        "include_tests": True,
    })
    print(f"trace_path (outbound) success: {trace_out.success}", flush=True)
    print("trace_path (outbound) output:", flush=True)
    print(trace_out.text, flush=True)

    print("\n" + "=" * 70, flush=True)
    print(" 6. REPOSITORY ARCHITECTURE & DEPENDENCIES (get_architecture)", flush=True)
    print("=" * 70, flush=True)
    arch_res = await manager.call_tool("code_graph", "get_architecture", {
        "project": project_name,
    })
    print(f"get_architecture success: {arch_res.success}", flush=True)
    print("get_architecture output:\n", arch_res.text[:1200] + ("..." if len(arch_res.text) > 1200 else ""), flush=True)

    print("\n" + "=" * 70, flush=True)
    print(" 7. DYNAMIC ARGUMENT VALIDATION TEST", flush=True)
    print("=" * 70, flush=True)
    # Attempt call with missing required parameter 'project'
    val_fail = await manager.call_tool("code_graph", "search_graph", {"query": "test"})
    print(f"Missing parameter validation caught: {val_fail.is_error} | Error: {val_fail.error_message}", flush=True)

    await manager.close_all()
    print("\n[+] Verification completed cleanly.", flush=True)


if __name__ == "__main__":
    asyncio.run(verify_codebase_memory_mcp())
