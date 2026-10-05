from __future__ import annotations

import json
from pathlib import Path

from bs4 import BeautifulSoup

from src.contracts.report_assets import RenderRequest
from src.services._render_service.normalization import (
    _build_core_signal,
    _build_signal_cards,
    _coerce_insights,
    _core_signal_heading,
    _sanitize_linkedin_post,
    _sanitize_public_prose,
)
from src.services.config_service import new_runtime_context
from src.services.render_service import render_report


def test_report_renders_insight_once_and_uses_distinct_topic_copy_for_signals(
    tmp_path: Path,
) -> None:
    insight = "Decision relevance is shifting as buyers reassess channel investments."
    request = RenderRequest(
        schema_version="1.0",
        data={
            "title": "Market Outlook 2026",
            "publisher": "Example Research",
            "_figure_section_enabled": False,
            "artifacts": {
                "toc_topics": ["Channel mix"],
                "toc_topics_expanded": [
                    {
                        "section_id": "channel-mix",
                        "title": "Channel mix",
                        "summary": "A separate theme summary from the contents.",
                    }
                ],
                "insights_final": [
                    {
                        "text": insight,
                        "evidence_id": "finding-1",
                        "so_what": "Investment choices depend on channel performance.",
                        "section_ids": ["channel-mix"],
                    }
                ],
            },
            "evidence_packs": {"doc_map": {"title": "Market Outlook 2026"}},
        },
        doc_name="Market Outlook 2026.pdf",
        file_id="market-outlook-2026",
        out_dir=str(tmp_path / "output"),
    )

    response = render_report(
        request,
        new_runtime_context(task_id="render-signal-duplication-test"),
    )
    document = BeautifulSoup(
        Path(response.html_path).read_text(encoding="utf-8"), "html.parser"
    )
    findings = document.select_one("#findings")
    signals = document.select_one("#signals")

    assert findings is not None
    assert signals is not None
    assert findings.get_text(" ", strip=True).count(insight) == 1
    assert insight not in signals.get_text(" ", strip=True)
    assert "A separate theme summary from the contents." in signals.get_text(
        " ", strip=True
    )


def test_report_omits_advisory_items_repeated_by_retained_insights(
    tmp_path: Path,
) -> None:
    decision_implication = "Track channel investment against buyer demand."
    priority_move = "Reallocate spend when channel returns weaken."
    request = RenderRequest(
        schema_version="1.0",
        data={
            "title": "Market Outlook 2026",
            "publisher": "Example Research",
            "_figure_section_enabled": False,
            "artifacts": {
                "insights_final": [
                    {
                        "text": "Buyers are shifting investment across channels.",
                        "so_what": decision_implication,
                        "now_what": priority_move,
                        "evidence_id": "finding-1",
                    }
                ],
                "executive_advisory": {
                    "decision_brief": {
                        "status": "generated",
                        "decision_implications": [decision_implication],
                        "priority_moves": [priority_move],
                    }
                },
            },
            "evidence_packs": {"doc_map": {"title": "Market Outlook 2026"}},
        },
        doc_name="Market Outlook 2026.pdf",
        file_id="market-outlook-advisory-duplication",
        out_dir=str(tmp_path / "output"),
    )

    response = render_report(
        request,
        new_runtime_context(task_id="render-advisory-duplication-test"),
    )
    document = BeautifulSoup(
        Path(response.html_path).read_text(encoding="utf-8"), "html.parser"
    )
    findings = document.select_one("#findings")
    advisory = document.select_one(".advisory-suite")

    assert findings is not None
    assert advisory is not None
    findings_text = findings.get_text(" ", strip=True)
    advisory_text = advisory.get_text(" ", strip=True)
    assert findings_text.count(decision_implication) == 1
    assert findings_text.count(priority_move) == 1
    assert decision_implication not in advisory_text
    assert priority_move not in advisory_text


def test_signal_cards_use_retained_insights_and_editorial_implications() -> None:
    cards = _build_signal_cards(
        topics=["Value redefined"],
        topic_briefs=[
            {
                "title": "Value redefined",
                "section_id": "value-redefined",
                "summary": "Generic chapter description.",
                "key_points": ["Generic section point."],
            }
        ],
        tags=[],
        insights=[
            {
                "text": "Consumers weigh price against trust and convenience.",
                "so_what": "Pricing decisions should account for perceived value.",
                "now_what": (
                    "Review value messages across routine and complex purchases."
                ),
                "evidence_id": "finding-1",
                "section_ids": ["value-redefined"],
                "citation_line": "Sample Report, page 8",
            }
        ],
    )

    assert cards[0]["title"] == "Value redefined"
    assert cards[0]["signal"] == "Consumers weigh price against trust and convenience."
    assert cards[0]["so_what"] == (
        "Pricing decisions should account for perceived value."
    )
    assert cards[0]["now_what"] == (
        "Review value messages across routine and complex purchases."
    )
    assert cards[0]["source_label"] == "Sample Report, page 8"


def test_core_signal_uses_complete_sentence_if_no_short_heading() -> None:
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

    assert signal["heading"] == (
        "The leading finding is intentionally longer than the compact signal limit "
        "so the renderer must not publish a clipped claim."
    )
    assert signal["body"] == (
        "The leading finding is intentionally longer than the compact signal limit "
        "so the renderer must not publish a clipped claim."
    )
    assert signal["heading"] == signal["body"]
    assert signal["heading"] != "Source-backed market signal"


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


