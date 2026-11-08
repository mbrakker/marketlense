from __future__ import annotations

from pathlib import Path

import pytest

from src.contracts.report_assets import RenderRequest
from src.generators.public_editorial_quality_generator import (
    evaluate_public_editorial_quality,
    public_editorial_report_review_scope,
    public_editorial_semantic_review_items,
)
from src.orchestrators._report_analysis_orchestrator.validation import (
    _validate_public_editorial_review_payload,
)
from src.services.render_service import render_report
from src.utils.errors import AppError
from tests._test_validation_generator._shared import _ctx
from tests.test_verified_facts_validation_authority import _authority_artifacts


def _report_review_verdict(
    *,
    status: str = "pass",
    evidence_ids: list[str] | None = None,
    affected_item_id: str = "",
    repair_target: str = "",
    coverage_status: str = "pass",
) -> dict:
    return {
        "status": status,
        "severity": "info" if status == "pass" else "error",
        "rule_id": (
            "" if status == "pass" else "public_editorial_quality.report_acceptance"
        ),
        "hard_fail_class": "" if status == "pass" else "report_editorial_acceptance",
        "reason": "The final report is assessed against its retained source context.",
        "evidence_ids": list(evidence_ids or []),
        "repair_target": repair_target,
        "affected_item_id": affected_item_id,
        "dimensions": {
            "material_coverage": {
                "status": coverage_status,
                "reason": "The admitted findings are or are not materially covered.",
            },
            "analytical_depth": {
                "status": "pass",
                "reason": "The report contains defensible interpretation.",
            },
            "distinctness": {
                "status": "pass",
                "reason": "The selected items remain distinct and coherent.",
            },
            "limitations": {
                "status": "pass",
                "reason": "Material boundaries and uncertainty are represented.",
            },
        },
    }


def _add_valid_obligation_contract(
    items: list[dict], scope: dict, payload: dict
) -> None:
    insight_items = [
        item
        for item in items
        if item.get("artifact") == "insights_final"
        and (
            item.get("field") in {"text", "so_what", "now_what"}
            or str(item.get("field") or "").startswith("insights:")
        )
    ]
    scope["original_editorial_plan_coverage"] = {
        "original_plan_identity": "test-plan",
        "original_essential_obligations": [
            {
                "theme": "Verified essential theme",
                "evidence_ids": ["verified-fact:fact-1"],
                "importance": "essential",
                "coverage_obligation": "Retain the verified analytical theme.",
            }
        ],
    }
    payload["original_essential_obligation_assessments"] = [
        {
            "theme": "Verified essential theme",
            "evidence_ids": ["verified-fact:fact-1"],
            "status": "covered",
            "supporting_insight_ids": [str(insight_items[0]["public_item_id"])],
            "explanation": (
                "The retained final insight develops the verified essential "
                "theme with the authorized fact."
            ),
        }
    ]


def _valid_report_review_payload() -> tuple[list[dict], dict, dict]:
    artifacts = _authority_artifacts()
    items = public_editorial_semantic_review_items(artifacts)
    scope = public_editorial_report_review_scope(artifacts, items)
    payload = {
        "verdicts": [
            {
                "item_id": str(item["public_item_id"]),
                "status": "pass",
                "classification": "factual_claim",
                "severity": "info",
                "rule_id": "",
                "hard_fail_class": "",
                "reason": "The item remains supported by its retained source context.",
                "evidence_ids": list(item.get("evidence_ids") or []),
                "repair_target": "",
            }
            for item in items
        ],
        "report_verdict": _report_review_verdict(evidence_ids=["verified-fact:fact-1"]),
    }
    _add_valid_obligation_contract(items, scope, payload)
    return items, scope, payload


