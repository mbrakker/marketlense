import pytest

from src.generators.artifact_normalization import (
    constrain_summary_to_source_backed_claims,
    normalize_artifact_insights,
    preserve_public_source_displays,
    select_artifact_insights,
)
from src.utils.errors import AppError


def test_insight_normalization_collapses_ocr_double_numeric_signs() -> None:
    normalized = normalize_artifact_insights(
        [
            {
                "id": "time-spend",
                "text": "Social media changed by −-5% after shelter in place.",
                "evidence_id": "f1",
                "evidence": "Social media changed by -5% after shelter in place.",
            }
        ],
        prefix="insight",
    )

    assert normalized[0]["text"] == (
        "Social media changed by −5% after shelter in place."
    )


def test_preservation_replaces_an_unsupported_insight_number_and_clears_metric() -> (
    None
):
    summary = {"claim_evidence_map": []}
    evidence = "Private-label expansion is one of the trends expected through 2026."
    insights = [
        {
            "id": "private-label",
            "text": "Private labels contributed +3.6% to global value growth.",
            "evidence_id": "trend-1",
            "evidence": evidence,
            "metric": {
                "label": "Private-label contribution",
                "value": "+3.6%",
                "unit": "percent",
                "timeframe": "MAT",
                "trend": "growth",
            },
        }
    ]

    preserve_public_source_displays(
        summary=summary,
        insights_final=insights,
        expert_comment="",
        linkedin_post="",
    )

    assert insights[0]["text"] == evidence
    assert insights[0]["metric"]["value"] == ""
    assert insights[0]["metric"]["label"] == ""
    assert insights[0]["metric"]["timeframe"] == ""


def test_summary_constraint_replaces_weakly_bound_summary_copy_with_direct_claims() -> (
    None
):
    summary = {
        "tldr": "Forecast growth will be led by unsupported drivers.",
        "card_tldr_compact": "Unsupported drivers lead the forecast.",
        "executive_summary": "Unsupported drivers lead the forecast.",
        "claim_evidence_map": [
            {
                "claim": "The report forecasts almost $375B in global growth dollars.",
                "evidence_id": "quote-1",
                "evidence_spans": [
                    {
                        "evidence_id": "quote-1",
                        "source_pack": "quote_candidates",
                        "text": (
                            "The report forecasts almost $375B in global growth "
                            "dollars."
                        ),
                    }
                ],
            },
            {
                "claim": "Advertising will rely on multiple identity approaches.",
                "evidence_id": "identity-section",
                "evidence_spans": [
                    {
                        "evidence_id": "identity-section",
                        "source_pack": "doc_map",
                        "text": "The section examines identity approaches.",
                    }
                ],
            },
        ],
    }

    changed = constrain_summary_to_source_backed_claims(summary)

    assert changed is True
    assert (
        summary["tldr"] == "The report forecasts almost $375B in global growth dollars."
    )
    assert summary["card_tldr_compact"] == summary["tldr"]
    assert summary["executive_summary"] == summary["tldr"]
    assert [claim["evidence_id"] for claim in summary["claim_evidence_map"]] == [
        "quote-1"
    ]


def test_summary_constraint_accepts_direct_verified_fact_claims() -> None:
    claim = "91% of consumers expect brands to disclose AI use in marketing."
    summary = {
        "tldr": "Unsupported summary copy.",
        "card_tldr_compact": claim,
        "executive_summary": "Unsupported summary copy.",
        "claim_evidence_map": [
            {
                "claim": claim,
                "evidence_id": "verified-fact:ai-disclosure",
                "evidence_spans": [
                    {
                        "evidence_id": "verified-fact:ai-disclosure",
                        "source_pack": "verified_facts",
                        "page": 13,
                        "text": claim,
                    }
                ],
            }
        ],
    }

    assert (
        constrain_summary_to_source_backed_claims(
            summary,
            require_direct_fallback=True,
        )
        is True
    )
    assert summary["tldr"] == claim
    assert summary["card_tldr_compact"] == claim


