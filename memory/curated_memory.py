"""
Curated Memory Manager for the Samsung PRISM Unified Engineering Agent.

Handles:
  - Markdown-based curated memory in memory/curated/
  - YAML frontmatter metadata (id, title, category, status, evidence_refs, date, confirmed_by)
  - Two-way sync: SQLite <-> Markdown (import / export)
  - Dual-layer deduplication (normalised text hash + word-level Jaccard similarity)
  - Stale detection (identifies missing/renamed files or symbols)
  - Strict secret redaction on all write paths
"""

import hashlib
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agent.policy import redact_secrets
from config.settings import PROJECT_ROOT
from memory.memory import (
    EngineeringMemory,
    STATUS_CONFIRMED,
    STATUS_HYPOTHESIS,
    STATUS_NEEDS_REVIEW,
    STATUS_PROPOSED,
    STATUS_REJECTED,
    STATUS_VERIFIED,
)

logger = logging.getLogger(__name__)

CURATED_DIR_DEFAULT = PROJECT_ROOT / "memory" / "curated"


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def compute_jaccard_similarity(text1: str, text2: str) -> float:
    """Compute word-level Jaccard similarity between two texts."""
    w1 = set(re.findall(r"\w+", text1.lower()))
    w2 = set(re.findall(r"\w+", text2.lower()))
    if not w1 or not w2:
        return 1.0 if w1 == w2 else 0.0
    return len(w1 & w2) / len(w1 | w2)


def compute_normalised_hash(text: str) -> str:
    """SHA-256 hash of normalised (lower-case alphanumeric token) text."""
    tokens = re.findall(r"\w+", text.lower())
    normalised = " ".join(tokens)
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()


