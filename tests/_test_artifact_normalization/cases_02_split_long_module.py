# ruff: noqa: F401,F403,F405
from __future__ import annotations

from .cases_01_split_long_module import *  # noqa: F401,F403


def _supported_findings_fidelity(evidence_id: str, statement: str, page: int) -> dict:
    return {
        "results": [
            {
                "candidate": {
                    "claim_id": f"evidence:findings:{evidence_id}",
                    "text": statement,
                    "evidence_references": [
                        {"source_pack": "source_pdf", "page": page}
                    ],
                },
                "status": "supported",
            }
        ]
    }


def test_insight_binding_carries_validated_finding_with_page_excerpt() -> None:
    statement = (
        "In the U.S. in 2017, the top 25% of video users (4.5+ hours of daily "
        "video attention) account for 61% of time spent and 34% of consumer spend; "
        "all other users account for 39% of time spent and 66% of consumer spend."
    )
    excerpt = (
        "VIDEO TIME AND SPEND RELATIVE TO SHARE OF USERS, U.S., 2017, % TOTAL\n"
        "66%\n39%\n34%\n61%\nShare of Time Spent Share of Consumer Spend\n"
        "Top 25% of Users (4.5+ hours of daily video attention) All Other Users"
    )
    insights = [
        {
            "id": "video-attention-and-spend-cohorts",
            "text": (
                "U.S. 2017 video users: top 25% (4.5+ daily video-attention hours), "
                "61% time/34% consumer spend; others, 39% time/66% spend."
            ),
            "evidence_id": "video_super_users_time_spend",
            "evidence": excerpt,
        }
    ]

    bind_artifact_evidence_spans(
        summary={},
        insights_candidates=[],
        insights_final=insights,
        quotes_final=[],
        doc_map={},
        evidence_packs={
            "evidence_fidelity": _supported_findings_fidelity(
                "video_super_users_time_spend", statement, 15
            ),
            "findings": {
                "family_status": {"status": "generated", "policy_action": "keep"},
                "findings": [
                    {
                        "id": "video_super_users_time_spend",
                        "text": statement,
                        "evidence": excerpt,
                        "pages": [15],
                    }
                ],
            },
        },
    )

    assert statement in insights[0]["evidence"]
    assert excerpt in insights[0]["evidence"]
    assert {
        (span["evidence_id"], span["source_pack"], span["page"], span["text"])
        for span in insights[0]["evidence_spans"]
    } == {
        ("video_super_users_time_spend", "findings_statement", 15, statement),
        ("video_super_users_time_spend", "findings", 15, excerpt),
    }

    quality = evaluate_public_editorial_quality(
        report_id="activate-video-cohort", artifacts={"insights_final": insights}
    )
    assert "public_editorial_quality.unsupported_numeric_claim" not in {
        issue.rule_id for issue in quality.issues
    }


def test_reuters_insight_binding_carries_exact_findings_statement_and_page() -> None:
    statement = (
        "For possible licensing deals with AI companies around news content IP, "
        "respondents expected 49% minor contribution and 20% significant source "
        "of income in three years (Base = 272)."
    )
    excerpt = (
        "Half (49%) are expecting a minor contribution.\n"
        "Q8. Possible licensing deals with AI companies around news content IP; "
        "in three years. Base = 272.\n"
        "Main source of income 0%\n"
        "Significant source of income 20%\n"
        "Minor source of income 49%\n"
        "We won't be getting any income 20%\n"
        "Don't know 11%"
    )
    insights = [
        {
            "id": "ai-platform-licensing-income-expectations",
            "text": statement,
            "evidence_id": "section-2-ai-platform-revenue",
            "evidence": excerpt,
        }
    ]

    bind_artifact_evidence_spans(
        summary={},
        insights_candidates=[],
        insights_final=insights,
        quotes_final=[],
        doc_map={},
        evidence_packs={
            "evidence_fidelity": _supported_findings_fidelity(
                "section-2-ai-platform-revenue", statement, 15
            ),
            "findings": {
                "family_status": {"status": "generated", "policy_action": "keep"},
                "findings": [
                    {
                        "id": "section-2-ai-platform-revenue",
                        "text": statement,
                        "evidence": excerpt,
                        "pages": [15],
                    }
                ],
            },
        },
    )

    assert statement in insights[0]["evidence"]
    assert excerpt in insights[0]["evidence"]
    assert {
        (span["evidence_id"], span["source_pack"], span["page"], span["text"])
        for span in insights[0]["evidence_spans"]
    } == {
        (
            "section-2-ai-platform-revenue",
            "findings_statement",
            15,
            statement,
        ),
        ("section-2-ai-platform-revenue", "findings", 15, excerpt),
    }


