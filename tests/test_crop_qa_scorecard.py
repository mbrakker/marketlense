from __future__ import annotations

import json
from pathlib import Path

from scripts.quality.crop_qa_scorecard import (
    build_crop_qa_scorecard,
    build_selection_telemetry,
    compare_crop_qa_scorecards,
    main,
)


def test_crop_qa_scorecard_aggregates_retained_sidecars_and_missing_evidence(
    tmp_path: Path,
) -> None:
    image = tmp_path / "chart.png"
    image.write_bytes(b"png")
    sidecar = image.with_suffix(".png.qa.json")
    sidecar.write_text(
        json.dumps(
            {
                "candidate_id": "chart-1",
                "candidate_type": "chart",
                "mode": "publication_strict",
                "accepted": True,
                "render_dpi": 216,
                "qa": {
                    "accepted": True,
                    "total_score": 0.87,
                    "defect_labels": ["chart_axis_clipped"],
                    "detectors": {
                        "chart_completeness": {"confidence": 0.7},
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    scorecard = build_crop_qa_scorecard(
        [str(sidecar), str(tmp_path / "missing.qa.json")]
    )

    assert scorecard.sidecar_count == 1
    assert scorecard.accepted_count == 1
    assert scorecard.clipping_defect_count == 1
    assert scorecard.artifact_bytes == 3
    assert scorecard.detector_confidence == {"chart_completeness": 0.7}
    assert scorecard.missing_sidecars == (str(tmp_path / "missing.qa.json"),)


def test_selection_telemetry_preserves_operator_only_qa_facts() -> None:
    telemetry = build_selection_telemetry(
        [
            {
                "candidate_id": "chart-1",
                "crop_quality_profile": "publication_strict",
                "crop_qa_sidecar_path": "slices/chart-1.png.qa.json",
                "crop_qa_score": 0.87,
                "crop_qa_defects": ["chart_axis_clipped"],
                "crop_qa_detector_summary": {"chart_completeness": 0.7},
            }
        ]
    )

    assert telemetry[0].quality_profile == "publication_strict"
    assert telemetry[0].qa_sidecar_path.endswith("chart-1.png.qa.json")
    assert telemetry[0].total_score == 0.87
    assert telemetry[0].detector_confidence == {"chart_completeness": 0.7}


def test_scorecard_cli_creates_the_requested_output_directory(tmp_path: Path) -> None:
    image = tmp_path / "chart.png"
    image.write_bytes(b"png")
    sidecar = image.with_suffix(".png.qa.json")
    sidecar.write_text(
        json.dumps({"accepted": True, "qa": {"accepted": True}}),
        encoding="utf-8",
    )
    output_path = tmp_path / "nested" / "scorecard.json"

    assert main([str(sidecar), "--output-json", str(output_path)]) == 0
    assert json.loads(output_path.read_text(encoding="utf-8"))["sidecar_count"] == 1


def test_crop_qa_scorecard_comparison_fails_clipping_regression(tmp_path: Path) -> None:
    accepted = tmp_path / "accepted.png"
    accepted.write_bytes(b"image")
    accepted_sidecar = accepted.with_suffix(".png.qa.json")
    accepted_sidecar.write_text(
        json.dumps({"accepted": True, "qa": {"accepted": True, "total_score": 0.9}}),
        encoding="utf-8",
    )
    rejected = tmp_path / "rejected.png"
    rejected.write_bytes(b"image")
    rejected_sidecar = rejected.with_suffix(".png.qa.json")
    rejected_sidecar.write_text(
        json.dumps(
            {
                "accepted": False,
                "qa": {
                    "accepted": False,
                    "total_score": 0.5,
                    "defect_labels": ["chart_axis_clipped"],
                },
            }
        ),
        encoding="utf-8",
    )

    comparison = compare_crop_qa_scorecards(
        build_crop_qa_scorecard([str(accepted_sidecar)]),
        build_crop_qa_scorecard([str(rejected_sidecar)]),
    )

    assert comparison.accepted_rate_delta == -1.0
    assert "clipping_defects_increased" in comparison.failures
