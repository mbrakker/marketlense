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

    verified_mode = runtime.prepared.verified_facts_mode
    if verified_mode:
        return _run_verified_claim_support_rule(
            claim_map, set(runtime.prepared.evidence_map)
        )
    # Evidence identity and span membership are technical checks.  Whether a
    # sentence overstates or semantically follows its evidence belongs to the
    # single grounding verdict, not to this legacy rule.
    known_evidence_ids = set(runtime.prepared.evidence_map)
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


def _run_verified_claim_support_rule(
    claim_map: list[object], known_evidence_ids: set[str]
) -> List[ValidationIssue]:
    """Check only the verified-fact reference contract, never source grades."""

    issues: List[ValidationIssue] = []
    for index, raw_claim in enumerate(claim_map):
        if not isinstance(raw_claim, dict):
            continue
        claim_text = s(raw_claim.get("claim")).strip()
        evidence_id = s(raw_claim.get("evidence_id")).strip()
        spans = [
            span
            for span in raw_claim.get("evidence_spans") or []
            if isinstance(span, dict)
        ]
        if not evidence_id or evidence_id not in known_evidence_ids:
            issues.append(
                issue(
                    rule_id=RULE_ID,
                    message=(
                        f"Verified-fact summary claim references unknown evidence_id "
                        f"'{evidence_id}': {claim_text[:160]}"
                    ),
                    severity="error",
                    section=f"summary.claim_evidence_map[{index}]",
                    repair_target="summary",
                    entity_id=evidence_id,
                )
            )
            continue
        if not spans:
            issues.append(
                issue(
                    rule_id=RULE_ID,
                    message="Verified-fact summary claim is missing evidence spans.",
                    severity="error",
                    section=f"summary.claim_evidence_map[{index}]",
                    repair_target="summary",
                    entity_id=evidence_id,
                )
            )
            continue
        if any(s(span.get("evidence_id")).strip() != evidence_id for span in spans):
            issues.append(
                issue(
                    rule_id=RULE_ID,
                    message=(
                        "Verified-fact summary claim has an inconsistent evidence span."
                    ),
                    severity="error",
                    section=f"summary.claim_evidence_map[{index}]",
                    repair_target="summary",
                    entity_id=evidence_id,
                )
            )
    return issues
