# ruff: noqa: F401,F403,F405
from __future__ import annotations
from pathlib import Path as _SplitPath

__file__ = str(
    _SplitPath(__file__).resolve().parent.parent / "test_artifact_normalization.py"
)

from ._split_support_test_artifact_normalization import *  # noqa: F401,F403


def test_binding_semantics_follow_a_same_grid_source_display_correction() -> None:
    """A deterministic display correction changes only the binding's claim text."""
    original = "Growth reached 7.3% in January."
    corrected = "Growth reached +7.30% in January 2025."

    carried = carry_soft_copy_binding_semantics_to_final_sentences(
        artifact_family="expert_comment",
        original_public_text=original,
        final_public_text=corrected,
        original_claim_bindings=[
            {
                "claim": original,
                "classification": "factual",
                "evidence_ids": ["f1"],
            }
        ],
    )

    assert carried == [
        {
            "claim": corrected,
            "classification": "factual",
            "evidence_ids": ["f1"],
        }
    ]


def test_normalize_artifact_insights_preserves_metric_fields() -> None:
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


def test_normalize_artifact_summary_recovers_invalid_compact_copy_from_short_claim() -> (
    None
):
    summary = normalize_artifact_summary(
        {
            "card_tldr_compact": "This model-provided compact summary exceeds the configured card limit and cannot be safely retained as public reader-facing copy today.",
            "claim_evidence_map": [
                {
                    "claim": "Retail media investment is increasing.",
                    "evidence_id": "finding-1",
                    "evidence": "Retail media investment is increasing.",
                    "pages": [4],
                }
            ],
        }
    )

    assert summary["card_tldr_compact"] == "Retail media investment is increasing."


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


def test_preserve_public_source_displays_leaves_ambiguous_prose_unchanged() -> None:
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


def test_source_display_preservation_replaces_unsupported_number() -> None:
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
