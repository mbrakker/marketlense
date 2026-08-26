from __future__ import annotations

from scripts.quality.build_release_evidence_summary import (
    build_release_evidence_summary,
)


def test_summary_derives_machine_claims_from_telemetry_and_benchmark() -> None:
    summary = build_release_evidence_summary(
        release_id="release-123",
        repository_commit_sha="a" * 40,
        test_telemetry={
            "schema_version": "1.0",
            "repository_commit_sha": "a" * 40,
            "evidence_run_id": "release-123",
            "pytest_exit_code": 0,
            "tests": [{"outcome": "passed"}],
        },
        ci_performance_benchmark={
            "schema_version": "1.0",
            "repository_commit_sha": "a" * 40,
            "evidence_run_id": "release-123",
            "passed": True,
            "quality_passed": True,
        },
    )

    assert summary["repository_commit_sha"] == "a" * 40
    assert summary["evidence_run_id"] == "release-123"
    assert summary["claims"] == {
        "pytest_exit_code": 0,
        "failed_test_count": 0,
        "performance_passed": True,
        "performance_quality_passed": True,
    }
