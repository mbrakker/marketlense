# ruff: noqa: F401,F403,F405
from __future__ import annotations
from pathlib import Path as _SplitPath

__file__ = str(
    _SplitPath(__file__).resolve().parent.parent / "test_artifact_normalization.py"
)

from ._split_support_test_artifact_normalization import *  # noqa: F401,F403


def test_source_display_preservation_restores_unique_range_qualifiers() -> None:
    insights = [
        {
            "id": "subscriptions",
            "text": "Subscriptions are forecast to increase.",
            "evidence": (
                "Average paid subscriptions are forecast to rise from 4.1 "
                "subscriptions per subscriber today to 5.7 by 2024."
            ),
        }
    ]

    expert_comment, _ = preserve_public_source_displays(
        summary={},
        insights_final=insights,
        expert_comment=(
            "Paid subscriptions are forecast to rise from 4.1 to 5.7, "
            "which changes distribution planning."
        ),
        linkedin_post="",
    )

    assert expert_comment == (
        "Paid subscriptions are forecast to rise from 4.1 subscriptions per "
        "subscriber today to 5.7 by 2024, which changes distribution planning."
    )


def test_source_display_preservation_abstains_for_ambiguous_range_qualifiers() -> None:
    insights = [
        {
            "id": "subscriptions-one",
            "text": "Subscriptions are forecast to increase.",
            "evidence": "Subscriptions rise from 4.1 per user to 5.7 by 2024.",
        },
        {
            "id": "subscriptions-two",
            "text": "Subscriptions are forecast to increase.",
            "evidence": "Subscriptions rise from 4.1 per household to 5.7 by 2024.",
        },
    ]

    expert_comment, _ = preserve_public_source_displays(
        summary={},
        insights_final=insights,
        expert_comment="Subscriptions rise from 4.1 to 5.7.",
        linkedin_post="",
    )

    assert expert_comment == "Subscriptions rise from 4.1 to 5.7."


def test_exact_source_display_survives_ambiguous_shortening() -> None:
    summary = {
        "tldr": "The forecast reaches $3.0T.",
        "card_tldr_compact": "The forecast reaches $3.0T.",
        "executive_summary": "The forecast reaches $3.0T.",
        "claim_evidence_map": [
            {
                "claim": "One displayed source value is already exact.",
                "evidence_id": "forecast",
                "evidence": (
                    "Consumer demand reaches $3.0T while B2B demand reaches $3.2T."
                ),
            }
        ],
    }

    preserve_public_source_displays(
        summary=summary,
        insights_final=[],
        expert_comment="",
        linkedin_post="",
    )

    assert summary["executive_summary"] == "The forecast reaches $3.0T."


def test_fallback_artifact_insights_uses_distinct_grounded_findings_only():
    findings = {
        "findings": [
            {
                "id": "finding_1",
                "text": "Brand tracking identifies funnel drop-offs.",
                "evidence": "The report identifies where audiences drop off.",
                "pages": [4],
            },
            {
                "id": "finding_2",
                "text": "Harmonized data supports cross-market comparison.",
                "evidence": "The report covers more than 50 markets.",
                "pages": [7],
            },
            {
                "id": "finding_1",
                "text": "Brand tracking identifies funnel drop-offs.",
                "evidence": "Duplicate claim with a different locator.",
                "pages": [8],
            },
            {
                "id": "",
                "text": "An unaddressable finding must not be used.",
                "evidence": "No evidence id.",
            },
        ]
    }

    fallback = fallback_artifact_insights_from_findings(findings)

    assert fallback == [
        {
            "id": "finding_1",
            "text": "Brand tracking identifies funnel drop-offs.",
            "evidence_id": "finding_1",
            "evidence": "The report identifies where audiences drop off.",
            "evidence_spans": [],
            "metric": {
                "label": "",
                "value": "",
                "unit": "",
                "trend": "",
                "timeframe": "",
                "geography": "",
                "segment": "",
                "sample_size": "",
                "confidence": "",
            },
            "pages": [4],
        },
        {
            "id": "finding_2",
            "text": "Harmonized data supports cross-market comparison.",
            "evidence_id": "finding_2",
            "evidence": "The report covers more than 50 markets.",
            "evidence_spans": [],
            "metric": {
                "label": "",
                "value": "",
                "unit": "",
                "trend": "",
                "timeframe": "",
                "geography": "",
                "segment": "",
                "sample_size": "",
                "confidence": "",
            },
            "pages": [7],
        },
    ]


