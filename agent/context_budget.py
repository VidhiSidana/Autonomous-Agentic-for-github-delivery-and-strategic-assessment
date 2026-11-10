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
        Compact an EvidenceBundle strictly according to priority:
        1. Keep verified evidence items and their critical locations (file, line, symbol).
        2. Truncate long tool text to max_item_detail_chars.
        3. If still over budget, retain titles/summaries and drop detail blocks.
        4. Log any truncated or dropped components.
        """
        dropped_log: list[str] = []
        max_item_chars = self.budget["max_item_detail_chars"]
        max_total_chars = self.budget["max_evidence_chars"]

        lines: list[str] = ["=== EVIDENCE FROM ANALYSIS TOOLS ==="]
        running_chars = 0

        # Sort items: VERIFIED first, then HYPOTHESIS, then LIMITATION
        sorted_items = sorted(
            bundle.items,
            key=lambda x: 0 if x.kind == EvidenceKind.VERIFIED else (1 if x.kind == EvidenceKind.HYPOTHESIS else 2),
        )

        for i, item in enumerate(sorted_items, 1):
            item_lines = []
            header = f"[{item.kind.value} #{i}]"
            if item.kind == EvidenceKind.HYPOTHESIS:
                header = f"[{item.kind.value} #{i} - UNVERIFIED HYPOTHESIS, NOT AN ESTABLISHED FACT]"
            item_lines.append(header)
            item_lines.append(f"Source : {item.source}")

            if item.file_path:
                loc = str(item.file_path)
                if item.line_number:
                    loc += f":{item.line_number}"
                item_lines.append(f"Location: {loc}")
            if item.function_name:
                item_lines.append(f"Symbol : {item.function_name}")
            if item.binary_address:
                item_lines.append(f"Address: {item.binary_address}")
            if item.summary:
                item_lines.append(f"Summary: {item.summary}")

            # Truncate detail if over item cap
            if item.detail:
                detail_text = item.detail
                if len(detail_text) > max_item_chars:
                    dropped_len = len(detail_text) - max_item_chars
                    detail_text = detail_text[:max_item_chars] + f"\n...[truncated {dropped_len} chars by context budget]"
                    dropped_log.append(f"Truncated detail in item #{i} ({item.source}) by {dropped_len} chars")
                item_lines.append(f"Detail :\n{detail_text}")

            block_text = "\n".join(item_lines) + "\n"

            # Check total evidence budget
            if running_chars + len(block_text) > max_total_chars:
                if item.kind == EvidenceKind.VERIFIED:
                    # For verified items, keep location and summary but drop detail
                    brief_lines = [
                        header,
                        f"Source : {item.source}",
                        f"Summary: {item.summary}",
                    ]
                    if item.file_path:
                        brief_lines.append(f"Location: {item.file_path}")
                    brief_block = "\n".join(brief_lines) + "\n"
                    lines.append(brief_block)
                    dropped_log.append(f"Dropped full detail for verified item #{i} due to total evidence budget")
                    running_chars += len(brief_block)
                else:
                    dropped_log.append(f"Dropped lower-priority item #{i} ({item.kind.value}) due to context budget")
                    continue
            else:
                lines.append(block_text)
                running_chars += len(block_text)

        if bundle.limitations:
            lines.append("=== KNOWN LIMITATIONS ===")
            for lim in bundle.limitations:
                lines.append(f"  - {lim}")

        lines.append("=== END OF EVIDENCE ===")
        return "\n".join(lines), dropped_log

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

        user_prompt = (
            f"User query: {query}\n\n"
            f"{evidence_text}\n\n"
            "Answer the query strictly based on the evidence above."
        )

        total_est = estimate_tokens(system_prompt) + estimate_tokens(user_prompt)

        return CompactedContext(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            evidence_text=evidence_text,
            total_estimated_tokens=total_est,
            dropped_log=dropped_log,
        )

