from __future__ import annotations

from copy import deepcopy

import pytest

from src.contracts.report_assets import RenderRequest
from src.contracts.validation import ValidationIssue
from src.generators._artifact_generator.storage import (
    build_executive_advisory_artifacts,
    build_key_figures,
    build_universal_claim_ledger,
)
from src.generators.artifact_normalization import build_expert_synthesis_context
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
from src.services._render_service.view import _build_render_view
from src.utils.errors import AppError
from tests.test_verified_facts_validation_authority import _authority_artifacts


def test_verified_render_does_not_promote_discovery_methodology_or_chapter_copy(
    tmp_path,
) -> None:
    artifacts = _authority_artifacts()
    artifacts["toc_entries"] = [
        {
            "display_title": "Verified chapter",
            "summary": "UNTRUSTED discovery chapter summary.",
            "pages": [4],
        }
    ]
    discovery_packs = {
        "doc_map": {
            "methodology": (
                "UNTRUSTED discovery methodology. Fieldwork: January 1, 2020 - "
                "January 2, 2020."
            ),
            "sections": [
                {
                    "title": "Discovery-only chapter",
                    "summary": "UNTRUSTED section summary.",
                }
            ],
        },
        "methods": {"methods": [{"description": "UNTRUSTED method pack."}]},
    }
    authoritative_packs = deepcopy(
        artifacts["_cache"]["visual_authority_canary"]["verified_evidence_packs"]
    )

    view = _build_render_view(
        RenderRequest(
            schema_version="1.0",
            data={
                "title": "Verified authority",
                "artifacts": artifacts,
                "evidence_packs": discovery_packs,
                "authoritative_evidence_packs": authoritative_packs,
            },
            doc_name="verified-authority.pdf",
            file_id="verified-authority",
            out_dir=str(tmp_path),
        ),
        {},
    )

    rendered_text = str(view["editorial_cards"]) + str(view["chapters"])
    assert "UNTRUSTED" not in rendered_text
    assert view["fieldwork_dates"] == ""
    assert view["chapters"][0]["title"] == "Verified chapter"
    assert view["chapters"][0]["summary"] == ""
    limitations_card = next(
        card for card in view["editorial_cards"] if card["label"] == "Limitations"
    )
    assert "among buyers" in limitations_card["items"]


def test_verified_expert_context_falls_back_to_fact_qualifiers() -> None:
    context = build_expert_synthesis_context(
        editorial_plan={
            "report_thesis": "The report compares source-backed buyer behavior.",
            "themes": [
                {
                    "theme": "Buyer scope",
                    "priority": 1,
                    "evidence_ids": ["verified-fact:fact-qualifier"],
                },
                {
                    "theme": "Measurement status",
                    "priority": 2,
                    "evidence_ids": ["verified-fact:fact-qualifier-2"],
                },
            ],
        },
        insights_final=[],
        doc_map={},
        evidence_packs={
            "verified_facts": {
                "verified_facts": [
                    {
                        "fact_id": "fact-qualifier",
                        "qualifiers": [
                            "Results cover surveyed buyers only.",
                            "The measure is observed, not a forecast.",
                        ],
                    }
                ]
            }
        },
    )

    assert context["limitations"] == [
        {
            "evidence_id": "verified-fact:fact-qualifier",
            "text": "Results cover surveyed buyers only.",
        },
        {
            "evidence_id": "verified-fact:fact-qualifier",
            "text": "The measure is observed, not a forecast.",
        },
    ]


def test_verified_expert_context_keeps_late_material_qualifiers() -> None:
    qualifiers = [f"Qualifier {index}" for index in range(1, 9)]
    context = build_expert_synthesis_context(
        editorial_plan={
            "report_thesis": "A source-backed thesis.",
            "themes": [
                {
                    "theme": "Observed measure",
                    "priority": 1,
                    "evidence_ids": ["verified-fact:fact-qualifier"],
                },
                {
                    "theme": "Scope and limitations",
                    "priority": 2,
                    "evidence_ids": ["verified-fact:fact-qualifier"],
                },
            ],
        },
        insights_final=[],
        doc_map={},
        evidence_packs={
            "verified_facts": {
                "verified_facts": [
                    {
                        "fact_id": "fact-qualifier",
                        "qualifiers": qualifiers,
                    }
                ]
            }
        },
    )

    assert [item["text"] for item in context["limitations"]] == qualifiers


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
                    "metric_public_copy": "42% of surveyed buyers adopted the product.",
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
                    "metric_public_copy": (
                        f"Metric {index} is {index}% for surveyed buyers."
                    ),
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
                    "metric_public_copy": (
                        f"Figure {index} is {index}% for surveyed buyers."
                    ),
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
    assert len(by_artifact["claim_ledgers"]) == 1
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
    metric["observations"] = ["ignored observation", {"value": "42%"}]
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
    figures = build_key_figures(
        metric_spine=[],
        evidence_packs={},
        insights_final=artifacts["insights_final"],
        verified_mode=True,
    )
    assert figures[0]["forecast_status"] == "not a forecast"


