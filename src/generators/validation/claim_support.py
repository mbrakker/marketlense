from __future__ import annotations

from typing import List

from src.contracts.validation import ValidationIssue

from .models import ValidationRuntime
from .shared import ensure_dict, issue, s

RULE_ID = "claim_support"


def run_claim_support_rule(runtime: ValidationRuntime) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    artifacts = ensure_dict(runtime.request.artifacts)
    summary = ensure_dict(artifacts.get("summary"))
    claim_map = summary.get("claim_evidence_map")
    if not isinstance(claim_map, list):
        return issues

    known_evidence_ids = _collect_known_evidence_ids(runtime.request.evidence_packs)
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
        if not evidence_id:
            issues.append(
                issue(
                    rule_id=RULE_ID,
                    message=(
                        "Summary claim is missing an evidence identifier and cannot be trusted: "
                        f"{claim_text[:160]}"
                    ),
                    severity="error",
                    section=f"summary.claim_evidence_map[{index}]",
                    repair_target="summary",
                    entity_id=f"claim_{index + 1}",
                )
            )
            continue
        if evidence_id not in known_evidence_ids:
            issues.append(
                issue(
                    rule_id=RULE_ID,
                    message=(
                        f"Summary claim references unknown evidence_id '{evidence_id}': "
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
                        f"Summary claim '{claim_text[:120]}' is missing evidence span references."
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
                        f"Summary claim '{claim_text[:120]}' has evidence spans that do not match "
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
    known: set[str] = set()
    if not isinstance(evidence_packs, dict):
        return known

    def _register(value: object) -> None:
        text = s(value).strip()
        if text:
            known.add(text)

    for pack_name, root_key in (
        ("findings", "findings"),
        ("quote_candidates", "quote_candidates"),
        ("key_metrics", "key_metrics"),
        ("risk_register", "risk_register"),
        ("recommendations", "recommendations"),
    ):
        pack = evidence_packs.get(pack_name)
        if not isinstance(pack, dict):
            continue
        for item in pack.get(root_key) or []:
            if not isinstance(item, dict):
                continue
            _register(item.get("id"))
            _register(item.get("evidence_id"))
    contradictions_pack = evidence_packs.get("contradictions")
    if isinstance(contradictions_pack, dict):
        for item in contradictions_pack.get("contradictions") or []:
            if not isinstance(item, dict):
                continue
            for evidence_id in item.get("evidence_ids") or []:
                _register(evidence_id)
    doc_map = evidence_packs.get("doc_map")
    if isinstance(doc_map, dict):
        for section in doc_map.get("sections") or []:
            if isinstance(section, dict):
                _register(section.get("id"))
    return known
