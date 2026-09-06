from __future__ import annotations

from src.generators.public_editorial_quality_generator import (
    evaluate_public_editorial_quality,
)


def test_key_figure_label_can_be_a_reader_facing_metric_phrase() -> None:
    artifacts = {
        "insights_final": [
            {
                "evidence_id": "F1",
                "evidence": "Internet penetration reached 95% of the population.",
            }
        ],
        "key_figures": [
            {
                "label": "Internet penetration",
                "figure": "95%",
                "why_it_matters": "Internet penetration reached 95% of the population.",
                "evidence_id": "F1",
            }
        ],
    }

    report = evaluate_public_editorial_quality(
        report_id="generic-key-figure-label", artifacts=artifacts
    )

    assert all(
        issue.rule_id != "public_editorial_quality.sentence_fragment"
        for issue in report.issues
    )
