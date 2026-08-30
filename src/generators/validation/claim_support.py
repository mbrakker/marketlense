from __future__ import annotations

import re
from typing import List

from src.contracts.validation import ValidationIssue

from .models import ValidationRuntime
from .shared import ensure_dict, issue, s

RULE_ID = "claim_support"
STRONG_CLAIM_RE = re.compile(
    r"(\d+(?:[\.,]\d+)?\s*(?:%|percent|percentage|bps|points|x|times|million|"
    r"billion|trillion|k|m|bn)\b|[$€£]\s*\d|"
    r"\b(?:proves?|guarantees?|must|will|always|never|only|highest|lowest|"
    r"largest|smallest|dominates?|requires?)\b)",
    re.IGNORECASE,
)
SOURCE_BACKED_GRADES = {
    "direct_evidence_span",
    "direct_metric",
    "direct_quote",
    "chart_readout",
    "explicit_finding",
    "explicit_recommendation",
    "explicit_risk",
    "source_backed",
}
WEAK_EVIDENCE_GRADES = {
    "weak_paraphrase",
    "section_summary",
    "unsupported_context",
    "low_confidence",
}


def run_claim_support_rule(runtime: ValidationRuntime) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    artifacts = ensure_dict(runtime.request.artifacts)
    summary = ensure_dict(artifacts.get("summary"))
    claim_map = summary.get("claim_evidence_map")
    if not isinstance(claim_map, list):
        return issues

    evidence_quality_grades = _collect_evidence_quality_grades(
        runtime.request.evidence_packs
    )
    known_evidence_ids = set(evidence_quality_grades)
    for index, raw_claim in enumerate(claim_map):
        if not isinstance(raw_claim, dict):
            continue
        claim_text = s(raw_claim.get("claim")).strip()
        if not claim_text:
            continue
        evidence_id = s(raw_claim.get("evidence_id")).strip()
        evidence_spans = [
            span
            for span in raw_claim.get("evidence_spans") or []
            if isinstance(span, dict)
        ]
        referenced_evidence_ids = _claim_evidence_ids(
            evidence_id=evidence_id,
            evidence_spans=evidence_spans,
        )
        if not evidence_id:
            issues.append(
                issue(
                    rule_id=RULE_ID,
                    message=(
                        "Summary claim is missing an evidence identifier and cannot "
                        "be trusted: "
                        f"{claim_text[:160]}"
                    ),
                    severity="error",
                    section=f"summary.claim_evidence_map[{index}]",
                    repair_target="summary",
                    entity_id=f"claim_{index + 1}",
                )
            )
            continue
        inline_grade = _quality_grade(raw_claim)
        if inline_grade:
            evidence_quality_grades[evidence_id] = inline_grade
        if evidence_id not in known_evidence_ids:
            issues.append(
                issue(
                    rule_id=RULE_ID,
                    message=(
                        "Summary claim references unknown evidence_id "
                        f"'{evidence_id}': "
                        f"{claim_text[:160]}"
                    ),
                    severity="error",
                    section=f"summary.claim_evidence_map[{index}]",
                    repair_target="summary",
                    entity_id=evidence_id,
                )
            )
            continue
        if not evidence_spans:
            issues.append(
                issue(
                    rule_id=RULE_ID,
                    message=(
                        f"Summary claim '{claim_text[:120]}' is missing evidence "
                        "span references."
                    ),
                    severity="error",
                    section=f"summary.claim_evidence_map[{index}]",
                    repair_target="summary",
                    entity_id=evidence_id,
                )
            )
            continue
        if _strong_claim_overstates_support(
            claim_text=claim_text,
            evidence_ids=referenced_evidence_ids,
            evidence_quality_grades=evidence_quality_grades,
        ):
            grades = [
                evidence_quality_grades.get(item, "unknown")
                for item in referenced_evidence_ids
            ]
            issues.append(
                issue(
                    rule_id=RULE_ID,
                    message=(
                        "weak_evidence_strong_claim: summary claim uses strong "
                        f"language but evidence quality is {', '.join(grades)}."
                    ),
                    severity="error",
                    section=f"summary.claim_evidence_map[{index}]",
                    repair_target="summary",
                    entity_id=evidence_id,
                )
            )
            continue
        if not any(
            s(span.get("evidence_id")).strip() == evidence_id for span in evidence_spans
        ):
            issues.append(
                issue(
                    rule_id=RULE_ID,
                    message=(
                        f"Summary claim '{claim_text[:120]}' has evidence spans "
                        "that do not match "
                        f"evidence_id '{evidence_id}'."
                    ),
                    severity="error",
                    section=f"summary.claim_evidence_map[{index}]",
                    repair_target="summary",
                    entity_id=evidence_id,
                )
            )
    return issues


def _collect_known_evidence_ids(evidence_packs: dict) -> set[str]:
    return set(_collect_evidence_quality_grades(evidence_packs))


def _collect_evidence_quality_grades(evidence_packs: dict) -> dict[str, str]:
    grades: dict[str, str] = {}
    if not isinstance(evidence_packs, dict):
        return grades

    def _register(value: object, grade: str) -> None:
        text = s(value).strip()
        if text:
            grades[text] = _normalize_quality_grade(grade)

    for pack_name, root_key in (
        ("findings", "findings"),
        ("quote_candidates", "quote_candidates"),
    ):
        pack = evidence_packs.get(pack_name)
        if not isinstance(pack, dict):
            continue
        for item in pack.get(root_key) or []:
            if not isinstance(item, dict):
                continue
            grade = _quality_grade(item) or _default_quality_grade(pack_name)
            _register(item.get("id"), grade)
            _register(item.get("evidence_id"), grade)
    doc_map = evidence_packs.get("doc_map")
    if isinstance(doc_map, dict):
        for section in doc_map.get("sections") or []:
            if isinstance(section, dict):
                _register(
                    section.get("id"),
                    _quality_grade(section) or "section_summary",
                )
    return grades


def _quality_grade(item: dict) -> str:
    for field_name in ("quality_grade", "evidence_quality_grade", "support_grade"):
        grade = _normalize_quality_grade(item.get(field_name))
        if grade:
            return grade
    return ""


def _normalize_quality_grade(value: object) -> str:
    return "_".join(s(value).strip().lower().replace("-", "_").split())


def _default_quality_grade(pack_name: str) -> str:
    return {
        "findings": "explicit_finding",
        "quote_candidates": "direct_quote",
    }.get(pack_name, "source_backed")


def _claim_evidence_ids(*, evidence_id: str, evidence_spans: list[dict]) -> list[str]:
    ids = [evidence_id]
    for span in evidence_spans:
        span_id = s(span.get("evidence_id")).strip()
        if span_id:
            ids.append(span_id)
    return sorted(dict.fromkeys(item for item in ids if item))


def _strong_claim_overstates_support(
    *,
    claim_text: str,
    evidence_ids: list[str],
    evidence_quality_grades: dict[str, str],
) -> bool:
    if not STRONG_CLAIM_RE.search(claim_text):
        return False
    grades = [
        evidence_quality_grades.get(evidence_id, "") for evidence_id in evidence_ids
    ]
    known_grades = [grade for grade in grades if grade]
    if not known_grades:
        return False
    if any(grade in SOURCE_BACKED_GRADES for grade in known_grades):
        return False
    return all(grade in WEAK_EVIDENCE_GRADES for grade in known_grades)
