from copy import deepcopy

import pytest

from src.contracts.run_context import RunContext
from src.generators._artifact_generator.family_policy import (
    build_artifact_family_status,
)
from src.generators.artifact_normalization import (
    bind_artifact_evidence_spans,
    fallback_artifact_insights_from_findings,
    normalize_artifact_insights,
    normalize_artifact_summary,
    preserve_public_source_displays,
    select_artifact_insights,
    strip_linkedin_inline_reference_ids,
)
from src.generators.public_editorial_quality_generator import (
    evaluate_public_editorial_quality,
)
from src.services.schema_validator_service import validate_output_schema
from src.utils.errors import AppError


def test_normalize_artifact_insights_preserves_metric_label_scoring_and_strategy_fields() -> (
    None
):
    insights = normalize_artifact_insights(
        [
            {
                "id": "i1",
                "text": "Wallet adoption changes checkout planning.",
                "evidence_id": "f1",
                "evidence": "Wallet adoption is rising.",
                "metric": {
                    "label": "Enterprise wallet adoption",
                    "value": "42",
                    "unit": "percent",
                },
                "pages": [4],
                "score": 0.91,
                "decision_relevance_score": 0.95,
                "metric_strength_score": 0.8,
                "novelty_score": 0.7,
                "coverage_role": "operating_implication",
                "so_what": (
                    "Checkout teams need to treat wallets as core infrastructure."
                ),
                "now_what": (
                    "Prioritize wallet coverage in payment orchestration roadmaps."
                ),
                "report_type_lens": "operations",
            }
        ],
        prefix="insight",
    )

    assert insights == [
        {
            "id": "i1",
            "text": "Wallet adoption changes checkout planning.",
            "evidence_id": "f1",
            "evidence": "Wallet adoption is rising.",
            "evidence_spans": [],
            "metric": {
                "label": "Enterprise wallet adoption",
                "value": "42",
                "unit": "percent",
                "trend": "",
                "timeframe": "",
                "geography": "",
                "segment": "",
                "sample_size": "",
                "confidence": "",
            },
            "pages": [4],
            "coverage_role": "operating_implication",
            "so_what": "Checkout teams need to treat wallets as core infrastructure.",
            "now_what": "Prioritize wallet coverage in payment orchestration roadmaps.",
            "report_type_lens": "operations",
            "score": 0.91,
            "decision_relevance_score": 0.95,
            "metric_strength_score": 0.8,
            "novelty_score": 0.7,
        }
    ]


def test_normalize_artifact_insights_preserves_numeric_relationship_binding() -> None:
    insights = normalize_artifact_insights(
        [
            {
                "id": "super-users",
                "text": "Super Users account for 59% of total eCommerce spend.",
                "evidence_id": "finding-super-users",
                "evidence": (
                    "Super Users are 23% of users and account for 59% of total "
                    "eCommerce spend."
                ),
                "metric": {
                    "label": "Share of eCommerce spend",
                    "value": "59%",
                    "subject": "Super Users",
                    "cohort": "technology and media users",
                    "denominator": "total eCommerce spend",
                    "observation_status": "observed",
                },
            }
        ],
        prefix="insight",
    )

    assert insights[0]["metric"] == {
        "label": "Share of eCommerce spend",
        "value": "59%",
        "unit": "",
        "trend": "",
        "timeframe": "",
        "geography": "",
        "segment": "",
        "sample_size": "",
        "confidence": "",
        "subject": "Super Users",
        "cohort": "technology and media users",
        "denominator": "total eCommerce spend",
        "observation_status": "observed",
    }


@pytest.mark.parametrize("root_key", ["insights_candidates", "insights_final"])
def test_insight_metric_value_requires_a_human_readable_label_in_output_schema(
    root_key: str,
) -> None:
    payload = {
        root_key: [
            {
                "id": "i1",
                "text": "Digital video revenue grew.",
                "evidence_id": "iab-video",
                "metric": {"value": "19.2%", "unit": ""},
            }
        ]
    }
    ctx = RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")

    with pytest.raises(AppError) as captured:
        validate_output_schema(
            payload=payload,
            schema_name="artifacts",
            root_key=root_key,
            ctx=ctx,
        )

    assert captured.value.code == "schema_missing_required"


