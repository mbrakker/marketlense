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
