from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from src.generators.public_editorial_quality_generator import (
    evaluate_public_editorial_quality,
)
from tests._test_public_editorial_quality_generator._shared import (
    _retained_artifacts,
    _rule_ids,
    _set_near_duplicate,
)


def test_public_html_blocks_operational_source_and_editorial_scaffolding() -> None:
    report = evaluate_public_editorial_quality(
        report_id="retained-report",
        artifacts=_retained_artifacts(),
        html=(
            '<a href="https://drive.google.com/file/d/private">Source</a>'
            "<p>Observation: the source says demand rose...</p>"
        ),
    )

    assert report.status == "fail"
    assert {
        "public_editorial_quality.private_operational_reference",
        "public_editorial_quality.mechanical_editorial_scaffold",
        "public_editorial_quality.literal_truncation",
    } <= _rule_ids(report)


def test_public_html_ignores_non_visible_text_in_spaced_script_tags() -> None:
    report = evaluate_public_editorial_quality(
        report_id="retained-report",
        artifacts=_retained_artifacts(),
        html="<script >Drive file ID: private-123</script >",
    )

    assert report.status == "pass"
    assert "public_editorial_quality.internal_identifier" not in _rule_ids(report)


def test_public_html_allows_pipe_separated_public_taxonomy_labels() -> None:
    report = evaluate_public_editorial_quality(
        report_id="retained-report",
        artifacts=_retained_artifacts(),
        html="<small>luxury | premium | midscale, Global, announced 2026</small>",
    )

    assert "public_editorial_quality.malformed_extraction_fragment" not in _rule_ids(
        report
    )


def test_public_html_allows_short_designator_segment_in_report_title() -> None:
    report = evaluate_public_editorial_quality(
        report_id="retained-report",
        artifacts=_retained_artifacts(),
        html=(
            "<title>RCP Trends Report | Q1 2026 | MarketBearing</title>"
            "<p>RCP Trends Report | Q1 2026, page 5</p>"
        ),
    )

    assert "public_editorial_quality.malformed_extraction_fragment" not in _rule_ids(
        report
    )


def test_public_html_still_flags_broken_pipe_extraction_remnants() -> None:
    report = evaluate_public_editorial_quality(
        report_id="retained-report",
        artifacts=_retained_artifacts(),
        html="<p>Revenue | 5</p><p>Brand | A</p>",
    )

    assert "public_editorial_quality.malformed_extraction_fragment" in _rule_ids(report)


def test_public_html_allows_ellipsis_that_closes_a_quoted_prompt() -> None:
    report = evaluate_public_editorial_quality(
        report_id="retained-report",
        artifacts=_retained_artifacts(),
        html=(
            "<p>Use the prompt “We are doing this because we believe…” to surface "
            "assumptions.</p>"
        ),
    )

    assert "public_editorial_quality.literal_truncation" not in _rule_ids(report)


def test_mintel_source_heading_ellipsis_is_complete_public_prose() -> None:
    fixture = json.loads(
        (
            Path(__file__).parent
            / "fixtures/public_editorial/mintel_2026_readiness_ellipsis.json"
        ).read_text(encoding="utf-8")
    )
    source = (
        Path(__file__).parent
        / "fixtures/pdf_benchmark/golden/2026_Global_Food_and_Drink_Predictions.pdf"
    )
    assert hashlib.sha256(source.read_bytes()).hexdigest() == fixture["source_sha256"]
    assert fixture["artifact_toc_entry"]["section_title"] == fixture["source_heading"]
    assert fixture["source_heading"].casefold() in fixture["rendered_html"].casefold()
    report = evaluate_public_editorial_quality(
        report_id=fixture["report_id"],
        artifacts=_retained_artifacts(),
        html=fixture["rendered_html"],
    )

    assert report.status == "pass"
    assert fixture["before_quality_rule_id"] not in _rule_ids(report)


def test_public_html_still_blocks_terminal_ellipsis_and_mechanical_scaffold() -> None:
    report = evaluate_public_editorial_quality(
        report_id="retained-report",
        artifacts=_retained_artifacts(),
        html="<p>Observation: demand rose...</p>",
    )

    assert report.status == "fail"
    assert {
        "public_editorial_quality.literal_truncation",
        "public_editorial_quality.mechanical_editorial_scaffold",
    } <= _rule_ids(report)


