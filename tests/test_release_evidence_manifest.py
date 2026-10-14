from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path

import pytest

from scripts.quality.release_evidence_manifest import (
    ReleaseEvidenceArtifactInput,
    ReleaseEvidenceManifest,
    build_release_evidence_manifest,
    main,
    write_release_evidence_manifest,
)
from scripts.quality.pdf_candidate_benchmark import (
    DEFAULT_BASELINE_PATH,
    PdfCandidateBenchmarkObservation,
    ROOT as PDF_BENCHMARK_ROOT,
    compare_benchmark_observations,
    load_benchmark_baseline,
)

PDF_CANDIDATE_BASELINE_PATH = Path(DEFAULT_BASELINE_PATH)


def _pdf_candidate_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "pdf_path": "cache/benchmark/report.pdf",
        "report_name": "report",
        "expected_candidate_count": 2,
        "actual_candidate_count": 2,
        "expected_pdf_sha256": "a" * 64,
        "actual_pdf_sha256": "a" * 64,
        "expected_signature": "candidate-signature",
        "actual_signature": "candidate-signature",
        "expected_degraded_page_count": 0,
        "actual_degraded_page_count": 0,
        "status": "passed",
    }
    row.update(overrides)
    return row


def _pdf_candidate_manifest(
    tmp_path: Path,
    *,
    comparison: dict[str, object] | None = None,
    observations: list[dict[str, object]] | None = None,
    skipped_pdf_paths: list[str] | None = None,
    baseline_path: str | None = None,
) -> ReleaseEvidenceManifest:
    default_observations, default_comparison = _pdf_candidate_evidence()
    candidate_path = tmp_path / "pdf_candidate_benchmark.json"
    candidate_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "baseline_path": baseline_path
                or str((PDF_BENCHMARK_ROOT / PDF_CANDIDATE_BASELINE_PATH).resolve()),
                "iterations": 3,
                "parallel_workers": 1,
                "output_root": str(tmp_path / "pdf_candidate_benchmark"),
                "observations": (
                    default_observations if observations is None else observations
                ),
                "skipped_pdf_paths": skipped_pdf_paths or [],
                "comparison": (
                    default_comparison if comparison is None else comparison
                ),
            }
        ),
        encoding="utf-8",
    )
    return build_release_evidence_manifest(
        artifact_inputs=(
            ReleaseEvidenceArtifactInput(
                name="pdf_candidate",
                path=candidate_path,
                expected_schema_version="1.0",
            ),
        ),
        release_id="release-20261014",
        commit_sha="abc123",
        command_args=("manifest",),
        generated_at="2026-10-14T12:00:00+00:00",
    )


