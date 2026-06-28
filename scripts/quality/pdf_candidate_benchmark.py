from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.contracts.candidates import Candidate
from src.contracts.report_assets import ExtractCandidatesRequest
from src.contracts.run_context import RunContext
from src.services.pdf_service import collect_candidates
from src.utils.path_utils import safe_path_segment


@dataclass(frozen=True)
class PdfCandidateBenchmarkBaselineEntry:
    pdf_path: str
    report_name: str
    expected_candidate_count: int
    expected_signature: str
    expected_degraded_page_count: int
    baseline_median_seconds: float
    runtime_warn_percent: float = 25.0
    runtime_fail_percent: float = 75.0


@dataclass(frozen=True)
class PdfCandidateBenchmarkObservation:
    pdf_path: str
    report_name: str
    candidate_count: int
    signature: str
    degraded_page_count: int
    durations_seconds: tuple[float, ...]
    median_seconds: float


@dataclass(frozen=True)
class PdfCandidateBenchmarkIssue:
    pdf_path: str
    reason: str
    detail: str


@dataclass(frozen=True)
class PdfCandidateBenchmarkRow:
    pdf_path: str
    report_name: str
    expected_candidate_count: int
    actual_candidate_count: int | None
    expected_signature: str
    actual_signature: str | None
    expected_degraded_page_count: int
    actual_degraded_page_count: int | None
    baseline_median_seconds: float
    actual_median_seconds: float | None
    runtime_delta_seconds: float | None
    runtime_delta_percent: float | None
    status: str


@dataclass(frozen=True)
class PdfCandidateBenchmarkComparison:
    passed: bool
    failures: tuple[PdfCandidateBenchmarkIssue, ...]
    warnings: tuple[PdfCandidateBenchmarkIssue, ...]
    rows: tuple[PdfCandidateBenchmarkRow, ...]


