from __future__ import annotations

from scripts.quality.build_release_evidence_summary import (
    build_release_evidence_summary,
)

REQUIRED_QUALITY_STAGES = (
    "coverage",
    "mutation",
    "quality_non_regression",
    "pdf_candidate_benchmark",
    "pdf_crop_refine_benchmark",
    "pdf_benchmark_trends",
    "public_report_quality",
    "llm_routing_retained_benchmark",
    "workflow_queue_evidence",
    "prompt_fixture_regression",
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
            "test_count": 1,
            "total_run_duration_ms": 1,
            "tests": [
                {
                    "nodeid": "tests/test_one.py::test_one",
                    "duration_ms": 1,
                    "outcome": "passed",
                    "resource_status": "unavailable",
                }
            ],
        },
        ci_performance_benchmark={
            "schema_version": "1.0",
            "repository_commit_sha": "a" * 40,
            "evidence_run_id": "release-123",
            "measurement_profile_hash": "ci:pytest-and-quality-gates:v2",
            "total_run_duration_ms": 1,
            "pytest_duration_ms": 1,
            "quality_command_duration_ms": len(REQUIRED_QUALITY_STAGES),
            "aggregate_command_duration_ms": 1 + len(REQUIRED_QUALITY_STAGES),
            "workflow_elapsed_ms": None,
            "workflow_critical_path_ms": None,
            "workflow_timing_status": "pending_completed_github_actions_timestamps",
            "estimated_cost_usd": None,
            "passed": True,
            "quality_passed": True,
            "quality_validation_errors": [],
            "test_summary": {"total": 1, "passed": 1, "failed": 0},
            "quality_stage_summaries": [
                {
                    "stage": stage,
                    "wall_time_ms": 1,
                    "exit_code": 0,
                    "outcome": "passed",
                    "resource_status": "unavailable",
                }
                for stage in REQUIRED_QUALITY_STAGES
            ],
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


def test_summary_rejects_legacy_green_benchmark_with_missing_quality_stages() -> None:
    summary = build_release_evidence_summary(
        release_id="release-123",
        repository_commit_sha="a" * 40,
        test_telemetry={
            "schema_version": "1.0",
            "repository_commit_sha": "a" * 40,
            "evidence_run_id": "release-123",
            "pytest_exit_code": 0,
            "test_count": 1,
            "total_run_duration_ms": 1,
            "tests": [
                {
                    "nodeid": "tests/test_one.py::test_one",
                    "duration_ms": 1,
                    "outcome": "passed",
                    "resource_status": "unavailable",
                }
            ],
        },
        ci_performance_benchmark={
            "schema_version": "1.0",
            "repository_commit_sha": "a" * 40,
            "evidence_run_id": "release-123",
            "measurement_profile_hash": "ci:pytest-and-quality-gates:v1",
            "passed": True,
            "quality_passed": True,
            "quality_stage_summaries": [],
        },
    )

    assert summary["passed"] is False