def test_normalize_artifact_summary_removes_editorial_scaffold_labels() -> None:
    summary = normalize_artifact_summary(
        {
            "executive_summary": (
                "Answer: Brand tracking joins survey design and activation. "
                "Scale: The service covers 50 markets. "
                "Implication: Teams can compare markets."
            )
        }
    )

    assert summary["executive_summary"] == (
        "Brand tracking joins survey design and activation. "
        "The service covers 50 markets. Teams can compare markets."
    )


def test_linkedin_reference_id_stripping_preserves_blank_line_paragraphs() -> None:
    assert (
        strip_linkedin_inline_reference_ids(
            "First paragraph (IC-12).\n\nSecond paragraph (F-2)."
        )
        == "First paragraph.\n\nSecond paragraph."
    )


def test_binding_known_evidence_canonicalizes_model_supplied_claim_pages() -> None:
    summary = {
        "claim_evidence_map": [
            {
                "claim": "Known finding remains grounded.",
                "evidence_id": "finding-1",
                "evidence": "Known evidence.",
                "pages": [7, 99],
                "evidence_spans": [
                    {
                        "evidence_id": "finding-1",
                        "source_pack": "model",
                        "page": 99,
                        "text": "Model supplied page.",
                    }
                ],
            }
        ]
    }

    bind_artifact_evidence_spans(
        summary=summary,
        insights_candidates=[],
        insights_final=[],
        quotes_final=[],
        doc_map={},
        evidence_packs={
            "findings": {
                "findings": [
                    {
                        "id": "finding-1",
                        "evidence": "Known evidence.",
                        "pages": [7],
                    }
                ]
            }
        },
    )

    claim = summary["claim_evidence_map"][0]
    assert claim["pages"] == [7]
    assert claim["evidence_spans"] == [
        {
            "evidence_id": "finding-1",
            "source_pack": "findings",
            "page": 7,
            "text": "Known evidence.",
        }
    ]


def test_binding_known_evidence_replaces_model_supplied_insight_evidence() -> None:
    insights = [
        {
            "id": "insight-1",
            "text": "The audience reached 9.25 million users, or 90.8 percent.",
            "evidence_id": "finding-1",
            "evidence": "Model-supplied evidence claims 90.8 percent.",
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
                "findings": [
                    {
                        "id": "finding-1",
                        "evidence": (
                            "There were 9.25 million users; the number increased "
                            "by 930 thousand (+11.2 percent)."
                        ),
                    }
                ]
            }
        },
    )

    assert insights[0]["evidence"] == (
        "There were 9.25 million users; the number increased by 930 thousand "
        "(+11.2 percent)."
    )
    quality = evaluate_public_editorial_quality(
        report_id="canonical-evidence", artifacts={"insights_final": insights}
    )
    assert "public_editorial_quality.unsupported_numeric_claim" in {
        issue.rule_id for issue in quality.issues
    }


def test_initial_artifact_normalization_preserves_distinct_quarterly_periods() -> None:
    source = "Share fell from 43% in Q1 2025 to 41% in Q2 2025."

    summary = normalize_artifact_summary(
        {
            "tldr": source,
            "card_tldr_compact": source,
            "executive_summary": source,
            "claim_evidence_map": [
                {"claim": source, "evidence": source, "evidence_id": "activate-43-41"}
            ],
        }
    )
    insights = normalize_artifact_insights(
        [{"id": "candidate-1", "text": source, "evidence": source}],
        prefix="candidate",
    )

    assert summary["tldr"] == source
    assert summary["claim_evidence_map"][0]["evidence"] == source
    assert insights[0]["text"] == source


