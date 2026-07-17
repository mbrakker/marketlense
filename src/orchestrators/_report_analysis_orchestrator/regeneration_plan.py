"""Validation issue to artifact-regeneration target mapping.

This module owns deterministic regeneration-plan construction and grounding
lookup used by the report-analysis validation repair loop.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

from src.contracts.regeneration import (
    RegenerationIssue,
    RegenerationPlan,
    RegenerationTarget,
)
from src.contracts.validation import ValidationIssue
from src.utils.errors import AppError

__all__ = [
    "BROAD_TARGETS",
    "RULE_ID_RE",
    "TARGET_ORDER",
    "_build_regeneration_plan",
    "_build_target",
    "_issue_grounding",
    "_normalize_regeneration_issue",
    "_target_prompt_namespaces",
    "_target_section",
    "_target_steps",
]


def _target_section(affected_section: str) -> str:
    section = str(affected_section or "").strip().lower()
    if not section:
        return ""
    if (
        section.startswith("topics")
        or section.startswith("toc_entries")
        or section.startswith("toc_topics")
        or section.startswith("toc_topics_expanded")
    ):
        return "topics"
    if section in {"tldr", "executive_summary", "claim_evidence_map"}:
        return "summary"
    if section.startswith("summary"):
        return "summary"
    if section.startswith("insights"):
        return "insights_bundle"
    if section.startswith("key_data_insights"):
        return "insights_bundle"
    if section.startswith("claims_list"):
        return "insights_bundle"
    if section.startswith("quotes"):
        return "quotes"
    if section.startswith("expert_comment"):
        return "expert_comment"
    if section.startswith("linkedin_post"):
        return "linkedin_post"
    return ""


def _lookup_insight_grounding(
    insight_id: str,
    artifacts: Dict[str, Any],
) -> tuple[List[str], List[int]]:
    insight_id = str(insight_id or "").split(".", 1)[0].strip()
    evidence_ids: List[str] = []
    pages: List[int] = []
    for key in ("insights_final", "insights_candidates"):
        for entry in artifacts.get(key) or []:
            if not isinstance(entry, dict):
                continue
            entry_id = str(entry.get("id") or "").strip()
            if insight_id and entry_id != insight_id:
                continue
            evidence_id = str(entry.get("evidence_id") or "").strip()
            if evidence_id and evidence_id not in evidence_ids:
                evidence_ids.append(evidence_id)
            for page in entry.get("pages") or []:
                if isinstance(page, int) and page not in pages:
                    pages.append(page)
            if insight_id:
                break
    return evidence_ids, pages


def _lookup_topic_grounding(
    topic_index: str,
    artifacts: Dict[str, Any],
) -> tuple[List[str], List[int]]:
    evidence_ids: List[str] = []
    pages: List[int] = []
    toc_entries = artifacts.get("toc_entries") or []
    if isinstance(toc_entries, list) and toc_entries:
        for entry in toc_entries:
            if not isinstance(entry, dict):
                continue
            section_id = str(entry.get("section_id") or "").strip()
            if topic_index and not topic_index.isdigit() and section_id != topic_index:
                continue
            if section_id and section_id not in evidence_ids:
                evidence_ids.append(section_id)
            for page in entry.get("pages") or []:
                if isinstance(page, int) and page not in pages:
                    pages.append(page)
            if topic_index and not topic_index.isdigit():
                return evidence_ids, pages
    topic_briefs = artifacts.get("toc_topics_expanded") or []
    resolved_index = int(topic_index) - 1 if topic_index.isdigit() else -1
    for idx, entry in enumerate(topic_briefs):
        if not isinstance(entry, dict):
            continue
        if resolved_index >= 0 and idx != resolved_index:
            continue
        section_id = str(entry.get("section_id") or "").strip()
        if section_id and section_id not in evidence_ids:
            evidence_ids.append(section_id)
        for page in entry.get("pages") or []:
            if isinstance(page, int) and page not in pages:
                pages.append(page)
        if resolved_index >= 0:
            break
    return evidence_ids, pages


def _issue_grounding(
    affected_section: str,
    artifacts: Dict[str, Any],
) -> tuple[List[str], List[int]]:
    section = str(affected_section or "").strip()
    if not section:
        return [], []
    lower_section = section.lower()
    if (
        lower_section.startswith("topics")
        or lower_section.startswith("toc_entries")
        or lower_section.startswith("toc_topics")
        or lower_section.startswith("toc_topics_expanded")
    ):
        topic_index = section.split(":", 1)[1].strip() if ":" in section else ""
        return _lookup_topic_grounding(topic_index, artifacts)
    if lower_section in {
        "tldr",
        "executive_summary",
        "claim_evidence_map",
    } or lower_section.startswith("summary"):
        evidence_ids: List[str] = []
        pages: List[int] = []
        summary_value = artifacts.get("summary")
        summary = summary_value if isinstance(summary_value, dict) else {}
        for claim in summary.get("claim_evidence_map") or []:
            if not isinstance(claim, dict):
                continue
            evidence_id = str(claim.get("evidence_id") or "").strip()
            if evidence_id and evidence_id not in evidence_ids:
                evidence_ids.append(evidence_id)
            for page in claim.get("pages") or []:
                if isinstance(page, int) and page not in pages:
                    pages.append(page)
        return evidence_ids, pages
    if lower_section.startswith("insights"):
        insight_id = section.split(":", 1)[1].strip() if ":" in section else ""
        return _lookup_insight_grounding(insight_id, artifacts)
    if lower_section.startswith("quotes"):
        quote_id = section.split(":", 1)[1].strip() if ":" in section else ""
        return _lookup_quote_grounding(quote_id, artifacts)
    return [], []


RULE_ID_RE = re.compile(r"^\[([^\]]+)\]")


def _extract_rule_id(message: str) -> str:
    match = RULE_ID_RE.match(str(message or "").strip())
    if match:
        return str(match.group(1)).strip().lower()
    return "unknown"


TARGET_ORDER = [
    "topics",
    "summary",
    "insights_bundle",
    "quotes",
    "expert_comment",
    "linkedin_post",
]


BROAD_TARGETS = [
    "summary",
    "insights_bundle",
    "quotes",
    "expert_comment",
    "linkedin_post",
]

SUPPORTED_TARGETS = set(TARGET_ORDER)

REGENERATION_SEVERITY_ORDER = {"error": 0, "warning": 1}

RULE_TARGETS = {
    "claim_support": ["summary"],
    "metrics": ["insights_bundle"],
    "quotes": ["quotes"],
    "semantic": ["insights_bundle", "quotes"],
}

NUMBER_RULE_TARGETS = ["summary", "expert_comment", "linkedin_post"]


def _normalize_regeneration_issue(
    issue: ValidationIssue,
    artifacts: Dict[str, Any],
) -> RegenerationIssue:
    evidence_ids, pages = _issue_grounding(issue.affected_section, artifacts)
    return RegenerationIssue(
        rule_id=issue.rule_id or _extract_rule_id(issue.message),
        affected_section=issue.affected_section,
        message=issue.message,
        severity=issue.severity,
        repair_target=issue.repair_target,
        entity_id=issue.entity_id,
        evidence_ids=evidence_ids,
        pages=pages,
    )


def _target_steps(target_key: str) -> List[str]:
    if target_key == "topics":
        return ["toc_entries", "toc_topics", "toc_topics_expanded"]
    if target_key == "summary":
        return ["summary"]
    if target_key == "insights_bundle":
        return ["insights_candidates", "insights_final"]
    if target_key == "quotes":
        return ["quotes"]
    if target_key == "expert_comment":
        return ["expert_comment"]
    if target_key == "linkedin_post":
        return ["linkedin_post"]
    return []


def _target_prompt_namespaces(target_key: str) -> List[str]:
    if target_key == "topics":
        return []
    if target_key == "summary":
        return ["report_vs/artifacts/regenerate/summary"]
    if target_key == "insights_bundle":
        return [
            "report_vs/artifacts/regenerate/insights_candidates",
            "report_vs/artifacts/regenerate/insights_final",
        ]
    if target_key == "quotes":
        return ["report_vs/artifacts/regenerate/quotes"]
    if target_key == "expert_comment":
        return ["report_vs/artifacts/regenerate/expert_comment"]
    if target_key == "linkedin_post":
        return ["report_vs/artifacts/regenerate/linkedin_post"]
    return []


def _lookup_quote_grounding(
    quote_id: str,
    artifacts: Dict[str, Any],
) -> tuple[List[str], List[int]]:
    evidence_ids: List[str] = []
    pages: List[int] = []
    quotes = artifacts.get("quotes_final") or []
    for idx, entry in enumerate(quotes):
        if not isinstance(entry, dict):
            continue
        candidate_ids = {
            str(entry.get("id") or "").strip(),
            str(entry.get("evidence_id") or "").strip(),
            str(idx + 1),
        }
        if quote_id and quote_id not in candidate_ids:
            continue
        evidence_id = str(entry.get("evidence_id") or "").strip()
        if evidence_id and evidence_id not in evidence_ids:
            evidence_ids.append(evidence_id)
        page = entry.get("page")
        if isinstance(page, int) and page not in pages:
            pages.append(page)
        if quote_id:
            break
    return evidence_ids, pages


def _build_target(
    target_key: str,
    issues: List[RegenerationIssue],
) -> RegenerationTarget:
    ordered_issues = sorted(
        issues,
        key=lambda issue: (
            REGENERATION_SEVERITY_ORDER.get(str(issue.severity).lower(), 99),
            issue.rule_id,
            issue.affected_section,
        ),
    )
    return RegenerationTarget(
        target_section=target_key,
        regenerate_steps=_target_steps(target_key),
        prompt_namespaces=_target_prompt_namespaces(target_key),
        issues=ordered_issues,
    )


def _build_regeneration_plan(
    *,
    issues: List[ValidationIssue],
    artifacts: Dict[str, Any],
    broad_retry_available: bool,
) -> RegenerationPlan:
    grouped: Dict[str, List[RegenerationIssue]] = {}
    unmappable: List[RegenerationIssue] = []
    public_editorial_abstention = False
    for issue in issues:
        if str(issue.severity or "").strip().lower() not in REGENERATION_SEVERITY_ORDER:
            continue
        normalized = _normalize_regeneration_issue(issue, artifacts)
        if (
            normalized.rule_id.startswith("public_editorial_quality.")
            and not str(normalized.repair_target).strip()
        ):
            # A deterministic blocker without retained grounding must remain
            # blocked; it must never trigger broad regeneration or invented copy.
            unmappable.append(normalized)
            public_editorial_abstention = True
            continue
        target_keys = _target_keys_for_issue(normalized)
        if target_keys:
            for target_key in target_keys:
                grouped.setdefault(target_key, []).append(normalized)
        else:
            unmappable.append(normalized)
    if grouped:
        targets = [
            _build_target(target_key, grouped[target_key])
            for target_key in TARGET_ORDER
            if target_key in grouped
        ]
        return RegenerationPlan(
            mode="targeted",
            targets=targets,
            unmappable_issues=unmappable,
            broad_retry_allowed=broad_retry_available,
        )
    if public_editorial_abstention:
        return RegenerationPlan(
            mode="skip",
            targets=[],
            unmappable_issues=unmappable,
            broad_retry_allowed=False,
        )
    if unmappable and broad_retry_available:
        return RegenerationPlan(
            mode="broad",
            targets=[
                _build_target(target_key, list(unmappable))
                for target_key in BROAD_TARGETS
            ],
            unmappable_issues=unmappable,
            broad_retry_allowed=False,
        )
    return RegenerationPlan(
        mode="skip",
        targets=[],
        unmappable_issues=unmappable,
        broad_retry_allowed=False,
    )


def _target_keys_for_issue(issue: RegenerationIssue) -> List[str]:
    explicit_target = str(issue.repair_target or "").strip()
    if explicit_target:
        if explicit_target not in SUPPORTED_TARGETS:
            raise AppError(
                code="regeneration_repair_target_unsupported",
                message="Validation issue requested an unsupported regeneration repair target",
                retryable=False,
                severity="error",
                context={
                    "repair_target": explicit_target,
                    "rule_id": issue.rule_id,
                    "affected_section": issue.affected_section,
                },
            )
        return [explicit_target]
    section_target = _target_section(issue.affected_section)
    if section_target:
        return [section_target]
    return _rule_targets_for_issue(issue)


def _rule_targets_for_issue(issue: RegenerationIssue) -> List[str]:
    rule_id = str(issue.rule_id or "").strip().lower()
    if rule_id == "numbers":
        return list(NUMBER_RULE_TARGETS)
    if rule_id == "grounding":
        return _grounding_rule_targets(issue)
    return list(RULE_TARGETS.get(rule_id, []))


def _grounding_rule_targets(issue: RegenerationIssue) -> List[str]:
    message = str(issue.message or "").lower()
    if "quote" in message:
        return ["quotes"]
    if "metric" in message or "insight" in message:
        return ["insights_bundle"]
    if "linkedin" in message:
        return ["linkedin_post"]
    if "expert" in message:
        return ["expert_comment"]
    if "summary" in message or "tldr" in message:
        return ["summary"]
    if "unsupported_number" in message:
        return list(NUMBER_RULE_TARGETS)
    return []
