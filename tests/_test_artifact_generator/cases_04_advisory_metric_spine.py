# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._support_cases import *  # noqa: F401,F403


def test_derive_metric_spine_from_insights_uses_embedded_metric_contract() -> None:
    spine = derive_metric_spine_from_insights(
        [
            {
                "id": "insight_ai_purchases",
                "text": (
                    "AI recommendations already drive purchases: "
                    "46% of shoppers make purchases based on AI recommendations."
                ),
                "evidence_id": "q5",
                "metric": {
                    "value": "46",
                    "unit": "percent",
                    "timeframe": "2026",
                    "segment": "shoppers",
                    "confidence": "high",
                },
            }
        ]
    )

    assert spine == [
        {
            "schema_version": "1.0",
            "metric_id": "insight_ai_purchases",
            "label": "AI recommendations already drive purchases",
            "value": "46",
            "unit": "percent",
            "timeframe": "2026",
            "segment": "shoppers",
            "geography": "",
            "comparator": "",
            "baseline": "",
            "delta": "",
            "sample_size": "",
            "subject": "",
            "cohort": "",
            "denominator": "",
            "observation_status": "",
            "confidence": "high",
            "missing_context_notes": ["geography"],
            "evidence_id": "q5",
        }
    ]


def test_metric_label_survives_candidate_to_final_insight_to_key_figure() -> None:
    candidate = normalize_artifact_insights(
        [
            {
                "id": "iab-video-growth",
                "text": (
                    "Search retained the largest share of U.S. digital ad revenue. "
                    "Digital video revenue grew 19.2%."
                ),
                "evidence_id": "iab-video",
                "metric": {
                    "label": "Digital video revenue growth",
                    "value": "19.2%",
                    "unit": "",
                },
            }
        ],
        prefix="candidate",
    )
    final = normalize_artifact_insights(candidate, prefix="insight")

    spine = derive_metric_spine_from_insights(final)
    figures = build_key_figures(
        metric_spine=spine,
        evidence_packs={
            "findings": {
                "findings": [
                    {
                        "id": "iab-video",
                        "text": "Digital video revenue growth was 19.2%.",
                    }
                ]
            }
        },
        insights_final=final,
    )

    assert spine[0]["label"] == "Digital video revenue growth"
    assert spine[0]["evidence_id"] == "iab-video"
    assert figures[0]["figure"] == "19.2%"
    assert figures[0]["label"] == "Digital video revenue growth"
    assert figures[0]["evidence_id"] == "iab-video"


def test_iab_19_2_key_figure_uses_its_explicit_digital_video_label() -> None:
    fixture_path = (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "editorial_temporal"
        / "iab_video_19_2_key_figure.json"
    )
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    spine = derive_metric_spine_from_insights(
        [
            {
                "id": fixture["insight_id"],
                "text": fixture["insight_text"],
                "evidence_id": fixture["evidence_id"],
                "metric": fixture["metric"],
            }
        ]
    )

    assert spine[0]["value"] == "19.2%"
    assert spine[0]["label"] == "Digital video revenue growth"
    assert spine[0]["evidence_id"] == "iab-video"


def test_activate_2026_128_million_key_figure_uses_its_explicit_metric_label() -> None:
    fixture_path = (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "editorial_temporal"
        / "activate_2026_128m_key_figure.json"
    )
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    spine = derive_metric_spine_from_insights(
        [
            {
                "id": fixture["insight_id"],
                "text": fixture["insight_text"],
                "evidence_id": fixture["evidence_id"],
                "metric": fixture["metric"],
            }
        ]
    )

    assert spine[0]["value"] == "128 million"
    assert spine[0]["label"] == "Monthly U.S. adult generative AI users"
    assert spine[0]["evidence_id"] == "activate-ai-users"


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("Monthly U.S. adult generative AI users reached 128 million.", "128 million"),
        ("Monthly U.K. adult generative AI users reached 8 million.", "8 million"),
    ],
)
def test_legacy_metric_label_never_truncates_us_or_uk_abbreviations(
    text: str, value: str
) -> None:
    spine = derive_metric_spine_from_insights(
        [
            {
                "id": "legacy-users",
                "text": text,
                "evidence_id": "legacy-users",
                "metric": {"value": value, "unit": ""},
            }
        ]
    )

    assert spine[0]["label"] == text
    assert not spine[0]["label"].endswith(("U.S.", "U.K."))


