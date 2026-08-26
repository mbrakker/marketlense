from __future__ import annotations

import json
from pathlib import Path

from scripts.quality.release_evidence_review import (
    build_release_evidence_review,
    render_release_evidence_review_markdown,
    write_release_evidence_review,
)


def _write_manifest(path: Path, *, issues: list[dict[str, str]]) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "release_id": "release-20260628",
                "generated_at": "2026-06-28T12:00:00+00:00",
                "commit_sha": "abc123",
                "command_args": ("manifest",),
                "passed": not issues,
                "artifacts": [
                    {
                        "name": "coverage",
                        "path": "coverage.xml",
                        "required": True,
                        "expected_schema_version": "7.14.1",
                        "schema_version": "7.14.1",
                        "status": "passed" if not issues else "stale",
                        "passed": not issues,
                        "generated_at": "1781589182618",
                        "modified_at": "2026-06-28T11:59:00+00:00",
                        "producer_command": "python scripts/ci/check_coverage.py",
                        "byte_count": 100,
                        "artifact_sha256": "a" * 64,
                    }
                ],
                "issues": issues,
            },
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def test_release_evidence_review_summarizes_clean_manifest(tmp_path: Path) -> None:
    manifest_path = tmp_path / "release_evidence_manifest.json"
    _write_manifest(manifest_path, issues=[])
    telemetry_path, benchmark_path, summary_path = _write_machine_evidence(tmp_path)

    review = build_release_evidence_review(
        manifest_paths=(manifest_path,),
        test_telemetry_path=telemetry_path,
        ci_performance_benchmark_path=benchmark_path,
        executive_summary_path=summary_path,
        generated_at="2026-06-28T13:00:00+00:00",
        today="2026-06-28",
    )

    markdown = render_release_evidence_review_markdown(review)
    assert review.schema_version == "1.0"
    assert review.passed is True
    assert review.artifact_count == 1
    assert review.issue_count == 0
    assert review.unwaived_issue_count == 0
    assert "| coverage | passed | yes | 0 | 0 |" in markdown
    assert "Release Evidence Review" in markdown


