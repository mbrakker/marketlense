"""Validation issue to artifact-regeneration target mapping.

This module owns deterministic regeneration-plan construction and grounding
lookup used by the report-analysis validation repair loop.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

from src.contracts.regeneration import (
    FailureFingerprint,
    RegenerationIssue,
    RegenerationPlan,
    RegenerationTarget,
    repair_strategy_fingerprint,
)
from src.contracts.soft_copy_claim_provenance import (
    soft_copy_claim_provenance_from_payload,
)
from src.contracts.validation import ValidationIssue
from src.utils.editorial_identity import (
    insight_entity_id,
    insight_entity_id_from_public_item_id,
)
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
    if section in {"metadata.title", "metadata.publisher"} or (
        section.startswith("metadata.")
    ):
        # Report identity fields are repaired from canonical source identity,
        # never by regenerating an unrelated claim-bearing family.
        return "report_identity"
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
    if section.startswith("key_figures"):
        return "key_figures"
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
            entry_id = insight_entity_id(entry)
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
    entity_id: str = "",
) -> tuple[List[str], List[int]]:
    section = str(affected_section or "").strip()
    if not section:
        return [], []
    resolved_entity_id = str(entity_id or "").strip()
    if resolved_entity_id:
        try:
            claims = soft_copy_claim_provenance_from_payload(
                artifacts.get("soft_copy_claim_provenance")
            )
        except AppError:
            claims = []
        matching = [claim for claim in claims if claim.claim_id == resolved_entity_id]
        if len(matching) == 1:
            claim = matching[0]
            claim_evidence_ids = list(claim.evidence_ids)
            claim_pages = list(
                dict.fromkeys(
                    int(span["page"])
                    for span in claim.source_spans
                    if isinstance(span, dict) and isinstance(span.get("page"), int)
                )
            )
            return claim_evidence_ids, claim_pages
    public_insight_id = insight_entity_id_from_public_item_id(resolved_entity_id)
    if public_insight_id:
        return _lookup_insight_grounding(public_insight_id, artifacts)
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
    "key_figures",
    "quotes",
    "expert_comment",
    "linkedin_post",
    "report_identity",
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
    derived_evidence_ids, pages = _issue_grounding(
        issue.affected_section, artifacts, issue.entity_id
    )
    evidence_ids = derived_evidence_ids or list(issue.evidence_ids)
    excluded_evidence_ids = (
        list(evidence_ids) if _quarantines_failed_evidence(issue) else []
    )
    fingerprint = FailureFingerprint(
        rule_id=issue.rule_id or _extract_rule_id(issue.message),
        affected_section=issue.affected_section,
        entity_id=issue.entity_id,
        evidence_ids=sorted(evidence_ids),
    )
    return RegenerationIssue(
        rule_id=issue.rule_id or _extract_rule_id(issue.message),
        affected_section=issue.affected_section,
        message=issue.message,
        severity=issue.severity,
        repair_target=issue.repair_target,
        entity_id=issue.entity_id,
        evidence_ids=evidence_ids,
        excluded_evidence_ids=excluded_evidence_ids,
        pages=pages,
        failure_fingerprint=fingerprint.key,
    )


def _quarantines_failed_evidence(issue: ValidationIssue) -> bool:
    """Keep a rejected binding out of the next atomic repair prompt."""

    rule_id = str(issue.rule_id or "").strip().lower()
    if rule_id == "public_editorial_quality.duplicate_insight":
        # The wording duplicates a sibling; their shared source is still valid.
        return False
    return str(issue.severity or "").strip().lower() == "error" and (
        rule_id == "grounding"
        or rule_id in {"numbers", "metrics"}
        or rule_id.startswith("public_editorial_quality.")
    )


def _target_steps(target_key: str) -> List[str]:
    if target_key == "topics":
        return ["toc_entries", "toc_topics", "toc_topics_expanded"]
    if target_key == "summary":
        return ["summary"]
    if target_key == "insights_bundle":
        return ["insights_candidates", "insights_final"]
    if target_key == "key_figures":
        return ["key_figures"]
    if target_key == "quotes":
        return ["quotes"]
    if target_key == "expert_comment":
        return ["expert_comment"]
    if target_key == "linkedin_post":
        return ["linkedin_post"]
    return []


def _target_prompt_namespaces(target_key: str) -> List[str]:
    if target_key == "report_identity":
        return []
    if target_key == "topics":
        return []
    if target_key == "summary":
        return ["report_vs/artifacts/regenerate/summary"]
    if target_key == "insights_bundle":
        return [
            "report_vs/artifacts/regenerate/insights_candidates",
            "report_vs/artifacts/regenerate/insights_final",
        ]
    if target_key == "key_figures":
        return []
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


def _allowed_paths(target_key: str) -> List[str]:
    roots = {
        "topics": ["toc_entries", "toc_topics", "toc_topics_expanded"],
        "summary": ["summary"],
        "insights_bundle": ["insights_candidates", "insights_final"],
        "key_figures": ["key_figures"],
        "quotes": ["quotes_final"],
        "expert_comment": ["expert_comment"],
        "linkedin_post": ["linkedin_post"],
        "report_identity": [],
    }.get(target_key, [])
    return roots + [
        "soft_copy_claim_provenance",
        "family_status",
        "_cache",
        "_repair_evidence_selection",
    ]


# Ordered, materially distinct repair strategies per target.  The planner
# picks the first strategy whose fingerprint was not already rejected, so a
# retry can never repeat an equivalent failed strategy under another label.
_ALTERNATIVE_EVIDENCE_TARGETS = frozenset(
    {"summary", "insights_bundle", "quotes", "expert_comment", "linkedin_post"}
)


def _strategy_options(
    target_key: str, ordered_issues: List[RegenerationIssue]
) -> List[tuple[str, str]]:
    """Return the ordered (repair_action, repair_strategy) ladder for a target."""

    options: List[tuple[str, str]] = []
    if target_key == "report_identity":
        # Report identity has exactly one source-provable correction and one
        # safe terminal.  A generic model rewrite of an identity failure is
        # never a distinct strategy.
        options.append(("COPY_CANONICAL_SOURCE_VALUE", "canonical_identity"))
        options.append(("ABSTAIN", "safe_abstain"))
    elif target_key == "quotes" and _issues_support_quote_restore(ordered_issues):
        options.append(("COPY_CANONICAL_SOURCE_VALUE", "canonical_quote_restore"))
        options.append(("REGENERATE_ITEM", "current_evidence"))
        if target_key in _ALTERNATIVE_EVIDENCE_TARGETS:
            options.append(("REBIND_EVIDENCE", "alternative_evidence"))
        options.append(("REMOVE_CLAIM", "safe_removal"))
    elif target_key == "insights_bundle" and _issues_support_metric_copy(
        ordered_issues
    ):
        options.append(("CORRECT_PROTECTED_FACT", "canonical_metric_copy"))
        options.append(("REGENERATE_ITEM", "current_evidence"))
        if target_key in _ALTERNATIVE_EVIDENCE_TARGETS:
            options.append(("REBIND_EVIDENCE", "alternative_evidence"))
        options.append(("REMOVE_CLAIM", "safe_removal"))
    else:
        options.append(("REGENERATE_ITEM", "current_evidence"))
        if target_key in _ALTERNATIVE_EVIDENCE_TARGETS:
            options.append(("REBIND_EVIDENCE", "alternative_evidence"))
        options.append(("REMOVE_CLAIM", "safe_removal"))
    return options


def _issues_support_quote_restore(ordered_issues: List[RegenerationIssue]) -> bool:
    """A failed quote can be restored verbatim only from a retained source quote."""

    return all(
        str(issue.rule_id or "").strip().lower() in {"grounding", "semantic"}
        and str(issue.severity or "").lower() == "error"
        for issue in ordered_issues
    )


def _issues_support_metric_copy(ordered_issues: List[RegenerationIssue]) -> bool:
    """A failed insight metric can be copied only from retained bound evidence."""

    return any(
        str(issue.rule_id or "").strip().lower() in {"grounding", "numbers", "metrics"}
        and str(issue.severity or "").lower() == "error"
        for issue in ordered_issues
    )


def _build_target(
    target_key: str,
    issues: List[RegenerationIssue],
    rejected_strategy_keys: set[str] | None = None,
) -> RegenerationTarget | None:
    ordered_issues = sorted(
        issues,
        key=lambda issue: (
            REGENERATION_SEVERITY_ORDER.get(str(issue.severity).lower(), 99),
            issue.rule_id,
            issue.affected_section,
        ),
    )
    failure_fingerprints = [issue.failure_fingerprint for issue in ordered_issues]
    evidence_ids = sorted(
        {evidence_id for issue in ordered_issues for evidence_id in issue.evidence_ids}
    )
    rejected = rejected_strategy_keys or set()
    repair_action = ""
    repair_strategy = ""
    selected_evidence_ids: List[str] = []
    for action, strategy in _strategy_options(target_key, ordered_issues):
        candidate_key = repair_strategy_fingerprint(
            failure_fingerprints, strategy, evidence_ids
        )
        if candidate_key in rejected:
            continue
        repair_action = action
        repair_strategy = strategy
        selected_evidence_ids = (
            [] if action in {"REMOVE_CLAIM", "ABSTAIN"} else evidence_ids
        )
        break
    if not repair_strategy:
        # Every materially distinct strategy for this failure was already
        # rejected. Repeating any of them under another label is prohibited;
        # the failure stays terminal instead of burning bounded attempts.
        return None
    return RegenerationTarget(
        target_section=target_key,
        regenerate_steps=_target_steps(target_key),
        prompt_namespaces=_target_prompt_namespaces(target_key),
        issues=ordered_issues,
        repair_action=repair_action,
        repair_strategy=repair_strategy,
        allowed_paths=_allowed_paths(target_key),
        selected_evidence_ids=selected_evidence_ids,
        quarantined_evidence_ids=sorted(
            {value for issue in ordered_issues for value in issue.excluded_evidence_ids}
        ),
    )


def _build_regeneration_plan(
    *,
    issues: List[ValidationIssue],
    artifacts: Dict[str, Any],
    broad_retry_available: bool,
    rejected_strategy_keys: set[str] | None = None,
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
    hard_target_keys = {
        target_key
        for target_key, target_issues in grouped.items()
        if any(str(issue.severity).lower() == "error" for issue in target_issues)
    }
    if hard_target_keys:
        # A blocking, targetable failure must not fan out into unrelated
        # warning-only families. Retain warnings on the same target so its
        # repair still sees all local context, but keep claim recovery bounded.
        grouped = {
            target_key: target_issues
            for target_key, target_issues in grouped.items()
            if target_key in hard_target_keys
        }
        unmappable = [
            issue for issue in unmappable if str(issue.severity).lower() == "error"
        ]
    if grouped:
        targets = [
            built_target
            for built_target in (
                _build_target(target_key, grouped[target_key], rejected_strategy_keys)
                for target_key in TARGET_ORDER
                if target_key in grouped
            )
            if built_target is not None
        ]
        if not targets:
            # Every targetable failure exhausted its distinct strategies; the
            # remaining issues stay terminal instead of repeating a rejection.
            return RegenerationPlan(
                mode="skip",
                targets=[],
                unmappable_issues=[
                    issue
                    for target_issues in grouped.values()
                    for issue in target_issues
                ],
                broad_retry_allowed=False,
            )
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
        broad_targets = [
            built_target
            for built_target in (
                _build_target(target_key, list(unmappable), rejected_strategy_keys)
                for target_key in BROAD_TARGETS
            )
            if built_target is not None
        ]
        if not broad_targets:
            return RegenerationPlan(
                mode="skip",
                targets=[],
                unmappable_issues=unmappable,
                broad_retry_allowed=False,
            )
        return RegenerationPlan(
            mode="broad",
            targets=broad_targets,
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
        if explicit_target == "artifact_copy":
            # Public-editorial quality deliberately reports the semantic copy
            # category rather than a generator implementation detail.  Map it
            # deterministically from the retained affected section; never let
            # a valid live quality finding dead-letter the full report solely
            # because it used that public contract label.
            derived_target = _target_section(issue.affected_section)
            if derived_target:
                return [derived_target]
            affected = str(issue.affected_section or "").strip().lower()
            if affected.startswith("key_figures"):
                return ["key_figures"]
            if affected.startswith("chart_insight_cards"):
                return ["insights_bundle"]
            if affected.startswith("topics_covered"):
                return ["topics"]
            return []
        if explicit_target not in SUPPORTED_TARGETS:
            raise AppError(
                code="regeneration_repair_target_unsupported",
                message=(
                    "Validation issue requested an unsupported regeneration "
                    "repair target"
                ),
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