def test_preserve_public_source_displays_repairs_unique_proven_values() -> None:
    summary = {
        "tldr": "The report has a material outlook.",
        "card_tldr_compact": "The report has a material outlook.",
        "executive_summary": "Global eCommerce is forecast to add over $3T.",
        "claim_evidence_map": [
            {
                "claim": "Global eCommerce is forecast to add over $3T.",
                "evidence_id": "market-growth",
                "evidence": "Global eCommerce is forecast to add over $3.0T.",
            }
        ],
    }
    insights = [
        {
            "id": "ad-market",
            "text": (
                "The 2025 U.S. ad-spend forecast was revised from +7.3% in "
                "January to +5.7% in September."
            ),
            "evidence_id": "ad-market-growth",
            "evidence": (
                "The January 2025 outlook forecast +7.3%, while the September "
                "2025 update revised it to +5.7%."
            ),
            "metric": {},
            "pages": [1],
        }
    ]

    preserve_public_source_displays(
        summary=summary,
        insights_final=insights,
        expert_comment="",
        linkedin_post="",
    )

    assert summary["executive_summary"] == (
        "Global eCommerce is forecast to add over $3.0T."
    )
    assert insights[0]["text"] == (
        "The 2025 U.S. ad-spend forecast was revised from +7.3% in January "
        "2025 to +5.7% in September 2025."
    )
    quality = evaluate_public_editorial_quality(
        report_id="source-display-preservation",
        artifacts={"summary": summary, "insights_final": insights},
    )
    assert quality.status == "pass"


