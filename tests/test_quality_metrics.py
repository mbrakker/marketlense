from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.quality.migrate_golden_artifact_fixtures import migrate_artifact_payload
from scripts.quality.quality_metrics import (
    collect_candidate_pack_metrics,
    collect_docpack_metrics,
)

_GOLDEN_DOCPACK_ROOT = Path(__file__).parent / "fixtures" / "docpacks" / "golden"


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


def test_golden_docpack_artifacts_remain_schema_valid() -> None:
    metrics = collect_docpack_metrics(str(_GOLDEN_DOCPACK_ROOT))

    assert metrics["packs"]["artifacts"]["schema_valid_rate"] == 1.0


def test_migrate_artifact_payload_derives_only_retained_fields() -> None:
    payload = {
        "summary": {"tldr": "The report's retained thesis."},
        "insights_final": [
            {
                "text": "First retained finding.",
                "evidence_id": "finding-1",
                "metric": {"value": "20", "unit": "%"},
            },
            {
                "text": "Second retained finding.",
                "evidence_id": "finding-2",
                "metric": {"value": "2", "label": "Existing label"},
            },
        ],
        "insights_candidates": [],
        "quotes_final": [],
    }

    assert migrate_artifact_payload(payload) is True
    assert payload["editorial_plan"] == {
        "report_thesis": "The report's retained thesis.",
        "themes": [
            {
                "theme": "First retained finding.",
                "priority": 1,
                "evidence_ids": ["finding-1"],
            },
            {
                "theme": "Second retained finding.",
                "priority": 2,
                "evidence_ids": ["finding-2"],
            },
        ],
    }
    assert payload["insights_final"][0]["metric"]["label"] == "First retained finding."
    assert payload["insights_final"][1]["metric"]["label"] == "Existing label"
    assert migrate_artifact_payload(payload) is False


def test_migrate_artifact_payload_rejects_untraceable_editorial_plan() -> None:
    with pytest.raises(ValueError, match="evidence-linked source statements"):
        migrate_artifact_payload({"summary": {"tldr": "A thesis."}})
