from __future__ import annotations

from scripts.quality.benchmark_pdf_candidate_parallelism import (
    PdfCandidateWorkerBenchmarkResult,
    select_optimal_workers,
)


def test_select_optimal_workers_rejects_quality_regression_and_selects_fastest(
) -> None:
    baseline = PdfCandidateWorkerBenchmarkResult(
        parallel_workers=5,
        samples_ms=(125, 125, 126, 125, 124, 125, 125),
        quality_passed=True,
        estimated_cost_usd="0",
        outcome_digest="matching-candidates",
    )
    fastest = PdfCandidateWorkerBenchmarkResult(
        parallel_workers=3,
        samples_ms=(99, 99, 100, 99, 100, 99, 99),
        quality_passed=True,
        estimated_cost_usd="0",
        outcome_digest="matching-candidates",
    )
    quality_regression = PdfCandidateWorkerBenchmarkResult(
        parallel_workers=4,
        samples_ms=(90, 90, 91, 90, 89, 90, 90),
        quality_passed=False,
        estimated_cost_usd="0",
        outcome_digest="matching-candidates",
    )

    recommendation = select_optimal_workers(
        [baseline, fastest, quality_regression]
    )

    assert recommendation.baseline_parallel_workers == 5
    assert recommendation.selected_parallel_workers == 3
    assert recommendation.baseline_median_ms == 125
    assert recommendation.selected_median_ms == 99
    assert recommendation.speedup_ratio == 1.2626


def test_select_optimal_workers_keeps_baseline_when_gain_is_within_noise() -> None:
    baseline = PdfCandidateWorkerBenchmarkResult(
        parallel_workers=5,
        samples_ms=(
            19640,
            19723,
            19228,
            21287,
            20333,
            21963,
            19313,
            19812,
            20691,
            20166,
            19894,
            20017,
            20250,
            20519,
            20177,
        ),
        quality_passed=True,
        estimated_cost_usd="0",
        outcome_digest="matching-candidates",
    )
    candidate = PdfCandidateWorkerBenchmarkResult(
        parallel_workers=4,
        samples_ms=(
            17628,
            18672,
            17904,
            17910,
            18069,
            18144,
            18068,
            20297,
            20715,
            20611,
            19650,
            20342,
            19913,
            20025,
            20658,
        ),
        quality_passed=True,
        estimated_cost_usd="0",
        outcome_digest="matching-candidates",
    )

    recommendation = select_optimal_workers([baseline, candidate])

    assert recommendation.selected_parallel_workers == 5
    assert recommendation.selected_median_ms == 20166