@pytest.mark.parametrize(
    ("mutation", "expected_type"),
    [
        (
            lambda payload: payload["verdicts"][0].update(severity="error"),
            "item_pass_contains_failure_fields",
        ),
        (
            lambda payload: payload["verdicts"][0].update(
                rule_id="public_editorial_quality.semantic_integrity"
            ),
            "item_pass_contains_failure_fields",
        ),
        (
            lambda payload: payload["verdicts"][0].update(
                hard_fail_class="unsupported_claim"
            ),
            "item_pass_contains_failure_fields",
        ),
        (
            lambda payload: payload["verdicts"][0].update(
                status="fail", severity="warning"
            ),
            "item_failure_severity_not_error",
        ),
        (
            lambda payload: payload["verdicts"][0].update(
                status="fail", severity="error", rule_id="", hard_fail_class=""
            ),
            "item_failure_classification_missing",
        ),
    ],
)
def test_public_item_status_contract_is_fail_closed(mutation, expected_type) -> None:
    items, scope, payload = _valid_report_review_payload()
    mutation(payload)

    with pytest.raises(AppError) as raised:
        _validate_public_editorial_review_payload(payload, items, _ctx(), scope)

    assert raised.value.code == "public_editorial_quality_review_status_conflict"
    assert raised.value.context["status_conflict_type"] == expected_type
    assert "model" not in str(raised.value.context).casefold()


@pytest.mark.parametrize(
    ("mutation", "expected_type"),
    [
        (
            lambda payload: payload["report_verdict"].update(severity="error"),
            "report_pass_contains_failure_fields",
        ),
        (
            lambda payload: payload["report_verdict"].update(
                rule_id="public_editorial_quality.report_acceptance"
            ),
            "report_pass_contains_failure_fields",
        ),
        (
            lambda payload: payload["report_verdict"].update(
                affected_item_id="insight:fact-1"
            ),
            "report_pass_contains_failure_fields",
        ),
        (
            lambda payload: payload["report_verdict"].update(
                status="fail",
                dimensions=_report_review_verdict(
                    status="fail", coverage_status="fail"
                )["dimensions"],
                severity="warning",
            ),
            "report_failure_severity_not_error",
        ),
        (
            lambda payload: payload["report_verdict"].update(
                status="fail",
                severity="error",
                rule_id="",
                hard_fail_class="",
                dimensions=_report_review_verdict(
                    status="fail", coverage_status="fail"
                )["dimensions"],
            ),
            "report_failure_classification_missing",
        ),
    ],
)
def test_public_report_status_contract_is_fail_closed(mutation, expected_type) -> None:
    items, scope, payload = _valid_report_review_payload()
    mutation(payload)

    with pytest.raises(AppError) as raised:
        _validate_public_editorial_review_payload(payload, items, _ctx(), scope)

    assert raised.value.code == "public_editorial_quality_report_review_status_conflict"
    assert raised.value.context["status_conflict_type"] == expected_type
    assert "model" not in str(raised.value.context).casefold()


def test_semantic_review_projection_includes_all_public_surface_fields() -> None:
    artifacts = _authority_artifacts()
    evidence_id = "verified-fact:fact-1"
    evidence = artifacts["verified_facts"][0]["statement"]
    artifacts["key_figures"] = [
        {
            "label": "Adoption",
            "figure": "42%",
            "metric_public_copy": "42% of surveyed buyers adopted the product.",
            "why_it_matters": "Buyer adoption is commercially material.",
            "evidence_id": evidence_id,
            "evidence": evidence,
        }
    ]
    artifacts["metric_spine"] = [
        {
            "label": "Retention",
            "value": "77",
            "unit": "%",
            "metric_public_copy": "Retention reached 77% in the surveyed cohort.",
            "evidence_id": evidence_id,
            "evidence": evidence,
        }
    ]
    artifacts["quotes_final"] = [
        {"id": "quote-1", "text": evidence, "evidence_id": evidence_id}
    ]
    artifacts["chart_insight_cards"] = [
        {
            "title": "Adoption",
            "caption": "42% among buyers in 2026.",
            "public_takeaway": "Buyer adoption is commercially material.",
            "status": "accepted",
            "crop_qa_accepted": True,
            "candidate_id": "candidate-1",
            "source_page": 4,
            "insight_id": "fact-1",
            "evidence_id": evidence_id,
            "evidence": evidence,
        }
    ]

    item_ids = {
        str(item["public_item_id"])
        for item in public_editorial_semantic_review_items(artifacts)
    }

    assert {
        "key_figures:key_figures:1",
        "metric_spine:metric_spine:1",
        "chart_insight_cards:chart_insight_cards:candidate-1",
    } <= item_ids
    assert "quotes_final:quotes:quote-1" in item_ids
    assert "key_figures:key_figures:1:why_it_matters" not in item_ids
    assert "chart_insight_cards:chart_insight_cards:1:title" not in item_ids

    quality = evaluate_public_editorial_quality(
        report_id="public-surface-projection", artifacts=artifacts
    )
    assert quality.status == "pass"