def test_fallback_artifact_insights_uses_approved_quote_when_findings_are_short():
    fallback = fallback_artifact_insights_from_evidence(
        {
            "findings": [
                {
                    "id": "finding_1",
                    "text": "Verified market growth remains material.",
                    "evidence": "The market grew 10.5%.",
                    "pages": [2],
                }
            ]
        },
        {
            "quote_candidates": [
                {
                    "id": "quote_1",
                    "text": "Video now accounts for more than half of display.",
                    "source": "Chief Economist, p. 5",
                    "page": 5,
                }
            ]
        },
        limit=2,
    )

    assert [(item["evidence_id"], item["text"]) for item in fallback] == [
        ("finding_1", "Verified market growth remains material."),
        ("quote_1", "Video now accounts for more than half of display."),
    ]
    assert fallback[1]["evidence"] == (
        "Video now accounts for more than half of display."
    )
    assert fallback[1]["pages"] == [5]


def test_insight_candidate_structured_output_failure_defers_to_source_fallback():
    ctx = RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")
    task = ArtifactRenderTask(
        schema_version="1.0",
        step_name="insights_candidates",
        namespace="report_vs/artifacts/insights_candidates",
        variables={},
        ctx=ctx,
    )

    def terminal_model_failure(_: ArtifactRenderTask):
        raise StructuredOutputFailure(
            code="artifact_json_invalid",
            message="Model did not produce a substantive artifact.",
            artifact_family="insights_candidates",
            response_text="not-json",
            repair_attempt=2,
        )

    assert _render_insights_candidates_or_defer_to_fallback(
        task, terminal_model_failure
    ) == {"insights_candidates": [], "_deferred_to_source_fallback": True}


def test_non_candidate_structured_output_failure_is_not_masked():
    ctx = RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")
    task = ArtifactRenderTask(
        schema_version="1.0",
        step_name="summary",
        namespace="report_vs/artifacts/summary",
        variables={},
        ctx=ctx,
    )

    def terminal_model_failure(_: ArtifactRenderTask):
        raise StructuredOutputFailure(
            code="artifact_json_invalid",
            message="Model did not produce a substantive artifact.",
            artifact_family="summary",
            response_text="not-json",
            repair_attempt=2,
        )

    with pytest.raises(StructuredOutputFailure):
        _render_insights_candidates_or_defer_to_fallback(task, terminal_model_failure)


def test_insights_family_abstains_when_fewer_than_two_grounded_claims_exist():
    insights = normalize_artifact_insights(
        [
            {
                "id": "IC1",
                "text": "One supported report theme remains.",
                "evidence_id": "share_of_ear",
                "evidence": "Grounded source evidence.",
            }
        ],
        prefix="insight",
    )

    statuses = build_artifact_family_status(
        summary={},
        insights_candidates=insights,
        insights_final=insights,
        quotes_final=[],
        expert_comment="",
        linkedin_post="",
    )

    assert statuses["insights_bundle"]["status"] == "abstained"
    assert statuses["insights_bundle"]["reason"] == "insights_missing_required_count"


def test_normalize_artifact_insights_repairs_cross_enum_strategy_fields():
    insights = normalize_artifact_insights(
        [
            {
                "id": "i1",
                "text": "Rules changes create implementation risk.",
                "coverage_role": "risk_regulation",
                "report_type_lens": "strategic_risk",
            },
            {
                "id": "i2",
                "text": "Consumer preference shifts affect payment adoption.",
                "coverage_role": "consumer_behavior",
                "report_type_lens": "behavior_shift",
            },
        ],
        prefix="insight",
    )

    assert insights[0]["coverage_role"] == "strategic_risk"
    assert insights[0]["report_type_lens"] == "risk_regulation"
    assert insights[1]["coverage_role"] == "behavior_shift"
    assert insights[1]["report_type_lens"] == "consumer_behavior"


def test_normalize_artifact_insights_drops_unknown_optional_strategy_fields():
    insights = normalize_artifact_insights(
        [
            {
                "id": "i1",
                "text": "Unexpected vocabulary should still reach schema validation.",
                "coverage_role": "not_a_role",
                "report_type_lens": "not_a_lens",
            }
        ],
        prefix="insight",
    )

    assert "coverage_role" not in insights[0]
    assert "report_type_lens" not in insights[0]


