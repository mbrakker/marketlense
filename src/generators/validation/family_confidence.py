from __future__ import annotations

from typing import List

from src.contracts.validation import ValidationIssue
from src.utils.analysis_family import get_family_status
from src.utils.coercion import coerce_float

from .models import ValidationRuntime
from .shared import ensure_dict, issue, s

RULE_ID = "family_confidence"
_ARTIFACT_REPAIR_TARGETS = {
    "summary": ("summary", "summary"),
    "insights_bundle": ("insights", "insights_bundle"),
    "quotes": ("quotes", "quotes"),
}


def run_family_confidence_rule(runtime: ValidationRuntime) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    artifacts = ensure_dict(runtime.request.artifacts)
    for family, (section, repair_target) in _ARTIFACT_REPAIR_TARGETS.items():
        status = get_family_status(artifacts, family)
        if str(status.get("status") or "").strip().lower() != "abstained":
            continue
        policy_action = s(status.get("policy_action")).strip().lower()
        reason = s(status.get("reason")).strip() or "insufficient_evidence_support"
        confidence = status.get("confidence_score")
        if policy_action == "regenerate":
            issues.append(
                issue(
                    rule_id=RULE_ID,
                    message=(
                        f"Artifact family '{family}' abstained at confidence="
                        f"{_format_confidence(confidence)} because {reason}."
                    ),
                    severity="error",
                    section=section,
                    repair_target=repair_target,
                )
            )
    for family in ("expert_comment", "linkedin_post"):
        status = get_family_status(artifacts, family)
        if str(status.get("status") or "").strip().lower() != "abstained":
            continue
        issues.append(
            issue(
                rule_id=RULE_ID,
                message=(
                    f"Artifact family '{family}' was intentionally omitted at confidence="
                    f"{_format_confidence(status.get('confidence_score'))} because "
                    f"{s(status.get('reason')).strip() or 'insufficient_evidence_support'}."
                ),
                severity="warning",
                section=family,
            )
        )
    for pack_name, pack_payload in runtime.request.evidence_packs.items():
        pack = ensure_dict(pack_payload)
        status = get_family_status(pack, pack_name)
        if str(status.get("status") or "").strip().lower() != "abstained":
            continue
        issues.append(
            issue(
                rule_id=RULE_ID,
                message=(
                    f"Evidence pack '{pack_name}' abstained at confidence="
                    f"{_format_confidence(status.get('confidence_score'))} because "
                    f"{s(status.get('reason')).strip() or 'insufficient_pack_content'}."
                ),
                severity="info",
                section=f"evidence_pack:{pack_name}",
            )
        )
    return issues


def _format_confidence(value: object) -> str:
    return f"{coerce_float(value, 0.0):.2f}"