def test_legacy_multi_metric_insight_uses_sentence_for_its_metric_not_first() -> None:
    spine = derive_metric_spine_from_insights(
        [
            {
                "id": "legacy-iab-video",
                "text": (
                    "Search retained the largest share of U.S. digital ad revenue. "
                    "Digital video revenue grew 19.2%."
                ),
                "evidence_id": "iab-video",
                "metric": {"value": "19.2%", "unit": ""},
            }
        ]
    )

    assert spine[0]["label"] == "Digital video revenue grew 19.2%."
    assert "Search retained" not in spine[0]["label"]


def test_legacy_metric_omits_key_figure_when_no_metric_specific_label_is_reliable() -> (
    None
):
    insight = {
        "id": "legacy-ambiguous",
        "text": "Search held 42% share; 19.2%.",
        "evidence_id": "iab-mixed",
        "metric": {"value": "19.2%", "unit": ""},
    }

    assert derive_metric_spine_from_insights([insight]) == []


def test_legacy_metric_uses_its_complete_clause_when_supporting_metrics_follow() -> (
    None
):
    spine = derive_metric_spine_from_insights(
        [
            {
                "id": "legacy-activate-users",
                "text": (
                    "Monthly U.S. adult generative AI users reached 128 million in "
                    "2025, up 45 million year over year."
                ),
                "evidence_id": "activate-ai-users",
                "metric": {"value": "128 million", "unit": ""},
            }
        ]
    )

    assert spine[0]["label"] == (
        "Monthly U.S. adult generative AI users reached 128 million in 2025"
    )


def test_legacy_metric_omits_a_lowercase_clause_without_a_complete_subject() -> None:
    insight = {
        "id": "legacy-fragment",
        "text": "Search held 42% share; cited by 19.2% of users.",
        "evidence_id": "legacy-fragment",
        "metric": {"value": "19.2%", "unit": ""},
    }

    assert derive_metric_spine_from_insights([insight]) == []


def test_metric_spine_label_does_not_split_a_decimal_display() -> None:
    spine = derive_metric_spine_from_insights(
        [
            {
                "id": "insight-revenue",
                "text": (
                    "Global eCommerce is forecast to grow from $7.2 trillion "
                    "in 2024 to $10.4 trillion in 2028."
                ),
                "evidence_id": "finding-revenue",
                "metric": {
                    "value": "$7.2T to $10.4T",
                    "unit": "global sales",
                },
            }
        ]
    )

    assert spine[0]["label"] == (
        "Global eCommerce is forecast to grow from $7.2 trillion in 2024 to "
        "$10.4 trillion in 2028."
    )


def test_metric_spine_label_keeps_leading_abbreviation_with_its_sentence() -> None:
    spine = derive_metric_spine_from_insights(
        [
            {
                "id": "insight-retail-media",
                "text": (
                    "U.S. retail media revenue is forecast to nearly double from "
                    "$54 billion in 2024 to $101 billion in 2028."
                ),
                "evidence_id": "finding-retail-media",
                "metric": {"value": "$54B to $101B", "unit": "USD revenue"},
            }
        ]
    )

    assert spine[0]["label"] == (
        "U.S. retail media revenue is forecast to nearly double from $54 billion "
        "in 2024 to $101 billion in 2028."
    )


def test_metric_spine_label_keeps_a_complete_long_source_sentence() -> None:
    text = (
        "Generative AI is already used for shopping inspiration or research by 41% "
        "of online shoppers aged 18-34, compared with 9% of shoppers aged 55 and "
        "older."
    )
    spine = derive_metric_spine_from_insights(
        [
            {
                "id": "insight-generative-ai",
                "text": text,
                "evidence_id": "finding-generative-ai",
                "metric": {
                    "value": "41% vs. 9%",
                    "unit": "share of online shoppers",
                },
            }
        ]
    )

    assert spine[0]["label"] == text