def test_summary_fallback_keeps_descriptive_doc_map_claims() -> None:
    direct_claim = "The report identifies three retention measures."
    descriptive_claim = "The section distinguishes acquisition from retention."
    strong_doc_map_claim = "The forecast guarantees $375B in growth."
    summary = {
        "tldr": "Unsupported fallback headline.",
        "card_tldr_compact": direct_claim,
        "executive_summary": "Unsupported executive summary.",
        "claim_evidence_map": [
            {
                "claim": direct_claim,
                "evidence_id": "finding-1",
                "evidence_spans": [
                    {
                        "evidence_id": "finding-1",
                        "source_pack": "findings",
                        "text": direct_claim,
                    }
                ],
            },
            {
                "claim": descriptive_claim,
                "evidence_id": "section-1",
                "evidence_spans": [
                    {
                        "evidence_id": "section-1",
                        "source_pack": "doc_map",
                        "text": descriptive_claim,
                    }
                ],
            },
            {
                "claim": strong_doc_map_claim,
                "evidence_id": "section-2",
                "evidence_spans": [
                    {
                        "evidence_id": "section-2",
                        "source_pack": "doc_map",
                        "text": strong_doc_map_claim,
                    }
                ],
            },
        ],
    }

    changed = constrain_summary_to_source_backed_claims(summary)

    assert changed is True
    assert summary["tldr"] == direct_claim
    assert [claim["claim"] for claim in summary["claim_evidence_map"]] == [
        direct_claim,
        descriptive_claim,
    ]


def test_summary_constraint_fails_before_mutation_without_short_direct_sentence() -> (
    None
):
    long_direct_claim = (
        "Criteo says commerce media plans now span multiple retailer networks, "
        "formats, measurement systems, and audience strategies across the global "
        "advertising market."
    )
    summary = {
        "tldr": "Unsupported growth will reshape the market.",
        "card_tldr_compact": "Existing compact copy remains valid.",
        "executive_summary": "Unsupported growth will reshape the market.",
        "claim_evidence_map": [
            {
                "claim": "The unsupported forecast guarantees $375B in growth.",
                "evidence_id": "section-1",
                "evidence_spans": [
                    {
                        "evidence_id": "section-1",
                        "source_pack": "doc_map",
                        "text": "The section reviews the market outlook.",
                    }
                ],
            },
            {
                "claim": long_direct_claim,
                "evidence_id": "quote-1",
                "evidence_spans": [
                    {
                        "evidence_id": "quote-1",
                        "source_pack": "quote_candidates",
                        "text": long_direct_claim,
                    }
                ],
            },
        ],
    }
    original = {**summary, "claim_evidence_map": list(summary["claim_evidence_map"])}

    with pytest.raises(AppError) as captured:
        constrain_summary_to_source_backed_claims(summary)

    assert captured.value.code == "card_tldr_compact_invalid"
    assert summary == original


def test_select_artifact_insights_uses_each_stable_id_once():
    candidates = [
        {
            "id": f"insight-{index}",
            "text": f"Distinct source finding for category {index}.",
            "evidence_id": f"finding-{index}",
        }
        for index in range(6)
    ]
    final = [dict(item) for item in candidates[:5]]
    final.insert(
        1, {**candidates[0], "text": "Different wording for the first finding."}
    )

    selected = select_artifact_insights(
        final_insights=final,
        candidate_insights=candidates,
        editorial_plan={
            "report_thesis": "Distinct findings describe the market.",
            "themes": [
                {"theme": "First", "priority": 1, "evidence_ids": ["finding-0"]},
                {"theme": "Second", "priority": 2, "evidence_ids": ["finding-1"]},
            ],
        },
    )

    assert len(selected) == 5
    assert len({item["id"] for item in selected}) == len(selected)
    assert next(item for item in selected if item["id"] == "insight-0") == final[0]