def test_public_derived_claim_routes_to_supported_insight_source() -> None:
    artifacts = _public_contract_artifacts()
    item = next(
        item
        for item in public_editorial_semantic_review_items(artifacts)
        if item["artifact"] == "claim_ledgers"
    )

    assert item["repair_target"] == "insights_bundle"
    assert item["repair_field"] == "insights:insight-1.metric_public_copy"

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
        "insights_final[item=insight-1].metric_public_copy"
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


def test_verified_advisory_items_keep_exact_per_statement_evidence_bindings() -> None:
    artifacts = _public_contract_artifacts()
    first_fact = deepcopy(artifacts["verified_facts"][0])
    second_fact = deepcopy(first_fact)
    second_fact["fact_id"] = "fact-2"
    second_fact["statement"] = "Adoption reached 58% among enterprise buyers in 2026."
    second_fact["metric"] = deepcopy(second_fact["metric"])
    second_fact["metric"]["value"] = "58%"
    artifacts["verified_facts"] = [first_fact, second_fact]
    first_evidence_id = "verified-fact:fact-1"
    second_evidence_id = "verified-fact:fact-2"
    decision = artifacts["executive_advisory"]["decision_brief"]
    decision.update(
        {
            "decision_implications": [
                "First fact requires a focused margin response.",
                "Second fact requires an enterprise adoption response.",
            ],
            "evidence_links": [first_evidence_id, second_evidence_id],
            "evidence_links_by_item": {
                "decision_implications": [
                    {
                        "text": "First fact requires a focused margin response.",
                        "evidence_ids": [first_evidence_id],
                    },
                    {
                        "text": "Second fact requires an enterprise adoption response.",
                        "evidence_ids": [second_evidence_id],
                    },
                ]
            },
        }
    )

    items = public_editorial_semantic_review_items(artifacts)
    by_text = {
        item["text"]: item for item in items if item["artifact"] == "executive_advisory"
    }

    assert by_text["First fact requires a focused margin response."][
        "evidence_ids"
    ] == [first_evidence_id]
    assert by_text["Second fact requires an enterprise adoption response."][
        "evidence_ids"
    ] == [second_evidence_id]


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


