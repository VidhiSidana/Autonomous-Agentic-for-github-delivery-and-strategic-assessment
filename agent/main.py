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

            if user_input.lower() == "summary":
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
        agent.session_mgr.end_session("Session closed by user.")
        await agent.close()
        print("Agent stopped cleanly.")


if __name__ == "__main__":
    asyncio.run(cli_main())
