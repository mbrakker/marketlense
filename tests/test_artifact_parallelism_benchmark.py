from __future__ import annotations

from scripts.quality.benchmark_artifact_parallelism import (
    ArtifactBenchmarkResult,
    ArtifactWorkerProfile,
    run_artifact_worker_matrix,
    select_optimal_profiles,
)


def test_select_optimal_profiles_rejects_quality_regression_and_selects_fastest(
) -> None:
    baseline = ArtifactBenchmarkResult(
        report_count=5,
        profile=ArtifactWorkerProfile(parallel_workers=5, max_in_flight=5),
        samples_ms=(125, 125, 126, 125, 124, 125, 125),
        quality_passed=True,
        estimated_cost_usd="0",
        outcome_digest="matching-artifacts",
        maximum_observed_in_flight=5,
    )
    fastest = ArtifactBenchmarkResult(
        report_count=5,
        profile=ArtifactWorkerProfile(parallel_workers=3, max_in_flight=3),
        samples_ms=(99, 99, 100, 99, 100, 99, 99),
        quality_passed=True,
        estimated_cost_usd="0",
        outcome_digest="matching-artifacts",
        maximum_observed_in_flight=3,
    )
    quality_regression = ArtifactBenchmarkResult(
        report_count=5,
        profile=ArtifactWorkerProfile(parallel_workers=4, max_in_flight=4),
        samples_ms=(90, 90, 91, 90, 89, 90, 90),
        quality_passed=False,
        estimated_cost_usd="0",
        outcome_digest="matching-artifacts",
        maximum_observed_in_flight=4,
    )

    recommendation = select_optimal_profiles(
        [baseline, fastest, quality_regression]
    )[5]

    assert recommendation.baseline_profile == ArtifactWorkerProfile(5, 5)
    assert recommendation.selected_profile == ArtifactWorkerProfile(3, 3)
    assert recommendation.baseline_median_ms == 125
    assert recommendation.selected_median_ms == 99
    assert recommendation.speedup_ratio == 1.2626


def test_worker_matrix_retains_complete_artifact_batches_within_rate_limit() -> None:
    profile = ArtifactWorkerProfile(parallel_workers=2, max_in_flight=2)

    results = run_artifact_worker_matrix(
        report_counts=(1,),
        profiles=(ArtifactWorkerProfile(5, 5), profile),
        warmups=0,
        runs=1,
        model_latency_ms=1,
    )

    result = next(item for item in results if item.profile == profile)
    assert result.quality_passed is True
    assert result.estimated_cost_usd == "0"
    assert result.maximum_observed_in_flight <= profile.max_in_flight
    assert result.outcome_digest