def _pdf_candidate_evidence(
    *,
    global_food_median_seconds: float | None = None,
    fail_on_runtime_regression: bool = False,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    baseline_entries = load_benchmark_baseline(
        PDF_BENCHMARK_ROOT / PDF_CANDIDATE_BASELINE_PATH
    )
    observations = tuple(
        PdfCandidateBenchmarkObservation(
            pdf_path=entry.pdf_path,
            report_name=entry.report_name,
            candidate_count=entry.expected_candidate_count,
            signature=entry.expected_signature,
            degraded_page_count=entry.expected_degraded_page_count,
            durations_seconds=(
                entry.baseline_median_seconds,
                entry.baseline_median_seconds,
                entry.baseline_median_seconds,
            )
            if (
                global_food_median_seconds is None
                or entry.report_name != "2026_Global_Food_and_Drink_Predictions"
            )
            else (
                global_food_median_seconds,
                global_food_median_seconds,
                global_food_median_seconds,
            ),
            median_seconds=(
                entry.baseline_median_seconds
                if (
                    global_food_median_seconds is None
                    or entry.report_name != "2026_Global_Food_and_Drink_Predictions"
                )
                else global_food_median_seconds
            ),
            pdf_sha256=entry.expected_pdf_sha256,
        )
        for entry in baseline_entries
    )
    comparison = compare_benchmark_observations(
        baseline_entries=baseline_entries,
        observations=observations,
        fail_on_runtime_regression=fail_on_runtime_regression,
    )
    return (
        [asdict(observation) for observation in observations],
        {
            "passed": comparison.passed,
            "failures": [asdict(issue) for issue in comparison.failures],
            "warnings": [asdict(issue) for issue in comparison.warnings],
            "rows": [asdict(row) for row in comparison.rows],
        },
    )


def test_release_evidence_manifest_orders_and_summarizes_artifacts(
    tmp_path: Path,
) -> None:
    health_path = tmp_path / "run_health_scorecard.json"
    candidate_path = tmp_path / "pdf_candidate_benchmark.json"
    observations, comparison = _pdf_candidate_evidence()
    health_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "warnings": [],
                "pdf_benchmark_scorecard": {
                    "passed": True,
                    "evidence_complete": True,
                },
            }
        ),
        encoding="utf-8",
    )
    candidate_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "baseline_path": str(
                    (PDF_BENCHMARK_ROOT / PDF_CANDIDATE_BASELINE_PATH).resolve()
                ),
                "iterations": 3,
                "parallel_workers": 1,
                "output_root": str(tmp_path / "pdf_candidate_benchmark"),
                "observations": observations,
                "skipped_pdf_paths": [],
                "comparison": comparison,
            }
        ),
        encoding="utf-8",
    )

    manifest = build_release_evidence_manifest(
        artifact_inputs=(
            ReleaseEvidenceArtifactInput(
                name="health_scorecard",
                path=health_path,
                expected_schema_version="1.0",
            ),
            ReleaseEvidenceArtifactInput(
                name="pdf_candidate",
                path=candidate_path,
                expected_schema_version="1.0",
            ),
        ),
        release_id="release-20260628",
        commit_sha="abc123",
        command_args=("python", "scripts/quality/release_evidence_manifest.py"),
        generated_at="2026-06-28T12:00:00+00:00",
    )

    assert manifest.schema_version == "1.0"
    assert manifest.release_id == "release-20260628"
    assert manifest.commit_sha == "abc123"
    assert manifest.command_args == (
        "python",
        "scripts/quality/release_evidence_manifest.py",
    )
    assert manifest.passed is True
    assert [artifact.name for artifact in manifest.artifacts] == [
        "health_scorecard",
        "pdf_candidate",
    ]
    assert [artifact.status for artifact in manifest.artifacts] == [
        "passed",
        "passed",
    ]
    assert manifest.artifacts[0].schema_version == "1.0"
    assert manifest.artifacts[0].artifact_sha256
    assert manifest.artifacts[0].byte_count > 0
    assert manifest.issues == ()


def test_release_evidence_manifest_reports_missing_invalid_and_failed_artifacts(
    tmp_path: Path,
) -> None:
    invalid_path = tmp_path / "coverage.json"
    failed_path = tmp_path / "mutation.json"
    invalid_path.write_text("{not-json", encoding="utf-8")
    failed_path.write_text(
        json.dumps({"schema_version": "2.0", "passed": False}),
        encoding="utf-8",
    )

    manifest = build_release_evidence_manifest(
        artifact_inputs=(
            ReleaseEvidenceArtifactInput(
                name="missing_scorecard",
                path=tmp_path / "missing.json",
                expected_schema_version="1.0",
            ),
            ReleaseEvidenceArtifactInput(
                name="invalid_coverage",
                path=invalid_path,
                expected_schema_version="1.0",
            ),
            ReleaseEvidenceArtifactInput(
                name="mutation",
                path=failed_path,
                expected_schema_version="1.0",
            ),
        ),
        release_id="release-20260628",
        commit_sha="abc123",
        command_args=("manifest",),
        generated_at="2026-06-28T12:00:00+00:00",
    )

    assert manifest.passed is False
    assert [artifact.name for artifact in manifest.artifacts] == [
        "invalid_coverage",
        "missing_scorecard",
        "mutation",
    ]
    assert [artifact.status for artifact in manifest.artifacts] == [
        "invalid",
        "missing",
        "failed",
    ]
    assert {issue.reason for issue in manifest.issues} == {
        "artifact_invalid_json",
        "artifact_failed",
        "artifact_missing",
        "schema_version_mismatch",
    }