def candidate_output_signature(candidates: Sequence[Candidate]) -> str:
    payload = [
        {
            "id": candidate.id,
            "kind": candidate.kind,
            "page": candidate.page,
            "bbox": [round(float(value), 3) for value in candidate.bbox],
            "caption": candidate.caption,
            "preview_text": candidate.preview_text,
        }
        for candidate in candidates
    ]
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_benchmark_baseline(
    path: Path,
) -> tuple[PdfCandidateBenchmarkBaselineEntry, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries = payload.get("benchmarks") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        raise ValueError(f"Benchmark baseline must contain a benchmarks list: {path}")
    return tuple(
        PdfCandidateBenchmarkBaselineEntry(
            pdf_path=str(entry["pdf_path"]),
            report_name=str(entry["report_name"]),
            expected_candidate_count=int(entry["expected_candidate_count"]),
            expected_signature=str(entry["expected_signature"]),
            expected_degraded_page_count=int(entry["expected_degraded_page_count"]),
            baseline_median_seconds=float(entry["baseline_median_seconds"]),
            runtime_warn_percent=float(entry.get("runtime_warn_percent", 25.0)),
            runtime_fail_percent=float(entry.get("runtime_fail_percent", 75.0)),
        )
        for entry in entries
    )


def compare_benchmark_observations(
    *,
    baseline_entries: Sequence[PdfCandidateBenchmarkBaselineEntry],
    observations: Sequence[PdfCandidateBenchmarkObservation],
    skipped_pdf_paths: Sequence[str] = (),
    allow_missing_assets: bool = False,
    fail_on_runtime_regression: bool = False,
) -> PdfCandidateBenchmarkComparison:
    observations_by_path = {
        observation.pdf_path: observation for observation in observations
    }
    skipped = set(skipped_pdf_paths)
    failures: list[PdfCandidateBenchmarkIssue] = []
    warnings: list[PdfCandidateBenchmarkIssue] = []
    rows: list[PdfCandidateBenchmarkRow] = []

    for entry in baseline_entries:
        observation = observations_by_path.get(entry.pdf_path)
        if observation is None:
            issue = PdfCandidateBenchmarkIssue(
                pdf_path=entry.pdf_path,
                reason="benchmark_pdf_missing",
                detail="Benchmark PDF asset was not available for this run.",
            )
            if allow_missing_assets and entry.pdf_path in skipped:
                warnings.append(issue)
                rows.append(_missing_row(entry))
                continue
            failures.append(issue)
            rows.append(_missing_row(entry))
            continue

        row_status = "passed"
        if observation.candidate_count != entry.expected_candidate_count:
            row_status = "failed"
            failures.append(
                PdfCandidateBenchmarkIssue(
                    pdf_path=entry.pdf_path,
                    reason="candidate_count_changed",
                    detail=(
                        f"expected {entry.expected_candidate_count}, "
                        f"observed {observation.candidate_count}"
                    ),
                )
            )
        if observation.signature != entry.expected_signature:
            row_status = "failed"
            failures.append(
                PdfCandidateBenchmarkIssue(
                    pdf_path=entry.pdf_path,
                    reason="candidate_signature_changed",
                    detail=(
                        f"expected {entry.expected_signature}, "
                        f"observed {observation.signature}"
                    ),
                )
            )
        if observation.degraded_page_count != entry.expected_degraded_page_count:
            row_status = "failed"
            failures.append(
                PdfCandidateBenchmarkIssue(
                    pdf_path=entry.pdf_path,
                    reason="degraded_page_count_changed",
                    detail=(
                        f"expected {entry.expected_degraded_page_count}, "
                        f"observed {observation.degraded_page_count}"
                    ),
                )
            )

        delta_seconds = observation.median_seconds - entry.baseline_median_seconds
        delta_percent = (
            (delta_seconds / entry.baseline_median_seconds) * 100.0
            if entry.baseline_median_seconds > 0.0
            else 0.0
        )
        if delta_percent > entry.runtime_fail_percent:
            issue = PdfCandidateBenchmarkIssue(
                pdf_path=entry.pdf_path,
                reason="runtime_regression_failure",
                detail=(
                    f"median runtime increased {delta_percent:.1f}% "
                    f"({entry.baseline_median_seconds:.3f}s -> "
                    f"{observation.median_seconds:.3f}s)"
                ),
            )
            if fail_on_runtime_regression:
                row_status = "failed"
                failures.append(issue)
            else:
                warnings.append(issue)
                if row_status == "passed":
                    row_status = "warned"
        elif delta_percent > entry.runtime_warn_percent:
            warnings.append(
                PdfCandidateBenchmarkIssue(
                    pdf_path=entry.pdf_path,
                    reason="runtime_regression_warning",
                    detail=(
                        f"median runtime increased {delta_percent:.1f}% "
                        f"({entry.baseline_median_seconds:.3f}s -> "
                        f"{observation.median_seconds:.3f}s)"
                    ),
                )
            )
            if row_status == "passed":
                row_status = "warned"

        rows.append(
            PdfCandidateBenchmarkRow(
                pdf_path=entry.pdf_path,
                report_name=entry.report_name,
                expected_candidate_count=entry.expected_candidate_count,
                actual_candidate_count=observation.candidate_count,
                expected_signature=entry.expected_signature,
                actual_signature=observation.signature,
                expected_degraded_page_count=entry.expected_degraded_page_count,
                actual_degraded_page_count=observation.degraded_page_count,
                baseline_median_seconds=entry.baseline_median_seconds,
                actual_median_seconds=observation.median_seconds,
                runtime_delta_seconds=round(delta_seconds, 6),
                runtime_delta_percent=round(delta_percent, 6),
                status=row_status,
            )
        )

    return PdfCandidateBenchmarkComparison(
        passed=not failures,
        failures=tuple(failures),
        warnings=tuple(warnings),
        rows=tuple(rows),
    )


def observe_benchmark_entry(
    entry: PdfCandidateBenchmarkBaselineEntry,
    *,
    root: Path,
    output_root: Path,
    iterations: int,
    parallel_workers: int,
) -> PdfCandidateBenchmarkObservation | None:
    pdf_path = (root / entry.pdf_path).resolve()
    if not pdf_path.exists():
        return None
    durations: list[float] = []
    signature = ""
    candidate_count = 0
    degraded_page_count = 0
    for iteration in range(iterations):
        report_segment = safe_path_segment(entry.report_name, fallback="report")
        out_dir = output_root / report_segment / f"run-{iteration}"
        started = time.perf_counter()
        response = collect_candidates(
            ExtractCandidatesRequest(
                schema_version="1.0",
                pdf_path=pdf_path.as_posix(),
                out_dir=out_dir.as_posix(),
                report_name=entry.report_name,
                parallel_workers=parallel_workers,
            ),
            _ctx(f"pdf-candidate-benchmark:{entry.report_name}:{iteration}"),
        )
        durations.append(time.perf_counter() - started)
        signature = candidate_output_signature(response.candidates)
        candidate_count = len(response.candidates)
        degraded_page_count = len(response.stats.degraded_pages)
    return PdfCandidateBenchmarkObservation(
        pdf_path=entry.pdf_path,
        report_name=entry.report_name,
        candidate_count=candidate_count,
        signature=signature,
        degraded_page_count=degraded_page_count,
        durations_seconds=tuple(round(value, 6) for value in durations),
        median_seconds=round(float(statistics.median(durations)), 6),
    )


def run_benchmark(
    *,
    baseline_path: Path,
    output_root: Path,
    iterations: int,
    parallel_workers: int,
    allow_missing_assets: bool,
    fail_on_runtime_regression: bool,
    output_json: Path | None = None,
) -> tuple[PdfCandidateBenchmarkComparison, dict[str, Any]]:
    baseline_entries = load_benchmark_baseline(baseline_path)
    observations: list[PdfCandidateBenchmarkObservation] = []
    skipped_paths: list[str] = []
    output_root.mkdir(parents=True, exist_ok=True)
    for entry in baseline_entries:
        observation = observe_benchmark_entry(
            entry,
            root=ROOT,
            output_root=output_root,
            iterations=iterations,
            parallel_workers=parallel_workers,
        )
        if observation is None:
            skipped_paths.append(entry.pdf_path)
            continue
        observations.append(observation)

    comparison = compare_benchmark_observations(
        baseline_entries=baseline_entries,
        observations=observations,
        skipped_pdf_paths=tuple(skipped_paths),
        allow_missing_assets=allow_missing_assets,
        fail_on_runtime_regression=fail_on_runtime_regression,
    )
    payload = _payload(
        baseline_path=baseline_path,
        output_root=output_root,
        iterations=iterations,
        parallel_workers=parallel_workers,
        observations=observations,
        skipped_paths=skipped_paths,
        comparison=comparison,
    )
    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(
            json.dumps(payload, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )
    return comparison, payload


def _ctx(task_id: str) -> RunContext:
    return RunContext(
        schema_version="1.0",
        run_id="pdf-candidate-benchmark",
        task_id=task_id,
        span_id=task_id,
    )


def _missing_row(entry: PdfCandidateBenchmarkBaselineEntry) -> PdfCandidateBenchmarkRow:
    return PdfCandidateBenchmarkRow(
        pdf_path=entry.pdf_path,
        report_name=entry.report_name,
        expected_candidate_count=entry.expected_candidate_count,
        actual_candidate_count=None,
        expected_signature=entry.expected_signature,
        actual_signature=None,
        expected_degraded_page_count=entry.expected_degraded_page_count,
        actual_degraded_page_count=None,
        baseline_median_seconds=entry.baseline_median_seconds,
        actual_median_seconds=None,
        runtime_delta_seconds=None,
        runtime_delta_percent=None,
        status="skipped",
    )


def _payload(
    *,
    baseline_path: Path,
    output_root: Path,
    iterations: int,
    parallel_workers: int,
    observations: Sequence[PdfCandidateBenchmarkObservation],
    skipped_paths: Sequence[str],
    comparison: PdfCandidateBenchmarkComparison,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "baseline_path": baseline_path.as_posix(),
        "output_root": output_root.as_posix(),
        "iterations": iterations,
        "parallel_workers": parallel_workers,
        "observations": [asdict(observation) for observation in observations],
        "skipped_pdf_paths": list(skipped_paths),
        "comparison": {
            "passed": comparison.passed,
            "failures": [asdict(issue) for issue in comparison.failures],
            "warnings": [asdict(issue) for issue in comparison.warnings],
            "rows": [asdict(row) for row in comparison.rows],
        },
    }


def _baseline_payload_from_observations(
    observations: Iterable[PdfCandidateBenchmarkObservation],
    *,
    runtime_warn_percent: float,
    runtime_fail_percent: float,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "benchmarks": [
            {
                "pdf_path": observation.pdf_path,
                "report_name": observation.report_name,
                "expected_candidate_count": observation.candidate_count,
                "expected_signature": observation.signature,
                "expected_degraded_page_count": observation.degraded_page_count,
                "baseline_median_seconds": observation.median_seconds,
                "runtime_warn_percent": runtime_warn_percent,
                "runtime_fail_percent": runtime_fail_percent,
            }
            for observation in observations
        ],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run pdf_service.collect_candidates on existing dense PDFs and compare "
            "candidate signatures/counts/runtime against a committed baseline."
        )
    )
    parser.add_argument(
        "--baseline",
        default="docs/quality/pdf_candidate_extraction_benchmark_baseline.json",
    )
    parser.add_argument(
        "--output-root",
        default="out/pdf_candidate_benchmark",
    )
    parser.add_argument("--output-json", default="")
    parser.add_argument("--iterations", type=int, default=2)
    parser.add_argument("--parallel-workers", type=int, default=1)
    parser.add_argument("--allow-missing-assets", action="store_true")
    parser.add_argument("--fail-on-runtime-regression", action="store_true")
    parser.add_argument("--write-current-baseline", default="")
    parser.add_argument("--runtime-warn-percent", type=float, default=25.0)
    parser.add_argument("--runtime-fail-percent", type=float, default=75.0)
    args = parser.parse_args(argv)

    baseline_path = (ROOT / args.baseline).resolve()
    output_root = (ROOT / args.output_root).resolve()
    output_json = (ROOT / args.output_json).resolve() if args.output_json else None
    comparison, payload = run_benchmark(
        baseline_path=baseline_path,
        output_root=output_root,
        iterations=max(1, int(args.iterations)),
        parallel_workers=int(args.parallel_workers),
        allow_missing_assets=bool(args.allow_missing_assets),
        fail_on_runtime_regression=bool(args.fail_on_runtime_regression),
        output_json=output_json,
    )

    if args.write_current_baseline:
        current_baseline_path = (ROOT / args.write_current_baseline).resolve()
        current_baseline_path.parent.mkdir(parents=True, exist_ok=True)
        current_baseline_path.write_text(
            json.dumps(
                _baseline_payload_from_observations(
                    (
                        PdfCandidateBenchmarkObservation(**observation)
                        for observation in payload["observations"]
                    ),
                    runtime_warn_percent=float(args.runtime_warn_percent),
                    runtime_fail_percent=float(args.runtime_fail_percent),
                ),
                ensure_ascii=True,
                indent=2,
            ),
            encoding="utf-8",
        )

    print(json.dumps(payload["comparison"], ensure_ascii=True, indent=2))
    return 0 if comparison.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
