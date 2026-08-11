from __future__ import annotations

from scripts.quality.benchmark_evidence_pack_parallelism import (
    EvidencePackBenchmarkResult,
    EvidencePackWorkerProfile,
    run_evidence_pack_worker_matrix,
    select_optimal_profiles,
)


def test_select_optimal_profiles_rejects_quality_regression_and_selects_fastest(
) -> None:
    baseline = EvidencePackBenchmarkResult(
        report_count=5,
        profile=EvidencePackWorkerProfile(parallel_workers=5, max_in_flight=5),
        samples_ms=(125, 125, 126, 125, 124, 125, 125),
        quality_passed=True,
        estimated_cost_usd="0",
        outcome_digest="matching-packs",
        maximum_observed_in_flight=5,
    )
    fastest = EvidencePackBenchmarkResult(
        report_count=5,
        profile=EvidencePackWorkerProfile(parallel_workers=3, max_in_flight=3),
        samples_ms=(99, 99, 100, 99, 100, 99, 99),
        quality_passed=True,
        estimated_cost_usd="0",
        outcome_digest="matching-packs",
        maximum_observed_in_flight=3,
    )
    quality_regression = EvidencePackBenchmarkResult(
        report_count=5,
        profile=EvidencePackWorkerProfile(parallel_workers=4, max_in_flight=4),
        samples_ms=(90, 90, 91, 90, 89, 90, 90),
        quality_passed=False,
        estimated_cost_usd="0",
        outcome_digest="matching-packs",
        maximum_observed_in_flight=4,
    )

    recommendation = select_optimal_profiles(
        [baseline, fastest, quality_regression]
    )[5]

    assert recommendation.baseline_profile == EvidencePackWorkerProfile(5, 5)
    assert recommendation.selected_profile == EvidencePackWorkerProfile(3, 3)
    assert recommendation.baseline_median_ms == 125
    assert recommendation.selected_median_ms == 99
    assert recommendation.speedup_ratio == 1.2626


def test_worker_matrix_retains_complete_evidence_packs_within_rate_limit() -> None:
    profile = EvidencePackWorkerProfile(parallel_workers=2, max_in_flight=2)

    results = run_evidence_pack_worker_matrix(
        report_counts=(1,),
        profiles=(EvidencePackWorkerProfile(5, 5), profile),
        warmups=0,
        runs=1,
        model_latency_ms=1,
    )

    result = next(item for item in results if item.profile == profile)
    assert result.quality_passed is True
    assert result.estimated_cost_usd == "0"
    assert result.maximum_observed_in_flight <= profile.max_in_flight
    assert result.outcome_digest


def test_select_optimal_profiles_keeps_baseline_when_gain_is_within_noise() -> None:
    baseline = EvidencePackBenchmarkResult(
        report_count=5,
        profile=EvidencePackWorkerProfile(parallel_workers=5, max_in_flight=5),
        samples_ms=(212, 209, 207, 212, 207, 210, 209),
        quality_passed=True,
        estimated_cost_usd="0",
        outcome_digest="matching-packs",
        maximum_observed_in_flight=5,
    )
    noisy_candidate = EvidencePackBenchmarkResult(
        report_count=5,
        profile=EvidencePackWorkerProfile(parallel_workers=1, max_in_flight=5),
        samples_ms=(207, 206, 208, 245, 208, 209, 209),
        quality_passed=True,
        estimated_cost_usd="0",
        outcome_digest="matching-packs",
        maximum_observed_in_flight=5,
    )

    recommendation = select_optimal_profiles([baseline, noisy_candidate])[5]

    assert recommendation.selected_profile == EvidencePackWorkerProfile(5, 5)
    assert recommendation.selected_median_ms == 209
