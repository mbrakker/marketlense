from __future__ import annotations

import json
from pathlib import Path

from scripts.quality.public_advisory_render_benchmark import (
    build_public_advisory_render_benchmark,
)


def test_public_advisory_render_benchmark_reports_coverage_and_leakage(
    tmp_path: Path,
) -> None:
    artifact_path = tmp_path / "artifact.json"
    artifact_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "summary": {
                    "tldr": "Public summary",
                    "executive_summary": "Public executive summary",
                },
                "insights_final": [
                    {"text": "Insight", "so_what": "So what", "now_what": "Now what"}
                ],
                "metric_spine": [
                    {"label": "Growth", "value": "18", "unit": "%"}
                ],
                "executive_advisory": {
                    "decision_brief": {
                        "status": "generated",
                        "strategic_context": "Use the growth signal.",
                    }
                },
                "claim_ledgers": [
                    {
                        "canonical_claim_id": "report:internal:1",
                        "claim_text": "Use the growth signal.",
                        "support_type": "explicit_recommendation",
                        "confidence": "source_backed",
                    }
                ],
            },
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )

    report = build_public_advisory_render_benchmark(
        artifact_paths=[str(artifact_path)],
        output_dir=str(tmp_path / "rendered"),
        screenshot_paths=["populated.png"],
    )

    assert report.schema_version == "1.0"
    assert report.report_count == 1
    assert report.rows[0].advisory_available is True
    assert report.rows[0].metric_spine_count == 1
    assert report.rows[0].claim_support_count == 1
    assert report.rows[0].so_what_coverage == 1.0
    assert report.rows[0].now_what_coverage == 1.0
    assert report.rows[0].internal_id_leak_count == 0
    assert report.rows[0].remediation_targets == []
    assert report.screenshot_paths == ("populated.png",)
