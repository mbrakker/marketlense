"""Select PDF visual-candidate worker count from equivalent golden-PDF runs."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from statistics import median, pstdev

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.quality.pdf_candidate_benchmark import (  # noqa: E402
    PdfCandidateBenchmarkBaselineEntry,
    PdfCandidateBenchmarkObservation,
    load_benchmark_baseline,
    observe_benchmark_entry,
)


@dataclass(frozen=True)
class PdfCandidateWorkerBenchmarkResult:
    parallel_workers: int
    samples_ms: tuple[int, ...]
    quality_passed: bool
    estimated_cost_usd: str
    outcome_digest: str


@dataclass(frozen=True)
class PdfCandidateWorkerRecommendation:
    baseline_parallel_workers: int
    selected_parallel_workers: int
    baseline_median_ms: int
    selected_median_ms: int
    speedup_ratio: float


_BASELINE_WORKERS = 5
_DEFAULT_WORKERS = (_BASELINE_WORKERS, 1, 2, 3, 4, 6, 7, 8)


def run_pdf_candidate_worker_matrix(
    *,
    baseline_path: Path,
    output_root: Path,
    workers: tuple[int, ...] = _DEFAULT_WORKERS,
    warmups: int = 2,
    runs: int = 7,
) -> list[PdfCandidateWorkerBenchmarkResult]:
    """Run real visual-candidate extraction for each worker-count profile."""
    _validate_matrix_inputs(workers=workers, warmups=warmups, runs=runs)
    entries = load_benchmark_baseline(baseline_path)
    results: list[PdfCandidateWorkerBenchmarkResult] = []
    for worker_count in workers:
        profile_root = output_root / f"workers-{worker_count}"
        for entry in entries:
            observe_benchmark_entry(
                entry,
                root=ROOT,
                output_root=profile_root / "warmups",
                iterations=warmups,
                parallel_workers=worker_count,
            )
        observations = _observe_entries(
            entries=entries,
            output_root=profile_root / "samples",
            iterations=runs,
            parallel_workers=worker_count,
        )
        samples_ms = _aggregate_samples_ms(observations=observations, runs=runs)
        quality_passed = _observations_match_baseline(entries, observations)
        results.append(
            PdfCandidateWorkerBenchmarkResult(
                parallel_workers=worker_count,
                samples_ms=samples_ms,
                quality_passed=quality_passed,
                estimated_cost_usd="0",
                outcome_digest=_outcome_digest(observations),
            )
        )
    return results


def build_worker_matrix_artifact(
    results: list[PdfCandidateWorkerBenchmarkResult],
    *,
    baseline_path: Path,
    warmups: int,
    runs: int,
) -> dict[str, object]:
    """Build a scalar-only artifact for worker-count selection evidence."""
    recommendation = select_optimal_workers(results)
    return {
        "schema_version": "1.0",
        "measurement_profile_hash": _measurement_profile_hash(
            results=results,
            baseline_path=baseline_path,
            warmups=warmups,
            runs=runs,
        ),
        "baseline_path": baseline_path.as_posix(),
        "warmups": warmups,
        "runs": runs,
        "results": [asdict(result) for result in results],
        "recommendation": asdict(recommendation),
    }


def select_optimal_workers(
    results: list[PdfCandidateWorkerBenchmarkResult],
) -> PdfCandidateWorkerRecommendation:
    """Select a proven faster worker count without quality or cost regression."""
    baseline = _baseline_for(results)
    baseline_cost = _cost(baseline.estimated_cost_usd)
    eligible = [
        result
        for result in results
        if result.quality_passed
        and result.outcome_digest == baseline.outcome_digest
        and _cost(result.estimated_cost_usd) <= baseline_cost
    ]
    if not eligible:
        raise ValueError("no quality- and cost-equivalent worker profile is available")
    selected = min(
        eligible,
        key=lambda result: (_median_ms(result), result.parallel_workers),
    )
    if selected != baseline and not _is_proven_faster(
        baseline=baseline, candidate=selected
    ):
        selected = baseline
    baseline_median = _median_ms(baseline)
    selected_median = _median_ms(selected)
    return PdfCandidateWorkerRecommendation(
        baseline_parallel_workers=baseline.parallel_workers,
        selected_parallel_workers=selected.parallel_workers,
        baseline_median_ms=baseline_median,
        selected_median_ms=selected_median,
        speedup_ratio=round(baseline_median / selected_median, 4),
    )


def _observe_entries(
    *,
    entries: tuple[PdfCandidateBenchmarkBaselineEntry, ...],
    output_root: Path,
    iterations: int,
    parallel_workers: int,
) -> tuple[PdfCandidateBenchmarkObservation, ...]:
    observations: list[PdfCandidateBenchmarkObservation] = []
    for entry in entries:
        observation = observe_benchmark_entry(
            entry,
            root=ROOT,
            output_root=output_root,
            iterations=iterations,
            parallel_workers=parallel_workers,
        )
        if observation is None:
            raise FileNotFoundError(f"benchmark fixture is missing: {entry.pdf_path}")
        observations.append(observation)
    return tuple(observations)


def _aggregate_samples_ms(
    *, observations: tuple[PdfCandidateBenchmarkObservation, ...], runs: int
) -> tuple[int, ...]:
    if len(observations) == 0 or any(
        len(observation.durations_seconds) != runs for observation in observations
    ):
        raise ValueError("each benchmark observation must have every measured run")
    return tuple(
        round(
            sum(observation.durations_seconds[index] for observation in observations)
            * 1_000
        )
        for index in range(runs)
    )


def _observations_match_baseline(
    entries: tuple[PdfCandidateBenchmarkBaselineEntry, ...],
    observations: tuple[PdfCandidateBenchmarkObservation, ...],
) -> bool:
    by_path = {observation.pdf_path: observation for observation in observations}
    if len(by_path) != len(entries):
        return False
    return all(
        (observation := by_path.get(entry.pdf_path)) is not None
        and observation.pdf_sha256 == entry.expected_pdf_sha256
        and observation.candidate_count == entry.expected_candidate_count
        and observation.signature == entry.expected_signature
        and observation.degraded_page_count == entry.expected_degraded_page_count
        for entry in entries
    )


def _outcome_digest(
    observations: tuple[PdfCandidateBenchmarkObservation, ...]
) -> str:
    payload = [
        {
            "pdf_path": observation.pdf_path,
            "candidate_count": observation.candidate_count,
            "signature": observation.signature,
            "degraded_page_count": observation.degraded_page_count,
            "pdf_sha256": observation.pdf_sha256,
        }
        for observation in observations
    ]
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=True, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _baseline_for(
    results: list[PdfCandidateWorkerBenchmarkResult],
) -> PdfCandidateWorkerBenchmarkResult:
    for result in results:
        if result.parallel_workers == _BASELINE_WORKERS:
            return result
    raise ValueError("worker profiles must include the current 5-worker baseline")


def _median_ms(result: PdfCandidateWorkerBenchmarkResult) -> int:
    if not result.samples_ms or any(sample < 0 for sample in result.samples_ms):
        raise ValueError("benchmark samples must be non-negative")
    return round(median(result.samples_ms))


def _cost(value: str) -> Decimal:
    try:
        cost = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("estimated_cost_usd must be a decimal") from exc
    if not cost.is_finite() or cost < 0:
        raise ValueError("estimated_cost_usd must be non-negative")
    return cost


def _is_proven_faster(
    *,
    baseline: PdfCandidateWorkerBenchmarkResult,
    candidate: PdfCandidateWorkerBenchmarkResult,
) -> bool:
    baseline_median = _median_ms(baseline)
    candidate_median = _median_ms(candidate)
    if candidate_median >= baseline_median:
        return False
    maximum_cv = max(
        _coefficient_of_variation(baseline),
        _coefficient_of_variation(candidate),
    )
    if maximum_cv > 0.15:
        return False
    improvement = (baseline_median - candidate_median) / baseline_median
    return improvement >= max(0.03, 2 * maximum_cv)


def _coefficient_of_variation(result: PdfCandidateWorkerBenchmarkResult) -> float:
    samples = result.samples_ms
    average = sum(samples) / len(samples)
    return 0.0 if average <= 0 else pstdev(samples) / average


def _validate_matrix_inputs(
    *, workers: tuple[int, ...], warmups: int, runs: int
) -> None:
    if _BASELINE_WORKERS not in workers:
        raise ValueError("workers must include the current 5-worker baseline")
    if not workers or len(set(workers)) != len(workers) or any(
        value < 1 or value > 8 for value in workers
    ):
        raise ValueError("workers must be distinct values from one through eight")
    if warmups < 0 or runs < 1:
        raise ValueError("warmups must be non-negative and runs must be positive")


def _measurement_profile_hash(
    *,
    results: list[PdfCandidateWorkerBenchmarkResult],
    baseline_path: Path,
    warmups: int,
    runs: int,
) -> str:
    payload = {
        "workers": [result.parallel_workers for result in results],
        "baseline_path": baseline_path.as_posix(),
        "warmups": warmups,
        "runs": runs,
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=True, sort_keys=True).encode("utf-8")
    ).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--baseline",
        default="docs/quality/pdf_candidate_extraction_benchmark_baseline.json",
    )
    parser.add_argument("--output-root", default="out/pdf_candidate_worker_matrix")
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--warmups", type=int, default=2)
    parser.add_argument("--runs", type=int, default=7)
    args = parser.parse_args(argv)
    baseline_path = (ROOT / args.baseline).resolve()
    results = run_pdf_candidate_worker_matrix(
        baseline_path=baseline_path,
        output_root=(ROOT / args.output_root).resolve(),
        warmups=args.warmups,
        runs=args.runs,
    )
    artifact = build_worker_matrix_artifact(
        results,
        baseline_path=baseline_path,
        warmups=args.warmups,
        runs=args.runs,
    )
    output = (ROOT / args.output_json).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(artifact, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(artifact, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
