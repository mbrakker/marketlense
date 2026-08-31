from __future__ import annotations

import json
from pathlib import Path

from src.services._render_service.normalization import (
    _build_core_signal,
    _core_signal_heading,
    _sanitize_linkedin_post,
    _sanitize_public_prose,
)


def test_core_signal_uses_a_complete_later_sentence_before_a_fallback() -> None:
    signal = _build_core_signal(
        tldr_text=(
            "The first source sentence is deliberately longer than the compact "
            "signal limit because it contains several material qualifiers. "
            "Demand is accelerating."
        ),
        executive_summary="Leaders should review the retained source evidence.",
        insights=[
            {
                "text": (
                    "The leading finding is intentionally longer than the compact "
                    "signal limit so the renderer must not publish a clipped claim."
                )
            }
        ],
    )

    assert signal["heading"] == "Demand is accelerating."
    assert signal["body"].endswith(".")
    assert signal["heading"] != "Executive signal pending"
    assert signal["body"] != "Source-supported signal unavailable for this report."


def test_core_signal_prefers_market_evidence_over_report_annotation() -> None:
    signal = _build_core_signal(
        tldr_text="The report presents nine foundational elements.",
        executive_summary="The study documents proof points across those elements.",
        insights=[
            {"text": "The report documents nine foundational elements."},
            {
                "text": (
                    "Creator economies already show high participation in user-"
                    "generated content and functioning monetization models."
                )
            },
        ],
    )

    assert "Creator economies" in signal["body"]
    assert "documents nine foundational" not in signal["body"]


def test_core_signal_derives_a_short_heading_from_a_long_strategic_claim() -> None:
    signal = _build_core_signal(
        tldr_text="",
        executive_summary="",
        insights=[
            {
                "text": (
                    "Brand tracking pinpoints where audiences drop out of the "
                    "purchase funnel and reveals emotional gaps that weaken "
                    "conversion."
                )
            }
        ],
    )

    assert signal["heading"] == (
        "Brand tracking pinpoints where audiences drop out of the purchase funnel."
    )
    assert signal["heading"] != "Source-backed market signal"


def test_core_signal_prefers_a_curated_strategic_implication() -> None:
    signal = _build_core_signal(
        tldr_text="",
        executive_summary="",
        insights=[
            {
                "text": (
                    "GWI harmonizes bespoke studies against a Core of 960,000+ "
                    "global datapoints across 50+ markets."
                ),
                "so_what": (
                    "You can benchmark bespoke tracker results against a large "
                    "harmonized dataset to contextualize brand performance across "
                    "markets and competitors."
                ),
            }
        ],
    )

    assert signal["heading"] == (
        "You can benchmark bespoke tracker results against a large harmonized dataset."
    )
    assert signal["heading"] != "Source-backed market signal"


def test_core_signal_does_not_break_a_numeric_fact_at_its_thousands_separator() -> None:
    signal = _build_core_signal(
        tldr_text="",
        executive_summary="",
        insights=[
            {
                "text": (
                    "GWI harmonizes bespoke studies against a Core of 960,000+ "
                    "global datapoints across 50+ markets, enabling large-scale "
                    "cross-market and cross-brand benchmarking."
                )
            }
        ],
    )

    assert signal["heading"] == "Large-scale cross-market and cross-brand benchmarking."


def test_core_signal_does_not_split_common_geographic_abbreviations() -> None:
    signal = _build_core_signal(
        tldr_text="",
        executive_summary="",
        insights=[
            {
                "text": (
                    "U.S. creator economies already support measurable content "
                    "participation and monetization."
                )
            }
        ],
    )

    assert signal["body"].endswith("monetization.")


def test_core_signal_heading_preserves_iab_between_coordination() -> None:
    fixture_path = (
        Path(__file__).resolve().parent
        / "fixtures"
        / "editorial_temporal"
        / "iab_pwc_quarterly.json"
    )
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    assert _core_signal_heading(fixture["core_signal_source"]) == fixture[
        "expected_core_signal_heading"
    ]