def test_verified_projection_covers_rendered_families_and_ambiguous_sources() -> None:
    artifacts = _public_contract_artifacts()
    evidence_id = "verified-fact:fact-1"
    artifacts["topics_covered"] = [
        {
            "id": "topic-1",
            "title": "Adoption",
            "summary": "The report covers adoption.",
            "subtopics": ["Buyer segments"],
            "pages": [4],
            "evidence_ids": [evidence_id],
        },
        {"title": "", "evidence_ids": [evidence_id]},
    ]
    artifacts["chart_insight_cards"] = [
        {
            "candidate_id": "chart-1",
            "insight_id": "insight-1",
            "evidence_id": evidence_id,
            "source_page": 4,
            "caption": "Adoption by buyer segment",
            "public_takeaway": "Buyer adoption reached 42%.",
            "so_what": "Buyer adoption is commercially material.",
            "now_what": "Plan around buyer adoption.",
            "crop_qa_accepted": True,
        },
        {"candidate_id": "chart-weak", "evidence_id": evidence_id},
    ]
    artifacts["quotes_final"] = [
        {"id": "quote-1", "text": "A source-backed quote.", "evidence_id": evidence_id},
        {"id": "quote-empty", "text": "", "evidence_id": evidence_id},
    ]
    artifacts["summary"]["claim_evidence_map"] = [
        {"claim": "A grounded summary claim.", "evidence_ids": [evidence_id]},
        {"claim": "Unbound summary claim.", "evidence_ids": []},
        {"claim": "", "evidence_ids": [evidence_id]},
        "ignored non-mapping summary entry",
    ]
    artifacts["summary"]["card_tldr_compact"] = "Hidden compact summary copy."
    artifacts["claim_ledgers"] = [
        {
            "canonical_claim_id": "report:insights_final:insight-1",
            "artifact_section": "insights_final",
            "claim_text": "Repeated public finding.",
            "evidence_ids": [evidence_id],
        },
        {
            "canonical_claim_id": "report:quotes_final:1",
            "artifact_section": "quotes_final",
            "claim_text": "A source-backed quote.",
            "evidence_ids": [evidence_id],
        },
        {
            "canonical_claim_id": "report:summary.claim_evidence_map:summary-1",
            "artifact_section": "summary.claim_evidence_map",
            "claim_text": "A grounded summary claim.",
            "evidence_ids": [evidence_id],
        },
        {
            "canonical_claim_id": "report:executive_advisory:1",
            "artifact_section": "executive_advisory.decision_brief",
            "claim_text": "Buyer adoption is commercially material.",
            "evidence_ids": [evidence_id],
        },
    ]
    artifacts["insights_candidates"] = [
        {
            "id": "candidate-only",
            "text": "Candidate-only finding.",
            "metric_public_copy": "7% for the candidate-only cohort.",
            "metric": {"value": "7"},
            "evidence_id": evidence_id,
        }
    ]
    artifacts["metric_spine"] = [
        {
            "metric_id": "candidate-only",
            "label": "Candidate metric",
            "value": "7",
            "unit": "%",
            "metric_public_copy": "7% for the candidate-only cohort.",
            "evidence_id": evidence_id,
        },
        {
            "metric_id": "insight-2",
            "label": "Unbound metric",
            "value": "8",
            "unit": "%",
            "evidence_id": evidence_id,
        },
    ]
    artifacts["summary"]["claim_evidence_map"][0]["id"] = "summary-1"
    artifacts["insights_final"].append(
        {"text": "Missing identity should not authorize a repair."}
    )
    artifacts["executive_advisory"]["decision_brief"].update(
        {
            "evidence_ids": [evidence_id],
            "strategic_context": "Repeated public finding.",
            "confidence_note": "Second source-backed finding.",
            "decision_implications": [
                "Buyer adoption is commercially material.",
                "A second implication.",
            ],
            "priority_moves": [
                "Plan around buyer adoption.",
                "A second move.",
            ],
        }
    )
    artifacts["insights_final"].append(
        {
            "id": "insight-2",
            "text": "Second source-backed finding.",
            "so_what": "A second implication.",
            "now_what": "A second move.",
            "evidence_id": evidence_id,
            "evidence": "The source supports a second finding.",
        }
    )
    artifacts["insights_final"].append(
        {
            "id": "insight-ambiguous",
            "text": "Ambiguous advisory source.",
            "so_what": "Ambiguous advisory source.",
            "now_what": "Use the buyer cohort.",
            "evidence_id": evidence_id,
            "evidence": "The source supports an ambiguous advisory source.",
        }
    )
    artifacts["executive_advisory"]["decision_brief"]["watchouts"] = [
        "Ambiguous advisory source."
    ]

    items = public_editorial_semantic_review_items(artifacts)
    by_artifact = {}
    for item in items:
        by_artifact.setdefault(item["artifact"], []).append(item)

    assert by_artifact["topics_covered"]
    assert by_artifact["chart_insight_cards"][0]["repair_target"] == ("insights_bundle")
    assert by_artifact["quotes_final"][0]["repair_target"] == "quotes"
    assert any(
        item["repair_field"] == "summary.claim_evidence_map:summary-1.claim"
        for item in by_artifact["claim_ledgers"]
    )
    assert any(
        item["repair_field"] == "insights:insight-1.text"
        for item in by_artifact["claim_ledgers"]
    )
    assert any(
        item["repair_field"] == "insights:candidate-only.metric_public_copy"
        for item in by_artifact["metric_spine"]
    )
    assert not any(
        item["text"] in {"Metric spine available", "Evidence-linked insights available"}
        for item in by_artifact["executive_advisory"]
    )

    artifacts["claim_ledgers"] = [
        {
            "canonical_claim_id": "report:summary.claim_evidence_map:1",
            "artifact_section": "summary.claim_evidence_map",
            "claim_text": "A grounded summary claim.",
            "evidence_ids": [evidence_id],
        }
    ]
    numeric_summary_items = public_editorial_semantic_review_items(artifacts)
    numeric_summary_claim = next(
        item for item in numeric_summary_items if item["artifact"] == "claim_ledgers"
    )
    assert numeric_summary_claim["repair_field"] == "summary.claim_evidence_map:1.claim"

    duplicate = deepcopy(artifacts["insights_final"][0])
    artifacts["insights_final"].append(duplicate)
    duplicate_items = public_editorial_semantic_review_items(artifacts)
    duplicate_ids = [str(item["public_item_id"]) for item in duplicate_items]
    assert len(duplicate_ids) == len(set(duplicate_ids))

    conflicting_duplicate = deepcopy(artifacts["insights_final"][0])
    conflicting_duplicate["text"] = "A different visible proposition."
    artifacts["insights_final"].append(conflicting_duplicate)
    with pytest.raises(AppError) as raised:
        public_editorial_semantic_review_items(artifacts)
    assert raised.value.code == "public_editorial_review_identity_conflict"

    invalid_binding = _public_contract_artifacts()
    invalid_binding["chart_insight_cards"] = [
        {
            "candidate_id": "wrong-page",
            "insight_id": "insight-1",
            "evidence_id": evidence_id,
            "source_page": 3,
            "caption": "Adoption by buyer segment",
            "public_takeaway": "Buyer adoption reached 42%.",
            "crop_qa_accepted": True,
        }
    ]
    invalid_items = public_editorial_semantic_review_items(invalid_binding)
    assert not any(item["artifact"] == "executive_advisory" for item in invalid_items)
