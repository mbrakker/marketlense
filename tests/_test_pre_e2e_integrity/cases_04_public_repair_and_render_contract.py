from __future__ import annotations

from copy import deepcopy

from src.contracts.validation import ValidationIssue
from src.generators._artifact_generator.storage import (
    build_executive_advisory_artifacts,
    build_universal_claim_ledger,
)
from src.generators.public_editorial_quality_generator import (
    public_editorial_semantic_review_items,
)
from src.orchestrators._report_analysis_orchestrator.regeneration_plan import (
    _build_regeneration_plan,
)
from src.services._render_service.normalization import (
    _coerce_public_key_figures,
    _coerce_public_metric_spine,
)
from tests.test_verified_facts_validation_authority import _authority_artifacts


def _public_contract_artifacts() -> dict:
    artifacts = deepcopy(_authority_artifacts())
    fact = deepcopy(artifacts["verified_facts"][0])
    evidence_id = f"verified-fact:{fact['fact_id']}"
    metric = {
        "label": "Adoption",
        "value": "42",
        "unit": "%",
        "subject": "buyers",
        "segment": "buyers",
        "cohort": "survey respondents",
        "denominator": "respondents",
        "geography": "Global",
        "timeframe": "2026",
        "observation_status": "observed",
        "forecast_status": "not a forecast",
    }
    artifacts.update(
        {
            "summary": {
                "tldr": "Repeated public finding.",
                "executive_summary": "The report summary is distinct.",
                "claim_evidence_map": [],
            },
            "insights_final": [
                {
                    "id": "insight-1",
                    "text": "Repeated public finding.",
                    "so_what": "Buyer adoption is commercially material.",
                    "now_what": "Plan around buyer adoption.",
                    "metric": deepcopy(metric),
                    "evidence_id": evidence_id,
                    "evidence": fact["statement"],
                }
            ],
            "metric_spine": [
                {
                    "metric_id": "insight-1" if index == 1 else f"metric-{index}",
                    "label": f"Metric {index}",
                    "value": str(index),
                    "unit": "%",
                    "segment": "buyers",
                    "geography": "Global",
                    "timeframe": "2026",
                    "cohort": "survey respondents",
                    "denominator": "respondents",
                    "observation_status": "observed",
                    "forecast_status": "not a forecast",
                    "evidence_id": evidence_id,
                }
                for index in range(1, 7)
            ],
            "key_figures": [
                {
                    "figure_id": f"figure-{index}",
                    "label": f"Figure {index}",
                    "figure": f"{index}%",
                    "cohort": "survey respondents",
                    "denominator": "respondents",
                    "segment": "buyers",
                    "geography": "Global",
                    "timeframe": "2026",
                    "observation_status": "observed",
                    "forecast_status": "not a forecast",
                    "evidence_id": evidence_id,
                }
                for index in range(1, 8)
            ],
            "claim_ledgers": [
                {
                    "canonical_claim_id": (
                        "report:metric_spine:insight-1"
                        if index == 1
                        else f"report:metric_spine:metric-{index}"
                    ),
                    "claim_text": f"Metric {index} is {index}%.",
                    "artifact_section": "metric_spine",
                    "evidence_ids": [evidence_id],
                }
                for index in range(1, 6)
            ],
            "executive_advisory": {
                "decision_brief": {
                    "status": "generated",
                    "strategic_context": "The report summary is distinct.",
                    "decision_implications": [
                        "Buyer adoption is commercially material."
                    ],
                    "priority_moves": ["Plan around buyer adoption."],
                    "watchouts": [],
                    "confidence_note": "Metric spine available",
                    "evidence_links": [evidence_id],
                }
            },
        }
    )
    return artifacts


def test_public_review_uses_render_limits_and_one_complete_metric_card() -> None:
    artifacts = _public_contract_artifacts()

    items = public_editorial_semantic_review_items(artifacts)
    by_artifact = {}
    for item in items:
        by_artifact.setdefault(item["artifact"], []).append(item)

    assert len(by_artifact["metric_spine"]) == 4
    assert len(by_artifact["key_figures"]) == 6
    assert len(by_artifact["claim_ledgers"]) == 4
    assert all(
        "label" in item["text"] or "Metric" in item["text"]
        for item in by_artifact["metric_spine"]
    )
    assert not any(":label" in item["public_item_id"] for item in items)
    assert not any(":value" in item["public_item_id"] for item in items)
    assert {
        item["public_item_id"] for item in items if item["artifact"] == "insights_final"
    } >= {"insight:insight-1:text"}
    assert sum(item["text"] == "Repeated public finding." for item in items) >= 2
    assert not any(
        item["artifact"] == "executive_advisory"
        and item["field"] == "decision_brief.confidence_note"
        for item in items
    )


