from __future__ import annotations

from scripts.quality.performance_telemetry_baseline import compare_artifacts


def test_comparison_rejects_faster_candidate_when_cost_regresses() -> None:
    result = compare_artifacts(
        baseline={
            "measurement_profile_hash": "profile-1",
            "quality_passed": True,
            "estimated_cost_usd": "0.10",
            "total_run_duration_ms": 1000,
        },
        candidate={
            "measurement_profile_hash": "profile-1",
            "quality_passed": True,
            "estimated_cost_usd": "0.11",
            "total_run_duration_ms": 800,
        },
    )

    assert result["speed_improvement_proven"] is False
    assert result["blocking_reasons"] == ["cost_regression"]


def test_comparison_proves_faster_compatible_candidate_without_regression() -> None:
    result = compare_artifacts(
        baseline={
            "measurement_profile_hash": "profile-1",
            "quality_passed": True,
            "estimated_cost_usd": "0.10",
            "total_run_duration_ms": 1000,
        },
        candidate={
            "measurement_profile_hash": "profile-1",
            "quality_passed": True,
            "estimated_cost_usd": "0.10",
            "total_run_duration_ms": 800,
        },
    )

    assert result["speed_improvement_proven"] is True
    assert result["duration_delta_ms"] == -200


def test_ci_comparison_uses_completed_workflow_wall_and_critical_path() -> None:
    result = compare_artifacts(
        baseline={
            "measurement_profile_hash": "ci:pytest-and-quality-gates:v2",
            "quality_passed": True,
            "estimated_cost_usd": None,
            "total_run_duration_ms": 500,
            "workflow_elapsed_ms": 100_000,
            "workflow_critical_path_ms": 95_000,
            "workflow_timing_status": "completed_github_actions_timestamps",
        },
        candidate={
            "measurement_profile_hash": "ci:pytest-and-quality-gates:v2",
            "quality_passed": True,
            "estimated_cost_usd": None,
            "total_run_duration_ms": 300,
            "workflow_elapsed_ms": 90_000,
            "workflow_critical_path_ms": 86_000,
            "workflow_timing_status": "completed_github_actions_timestamps",
        },
    )

    assert result["duration_metric"] == "workflow_elapsed_ms"
    assert result["duration_delta_ms"] == -10_000
    assert result["critical_path_delta_ms"] == -9_000
    assert result["speed_improvement_proven"] is False


def test_ci_comparison_does_not_use_precompletion_command_totals_as_wall_time() -> None:
    result = compare_artifacts(
        baseline={
            "measurement_profile_hash": "ci:pytest-and-quality-gates:v2",
            "quality_passed": True,
            "estimated_cost_usd": None,
            "total_run_duration_ms": 100_000,
            "workflow_elapsed_ms": None,
            "workflow_critical_path_ms": None,
            "workflow_timing_status": "pending_completed_github_actions_timestamps",
        },
        candidate={
            "measurement_profile_hash": "ci:pytest-and-quality-gates:v2",
            "quality_passed": True,
            "estimated_cost_usd": None,
            "total_run_duration_ms": 1,
            "workflow_elapsed_ms": None,
            "workflow_critical_path_ms": None,
            "workflow_timing_status": "pending_completed_github_actions_timestamps",
        },
    )

    assert result["duration_metric"] == "workflow_elapsed_ms"
    assert result["duration_delta_ms"] is None
    assert result["baseline_duration_ms"] is None
    assert "duration_unavailable" in result["blocking_reasons"]
    assert "workflow_timing_not_completed" in result["blocking_reasons"]
