"""Select bounded artifact-batch concurrency from comparable benchmark samples."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from statistics import median, pstdev
from threading import BoundedSemaphore, Lock
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.contracts.artifact_generation import ArtifactRenderTask  # noqa: E402
from src.orchestrators._report_analysis_orchestrator.artifact_batches import (  # noqa: E402
    _execute_artifact_step_batch,
)
from src.utils.logging import new_run_context  # noqa: E402


@dataclass(frozen=True)
class ArtifactWorkerProfile:
    parallel_workers: int
    max_in_flight: int


@dataclass(frozen=True)
class ArtifactBenchmarkResult:
    report_count: int
    profile: ArtifactWorkerProfile
    samples_ms: tuple[int, ...]
    quality_passed: bool
    estimated_cost_usd: str
    outcome_digest: str
    maximum_observed_in_flight: int


@dataclass(frozen=True)
class ArtifactRecommendation:
    report_count: int
    baseline_profile: ArtifactWorkerProfile
    selected_profile: ArtifactWorkerProfile
    baseline_median_ms: int
    selected_median_ms: int
    speedup_ratio: float


_BASELINE_PROFILE = ArtifactWorkerProfile(parallel_workers=5, max_in_flight=5)
_DEFAULT_PROFILES = (_BASELINE_PROFILE,) + tuple(
    ArtifactWorkerProfile(parallel_workers=parallel_workers, max_in_flight=cap)
    for parallel_workers in range(1, 6)
    for cap in range(1, 6)
    if (parallel_workers, cap) != (5, 5)
)
_DEFAULT_REPORT_COUNTS = (1, 5, 10)
_BATCH_WORKER_LIMIT = 5
_STAGE_ONE_STEPS = ("summary", "insights_candidates", "quotes")
_DISTRIBUTION_STEPS = ("expert_comment", "linkedin_post")


class _BoundedDeterministicRenderer:
    def __init__(self, *, max_in_flight: int, latency_ms: int) -> None:
        self._slots = BoundedSemaphore(max_in_flight)
        self._latency_seconds = latency_ms / 1_000
        self._lock = Lock()
        self.calls = 0
        self._active = 0
        self.maximum_observed_in_flight = 0

    def __call__(self, task: ArtifactRenderTask) -> dict[str, str]:
        with self._slots:
            with self._lock:
                self.calls += 1
                self._active += 1
                self.maximum_observed_in_flight = max(
                    self.maximum_observed_in_flight, self._active
                )
            try:
                time.sleep(self._latency_seconds)
                return {
                    "artifact": task.step_name,
                    "namespace": task.namespace,
                }
            finally:
                with self._lock:
                    self._active -= 1


def run_artifact_worker_matrix(
    *,
    report_counts: tuple[int, ...] = _DEFAULT_REPORT_COUNTS,
    profiles: tuple[ArtifactWorkerProfile, ...] = _DEFAULT_PROFILES,
    warmups: int = 2,
    runs: int = 7,
    model_latency_ms: int = 30,
) -> list[ArtifactBenchmarkResult]:
    """Measure the real artifact-batch executor with bounded local rendering."""
    _validate_matrix_inputs(
        report_counts=report_counts,
        profiles=profiles,
        warmups=warmups,
        runs=runs,
        model_latency_ms=model_latency_ms,
    )
    results: list[ArtifactBenchmarkResult] = []
    with tempfile.TemporaryDirectory(prefix="marketlense-artifact-matrix-") as root:
        root_path = Path(root)
        for report_count in report_counts:
            for profile in profiles:
                for _ in range(warmups):
                    _run_artifact_sample(
                        root_path=root_path,
                        report_count=report_count,
                        profile=profile,
                        model_latency_ms=model_latency_ms,
                    )
                samples: list[int] = []
                outcome_digests: set[str] = set()
                quality_passed = True
                maximum_observed_in_flight = 0
                for _ in range(runs):
                    elapsed_ms, digest, quality, observed = _run_artifact_sample(
                        root_path=root_path,
                        report_count=report_count,
                        profile=profile,
                        model_latency_ms=model_latency_ms,
                    )
                    samples.append(elapsed_ms)
                    outcome_digests.add(digest)
                    quality_passed = quality_passed and quality
                    maximum_observed_in_flight = max(
                        maximum_observed_in_flight, observed
                    )
                if len(outcome_digests) != 1:
                    quality_passed = False
                results.append(
                    ArtifactBenchmarkResult(
                        report_count=report_count,
                        profile=profile,
                        samples_ms=tuple(samples),
                        quality_passed=quality_passed,
                        estimated_cost_usd="0",
                        outcome_digest=next(iter(outcome_digests), ""),
                        maximum_observed_in_flight=maximum_observed_in_flight,
                    )
                )
    return results


def build_worker_matrix_artifact(
    results: list[ArtifactBenchmarkResult],
    *,
    warmups: int,
    runs: int,
    model_latency_ms: int,
) -> dict[str, object]:
    """Build a bounded, scalar-only benchmark artifact."""
    recommendations = select_optimal_profiles(results)
    return {
        "schema_version": "1.0",
        "measurement_profile_hash": _measurement_profile_hash(
            results=results,
            warmups=warmups,
            runs=runs,
            model_latency_ms=model_latency_ms,
        ),
        "batch_worker_limit": _BATCH_WORKER_LIMIT,
        "stage_one_steps": list(_STAGE_ONE_STEPS),
        "distribution_steps": list(_DISTRIBUTION_STEPS),
        "warmups": warmups,
        "runs": runs,
        "model_latency_ms": model_latency_ms,
        "results": [asdict(result) for result in results],
        "recommendations": [
            asdict(recommendations[report_count])
            for report_count in sorted(recommendations)
        ],
    }


def select_optimal_profiles(
    results: list[ArtifactBenchmarkResult],
) -> dict[int, ArtifactRecommendation]:
    """Choose the fastest quality- and cost-equivalent profile per batch size."""
    recommendations: dict[int, ArtifactRecommendation] = {}
    for report_count in sorted({result.report_count for result in results}):
        cohort = [result for result in results if result.report_count == report_count]
        baseline = _baseline_for(cohort)
        baseline_cost = _cost(baseline.estimated_cost_usd)
        eligible = [
            result
            for result in cohort
            if result.quality_passed
            and result.outcome_digest == baseline.outcome_digest
            and result.maximum_observed_in_flight <= result.profile.max_in_flight
            and _cost(result.estimated_cost_usd) <= baseline_cost
        ]
        if not eligible:
            continue
        selected = min(
            eligible,
            key=lambda result: (_median_ms(result), _selection_key(result)),
        )
        if selected != baseline and not _is_proven_faster(
            baseline=baseline, candidate=selected
        ):
            selected = baseline
        baseline_median = _median_ms(baseline)
        selected_median = _median_ms(selected)
        recommendations[report_count] = ArtifactRecommendation(
            report_count=report_count,
            baseline_profile=baseline.profile,
            selected_profile=selected.profile,
            baseline_median_ms=baseline_median,
            selected_median_ms=selected_median,
            speedup_ratio=round(baseline_median / selected_median, 4),
        )
    return recommendations


def _run_artifact_sample(
    *,
    root_path: Path,
    report_count: int,
    profile: ArtifactWorkerProfile,
    model_latency_ms: int,
) -> tuple[int, str, bool, int]:
    del root_path
    settings = SimpleNamespace(
        artifact_parallel_workers=profile.parallel_workers,
        artifact_global_max_in_flight=profile.max_in_flight,
    )
    renderer = _BoundedDeterministicRenderer(
        max_in_flight=profile.max_in_flight,
        latency_ms=model_latency_ms,
    )

    def run_report(index: int) -> dict[str, dict[str, dict[str, str]]]:
        report_ctx = new_run_context(task_id=f"artifact-matrix:report-{index:02d}")
        stage_one = _execute_artifact_step_batch(
            settings,
            _tasks_for_steps(_STAGE_ONE_STEPS, report_ctx),
            renderer,
            report_ctx,
            "stage_one",
        )
        distribution = _execute_artifact_step_batch(
            settings,
            _tasks_for_steps(_DISTRIBUTION_STEPS, report_ctx),
            renderer,
            report_ctx,
            "distribution",
        )
        return {"stage_one": stage_one, "distribution": distribution}

    started_ns = time.monotonic_ns()
    with ThreadPoolExecutor(
        max_workers=min(report_count, _BATCH_WORKER_LIMIT)
    ) as executor:
        results_by_report = list(executor.map(run_report, range(report_count)))
    elapsed_ms = round((time.monotonic_ns() - started_ns) / 1_000_000)
    digest = hashlib.sha256(
        json.dumps(results_by_report, ensure_ascii=True, sort_keys=True).encode("utf-8")
    ).hexdigest()
    quality_passed = (
        all(_report_result_is_complete(result) for result in results_by_report)
        and renderer.calls
        == report_count * (len(_STAGE_ONE_STEPS) + len(_DISTRIBUTION_STEPS))
        and renderer.maximum_observed_in_flight <= profile.max_in_flight
    )
    return elapsed_ms, digest, quality_passed, renderer.maximum_observed_in_flight


def _tasks_for_steps(
    steps: tuple[str, ...], ctx
) -> tuple[ArtifactRenderTask, ...]:
    return tuple(
        ArtifactRenderTask(
            schema_version="1.0",
            step_name=step,
            namespace=f"report_vs/artifacts/{step}",
            variables={},
            ctx=ctx,
        )
        for step in steps
    )


def _report_result_is_complete(result: dict[str, dict[str, dict[str, str]]]) -> bool:
    return (
        set(result.get("stage_one", {})) == set(_STAGE_ONE_STEPS)
        and set(result.get("distribution", {})) == set(_DISTRIBUTION_STEPS)
        and all(
            payload.get("artifact") == step
            for step, payload in result.get("stage_one", {}).items()
        )
        and all(
            payload.get("artifact") == step
            for step, payload in result.get("distribution", {}).items()
        )
    )


def _baseline_for(cohort: list[ArtifactBenchmarkResult]) -> ArtifactBenchmarkResult:
    for result in cohort:
        if result.profile == _BASELINE_PROFILE:
            return result
    raise ValueError("each report-count cohort requires the current 5x5 baseline")


def _median_ms(result: ArtifactBenchmarkResult) -> int:
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


def _selection_key(result: ArtifactBenchmarkResult) -> tuple[int, int, int]:
    profile = result.profile
    return (
        profile.parallel_workers * profile.max_in_flight,
        profile.parallel_workers,
        profile.max_in_flight,
    )


def _is_proven_faster(
    *, baseline: ArtifactBenchmarkResult, candidate: ArtifactBenchmarkResult
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


def _coefficient_of_variation(result: ArtifactBenchmarkResult) -> float:
    samples = result.samples_ms
    average = sum(samples) / len(samples)
    return 0.0 if average <= 0 else pstdev(samples) / average


def _validate_matrix_inputs(
    *,
    report_counts: tuple[int, ...],
    profiles: tuple[ArtifactWorkerProfile, ...],
    warmups: int,
    runs: int,
    model_latency_ms: int,
) -> None:
    if not report_counts or any(value < 1 for value in report_counts):
        raise ValueError("report_counts must contain positive values")
    if _BASELINE_PROFILE not in profiles:
        raise ValueError("profiles must include the current 5x5 baseline")
    if any(
        profile.parallel_workers < 1 or profile.max_in_flight < 1
        for profile in profiles
    ):
        raise ValueError("worker counts must be positive")
    if warmups < 0 or runs < 1 or model_latency_ms < 1:
        raise ValueError("warmups, runs, and model_latency_ms must be positive")


def _measurement_profile_hash(
    *,
    results: list[ArtifactBenchmarkResult],
    warmups: int,
    runs: int,
    model_latency_ms: int,
) -> str:
    payload = {
        "report_counts": sorted({result.report_count for result in results}),
        "profiles": [
            (result.profile.parallel_workers, result.profile.max_in_flight)
            for result in results
        ],
        "batch_worker_limit": _BATCH_WORKER_LIMIT,
        "stage_one_steps": _STAGE_ONE_STEPS,
        "distribution_steps": _DISTRIBUTION_STEPS,
        "warmups": warmups,
        "runs": runs,
        "model_latency_ms": model_latency_ms,
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=True, sort_keys=True).encode("utf-8")
    ).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--model-latency-ms", type=int, default=30)
    parser.add_argument("--warmups", type=int, default=2)
    parser.add_argument("--runs", type=int, default=7)
    args = parser.parse_args(argv)
    results = run_artifact_worker_matrix(
        warmups=args.warmups,
        runs=args.runs,
        model_latency_ms=args.model_latency_ms,
    )
    artifact = build_worker_matrix_artifact(
        results,
        warmups=args.warmups,
        runs=args.runs,
        model_latency_ms=args.model_latency_ms,
    )
    output = Path(args.output_json)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(artifact, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(artifact, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