def test_public_renderer_retains_complete_metric_context_and_status() -> None:
    artifacts = _public_contract_artifacts()

    metric = _coerce_public_metric_spine(artifacts, limit=1)[0]
    figure = _coerce_public_key_figures(artifacts, limit=1)[0]

    for rendered in (metric, figure):
        assert "survey respondents" in rendered["context"]
        assert "respondents" in rendered["context"]
        assert "observed" in rendered["context"]
        assert "not a forecast" in rendered["context"]


def test_derived_metric_claim_context_and_advisory() -> None:
    artifacts = _public_contract_artifacts()
    metric = artifacts["metric_spine"][0]
    advisory = build_executive_advisory_artifacts(
        summary=artifacts["summary"],
        insights_final=artifacts["insights_final"],
        quotes_final=[],
        metric_spine=[metric],
        evidence_packs={},
    )
    ledger = build_universal_claim_ledger(
        report_id="report",
        summary=artifacts["summary"],
        insights_final=artifacts["insights_final"],
        quotes_final=[],
        metric_spine=[metric],
        executive_advisory=advisory,
    )

    metric_claim = next(
        item for item in ledger if item["artifact_section"] == "metric_spine"
    )
    for value in (
        "Global",
        "2026",
        "survey respondents",
        "respondents",
        "observed",
        "not a forecast",
    ):
        assert value in metric_claim["claim_text"]
    assert advisory["decision_brief"]["confidence_note"] == ""


def test_public_derived_claim_routes_to_supported_insight_source() -> None:
    artifacts = _public_contract_artifacts()
    item = next(
        item
        for item in public_editorial_semantic_review_items(artifacts)
        if item["artifact"] == "claim_ledgers"
    )

    assert item["repair_target"] == "insights_bundle"
    assert item["repair_field"] == "insights:insight-1.metric.value"

    issue = ValidationIssue(
        schema_version="1.0",
        message="[public_editorial_quality.semantic_review] incomplete context",
        severity="error",
        affected_section=item["repair_field"],
        rule_id="public_editorial_quality.semantic_review",
        repair_target=item["repair_target"],
        entity_id=item["public_item_id"],
        evidence_ids=list(item["evidence_ids"]),
    )
    plan = _build_regeneration_plan(
        issues=[issue], artifacts=artifacts, broad_retry_available=True
    )

    assert plan.mode == "targeted"
    assert plan.targets[0].allowed_paths == [
        "insights_final[item=insight-1].metric.value"
    ]


def test_public_advisory_implications_route_to_unique_insight_leaves() -> None:
    artifacts = _public_contract_artifacts()
    evidence_id = "verified-fact:fact-1"
    artifacts["insights_final"].append(
        {
            "id": "insight-2",
            "text": "A second source-backed finding.",
            "so_what": "A unique advisory implication.",
            "now_what": "A unique priority move.",
            "evidence_id": evidence_id,
            "evidence": artifacts["verified_facts"][0]["statement"],
        }
    )
    artifacts["executive_advisory"]["decision_brief"].update(
        {
            "decision_implications": ["A unique advisory implication."],
            "priority_moves": ["A unique priority move."],
            "watchouts": ["A second source-backed finding."],
        }
    )

    items = public_editorial_semantic_review_items(artifacts)
    advisory_items = {
        item["field"]: item
        for item in items
        if item["artifact"] == "executive_advisory"
    }

    assert "decision_brief.decision_implications:1" not in advisory_items
    assert "decision_brief.priority_moves:1" not in advisory_items
    assert advisory_items["decision_brief.watchouts:1"]["repair_target"] == (
        "insights_bundle"
    )
    assert advisory_items["decision_brief.watchouts:1"]["repair_field"] == (
        "insights:insight-2.text"
    )
    assert not any(
        item["artifact"] == "executive_advisory"
        and item["text"] == "Buyer adoption is commercially material."
        for item in items
    )


def test_unsupported_derived_public_target_fails_closed_without_planner_crash() -> None:
    artifacts = _public_contract_artifacts()
    issue = ValidationIssue(
        schema_version="1.0",
        message="[public_editorial_quality.semantic_review] derived issue",
        severity="error",
        affected_section="claim:1",
        rule_id="public_editorial_quality.semantic_review",
        repair_target="executive_advisory",
        entity_id="claim_ledgers:report:metric_spine:metric-1",
        evidence_ids=["verified-fact:fact-1"],
    )

    plan = _build_regeneration_plan(
        issues=[issue], artifacts=artifacts, broad_retry_available=True
    )

    assert plan.mode == "skip"
    assert plan.targets == []
    assert plan.unmappable_issues
