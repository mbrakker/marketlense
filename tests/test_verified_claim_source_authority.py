from copy import deepcopy

from src.contracts.validation import ValidationIssue
from src.orchestrators._report_analysis_orchestrator.regeneration_plan import (
    _build_regeneration_plan,
)
from tests._test_regeneration_candidate._shared import _soft_copy_claim
from tests.test_verified_wording_repair_evidence import _artifacts


def _issue(violation_type: str, *, outcome: str = "not_established") -> ValidationIssue:
    return ValidationIssue(
        rule_id="grounding",
        severity="error",
        violation_type=violation_type,
        entailment_outcome=outcome,
        classification="factual_claim",
        entity_id="insight:i1:text",
        affected_section="insights:i1.text",
        evidence_ids=["verified-fact:f1"],
        message="The public claim is not supported.",
    )


def test_rejected_public_number_keeps_exact_validated_source_for_repair():
    plan = _build_regeneration_plan(
        issues=[_issue("unsupported_number")],
        artifacts=_artifacts(),
        broad_retry_available=True,
    )
    target = plan.targets[0]
    assert target.quarantined_evidence_ids == []
    assert target.selected_evidence_ids == ["verified-fact:f1"]


def test_rejected_recommendation_keeps_its_exact_verified_fact():
    artifacts = _artifacts()
    artifacts["expert_comment"] = "MarketLense recommends testing the finding."
    claim = _soft_copy_claim(
        family="expert_comment",
        text=artifacts["expert_comment"],
        evidence_id="verified-fact:f1",
        page=1,
    )
    claim["source_spans"][0]["source_pack"] = "verified_facts"
    artifacts["soft_copy_claim_provenance"] = {
        "schema_version": "1.0",
        "claims": [claim],
    }
    issue = ValidationIssue(
        rule_id="grounding",
        severity="error",
        violation_type="report_directive_misattribution",
        entailment_outcome="not_established",
        classification="prescriptive_recommendation",
        entity_id=str(claim["claim_id"]),
        affected_section="expert_comment",
        evidence_ids=["verified-fact:f1"],
        message="The recommendation attribution is not established.",
    )
    plan = _build_regeneration_plan(
        issues=[issue], artifacts=artifacts, broad_retry_available=True
    )
    target = next(
        item for item in plan.targets if item.target_section == "expert_comment"
    )
    assert target.quarantined_evidence_ids == []
    assert target.selected_evidence_ids == ["verified-fact:f1"]


def test_source_retrieval_failure_and_invalid_identity_stay_quarantined():
    invalid = deepcopy(_artifacts())
    invalid["verified_facts"][0]["source_pdf_sha256"] = "b" * 64
    for issue, artifacts in [
        (_issue("evidence_retrieval_failure"), _artifacts()),
        (_issue("unsupported_number"), invalid),
    ]:
        plan = _build_regeneration_plan(
            issues=[issue], artifacts=artifacts, broad_retry_available=True
        )
        assert plan.targets[0].quarantined_evidence_ids == ["verified-fact:f1"]


def test_missing_verdict_and_mismatched_binding_do_not_release_evidence():
    issue = _issue("unsupported_number", outcome="")
    plan = _build_regeneration_plan(
        issues=[issue], artifacts=_artifacts(), broad_retry_available=True
    )
    assert plan.targets[0].quarantined_evidence_ids == ["verified-fact:f1"]

    artifacts = _artifacts()
    artifacts["insights_final"][0]["evidence_id"] = "verified-fact:other"
    plan = _build_regeneration_plan(
        issues=[_issue("unsupported_number")],
        artifacts=artifacts,
        broad_retry_available=True,
    )
    assert plan.targets[0].quarantined_evidence_ids == ["verified-fact:f1"]


def test_source_failure_still_quarantines_a_fact_with_a_separate_wording_failure():
    plan = _build_regeneration_plan(
        issues=[_issue("unsupported_number"), _issue("evidence_retrieval_failure")],
        artifacts=_artifacts(),
        broad_retry_available=True,
    )
    assert plan.targets[0].quarantined_evidence_ids == ["verified-fact:f1"]
