from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from scripts.quality.benchmark_ingest_parallelism import (
    IngestWorkerBenchmarkResult,
    IngestWorkerProfile,
    run_ingest_worker_matrix,
    select_optimal_profiles,
)


def test_select_optimal_profiles_rejects_regressions_and_selects_fastest_profile(
) -> None:
    baseline = IngestWorkerBenchmarkResult(
        report_count=10,
        profile=IngestWorkerProfile(outer_workers=5, inner_workers=5),
        samples_ms=(125, 125, 126, 125, 124, 125, 125),
        quality_passed=True,
        estimated_cost_usd="0",
        outcome_digest="matching-outcomes",
    )
    fastest = IngestWorkerBenchmarkResult(
        report_count=10,
        profile=IngestWorkerProfile(outer_workers=1, inner_workers=4),
        samples_ms=(99, 99, 100, 99, 100, 99, 99),
        quality_passed=True,
        estimated_cost_usd="0",
        outcome_digest="matching-outcomes",
    )
    bounded = IngestWorkerBenchmarkResult(
        report_count=10,
        profile=IngestWorkerProfile(outer_workers=4, inner_workers=1),
        samples_ms=(100, 100, 101, 100, 99, 100, 100),
        quality_passed=True,
        estimated_cost_usd="0",
        outcome_digest="matching-outcomes",
    )
    quality_regression = IngestWorkerBenchmarkResult(
        report_count=10,
        profile=IngestWorkerProfile(outer_workers=2, inner_workers=2),
        samples_ms=(95, 95, 96, 95, 94, 95, 95),
        quality_passed=False,
        estimated_cost_usd="0",
        outcome_digest="matching-outcomes",
    )

    recommendation = select_optimal_profiles(
        [baseline, fastest, bounded, quality_regression]
    )[10]

    assert recommendation.baseline_profile == IngestWorkerProfile(5, 5)
    assert recommendation.selected_profile == IngestWorkerProfile(1, 4)
    assert recommendation.baseline_median_ms == 125
    assert recommendation.selected_median_ms == 99
    assert recommendation.speedup_ratio == 1.2626


def test_worker_matrix_retains_processed_outcomes_for_an_isolated_ingest() -> None:
    results = run_ingest_worker_matrix(
        report_counts=(1,),
        profiles=(IngestWorkerProfile(outer_workers=5, inner_workers=5),),
        warmups=0,
        runs=1,
        work_unit_ms=1,
    )

    assert len(results) == 1
    result = results[0]
    assert result.report_count == 1
    assert result.samples_ms[0] >= 0
    assert result.quality_passed is True
    assert result.estimated_cost_usd == "0"
    assert result.outcome_digest


def test_benchmark_script_runs_directly_from_the_repository_root(
    tmp_path: Path,
) -> None:
    script = (
        Path(__file__).resolve().parents[1]
        / "scripts/quality/benchmark_ingest_parallelism.py"
    )
    output = tmp_path / "benchmark.json"

    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--output-json",
            str(output),
            "--warmups",
            "0",
            "--runs",
            "1",
            "--work-unit-ms",
            "1",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert output.is_file()