def test_insight_binding_does_not_promote_abstained_or_doc_map_findings() -> None:
    unsupported_statement = "Top 25% of users account for 66% of time spent."
    excerpt = "66% 39% 34% 61% Share of Time Spent Share of Consumer Spend"
    insights = [
        {
            "id": "insight-1",
            "text": "Top 25% of users account for 66% of time spent.",
            "evidence_id": "video_super_users_time_spend",
            "evidence": "Model supplied text.",
        }
    ]

    bind_artifact_evidence_spans(
        summary={},
        insights_candidates=[],
        insights_final=insights,
        quotes_final=[],
        doc_map={
            "sections": [
                {
                    "id": "video_super_users_time_spend",
                    "summary": unsupported_statement,
                    "key_points": [unsupported_statement],
                    "pages": [15],
                }
            ]
        },
        evidence_packs={
            "findings": {
                "family_status": {"status": "abstained", "policy_action": "abstain"},
                "findings": [
                    {
                        "id": "video_super_users_time_spend",
                        "text": unsupported_statement,
                        "evidence": excerpt,
                        "pages": [15],
                    }
                ],
            }
        },
    )

    assert excerpt in insights[0]["evidence"]
    assert unsupported_statement not in insights[0]["evidence"]
    assert all(
        span["source_pack"] != "findings_statement"
        for span in insights[0]["evidence_spans"]
    )


def test_binding_requires_source_excerpt_before_finding_statement() -> None:
    statement = "Top 25% of users accounted for 61% of time spent."
    insights = [
        {
            "id": "insight-1",
            "text": statement,
            "evidence_id": "finding-1",
            "evidence": "Model supplied text.",
        }
    ]

    bind_artifact_evidence_spans(
        summary={},
        insights_candidates=[],
        insights_final=insights,
        quotes_final=[],
        doc_map={},
        evidence_packs={
            "findings": {
                "family_status": {"status": "generated", "policy_action": "keep"},
                "findings": [
                    {
                        "id": "finding-1",
                        "text": statement,
                        "evidence": "",
                        "pages": [15],
                    }
                ],
            }
        },
    )

    assert insights[0]["evidence"] == "Model supplied text."
    assert insights[0]["evidence_spans"] == []


def test_finding_statement_is_not_promoted_without_matching_fidelity_record() -> None:
    statement = "The top 25% of users accounted for 61% of video time."
    excerpt = "Top 25% of Users 61% Share of Time Spent"
    insights = [
        {
            "id": "insight-1",
            "text": statement,
            "evidence_id": "video-finding",
            "evidence": "Model supplied text.",
        }
    ]

    bind_artifact_evidence_spans(
        summary={},
        insights_candidates=[],
        insights_final=insights,
        quotes_final=[],
        doc_map={},
        evidence_packs={
            "findings": {
                "family_status": {"status": "generated", "policy_action": "keep"},
                "findings": [
                    {
                        "id": "video-finding",
                        "text": statement,
                        "evidence": excerpt,
                        "pages": [15],
                    }
                ],
            }
        },
    )

    assert excerpt in insights[0]["evidence"]
    assert statement not in insights[0]["evidence"]
    assert all(
        span["source_pack"] != "findings_statement"
        for span in insights[0]["evidence_spans"]
    )


def test_finding_statement_requires_exact_fidelity_text_and_source_page() -> None:
    statement = "The top 25% of users accounted for 61% of video time."
    excerpt = "Top 25% of Users 61% Share of Time Spent"
    for fidelity_statement, fidelity_page in (
        (f"{statement} Additional unsupported detail.", 15),
        (statement, 14),
    ):
        insights = [
            {
                "id": "insight-1",
                "text": statement,
                "evidence_id": "video-finding",
                "evidence": excerpt,
            }
        ]
        bind_artifact_evidence_spans(
            summary={},
            insights_candidates=[],
            insights_final=insights,
            quotes_final=[],
            doc_map={},
            evidence_packs={
                "evidence_fidelity": _supported_findings_fidelity(
                    "video-finding", fidelity_statement, fidelity_page
                ),
                "findings": {
                    "family_status": {
                        "status": "generated",
                        "policy_action": "keep",
                    },
                    "findings": [
                        {
                            "id": "video-finding",
                            "text": statement,
                            "evidence": excerpt,
                            "pages": [15],
                        }
                    ],
                },
            },
        )

        assert excerpt in insights[0]["evidence"]
        assert statement not in insights[0]["evidence"]
        assert all(
            span["source_pack"] != "findings_statement"
            for span in insights[0]["evidence_spans"]
        )


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


def test_select_artifact_insights_preserves_bindings_without_duplicate_public_prose():
    """Final wording survives unless distinct facts would publish duplicate prose."""
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
    assert selected_by_id["final-4"]["text"] == (
        "The retained candidate explains assistant boundaries."
    )
    assert selected_by_id["final-5"]["text"] == (
        "The retained candidate explains weekly assistant use."
    )
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
