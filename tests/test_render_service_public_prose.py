from __future__ import annotations

from src.services._render_service.normalization import (
    _build_core_signal,
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


def test_render_sanitizer_removes_editorial_labels_without_hiding_prose() -> None:
    assert _sanitize_public_prose("Observation: Demand is accelerating.") == (
        "Demand is accelerating."
    )
