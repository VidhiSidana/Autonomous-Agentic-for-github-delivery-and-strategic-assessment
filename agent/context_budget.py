"""
Context Budget Manager for Samsung PRISM Unified Engineering Agent.

Provides:
  - Model-specific token budgets (Qwen 1.5B, Phi-3.5, Llama 3.1, Mistral Nemo)
  - Strict priority compaction order when context limits are approached:
      1. System prompt + instructions (never dropped)
      2. Verified evidence (locations, line numbers, symbols preserved; tool text truncated)
      3. Memory / past findings (titles and summaries preserved; raw dumps dropped)
      4. Session history (compacted to latest turns)
      5. Tool schemas (compacted to category-relevant subset)
  - Dropped component audit logging
  - Prompt tuning helpers for evidence reliance and false-premise rejection
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from agent.evidence import EvidenceBundle, EvidenceKind

logger = logging.getLogger(__name__)


# Model context limits (in tokens)
MODEL_BUDGETS: dict[str, dict[str, int]] = {
    "qwen2.5:1.5b": {
        "context_window": 4096,
        "max_prompt_tokens": 3000,
        "max_evidence_chars": 3500,
        "max_item_detail_chars": 600,
        "max_history_turns": 2,
    },
    "phi3.5:latest": {
        "context_window": 8192,
        "max_prompt_tokens": 6500,
        "max_evidence_chars": 8000,
        "max_item_detail_chars": 1500,
        "max_history_turns": 4,
    },
    "llama3.1:8b": {
        "context_window": 16384,
        "max_prompt_tokens": 8000,
        "max_evidence_chars": 6000,
        "max_item_detail_chars": 1000,
        "max_history_turns": 4,
    },
    "mistral-nemo:12b": {
        "context_window": 32768,
        "max_prompt_tokens": 26000,
        "max_evidence_chars": 35000,
        "max_item_detail_chars": 5000,
        "max_history_turns": 10,
    },
}

DEFAULT_BUDGET = MODEL_BUDGETS["qwen2.5:1.5b"]


def estimate_tokens(text: str) -> int:
    """Fast, safe token estimation (~4 chars per token for English/code)."""
    if not text:
        return 0
    return max(1, len(text) // 4)


@dataclass
class CompactedContext:
    system_prompt: str
    user_prompt: str
    evidence_text: str
    total_estimated_tokens: int
    dropped_log: list[str] = field(default_factory=list)


class ContextBudgetManager:
    """
    Manages and compacts prompt context to prevent context window overflow
    on local small-parameter models.
    """

    def __init__(self, model_tag: str = "qwen2.5:1.5b") -> None:
        self.model_tag = model_tag
        self.budget = MODEL_BUDGETS.get(model_tag, DEFAULT_BUDGET)

    def compact_evidence_bundle(
        self,
        bundle: EvidenceBundle,
    ) -> tuple[str, list[str]]:
        """
        Compact evidence without exceeding the configured character budget.
        Verified evidence is prioritized, but even its brief representation is
        omitted when it cannot fit; the budget is a hard ceiling.
        """
        dropped_log: list[str] = []
        max_item_chars = self.budget["max_item_detail_chars"]
        max_total_chars = self.budget["max_evidence_chars"]
        lines: list[str] = []
        used_chars = 0

        sorted_items = sorted(
            bundle.items,
            key=lambda item: (
                0 if item.kind == EvidenceKind.VERIFIED
                else 1 if item.kind == EvidenceKind.HYPOTHESIS
                else 2
            ),
        )

        def append_block(block: str) -> bool:
            nonlocal used_chars
            separator = 1 if lines else 0
            cost = len(block) + separator
            if used_chars + cost > max_total_chars:
                return False
            lines.append(block)
            used_chars += cost
            return True

        for index, item in enumerate(sorted_items, 1):
            header = f"[{item.kind.value} #{index}]"
            if item.kind == EvidenceKind.HYPOTHESIS:
                header += " - UNVERIFIED HYPOTHESIS, NOT AN ESTABLISHED FACT"

            item_lines = [
                header,
                f"Source: {item.source}",
            ]
            if item.file_path:
                location = str(item.file_path)
                if item.line_number:
                    location += f":{item.line_number}"
                item_lines.append(f"Location: {location}")
            if item.function_name:
                item_lines.append(f"Symbol: {item.function_name}")
            if item.binary_address:
                item_lines.append(f"Address: {item.binary_address}")
            if item.summary:
                item_lines.append(f"Summary: {item.summary}")

            detail = item.detail or ""
            if detail and len(detail) > max_item_chars:
                removed = len(detail) - max_item_chars
                detail = detail[:max_item_chars]
                dropped_log.append(
                    f"Truncated detail in item #{index} ({item.source}) by {removed} chars"
                )
            if detail:
                item_lines.append(f"Detail:\n{detail}")

            full_block = "\n".join(item_lines)
            if append_block(full_block):
                continue

            # Retry verified evidence without its detail, retaining provenance
            # and location where possible. It still must fit the hard ceiling.
            if item.kind == EvidenceKind.VERIFIED:
                brief_lines = [
                    header,
                    f"Source: {item.source}",
                ]
                if item.file_path:
                    location = str(item.file_path)
                    if item.line_number:
                        location += f":{item.line_number}"
                    brief_lines.append(f"Location: {location}")
                if item.function_name:
                    brief_lines.append(f"Symbol: {item.function_name}")
                if item.summary:
                    brief_lines.append(f"Summary: {item.summary}")
                if append_block("\n".join(brief_lines)):
                    dropped_log.append(
                        f"Dropped detail for verified item #{index} due to total evidence budget"
                    )
                    continue

            dropped_log.append(
                f"Dropped item #{index} ({item.kind.value}) due to total evidence budget"
            )

        if bundle.limitations:
            limitation_lines = ["=== KNOWN LIMITATIONS ==="]
            for limitation in bundle.limitations:
                candidate = "\n".join(limitation_lines + [f"- {limitation}"])
                # Reserve the closing marker and never exceed the configured cap.
                closing = "=== END OF EVIDENCE ==="
                candidate_full = candidate + "\n" + closing
                if len(candidate_full) > max_total_chars:
                    dropped_log.append("Omitted limitation text due to evidence budget")
                    continue
                limitation_lines.append(f"- {limitation}")
            if len(limitation_lines) > 1:
                append_block("\n".join(limitation_lines))

        closing = "=== END OF EVIDENCE ==="
        if append_block(closing):
            return "\n".join(lines), dropped_log

        # A tiny configured budget may not fit any content plus the marker.
        # Return a bounded marker rather than silently exceeding the limit.
        if max_total_chars >= len(closing):
            return closing, dropped_log
        return closing[:max_total_chars], dropped_log

    def build_grounded_prompts(
        self,
        query: str,
        bundle: EvidenceBundle,
        system_instructions: Optional[str] = None,
    ) -> CompactedContext:
        """
        Build system prompt and user message tuned for small models with guardrails:
        - Strict reliance on provided evidence
        - Refusal when evidence is missing ('INSUFFICIENT EVIDENCE')
        - Explicit refutation of false or contradictory premises
        """
        evidence_text, dropped_log = self.compact_evidence_bundle(bundle)

        default_system = (
            "You are a Unified Engineering Agent for the Samsung PRISM project. "
            "You have access to real analysis tool results provided below.\n\n"
            "RULES:\n"
            "1. Base your answer ONLY on the provided evidence. Never invent file paths, functions, or addresses.\n"
            "2. If the evidence is insufficient to answer the question, state: 'INSUFFICIENT EVIDENCE' and explain what is missing.\n"
            "3. If the user query makes an assumption contradicted by the evidence, explicitly reject the false premise.\n"
            "4. Structure your response with FINDINGS, LIMITATIONS, and SOURCES."
        )
        system_prompt = system_instructions or default_system

        # Enforce the model's total prompt budget after reserving system
        # instructions and the user-query framing. Evidence is already ordered
        # by verification priority, so prefix truncation retains stronger items.
        query_prefix = "User query: "
        query_suffix = "\n\nAnswer the query strictly based on the evidence above."
        separator = "\n\n"
        max_chars = self.budget["max_prompt_tokens"] * 4
        query_text = query

        evidence_allowance = max(
            0,
            max_chars
            - len(system_prompt)
            - len(query_prefix)
            - len(query_text)
            - len(separator)
            - len(query_suffix),
        )
        if len(evidence_text) > evidence_allowance:
            evidence_text = evidence_text[:evidence_allowance]
            dropped_log.append(
                "Truncated evidence to satisfy the total model prompt-token budget"
            )

        query_allowance = max(
            0,
            max_chars
            - len(system_prompt)
            - len(query_prefix)
            - len(separator)
            - len(evidence_text)
            - len(query_suffix),
        )
        if len(query_text) > query_allowance:
            query_text = query_text[:query_allowance]
            dropped_log.append(
                "Truncated user query to satisfy the total model prompt-token budget"
            )

        user_prompt = (
            f"{query_prefix}{query_text}{separator}"
            f"{evidence_text}{query_suffix}"
        )

        total_est = estimate_tokens(system_prompt) + estimate_tokens(user_prompt)

        return CompactedContext(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            evidence_text=evidence_text,
            total_estimated_tokens=total_est,
            dropped_log=dropped_log,
        )

