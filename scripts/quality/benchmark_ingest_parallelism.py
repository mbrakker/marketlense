"""Select bounded ingest worker profiles from comparable benchmark samples."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, replace
from decimal import Decimal, InvalidOperation
from pathlib import Path
from statistics import median
from threading import BoundedSemaphore

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.contracts.drive import DriveFile  # noqa: E402
from src.contracts.ingest import IngestOutcome, IngestSettings  # noqa: E402
from src.orchestrators import ingest_orchestrator as ingest_orchestrator  # noqa: E402
from src.utils.logging import new_run_context  # noqa: E402


@dataclass(frozen=True)
class IngestWorkerProfile:
    outer_workers: int
    inner_workers: int


@dataclass(frozen=True)
class IngestWorkerBenchmarkResult:
    report_count: int
    profile: IngestWorkerProfile
    samples_ms: tuple[int, ...]
    quality_passed: bool
    estimated_cost_usd: str
    outcome_digest: str


@dataclass(frozen=True)
class IngestWorkerRecommendation:
    report_count: int
    baseline_profile: IngestWorkerProfile
    selected_profile: IngestWorkerProfile
    baseline_median_ms: int
    selected_median_ms: int
    speedup_ratio: float


_BASELINE_PROFILE = IngestWorkerProfile(outer_workers=5, inner_workers=5)
_DEFAULT_PROFILES = (
    _BASELINE_PROFILE,
    IngestWorkerProfile(outer_workers=1, inner_workers=1),
    IngestWorkerProfile(outer_workers=1, inner_workers=2),
    IngestWorkerProfile(outer_workers=1, inner_workers=4),
    IngestWorkerProfile(outer_workers=2, inner_workers=2),
    IngestWorkerProfile(outer_workers=4, inner_workers=1),
)
_DEFAULT_REPORT_COUNTS = (1, 5, 10)
_RESOURCE_LIMIT = 4
_RESOURCE_UNITS_PER_REPORT = 4


def run_ingest_worker_matrix(
    *,
    report_counts: tuple[int, ...] = _DEFAULT_REPORT_COUNTS,
    profiles: tuple[IngestWorkerProfile, ...] = _DEFAULT_PROFILES,
    warmups: int = 2,
    runs: int = 7,
    work_unit_ms: int = 30,
) -> list[IngestWorkerBenchmarkResult]:
    """Measure real ingest scheduling with bounded deterministic local work."""
    _validate_matrix_inputs(
        report_counts=report_counts,
        profiles=profiles,
        warmups=warmups,
        runs=runs,
        work_unit_ms=work_unit_ms,
    )
    results: list[IngestWorkerBenchmarkResult] = []
    with tempfile.TemporaryDirectory(prefix="marketlense-ingest-matrix-") as root:
        root_path = Path(root)
        for report_count in report_counts:
            for profile in profiles:
                for _ in range(warmups):
                    _run_ingest_sample(
                        root_path=root_path,
                        report_count=report_count,
                        profile=profile,
                        work_unit_ms=work_unit_ms,
                    )
                samples: list[int] = []
                outcomes: tuple[str, ...] = ()
                for _ in range(runs):
                    elapsed_ms, outcomes = _run_ingest_sample(
                        root_path=root_path,
                        report_count=report_count,
                        profile=profile,
                        work_unit_ms=work_unit_ms,
                    )
                    samples.append(elapsed_ms)
                results.append(
                    IngestWorkerBenchmarkResult(
                        report_count=report_count,
                        profile=profile,
                        samples_ms=tuple(samples),
                        quality_passed=outcomes == tuple(
                            "processed" for _ in range(report_count)
                        ),
                        estimated_cost_usd="0",
                        outcome_digest=_outcome_digest(outcomes),
                    )
                )
    return results


def build_worker_matrix_artifact(
    results: list[IngestWorkerBenchmarkResult],
    *,
    warmups: int,
    runs: int,
    work_unit_ms: int,
) -> dict[str, object]:
    """Build a scalar artifact suitable for retained local benchmark evidence."""
    recommendations = select_optimal_profiles(results)
    return {
        "schema_version": "1.0",
        "measurement_profile_hash": _measurement_profile_hash(
            results=results,
            warmups=warmups,
            runs=runs,
            work_unit_ms=work_unit_ms,
        ),
        "resource_limit": _RESOURCE_LIMIT,
        "resource_units_per_report": _RESOURCE_UNITS_PER_REPORT,
        "warmups": warmups,
        "runs": runs,
        "work_unit_ms": work_unit_ms,
        "results": [asdict(result) for result in results],
        "recommendations": [
            asdict(recommendations[report_count])
            for report_count in sorted(recommendations)
        ],
    }


def select_optimal_profiles(
    results: list[IngestWorkerBenchmarkResult],
) -> dict[int, IngestWorkerRecommendation]:
    """Choose the fastest quality- and cost-equivalent profile per batch size."""
    recommendations: dict[int, IngestWorkerRecommendation] = {}
    for report_count in sorted({result.report_count for result in results}):
        cohort = [result for result in results if result.report_count == report_count]
        baseline = _baseline_for(cohort)
        baseline_cost = _cost(baseline.estimated_cost_usd)
        eligible = [
            result
            for result in cohort
            if result.quality_passed
            and result.outcome_digest == baseline.outcome_digest
            and _cost(result.estimated_cost_usd) <= baseline_cost
        ]
        if not eligible:
            continue
        selected = min(
            eligible,
            key=lambda result: (
                _median_ms(result),
                _selection_key(result, report_count=report_count),
            ),
        )
        baseline_median = _median_ms(baseline)
        selected_median = _median_ms(selected)
        recommendations[report_count] = IngestWorkerRecommendation(
            report_count=report_count,
            baseline_profile=baseline.profile,
            selected_profile=selected.profile,
            baseline_median_ms=baseline_median,
            selected_median_ms=selected_median,
            speedup_ratio=round(baseline_median / selected_median, 4),
        )
    return recommendations


def _baseline_for(
    cohort: list[IngestWorkerBenchmarkResult],
) -> IngestWorkerBenchmarkResult:
    for result in cohort:
        if result.profile == IngestWorkerProfile(outer_workers=5, inner_workers=5):
            return result
    raise ValueError("each report-count cohort requires the current 5x5 baseline")


def _median_ms(result: IngestWorkerBenchmarkResult) -> int:
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


def _selection_key(
    result: IngestWorkerBenchmarkResult, *, report_count: int
) -> tuple[int, int, int, int]:
    profile = result.profile
    nested_workers = profile.outer_workers * profile.inner_workers
    if report_count == 1:
        preference = (profile.outer_workers, profile.inner_workers)
    else:
        preference = (profile.inner_workers, profile.outer_workers)
    return (nested_workers, *preference, _median_ms(result))


def _run_ingest_sample(
    *,
    root_path: Path,
    report_count: int,
    profile: IngestWorkerProfile,
    work_unit_ms: int,
) -> tuple[int, tuple[str, ...]]:
    sample_root = root_path / (
        f"reports-{report_count}-outer-{profile.outer_workers}"
        f"-inner-{profile.inner_workers}-{time.monotonic_ns()}"
    )
    settings = _settings_for_sample(
        sample_root=sample_root,
        report_count=report_count,
        profile=profile,
    )
    files = [
        DriveFile(
            schema_version="1.0",
            file_id=f"benchmark-{index:02d}",
            name=f"benchmark-{index:02d}.pdf",
            modified_time=None,
            md5_checksum=f"benchmark-md5-{index:02d}",
        )
        for index in range(report_count)
    ]
    resource_slots = BoundedSemaphore(_RESOURCE_LIMIT)

    def process_file(file, index, current_settings, root_ctx, force_report_cards):
        del current_settings, root_ctx, force_report_cards
        with ThreadPoolExecutor(max_workers=profile.inner_workers) as executor:
            futures = [
                executor.submit(
                    _run_bounded_work,
                    resource_slots=resource_slots,
                    work_unit_ms=work_unit_ms,
                )
                for _ in range(_RESOURCE_UNITS_PER_REPORT)
            ]
            for future in futures:
                future.result()
        return ingest_orchestrator._FileProcessResult(
            index=index,
            outcome=IngestOutcome(
                schema_version="1.0",
                file_id=file.file_id,
                name=file.name or file.file_id,
                md5=file.md5_checksum,
                html_path=str(sample_root / f"{file.file_id}.html"),
                status="processed",
            ),
            processed=1,
            had_error=False,
        )

    dependencies = replace(
        ingest_orchestrator.IngestBatchDependencies.default(),
        list_pdfs=lambda _request, _ctx: files,
        batch_should_skip=lambda _files, _state_db, _ctx: {},
        process_file=process_file,
    )
    started_ns = time.monotonic_ns()
    results = ingest_orchestrator._process_ingest_batch(
        files,
        settings=settings,
        deps=dependencies,
        root_ctx=new_run_context(task_id="ingest-worker-matrix"),
        force_report_cards=False,
    )
    elapsed_ms = round((time.monotonic_ns() - started_ns) / 1_000_000)
    return elapsed_ms, tuple(str(result.outcome.status) for result in results)


def _settings_for_sample(
    *, sample_root: Path, report_count: int, profile: IngestWorkerProfile
) -> IngestSettings:
    repository_root = Path(__file__).resolve().parents[2]
    return IngestSettings(
        schema_version="1.0",
        google_sa_path="",
        gdrive_folder_id="benchmark-local-only",
        openai_api_key="",
        openai_model="benchmark-local-only",
        batch_limit=report_count,
        output_dir=str(sample_root / "out"),
        cache_dir=str(sample_root / "cache"),
        state_db=str(sample_root / "state.sqlite"),
        reports_db=str(sample_root / "reports.sqlite"),
        category_mapping_path=str(
            repository_root / "src/config/category-mappings.yaml"
        ),
        cover_style_path=str(repository_root / "src/config/cover-styles.yaml"),
        ingest_lock_path=str(sample_root / "ingest.lock"),
        temperature=0.0,
        ingest_worker_limit=profile.outer_workers,
        report_worker_limit=profile.inner_workers,
        source_quarantine_enabled=False,
        vector_store_keep=False,
        model_pricing={},
    )


def _run_bounded_work(*, resource_slots: BoundedSemaphore, work_unit_ms: int) -> None:
    with resource_slots:
        time.sleep(work_unit_ms / 1_000)


def _outcome_digest(outcomes: tuple[str, ...]) -> str:
    return hashlib.sha256("|".join(outcomes).encode("utf-8")).hexdigest()


def _validate_matrix_inputs(
    *,
    report_counts: tuple[int, ...],
    profiles: tuple[IngestWorkerProfile, ...],
    warmups: int,
    runs: int,
    work_unit_ms: int,
) -> None:
    if not report_counts or any(value < 1 for value in report_counts):
        raise ValueError("report_counts must contain positive values")
    if _BASELINE_PROFILE not in profiles:
        raise ValueError("profiles must include the current 5x5 baseline")
    if any(
        profile.outer_workers < 1 or profile.inner_workers < 1
        for profile in profiles
    ):
        raise ValueError("worker counts must be positive")
    if warmups < 0 or runs < 1 or work_unit_ms < 1:
        raise ValueError("warmups, runs, and work_unit_ms must be positive")


def _measurement_profile_hash(
    *,
    results: list[IngestWorkerBenchmarkResult],
    warmups: int,
    runs: int,
    work_unit_ms: int,
) -> str:
    payload = {
        "report_counts": sorted({result.report_count for result in results}),
        "profiles": [
            (result.profile.outer_workers, result.profile.inner_workers)
            for result in results
        ],
        "resource_limit": _RESOURCE_LIMIT,
        "resource_units_per_report": _RESOURCE_UNITS_PER_REPORT,
        "warmups": warmups,
        "runs": runs,
        "work_unit_ms": work_unit_ms,
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=True, sort_keys=True).encode("utf-8")
    ).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--work-unit-ms", type=int, default=30)
    parser.add_argument("--warmups", type=int, default=2)
    parser.add_argument("--runs", type=int, default=7)
    args = parser.parse_args(argv)
    results = run_ingest_worker_matrix(
        warmups=args.warmups,
        runs=args.runs,
        work_unit_ms=args.work_unit_ms,
    )
    artifact = build_worker_matrix_artifact(
        results,
        warmups=args.warmups,
        runs=args.runs,
        work_unit_ms=args.work_unit_ms,
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