def test_semantic_review_projection_matches_rendered_material_surfaces() -> None:
    artifacts = _authority_artifacts()
    evidence_id = "verified-fact:fact-1"
    artifacts.update(
        {
            "toc_topics": ["Adoption"],
            "toc_topics_expanded": [
                {
                    "section_id": "adoption",
                    "title": "Adoption",
                    "summary": "Adoption is the report's central theme.",
                }
            ],
            "topics_covered": [
                {
                    "topic": "Adoption",
                    "status": "source_backed",
                    "why_it_matters": "Adoption is the report's central theme.",
                    "subtopics": ["Buyer adoption reached 42%."],
                    "pages": [4],
                }
            ],
            "metric_spine": [
                {
                    "label": "Adoption",
                    "value": "42",
                    "unit": "%",
                    "segment": "buyers",
                    "timeframe": "2026",
                    "evidence_id": evidence_id,
                }
            ],
            "executive_advisory": {
                "decision_brief": {
                    "status": "generated",
                    "strategic_context": "Adoption is the decision context.",
                    "decision_implications": ["Plan around buyer adoption."],
                    "priority_moves": ["Protect the adoption funnel."],
                    "watchouts": ["Do not generalize beyond buyers."],
                    "evidence_links": [evidence_id],
                    "evidence_links_by_item": {
                        "decision_implications": [
                            {
                                "text": "Plan around buyer adoption.",
                                "evidence_ids": [evidence_id],
                            }
                        ],
                        "priority_moves": [
                            {
                                "text": "Protect the adoption funnel.",
                                "evidence_ids": [evidence_id],
                            }
                        ],
                        "watchouts": [
                            {
                                "text": "Do not generalize beyond buyers.",
                                "evidence_ids": [evidence_id],
                            }
                        ],
                    },
                }
            },
            "claim_ledgers": [
                {
                    "claim_text": "Buyer adoption reached 42%.",
                    "evidence_ids": [evidence_id],
                    "support_type": "source_backed",
                }
            ],
            "chart_insight_cards": [
                {
                    "title": "Weak card",
                    "caption": "Weak evidence card.",
                    "public_takeaway": "Weak evidence should not render.",
                    "so_what": "Weak card implication.",
                    "now_what": "Weak card action.",
                    "status": "weak",
                    "crop_qa_accepted": True,
                    "candidate_id": "candidate-weak",
                    "evidence_id": evidence_id,
                    "source_page": 4,
                    "insight_id": "weak",
                },
                {
                    "title": "Accepted card",
                    "caption": "Accepted evidence card.",
                    "public_takeaway": "Buyer adoption is commercially material.",
                    "so_what": "Prioritize adoption-led growth.",
                    "now_what": "Measure adoption by buyer cohort.",
                    "status": "accepted",
                    "crop_qa_accepted": True,
                    "candidate_id": "candidate-accepted",
                    "evidence_id": evidence_id,
                    "source_page": 4,
                    "insight_id": "fact-1",
                },
            ],
        }
    )

    items = public_editorial_semantic_review_items(artifacts)
    item_ids = {str(item["public_item_id"]) for item in items}
    item_text = {str(item["text"]) for item in items}

    assert "chart_insight_cards:chart_insight_cards:candidate-weak" not in item_ids
    assert "chart_insight_cards:chart_insight_cards:candidate-accepted" in item_ids
    assert "Weak evidence should not render." not in item_text
    assert any("Adoption" in value for value in item_text)
    assert any(
        "Buyer adoption is commercially material." in value for value in item_text
    )
    assert any("Plan around buyer adoption." in value for value in item_text)
    assert any("Buyer adoption reached 42%." in value for value in item_text)


