"""
Unified Engineering Agent - Main CLI Interface
Samsung PRISM Project: Unified Local-LLM Agent for Code Comprehension,
Binary Investigation and Persistent Engineering Memory.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from agent.llm import LocalLLM
from agent.orchestrator import AgentOrchestrator
from agent.planner import AgentPlanner
from memory.memory import EngineeringMemory
from memory.session_manager import SessionManager


class UnifiedEngineeringAgent:
    """
    Unified Engineering Agent interface.
    Delegates planning, tool execution, and LLM synthesis to AgentOrchestrator.
    """

    def __init__(self) -> None:
        self.llm = LocalLLM()
        self.planner = AgentPlanner()
        self.memory = EngineeringMemory()
        self.session_mgr = SessionManager()
        self.orchestrator = AgentOrchestrator(
            llm=self.llm,
            planner=self.planner,
            memory=self.memory,
            session_manager=self.session_mgr,
        )

    def process_query(self, user_input: str, overrides: dict = None) -> str:
        """
        Synchronous entry point for processing a query.
        Safe for CLI, scripts, and unit tests.
        """
        return asyncio.run(self.process_query_async(user_input, overrides))

    async def process_query_async(self, user_input: str, overrides: dict = None) -> str:
        """
        Asynchronous processing pipeline.
        """
        result = await self.orchestrator.process_query(user_input, overrides=overrides)
        return result.response_text

    async def close(self) -> None:
        """Release MCP and background resources."""
        await self.orchestrator.close()


def print_banner(agent: UnifiedEngineeringAgent) -> None:
    print("=" * 60)
    print("  Samsung PRISM — Unified Local Engineering Agent")
    print("  Code Comprehension | Binary Analysis | Persistent Memory")
    print("=" * 60)
    avail, reason = agent.llm.check_availability()
    print(f"[*] Local LLM ({agent.llm.model}): {'ONLINE' if avail else 'OFFLINE (' + reason + ')'}")
    print(f"[*] Session ID: {agent.session_mgr.current_session_id}")
    print("[*] Type 'exit' to quit, 'summary' for session info.")
    print("-" * 60)


async def cli_main() -> None:
    agent = UnifiedEngineeringAgent()
    print_banner(agent)

    try:
        while True:
            try:
                user_input = input("\nYou: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nStopping agent...")
                break

            if not user_input:
                continue

            if user_input.lower() in ("exit", "quit", "q"):
                print("Ending session and exiting...")
                break

            if user_input.lower() in ("/pending", "pending"):
                pending = agent.memory.get_pending_proposals()
                if not pending:
                    print("\n[Engineer Flow] No pending findings awaiting confirmation.")
                else:
                    print(f"\n[Engineer Flow] {len(pending)} pending finding(s) awaiting confirmation:")
                    for row in pending:
                        r = dict(row)
                        print(f"  [{r['id']}] {r['title']} (source: {r.get('source', 'unknown')}, refs: {r.get('evidence_refs', 'none')})")
                continue

            if user_input.startswith("/confirm ") or user_input.startswith("confirm "):
                parts = user_input.split(maxsplit=1)
                if len(parts) > 1 and parts[1].strip().isdigit():
                    mem_id = int(parts[1].strip())
                    res = agent.memory.confirm_finding(mem_id, confirmed_by="engineer")
                    print(f"\n[Engineer Flow] {res['message']}")
                else:
                    print("\n[Engineer Flow] Usage: /confirm <id>")
                continue

            if user_input.startswith("/reject ") or user_input.startswith("reject "):
                parts = user_input.split(maxsplit=2)
                if len(parts) > 1 and parts[1].strip().isdigit():
                    mem_id = int(parts[1].strip())
                    reason = parts[2].strip() if len(parts) > 2 else ""
                    res = agent.memory.reject_finding(mem_id, reason=reason, rejected_by="engineer")
                    print(f"\n[Engineer Flow] {res['message']}")
                else:
                    print("\n[Engineer Flow] Usage: /reject <id> [reason]")
                continue

            if user_input.lower() in ("summary", "/summary"):
                session_id = agent.session_mgr.current_session_id
                print(f"\n[Session Info] Active ID: {session_id}")
                recent = agent.memory.retrieve_memory(limit=5)
                print(f"[Session Info] Stored findings: {len(recent)} recent items")
                continue

            # Process query
            result = await agent.orchestrator.process_query(user_input)

            # If parameter clarification is required, ask user at CLI layer
            if result.clarification_needed:
                print(f"\n[Agent]: {result.clarification_question}")
                param_input = input("Your input: ").strip()
                if param_input:
                    # Retry with parameter override
                    overrides = {}
                    if "binary" in result.category:
                        overrides["binary_path"] = param_input
                    elif "code" in result.category:
                        overrides["function_name"] = param_input
                    result = await agent.orchestrator.process_query(user_input, overrides=overrides)

            print(f"\n[Agent - {result.category.upper()}]:")
            print(result.response_text)
            print("-" * 60)

    finally:
        agent.session_mgr.on_session_end(llm=agent.llm)
        await agent.close()
        print("Agent stopped cleanly.")


if __name__ == "__main__":
    asyncio.run(cli_main())
