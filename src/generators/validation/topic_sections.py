from __future__ import annotations

from typing import List

from src.contracts.validation import ValidationIssue
from src.generators.artifact_generator import audit_toc_artifacts

from .models import ValidationRuntime
from .shared import ensure_dict, issue, s

RULE_ID = "toc_integrity"


def run_topic_section_rule(runtime: ValidationRuntime) -> List[ValidationIssue]:
    artifacts = ensure_dict(runtime.request.artifacts)
    if not artifacts:
        return []
    evidence_packs = (
        runtime.request.evidence_packs
        if isinstance(runtime.request.evidence_packs, dict)
        else {}
    )
    doc_map = ensure_dict(evidence_packs.get("doc_map"))
    if not doc_map:
        return []

    issues: List[ValidationIssue] = []
    for diagnostic in audit_toc_artifacts(artifacts=artifacts, doc_map=doc_map):
        status = s(diagnostic.get("status")).strip().lower()
        if status in {"", "ok"}:
            continue
        section_id = s(diagnostic.get("section_id")).strip()
        section_title = s(diagnostic.get("section_title")).strip()
        affected_section = s(diagnostic.get("affected_section")).strip() or (
            f"toc_entries:{section_id}" if section_id else "toc_entries"
        )

        if status == "missing_entries":
            message = "Artifacts are missing deterministic TOC entries."
        elif status == "missing_section":
            message = (
                f"TOC coverage is missing section '{section_title or section_id}'."
            )
        elif status == "duplicate_section":
            message = f"TOC contains duplicate coverage for section '{section_title or section_id}'."
        elif status == "unknown_section":
            message = f"TOC contains unknown section '{section_title or section_id}'."
        elif status == "out_of_order":
            message = "TOC entries are out of source-section order."
        elif status == "legacy_topics_stale":
            message = "Legacy toc_topics no longer matches deterministic TOC entries."
        elif status == "legacy_briefs_count_mismatch":
            message = "Legacy toc_topics_expanded count no longer matches deterministic TOC entries."
        elif status == "legacy_brief_invalid":
            message = f"Legacy toc_topics_expanded entry is invalid for section '{section_title or section_id}'."
        elif status.startswith("legacy_brief_"):
            message = f"Legacy toc_topics_expanded is stale for section '{section_title or section_id}'."
        elif status.startswith("stale_"):
            message = f"TOC entry is stale for section '{section_title or section_id}'."
        elif status == "empty_display_title":
            message = (
                f"TOC entry label is empty for section '{section_title or section_id}'."
            )
        elif status == "section_title_mismatch":
            message = f"TOC entry metadata conflicts with source section '{section_title or section_id}'."
        else:
            message = f"TOC integrity check failed with status '{status}'."
        issues.append(
            issue(
                rule_id=RULE_ID,
                message=message,
                severity="error",
                section=affected_section,
                repair_target="topics",
                entity_id=section_id,
            )
        )
    return issues
