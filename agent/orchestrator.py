
"""
Consolidated Agent Orchestrator for the Samsung PRISM Unified Engineering Agent.

Coordinates:
1. Query understanding and planning.
2. Policy validation and authorization.
3. MCP tool invocation across named servers.
4. Persistent engineering memory.
5. Multi-session lifecycle management.
6. Evidence normalization and aggregation.
7. Evidence-grounded local LLM response generation.
"""

import json
import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from agent.evidence import (
    EvidenceBundle,
    EvidenceItem,
    EvidenceKind,
    normalise_binary_result,
    normalise_code_result,
    normalise_memory_result,
)
from agent.llm import LocalLLM
from agent.mcp_client import MCPClientManager
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
    prompt_tokens: int = 0
    eval_tokens: int = 0
    total_tokens: int = 0


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

        if not self.session_mgr.current_session_id:
            self.session_mgr.start_session()

    async def process_query(
        self,
        user_query: str,
        overrides: Optional[dict[str, Any]] = None,
    ) -> OrchestrationResult:
        """
        Process a query:
        Plan -> Tool Selection -> MCP Execution -> Evidence -> Response.
        """
        overrides = overrides or {}
        session_id = self.session_mgr.current_session_id or "unknown"

        plan = self.planner.plan(user_query)

        category = getattr(plan, "category", None)
        self.session_mgr.on_query(
            session_id,
            user_query,
            intent=category.value if category else "",
        )

        for key, value in overrides.items():
            if hasattr(plan, key) and value is not None:
                setattr(plan, key, value)

        # A CLI clarification is answered in a second turn by supplying
        # the missing parameter as an override. Clear the planner's stale
        # clarification state once the required value is present.
        if (
            plan.category == QueryCategory.BINARY_ANALYSIS
            and overrides.get("binary_path")
        ):
            plan.clarification_needed = False
            plan.clarification_question = None
        elif (
            plan.category == QueryCategory.CODE_ANALYSIS
            and overrides.get("function_name")
        ):
            plan.clarification_needed = False
            plan.clarification_question = None

        if plan.clarification_needed:
            bundle = EvidenceBundle(query=user_query)
            bundle.add_limitation(
                plan.clarification_question or "Parameter missing."
            )

            return OrchestrationResult(
                query=user_query,
                category=plan.category.value,
                plan=plan,
                evidence_bundle=bundle,
                response_text=(
                    plan.clarification_question
                    or "Please clarify your request."
                ),
                clarification_needed=True,
                clarification_question=plan.clarification_question,
                session_id=session_id,
            )

        evidence_bundle = EvidenceBundle(query=user_query)

        try:
            if plan.category == QueryCategory.MEMORY:
                await self._handle_memory(
                    plan, evidence_bundle, session_id
                )

            elif plan.category == QueryCategory.CODE_ANALYSIS:
                await self._handle_code_analysis(
                    plan, evidence_bundle
                )

            elif plan.category == QueryCategory.BINARY_ANALYSIS:
                await self._handle_binary_analysis(
                    plan, evidence_bundle
                )

            elif plan.category == QueryCategory.MULTI_TOOL:
                await self._handle_multi_tool(
                    plan, evidence_bundle
                )

            elif plan.category == QueryCategory.GENERAL:
                await self._handle_general(
                    plan, evidence_bundle
                )

        except Exception as exc:
            logger.error(
                "Error during tool execution: %s",
                exc,
                exc_info=True,
            )
            evidence_bundle.add_limitation(
                f"Tool execution exception: {exc}"
            )

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
                logger.info(
                    "Automatically saved %d finding(s).",
                    saved_count,
                )

            self._record_hypothesis_findings(
                evidence_bundle,
                plan,
                session_id,
            )

        response_text = await self._generate_response(
            user_query,
            plan,
            evidence_bundle,
        )

        token_meta = getattr(self, "_last_token_meta", {}) or {}
        prompt_tokens = token_meta.get("prompt_eval_count") or 0
        eval_tokens = token_meta.get("eval_count") or 0

        return OrchestrationResult(
            query=user_query,
            category=plan.category.value,
            plan=plan,
            evidence_bundle=evidence_bundle,
            response_text=response_text,
            session_id=session_id,
            prompt_tokens=prompt_tokens,
            eval_tokens=eval_tokens,
            total_tokens=prompt_tokens + eval_tokens,
        )

    # ---------------------------------------------------------
    # Engineering memory retrieval
    # ---------------------------------------------------------

    def _add_relevant_memory(
        self,
        query: str,
        bundle: EvidenceBundle,
    ) -> None:
        """Retrieve relevant past engineering findings."""

        try:
            results = self.memory.search_memory(query)

            if results:
                items = normalise_memory_result(
                    results,
                    keyword=query,
                )

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

    async def _handle_memory(
        self,
        plan: QueryPlan,
        bundle: EvidenceBundle,
        session_id: str,
    ) -> None:
        """Handle save, search, and retrieve memory operations."""

        operation = plan.memory_operation or "retrieve"

        # Executable/DLL memory lookups must not mix unrelated findings.
        binary_match = re.search(
            r"([A-Za-z0-9_.-]+\.(?:exe|dll))",
            plan.raw_query,
            re.IGNORECASE,
        )
        if binary_match and operation != "save":
            binary_name = binary_match.group(1)
            results = self.memory.search_memory(
                binary_name,
                category="binary_finding",
            )
            items = normalise_memory_result(results, keyword=binary_name)
            for item in items:
                bundle.add(item)
            if not items:
                bundle.add_limitation(
                    "No verified binary memory findings were found "
                    f"for '{binary_name}'."
                )
            return

        if operation == "save":
            title = plan.memory_title or plan.raw_query[:50]
            content = plan.memory_content or plan.raw_query
            # Never promote an unlabelled user assertion to a verified fact.
            status = plan.memory_verification_status or "PROPOSED"

            save_result = self.memory.save_memory(
                title=title,
                content=content,
                category=plan.memory_category or "technical_finding",
                verification_status=status,
                session_id=session_id,
            )

            bundle.add(
                EvidenceItem(
                    kind=(
                        EvidenceKind.VERIFIED
                        if status == "VERIFIED"
                        else EvidenceKind.HYPOTHESIS
                    ),
                    source="engineering_memory.save",
                    summary=save_result.get(
                        "message",
                        "Memory recorded.",
                    ),
                    detail=f"Title: {title}\nStatus: {status}",
                )
            )

        elif operation == "search":
            keywords = (
                " ".join(plan.memory_keywords)
                if plan.memory_keywords
                else plan.raw_query
            )

            results = self.memory.search_memory(keywords)
            items = normalise_memory_result(
                results,
                keyword=keywords,
            )

            for item in items:
                bundle.add(item)

            if not items:
                bundle.add_limitation(
                    f"No existing engineering memory entries found "
                    f"matching '{keywords}'."
                )

        else:
            results = self.memory.retrieve_memory(limit=10)
            items = normalise_memory_result(results)

            for item in items:
                bundle.add(item)

            if not items:
                bundle.add_limitation(
                    "No stored engineering findings found in memory."
                )

    # ---------------------------------------------------------
    # Code Graph project resolution
    # ---------------------------------------------------------

    async def _resolve_code_graph_project(
        self,
        target_dir: str,
    ) -> Optional[str]:
        """Find or create an indexed Code Graph project."""

        if "code_graph" not in self.mcp.available_servers():
            return None

        try:
            result = await self.mcp.call_tool(
                "code_graph",
                "list_projects",
                {},
                session_id=self.session_mgr.current_session_id or "unknown",
            )

            if result.success and result.text:
                for line in result.text.splitlines():
                    parts = line.strip().split()

                    if (
                        parts
                        and not parts[0].startswith("projects:")
                        and not parts[0].startswith("total:")
                    ):
                        return parts[0]

            index_result = await self.mcp.call_tool(
                "code_graph",
                "index_repository",
                {"repo_path": target_dir},
                session_id=self.session_mgr.current_session_id or "unknown",
            )

            if index_result.success and index_result.text:
                try:
                    data = json.loads(index_result.text)

                    if isinstance(data, dict):
                        return data.get("project")

                except (json.JSONDecodeError, TypeError):
                    logger.debug(
                        "Could not parse Code Graph indexing response."
                    )

        except Exception as exc:
            logger.debug(
                "Code Graph project lookup failed: %s",
                exc,
            )

        return None

    # ---------------------------------------------------------
    # Dynamic MCP tool discovery
    # ---------------------------------------------------------

    def _find_compatible_tool(
        self,
        tools_with_schemas: dict[str, Any],
        intent: str,
    ) -> Optional[tuple[str, dict[str, Any]]]:
        """
        Dynamically map an intended operation to an MCP tool
        using tool names and descriptions.
        """

        for name, info in tools_with_schemas.items():
            if not isinstance(info, dict):
                continue

            description = (
                info.get("description") or ""
            ).lower()

            name_lower = name.lower()

            schema = (
                info.get("inputSchema")
                or info.get("input_schema")
                or {}
            )

            # Prefer the exact Code Graph tracing tool.
            if (
                intent in ("trace_callers", "trace_callees")
                and name_lower == "trace_path"
            ):
                return name, schema

            if intent == "symbol_search":
                if (
                    any(
                        word in name_lower
                        for word in (
                            "search",
                            "find",
                            "symbol",
                            "query",
                        )
                    )
                    and any(
                        word in description
                        for word in (
                            "symbol",
                            "graph",
                            "bm25",
                            "query",
                            "code",
                            "definition",
                            "find",
                        )
                    )
                ):
                    return name, schema

            elif intent == "trace_callers":
                if (
                    any(
                        word in name_lower
                        for word in (
                            "trace",
                            "call",
                            "path",
                            "caller",
                        )
                    )
                    and any(
                        word in description
                        for word in (
                            "caller",
                            "inbound",
                            "path",
                            "call",
                        )
                    )
                ):
                    return name, schema

            elif intent == "trace_callees":
                if (
                    any(
                        word in name_lower
                        for word in (
                            "trace",
                            "call",
                            "path",
                            "callee",
                        )
                    )
                    and any(
                        word in description
                        for word in (
                            "callee",
                            "outbound",
                            "path",
                            "call",
                        )
                    )
                ):
                    return name, schema

            elif intent == "architecture":
                if (
                    any(
                        word in name_lower
                        for word in (
                            "architecture",
                            "overview",
                            "structure",
                            "graph",
                        )
                    )
                    and any(
                        word in description
                        for word in (
                            "architecture",
                            "component",
                            "structure",
                            "overview",
                            "schema",
                        )
                    )
                ):
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
        """Map inputs to accepted schema parameters and validate them."""

        props = schema.get("properties", {})
        required = schema.get("required", [])
        args: dict[str, Any] = {}

        for key in (
            "project",
            "project_name",
            "repo",
            "repo_path",
        ):
            if key in props and project_name:
                args[key] = project_name
                break

        for key in (
            "name_pattern",
            "function_name",
            "pattern",
            "symbol",
            "name",
            "query",
        ):
            if key in props and symbol_or_query:
                args[key] = symbol_or_query
                break

        for key in (
            "file_path",
            "path",
            "filename",
            "file",
        ):
            if key in props and file_path:
                args[key] = file_path
                break

        if "direction" in props and direction:
            args["direction"] = direction

        if "include_tests" in props:
            args["include_tests"] = True

        missing = [
            key
            for key in required
            if key not in args
        ]

        if missing:
            return (
                False,
                {},
                f"Tool '{tool_name}' schema missing required "
                f"argument(s): {missing}",
            )

        return True, args, ""

    @staticmethod
    def _should_use_architecture_tool(plan: QueryPlan, query_lower: str) -> bool:
        """Avoid substituting a broad architecture summary for precise AST queries."""
        if plan.function_name:
            return False

        module_terms = (
            "import", "imports", "module", "depend", "dependencies",
        )
        if plan.file_path and any(term in query_lower for term in module_terms):
            return False

        function_inventory_terms = (
            "function", "functions", "list functions", "function discovery",
        )
        if not plan.file_path and any(
            term in query_lower for term in function_inventory_terms
        ):
            return False

        return True

    # ---------------------------------------------------------
    # Code analysis
    # ---------------------------------------------------------

    async def _handle_code_analysis(
        self,
        plan: QueryPlan,
        bundle: EvidenceBundle,
    ) -> None:
        target_dir = str(
            plan.repository_path or self.default_repo_dir
        )

        query_lower = plan.raw_query.lower()

        memory_query = (
            plan.function_name
            or plan.file_path
            or plan.raw_query
        )

        self._add_relevant_memory(
            memory_query,
            bundle,
        )

        graph_used = False

        project_name = await self._resolve_code_graph_project(
            target_dir
        )

        if project_name:
            try:
                tools = await self.mcp.list_tools_with_schemas(
                    "code_graph"
                )

                from agent.tool_router import (
                    filter_available_tools_for_category,
                )

                tools = filter_available_tools_for_category(
                    plan.category.value,
                    tools,
                )

                if plan.function_name:
                    matched_search = self._find_compatible_tool(
                        tools,
                        "symbol_search",
                    )

                    if matched_search:
                        search_tool, search_schema = matched_search

                        valid, search_args, error = (
                            self._build_and_validate_tool_args(
                                tool_name=search_tool,
                                schema=search_schema,
                                project_name=project_name,
                                symbol_or_query=(
                                    plan.function_name.rsplit(".", 1)[-1]
                                ),
                            )
                        )

                        if valid:
                            if (
                                "format"
                                in search_schema.get("properties", {})
                            ):
                                search_args["format"] = "json"

                            search_result = await self.mcp.call_tool(
                                "code_graph",
                                search_tool,
                                search_args,
                                session_id=self.session_mgr.current_session_id or "unknown",
                            )

                            if (
                                search_result.success
                                and "results: 0" not in search_result.text
                            ):
                                item = normalise_code_result(
                                    search_tool,
                                    "code_graph",
                                    search_result.text,
                                    search_result.is_error,
                                )

                                item.function_name = plan.function_name

                                target_qns = []

                                try:
                                    graph_data = json.loads(
                                        search_result.text
                                    )

                                    if not isinstance(graph_data, dict):
                                        raise ValueError(
                                            "Symbol search response "
                                            "is not a JSON object."
                                        )

                                    requested_name = (
                                        plan.function_name
                                        .strip()
                                        .strip(".")
                                    )

                                    requested_short_name = (
                                        requested_name
                                        .split(".")[-1]
                                        .casefold()
                                    )

                                    requested_file = (
                                        (plan.file_path or "")
                                        .replace("\\", "/")
                                        .casefold()
                                        .lstrip("./")
                                    )

                                    exact_matches = []
                                    short_matches = []

                                    groups = graph_data.get("groups", [])

                                    if not isinstance(groups, list):
                                        groups = []

                                    for group in groups:
                                        if not isinstance(group, dict):
                                            continue

                                        prefix = str(
                                            group.get("qn_prefix", "")
                                        ).strip(".")

                                        source_file = str(
                                            group.get("file") or ""
                                        ).replace("\\", "/")

                                        normalized_file = (
                                            source_file
                                            .casefold()
                                            .lstrip("./")
                                        )

                                        if (
                                            requested_file
                                            and normalized_file
                                            != requested_file
                                        ):
                                            continue

                                        rows = group.get("rows", [])

                                        if not isinstance(rows, list):
                                            continue

                                        for row in rows:
                                            if (
                                                not isinstance(
                                                    row,
                                                    (list, tuple),
                                                )
                                                or not row
                                            ):
                                                continue

                                            symbol_name = str(
                                                row[0]
                                            ).strip()

                                            qualified_name = (
                                                f"{prefix}.{symbol_name}"
                                                if prefix
                                                else symbol_name
                                            )

                                            if (
                                                symbol_name.casefold()
                                                != requested_short_name
                                            ):
                                                continue

                                            short_matches.append(
                                                qualified_name
                                            )

                                            if (
                                                qualified_name.casefold()
                                                == requested_name.casefold()
                                                or qualified_name.casefold().endswith(
                                                    "."
                                                    + requested_name.casefold()
                                                )
                                            ):
                                                exact_matches.append(
                                                    qualified_name
                                                )

                                    if "." in requested_name:
                                        target_qns = list(
                                            dict.fromkeys(exact_matches)
                                        )
                                    else:
                                        target_qns = list(
                                            dict.fromkeys(short_matches)
                                        )

                                except (
                                    json.JSONDecodeError,
                                    AttributeError,
                                    TypeError,
                                    ValueError,
                                ):
                                    logger.debug(
                                        "Could not parse Code Graph "
                                        "symbol-search JSON.",
                                        exc_info=True,
                                    )

                                item.file_path = (
                                    item.file_path or plan.file_path
                                )

                                bundle.add(item)

                                is_caller_query = any(
                                    phrase in query_lower
                                    for phrase in (
                                        "caller",
                                        "callers",
                                        "who calls",
                                        "called by",
                                        "that call",
                                        "calling",
                                        "calls ",
                                    )
                                )

                                is_callee_query = any(
                                    phrase in query_lower
                                    for phrase in (
                                        "callee",
                                        "callees",
                                        "calls made",
                                        "what does",
                                    )
                                )

                                if is_caller_query or is_callee_query:
                                    intent = (
                                        "trace_callers"
                                        if is_caller_query
                                        else "trace_callees"
                                    )

                                    matched_trace = (
                                        self._find_compatible_tool(
                                            tools,
                                            intent,
                                        )
                                    )

                                    direction = (
                                        "inbound"
                                        if is_caller_query
                                        else "outbound"
                                    )

                                    trace_succeeded = False

                                    if matched_trace and target_qns:
                                        trace_tool, trace_schema = (
                                            matched_trace
                                        )

                                        for target_function in target_qns:
                                            valid, trace_args, error = (
                                                self._build_and_validate_tool_args(
                                                    tool_name=trace_tool,
                                                    schema=trace_schema,
                                                    project_name=project_name,
                                                    symbol_or_query=target_function,
                                                    direction=direction,
                                                )
                                            )

                                            if not valid:
                                                bundle.add_limitation(
                                                    "Path tracing validation "
                                                    f"failed for {target_function}: "
                                                    f"{error}"
                                                )
                                                continue

                                            if (
                                                "format"
                                                in trace_schema.get(
                                                    "properties",
                                                    {},
                                                )
                                            ):
                                                trace_args["format"] = "json"

                                            if (
                                                "depth"
                                                in trace_schema.get(
                                                    "properties",
                                                    {},
                                                )
                                            ):
                                                trace_args["depth"] = 2

                                            trace_result = (
                                                await self.mcp.call_tool(
                                                    "code_graph",
                                                    trace_tool,
                                                    trace_args,
                                                    session_id=self.session_mgr.current_session_id or "unknown",
                                                )
                                            )

                                            if (
                                                not trace_result.success
                                                or trace_result.is_error
                                            ):
                                                bundle.add_limitation(
                                                    "Code Graph tracing "
                                                    f"failed for {target_function}: "
                                                    f"{trace_result.text}"
                                                )
                                                continue

                                            trace_item = (
                                                normalise_code_result(
                                                    f"{trace_tool} ({direction})",
                                                    "code_graph",
                                                    trace_result.text,
                                                    trace_result.is_error,
                                                )
                                            )

                                            trace_item.function_name = (
                                                target_function
                                            )

                                            trace_item.file_path = (
                                                trace_item.file_path
                                                or plan.file_path
                                            )

                                            bundle.add(trace_item)

                                            if (
                                                trace_item.kind
                                                == EvidenceKind.VERIFIED
                                            ):
                                                trace_succeeded = True

                                    elif not matched_trace:
                                        bundle.add_limitation(
                                            "No compatible caller/callee "
                                            "tracing tool discovered for "
                                            f"intent '{intent}'."
                                        )

                                    else:
                                        bundle.add_limitation(
                                            "No exact Code Graph definition "
                                            f"matched '{plan.function_name}'."
                                        )

                                    graph_used = trace_succeeded

                                else:
                                    graph_used = True

                # Class/method outline queries use local AST analysis.
                wants_class_outline = any(
                    phrase in query_lower
                    for phrase in (
                        "class",
                        "classes",
                        "methods",
                        "class outline",
                    )
                )

                if (
                    not wants_class_outline
                    and self._should_use_architecture_tool(
                        plan,
                        query_lower,
                    )
                ):
                    matched_arch = self._find_compatible_tool(
                        tools,
                        "architecture",
                    )

                    if matched_arch:
                        architecture_tool, architecture_schema = (
                            matched_arch
                        )

                        valid, args, error = (
                            self._build_and_validate_tool_args(
                                tool_name=architecture_tool,
                                schema=architecture_schema,
                                project_name=project_name,
                            )
                        )

                        if valid:
                            result = await self.mcp.call_tool(
                                "code_graph",
                                architecture_tool,
                                args,
                                session_id=self.session_mgr.current_session_id or "unknown",
                            )

                            if result.success and not result.is_error:
                                bundle.add(
                                    normalise_code_result(
                                        architecture_tool,
                                        "code_graph",
                                        result.text,
                                        result.is_error,
                                    )
                                )
                                graph_used = True

                        else:
                            bundle.add_limitation(
                                "Dynamic schema validation failed for "
                                f"architecture overview: {error}"
                            )

            except Exception as exc:
                logger.debug(
                    "Code Graph query failed: %s",
                    exc,
                    exc_info=True,
                )

        # Local AST fallback.
        if not graph_used:
            server_name = "code_fallback"

            if plan.function_name and any(
                phrase in query_lower
                for phrase in (
                    "caller",
                    "callers",
                    "who calls",
                    "called by",
                )
            ):
                tool_name = "find_callers"
                args = {
                    "directory": target_dir,
                    "function_name": plan.function_name,
                }

            elif plan.function_name and any(
                phrase in query_lower
                for phrase in (
                    "callee",
                    "callees",
                    "calls made",
                    "what does",
                )
            ):
                tool_name = "find_callees"
                args = {
                    "directory": target_dir,
                    "function_name": plan.function_name,
                }

            elif plan.function_name and any(
                phrase in query_lower
                for phrase in (
                    "impact",
                    "affect",
                    "change impact",
                )
            ):
                tool_name = "find_change_impact"
                args = {
                    "directory": target_dir,
                    "function_name": plan.function_name,
                }

            elif plan.file_path and any(
                phrase in query_lower
                for phrase in (
                    "import",
                    "imports",
                    "module",
                    "depend",
                    "dependencies",
                )
            ):
                tool_name = "find_module_relationships"
                args = {
                    "directory": target_dir,
                    "filename": plan.file_path,
                }

            elif any(
                phrase in query_lower
                for phrase in (
                    "class",
                    "classes",
                    "methods",
                )
            ):
                tool_name = "find_classes"
                args = {"directory": target_dir}

            else:
                tool_name = "find_functions"
                args = {"directory": target_dir}

            result = await self.mcp.call_tool(
                server_name,
                tool_name,
                args,
                session_id=self.session_mgr.current_session_id or "unknown",
            )

            item = normalise_code_result(
                tool_name,
                server_name,
                result.text,
                result.is_error,
            )

            item.file_path = item.file_path or plan.file_path
            item.function_name = (
                item.function_name or plan.function_name
            )

            bundle.add(item)

    # ---------------------------------------------------------
    # Binary analysis
    # ---------------------------------------------------------

    async def _handle_binary_analysis(
        self,
        plan: QueryPlan,
        bundle: EvidenceBundle,
    ) -> None:
        binary_path = plan.binary_path

        memory_query = binary_path or plan.raw_query

        self._add_relevant_memory(
            memory_query,
            bundle,
        )

        if not binary_path:
            bundle.add_limitation(
                "Binary path was not specified for analysis."
            )
            return

        # Validate binary path before analysis.
        allowed, reason = authorize_binary_path(binary_path)

        if not allowed:
            bundle.add_limitation(
                f"Binary analysis denied by policy: {reason}"
            )
            return

        operation = plan.binary_operation or "metadata"

        if operation == "rea_status":
            tool_name = "query_rea_status"
            args = {"binary_path": binary_path}

        elif operation == "disassemble":
            tool_name = "disassemble_binary"
            args = {
                "binary_path": binary_path,
                "max_instructions": 50,
            }

        elif operation == "functions":
            tool_name = "find_binary_functions"
            args = {"binary_path": binary_path}

        elif operation == "imports":
            tool_name = "find_binary_imports"
            args = {"binary_path": binary_path}

        elif operation == "strings":
            tool_name = "extract_binary_strings"
            args = {
                "binary_path": binary_path,
                "limit": 40,
            }

        else:
            tool_name = "analyze_binary"
            args = {"binary_path": binary_path}

        result = await self.mcp.call_tool(
            "binary",
            tool_name,
            args,
            session_id=self.session_mgr.current_session_id or "unknown",
        )

        item = normalise_binary_result(
            tool_name,
            "binary",
            result.text,
            result.is_error,
        )

        item.file_path = binary_path
        bundle.add(item)

    # ---------------------------------------------------------
    # Multi-tool analysis
    # ---------------------------------------------------------

    async def _handle_multi_tool(
        self,
        plan: QueryPlan,
        bundle: EvidenceBundle,
    ) -> None:
        """Run code, binary, and memory analysis."""

        await self._handle_code_analysis(
            plan,
            bundle,
        )

        if plan.binary_path:
            await self._handle_binary_analysis(
                plan,
                bundle,
            )
        else:
            bundle.add_limitation(
                "Multi-tool query requested binary analysis, "
                "but binary path was omitted."
            )

        if plan.function_name:
            results = self.memory.search_memory(
                plan.function_name
            )

            for item in normalise_memory_result(results):
                bundle.add(item)

    async def _handle_general(
        self,
        plan: QueryPlan,
        bundle: EvidenceBundle,
    ) -> None:
        """Retrieve relevant memory for general queries."""

        results = self.memory.search_memory(
            plan.raw_query
        )

        if results:
            for item in normalise_memory_result(results):
                bundle.add(item)

    # ---------------------------------------------------------
    # Verified finding persistence
    # ---------------------------------------------------------

    def _save_verified_findings(
        self,
        bundle: EvidenceBundle,
        plan: QueryPlan,
    ) -> int:
        """
        Save verified code/binary findings.

        Never save hypotheses, limitations, or retrieved memories.
        """

        saved_count = 0

        for item in bundle.verified_items:
            if (
                item.server_name == "memory"
                or "engineering_memory" in item.source
            ):
                continue

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

            reference_parts = [item.tool_name]

            if item.file_path:
                reference_parts.append(str(item.file_path))

            if item.line_number:
                reference_parts.append(str(item.line_number))

            evidence_refs = ":".join(reference_parts)

            session_id = (
                self.session_mgr.current_session_id or ""
            )

            self.session_mgr.on_tool_result(
                session_id=session_id,
                tool_name=item.tool_name,
                args={
                    "file_path": item.file_path,
                    "line": item.line_number,
                    "function": item.function_name,
                },
                success=True,
                evidence_refs=evidence_refs,
                result_summary=item.summary,
            )

            try:
                result = self.memory.save_memory(
                    title=title,
                    content=content,
                    category=(
                        "binary_finding"
                        if item.server_name == "binary"
                        else "technical_finding"
                    ),
                    verification_status="VERIFIED",
                    source=item.source,
                    project=str(
                        plan.repository_path or self.default_repo_dir
                    ),
                    session_id=session_id,
                    confidence=0.9,
                    evidence_refs=evidence_refs,
                )

                if result.get("saved"):
                    saved_count += 1

            except Exception as exc:
                logger.warning(
                    "Could not save finding: %s",
                    exc,
                )

        return saved_count

    def _record_hypothesis_findings(
        self,
        bundle: EvidenceBundle,
        plan: QueryPlan,
        session_id: str,
    ) -> int:
        """Record hypothesis evidence separately from verified facts."""

        proposed_count = 0

        for item in bundle.hypothesis_items:
            if not item.summary.strip():
                continue

            try:
                self.memory.propose_finding(
                    title=f"[Hypothesis] {item.summary[:60]}",
                    content=(
                        f"Proposed Hypothesis:\n{item.summary}\n"
                        f"Detail:\n{item.detail}"
                    ),
                    evidence_refs=item.source,
                    session_id=session_id,
                )

                proposed_count += 1

            except Exception as exc:
                logger.debug(
                    "Failed to record hypothesis finding: %s",
                    exc,
                )

        return proposed_count

    # ---------------------------------------------------------
    # Response generation
    # ---------------------------------------------------------

    async def _generate_response(
        self,
        user_query: str,
        plan: QueryPlan,
        bundle: EvidenceBundle,
    ) -> str:
        """
        Generate an evidence-grounded response using the local LLM.

        Caller/callee queries receive deterministic graph answers.
        Other queries use compacted evidence-grounded prompts.
        """

        # Evidence validation.
        if plan.category in (
            QueryCategory.CODE_ANALYSIS,
            QueryCategory.BINARY_ANALYSIS,
            QueryCategory.MULTI_TOOL,
            QueryCategory.MEMORY,
        ):
            if not bundle.has_verified:
                limitation_summary = (
                    "; ".join(bundle.limitations)
                    if bundle.limitations
                    else "No verified findings available."
                )

                return (
                    f"INSUFFICIENT EVIDENCE: {limitation_summary}"
                )

            stop_words = {
                "what", "which", "where", "who", "when", "why",
                "how", "is", "are", "was", "were", "the", "a", "an",
                "in", "to", "and", "or", "of", "for", "with", "this",
                "that", "these", "tell", "me", "show", "find", "check",
                "confirm", "whether", "used", "build", "report",
                "inspect", "analyse", "analyze", "binary", "file",
                "codebase", "repository", "does", "do", "did",
            }

            query_tokens = set(
                re.findall(r"\w+", user_query.lower())
            )

            content_tokens = {
                token
                for token in query_tokens - stop_words
                if len(token) >= 3
                and not token.endswith(
                    (".exe", ".bin", ".py")
                )
            }

            if content_tokens:
                evidence_text = " ".join(
                    (
                        f"{item.summary} {item.detail} "
                        f"{item.file_path or ''} "
                        f"{item.function_name or ''} "
                        f"{item.binary_address or ''}"
                    )
                    for item in bundle.verified_items
                ).lower()

                matched_terms = [
                    token
                    for token in content_tokens
                    if token in evidence_text
                ]

                if not matched_terms:
                    missing_terms = ", ".join(
                        sorted(content_tokens)
                    )

                    return (
                        "INSUFFICIENT EVIDENCE: The collected empirical "
                        "evidence contains no data regarding: "
                        f"{missing_terms}."
                    )

        # Detect caller/callee queries.
        query_lower = user_query.lower()

        is_caller_query = any(
            phrase in query_lower
            for phrase in (
                "caller",
                "callers",
                "who calls",
                "called by",
                "that call",
                "calling",
            )
        )

        is_callee_query = any(
            phrase in query_lower
            for phrase in (
                "callee",
                "callees",
                "calls made",
                "what does",
            )
        )

        # Deterministic Code Graph response.
        if is_caller_query or is_callee_query:
            expected_key = (
                "callers"
                if is_caller_query
                else "callees"
            )

            trace_item = next(
                (
                    item
                    for item in bundle.verified_items
                    if "trace_path" in (
                        item.tool_name or ""
                    ).lower()
                    and item.raw_output
                ),
                None,
            )

            if trace_item:
                try:
                    trace_data = json.loads(
                        trace_item.raw_output
                    )

                    if not isinstance(trace_data, dict):
                        raise ValueError(
                            "Trace response is not a JSON object."
                        )

                    relationship_data = trace_data.get(
                        expected_key
                    )

                    if isinstance(relationship_data, dict):
                        entries = []
                        seen = set()

                        groups = relationship_data.get(
                            "groups",
                            [],
                        )

                        if not isinstance(groups, list):
                            groups = []

                        for group in groups:
                            if not isinstance(group, dict):
                                continue

                            prefix = str(
                                group.get("qn_prefix", "")
                            ).strip(".")

                            rows = group.get("rows", [])

                            if not isinstance(rows, list):
                                continue

                            for row in rows:
                                if (
                                    not isinstance(
                                        row,
                                        (list, tuple),
                                    )
                                    or not row
                                ):
                                    continue

                                name = str(row[0]).strip()

                                if not name:
                                    continue

                                qualified_name = (
                                    f"{prefix}.{name}"
                                    if prefix
                                    else name
                                )

                                hop = None

                                if len(row) > 1:
                                    try:
                                        hop = int(row[1])
                                    except (ValueError, TypeError):
                                        pass

                                is_test = False

                                if len(row) > 2:
                                    test_value = row[2]

                                    is_test = (
                                        test_value is True
                                        or (
                                            isinstance(
                                                test_value,
                                                str,
                                            )
                                            and test_value.strip().lower()
                                            in {
                                                "true",
                                                "1",
                                                "yes",
                                            }
                                        )
                                        or (
                                            isinstance(
                                                test_value,
                                                int,
                                            )
                                            and not isinstance(
                                                test_value,
                                                bool,
                                            )
                                            and test_value == 1
                                        )
                                    )

                                entry = (
                                    hop,
                                    qualified_name,
                                    is_test,
                                )

                                if entry not in seen:
                                    entries.append(entry)
                                    seen.add(entry)

                        direct = [
                            entry
                            for entry in entries
                            if entry[0] == 1
                        ]

                        indirect = [
                            entry
                            for entry in entries
                            if (
                                entry[0] is not None
                                and entry[0] >= 2
                            )
                        ]

                        unknown_hop = [
                            entry
                            for entry in entries
                            if (
                                entry[0] is None
                                or entry[0] < 1
                            )
                        ]

                        target = trace_data.get(
                            "function",
                            trace_item.function_name
                            or "Unknown function",
                        )

                        total = relationship_data.get(
                            "total",
                            trace_data.get(
                                f"{expected_key}_total",
                                len(entries),
                            ),
                        )

                        relation = relationship_data.get(
                            "total_relation",
                            trace_data.get(
                                f"{expected_key}_total_relation",
                                "eq",
                            ),
                        )

                        def format_entries(items):
                            if not items:
                                return ["- None reported"]

                            formatted = []

                            for hop, name, is_test in items:
                                hop_label = (
                                    f"hop {hop}"
                                    if hop is not None and hop >= 1
                                    else "hop unknown"
                                )

                                test_label = (
                                    ", test"
                                    if is_test
                                    else ""
                                )

                                formatted.append(
                                    f"- {name} "
                                    f"({hop_label}{test_label})"
                                )

                            return formatted

                        relationship_label = (
                            "Callers"
                            if is_caller_query
                            else "Callees"
                        )

                        answer_lines = [
                            "=== FINDINGS ===",
                            f"Target function: {target}",
                            (
                                f"Relationship type: "
                                f"{relationship_label}"
                            ),
                            "",
                            "Direct relationships (hop 1):",
                            *format_entries(direct),
                            "",
                            (
                                "Indirect relationships "
                                "(hop 2 or greater):"
                            ),
                            *format_entries(indirect),
                            "",
                            (
                                "Relationships with unknown "
                                "hop depth:"
                            ),
                            *format_entries(unknown_hop),
                            "",
                            (
                                f"Code Graph reported {total} "
                                f"{expected_key} ({relation})."
                            ),
                            "",
                            (
                                "Note: Entries marked 'test' belong "
                                "to test code. Hop numbers describe "
                                "graph distance, not source-code "
                                "line numbers."
                            ),
                            "",
                            "=== SOURCES ===",
                            (
                                f"Code Graph MCP tool: "
                                f"{trace_item.tool_name}"
                            ),
                        ]

                        if bundle.limitations:
                            answer_lines.extend([
                                "",
                                "=== LIMITATIONS ===",
                                *[
                                    f"- {limitation}"
                                    for limitation in bundle.limitations
                                ],
                            ])

                        return "\n".join(answer_lines)

                except (
                    json.JSONDecodeError,
                    ValueError,
                    TypeError,
                    KeyError,
                    AttributeError,
                ) as exc:
                    logger.warning(
                        "Could not build deterministic relationship "
                        "answer: %s",
                        exc,
                    )

        # Context budgeting.
        from agent.context_budget import ContextBudgetManager

        budget_manager = ContextBudgetManager(
            model_tag=self.llm.model
        )

        compacted = budget_manager.build_grounded_prompts(
            user_query,
            bundle,
        )

        system_prompt = compacted.system_prompt
        user_prompt = compacted.user_prompt

        # Local LLM.
        available, reason = self.llm.check_availability()

        if available:
            content, metadata = self.llm.chat_with_metadata(
                messages=[
                    {
                        "role": "user",
                        "content": user_prompt,
                    }
                ],
                system_prompt=system_prompt,
            )

            self._last_token_meta = metadata
            return content

        # Offline fallback.
        fallback_lines = [
            (
                f"[Agent Status: Local LLM ({self.llm.model}) "
                f"offline - {reason}]"
            ),
            f"Query Category: {plan.category.value.upper()}",
            "",
            "=== VERIFIED EVIDENCE ===",
        ]

        if bundle.items:
            for index, item in enumerate(
                bundle.items,
                1,
            ):
                fallback_lines.append(
                    f"\n[Source #{index}: {item.source}]"
                )

                fallback_lines.append(
                    f"Summary: {item.summary}"
                )

                if item.detail:
                    fallback_lines.append(
                        f"Output:\n{item.detail}"
                    )

        else:
            fallback_lines.append(
                "No tool evidence collected."
            )

        if bundle.limitations:
            fallback_lines.append(
                "\n=== LIMITATIONS ==="
            )

            for limitation in bundle.limitations:
                fallback_lines.append(
                    f"- {limitation}"
                )

        return "\n".join(fallback_lines)

    async def close(self) -> None:
        """Clean up MCP connections."""

        await self.mcp.close_all()

