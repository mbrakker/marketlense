from copy import deepcopy

from src.contracts.validation import ValidationIssue
from src.orchestrators._report_analysis_orchestrator.regeneration_plan import (
    _build_regeneration_plan,
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