def test_core_signal_heading_keeps_noun_lists_at_clause_boundaries() -> None:
    text = (
        "Search, video, and creator partnerships shape the media mix, and "
        "measurement must unify results across every channel."
    )

    assert _core_signal_heading(text) == (
        "Search, video, and creator partnerships shape the media mix."
    )


def test_core_signal_heading_splits_independent_comma_clauses() -> None:
    text = (
        "Consumer demand is rising across key commerce categories, and "
        "investment is following in the fastest-growing formats."
    )

    assert _core_signal_heading(text) == (
        "Consumer demand is rising across key commerce categories."
    )


def test_core_signal_heading_preserves_a_complete_clause_before_comma_but() -> None:
    text = (
        "The market is expanding materially, but eCommerce remains one channel "
        "within a broader retail market by 2028."
    )

    assert _core_signal_heading(text) == "The market is expanding materially."


def test_core_signal_falls_back_for_over_limit_activate_time_sentence() -> None:
    signal = _build_core_signal(
        tldr_text="",
        executive_summary="",
        insights=[
            {
                "text": (
                    "Super Users are 28% of the U.S. population yet spend 17:06 per "
                    "day with technology and media versus 9:31 for all other users, "
                    "concentrating disproportionate attention and platform impact."
                )
            }
        ],
    )

    assert signal["heading"] == "Source-backed market signal"
    assert "17:06" in signal["body"]
    assert "9:31" in signal["body"]


def test_core_signal_heading_preserves_1706_before_a_semicolon_boundary() -> None:
    text = (
        "Super Users spend 17:06 daily compared with other audiences; retailers "
        "need plans for their concentrated attention."
    )

    assert _core_signal_heading(text) == (
        "Super Users spend 17:06 daily compared with other audiences."
    )


def test_core_signal_heading_preserves_931_before_a_semicolon_boundary() -> None:
    text = (
        "Other users spend 9:31 daily across technology and media; retailers need "
        "plans for their concentrated attention."
    )

    assert _core_signal_heading(text) == (
        "Other users spend 9:31 daily across technology and media."
    )


def test_core_signal_heading_preserves_ratio_before_a_semicolon_boundary() -> None:
    text = (
        "Premium streaming inventory converts at a 3:1 ratio; buyers need plans "
        "for its concentrated demand."
    )

    assert _core_signal_heading(text) == (
        "Premium streaming inventory converts at a 3:1 ratio."
    )


def test_core_signal_heading_splits_at_a_prose_colon() -> None:
    text = (
        "Retailers face increasing acquisition costs across channels: they need "
        "simpler checkout journeys to protect conversion."
    )

    assert _core_signal_heading(text) == (
        "Retailers face increasing acquisition costs across channels."
    )


def test_core_signal_heading_splits_at_a_semicolon() -> None:
    text = (
        "Retailers face increasing acquisition costs across channels; they need "
        "simpler checkout journeys to protect conversion."
    )

    assert _core_signal_heading(text) == (
        "Retailers face increasing acquisition costs across channels."
    )


def test_render_sanitizer_removes_editorial_labels_without_hiding_prose() -> None:
    assert _sanitize_public_prose("Observation: Demand is accelerating.") == (
        "Demand is accelerating."
    )


def test_render_sanitizer_preserves_quarterly_and_half_year_periods() -> None:
    text = (
        "Share moved from 43% in Q1 2025 to 41% in Q2 2025 and from H1 2025 "
        "to H2 2025."
    )

    assert _sanitize_public_prose(text) == text


def test_linkedin_sanitizer_preserves_paragraphs() -> None:
    assert _sanitize_linkedin_post(
        "*Activate Technology & Media Outlook: 2026 Edition* (finding_12)\n\n"
        "A supported second paragraph.\n\n"
        "[PLACEHOLDER]"
    ) == (
        "Activate Technology & Media Outlook: 2026 Edition\n\n"
        "A supported second paragraph."
    )


def test_core_signal_preserves_distinct_quarterly_periods() -> None:
    signal = _build_core_signal(
        tldr_text="",
        executive_summary="",
        insights=[
            {"text": "Share moved from 43% in Q1 2025 to 41% in Q2 2025."}
        ],
    )

    assert "Q1 2025" in signal["body"]
    assert "Q2 2025" in signal["body"]
