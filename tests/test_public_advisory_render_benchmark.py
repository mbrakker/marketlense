from __future__ import annotations

from pathlib import Path

from scripts.quality.public_advisory_render_benchmark import (
    build_public_advisory_render_benchmark,
    public_html_quality_issues,
)


def test_public_advisory_render_benchmark_uses_retained_artifact_without_id_leakage(
    tmp_path: Path,
) -> None:
    artifact_path = (
        Path(__file__).resolve().parent
        / "fixtures"
        / "docpacks"
        / "golden"
        / "ias-industry-pulse-report-2026-acig-pdf"
        / "report_analysis"
        / "artifacts.json"
    )

    report = build_public_advisory_render_benchmark(
        artifact_paths=[str(artifact_path)],
        output_dir=str(tmp_path / "rendered"),
        screenshot_paths=["retained-report.png"],
    )

    assert report.schema_version == "1.0"
    assert report.report_count == 1
    assert report.rows[0].report_id == "ias-industry-pulse-report-2026-acig-pdf"
    assert report.rows[0].internal_id_leak_count == 0
    assert report.rows[0].placeholder_count == 0
    assert report.rows[0].raw_fragment_count == 0
    assert report.rows[0].broken_asset_count == 0
    assert report.rows[0].remediation_targets == []
    assert report.rows[0].html_path.endswith(
        "ias-industry-pulse-report-2026-acig-pdf.html"
    )
    assert report.screenshot_paths == ("retained-report.png",)


def test_public_html_quality_issues_detects_public_render_defects(
    tmp_path: Path,
) -> None:
    issues = public_html_quality_issues(
        html="<img src='missing-chart.png'>{{ report_title }}\ufffd",
        html_path=str(tmp_path / "report.html"),
    )

    assert issues == {
        "placeholders": ["{{ report_title }}"],
        "raw_fragments": ["\ufffd"],
        "broken_assets": ["missing-chart.png"],
    }