def test_write_release_evidence_manifest_persists_sorted_json(tmp_path: Path) -> None:
    artifact_path = tmp_path / "trend.json"
    output_path = tmp_path / "release_evidence_manifest.json"
    artifact_path.write_text(
        json.dumps({"schema_version": "1.0", "comparison": {"passed": True}}),
        encoding="utf-8",
    )

    manifest = build_release_evidence_manifest(
        artifact_inputs=(
            ReleaseEvidenceArtifactInput(
                name="trend",
                path=artifact_path,
                expected_schema_version="1.0",
            ),
        ),
        release_id="release-20260628",
        commit_sha="abc123",
        command_args=("manifest",),
        generated_at="2026-06-28T12:00:00+00:00",
    )

    write_release_evidence_manifest(manifest, output_path)
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert payload["schema_version"] == "1.0"
    assert payload["artifacts"][0]["name"] == "trend"
    assert output_path.read_text(encoding="utf-8").endswith("\n")


def test_release_evidence_manifest_accepts_coverage_xml_artifact(
    tmp_path: Path,
) -> None:
    coverage_path = tmp_path / "coverage.xml"
    coverage_path.write_text(
        '<?xml version="1.0" ?><coverage version="7.14.1" '
        'timestamp="1781589182618" line-rate="0.8314"></coverage>',
        encoding="utf-8",
    )

    manifest = build_release_evidence_manifest(
        artifact_inputs=(
            ReleaseEvidenceArtifactInput(
                name="coverage",
                path=coverage_path,
                expected_schema_version="7.14.1",
            ),
        ),
        release_id="release-20260628",
        commit_sha="abc123",
        command_args=("manifest",),
        generated_at="2026-06-28T12:00:00+00:00",
    )

    assert manifest.passed is True
    assert manifest.artifacts[0].schema_version == "7.14.1"
    assert manifest.artifacts[0].status == "passed"
    assert manifest.artifacts[0].generated_at == "1781589182618"


def test_release_evidence_manifest_flags_warning_payloads(tmp_path: Path) -> None:
    warning_path = tmp_path / "trend.json"
    warning_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "comparison": {
                    "passed": True,
                    "failures": [],
                    "warnings": [{"reason": "runtime_trend_regression_warning"}],
                },
            }
        ),
        encoding="utf-8",
    )

    manifest = build_release_evidence_manifest(
        artifact_inputs=(
            ReleaseEvidenceArtifactInput(
                name="trend",
                path=warning_path,
                expected_schema_version="1.0",
            ),
        ),
        release_id="release-20260628",
        commit_sha="abc123",
        command_args=("manifest",),
        generated_at="2026-06-28T12:00:00+00:00",
    )

    assert manifest.passed is False
    assert manifest.artifacts[0].status == "warned"
    assert [issue.reason for issue in manifest.issues] == ["artifact_failed"]


def test_release_evidence_manifest_accepts_only_pdf_runtime_advisories(
    tmp_path: Path,
) -> None:
    observations, comparison = _pdf_candidate_evidence(
        global_food_median_seconds=1.43865
    )
    manifest = _pdf_candidate_manifest(
        tmp_path,
        comparison=comparison,
        observations=observations,
    )

    assert manifest.passed is True
    assert manifest.artifacts[0].status == "warned"
    assert manifest.artifacts[0].passed is True
    assert manifest.issues == ()


def test_release_evidence_manifest_accepts_lenient_runtime_failure_warning(
    tmp_path: Path,
) -> None:
    observations, comparison = _pdf_candidate_evidence(global_food_median_seconds=2.1)
    manifest = _pdf_candidate_manifest(
        tmp_path,
        comparison=comparison,
        observations=observations,
    )

    assert manifest.passed is True
    assert manifest.artifacts[0].status == "warned"
    assert manifest.artifacts[0].passed is True


@pytest.mark.parametrize(
    "row_overrides",
    [
        {"expected_candidate_count": 2, "actual_candidate_count": 3},
        {"expected_pdf_sha256": "a" * 64, "actual_pdf_sha256": "b" * 64},
        {"expected_signature": "expected", "actual_signature": "changed"},
        {"expected_degraded_page_count": 0, "actual_degraded_page_count": 1},
    ],
)
def test_release_evidence_manifest_blocks_pdf_candidate_row_mismatches(
    tmp_path: Path,
    row_overrides: dict[str, object],
) -> None:
    manifest = _pdf_candidate_manifest(
        tmp_path,
        comparison={
            "passed": True,
            "failures": [],
            "warnings": [],
            "rows": [_pdf_candidate_row(**row_overrides)],
        },
    )

    assert manifest.passed is False
    assert manifest.artifacts[0].passed is False
    assert "artifact_failed" in {issue.reason for issue in manifest.issues}