def test_preserve_public_source_displays_leaves_ambiguous_display_and_prose_unchanged() -> (
    None
):
    summary = {
        "tldr": "The report has a material outlook.",
        "card_tldr_compact": "The report has a material outlook.",
        "executive_summary": (
            "The market outlook remains material. Commerce is forecast to add over "
            "$3T through 2028. Planning assumptions remain under review."
        ),
        "claim_evidence_map": [
            {
                "claim": "Two distinct forecast figures are retained.",
                "evidence_id": "ambiguous-growth",
                "evidence": (
                    "Consumer revenues rise to $3.0T while B2B revenues rise to $3.2T."
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

    assert summary["executive_summary"] == (
        "The market outlook remains material. Commerce is forecast to add over "
        "$3T through 2028. Planning assumptions remain under review."
    )
    quality = evaluate_public_editorial_quality(
        report_id="ambiguous-source-display", artifacts={"summary": summary}
    )
    assert quality.status == "fail"
    assert {issue.rule_id for issue in quality.issues} >= {
        "public_editorial_quality.incomplete_numeric_expression"
    }


def test_source_displays_restore_exact_metric_comparisons() -> None:
    summary = {
        "tldr": "The forecast reaches $3T in Q1 2025.",
        "card_tldr_compact": "The forecast reaches $3T in Q1 2025.",
        "executive_summary": "The forecast reaches $3T in Q1 2025.",
        "claim_evidence_map": [
            {
                "claim": "A forecast metric is retained.",
                "evidence_id": "forecast-metric",
                "evidence": "The forecast reaches $3.0T in Q1 FY2025E.",
            }
        ],
    }
    insights = [
        {
            "id": "comparison",
            "text": (
                "The outlook moves from 7.3% in January to 5.7% in September, "
                "with a 3 : 1 ratio and a 10%-15% range."
            ),
            "so_what": "Plan for 7.3% in January rather than 5.7% in September.",
            "now_what": "Compare the 10%-15% range before committing spend.",
            "evidence_id": "period-comparison",
            "evidence": (
                "The outlook moves from +7.30% in January 2025 to -5.70% in "
                "September 2025, with a 3:1 ratio and a 10.00% to 15.00% range."
            ),
            "metric": {"value": "7.3%", "timeframe": "January"},
            "pages": [1],
        }
    ]

    expert_comment, linkedin_post = preserve_public_source_displays(
        summary=summary,
        insights_final=insights,
        expert_comment="The outlook moves from 7.3% in January to 5.7% in September.",
        linkedin_post="The outlook moves from 7.3% in January to 5.7% in September.",
    )

    assert summary["executive_summary"] == "The forecast reaches $3.0T in Q1 FY2025E."
    assert insights[0]["text"] == (
        "The outlook moves from +7.30% in January 2025 to -5.70% in "
        "September 2025, with a 3:1 ratio and a 10.00% to 15.00% range."
    )
    assert insights[0]["so_what"] == (
        "Plan for +7.30% in January 2025 rather than -5.70% in September 2025."
    )
    assert insights[0]["now_what"] == (
        "Compare the 10.00% to 15.00% range before committing spend."
    )
    assert insights[0]["metric"] == {
        "value": "+7.30%",
        "timeframe": "January 2025",
    }
    assert expert_comment == (
        "The outlook moves from +7.30% in January 2025 to -5.70% in September 2025."
    )
    assert linkedin_post == expert_comment


def test_source_display_preservation_replaces_unsupported_insight_number_with_evidence() -> (
    None
):
    source = (
        "There were 9.25 million social media users in January 2022; the number "
        "increased by 930 thousand (+11.2 percent) between 2021 and 2022."
    )
    insights = [
        {
            "id": "social-media",
            "text": (
                "Social media reached 9.25 million users, or 90.8 percent of the "
                "population."
            ),
            "evidence": source,
            "metric": {"value": "9.25 million", "unit": "users"},
        }
    ]

    preserve_public_source_displays(
        summary={}, insights_final=insights, expert_comment="", linkedin_post=""
    )

    assert insights[0]["text"] == source
    quality = evaluate_public_editorial_quality(
        report_id="numeric-source-fallback", artifacts={"insights_final": insights}
    )
    assert "public_editorial_quality.unsupported_numeric_claim" not in {
        issue.rule_id for issue in quality.issues
    }


def test_source_displays_restore_uniquely_labelled_parallel_metric_values() -> None:
    summary = {"claim_evidence_map": []}
    insights = [
        {
            "id": "growth-drivers",
            "evidence": (
                "Total video grew 19.6% to €34.0 billion, while social grew "
                "19.2% to €35.5 billion."
            ),
        }
    ]

    expert_comment, _ = preserve_public_source_displays(
        summary=summary,
        insights_final=insights,
        expert_comment=("Video and social grew 19.1% and 19.1% as growth drivers."),
        linkedin_post="",
    )

    assert expert_comment == (
        "Video and social grew 19.6% and 19.2% as growth drivers."
    )


def test_preserve_public_source_displays_restores_month_and_half_year_forms() -> None:
    summary = {
        "tldr": "H1 2026 demand was measured in Jan 2025.",
        "card_tldr_compact": "H1 2026 demand was measured in Jan 2025.",
        "executive_summary": "H1 2026 demand was measured in Jan 2025.",
        "claim_evidence_map": [
            {
                "claim": "The source period is explicit.",
                "evidence_id": "source-period",
                "evidence": "H1 FY2026E demand was measured in January 2025.",
            }
        ],
    }

    preserve_public_source_displays(
        summary=summary,
        insights_final=[],
        expert_comment="",
        linkedin_post="",
    )

    assert summary["executive_summary"] == (
        "H1 FY2026E demand was measured in January 2025."
    )


def test_source_displays_restore_standalone_forecast_markers() -> None:
    summary = {
        "tldr": "The 2026 period changes planning assumptions.",
        "card_tldr_compact": "The 2026 period changes planning assumptions.",
        "executive_summary": "The 2026 period changes planning assumptions.",
        "claim_evidence_map": [
            {
                "claim": "The source forecast period is explicit.",
                "evidence_id": "forecast-period",
                "evidence": "The 2026E outlook changes planning assumptions.",
            }
        ],
    }

    preserve_public_source_displays(
        summary=summary,
        insights_final=[],
        expert_comment="",
        linkedin_post="",
    )

    assert summary["executive_summary"] == (
        "The 2026E period changes planning assumptions."
    )


def test_source_display_preservation_leaves_ordinary_may_paraphrase_untouched() -> None:
    summary = {
        "tldr": "Higher demand may reshape planning.",
        "card_tldr_compact": "Higher demand may reshape planning.",
        "executive_summary": "Higher demand may reshape planning.",
        "claim_evidence_map": [
            {
                "claim": "The source has a May observation.",
                "evidence_id": "may-observation",
                "evidence": "May 2025 demand increased year over year.",
            }
        ],
    }

    preserve_public_source_displays(
        summary=summary,
        insights_final=[],
        expert_comment="",
        linkedin_post="",
    )

    assert summary["executive_summary"] == "Higher demand may reshape planning."


def test_source_displays_preserve_unqualified_decimal_precision() -> None:
    summary = {
        "tldr": "The index reached 7.3.",
        "card_tldr_compact": "The index reached 7.3.",
        "executive_summary": "The index reached 7.3.",
        "claim_evidence_map": [
            {
                "claim": "The source has a precise index value.",
                "evidence_id": "index-value",
                "evidence": "The index reached 7.30.",
            }
        ],
    }

    preserve_public_source_displays(
        summary=summary,
        insights_final=[],
        expert_comment="",
        linkedin_post="",
    )

    assert summary["executive_summary"] == "The index reached 7.30."


def test_source_display_preservation_covers_all_public_fields_idempotently() -> None:
    summary = {
        "tldr": "The forecast reaches $3T in H1 2026.",
        "card_tldr_compact": "The forecast reaches $3T in H1 2026.",
        "executive_summary": "The forecast reaches $3T in H1 2026.",
        "claim_evidence_map": [
            {
                "claim": "The forecast period is source-backed.",
                "evidence_id": "forecast",
                "evidence": "The forecast reaches $3.0T in H1 FY2026E.",
            }
        ],
    }
    insights = [
        {
            "id": "growth",
            "text": "Growth reaches 7.3% in January.",
            "so_what": "Plan for 7.3% in January.",
            "now_what": "Compare 7.3% in January before committing spend.",
            "evidence_id": "growth",
            "evidence": "Growth reaches +7.30% in January 2025.",
            "metric": {"value": "7.3%", "timeframe": "January"},
            "pages": [1],
        }
    ]

    expert_comment, linkedin_post = preserve_public_source_displays(
        summary=summary,
        insights_final=insights,
        expert_comment="Growth reaches 7.3% in January.",
        linkedin_post="Growth reaches 7.3% in January.",
    )
    first_pass = deepcopy((summary, insights, expert_comment, linkedin_post))

    expert_comment, linkedin_post = preserve_public_source_displays(
        summary=summary,
        insights_final=insights,
        expert_comment=expert_comment,
        linkedin_post=linkedin_post,
    )

    assert summary["tldr"] == "The forecast reaches $3.0T in H1 FY2026E."
    assert summary["card_tldr_compact"] == summary["tldr"]
    assert summary["executive_summary"] == summary["tldr"]
    assert insights[0]["text"] == "Growth reaches +7.30% in January 2025."
    assert insights[0]["so_what"] == "Plan for +7.30% in January 2025."
    assert insights[0]["now_what"] == (
        "Compare +7.30% in January 2025 before committing spend."
    )
    assert insights[0]["metric"] == {
        "value": "+7.30%",
        "timeframe": "January 2025",
    }
    assert expert_comment == "Growth reaches +7.30% in January 2025."
    assert linkedin_post == expert_comment
    quality = evaluate_public_editorial_quality(
        report_id="first-pass-source-display",
        artifacts={
            "summary": summary,
            "insights_final": insights,
            "expert_comment": expert_comment,
            "linkedin_post": linkedin_post,
        },
    )
    assert quality.status == "pass"
    assert (summary, insights, expert_comment, linkedin_post) == first_pass


def test_source_display_preservation_leaves_unsupported_values_unchanged() -> None:
    summary = {
        "tldr": "Margin reaches 8.5% in March 2027.",
        "card_tldr_compact": "Margin reaches 8.5% in March 2027.",
        "executive_summary": "Margin reaches 8.5% in March 2027.",
        "claim_evidence_map": [
            {
                "claim": "A different source display is retained.",
                "evidence_id": "margin",
                "evidence": "Margin reaches +7.30% in January 2025.",
            }
        ],
    }

    preserve_public_source_displays(
        summary=summary,
        insights_final=[],
        expert_comment="",
        linkedin_post="",
    )

    assert summary["executive_summary"] == "Margin reaches 8.5% in March 2027."


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
