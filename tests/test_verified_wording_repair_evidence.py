from copy import deepcopy

from src.contracts.soft_copy_claim_provenance import (
    soft_copy_claim_provenance_to_payload,
)
from src.contracts.validation import ValidationIssue
from src.generators.soft_copy_claim_provenance import build_soft_copy_claim_provenance
from src.orchestrators._report_analysis_orchestrator.regeneration_plan import (
    _build_regeneration_plan,
    _normalize_regeneration_issue,
)


def _artifacts() -> dict:
    identity = "report|pdf-sha256:" + "a" * 64
    fact = {
        "schema_version": "1.0",
        "fact_id": "f1",
        "statement": "A source fact.",
        "metric": {},
        "qualifiers": [],
        "source_identity": identity,
        "source_pdf_sha256": "a" * 64,
        "supporting_physical_pages": [1],
        "verification_outcome": "verified",
        "provenance": {
            "inspected_physical_pages": [1],
            "source_truth_notes_by_page": {"1": "A source fact."},
        },
    }
    insight = {
        "id": "i1",
        "text": "Unsupported extra assertion.",
        "evidence_id": "verified-fact:f1",
    }
    return {
        "verified_facts": [fact],
        "insights_final": [insight],
        "insights_candidates": [deepcopy(insight)],
        "key_figures": [{"insight_id": "i1", "evidence_id": "verified-fact:f1"}],
    }


def test_verified_wording_repair_keeps_canonical_fact_for_insight_and_figure() -> None:
    issues = [
        ValidationIssue(
            rule_id="grounding",
            severity="error",
            violation_type="not_established",
            classification="factual_claim",
            entity_id=entity,
            affected_section=section,
            evidence_ids=["verified-fact:f1"],
            message="The extra assertion is not established.",
        )
        for entity, section in [
            ("insight:i1:text", "insights:i1.text"),
            ("key_figure:1:why_it_matters", "key_figures:1.why_it_matters"),
        ]
    ]
    plan = _build_regeneration_plan(
        issues=issues, artifacts=_artifacts(), broad_retry_available=True
    )
    target = next(
        item for item in plan.targets if item.target_section == "insights_bundle"
    )
    assert target.quarantined_evidence_ids == []
    assert "verified-fact:f1" in target.selected_evidence_ids


def test_invalid_canonical_identity_stays_quarantined() -> None:
    artifacts = _artifacts()
    artifacts["verified_facts"][0]["source_pdf_sha256"] = "b" * 64
    issue = ValidationIssue(
        rule_id="grounding",
        severity="error",
        violation_type="not_established",
        classification="factual_claim",
        entity_id="insight:i1:text",
        affected_section="insights:i1.text",
        evidence_ids=["verified-fact:f1"],
        message="The assertion is not established.",
    )
    plan = _build_regeneration_plan(
        issues=[issue], artifacts=artifacts, broad_retry_available=True
    )
    assert plan.targets[0].quarantined_evidence_ids == ["verified-fact:f1"]


def test_unmatched_binding_stays_quarantined() -> None:
    issue = ValidationIssue(
        rule_id="grounding",
        severity="error",
        violation_type="not_established",
        classification="factual_claim",
        entity_id="insight:i1:text",
        affected_section="insights:i1.text",
        evidence_ids=["verified-fact:unknown"],
        message="The assertion is not established.",
    )
    plan = _build_regeneration_plan(
        issues=[issue], artifacts=_artifacts(), broad_retry_available=True
    )
    assert plan.targets[0].quarantined_evidence_ids == ["verified-fact:unknown"]


def test_missing_claim_qualifier_does_not_quarantine_valid_verified_fact() -> None:
    issue = ValidationIssue(
        rule_id="grounding",
        severity="error",
        affected_section="insights:i1.text",
        entity_id="insight:i1:text",
        violation_type="missing_material_evidence",
        entailment_outcome="not_established",
        evidence_ids=["verified-fact:f1"],
        message="The claim omits the fact's timeframe.",
    )
    result = _normalize_regeneration_issue(issue, _artifacts())
    assert result.excluded_evidence_ids == []


def test_missing_qualifier_still_quarantines_invalid_source_identity() -> None:
    artifacts = _artifacts()
    artifacts["verified_facts"][0]["source_pdf_sha256"] = "b" * 64
    issue = ValidationIssue(
        rule_id="grounding",
        severity="error",
        affected_section="insights:i1.text",
        entity_id="insight:i1:text",
        violation_type="missing_material_evidence",
        entailment_outcome="not_established",
        evidence_ids=["verified-fact:f1"],
        message="The claim omits the fact's timeframe.",
    )
    result = _normalize_regeneration_issue(issue, artifacts)
    assert result.excluded_evidence_ids == ["verified-fact:f1"]


def test_source_retrieval_failure_still_quarantines_verified_fact() -> None:
    issue = ValidationIssue(
        rule_id="grounding",
        severity="error",
        affected_section="insights:i1.text",
        entity_id="insight:i1:text",
        violation_type="evidence_retrieval_failure",
        entailment_outcome="not_established",
        evidence_ids=["verified-fact:f1"],
        message="The source could not be retrieved.",
    )
    result = _normalize_regeneration_issue(issue, _artifacts())
    assert result.excluded_evidence_ids == ["verified-fact:f1"]


def test_soft_copy_missing_qualifier_keeps_its_canonical_binding() -> None:
    artifacts = _artifacts()
    text = "The measured share was 61%."
    artifacts["linkedin_post"] = text
    claims = build_soft_copy_claim_provenance(
        artifact_family="linkedin_post",
        text=text,
        declared_claims=[
            {
                "claim": text,
                "classification": "factual",
                "evidence_ids": ["verified-fact:f1"],
            }
        ],
        evidence_span_index={},
        producing_prompt_identity={},
        generation_attempt=1,
        regeneration_attempt=0,
    )
    artifacts["soft_copy_claim_provenance"] = soft_copy_claim_provenance_to_payload(
        claims
    )
    issue = ValidationIssue(
        rule_id="grounding",
        severity="error",
        affected_section="linkedin_post",
        entity_id=claims[0].claim_id,
        violation_type="missing_material_evidence",
        entailment_outcome="not_established",
        evidence_ids=["verified-fact:f1"],
        message="The claim omits its timeframe.",
    )
    result = _normalize_regeneration_issue(issue, artifacts)
    assert result.excluded_evidence_ids == []