@pytest.mark.parametrize(
    "comparison",
    [
        {
            "passed": False,
            "failures": [{"reason": "runtime_regression_failure"}],
            "warnings": [],
            "rows": [_pdf_candidate_row(status="failed")],
        },
        {
            "passed": False,
            "failures": [],
            "warnings": [],
            "rows": [_pdf_candidate_row()],
        },
        {
            "passed": True,
            "failures": [{"reason": "candidate_signature_changed"}],
            "warnings": [],
            "rows": [_pdf_candidate_row(status="failed")],
        },
        {
            "passed": True,
            "failures": [],
            "warnings": [
                {
                    "pdf_path": "cache/benchmark/report.pdf",
                    "reason": "runtime_regression_warning",
                    "detail": "median runtime increased 25.1%",
                },
                {
                    "pdf_path": "cache/benchmark/report.pdf",
                    "reason": "benchmark_pdf_missing",
                    "detail": "benchmark input was missing",
                },
            ],
            "rows": [_pdf_candidate_row(status="warned")],
        },
        {
            "passed": True,
            "failures": [],
            "warnings": [
                {
                    "pdf_path": "cache/benchmark/report.pdf",
                    "reason": "runtime_regression_warning",
                }
            ],
            "rows": [_pdf_candidate_row(status="warned")],
        },
        {
            "passed": True,
            "failures": [],
            "warnings": "runtime_regression_warning",
            "rows": [_pdf_candidate_row(status="warned")],
        },
        {
            "passed": "true",
            "failures": [],
            "warnings": [],
            "rows": [_pdf_candidate_row()],
        },
        {
            "passed": True,
            "failures": [],
            "warnings": [],
            "rows": [],
        },
        {
            "passed": True,
            "failures": [],
            "warnings": [],
            "rows": [
                _pdf_candidate_row(
                    expected_candidate_count=-1,
                    actual_candidate_count=-1,
                )
            ],
        },
        {
            "passed": True,
            "failures": [],
            "warnings": [],
            "rows": [
                _pdf_candidate_row(
                    expected_degraded_page_count=-1,
                    actual_degraded_page_count=-1,
                )
            ],
        },
        {
            "passed": True,
            "failures": [],
            "warnings": [],
            "rows": [_pdf_candidate_row(), _pdf_candidate_row()],
        },
        {
            "passed": True,
            "failures": [],
            "warnings": [
                {
                    "pdf_path": "cache/benchmark/report.pdf",
                    "reason": "runtime_regression_warning",
                    "detail": "runtime increased above warning threshold",
                },
                {
                    "pdf_path": "cache/benchmark/report.pdf",
                    "reason": "runtime_regression_failure",
                    "detail": "runtime increased above failure threshold",
                },
            ],
            "rows": [_pdf_candidate_row(status="warned")],
        },
        {
            "passed": True,
            "failures": [],
            "warnings": [
                {
                    "pdf_path": "cache/benchmark/report.pdf",
                    "reason": "runtime_regression_warning",
                    "detail": "runtime increased above warning threshold",
                },
                {
                    "pdf_path": "cache/benchmark/report.pdf",
                    "reason": "runtime_regression_warning",
                    "detail": "duplicate warning entry",
                },
            ],
            "rows": [_pdf_candidate_row(status="warned")],
        },
        {
            "passed": True,
            "failures": [],
            "warnings": [
                {
                    "pdf_path": "cache/benchmark/report.pdf",
                    "reason": "runtime_regression_warning",
                    "detail": "runtime increased above warning threshold",
                }
            ],
            "rows": [_pdf_candidate_row(status="passed")],
        },
        {
            "passed": True,
            "failures": [],
            "warnings": [],
            "rows": [_pdf_candidate_row(status="warned")],
        },
        {
            "passed": True,
            "failures": [],
            "warnings": [
                {
                    "pdf_path": "cache/benchmark/other.pdf",
                    "reason": "runtime_regression_warning",
                    "detail": "runtime increased above warning threshold",
                }
            ],
            "rows": [_pdf_candidate_row()],
        },
    ],
)
def test_release_evidence_manifest_fails_closed_for_invalid_pdf_comparisons(
    tmp_path: Path,
    comparison: dict[str, object],
) -> None:
    manifest = _pdf_candidate_manifest(tmp_path, comparison=comparison)

    assert manifest.passed is False
    assert manifest.artifacts[0].passed is False


