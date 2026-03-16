from __future__ import annotations

import json
from pathlib import Path

from scripts.quality.quality_metrics import collect_candidate_pack_metrics


def _write_candidate_pack(root: Path, report_name: str, payload: dict) -> None:
    report_dir = root / report_name / "candidates"
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "candidates.json").write_text(
        json.dumps(payload, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )


def test_collect_candidate_pack_metrics_aggregates_report_corpus(tmp_path) -> None:
    root = tmp_path / "candidate-fixtures"
    _write_candidate_pack(
        root,
        "report-a",
        {
            "schema_version": "1.0",
            "report_id": "report-a",
            "report_name": "report-a",
            "pdf_path": "out/report-a/report.pdf",
            "candidate_count": 2,
            "chart_count": 1,
            "table_count": 1,
            "candidates": [
                {
                    "id": "chart-0-0",
                    "kind": "chart",
                    "page": 0,
                    "bbox": [10, 20, 210, 160],
                    "preview_text": "Figure 1. Revenue growth",
                    "crop_path": "report-a/candidates/chart-0-0.png",
                },
                {
                    "id": "table-0-0",
                    "kind": "table",
                    "page": 0,
                    "bbox": [20, 220, 320, 420],
                    "preview_text": "Table 1. Revenue by segment",
                    "crop_path": "report-a/candidates/table-0-0.png",
                },
            ],
        },
    )
    _write_candidate_pack(
        root,
        "report-b",
        {
            "schema_version": "1.0",
            "report_id": "report-b",
            "report_name": "report-b",
            "pdf_path": "out/report-b/report.pdf",
            "candidate_count": 1,
            "candidates": [
                {
                    "id": "chart-1-0",
                    "kind": "chart",
                    "page": 1,
                    "bbox": [30, 40, 330, 240],
                    "preview_text": "Figure 2. Market outlook",
                    "crop_path": "report-b/candidates/chart-1-0.png",
                }
            ],
        },
    )

    metrics = collect_candidate_pack_metrics(str(root))

    assert metrics == {
        "report_count": 2,
        "pack_non_empty_rate": 1.0,
        "candidate_count_mean": 1.5,
        "chart_count_mean": 1.0,
        "table_count_mean": 0.5,
        "bbox_valid_rate": 1.0,
        "crop_path_coverage_rate": 1.0,
        "preview_text_rate": 1.0,
    }


def test_collect_candidate_pack_metrics_tolerates_invalid_payloads(tmp_path) -> None:
    root = tmp_path / "candidate-fixtures"
    report_dir = root / "broken-report" / "candidates"
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "candidates.json").write_text("{invalid", encoding="utf-8")

    metrics = collect_candidate_pack_metrics(str(root))

    assert metrics == {
        "report_count": 1,
        "pack_non_empty_rate": 0.0,
        "candidate_count_mean": 0.0,
        "chart_count_mean": 0.0,
        "table_count_mean": 0.0,
        "bbox_valid_rate": 1.0,
        "crop_path_coverage_rate": 1.0,
        "preview_text_rate": 1.0,
    }
