from __future__ import annotations

import argparse
import glob
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


@dataclass(frozen=True)
class PdfCropRefineBenchmarkBaselineEntry:
    report_root: str
    report_name: str
    candidate_pack_path: str
    crop_refine_path: str
    crop_artifact_globs: tuple[str, ...]
    expected_candidate_pack_signature: str
    expected_crop_refine_signature: str
    expected_crop_artifact_signature: str
    expected_crop_artifact_count: int
    expected_refine_decision_count: int
    expected_estimated_model_call_count: int
    baseline_median_seconds: float
    runtime_warn_percent: float = 25.0
    runtime_fail_percent: float = 75.0


@dataclass(frozen=True)
class PdfCropRefineBenchmarkObservation:
    report_root: str
    report_name: str
    candidate_pack_signature: str
    crop_refine_signature: str
    crop_artifact_signature: str
    crop_artifact_count: int
    refine_decision_count: int
    estimated_model_call_count: int
    durations_seconds: tuple[float, ...]
    median_seconds: float


@dataclass(frozen=True)
class PdfCropRefineBenchmarkIssue:
    report_root: str
    reason: str
    detail: str


@dataclass(frozen=True)
class PdfCropRefineBenchmarkRow:
    report_root: str
    report_name: str
    expected_candidate_pack_signature: str
    actual_candidate_pack_signature: str | None
    expected_crop_refine_signature: str
    actual_crop_refine_signature: str | None
    expected_crop_artifact_signature: str
    actual_crop_artifact_signature: str | None
    expected_crop_artifact_count: int
    actual_crop_artifact_count: int | None
    expected_refine_decision_count: int
    actual_refine_decision_count: int | None
    expected_estimated_model_call_count: int
    actual_estimated_model_call_count: int | None
    baseline_median_seconds: float
    actual_median_seconds: float | None
    runtime_delta_seconds: float | None
    runtime_delta_percent: float | None
    status: str


@dataclass(frozen=True)
class PdfCropRefineBenchmarkComparison:
    passed: bool
    failures: tuple[PdfCropRefineBenchmarkIssue, ...]
    warnings: tuple[PdfCropRefineBenchmarkIssue, ...]
    rows: tuple[PdfCropRefineBenchmarkRow, ...]


def candidate_pack_signature(payload: dict[str, Any]) -> str:
    candidates_value = payload.get("candidates")
    candidates = candidates_value if isinstance(candidates_value, list) else []
    normalized = {
        "schema_version": payload.get("schema_version"),
        "report_id": payload.get("report_id"),
        "report_name": payload.get("report_name"),
        "candidate_count": int(payload.get("candidate_count") or len(candidates)),
        "chart_count": int(payload.get("chart_count") or 0),
        "table_count": int(payload.get("table_count") or 0),
        "degraded_pages": list(payload.get("degraded_pages") or []),
        "candidates": [
            {
                "id": candidate.get("id"),
                "kind": candidate.get("kind") or candidate.get("type"),
                "page": candidate.get("page"),
                "bbox": _round_bbox(candidate.get("bbox")),
                "caption": candidate.get("caption") or "",
                "preview_text": candidate.get("preview_text") or "",
                "crop_path": candidate.get("crop_path") or "",
            }
            for candidate in candidates
            if isinstance(candidate, dict)
        ],
    }
    return _sha256_json(normalized)


def crop_refine_decision_signature(payload: dict[str, Any]) -> str:
    cache_value = payload.get("_cache")
    cache = cache_value if isinstance(cache_value, dict) else {}
    results_value = payload.get("results")
    results = results_value if isinstance(results_value, list) else []
    normalized = {
        "schema_version": payload.get("schema_version"),
        "profile": {
            "model": cache.get("model"),
            "temperature": cache.get("temperature"),
            "seed": cache.get("seed"),
            "mode": cache.get("mode"),
            "prompt_system_sha256": cache.get("prompt_system_sha256"),
            "prompt_user_sha256": cache.get("prompt_user_sha256"),
        },
        "results": [
            {
                "candidate_id": row.get("candidate_id"),
                "is_valid_candidate": bool(row.get("is_valid_candidate")),
                "refined_bbox": _round_bbox(row.get("refined_bbox")),
                "reason": row.get("reason") or "",
                "page": row.get("page"),
            }
            for row in sorted(
                (row for row in results if isinstance(row, dict)),
                key=lambda item: (
                    int(item.get("page") or -1),
                    str(item.get("candidate_id") or ""),
                    str(item.get("entry_key") or ""),
                ),
            )
        ],
    }
    return _sha256_json(normalized)