def test_release_evidence_manifest_rejects_missing_pdf_candidate_inputs(
    tmp_path: Path,
) -> None:
    manifest = _pdf_candidate_manifest(
        tmp_path,
        comparison={
            "passed": True,
            "failures": [],
            "warnings": [],
            "rows": [_pdf_candidate_row()],
        },
        skipped_pdf_paths=["cache/benchmark/missing.pdf"],
    )

    assert manifest.passed is False
    assert manifest.artifacts[0].passed is False


@pytest.mark.parametrize(
    "observations",
    [
        [],
        _pdf_candidate_evidence()[0][:-1],
        [*_pdf_candidate_evidence()[0], _pdf_candidate_evidence()[0][0]],
    ],
    ids=("missing-all", "missing-baseline-pdf", "duplicate-pdf"),
)
def test_release_evidence_manifest_rejects_incomplete_pdf_observations(
    tmp_path: Path,
    observations: list[dict[str, object]],
) -> None:
    manifest = _pdf_candidate_manifest(tmp_path, observations=observations)

    assert manifest.passed is False
    assert manifest.artifacts[0].passed is False


def test_release_evidence_manifest_rejects_noncanonical_pdf_baseline(
    tmp_path: Path,
) -> None:
    manifest = _pdf_candidate_manifest(
        tmp_path,
        baseline_path="baseline.json",
    )

    assert manifest.passed is False
    assert manifest.artifacts[0].passed is False


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("candidate_count", -1),
        ("degraded_page_count", -1),
        ("durations_seconds", []),
        ("durations_seconds", [9.0, 9.0, 9.0]),
        ("median_seconds", "not-a-number"),
    ],
)
def test_release_evidence_manifest_rejects_malformed_pdf_observations(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    observations, comparison = _pdf_candidate_evidence()
    observations[0] = {**observations[0], field: value}

    manifest = _pdf_candidate_manifest(
        tmp_path,
        observations=observations,
        comparison=comparison,
    )

    assert manifest.passed is False
    assert manifest.artifacts[0].passed is False


def test_release_evidence_manifest_rejects_self_consistent_forged_pdf_row(
    tmp_path: Path,
) -> None:
    observations, comparison = _pdf_candidate_evidence()
    rows = list(comparison["rows"])
    first_row = dict(rows[0])
    first_row["expected_candidate_count"] = 99
    first_row["actual_candidate_count"] = 99
    rows[0] = first_row
    comparison["rows"] = rows

    manifest = _pdf_candidate_manifest(
        tmp_path,
        observations=observations,
        comparison=comparison,
    )

    assert manifest.passed is False
    assert manifest.artifacts[0].passed is False


def test_release_evidence_manifest_fails_stale_required_artifact(
    tmp_path: Path,
) -> None:
    artifact_path = tmp_path / "mutation.json"
    artifact_path.write_text(
        json.dumps({"schema_version": "1.0", "passed": True}),
        encoding="utf-8",
    )
    os.utime(artifact_path, (100.0, 100.0))

    manifest = build_release_evidence_manifest(
        artifact_inputs=(
            ReleaseEvidenceArtifactInput(
                name="mutation",
                path=artifact_path,
                expected_schema_version="1.0",
            ),
        ),
        release_id="release-20260628",
        commit_sha="abc123",
        command_args=("manifest",),
        generated_at="2026-06-28T12:00:00+00:00",
        fresh_after="1970-01-01T00:02:00+00:00",
    )

    assert manifest.passed is False
    assert manifest.artifacts[0].status == "stale"
    assert manifest.artifacts[0].modified_at == "1970-01-01T00:01:40+00:00"
    assert [issue.reason for issue in manifest.issues] == ["artifact_stale"]


def test_release_evidence_manifest_fails_commit_sha_mismatch(
    tmp_path: Path,
) -> None:
    artifact_path = tmp_path / "scorecard.json"
    artifact_path.write_text(
        json.dumps({"schema_version": "1.0", "passed": True}),
        encoding="utf-8",
    )

    manifest = build_release_evidence_manifest(
        artifact_inputs=(
            ReleaseEvidenceArtifactInput(
                name="scorecard",
                path=artifact_path,
                expected_schema_version="1.0",
            ),
        ),
        release_id="release-20260628",
        commit_sha="old-sha",
        command_args=("manifest",),
        generated_at="2026-06-28T12:00:00+00:00",
        expected_commit_sha="new-sha",
    )

    assert manifest.passed is False
    assert {issue.reason for issue in manifest.issues} == {"commit_sha_mismatch"}


def test_release_evidence_manifest_accepts_passed_cto_leakage_artifact(
    tmp_path: Path,
) -> None:
    artifact_path = tmp_path / "log_content_leakage.json"
    artifact_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "generated_at": "2026-07-16T12:00:00+00:00",
                "repository_commit_sha": "a" * 40,
                "status": "passed",
                "passed": True,
            }
        ),
        encoding="utf-8",
    )

    manifest = build_release_evidence_manifest(
        artifact_inputs=(
            ReleaseEvidenceArtifactInput(
                name="cto_log_content_leakage",
                path=artifact_path,
                expected_schema_version="1.0",
            ),
        ),
        release_id="release-20260716",
        commit_sha="a" * 40,
        command_args=("manifest",),
        expected_commit_sha="a" * 40,
    )

    assert manifest.passed is True
    assert manifest.artifacts[0].repository_commit_sha == "a" * 40


