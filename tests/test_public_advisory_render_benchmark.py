from __future__ import annotations

from pathlib import Path

from scripts.quality.public_advisory_render_benchmark import (
    build_public_advisory_render_benchmark,
    build_public_advisory_repair_targets,
    compare_public_advisory_benchmark,
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
    assert {
        target["field"] for target in report.rows[0].advisory_remediation_targets
    } == {
        "coverage_role",
        "now_what",
        "report_type_lens",
        "score",
        "so_what",
    }
    assert report.remediation_targets == []
    assert len(report.advisory_remediation_targets) >= 5
    repair_targets = [
        target
        for target in report.rows[0].advisory_remediation_targets
        if target.get("field") == "so_what"
    ]
    assert repair_targets
    assert all(target["status"] == "repair_ready" for target in repair_targets)
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


def test_public_advisory_repair_targets_abstain_without_retained_evidence() -> None:
    targets = build_public_advisory_repair_targets(
        report_id="retained-report",
        insights=[{"id": "insight-1", "text": "A claim without a source id."}],
    )

    assert {target.field for target in targets} == {"so_what", "now_what"}
    assert all(target.status == "abstained" for target in targets)
    assert all(not target.replacement for target in targets)


def test_public_advisory_benchmark_is_baseline_stable_for_same_retained_artifact(
    tmp_path: Path,
) -> None:
    artifact_path = next(
        (Path(__file__).resolve().parent / "fixtures" / "docpacks" / "golden").glob(
            "*/report_analysis/artifacts.json"
        )
    )
    baseline = build_public_advisory_render_benchmark(
        artifact_paths=[str(artifact_path)], output_dir=str(tmp_path / "baseline")
    )
    current = build_public_advisory_render_benchmark(
        artifact_paths=[str(artifact_path)], output_dir=str(tmp_path / "current")
    )

    comparison = compare_public_advisory_benchmark(baseline, current)

    assert comparison.failures == ()
    assert comparison.so_what_coverage_delta == 0.0