def crop_artifact_signature(paths: Sequence[Path], *, root: Path) -> str:
    payload = []
    for path in sorted(paths, key=lambda item: _relative_key(item, root)):
        data = path.read_bytes()
        payload.append(
            {
                "path": _relative_key(path, root),
                "size_bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
    return _sha256_json(payload)


def load_benchmark_baseline(
    path: Path,
) -> tuple[PdfCropRefineBenchmarkBaselineEntry, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries = payload.get("benchmarks") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        raise ValueError(f"Benchmark baseline must contain a benchmarks list: {path}")
    return tuple(
        PdfCropRefineBenchmarkBaselineEntry(
            report_root=str(entry["report_root"]),
            report_name=str(entry["report_name"]),
            candidate_pack_path=str(entry["candidate_pack_path"]),
            crop_refine_path=str(entry["crop_refine_path"]),
            crop_artifact_globs=tuple(
                str(pattern) for pattern in entry["crop_artifact_globs"]
            ),
            expected_candidate_pack_signature=str(
                entry["expected_candidate_pack_signature"]
            ),
            expected_crop_refine_signature=str(entry["expected_crop_refine_signature"]),
            expected_crop_artifact_signature=str(
                entry["expected_crop_artifact_signature"]
            ),
            expected_crop_artifact_count=int(entry["expected_crop_artifact_count"]),
            expected_refine_decision_count=int(entry["expected_refine_decision_count"]),
            expected_estimated_model_call_count=int(
                entry["expected_estimated_model_call_count"]
            ),
            baseline_median_seconds=float(entry["baseline_median_seconds"]),
            runtime_warn_percent=float(entry.get("runtime_warn_percent", 25.0)),
            runtime_fail_percent=float(entry.get("runtime_fail_percent", 75.0)),
        )
        for entry in entries
    )


def compare_benchmark_observations(
    *,
    baseline_entries: Sequence[PdfCropRefineBenchmarkBaselineEntry],
    observations: Sequence[PdfCropRefineBenchmarkObservation],
    skipped_report_roots: Sequence[str] = (),
    allow_missing_assets: bool = False,
    fail_on_runtime_regression: bool = False,
) -> PdfCropRefineBenchmarkComparison:
    observations_by_root = {
        observation.report_root: observation for observation in observations
    }
    skipped = set(skipped_report_roots)
    failures: list[PdfCropRefineBenchmarkIssue] = []
    warnings: list[PdfCropRefineBenchmarkIssue] = []
    rows: list[PdfCropRefineBenchmarkRow] = []

    for entry in baseline_entries:
        observation = observations_by_root.get(entry.report_root)
        if observation is None:
            issue = PdfCropRefineBenchmarkIssue(
                report_root=entry.report_root,
                reason="benchmark_artifacts_missing",
                detail="Benchmark crop/refine artifacts were not available for this run.",
            )
            if allow_missing_assets and entry.report_root in skipped:
                warnings.append(issue)
                rows.append(_missing_row(entry))
                continue
            failures.append(issue)
            rows.append(_missing_row(entry))
            continue

        row_status = "passed"
        if (
            observation.candidate_pack_signature
            != entry.expected_candidate_pack_signature
        ):
            row_status = "failed"
            failures.append(
                PdfCropRefineBenchmarkIssue(
                    report_root=entry.report_root,
                    reason="candidate_pack_signature_changed",
                    detail=(
                        f"expected {entry.expected_candidate_pack_signature}, "
                        f"observed {observation.candidate_pack_signature}"
                    ),
                )
            )
        if observation.crop_refine_signature != entry.expected_crop_refine_signature:
            row_status = "failed"
            failures.append(
                PdfCropRefineBenchmarkIssue(
                    report_root=entry.report_root,
                    reason="crop_refine_signature_changed",
                    detail=(
                        f"expected {entry.expected_crop_refine_signature}, "
                        f"observed {observation.crop_refine_signature}"
                    ),
                )
            )
        if (
            observation.crop_artifact_signature
            != entry.expected_crop_artifact_signature
        ):
            row_status = "failed"
            failures.append(
                PdfCropRefineBenchmarkIssue(
                    report_root=entry.report_root,
                    reason="crop_artifact_signature_changed",
                    detail=(
                        f"expected {entry.expected_crop_artifact_signature}, "
                        f"observed {observation.crop_artifact_signature}"
                    ),
                )
            )
        if observation.crop_artifact_count != entry.expected_crop_artifact_count:
            row_status = "failed"
            failures.append(
                PdfCropRefineBenchmarkIssue(
                    report_root=entry.report_root,
                    reason="crop_artifact_count_changed",
                    detail=(
                        f"expected {entry.expected_crop_artifact_count}, "
                        f"observed {observation.crop_artifact_count}"
                    ),
                )
            )
        if observation.refine_decision_count != entry.expected_refine_decision_count:
            row_status = "failed"
            failures.append(
                PdfCropRefineBenchmarkIssue(
                    report_root=entry.report_root,
                    reason="refine_decision_count_changed",
                    detail=(
                        f"expected {entry.expected_refine_decision_count}, "
                        f"observed {observation.refine_decision_count}"
                    ),
                )
            )
        if (
            observation.estimated_model_call_count
            != entry.expected_estimated_model_call_count
        ):
            row_status = "failed"
            failures.append(
                PdfCropRefineBenchmarkIssue(
                    report_root=entry.report_root,
                    reason="estimated_model_call_count_changed",
                    detail=(
                        f"expected {entry.expected_estimated_model_call_count}, "
                        f"observed {observation.estimated_model_call_count}"
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
            issue = PdfCropRefineBenchmarkIssue(
                report_root=entry.report_root,
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
                PdfCropRefineBenchmarkIssue(
                    report_root=entry.report_root,
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
            PdfCropRefineBenchmarkRow(
                report_root=entry.report_root,
                report_name=entry.report_name,
                expected_candidate_pack_signature=entry.expected_candidate_pack_signature,
                actual_candidate_pack_signature=observation.candidate_pack_signature,
                expected_crop_refine_signature=entry.expected_crop_refine_signature,
                actual_crop_refine_signature=observation.crop_refine_signature,
                expected_crop_artifact_signature=entry.expected_crop_artifact_signature,
                actual_crop_artifact_signature=observation.crop_artifact_signature,
                expected_crop_artifact_count=entry.expected_crop_artifact_count,
                actual_crop_artifact_count=observation.crop_artifact_count,
                expected_refine_decision_count=entry.expected_refine_decision_count,
                actual_refine_decision_count=observation.refine_decision_count,
                expected_estimated_model_call_count=entry.expected_estimated_model_call_count,
                actual_estimated_model_call_count=observation.estimated_model_call_count,
                baseline_median_seconds=entry.baseline_median_seconds,
                actual_median_seconds=observation.median_seconds,
                runtime_delta_seconds=round(delta_seconds, 6),
                runtime_delta_percent=round(delta_percent, 6),
                status=row_status,
            )
        )

    return PdfCropRefineBenchmarkComparison(
        passed=not failures,
        failures=tuple(failures),
        warnings=tuple(warnings),
        rows=tuple(rows),
    )


def observe_benchmark_entry(
    entry: PdfCropRefineBenchmarkBaselineEntry,
    *,
    root: Path,
    iterations: int,
) -> PdfCropRefineBenchmarkObservation | None:
    candidate_pack_path = root / entry.candidate_pack_path
    crop_refine_path = root / entry.crop_refine_path
    artifact_paths = _expand_artifact_globs(entry.crop_artifact_globs, root=root)
    if (
        not candidate_pack_path.is_file()
        or not crop_refine_path.is_file()
        or not artifact_paths
    ):
        return None

    durations: list[float] = []
    candidate_signature = ""
    refine_signature = ""
    artifact_signature = ""
    artifact_count = 0
    decision_count = 0
    estimated_model_call_count = 0
    for _ in range(iterations):
        started = time.perf_counter()
        candidate_payload = json.loads(candidate_pack_path.read_text(encoding="utf-8"))
        crop_refine_payload = json.loads(crop_refine_path.read_text(encoding="utf-8"))
        candidate_signature = candidate_pack_signature(candidate_payload)
        refine_signature = crop_refine_decision_signature(crop_refine_payload)
        artifact_signature = crop_artifact_signature(artifact_paths, root=root)
        artifact_count = len(artifact_paths)
        results = _crop_refine_results(crop_refine_payload)
        decision_count = len(results)
        estimated_model_call_count = _estimated_model_call_count(results)
        durations.append(time.perf_counter() - started)

    return PdfCropRefineBenchmarkObservation(
        report_root=entry.report_root,
        report_name=entry.report_name,
        candidate_pack_signature=candidate_signature,
        crop_refine_signature=refine_signature,
        crop_artifact_signature=artifact_signature,
        crop_artifact_count=artifact_count,
        refine_decision_count=decision_count,
        estimated_model_call_count=estimated_model_call_count,
        durations_seconds=tuple(round(value, 6) for value in durations),
        median_seconds=round(float(statistics.median(durations)), 6),
    )


def run_benchmark(
    *,
    baseline_path: Path,
    iterations: int,
    allow_missing_assets: bool,
    fail_on_runtime_regression: bool,
    output_json: Path | None = None,
) -> tuple[PdfCropRefineBenchmarkComparison, dict[str, Any]]:
    baseline_entries = load_benchmark_baseline(baseline_path)
    observations: list[PdfCropRefineBenchmarkObservation] = []
    skipped_roots: list[str] = []
    for entry in baseline_entries:
        observation = observe_benchmark_entry(
            entry,
            root=ROOT,
            iterations=iterations,
        )
        if observation is None:
            skipped_roots.append(entry.report_root)
            continue
        observations.append(observation)

    comparison = compare_benchmark_observations(
        baseline_entries=baseline_entries,
        observations=observations,
        skipped_report_roots=tuple(skipped_roots),
        allow_missing_assets=allow_missing_assets,
        fail_on_runtime_regression=fail_on_runtime_regression,
    )
    payload = _payload(
        baseline_path=baseline_path,
        iterations=iterations,
        observations=observations,
        skipped_roots=skipped_roots,
        comparison=comparison,
    )
    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(
            json.dumps(payload, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )
    return comparison, payload


def _round_bbox(values: Any) -> list[float]:
    if not isinstance(values, (list, tuple)) or len(values) != 4:
        return []
    return [round(float(value), 3) for value in values]


def _sha256_json(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _relative_key(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _expand_artifact_globs(patterns: Sequence[str], *, root: Path) -> tuple[Path, ...]:
    paths: dict[str, Path] = {}
    for pattern in patterns:
        for matched in glob.glob((root / pattern).as_posix(), recursive=True):
            path = Path(matched)
            if path.is_file():
                paths[path.resolve().as_posix()] = path
    return tuple(paths[key] for key in sorted(paths))


def _crop_refine_results(payload: dict[str, Any]) -> list[dict[str, Any]]:
    results_value = payload.get("results")
    return (
        [row for row in results_value if isinstance(row, dict)]
        if isinstance(results_value, list)
        else []
    )


def _estimated_model_call_count(results: Sequence[dict[str, Any]]) -> int:
    pages: dict[int, bool] = {}
    for row in results:
        try:
            page = int(row.get("page"))
        except (TypeError, ValueError):
            continue
        pages[page] = pages.get(page, False) or bool(row.get("is_valid_candidate"))
    return sum(1 + int(has_valid_result) for has_valid_result in pages.values())


def _missing_row(
    entry: PdfCropRefineBenchmarkBaselineEntry,
) -> PdfCropRefineBenchmarkRow:
    return PdfCropRefineBenchmarkRow(
        report_root=entry.report_root,
        report_name=entry.report_name,
        expected_candidate_pack_signature=entry.expected_candidate_pack_signature,
        actual_candidate_pack_signature=None,
        expected_crop_refine_signature=entry.expected_crop_refine_signature,
        actual_crop_refine_signature=None,
        expected_crop_artifact_signature=entry.expected_crop_artifact_signature,
        actual_crop_artifact_signature=None,
        expected_crop_artifact_count=entry.expected_crop_artifact_count,
        actual_crop_artifact_count=None,
        expected_refine_decision_count=entry.expected_refine_decision_count,
        actual_refine_decision_count=None,
        expected_estimated_model_call_count=entry.expected_estimated_model_call_count,
        actual_estimated_model_call_count=None,
        baseline_median_seconds=entry.baseline_median_seconds,
        actual_median_seconds=None,
        runtime_delta_seconds=None,
        runtime_delta_percent=None,
        status="skipped",
    )


def _payload(
    *,
    baseline_path: Path,
    iterations: int,
    observations: Sequence[PdfCropRefineBenchmarkObservation],
    skipped_roots: Sequence[str],
    comparison: PdfCropRefineBenchmarkComparison,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "baseline_path": baseline_path.as_posix(),
        "iterations": iterations,
        "observations": [asdict(observation) for observation in observations],
        "skipped_report_roots": list(skipped_roots),
        "comparison": {
            "passed": comparison.passed,
            "failures": [asdict(issue) for issue in comparison.failures],
            "warnings": [asdict(issue) for issue in comparison.warnings],
            "rows": [asdict(row) for row in comparison.rows],
        },
    }


def _baseline_payload_from_observations(
    observations: Iterable[PdfCropRefineBenchmarkObservation],
    baseline_entries: Sequence[PdfCropRefineBenchmarkBaselineEntry],
    *,
    runtime_warn_percent: float,
    runtime_fail_percent: float,
) -> dict[str, Any]:
    entries_by_root = {entry.report_root: entry for entry in baseline_entries}
    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "benchmarks": [
            {
                "report_root": observation.report_root,
                "report_name": observation.report_name,
                "candidate_pack_path": entries_by_root[
                    observation.report_root
                ].candidate_pack_path,
                "crop_refine_path": entries_by_root[
                    observation.report_root
                ].crop_refine_path,
                "crop_artifact_globs": list(
                    entries_by_root[observation.report_root].crop_artifact_globs
                ),
                "expected_candidate_pack_signature": observation.candidate_pack_signature,
                "expected_crop_refine_signature": observation.crop_refine_signature,
                "expected_crop_artifact_signature": observation.crop_artifact_signature,
                "expected_crop_artifact_count": observation.crop_artifact_count,
                "expected_refine_decision_count": observation.refine_decision_count,
                "expected_estimated_model_call_count": observation.estimated_model_call_count,
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
            "Compare existing PDF crop artifacts and crop-refine decisions "
            "against committed artifact/cost baselines."
        )
    )
    parser.add_argument(
        "--baseline",
        default="docs/quality/pdf_crop_refine_benchmark_baseline.json",
    )
    parser.add_argument("--output-json", default="")
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--allow-missing-assets", action="store_true")
    parser.add_argument("--fail-on-runtime-regression", action="store_true")
    parser.add_argument("--write-current-baseline", default="")
    parser.add_argument("--runtime-warn-percent", type=float, default=50.0)
    parser.add_argument("--runtime-fail-percent", type=float, default=150.0)
    args = parser.parse_args(argv)

    baseline_path = (ROOT / args.baseline).resolve()
    output_json = (ROOT / args.output_json).resolve() if args.output_json else None
    baseline_entries = load_benchmark_baseline(baseline_path)
    comparison, payload = run_benchmark(
        baseline_path=baseline_path,
        iterations=max(1, int(args.iterations)),
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
                        PdfCropRefineBenchmarkObservation(**observation)
                        for observation in payload["observations"]
                    ),
                    baseline_entries,
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