@pytest.mark.parametrize(
    ("value", "unit", "expected_display"),
    [
        ("70%", "percent", "70%"),
        ("$258.6", "billion", "$258.6"),
        ("258.6", "$ billion", "$258.6"),
        ("$7.2T to $10.4T", "", "$7.2T to $10.4T"),
    ],
)
def test_metric_spine_renders_one_clean_primary_metric(
    value: str, unit: str, expected_display: str
) -> None:
    source_text = f"Source-backed primary metric: {expected_display}."
    insight = {
        "id": "primary-metric",
        "text": source_text,
        "evidence": source_text,
        "evidence_id": "iab-primary-metric",
        "metric": {
            "label": "Source-backed primary metric",
            "value": value,
            "unit": unit,
        },
    }
    spine = derive_metric_spine_from_insights([insight])

    figures = build_key_figures(
        metric_spine=spine,
        evidence_packs={},
        insights_final=[insight],
    )

    assert [figure["figure"] for figure in figures] == [expected_display]


def test_metric_spine_preserves_coherent_forecast_range() -> None:
    spine = derive_metric_spine_from_insights(
        [
            {
                "id": "market-range",
                "text": (
                    "AI revenue is projected to rise from roughly $200 billion in "
                    "2023 to around $1.4 trillion by 2029."
                ),
                "evidence_id": "market-range",
                "metric": {
                    "label": "AI revenue market scale",
                    "value": "~$1.4 trillion by 2029 (from ~$200 billion in 2023)",
                    "unit": "USD",
                    "timeframe": "2023-2029",
                    "observation_status": "forecast",
                },
            }
        ]
    )

    assert spine[0]["value"] == "~$1.4 trillion by 2029 (from ~$200 billion in 2023)"
    assert spine[0]["unit"] == "USD"
    assert spine[0]["observation_status"] == "forecast"


def test_metric_spine_omits_iab_semicolon_packed_metric_but_preserves_insight() -> None:
    fixture_path = (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "editorial_temporal"
        / "iab_pwc_quarterly.json"
    )
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    insight = {
        "id": "iab-composite-metric",
        "text": fixture["source_comparison"],
        "evidence_id": fixture["report_id"],
        "metric": {
            "value": fixture["malformed_key_figure_value"],
            "unit": fixture["malformed_key_figure_unit"],
        },
    }

    assert derive_metric_spine_from_insights([insight]) == []
    assert insight["text"] == fixture["source_comparison"]
    assert insight["evidence_id"] == fixture["report_id"]


def test_metric_spine_omits_metric_when_no_clean_display_is_available() -> None:
    spine = derive_metric_spine_from_insights(
        [
            {
                "id": "composite-metric",
                "text": "Supporting values remain available in the insight text.",
                "evidence_id": "source-1",
                "metric": {"value": "19.2%; $62.1; $102.9", "unit": "share"},
            }
        ]
    )

    assert spine == []


def test_key_figures_do_not_extract_an_unstructured_percentage_from_insight_text() -> (
    None
):
    insights = [
        {
            "id": "iab-market-scale",
            "text": (
                "AI revenue is projected to rise from roughly $200 billion in 2023 "
                "to around $1.4 trillion by 2029."
            ),
            "evidence_id": "iab-market-scale",
            "evidence": (
                "Market scale: AI revenue is projected to rise from roughly $200 "
                "billion in 2023 to around $1.4 trillion by 2029; "
                "generative AI is expected to augment ~61% of jobs in Europe."
            ),
            "metric": {
                "label": "AI revenue market scale",
                "value": "~$1.4 trillion by 2029 (from ~$200 billion in 2023)",
                "unit": "USD",
                "timeframe": "2023-2029",
                "geography": "Europe",
                "confidence": "high",
            },
        }
    ]
    spine = derive_metric_spine_from_insights(insights)
    figures = build_key_figures(
        metric_spine=spine, evidence_packs={}, insights_final=insights
    )

    structured_values = {item["value"] for item in spine}
    assert "~61%" not in {item["figure"] for item in figures}
    assert {item["figure"] for item in figures} <= structured_values


def test_key_figures_do_not_extract_numbers_from_evidence_pack_text() -> None:
    evidence_packs = {
        "findings": {
            "findings": [
                {
                    "id": "market-growth",
                    "text": (
                        "AI revenue is projected to rise from $200 billion in 2023 "
                        "to around $1.4 trillion by 2029."
                    ),
                    "confidence": "high",
                },
                {
                    "id": "workflow-scale",
                    "text": (
                        "The guide cites 20 million impression opportunities per "
                        "second, 10 milliseconds to decide and thousands of variables "
                        "per campaign."
                    ),
                    "confidence": "high",
                },
            ]
        }
    }
    figures = build_key_figures(metric_spine=[], evidence_packs=evidence_packs)

    assert figures == []