def test_select_artifact_insights_preserves_chosen_candidate_factual_fields():
    """Candidate→final selection must not carry final-stage factual drift.

    This is the DHL/SimilarWeb mutation shape: the final model rewrote the
    same-stable-ID insight with a drifted metric display. Selection keeps the
    final editorial wording but deterministically restores the chosen
    candidate's protected factual fields.
    """
    plan = {
        "report_thesis": "The report supports grounded decisions.",
        "themes": [
            {"theme": "Margin", "priority": 1, "evidence_ids": ["f1"]},
            {"theme": "Retention", "priority": 2, "evidence_ids": ["f2"]},
            {"theme": "Reach", "priority": 3, "evidence_ids": ["f3"]},
        ],
    }
    candidate_metric = {
        "label": "Europe margin",
        "value": "46%",
        "unit": "%",
        "trend": "",
        "timeframe": "2025",
        "geography": "Europe",
        "segment": "",
        "sample_size": "",
        "confidence": "",
    }
    drifted_metric = {
        "label": "Drifted label",
        "value": "99%",
        "unit": "%",
        "trend": "",
        "timeframe": "2024",
        "geography": "Global",
        "segment": "",
        "sample_size": "",
        "confidence": "",
    }
    candidate_insights = [
        {
            "id": "insight-1",
            "text": "Margin reached 46% in Europe during 2025.",
            "evidence_id": "f1",
            "metric": dict(candidate_metric),
            "pages": [3],
        },
        {
            "id": "insight-2",
            "text": "Retention held at 88%.",
            "evidence_id": "f2",
        },
    ]
    final_insights = [
        {
            # Same stable ID, drifted editorial wording AND drifted facts.
            "id": "insight-1",
            "text": "Margin improved to 46% in Europe in 2025.",
            "evidence_id": "f1",
            "metric": dict(drifted_metric),
            "pages": [3],
        },
    ]

    selected = select_artifact_insights(
        final_insights=final_insights,
        candidate_insights=candidate_insights,
        editorial_plan=plan,
    )

    repaired = next(item for item in selected if item["id"] == "insight-1")
    assert repaired["text"] == "Margin improved to 46% in Europe in 2025."
    for field_name, value in candidate_metric.items():
        assert repaired["metric"][field_name] == value
    # A stable-ID insight without a matching candidate keeps its own facts.
    untouched = next(item for item in selected if item["id"] == "insight-2")
    assert untouched["text"] == "Retention held at 88%."


def test_verified_selection_preserves_complete_candidate_metric_extensions():
    candidate_metric = {
        "label": "Composite adoption",
        "value": "42%",
        "unit": "%",
        "observations": [
            {"population": "new buyers", "period": "2026", "value": "42%"}
        ],
        "report_specific_method": {
            "denominator_rule": "eligible respondents",
            "weighting": "region-adjusted",
        },
    }
    selected = select_artifact_insights(
        final_insights=[
            {
                "id": "insight-1",
                "text": "Editorial wording remains concise.",
                "evidence_id": "f1",
                "metric": {
                    "label": "Unsupported final metric",
                    "value": "99%",
                    "unit": "%",
                    "final_only_context": "not authoritative",
                },
            }
        ],
        candidate_insights=[
            {
                "id": "insight-1",
                "text": "The candidate fact is source-backed.",
                "evidence_id": "f1",
                "metric": candidate_metric,
            }
        ],
        editorial_plan={
            "report_thesis": "The canonical fact remains authoritative.",
            "themes": [
                {"theme": "Theme 1", "priority": 1, "evidence_ids": ["f1"]},
                {"theme": "Theme 2", "priority": 2, "evidence_ids": ["f2"]},
            ],
        },
        verified_mode=True,
    )

    metric = selected[0]["metric"]
    assert metric["value"] == "42%"
    assert metric["observations"] == candidate_metric["observations"]
    assert (
        metric["report_specific_method"] == candidate_metric["report_specific_method"]
    )
    assert "final_only_context" not in metric