def test_core_signal_uses_selected_sentence_not_implication() -> None:
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

    assert signal["heading"] == signal["body"]
    assert signal["heading"].startswith("GWI harmonizes bespoke studies")
    assert signal["heading"] != "Source-backed market signal"


def test_core_signal_keeps_yougov_heading_and_body_on_one_insight() -> None:
    fixture_path = (
        Path(__file__).resolve().parent
        / "fixtures"
        / "editorial_temporal"
        / "yougov_core_signal_pairing.json"
    )
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    signal = _build_core_signal(
        tldr_text="",
        executive_summary="",
        insights=fixture["insights"],
    )

    assert signal["heading"] == fixture["expected"]["heading"]
    assert signal["body"] == fixture["expected"]["body"]
    assert signal["insight_id"] == fixture["expected"]["insight_id"]
    assert signal["evidence_id"] == fixture["expected"]["evidence_id"]
    assert "benefits" not in signal["heading"].casefold()
    assert "benefits" not in signal["body"].casefold()


def test_core_signal_batch_03_fixture_pairs_never_use_generic_headings() -> None:
    fixture_path = (
        Path(__file__).resolve().parent
        / "fixtures"
        / "editorial_core_signal"
        / "batch_03_core_signals.json"
    )
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    for report in fixture["reports"]:
        signal = _build_core_signal(
            tldr_text="",
            executive_summary="",
            insights=[report["insight"]],
        )

        assert signal == report["expected"], report["name"]
        assert signal["heading"] != "Source-backed market signal", report["name"]


def test_core_signal_uses_the_selected_benefit_insight_for_both_fields() -> None:
    insight = {
        "id": "benefits",
        "evidence_id": "finding-benefits",
        "text": (
            "The strongest perceived benefits are operational: 54% cite greater "
            "efficiency and cost savings."
        ),
    }

    signal = _build_core_signal(tldr_text="", executive_summary="", insights=[insight])

    assert signal["heading"] == "The strongest perceived benefits are operational."
    assert signal["body"] == insight["text"]
    assert signal["insight_id"] == insight["id"]
    assert signal["evidence_id"] == insight["evidence_id"]


def test_core_signal_uses_the_selected_risk_insight_for_both_fields() -> None:
    insight = {
        "id": "risks",
        "evidence_id": "finding-risks",
        "text": (
            "Misinformation and deepfakes are the leading concern at 57%; privacy "
            "follows at 49% and job displacement at 44%."
        ),
    }

    signal = _build_core_signal(tldr_text="", executive_summary="", insights=[insight])

    assert (
        signal["heading"]
        == "Misinformation and deepfakes are the leading concern at 57%."
    )
    assert signal["body"] == insight["text"]
    assert signal["insight_id"] == insight["id"]
    assert signal["evidence_id"] == insight["evidence_id"]


def test_core_signal_shortens_a_long_selected_insight() -> None:
    insight = {
        "id": "funnel-coverage",
        "evidence_id": "finding-funnel",
        "text": (
            "Brand tracking pinpoints where audiences drop out of the purchase "
            "funnel and reveals emotional gaps that weaken conversion."
        ),
    }

    signal = _build_core_signal(tldr_text="", executive_summary="", insights=[insight])

    assert signal["heading"] == (
        "Brand tracking pinpoints where audiences drop out of the purchase funnel."
    )
    assert signal["body"] == insight["text"]
    assert signal["insight_id"] == insight["id"]
    assert signal["evidence_id"] == insight["evidence_id"]


def test_core_signal_retains_normalized_insight_identity() -> None:
    insights = _coerce_insights(
        [
            {
                "id": "risk-insight",
                "evidence_id": "finding-risk",
                "text": "Misinformation and deepfakes are the leading concern at 57%.",
            }
        ],
        report_title="YouGov AI report",
    )

    signal = _build_core_signal(tldr_text="", executive_summary="", insights=insights)

    assert signal["heading"] == signal["body"]
    assert signal["insight_id"] == "risk-insight"
    assert signal["evidence_id"] == "finding-risk"


def test_core_signal_preserves_selected_numeric_values() -> None:
    cases = (
        (
            "decimal",
            "Growth reaches 12.5% in the tracked market; leaders should plan "
            "carefully for sustained cross-channel demand.",
            "Growth reaches 12.5% in the tracked market.",
        ),
        (
            "time",
            "Super Users spend 17:06 daily compared with other audiences; "
            "retailers need plans.",
            "Super Users spend 17:06 daily compared with other audiences.",
        ),
        (
            "ratio",
            "Premium streaming inventory converts at a 3:1 ratio; buyers need "
            "plans for concentrated demand across the year.",
            "Premium streaming inventory converts at a 3:1 ratio.",
        ),
    )

    for identifier, text, heading in cases:
        signal = _build_core_signal(
            tldr_text="",
            executive_summary="",
            insights=[
                {
                    "id": identifier,
                    "evidence_id": f"finding-{identifier}",
                    "text": text,
                }
            ],
        )

        assert signal["heading"] == heading
        assert signal["body"] == text
        assert signal["insight_id"] == identifier
        assert signal["evidence_id"] == f"finding-{identifier}"


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


def test_core_signal_uses_complete_heading_for_long_time_sentence() -> None:
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

    assert signal["heading"] == signal["body"]
    assert signal["heading"] != "Source-backed market signal"
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


def test_render_sanitizer_preserves_day_number_metric_terms() -> None:
    text = "Day-1 retention improved, while day-7 retention stayed stable."

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