def test_select_artifact_insights_fills_required_report_slots_after_theme_coverage():
    """A four-theme plan must not truncate an otherwise grounded five-insight report."""
    plan = {
        "report_thesis": "The report supports five distinct grounded decisions.",
        "themes": [
            {
                "theme": f"Theme {index}",
                "priority": index,
                "evidence_ids": [f"e{index}"],
            }
            for index in range(1, 5)
        ],
    }
    final_insights = [
        {
            "id": f"final-{index}",
            "text": f"Final insight {index}.",
            "evidence_id": f"e{index}",
            "score": 0.9,
        }
        for index in range(1, 5)
    ]
    candidate_insights = [
        {
            "id": "candidate-5",
            "text": "Fifth grounded insight.",
            "evidence_id": "e5",
            "score": 0.8,
        }
    ]

    selected = select_artifact_insights(
        final_insights=final_insights,
        candidate_insights=candidate_insights,
        editorial_plan=plan,
    )

    assert [item["evidence_id"] for item in selected] == ["e1", "e2", "e3", "e4", "e5"]


def test_select_artifact_insights_deduplicates_claims_across_evidence_bindings():
    """Canonical evidence rebinding must not preserve duplicate public claims."""
    plan = {
        "report_thesis": "The report supports five distinct grounded decisions.",
        "themes": [
            {
                "theme": f"Theme {index}",
                "priority": index,
                "evidence_ids": [f"e{index}"],
            }
            for index in range(1, 5)
        ],
    }
    repeated_claim = "Consumers want clearer digital assistant controls."
    final_insights = [
        {
            "id": "final-1",
            "text": "First distinct insight.",
            "evidence_id": "e1",
        },
        {
            "id": "final-2",
            "text": "Second distinct insight.",
            "evidence_id": "e2",
        },
        {
            "id": "final-3",
            "text": "Third distinct insight.",
            "evidence_id": "e3",
        },
        {"id": "final-4", "text": repeated_claim, "evidence_id": "e4"},
        {"id": "final-5", "text": repeated_claim, "evidence_id": "e5"},
    ]
    candidate_insights = [
        {
            "id": "final-1",
            "text": "An alternate rewrite of the first insight.",
            "evidence_id": "e1",
        },
        {
            "id": "final-4",
            "text": "The retained candidate explains assistant boundaries.",
            "evidence_id": "e4",
            "metric": {"value": "76%"},
        },
        {
            "id": "final-5",
            "text": "The retained candidate explains weekly assistant use.",
            "evidence_id": "e5",
            "metric": {"value": "52%"},
        },
    ]

    selected = select_artifact_insights(
        final_insights=final_insights,
        candidate_insights=candidate_insights,
        editorial_plan=plan,
    )

    assert len(selected) == 5
    assert len({item["id"] for item in selected}) == 5
    assert sum(item["text"] == repeated_claim for item in selected) == 0
    selected_by_id = {item["id"]: item for item in selected}
    assert selected_by_id["final-1"]["text"] == "First distinct insight."
    assert selected_by_id["final-4"]["text"] == candidate_insights[1]["text"]
    assert selected_by_id["final-5"]["text"] == candidate_insights[2]["text"]
    assert selected_by_id["final-4"]["metric"]["value"] == "76%"
    assert selected_by_id["final-5"]["metric"]["value"] == "52%"


def test_normalize_artifact_insights_omits_composite_public_metric_fields() -> None:
    insight = normalize_artifact_insights(
        [
            {
                "id": "iab-composite",
                "text": "The insight keeps all supporting figures in its public prose.",
                "evidence_id": "iab-evidence-1",
                "evidence": (
                    "19.2%, $62.1 billion, and $102.9 billion are source-backed."
                ),
                "metric": {
                    "value": "19.2%; $62.1; $102.9; 39.8% growth",
                    "unit": "$ billion; $ billion; share",
                },
            }
        ],
        prefix="insight",
    )[0]

    assert insight["metric"]["value"] == ""
    assert insight["metric"]["unit"] == ""
    assert (
        insight["text"]
        == "The insight keeps all supporting figures in its public prose."
    )
    assert insight["evidence_id"] == "iab-evidence-1"