def test_verified_selection_scopes_composite_metric_to_final_observation() -> None:
    candidate_metric = {
        "label": "Global e-commerce CPI",
        "value": "Global: $1.00 in 2024; $0.98 in 2025",
        "unit": "USD per install",
        "trend": "Down overall; deal discovery up",
        "timeframe": "2024-2025",
        "geography": "Global",
        "segment": "E-commerce apps and named subverticals",
        "cohort": "Global e-commerce apps; deal discovery and shopping",
        "observation_status": "Reported values; not identified as forecasts",
        "forecast_status": "Not identified as a forecast",
        "observations": [
            {
                "label": "Deal discovery CPI",
                "value": "2024: $1.44; 2025: $2.26",
                "unit": "USD per install",
                "timeframe": "2024-2025",
                "segment": "Deal discovery",
                "geography": "Global",
                "cohort": "E-commerce apps",
                "observation_status": "Reported values; not identified as forecasts",
            },
            {
                "label": "Shopping CPI",
                "value": "2024: $0.93; 2025: $0.91",
                "unit": "USD per install",
                "timeframe": "2024-2025",
                "segment": "Shopping",
                "geography": "Global",
                "cohort": "E-commerce apps",
                "observation_status": "Reported values; not identified as forecasts",
            },
        ],
    }
    selected = select_artifact_insights(
        final_insights=[
            {
                "id": "ecommerce-cpi",
                "text": (
                    "Global e-commerce deal discovery CPI rose from $1.44 in 2024 "
                    "to $2.26 in 2025."
                ),
                "evidence_id": "final-only",
                "metric": {
                    "label": "Global deal discovery CPI",
                    "value": "from $1.44 in 2024 to $2.26 in 2025",
                    "unit": "USD per install",
                    "trend": "Increased",
                    "timeframe": "2024-2025",
                    "geography": "Global",
                    "segment": "Deal discovery",
                    "cohort": "E-commerce apps",
                    "observation_status": (
                        "Reported values; not identified as forecasts"
                    ),
                    "forecast_status": "Not identified as a forecast",
                },
            }
        ],
        candidate_insights=[
            {
                "id": "ecommerce-cpi",
                "text": "The retained composite CPI fact.",
                "evidence_id": "verified-fact:ecommerce-cpi",
                "evidence": "The source reports all e-commerce CPI observations.",
                "pages": [29],
                "metric": candidate_metric,
            }
        ],
        editorial_plan={
            "report_thesis": "Composite source facts remain authoritative.",
            "themes": [
                {
                    "theme": "Acquisition economics",
                    "priority": 1,
                    "evidence_ids": ["verified-fact:ecommerce-cpi"],
                },
                {
                    "theme": "Subvertical differences",
                    "priority": 2,
                    "evidence_ids": ["verified-fact:ecommerce-cpi"],
                },
            ],
        },
        verified_mode=True,
    )

    metric = selected[0]["metric"]
    assert selected[0]["text"].startswith("Global e-commerce deal discovery CPI")
    assert selected[0]["evidence_id"] == "verified-fact:ecommerce-cpi"
    assert selected[0]["pages"] == [29]
    assert metric["label"] == "Deal discovery CPI"
    assert metric["value"] == "2024: $1.44; 2025: $2.26"
    assert metric["segment"] == "Deal discovery"
    assert metric["cohort"] == "E-commerce apps"
    assert metric["observations"] == candidate_metric["observations"]


def test_verified_selection_keeps_full_composite_when_final_metric_is_sparse() -> None:
    candidate_metric = {
        "label": "Global e-commerce CPI",
        "value": (
            "Overall: $1.00 to $0.98; deal discovery: $1.44 to $2.26; "
            "shopping: $0.93 to $0.91"
        ),
        "unit": "USD per install",
        "timeframe": "2024 to 2025",
        "geography": "Global",
        "segment": "E-commerce apps",
        "observations": [
            {
                "label": "All e-commerce apps",
                "value": "$1.00 in 2024; $0.98 in 2025",
                "unit": "USD per install",
                "timeframe": "2024 to 2025",
                "segment": "All",
                "geography": "Global",
            },
            {
                "label": "Deal discovery",
                "value": "$1.44 in 2024; $2.26 in 2025",
                "unit": "USD per install",
                "timeframe": "2024 to 2025",
                "segment": "Deal discovery",
                "geography": "Global",
            },
            {
                "label": "Shopping",
                "value": "$0.93 in 2024; $0.91 in 2025",
                "unit": "USD per install",
                "timeframe": "2024 to 2025",
                "segment": "Shopping",
                "geography": "Global",
            },
        ],
    }
    selected = select_artifact_insights(
        final_insights=[
            {
                "id": "ecommerce-cpi",
                "text": (
                    "Overall global e-commerce CPI fell from $1.00 to $0.98; "
                    "deal discovery rose from $1.44 to $2.26; shopping fell "
                    "from $0.93 to $0.91."
                ),
                "evidence_id": "final-only",
                "metric": {
                    "label": "Global e-commerce CPI",
                    "value": "$1.00 in 2024 to $0.98 in 2025",
                    "unit": "USD per install",
                    "timeframe": "2024 to 2025",
                    "geography": "Global",
                    "segment": "E-commerce apps",
                },
            }
        ],
        candidate_insights=[
            {
                "id": "ecommerce-cpi",
                "text": "The retained composite CPI fact.",
                "evidence_id": "verified-fact:ecommerce-cpi",
                "evidence": "The source reports all e-commerce CPI observations.",
                "pages": [29],
                "metric": candidate_metric,
            }
        ],
        editorial_plan={
            "report_thesis": "Composite source facts remain authoritative.",
            "themes": [
                {
                    "theme": "Acquisition economics",
                    "priority": 1,
                    "evidence_ids": ["verified-fact:ecommerce-cpi"],
                },
                {
                    "theme": "Subvertical differences",
                    "priority": 2,
                    "evidence_ids": ["verified-fact:ecommerce-cpi"],
                },
            ],
        },
        verified_mode=True,
    )

    assert selected[0]["text"].startswith("Overall global e-commerce CPI")
    assert selected[0]["evidence_id"] == "verified-fact:ecommerce-cpi"
    assert selected[0]["metric"]["label"] == candidate_metric["label"]
    assert selected[0]["metric"]["value"] == candidate_metric["value"]
    assert selected[0]["metric"]["observations"] == candidate_metric["observations"]