def test_release_evidence_review_fails_without_mandatory_machine_inputs(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "release_evidence_manifest.json"
    _write_manifest(manifest_path, issues=[])

    review = build_release_evidence_review(
        manifest_paths=(manifest_path,),
        generated_at="2026-06-28T13:00:00+00:00",
        today="2026-06-28",
    )

    assert review.passed is False
    assert {issue.reason for issue in review.issues} == {
        "mandatory_machine_evidence_missing"
    }


def _write_machine_evidence(
    tmp_path: Path,
    *,
    pytest_exit_code: int = 0,
    failed_test_count: int = 0,
    performance_passed: bool = True,
    commit_sha: str = "abc123",
    run_id: str = "release-20260628",
    summary_claims: dict[str, object] | None = None,
) -> tuple[Path, Path, Path]:
    telemetry_path = tmp_path / "test_telemetry.json"
    benchmark_path = tmp_path / "ci_performance_benchmark.json"
    summary_path = tmp_path / "release_evidence_executive_summary.json"
    tests = [{"outcome": "passed"}] + [
        {"outcome": "failed"} for _ in range(failed_test_count)
    ]
    telemetry = {
        "schema_version": "1.0",
        "repository_commit_sha": commit_sha,
        "evidence_run_id": run_id,
        "pytest_exit_code": pytest_exit_code,
        "test_count": len(tests),
        "tests": tests,
    }
    benchmark = {
        "schema_version": "1.0",
        "repository_commit_sha": commit_sha,
        "evidence_run_id": run_id,
        "passed": performance_passed,
        "quality_passed": performance_passed,
        "test_summary": {
            "total": len(tests),
            "passed": len(tests) - failed_test_count,
            "failed": failed_test_count,
        },
    }
    claims = summary_claims or {
        "pytest_exit_code": pytest_exit_code,
        "failed_test_count": failed_test_count,
        "performance_passed": performance_passed,
        "performance_quality_passed": performance_passed,
    }
    summary = {
        "schema_version": "1.0",
        "repository_commit_sha": commit_sha,
        "evidence_run_id": run_id,
        "release_id": run_id,
        "passed": (
            pytest_exit_code == 0 and failed_test_count == 0 and performance_passed
        ),
        "claims": claims,
    }
    for path, payload in (
        (telemetry_path, telemetry),
        (benchmark_path, benchmark),
        (summary_path, summary),
    ):
        path.write_text(
            json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return telemetry_path, benchmark_path, summary_path


def test_release_evidence_review_rejects_failed_pytest_telemetry(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "release_evidence_manifest.json"
    _write_manifest(manifest_path, issues=[])
    telemetry_path, benchmark_path, summary_path = _write_machine_evidence(
        tmp_path,
        pytest_exit_code=1,
        failed_test_count=1,
    )

    review = build_release_evidence_review(
        manifest_paths=(manifest_path,),
        test_telemetry_path=telemetry_path,
        ci_performance_benchmark_path=benchmark_path,
        executive_summary_path=summary_path,
    )

    assert review.passed is False
    assert {issue.reason for issue in review.issues} >= {
        "pytest_exit_code_nonzero",
        "pytest_failed_tests",
    }


def test_release_evidence_review_rejects_failed_performance_benchmark(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "release_evidence_manifest.json"
    _write_manifest(manifest_path, issues=[])
    telemetry_path, benchmark_path, summary_path = _write_machine_evidence(
        tmp_path,
        performance_passed=False,
    )

    review = build_release_evidence_review(
        manifest_paths=(manifest_path,),
        test_telemetry_path=telemetry_path,
        ci_performance_benchmark_path=benchmark_path,
        executive_summary_path=summary_path,
    )

    assert review.passed is False
    assert {issue.reason for issue in review.issues} >= {
        "ci_performance_benchmark_failed",
        "ci_performance_quality_failed",
    }


def test_release_evidence_review_rejects_mismatched_commit_or_run(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "release_evidence_manifest.json"
    _write_manifest(manifest_path, issues=[])
    telemetry_path, benchmark_path, summary_path = _write_machine_evidence(tmp_path)
    benchmark = json.loads(benchmark_path.read_text(encoding="utf-8"))
    benchmark["repository_commit_sha"] = "different-sha"
    benchmark["evidence_run_id"] = "different-run"
    benchmark_path.write_text(json.dumps(benchmark), encoding="utf-8")

    review = build_release_evidence_review(
        manifest_paths=(manifest_path,),
        test_telemetry_path=telemetry_path,
        ci_performance_benchmark_path=benchmark_path,
        executive_summary_path=summary_path,
    )

    assert review.passed is False
    assert {issue.reason for issue in review.issues} >= {
        "evidence_commit_sha_mismatch",
        "evidence_run_id_mismatch",
    }


def test_release_evidence_review_rejects_contradictory_executive_summary(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "release_evidence_manifest.json"
    _write_manifest(manifest_path, issues=[])
    telemetry_path, benchmark_path, summary_path = _write_machine_evidence(
        tmp_path,
        summary_claims={
            "pytest_exit_code": 0,
            "failed_test_count": 99,
            "performance_passed": True,
            "performance_quality_passed": True,
        },
    )

    review = build_release_evidence_review(
        manifest_paths=(manifest_path,),
        test_telemetry_path=telemetry_path,
        ci_performance_benchmark_path=benchmark_path,
        executive_summary_path=summary_path,
    )

    assert review.passed is False
    assert {issue.reason for issue in review.issues} == {
        "executive_summary_contradicts_machine_evidence"
    }


def test_release_evidence_review_rejects_contradictory_executive_summary_status(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "release_evidence_manifest.json"
    _write_manifest(manifest_path, issues=[])
    telemetry_path, benchmark_path, summary_path = _write_machine_evidence(tmp_path)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["passed"] = False
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    review = build_release_evidence_review(
        manifest_paths=(manifest_path,),
        test_telemetry_path=telemetry_path,
        ci_performance_benchmark_path=benchmark_path,
        executive_summary_path=summary_path,
    )

    assert review.passed is False
    assert {issue.reason for issue in review.issues} == {
        "executive_summary_contradicts_machine_evidence"
    }


def test_release_evidence_review_applies_matching_waiver(tmp_path: Path) -> None:
    manifest_path = tmp_path / "release_evidence_manifest.json"
    waiver_path = tmp_path / "release_evidence_waivers.yaml"
    telemetry_path, benchmark_path, summary_path = _write_machine_evidence(tmp_path)
    _write_manifest(
        manifest_path,
        issues=[
            {
                "artifact_name": "coverage",
                "artifact_path": "coverage.xml",
                "reason": "artifact_stale",
                "detail": "coverage.xml was older than the gate start",
            }
        ],
    )
    waiver_path.write_text(
        "\n".join(
            [
                'schema_version: "1.0"',
                "waivers:",
                "  - artifact_name: coverage",
                "    reason: artifact_stale",
                "    owner: release-owner",
                '    expires_on: "2026-07-01"',
                "    justification: CI rerun reused audited coverage output.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    review = build_release_evidence_review(
        manifest_paths=(manifest_path,),
        test_telemetry_path=telemetry_path,
        ci_performance_benchmark_path=benchmark_path,
        executive_summary_path=summary_path,
        waiver_path=waiver_path,
        generated_at="2026-06-28T13:00:00+00:00",
        today="2026-06-28",
    )

    assert review.passed is False
    assert review.manifest_passed is False
    assert review.issue_count == 1
    assert review.waived_issue_count == 1
    assert review.unwaived_issue_count == 0
    assert review.issues[0].waived is True
    assert review.issues[0].waiver_owner == "release-owner"


def test_release_evidence_review_fails_unwaived_manifest_issue(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "release_evidence_manifest.json"
    telemetry_path, benchmark_path, summary_path = _write_machine_evidence(tmp_path)
    _write_manifest(
        manifest_path,
        issues=[
            {
                "artifact_name": "coverage",
                "artifact_path": "coverage.xml",
                "reason": "artifact_stale",
                "detail": "coverage.xml was older than the gate start",
            }
        ],
    )

    review = build_release_evidence_review(
        manifest_paths=(manifest_path,),
        test_telemetry_path=telemetry_path,
        ci_performance_benchmark_path=benchmark_path,
        executive_summary_path=summary_path,
        generated_at="2026-06-28T13:00:00+00:00",
        today="2026-06-28",
    )

    assert review.passed is False
    assert review.unwaived_issue_count == 1
    assert review.issues[0].waived is False


def test_release_evidence_review_rejects_invalid_waivers(tmp_path: Path) -> None:
    manifest_path = tmp_path / "release_evidence_manifest.json"
    waiver_path = tmp_path / "release_evidence_waivers.yaml"
    telemetry_path, benchmark_path, summary_path = _write_machine_evidence(tmp_path)
    _write_manifest(
        manifest_path,
        issues=[
            {
                "artifact_name": "coverage",
                "artifact_path": "coverage.xml",
                "reason": "artifact_stale",
                "detail": "coverage.xml was older than the gate start",
            }
        ],
    )
    waiver_path.write_text(
        "\n".join(
            [
                'schema_version: "1.0"',
                "waivers:",
                "  - artifact_name: coverage",
                "    reason: artifact_stale",
                "    owner: ''",
                '    expires_on: "2026-06-27"',
                "    justification: ''",
                "  - artifact_name: mutation",
                "    reason: artifact_failed",
                "    owner: release-owner",
                '    expires_on: "2026-07-01"',
                "    justification: not matched",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    review = build_release_evidence_review(
        manifest_paths=(manifest_path,),
        test_telemetry_path=telemetry_path,
        ci_performance_benchmark_path=benchmark_path,
        executive_summary_path=summary_path,
        waiver_path=waiver_path,
        generated_at="2026-06-28T13:00:00+00:00",
        today="2026-06-28",
    )

    assert review.passed is False
    assert {error.reason for error in review.waiver_errors} == {
        "waiver_expired",
        "waiver_justification_missing",
        "waiver_owner_missing",
        "waiver_unmatched",
    }


def test_write_release_evidence_review_persists_json_and_markdown(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "release_evidence_manifest.json"
    output_json = tmp_path / "release_evidence_review.json"
    output_md = tmp_path / "release_evidence_review.md"
    _write_manifest(manifest_path, issues=[])
    telemetry_path, benchmark_path, summary_path = _write_machine_evidence(tmp_path)
    review = build_release_evidence_review(
        manifest_paths=(manifest_path,),
        test_telemetry_path=telemetry_path,
        ci_performance_benchmark_path=benchmark_path,
        executive_summary_path=summary_path,
        generated_at="2026-06-28T13:00:00+00:00",
        today="2026-06-28",
    )

    write_release_evidence_review(
        review,
        output_json_path=output_json,
        output_markdown_path=output_md,
    )

    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert payload["passed"] is True
    assert payload["artifacts"][0]["name"] == "coverage"
    assert output_json.read_text(encoding="utf-8").endswith("\n")
    assert output_md.read_text(encoding="utf-8").endswith("\n")
