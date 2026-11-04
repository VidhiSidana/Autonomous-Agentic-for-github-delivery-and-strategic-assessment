"""
Consolidated Agent Orchestrator for the Samsung PRISM Unified Engineering Agent.

This module coordinates:
  1. Query understanding & planning (AgentPlanner)
  2. Policy validation & authorization (agent.policy)
  3. MCP tool invocation across named servers (MCPClientManager)
  4. Persistent engineering memory storage and retrieval (EngineeringMemory)
  5. Multi-session lifecycle management (SessionManager)
  6. Evidence normalization and aggregation (EvidenceBundle)
  7. Evidence-grounded local LLM response generation (LocalLLM)

No internal interactive input() calls: functions receive parameters explicitly
and return structured OrchestrationResult objects.
"""

import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from agent.evidence import (
    EvidenceBundle,
    EvidenceItem,
    EvidenceKind,
    build_llm_prompt,
    normalise_binary_result,
    normalise_code_result,
    normalise_memory_result,
)
from agent.llm import LocalLLM
from agent.mcp_client import MCPClientManager, ToolResult
from agent.planner import AgentPlanner, QueryCategory, QueryPlan
from agent.policy import authorize_binary_path
from memory.memory import EngineeringMemory
from memory.session_manager import SessionManager

logger = logging.getLogger(__name__)


@dataclass
class OrchestrationResult:
    """Structured response from the agent orchestrator."""
    query: str
    category: str
    plan: QueryPlan
    evidence_bundle: EvidenceBundle
    response_text: str
    clarification_needed: bool = False
    clarification_question: Optional[str] = None
    session_id: Optional[str] = None
    error: Optional[str] = None