def test_verified_selection_rejects_named_observation_without_unique_binding() -> None:
    candidate_metric = {
        "label": "Global e-commerce CPI",
        "value": "Global: $1.00 in 2024; $0.98 in 2025",
        "unit": "USD per install",
        "observations": [
            {
                "label": "Deal discovery CPI",
                "value": "2024: $1.44; 2025: $2.26",
                "unit": "USD per install",
                "segment": "Deal discovery",
            },
            {
                "label": "Shopping CPI",
                "value": "2024: $0.93; 2025: $0.91",
                "unit": "USD per install",
                "segment": "Shopping",
            },
        ],
    }

    with pytest.raises(AppError, match="observation binding"):
        select_artifact_insights(
            final_insights=[
                {
                    "id": "ecommerce-cpi",
                    "text": (
                        "Deal discovery CPI rose from $1.00 in 2024 to $0.98 in 2025."
                    ),
                    "evidence_id": "final-only",
                    "metric": {
                        "label": "Deal discovery CPI",
                        "value": "2024: $1.00; 2025: $0.98",
                        "unit": "USD per install",
                        "segment": "Deal discovery",
                    },
                }
            ],
            candidate_insights=[
                {
                    "id": "ecommerce-cpi",
                    "text": "The retained composite CPI fact.",
                    "evidence_id": "verified-fact:ecommerce-cpi",
                    "evidence": "The source reports all e-commerce CPI observations.",
                    "pages": [29],
                    "metric": candidate_metric,
                }
            ],
            editorial_plan={
                "report_thesis": "Composite source facts remain authoritative.",
                "themes": [
                    {
                        "theme": "Acquisition economics",
                        "priority": 1,
                        "evidence_ids": ["verified-fact:ecommerce-cpi"],
                    },
                    {
                        "theme": "Subvertical differences",
                        "priority": 2,
                        "evidence_ids": ["verified-fact:ecommerce-cpi"],
                    },
                ],
            },
            verified_mode=True,
        )


def test_verified_multi_fact_binding_survives_insight_normalization_and_selection():
    primary_id = "verified-fact:north-america"
    comparison_id = "verified-fact:apac"
    final = normalize_artifact_insights(
        [
            {
                "id": "regional-video",
                "text": "North America has the same top environment as APAC.",
                "evidence_id": primary_id,
                "evidence_ids": [primary_id, comparison_id],
                "metric": {
                    "label": "North America video attention",
                    "value": "128",
                    "unit": "index",
                },
            }
        ],
        prefix="insight",
        verified_mode=True,
    )
    selected = select_artifact_insights(
        final_insights=final,
        candidate_insights=[
            {
                "id": "regional-video",
                "text": "North America video attention.",
                "evidence_id": primary_id,
                "metric": {
                    "label": "North America video attention",
                    "value": "128",
                    "unit": "index",
                },
            },
            {
                "id": "apac-video",
                "text": "APAC video attention.",
                "evidence_id": comparison_id,
                "metric": {
                    "label": "APAC video attention",
                    "value": "131",
                    "unit": "index",
                },
            },
        ],
        editorial_plan={
            "report_thesis": "Regional video attention differs by environment.",
            "themes": [
                {"theme": "North America", "priority": 1, "evidence_ids": [primary_id]},
                {"theme": "APAC", "priority": 2, "evidence_ids": [comparison_id]},
            ],
        },
        verified_mode=True,
    )

    assert selected[0]["evidence_ids"] == [primary_id, comparison_id]