def test_public_html_source_section_requires_a_public_original_source_link() -> None:
    missing = evaluate_public_editorial_quality(
        report_id="retained-report",
        artifacts=_retained_artifacts(),
        html='<section id="source"><p>Source details</p></section>',
    )
    linked = evaluate_public_editorial_quality(
        report_id="retained-report",
        artifacts=_retained_artifacts(),
        html=(
            '<section id="source">'
            '<a href="https://publisher.example/report" rel="noopener">'
            "Open original source</a></section>"
        ),
    )
    unavailable = evaluate_public_editorial_quality(
        report_id="retained-report",
        artifacts=_retained_artifacts(),
        html='<section id="source"><p>Source URL: Not available</p></section>',
    )

    assert "public_editorial_quality.public_source_provenance_missing" in _rule_ids(
        missing
    )
    assert "public_editorial_quality.public_source_provenance_missing" not in _rule_ids(
        linked
    )
    assert "public_editorial_quality.public_source_provenance_missing" not in _rule_ids(
        unavailable
    )


@pytest.mark.parametrize(
    ("rule_id", "mutate"),
    [
        (
            "public_editorial_quality.unsupported_numeric_claim",
            lambda payload: payload["insights_final"][0].update(
                {"text": "The retained finding reports 99% adoption."}
            ),
        ),
        (
            "public_editorial_quality.material_claim_evidence_missing",
            lambda payload: payload["insights_final"][0].update(
                {"evidence_id": "", "evidence": ""}
            ),
        ),
        (
            "public_editorial_quality.internal_identifier",
            lambda payload: payload["insights_final"][0].update(
                {"text": "Drive file ID: private-123 remains relevant."}
            ),
        ),
        (
            "public_editorial_quality.placeholder",
            lambda payload: payload["insights_final"][0].update(
                {"text": "{{ replace with source-backed insight }}"}
            ),
        ),
        (
            "public_editorial_quality.malformed_extraction_fragment",
            lambda payload: payload["insights_final"][0].update(
                {"text": "The platfor | ms are changing."}
            ),
        ),
        (
            "public_editorial_quality.text_corruption",
            lambda payload: payload["insights_final"][0].update(
                {"text": "Consumer demand rose by 12â€% in the survey."}
            ),
        ),
        ("public_editorial_quality.duplicate_insight", _set_near_duplicate),
        (
            "public_editorial_quality.sentence_fragment",
            lambda payload: payload["insights_final"][0].update(
                {"text": "Across the market, and"}
            ),
        ),
        (
            "public_editorial_quality.ocr_fragment",
            lambda payload: payload["insights_final"][0].update(
                {"text": "The consum3rjourney is changing."}
            ),
        ),
        (
            "public_editorial_quality.generic_figure_label",
            lambda payload: payload.update(
                {
                    "chart_insight_cards": [
                        {
                            "status": "generated",
                            "crop_qa_accepted": True,
                            "title": "Figure 1",
                            "caption": "Retail demand moves across channels.",
                            "evidence_id": "retained-figure",
                        }
                    ]
                }
            ),
        ),
        (
            "public_editorial_quality.fallback_boilerplate",
            lambda payload: payload["insights_final"][0].update(
                {
                    "text": "Decision relevance: source-backed finding.",
                    "evidence": "Decision relevance: source-backed finding.",
                }
            ),
        ),
        (
            "public_editorial_quality.unsupported_certainty",
            lambda payload: payload["insights_final"][0].update(
                {
                    "text": "The evidence will certainly determine the market.",
                    "evidence_status": "limited",
                }
            ),
        ),
        (
            "public_editorial_quality.nonspecific_decision_implication",
            lambda payload: payload["insights_final"][0].update(
                {"now_what": "Review the finding."}
            ),
        ),
    ],
)
def test_public_editorial_blockers_detect_mutations_of_retained_artifact(
    rule_id: str, mutate
) -> None:
    artifacts = deepcopy(_retained_artifacts())
    mutate(artifacts)

    report = evaluate_public_editorial_quality(
        report_id="retained-report", artifacts=artifacts
    )

    assert report.status == "fail"
    assert rule_id in _rule_ids(report)


def test_public_editorial_html_missing_asset_is_a_blocker(tmp_path: Path) -> None:
    report = evaluate_public_editorial_quality(
        report_id="retained-report",
        artifacts=_retained_artifacts(),
        html="<img src='missing-chart.png'>",
        html_path=str(tmp_path / "report.html"),
    )

    assert "public_editorial_quality.missing_asset" in _rule_ids(report)