class CuratedMemoryManager:
    """
    Manages curated memory stored as Markdown files with YAML frontmatter.
    Synchronizes losslessly with SQLite EngineeringMemory.
    """

    def __init__(
        self,
        memory: Optional[EngineeringMemory] = None,
        curated_dir: Optional[Path] = None,
        project_root: Optional[Path] = None,
    ) -> None:
        self.memory = memory or EngineeringMemory()
        self.curated_dir = Path(curated_dir or CURATED_DIR_DEFAULT)
        self.curated_dir.mkdir(parents=True, exist_ok=True)
        self.project_root = Path(project_root or PROJECT_ROOT)

    # ------------------------------------------------------------------
    # Markdown Serialization Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _slugify(text: str) -> str:
        slug = re.sub(r"[^\w\s-]", "", text.lower()).strip()
        slug = re.sub(r"[-\s]+", "_", slug)
        return slug[:40] or "finding"

    @staticmethod
    def serialize_finding_to_markdown(finding: dict[str, Any]) -> str:
        """Render a finding dict into Markdown with YAML frontmatter."""
        metadata = {
            "id": finding.get("id"),
            "title": redact_secrets(finding.get("title", "")),
            "category": finding.get("category", "engineering_finding"),
            "status": finding.get("verification_status", STATUS_VERIFIED),
            "evidence_refs": redact_secrets(finding.get("evidence_refs", "")),
            "date": finding.get("created_at") or _now_utc(),
            "confirmed_by": redact_secrets(finding.get("confirmed_by", "")),
        }
        clean_content = redact_secrets(finding.get("content", ""))
        frontmatter = yaml.safe_dump(metadata, sort_keys=False).strip()
        return f"---\n{frontmatter}\n---\n\n{clean_content.strip()}\n"

    @staticmethod
    def parse_markdown_finding(file_content: str) -> tuple[dict[str, Any], str]:
        """Parse YAML frontmatter and body content from Markdown text."""
        match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", file_content, re.DOTALL)
        if match:
            raw_meta, body = match.group(1), match.group(2)
            try:
                meta = yaml.safe_load(raw_meta) or {}
            except Exception as e:
                logger.warning("Error parsing YAML frontmatter: %s", e)
                meta = {}
            return meta, body.strip()
        # Fallback if no frontmatter delimiters
        return {}, file_content.strip()

    # ------------------------------------------------------------------
    # Export SQLite -> Markdown
    # ------------------------------------------------------------------

    def export_curated_memory(
        self,
        verification_statuses: Optional[set[str]] = None,
    ) -> list[Path]:
        """
        Export findings from SQLite to Markdown files in curated_dir.
        Defaults to exporting CONFIRMED and VERIFIED findings.
        Applies secret redaction to all exported content.
        """
        statuses = verification_statuses or {STATUS_CONFIRMED, STATUS_VERIFIED, STATUS_NEEDS_REVIEW}
        exported_files: list[Path] = []

        all_findings = self.memory.retrieve_memory(limit=500, include_stale=False, include_proposed=True)
        for row in all_findings:
            f_dict = dict(row)
            status = f_dict.get("verification_status", "")
            if status not in statuses:
                continue

            f_id = f_dict.get("id")
            slug = self._slugify(f_dict.get("title", "finding"))
            file_name = f"{f_id:03d}_{slug}.md" if isinstance(f_id, int) else f"{slug}.md"
            file_path = self.curated_dir / file_name

            md_text = self.serialize_finding_to_markdown(f_dict)
            file_path.write_text(md_text, encoding="utf-8")
            exported_files.append(file_path)

        return exported_files

    # ------------------------------------------------------------------
    # Import Markdown -> SQLite
    # ------------------------------------------------------------------

    def import_curated_memory(self) -> dict[str, int]:
        """
        Import or re-synchronize edited Markdown files from curated_dir back to SQLite.
        Detects modifications or new files and losslessly syncs them.
        """
        stats = {"imported": 0, "updated": 0, "unchanged": 0, "total": 0}

        for md_file in sorted(self.curated_dir.glob("*.md")):
            stats["total"] += 1
            text = md_file.read_text(encoding="utf-8")
            meta, body = self.parse_markdown_finding(text)

            meta_id = meta.get("id")
            title = redact_secrets(meta.get("title") or md_file.stem)
            category = meta.get("category", "engineering_finding")
            status = meta.get("status", STATUS_CONFIRMED)
            evidence_refs = redact_secrets(str(meta.get("evidence_refs") or ""))
            confirmed_by = redact_secrets(str(meta.get("confirmed_by") or ""))
            clean_body = redact_secrets(body)

            existing_row = self.memory.get_memory_by_id(int(meta_id)) if meta_id is not None else None

            if existing_row:
                # Compare to detect changes
                curr = dict(existing_row)
                changed = (
                    curr.get("title") != title
                    or curr.get("content") != clean_body
                    or curr.get("category") != category
                    or curr.get("verification_status") != status
                    or curr.get("evidence_refs") != evidence_refs
                    or curr.get("confirmed_by") != confirmed_by
                )
                if changed:
                    self.memory.update_memory(
                        memory_id=curr["id"],
                        title=title,
                        content=clean_body,
                        category=category,
                        verification_status=status,
                    )
                    # Also update confirmation/refs in SQLite
                    with self.memory._connection() as conn:
                        conn.execute(
                            """
                            UPDATE findings
                            SET evidence_refs = ?, confirmed_by = ?
                            WHERE id = ?
                            """,
                            (evidence_refs, confirmed_by, curr["id"]),
                        )
                    stats["updated"] += 1
                else:
                    stats["unchanged"] += 1
            else:
                # Insert new finding
                res = self.memory.save_memory(
                    title=title,
                    content=clean_body,
                    category=category,
                    verification_status=status,
                    evidence_refs=evidence_refs,
                    confirmed_by=confirmed_by,
                )
                if res.get("saved"):
                    stats["imported"] += 1
                else:
                    stats["unchanged"] += 1

        return stats

    # ------------------------------------------------------------------
    # Dual-layer Deduplication
    # ------------------------------------------------------------------

    def check_duplicate(
        self,
        title: str,
        content: str,
        jaccard_threshold: float = 0.8,
    ) -> Optional[dict[str, Any]]:
        """
        Check both SQLite and curated Markdown files for duplicates.
        Matches if normalised hash matches or word Jaccard similarity >= threshold.
        """
        clean_title = redact_secrets(title)
        clean_content = redact_secrets(content)
        query_hash = compute_normalised_hash(f"{clean_title} {clean_content}")

        # Check SQLite layer
        all_findings = self.memory.retrieve_memory(limit=500, include_stale=True, include_proposed=True)
        for row in all_findings:
            f = dict(row)
            row_text = f"{f.get('title', '')} {f.get('content', '')}"
            if compute_normalised_hash(row_text) == query_hash:
                return {"layer": "sqlite", "id": f["id"], "title": f["title"], "reason": "exact_hash"}
            sim = compute_jaccard_similarity(f"{clean_title} {clean_content}", row_text)
            if sim >= jaccard_threshold:
                return {"layer": "sqlite", "id": f["id"], "title": f["title"], "reason": f"jaccard_{sim:.2f}"}

        # Check Markdown layer
        for md_file in self.curated_dir.glob("*.md"):
            try:
                meta, body = self.parse_markdown_finding(md_file.read_text(encoding="utf-8"))
                file_text = f"{meta.get('title', '')} {body}"
                if compute_normalised_hash(file_text) == query_hash:
                    return {"layer": "markdown", "file": str(md_file), "title": meta.get("title", ""), "reason": "exact_hash"}
                sim = compute_jaccard_similarity(f"{clean_title} {clean_content}", file_text)
                if sim >= jaccard_threshold:
                    return {"layer": "markdown", "file": str(md_file), "title": meta.get("title", ""), "reason": f"jaccard_{sim:.2f}"}
            except Exception:
                pass

        return None

    # ------------------------------------------------------------------
    # Stale Detection
    # ------------------------------------------------------------------

    def detect_stale_findings(self) -> list[dict[str, Any]]:
        """
        Inspect findings to check whether referenced files or symbols still exist.
        If a file referenced in evidence_refs or content no longer exists on disk,
        the finding is marked as stale in SQLite.
        """
        stale_findings: list[dict[str, Any]] = []
        findings = self.memory.retrieve_memory(limit=500, include_stale=False, include_proposed=True)

        for row in findings:
            f = dict(row)
            f_id = f["id"]
            refs = f.get("evidence_refs", "")
            content = f.get("content", "")

            # Extract referenced files: e.g. "tool:agent/main.py:100" or "File: agent/main.py"
            referenced_paths: list[str] = []
            for part in refs.split(":"):
                if "/" in part or "\\" in part or part.endswith((".py", ".json", ".md", ".exe", ".bin")):
                    referenced_paths.append(part.strip())

            for line in content.splitlines():
                if line.startswith("File:") or "path:" in line.lower():
                    _, _, p = line.partition(":")
                    candidate = p.strip()
                    if candidate and candidate != "Not specified":
                        referenced_paths.append(candidate)

            is_stale = False
            missing_target = ""

            for ref_path in referenced_paths:
                p = Path(ref_path)
                # Check absolute or relative to project_root
                if not p.is_absolute():
                    p = self.project_root / p
                if not p.exists():
                    is_stale = True
                    missing_target = str(ref_path)
                    break

            if is_stale:
                self.memory.mark_stale(f_id)
                stale_findings.append({
                    "id": f_id,
                    "title": f["title"],
                    "missing_target": missing_target,
                })

        return stale_findings

