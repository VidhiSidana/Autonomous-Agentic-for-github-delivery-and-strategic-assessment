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

        # Step 1: Query Understanding & Planning
        plan = self.planner.plan(user_query)
        self.session_mgr.on_query(session_id, user_query, intent=getattr(plan, "category", None).value if getattr(plan, "category", None) else "")

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
        
        # Automatically persist verified analysis findings.
       # Automatically persist verified analysis findings.
                # Automatically persist verified analysis findings.
        if plan.category in (
            QueryCategory.CODE_ANALYSIS,
            QueryCategory.BINARY_ANALYSIS,
            QueryCategory.MULTI_TOOL,
        ):
            saved_count = self._save_verified_findings(
                evidence_bundle,
                plan,
            )

            if saved_count:
                print(
                    f"[Memory] Automatically saved {saved_count} finding(s)."
                )

        # Step 4: Evidence Synthesis via Local LLM
        response_text = await self._generate_response(
            user_query,
            plan,
            evidence_bundle,
        )

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
    # Automatic engineering memory retrieval
    # ------------------------------------------------------------------

    def _add_relevant_memory(
        self,
        query: str,
        bundle: EvidenceBundle,
    ) -> None:
        """Retrieve relevant past engineering findings for the current query."""

        try:
            results = self.memory.search_memory(query)

            if results:
                items = normalise_memory_result(results, keyword=query)

                for item in items:
                    bundle.add(item)

                logger.info(
                    "Retrieved %d relevant memory entries.",
                    len(items),
                )

        except Exception as exc:
            logger.warning(
                "Memory retrieval failed: %s",
                exc,
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

    async def _resolve_code_graph_project(self, target_dir: str) -> Optional[str]:
        """Find or create an indexed project in codebase-memory-mcp."""
        if "code_graph" not in self.mcp.available_servers():
            return None
        try:
            lp_res = await self.mcp.call_tool("code_graph", "list_projects", {})
            if lp_res.success and lp_res.text:
                for line in lp_res.text.splitlines():
                    parts = line.strip().split()
                    if parts and not parts[0].startswith("projects:") and not parts[0].startswith("total:"):
                        return parts[0]
            # Index if none found
            idx_res = await self.mcp.call_tool("code_graph", "index_repository", {"repo_path": target_dir})
            if idx_res.success and idx_res.text:
                try:
                    data = json.loads(idx_res.text)
                    return data.get("project")
                except Exception:
                    pass
        except Exception as e:
            logger.debug("code_graph project lookup failed: %s", e)
        return None

    def _find_compatible_tool(
        self,
        tools_with_schemas: dict[str, Any],
        intent: str,
    ) -> Optional[tuple[str, dict[str, Any]]]:
        """
        Dynamically map an intended operation to an available MCP tool by analyzing
        tool names, descriptions, and input schemas.
        """
        for name, info in tools_with_schemas.items():
            desc = (info.get("description") or "").lower()
            name_lower = name.lower()
            schema = info.get("inputSchema") or {}

            if intent == "symbol_search":
                if any(k in name_lower for k in ["search", "find", "symbol", "query"]) and \
                   any(k in desc for k in ["symbol", "graph", "bm25", "query", "code", "definition", "find"]):
                    return name, schema

            elif intent == "trace_callers":
                if any(k in name_lower for k in ["trace", "call", "path", "caller"]) and \
                   any(k in desc for k in ["caller", "inbound", "path", "call"]):
                    return name, schema

            elif intent == "trace_callees":
                if any(k in name_lower for k in ["trace", "call", "path", "callee"]) and \
                   any(k in desc for k in ["callee", "outbound", "path", "call"]):
                    return name, schema

            elif intent == "architecture":
                if any(k in name_lower for k in ["architecture", "overview", "structure", "graph"]) and \
                   any(k in desc for k in ["architecture", "component", "structure", "overview", "schema"]):
                    return name, schema

        return None

    def _build_and_validate_tool_args(
        self,
        tool_name: str,
        schema: dict[str, Any],
        project_name: Optional[str] = None,
        symbol_or_query: Optional[str] = None,
        file_path: Optional[str] = None,
        direction: Optional[str] = None,
    ) -> tuple[bool, dict[str, Any], str]:
        """
        Dynamically map inputs to the schema's accepted properties and ensure
        all required properties are satisfied.
        """
        props = schema.get("properties", {})
        required = schema.get("required", [])
        args: dict[str, Any] = {}

        # Map project parameter
        for p_key in ["project", "project_name", "repo", "repo_path"]:
            if p_key in props and project_name:
                args[p_key] = project_name
                break

        # Map query / symbol parameter
        for q_key in ["query", "function_name", "pattern", "symbol", "name"]:
            if q_key in props and symbol_or_query:
                args[q_key] = symbol_or_query
                break

        # Map file path parameter
        for f_key in ["file_path", "path", "filename", "file"]:
            if f_key in props and file_path:
                args[f_key] = file_path
                break

        # Map direction parameter
        if "direction" in props and direction:
            args["direction"] = direction

        # Optional boolean flags (e.g. include_tests)
        if "include_tests" in props:
            args["include_tests"] = True

        missing = [r for r in required if r not in args]
        if missing:
            return False, {}, f"Tool '{tool_name}' schema missing required argument(s): {missing}"

        return True, args, ""

    async def _handle_code_analysis(
        self,
        plan: QueryPlan,
        bundle: EvidenceBundle,
    ) -> None:
        target_dir = str(plan.repository_path or self.default_repo_dir)
        q = plan.raw_query.lower()
        memory_query = plan.function_name or plan.file_path or plan.raw_query
        self._add_relevant_memory(memory_query, bundle)
        # Step 1: Try Tree-sitter Code Knowledge Graph (codebase-memory-mcp) dynamically
        graph_used = False
        project_name = await self._resolve_code_graph_project(target_dir)

        if project_name:
            try:
                tools_with_schemas = await self.mcp.list_tools_with_schemas("code_graph")

                if plan.function_name:
                    # Dynamically discover and validate symbol search tool
                    matched_search = self._find_compatible_tool(tools_with_schemas, "symbol_search")
                    first_qn = None
                    if matched_search:
                        tool_name, schema = matched_search
                        valid, args, err = self._build_and_validate_tool_args(
                            tool_name=tool_name,
                            schema=schema,
                            project_name=project_name,
                            symbol_or_query=plan.function_name,
                        )
                        if valid:
                            sr = await self.mcp.call_tool("code_graph", tool_name, args)
                            if sr.success and "results: 0" not in sr.text:
                                item = normalise_code_result(tool_name, "code_graph", sr.text, sr.is_error)
                                item.function_name = plan.function_name
                                for line in sr.text.splitlines():
                                    parts = line.strip().split()
                                    if len(parts) >= 2 and parts[1] in ("Method", "Function", "Constructor"):
                                        first_qn = parts[0]
                                        if len(parts) >= 3 and ("/" in parts[2] or "." in parts[2]):
                                            item.file_path = parts[2]
                                        break
                                item.file_path = item.file_path or plan.file_path
                                bundle.add(item)
                                graph_used = True
                        else:
                            bundle.add_limitation(f"Dynamic schema validation failed for symbol search: {err}")
                    else:
                        bundle.add_limitation("No compatible symbol search tool discovered on codebase-memory-mcp server.")

                    # Dynamically discover and validate caller/callee tracing tool
                    is_caller_query = any(kw in q for kw in ["caller", "callers", "who calls", "called by", "that call", "calling", "calls "])
                    is_callee_query = any(kw in q for kw in ["callee", "callees", "calls made", "what does"])
                    if is_caller_query or is_callee_query:
                        intent = "trace_callers" if is_caller_query else "trace_callees"
                        matched_trace = self._find_compatible_tool(tools_with_schemas, intent)
                        if matched_trace:
                            tool_name, schema = matched_trace
                            target_fn = first_qn or plan.function_name
                            direction = "inbound" if is_caller_query else "outbound"
                            valid, args, err = self._build_and_validate_tool_args(
                                tool_name=tool_name,
                                schema=schema,
                                project_name=project_name,
                                symbol_or_query=target_fn,
                                direction=direction,
                            )
                            if valid:
                                tr = await self.mcp.call_tool("code_graph", tool_name, args)
                                if tr.success and "ambiguous" not in tr.text and "not found" not in tr.text:
                                    item = normalise_code_result(f"{tool_name} ({direction})", "code_graph", tr.text, tr.is_error)
                                    item.function_name = plan.function_name
                                    item.file_path = item.file_path or plan.file_path
                                    bundle.add(item)
                                    graph_used = True
                            else:
                                bundle.add_limitation(f"Dynamic schema validation failed for path tracing: {err}")
                        else:
                            bundle.add_limitation(f"No compatible caller/callee tracing tool discovered for intent '{intent}'.")

                elif any(kw in q for kw in ["architecture", "overview", "components"]):
                    matched_arch = self._find_compatible_tool(tools_with_schemas, "architecture")
                    if matched_arch:
                        tool_name, schema = matched_arch
                        valid, args, err = self._build_and_validate_tool_args(
                            tool_name=tool_name,
                            schema=schema,
                            project_name=project_name,
                        )
                        if valid:
                            res = await self.mcp.call_tool("code_graph", tool_name, args)
                            if res.success:
                                bundle.add(normalise_code_result(tool_name, "code_graph", res.text, res.is_error))
                                graph_used = True
                        else:
                            bundle.add_limitation(f"Dynamic schema validation failed for architecture overview: {err}")
                    else:
                        bundle.add_limitation("No compatible architecture tool discovered on codebase-memory-mcp server.")

            except Exception as exc:
                logger.debug("Code graph query failed: %s", exc)

        # Step 2: Fallback to local AST server if code_graph was not used
        if not graph_used:
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
            item.file_path = item.file_path or plan.file_path
            item.function_name = item.function_name or plan.function_name
            bundle.add(item)

    async def _handle_binary_analysis(
        self,
        plan: QueryPlan,
        bundle: EvidenceBundle,
    ) -> None:
        binary_path = plan.binary_path
        memory_query = binary_path or plan.raw_query
        self._add_relevant_memory(memory_query, bundle)
        if not binary_path:
            bundle.add_limitation("Binary path was not specified for analysis.")
            return

        op = plan.binary_operation or "metadata"
        server_name = "binary"

        if op == "rea_status":
            tool_name = "query_rea_status"
            args = {"binary_path": binary_path}
        elif op == "disassemble":
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
    
    def _save_verified_findings(
        self,
        bundle: EvidenceBundle,
        plan: QueryPlan,
    ) -> int:
        """
        Automatically save verified code/binary analysis findings.
        Never save hypotheses, limitations, or previously retrieved memories.
        """
        saved_count = 0

        for item in bundle.verified_items:
            # Skip evidence that originated from memory retrieval.
            if item.server_name == "memory" or "engineering_memory" in item.source:
                continue

            # Only save evidence returned by actual analysis tools.
            if not item.tool_name:
                continue

            title = item.summary.strip()
            if not title:
                continue

            content = (
                f"Finding: {item.summary}\n"
                f"Source: {item.source}\n"
                f"Tool: {item.tool_name}\n"
                f"File: {item.file_path or 'Not specified'}\n"
                f"Line: {item.line_number or 'Not specified'}\n"
                f"Function: {item.function_name or 'Not specified'}\n"
                f"Details:\n{item.detail[:3000]}"
            )

            ref_parts = []
            if item.tool_name:
                ref_parts.append(item.tool_name)
            if item.file_path:
                ref_parts.append(str(item.file_path))
            if item.line_number:
                ref_parts.append(str(item.line_number))
            evidence_refs = ":".join(ref_parts)

            # Record tool result hook in session events
            self.session_mgr.on_tool_result(
                session_id=self.session_mgr.current_session_id or "",
                tool_name=item.tool_name,
                args={"file_path": item.file_path, "line": item.line_number, "function": item.function_name},
                success=True,
                evidence_refs=evidence_refs,
                result_summary=item.summary,
            )

            try:
                result = self.memory.save_memory(
                    title=title,
                    content=content,
                    category="engineering_finding",
                    verification_status="VERIFIED",
                    source=item.source,
                    project=str(plan.repository_path or self.default_repo_dir),
                    session_id=self.session_mgr.current_session_id or "",
                    confidence=0.9,
                    evidence_refs=evidence_refs,
                )

                if result.get("saved"):
                    saved_count += 1

            except Exception as exc:
                print(f"[Memory] Could not save finding: {exc}")

        return saved_count

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
        Applies context budgeting and compact grounded prompts.
        """
        from agent.context_budget import ContextBudgetManager
        budget_mgr = ContextBudgetManager(model_tag=self.llm.model)
        compacted = budget_mgr.build_grounded_prompts(user_query, bundle)
        system_prompt, user_prompt = compacted.system_prompt, compacted.user_prompt

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