def test_verified_signal_review_and_renderer_omit_unbound_topic_copy(tmp_path) -> None:
    artifacts = _authority_artifacts()
    evidence_id = "verified-fact:fact-1"
    artifacts.update(
        {
            "toc_topics": ["Bound topic", "Unbound topic"],
            "toc_topics_expanded": [
                {"title": "Bound topic", "summary": "Bound summary."},
                {"title": "Unbound topic", "summary": "Unbound summary."},
            ],
            "topics_covered": [
                {
                    "topic": "Bound topic",
                    "status": "source_backed",
                    "evidence_id": evidence_id,
                    "why_it_matters": "Bound summary.",
                },
                {
                    "topic": "Unbound topic",
                    "status": "source_backed",
                    "why_it_matters": "Unbound summary.",
                },
            ],
        }
    )

    items = public_editorial_semantic_review_items(artifacts)
    item_text = {str(item["text"]) for item in items}
    assert any(
        "Bound topic" in value and "Bound summary." in value for value in item_text
    )
    assert "Unbound summary." not in item_text

    response = render_report(
        RenderRequest(
            schema_version="1.0",
            data={
                "title": "Signal authority regression",
                "publisher": "Publisher",
                "taxonomy": [],
                "artifacts": artifacts,
            },
            doc_name="signal-authority-regression.pdf",
            file_id="signal-authority-regression",
            out_dir=str(tmp_path),
        ),
        _ctx(),
    )
    html = Path(response.html_path).read_text(encoding="utf-8")
    assert "Bound topic" in html
    assert "Unbound summary." not in html


def test_verified_render_does_not_fallback_to_legacy_public_content(tmp_path) -> None:
    artifacts = {
        "verified_facts": [_authority_artifacts()["verified_facts"][0]],
        "family_status": {
            "summary": {"status": "abstained", "reason": "weak"},
            "insights_bundle": {"status": "abstained", "reason": "weak"},
            "quotes": {"status": "abstained", "reason": "weak"},
        },
        "summary": {},
        "insights_final": [],
        "quotes_final": [],
    }
    response = render_report(
        RenderRequest(
            schema_version="1.0",
            data={
                "title": "Verified fallback boundary",
                "tldr": "LEGACY TLDR MUST NOT RENDER",
                "commentary": "LEGACY COMMENTARY MUST NOT RENDER",
                "insights": ["LEGACY INSIGHT MUST NOT RENDER"],
                "quote": {"text": "LEGACY QUOTE MUST NOT RENDER"},
                "artifacts": artifacts,
            },
            doc_name="verified-fallback.pdf",
            file_id="verified-fallback",
            out_dir=str(tmp_path),
        ),
        _ctx(),
    )

    html = Path(response.html_path).read_text(encoding="utf-8")
    assert "LEGACY TLDR MUST NOT RENDER" not in html
    assert "LEGACY COMMENTARY MUST NOT RENDER" not in html
    assert "LEGACY INSIGHT MUST NOT RENDER" not in html
    assert "LEGACY QUOTE MUST NOT RENDER" not in html
