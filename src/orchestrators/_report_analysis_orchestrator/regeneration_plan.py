"""Validation issue to artifact-regeneration target mapping.

This module owns deterministic regeneration-plan construction and grounding
lookup used by the report-analysis validation repair loop.
"""

from __future__ import annotations

import hashlib
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
    soft_copy_material_sentences,
)
from src.contracts.validation import ValidationIssue
from src.utils.editorial_identity import (
    failed_insight_id,
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
    evidence_ids = (
        list(issue.evidence_ids)
        if str(issue.rule_id or "").strip().lower().startswith("retained_claim.")
        else derived_evidence_ids or list(issue.evidence_ids)
    )
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
    if rule_id.startswith("retained_claim."):
        return rule_id == "retained_claim.evidence_reference_completeness"
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


def _allowed_paths(
    target_key: str,
    issues: List[RegenerationIssue],
    artifacts: Dict[str, Any],
    repair_action: str,
) -> List[str]:
    """Resolve issue targets to exact retained leaves before any model call."""

    family_roots = {
        "topics": ["toc_entries", "toc_topics", "toc_topics_expanded"],
        "summary": ["summary"],
        "insights_bundle": ["insights_candidates", "insights_final"],
        "key_figures": ["key_figures"],
        "quotes": ["quotes_final"],
        "expert_comment": ["expert_comment"],
        "linkedin_post": ["linkedin_post"],
        "report_identity": [],
    }.get(target_key, [])
    if target_key == "topics":
        return sorted(set(family_roots))

    resolved = [_issue_allowed_path(target_key, issue, artifacts) for issue in issues]
    if target_key in {
        "summary",
        "insights_bundle",
        "key_figures",
        "quotes",
        "expert_comment",
        "linkedin_post",
    } and any(not path for path in resolved):
        return []
    paths: set[str] = set()
    for path in resolved:
        if not path:
            continue
        if path in {
            "summary.tldr",
            "summary.card_tldr_compact",
            "summary.executive_summary",
            "expert_comment",
            "linkedin_post",
        }:
            text = (
                artifacts.get("summary", {}).get(path.split(".", 1)[1])
                if path.startswith("summary.")
                and isinstance(artifacts.get("summary"), dict)
                else artifacts.get(path)
            )
            sentences = (
                soft_copy_material_sentences(text) if isinstance(text, str) else []
            )
            paths.update(
                f"{path}[claim_index={index}]" for index in range(len(sentences))
            )
            if not sentences and isinstance(text, str):
                paths.add(path)
            continue
        if repair_action == "REMOVE_CLAIM" and target_key == "insights_bundle":
            paths.add(path.rsplit(".", 1)[0] if "." in path else path)
            continue
        paths.add(path)
    return sorted(paths)


def _issue_allowed_path(
    target_key: str, issue: RegenerationIssue, artifacts: Dict[str, Any]
) -> str:
    affected = str(issue.affected_section or "").strip()
    entity_id = str(issue.entity_id or "").strip()
    if target_key == "report_identity":
        return ""
    if target_key == "summary":
        soft_copy_path = _soft_copy_claim_path(
            family="summary", entity_id=entity_id, artifacts=artifacts
        )
        if soft_copy_path:
            return soft_copy_path
        match = re.match(
            r"^(?:summary\.)?(tldr|card_tldr_compact|executive_summary)(?:\.|$)",
            affected,
        )
        if match:
            return f"summary.{match.group(1)}"
        map_match = re.match(r"^summary\.claim_evidence_map:([^.:]+)", affected)
        if map_match:
            identity = map_match.group(1)
            entries = artifacts.get("summary", {}).get("claim_evidence_map", [])
            if isinstance(entries, list):
                for index, entry in enumerate(entries):
                    if not isinstance(entry, dict):
                        continue
                    stable_id = str(
                        entry.get("id") or entry.get("claim_id") or ""
                    ).strip()
                    if stable_id == identity:
                        return f"summary.claim_evidence_map[item={identity}].claim"
                    if not stable_id and str(index + 1) == identity:
                        return f"summary.claim_evidence_map[{index}].claim"
        return ""
    if target_key == "insights_bundle":
        indexed_match = re.match(
            r"^(insights_final|insights_candidates)\[(\d+)\]\.(.+)$", affected
        )
        if indexed_match:
            root, raw_index, field = indexed_match.groups()
            items = artifacts.get(root)
            index = int(raw_index)
            if isinstance(items, list) and index < len(items):
                item = items[index]
                if isinstance(item, dict) and _has_scalar_leaf(item, field):
                    identity = insight_entity_id(item)
                    if identity:
                        _, item_path = _identified_item_path(root, items, identity)
                    else:
                        item_path = f"[{index}]"
                    return f"{root}{item_path}.{field}"
            return ""
        insight_id = insight_entity_id_from_public_item_id(entity_id)
        if not insight_id:
            insight_id = failed_insight_id(entity_id, affected)
        if insight_id:
            final = artifacts.get("insights_final") or []
            candidates = artifacts.get("insights_candidates") or []
            root, item_path = _identified_item_path("insights_final", final, insight_id)
            if not root:
                root, item_path = _identified_item_path(
                    "insights_candidates", candidates, insight_id
                )
            if root:
                field = _insight_issue_field(entity_id, affected)
                items = final if root == "insights_final" else candidates
                item = _item_at_identity_path(items, item_path)
                return (
                    f"{root}{item_path}.{field}"
                    if (
                        field
                        and isinstance(item, dict)
                        and _has_scalar_leaf(item, field)
                    )
                    else ""
                )
        return ""
    if target_key == "quotes":
        identity = _public_item_identity(entity_id, "quote") or _section_identity(
            affected, "quotes"
        )
        if identity:
            items = artifacts.get("quotes_final") or []
            root, item_path = _identified_item_path("quotes_final", items, identity)
            item = _item_at_identity_path(items, item_path)
            if (
                root
                and isinstance(item, dict)
                and not isinstance(item.get("text"), (dict, list))
            ):
                return f"{root}{item_path}.text"
        return ""
    if target_key == "key_figures":
        identity = _public_item_identity(entity_id, "key_figure") or _section_identity(
            affected, "key_figures"
        )
        field = _key_figure_issue_field(entity_id, affected)
        if identity:
            root, item_path = _identified_item_path(
                "key_figures", artifacts.get("key_figures") or [], identity
            )
            items = artifacts.get("key_figures") or []
            item = _item_at_identity_path(items, item_path)
            if (
                root
                and field
                and isinstance(item, dict)
                and _has_scalar_leaf(item, field)
            ):
                return f"{root}{item_path}.{field}"
        return ""
    if target_key in {"expert_comment", "linkedin_post"}:
        claim_path = _soft_copy_claim_path(
            family=target_key, entity_id=entity_id, artifacts=artifacts
        )
        if claim_path:
            return claim_path
        issue_evidence_ids = {
            str(value).strip().casefold()
            for value in issue.evidence_ids
            if str(value).strip()
        }
        if issue_evidence_ids:
            try:
                claims = soft_copy_claim_provenance_from_payload(
                    artifacts.get("soft_copy_claim_provenance")
                )
            except AppError:
                claims = []
            paths = {
                path
                for claim in claims
                if claim.artifact_family == target_key
                and issue_evidence_ids.intersection(
                    value.casefold() for value in claim.evidence_ids
                )
                if (path := _soft_copy_claim_path(
                    family=target_key,
                    entity_id=claim.claim_id,
                    artifacts=artifacts,
                ))
            }
            if len(paths) == 1:
                return next(iter(paths))
        return ""
    return target_key


def _public_item_identity(entity_id: str, expected_kind: str) -> str:
    kind, separator, remainder = entity_id.partition(":")
    if kind != expected_kind or not separator:
        return ""
    return remainder.split(":", 1)[0].split(".", 1)[0].strip()


def _section_identity(affected: str, expected_root: str) -> str:
    prefix, separator, remainder = affected.partition(":")
    if prefix.casefold() != expected_root.casefold() or not separator:
        return ""
    return remainder.split(".", 1)[0].strip()


def _identified_item_path(root: str, items: object, identity: str) -> tuple[str, str]:
    if not isinstance(items, list):
        return "", ""
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        stable_id = str(
            item.get("id")
            or item.get("insight_id")
            or item.get("key_figure_id")
            or item.get("claim_id")
            or ""
        ).strip()
        if stable_id and stable_id == identity:
            return root, f"[item={stable_id}]"
        if not stable_id and str(index + 1) == identity:
            return root, f"[{index}]"
        if root == "quotes_final" and not stable_id:
            if str(item.get("evidence_id") or "").strip() == identity:
                return root, f"[{index}]"
    return "", ""


def _insight_issue_field(entity_id: str, affected: str) -> str:
    parts = entity_id.split(":")
    if len(parts) >= 3 and parts[0] == "insight":
        return ":".join(parts[2:]).strip()
    match = re.match(r"^insights:[^.:]+\.(.+)$", affected)
    if match:
        return match.group(1).strip()
    match = re.match(r"^insights_(?:final|candidates)\[\d+\]\.(.+)$", affected)
    return match.group(1).strip() if match else ""


def _key_figure_issue_field(entity_id: str, affected: str) -> str:
    match = re.match(r"^key_figure:[^:]+:(.+)$", entity_id)
    if match:
        return match.group(1).strip()
    match = re.match(r"^key_figures:[^.:]+\.(.+)$", affected)
    return match.group(1).strip() if match else ""


def _item_at_identity_path(items: object, item_path: str) -> Dict[str, Any] | None:
    if not isinstance(items, list):
        return None
    index_match = re.fullmatch(r"\[(\d+)\]", item_path)
    if index_match:
        index = int(index_match.group(1))
        item = items[index] if index < len(items) else None
        return item if isinstance(item, dict) else None
    identity_match = re.fullmatch(r"\[item=(.+)\]", item_path)
    if not identity_match:
        return None
    identity = identity_match.group(1)
    matches = [
        item
        for item in items
        if isinstance(item, dict)
        and identity
        in {
            str(item.get(field) or "").strip()
            for field in ("id", "insight_id", "key_figure_id", "claim_id")
        }
    ]
    return matches[0] if len(matches) == 1 else None


def _has_scalar_leaf(value: Dict[str, Any], field_path: str) -> bool:
    current: Any = value
    for segment in field_path.split("."):
        if not isinstance(current, dict) or segment not in current:
            return False
        current = current[segment]
    return not isinstance(current, (dict, list))


def _soft_copy_claim_path(
    *, family: str, entity_id: str, artifacts: Dict[str, Any]
) -> str:
    if not entity_id:
        return ""
    try:
        claims = soft_copy_claim_provenance_from_payload(
            artifacts.get("soft_copy_claim_provenance")
        )
    except AppError:
        return ""
    claim = next(
        (
            value
            for value in claims
            if value.artifact_family == family and value.claim_id == entity_id
        ),
        None,
    )
    if claim is None:
        return ""
    text_fields = (
        (
            ("summary", "tldr"),
            ("summary", "card_tldr_compact"),
            ("summary", "executive_summary"),
        )
        if family == "summary"
        else ((family, ""),)
    )
    matches: list[str] = []
    for artifact_root, field in text_fields:
        text = (
            artifacts.get(artifact_root, {}).get(field, "")
            if field
            else artifacts.get(artifact_root, "")
        )
        for index, sentence in enumerate(soft_copy_material_sentences(text)):
            text_hash = hashlib.sha256(
                " ".join(sentence.split()).encode("utf-8")
            ).hexdigest()
            if text_hash == claim.text_hash:
                base = f"summary.{field}" if field else family
                matches.append(f"{base}[claim_index={index}]")
    return matches[0] if len(matches) == 1 else ""


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
    elif target_key == "key_figures":
        # Key Figures are rebuilt deterministically from retained metrics and
        # bound evidence. The numeric-fidelity selector omits every invalid
        # projection, so a removal-labeled rebuild would be equivalent.
        options.append(("REGENERATE_ITEM", "current_evidence"))
    else:
        options.append(("REGENERATE_ITEM", "current_evidence"))
        if target_key in _ALTERNATIVE_EVIDENCE_TARGETS:
            options.append(("REBIND_EVIDENCE", "alternative_evidence"))
        options.append(("REMOVE_CLAIM", "safe_removal"))
    return options


def _issues_support_quote_restore(ordered_issues: List[RegenerationIssue]) -> bool:
    """A failed quote can be restored verbatim only from a retained source quote."""

    return all(
        str(issue.rule_id or "").strip().lower()
        in {
            "grounding",
            "semantic",
            "retained_claim.quote_match",
            "retained_claim.evidence_reference_completeness",
        }
        and str(issue.severity or "").lower() == "error"
        for issue in ordered_issues
    )


def _issues_support_metric_copy(ordered_issues: List[RegenerationIssue]) -> bool:
    """A failed insight metric can be copied only from retained bound evidence."""

    return any(
        (
            str(issue.rule_id or "").strip().lower()
            in {"grounding", "numbers", "metrics"}
            or str(issue.rule_id or "").strip().lower()
            in {
                "retained_claim.number_value_unit_match",
                "retained_claim.evidence_reference_completeness",
            }
            or str(issue.rule_id or "")
            .strip()
            .lower()
            .startswith("retained_claim.protected_fact_")
        )
        and str(issue.severity or "").lower() == "error"
        for issue in ordered_issues
    )


def _build_target(
    target_key: str,
    issues: List[RegenerationIssue],
    rejected_strategy_keys: set[str] | None = None,
    artifacts: Dict[str, Any] | None = None,
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
        strategy_evidence_ids = (
            [] if action in {"REMOVE_CLAIM", "ABSTAIN"} else evidence_ids
        )
        candidate_key = repair_strategy_fingerprint(
            failure_fingerprints, strategy, strategy_evidence_ids
        )
        if candidate_key in rejected:
            continue
        repair_action = action
        repair_strategy = strategy
        selected_evidence_ids = strategy_evidence_ids
        break
    if not repair_strategy:
        # Every materially distinct strategy for this failure was already
        # rejected. Repeating any of them under another label is prohibited;
        # the failure stays terminal instead of burning bounded attempts.
        return None
    allowed_paths = _allowed_paths(
        target_key, ordered_issues, artifacts or {}, repair_action
    )
    if (
        target_key
        in {
            "summary",
            "insights_bundle",
            "key_figures",
            "quotes",
            "expert_comment",
            "linkedin_post",
        }
        and repair_action != "ABSTAIN"
        and not allowed_paths
    ):
        return None
    return RegenerationTarget(
        target_section=target_key,
        regenerate_steps=_target_steps(target_key),
        prompt_namespaces=_target_prompt_namespaces(target_key),
        issues=ordered_issues,
        repair_action=repair_action,
        repair_strategy=repair_strategy,
        allowed_paths=allowed_paths,
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
                _build_target(
                    target_key,
                    grouped[target_key],
                    rejected_strategy_keys,
                    artifacts,
                )
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
                _build_target(
                    target_key,
                    list(unmappable),
                    rejected_strategy_keys,
                    artifacts,
                )
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