class AgentOrchestrator:
    """
    Main orchestration engine connecting planning, tools, memory, and LLM.
    Fully asynchronous and testable without CLI prompts.
    """

    def __init__(
        self,
        llm: Optional[LocalLLM] = None,
        planner: Optional[AgentPlanner] = None,
        mcp_manager: Optional[MCPClientManager] = None,
        memory: Optional[EngineeringMemory] = None,
        session_manager: Optional[SessionManager] = None,
        default_repo_dir: Optional[Path] = None,
    ) -> None:
        self.llm = llm or LocalLLM()
        self.planner = planner or AgentPlanner()
        self.mcp = mcp_manager or MCPClientManager()
        self.memory = memory or EngineeringMemory()
        self.session_mgr = session_manager or SessionManager()
        self.default_repo_dir = default_repo_dir or PROJECT_ROOT

        # Ensure active session exists
        if not self.session_mgr.current_session_id:
            self.session_mgr.start_session()

    async def process_query(
        self,
        user_query: str,
        overrides: Optional[dict[str, Any]] = None,
    ) -> OrchestrationResult:
        """
        Process a user query end-to-end:
          Plan -> Tool Selection -> MCP Execution -> Evidence Aggregation -> LLM Response.
        """
        overrides = overrides or {}
        session_id = self.session_mgr.current_session_id or "unknown"
        self.session_mgr.increment_query_count()

        # Step 1: Query Understanding & Planning
        plan = self.planner.plan(user_query)

        # Apply any explicit parameter overrides (e.g. from tests or UI)
        for key, val in overrides.items():
            if hasattr(plan, key) and val is not None:
                setattr(plan, key, val)

        # Step 2: Handle Clarification Requirements
        if plan.clarification_needed:
            bundle = EvidenceBundle(query=user_query)
            bundle.add_limitation(plan.clarification_question or "Parameter missing.")
            return OrchestrationResult(
                query=user_query,
                category=plan.category.value,
                plan=plan,
                evidence_bundle=bundle,
                response_text=plan.clarification_question or "Please clarify your request.",
                clarification_needed=True,
                clarification_question=plan.clarification_question,
                session_id=session_id,
            )

        evidence_bundle = EvidenceBundle(query=user_query)

        # Step 3: Dispatch by Category
        try:
            if plan.category == QueryCategory.MEMORY:
                await self._handle_memory(plan, evidence_bundle, session_id)

            elif plan.category == QueryCategory.CODE_ANALYSIS:
                await self._handle_code_analysis(plan, evidence_bundle)

            elif plan.category == QueryCategory.BINARY_ANALYSIS:
                await self._handle_binary_analysis(plan, evidence_bundle)

            elif plan.category == QueryCategory.MULTI_TOOL:
                await self._handle_multi_tool(plan, evidence_bundle)

            elif plan.category == QueryCategory.GENERAL:
                await self._handle_general(plan, evidence_bundle)

        except Exception as exc:
            logger.error("Error during tool execution: %s", exc, exc_info=True)
            evidence_bundle.add_limitation(f"Tool execution exception: {exc}")

        # Step 4: Evidence Synthesis via Local LLM
        response_text = await self._generate_response(user_query, plan, evidence_bundle)

        return OrchestrationResult(
            query=user_query,
            category=plan.category.value,
            plan=plan,
            evidence_bundle=evidence_bundle,
            response_text=response_text,
            session_id=session_id,
        )

    # ------------------------------------------------------------------
    # Category handlers
    # ------------------------------------------------------------------

    async def _handle_memory(
        self,
        plan: QueryPlan,
        bundle: EvidenceBundle,
        session_id: str,
    ) -> None:
        op = plan.memory_operation or "retrieve"

        if op == "save":
            title = plan.memory_title or plan.raw_query[:50]
            content = plan.memory_content or plan.raw_query
            status = plan.memory_verification_status or "VERIFIED"
            save_res = self.memory.save_memory(
                title=title,
                content=content,
                category=plan.memory_category or "technical_finding",
                verification_status=status,
                session_id=session_id,
            )
            bundle.add(EvidenceItem(
                kind=EvidenceKind.VERIFIED if status == "VERIFIED" else EvidenceKind.HYPOTHESIS,
                source="engineering_memory.save",
                summary=save_res.get("message", "Memory recorded."),
                detail=f"Title: {title}\nStatus: {status}",
            ))

        elif op == "search":
            keywords = " ".join(plan.memory_keywords) if plan.memory_keywords else plan.raw_query
            results = self.memory.search_memory(keywords)
            items = normalise_memory_result(results, keyword=keywords)
            for item in items:
                bundle.add(item)
            if not items:
                bundle.add_limitation(f"No existing engineering memory entries found matching '{keywords}'.")

        else:  # retrieve
            results = self.memory.retrieve_memory(limit=10)
            items = normalise_memory_result(results)
            for item in items:
                bundle.add(item)
            if not items:
                bundle.add_limitation("No stored engineering findings found in memory.")

    async def _handle_code_analysis(
        self,
        plan: QueryPlan,
        bundle: EvidenceBundle,
    ) -> None:
        target_dir = str(plan.repository_path or self.default_repo_dir)
        q = plan.raw_query.lower()

        # Select appropriate tool based on query and extracted parameters
        server_name = "code_fallback"

        if plan.function_name and any(kw in q for kw in ["caller", "callers", "who calls", "called by"]):
            tool_name = "find_callers"
            args = {"directory": target_dir, "function_name": plan.function_name}
        elif plan.function_name and any(kw in q for kw in ["callee", "callees", "calls made", "what does"]):
            tool_name = "find_callees"
            args = {"directory": target_dir, "function_name": plan.function_name}
        elif plan.function_name and any(kw in q for kw in ["impact", "affect", "change impact"]):
            tool_name = "find_change_impact"
            args = {"directory": target_dir, "function_name": plan.function_name}
        elif plan.file_path and any(kw in q for kw in ["import", "imports", "module", "depend", "dependencies"]):
            tool_name = "find_module_relationships"
            args = {"directory": target_dir, "filename": plan.file_path}
        elif any(kw in q for kw in ["class", "classes", "methods"]):
            tool_name = "find_classes"
            args = {"directory": target_dir}
        else:
            tool_name = "find_functions"
            args = {"directory": target_dir}

        result = await self.mcp.call_tool(server_name, tool_name, args)
        item = normalise_code_result(tool_name, server_name, result.text, result.is_error)
        item.file_path = plan.file_path
        item.function_name = plan.function_name
        bundle.add(item)

    async def _handle_binary_analysis(
        self,
        plan: QueryPlan,
        bundle: EvidenceBundle,
    ) -> None:
        binary_path = plan.binary_path
        if not binary_path:
            bundle.add_limitation("Binary path was not specified for analysis.")
            return

        op = plan.binary_operation or "metadata"
        server_name = "binary"

        if op == "disassemble":
            tool_name = "disassemble_binary"
            args = {"binary_path": binary_path, "max_instructions": 50}
        elif op == "functions":
            tool_name = "find_binary_functions"
            args = {"binary_path": binary_path}
        elif op == "imports":
            tool_name = "find_binary_imports"
            args = {"binary_path": binary_path}
        elif op == "strings":
            tool_name = "extract_binary_strings"
            args = {"binary_path": binary_path, "limit": 40}
        else:
            tool_name = "analyze_binary"
            args = {"binary_path": binary_path}

        result = await self.mcp.call_tool(server_name, tool_name, args)
        item = normalise_binary_result(tool_name, server_name, result.text, result.is_error)
        item.file_path = binary_path
        bundle.add(item)

    async def _handle_multi_tool(
        self,
        plan: QueryPlan,
        bundle: EvidenceBundle,
    ) -> None:
        """Run both code analysis and binary analysis or memory."""
        # 1. Code branch
        await self._handle_code_analysis(plan, bundle)

        # 2. Binary branch (if binary_path is provided)
        if plan.binary_path:
            await self._handle_binary_analysis(plan, bundle)
        else:
            bundle.add_limitation("Multi-tool query requested binary analysis, but binary path was omitted.")

        # 3. Check memory for relevant context
        if plan.function_name:
            mem_results = self.memory.search_memory(plan.function_name)
            for m in normalise_memory_result(mem_results):
                bundle.add(m)

    async def _handle_general(
        self,
        plan: QueryPlan,
        bundle: EvidenceBundle,
    ) -> None:
        # Check if memory has relevant engineering findings to anchor answer
        results = self.memory.search_memory(plan.raw_query)
        if results:
            for item in normalise_memory_result(results):
                bundle.add(item)

    # ------------------------------------------------------------------
    # Response synthesis
    # ------------------------------------------------------------------

    async def _generate_response(
        self,
        user_query: str,
        plan: QueryPlan,
        bundle: EvidenceBundle,
    ) -> str:
        """
        Generate answer via LocalLLM if available, or structured fallback if Ollama
        is not reachable or the model is not yet pulled.
        """
        system_prompt, user_prompt = build_llm_prompt(bundle)

        # Check LLM availability
        available, reason = self.llm.check_availability()
        if available:
            return self.llm.chat(
                messages=[{"role": "user", "content": user_prompt}],
                system_prompt=system_prompt,
            )

        # Graceful evidence-grounded fallback when local LLM is offline or model not pulled
        fallback_lines = [
            f"[Agent Status: Local LLM ({self.llm.model}) offline - {reason}]",
            f"Query Category: {plan.category.value.upper()}",
            "",
            "=== VERIFIED EVIDENCE ===",
        ]
        if bundle.items:
            for i, it in enumerate(bundle.items, 1):
                fallback_lines.append(f"\n[Source #{i}: {it.source}]")
                fallback_lines.append(f"Summary: {it.summary}")
                if it.detail:
                    fallback_lines.append(f"Output:\n{it.detail}")
        else:
            fallback_lines.append("No tool evidence collected.")

        if bundle.limitations:
            fallback_lines.append("\n=== LIMITATIONS ===")
            for lim in bundle.limitations:
                fallback_lines.append(f"- {lim}")

        return "\n".join(fallback_lines)

    async def close(self) -> None:
        """Clean up MCP connections."""
        await self.mcp.close_all()