def test_release_evidence_manifest_blocks_failed_cto_artifact_and_embedded_commit_mismatch(
    tmp_path: Path,
) -> None:
    artifact_path = tmp_path / "consistency_validation.json"
    artifact_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "generated_at": "2026-07-16T12:00:00+00:00",
                "repository_commit_sha": "b" * 40,
                "exact_head_verified": False,
                "status": "failed",
                "passed": False,
            }
        ),
        encoding="utf-8",
    )

    manifest = build_release_evidence_manifest(
        artifact_inputs=(
            ReleaseEvidenceArtifactInput(
                name="cto_consistency",
                path=artifact_path,
                expected_schema_version="1.0",
            ),
        ),
        release_id="release-20260716",
        commit_sha="a" * 40,
        command_args=("manifest",),
        expected_commit_sha="a" * 40,
    )

    assert manifest.passed is False
    assert {issue.reason for issue in manifest.issues} == {
        "artifact_failed",
        "artifact_commit_sha_mismatch",
    }


def test_release_evidence_manifest_applies_freshness_to_cto_artifact(
    tmp_path: Path,
) -> None:
    artifact_path = tmp_path / "log_content_leakage.json"
    artifact_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "generated_at": "2026-07-16T12:00:00+00:00",
                "passed": True,
            }
        ),
        encoding="utf-8",
    )
    os.utime(artifact_path, (100.0, 100.0))

    manifest = build_release_evidence_manifest(
        artifact_inputs=(
            ReleaseEvidenceArtifactInput(
                name="cto_log_content_leakage",
                path=artifact_path,
                expected_schema_version="1.0",
            ),
        ),
        release_id="release-20260716",
        commit_sha="a" * 40,
        command_args=("manifest",),
        fresh_after="1970-01-01T00:02:00+00:00",
    )

    assert [issue.reason for issue in manifest.issues] == ["artifact_stale"]


def test_release_evidence_manifest_allow_issues_writes_failed_manifest(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "release_evidence_manifest.json"

    exit_code = main(
        [
            "--release-id",
            "release-20260628",
            "--artifact",
            f"missing={tmp_path / 'missing.json'}",
            "--expected-schema",
            "missing=1.0",
            "--allow-issues",
            "--output-json",
            str(output_path),
        ]
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload["passed"] is False
    assert payload["issues"][0]["reason"] == "artifact_missing"
