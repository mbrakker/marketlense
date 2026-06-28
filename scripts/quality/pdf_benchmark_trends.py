from __future__ import annotations

import argparse
import json
import statistics
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@dataclass(frozen=True)
class PdfBenchmarkTrendMetric:
    gate: str
    key: str
    report_name: str
    runtime_seconds: float | None
    candidate_count: int | None = None
    degraded_page_count: int | None = None
    crop_artifact_count: int | None = None
    refine_decision_count: int | None = None
    estimated_model_call_count: int | None = None


@dataclass(frozen=True)
class PdfBenchmarkTrendRun:
    run_id: str
    generated_at: str
    source_files: tuple[str, ...]
    metrics: tuple[PdfBenchmarkTrendMetric, ...]


@dataclass(frozen=True)
class PdfBenchmarkTrendIssue:
    gate: str
    key: str
    reason: str
    detail: str


@dataclass(frozen=True)
class PdfBenchmarkTrendRow:
    gate: str
    key: str
    report_name: str
    metric_name: str
    baseline_median: float | None
    recent_median: float | None
    delta_percent: float | None
    sample_count: int
    status: str


@dataclass(frozen=True)
class PdfBenchmarkTrendComparison:
    passed: bool
    failures: tuple[PdfBenchmarkTrendIssue, ...]
    warnings: tuple[PdfBenchmarkTrendIssue, ...]
    rows: tuple[PdfBenchmarkTrendRow, ...]


def extract_trend_run(
    *,
    run_id: str,
    candidate_payloads: Sequence[dict[str, Any]],
    crop_refine_payloads: Sequence[dict[str, Any]],
    source_files: Sequence[str],
) -> PdfBenchmarkTrendRun:
    metrics: list[PdfBenchmarkTrendMetric] = []
    generated_candidates = [
        str(payload.get("generated_at") or "")
        for payload in (*candidate_payloads, *crop_refine_payloads)
        if isinstance(payload, dict) and payload.get("generated_at")
    ]
    generated_at = generated_candidates[0] if generated_candidates else _now()
    for payload in candidate_payloads:
        for row in _comparison_rows(payload):
            runtime = _float_or_none(row.get("actual_median_seconds"))
            candidate_count = _int_or_none(row.get("actual_candidate_count"))
            degraded_count = _int_or_none(row.get("actual_degraded_page_count"))
            if runtime is None and candidate_count is None and degraded_count is None:
                continue
            key = str(row.get("pdf_path") or row.get("report_name") or "").strip()
            if not key:
                continue
            metrics.append(
                PdfBenchmarkTrendMetric(
                    gate="candidate",
                    key=key,
                    report_name=str(row.get("report_name") or key),
                    runtime_seconds=runtime,
                    candidate_count=candidate_count,
                    degraded_page_count=degraded_count,
                )
            )
    for payload in crop_refine_payloads:
        for row in _comparison_rows(payload):
            runtime = _float_or_none(row.get("actual_median_seconds"))
            artifact_count = _int_or_none(row.get("actual_crop_artifact_count"))
            refine_count = _int_or_none(row.get("actual_refine_decision_count"))
            call_count = _int_or_none(row.get("actual_estimated_model_call_count"))
            if (
                runtime is None
                and artifact_count is None
                and refine_count is None
                and call_count is None
            ):
                continue
            key = str(row.get("report_root") or row.get("report_name") or "").strip()
            if not key:
                continue
            metrics.append(
                PdfBenchmarkTrendMetric(
                    gate="crop_refine",
                    key=key,
                    report_name=str(row.get("report_name") or key),
                    runtime_seconds=runtime,
                    crop_artifact_count=artifact_count,
                    refine_decision_count=refine_count,
                    estimated_model_call_count=call_count,
                )
            )
    metrics.sort(key=lambda item: (item.gate, item.key))
    return PdfBenchmarkTrendRun(
        run_id=run_id,
        generated_at=generated_at,
        source_files=tuple(source_files),
        metrics=tuple(metrics),
    )


def append_trend_run(
    history: dict[str, Any],
    run: PdfBenchmarkTrendRun,
    *,
    retained_run_limit: int,
) -> dict[str, Any]:
    runs_value = history.get("runs") if isinstance(history, dict) else None
    runs = list(runs_value) if isinstance(runs_value, list) else []
    runs.append(asdict(run))
    retained = max(1, int(retained_run_limit))
    runs = runs[-retained:]
    return {
        "schema_version": "1.0",
        "generated_at": _now(),
        "retained_run_limit": retained,
        "runs": runs,
    }


def compare_trend_history(
    history: dict[str, Any],
    *,
    min_runs: int,
    trend_warn_percent: float,
    trend_fail_percent: float,
    fail_on_trend_regression: bool = False,
) -> PdfBenchmarkTrendComparison:
    runs = _history_runs(history)
    grouped = _group_metric_values(runs)
    rows: list[PdfBenchmarkTrendRow] = []
    warnings: list[PdfBenchmarkTrendIssue] = []
    failures: list[PdfBenchmarkTrendIssue] = []
    recent_size = max(1, int(min_runs))
    for (gate, key, metric_name), samples in sorted(grouped.items()):
        if len(samples) <= recent_size:
            rows.append(_insufficient_row(gate, key, metric_name, samples))
            continue
        baseline_values = [sample["value"] for sample in samples[:-recent_size]]
        recent_values = [sample["value"] for sample in samples[-recent_size:]]
        baseline_median = float(statistics.median(baseline_values))
        recent_median = float(statistics.median(recent_values))
        delta_percent = (
            ((recent_median - baseline_median) / baseline_median) * 100.0
            if baseline_median > 0.0
            else 0.0
        )
        status = "passed"
        reason_metric = _reason_metric_name(metric_name)
        if delta_percent >= trend_fail_percent:
            if fail_on_trend_regression:
                issue = PdfBenchmarkTrendIssue(
                    gate=gate,
                    key=key,
                    reason=f"{reason_metric}_trend_regression_failure",
                    detail=(
                        f"recent {metric_name} median increased {delta_percent:.1f}% "
                        f"({baseline_median:.3f} -> {recent_median:.3f})"
                    ),
                )
                failures.append(issue)
                status = "failed"
            else:
                issue = PdfBenchmarkTrendIssue(
                    gate=gate,
                    key=key,
                    reason=f"{reason_metric}_trend_regression_warning",
                    detail=(
                        f"recent {metric_name} median increased {delta_percent:.1f}% "
                        f"({baseline_median:.3f} -> {recent_median:.3f})"
                    ),
                )
                warnings.append(issue)
                status = "warned"
        elif delta_percent >= trend_warn_percent:
            warnings.append(
                PdfBenchmarkTrendIssue(
                    gate=gate,
                    key=key,
                    reason=f"{reason_metric}_trend_regression_warning",
                    detail=(
                        f"recent {metric_name} median increased {delta_percent:.1f}% "
                        f"({baseline_median:.3f} -> {recent_median:.3f})"
                    ),
                )
            )
            status = "warned"
        rows.append(
            PdfBenchmarkTrendRow(
                gate=gate,
                key=key,
                report_name=str(samples[-1]["report_name"]),
                metric_name=metric_name,
                baseline_median=round(baseline_median, 6),
                recent_median=round(recent_median, 6),
                delta_percent=round(delta_percent, 6),
                sample_count=len(samples),
                status=status,
            )
        )
    return PdfBenchmarkTrendComparison(
        passed=not failures,
        failures=tuple(failures),
        warnings=tuple(warnings),
        rows=tuple(rows),
    )


def run_trend_check(
    *,
    candidate_json_paths: Sequence[Path],
    crop_refine_json_paths: Sequence[Path],
    history_path: Path,
    output_json: Path | None,
    run_id: str,
    retained_run_limit: int,
    min_runs: int,
    trend_warn_percent: float,
    trend_fail_percent: float,
    update_history: bool,
    allow_missing_inputs: bool,
    fail_on_trend_regression: bool,
) -> tuple[PdfBenchmarkTrendComparison, dict[str, Any]]:
    if (
        not candidate_json_paths
        and not crop_refine_json_paths
        and not allow_missing_inputs
    ):
        raise ValueError("At least one benchmark JSON input path is required.")
    candidate_payloads, candidate_sources = _load_payloads(
        candidate_json_paths,
        allow_missing_inputs=allow_missing_inputs,
    )
    crop_payloads, crop_sources = _load_payloads(
        crop_refine_json_paths,
        allow_missing_inputs=allow_missing_inputs,
    )
    history = _load_history(history_path)
    current_run = extract_trend_run(
        run_id=run_id,
        candidate_payloads=candidate_payloads,
        crop_refine_payloads=crop_payloads,
        source_files=(*candidate_sources, *crop_sources),
    )
    updated_history = append_trend_run(
        history,
        current_run,
        retained_run_limit=retained_run_limit,
    )
    comparison = compare_trend_history(
        updated_history,
        min_runs=min_runs,
        trend_warn_percent=trend_warn_percent,
        trend_fail_percent=trend_fail_percent,
        fail_on_trend_regression=fail_on_trend_regression,
    )
    payload = _payload(
        history_path=history_path,
        current_run=current_run,
        history=updated_history,
        comparison=comparison,
        retained_run_limit=retained_run_limit,
        min_runs=min_runs,
        trend_warn_percent=trend_warn_percent,
        trend_fail_percent=trend_fail_percent,
    )
    if update_history:
        history_path.parent.mkdir(parents=True, exist_ok=True)
        history_path.write_text(
            json.dumps(updated_history, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )
    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(
            json.dumps(payload, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )
    return comparison, payload


def _comparison_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    comparison = payload.get("comparison")
    rows_value = comparison.get("rows") if isinstance(comparison, dict) else None
    return (
        [row for row in rows_value if isinstance(row, dict)]
        if isinstance(rows_value, list)
        else []
    )


def _load_payloads(
    paths: Sequence[Path],
    *,
    allow_missing_inputs: bool,
) -> tuple[tuple[dict[str, Any], ...], tuple[str, ...]]:
    payloads: list[dict[str, Any]] = []
    sources: list[str] = []
    for path in paths:
        if not path.is_file():
            if allow_missing_inputs:
                continue
            raise FileNotFoundError(f"Benchmark JSON input not found: {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"Benchmark JSON input must be an object: {path}")
        payloads.append(payload)
        sources.append(_rel(path))
    return tuple(payloads), tuple(sources)


def _load_history(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"schema_version": "1.0", "runs": []}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Trend history must be a JSON object: {path}")
    return payload


def _history_runs(history: dict[str, Any]) -> list[dict[str, Any]]:
    runs_value = history.get("runs") if isinstance(history, dict) else None
    return (
        [run for run in runs_value if isinstance(run, dict)]
        if isinstance(runs_value, list)
        else []
    )


def _group_metric_values(
    runs: Sequence[dict[str, Any]],
) -> dict[tuple[str, str, str], list[dict[str, Any]]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for run in runs:
        metrics_value = run.get("metrics")
        metrics = metrics_value if isinstance(metrics_value, (list, tuple)) else []
        for metric in metrics:
            if not isinstance(metric, dict):
                continue
            gate = str(metric.get("gate") or "")
            key = str(metric.get("key") or "")
            report_name = str(metric.get("report_name") or key)
            for metric_name in ("runtime_seconds", "estimated_model_call_count"):
                if (
                    gate != "crop_refine"
                    and metric_name == "estimated_model_call_count"
                ):
                    continue
                value = _float_or_none(metric.get(metric_name))
                if value is None:
                    continue
                grouped.setdefault((gate, key, metric_name), []).append(
                    {"value": value, "report_name": report_name}
                )
    return grouped


def _insufficient_row(
    gate: str,
    key: str,
    metric_name: str,
    samples: Sequence[dict[str, Any]],
) -> PdfBenchmarkTrendRow:
    report_name = str(samples[-1]["report_name"]) if samples else key
    return PdfBenchmarkTrendRow(
        gate=gate,
        key=key,
        report_name=report_name,
        metric_name=metric_name,
        baseline_median=None,
        recent_median=None,
        delta_percent=None,
        sample_count=len(samples),
        status="insufficient_history",
    )


def _reason_metric_name(metric_name: str) -> str:
    if metric_name == "runtime_seconds":
        return "runtime"
    if metric_name == "estimated_model_call_count":
        return "estimated_model_call"
    return metric_name


def _payload(
    *,
    history_path: Path,
    current_run: PdfBenchmarkTrendRun,
    history: dict[str, Any],
    comparison: PdfBenchmarkTrendComparison,
    retained_run_limit: int,
    min_runs: int,
    trend_warn_percent: float,
    trend_fail_percent: float,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "generated_at": _now(),
        "history_path": _rel(history_path),
        "retained_run_limit": retained_run_limit,
        "min_runs": min_runs,
        "trend_warn_percent": trend_warn_percent,
        "trend_fail_percent": trend_fail_percent,
        "current_run": asdict(current_run),
        "history_run_count": len(_history_runs(history)),
        "comparison": {
            "passed": comparison.passed,
            "failures": [asdict(issue) for issue in comparison.failures],
            "warnings": [asdict(issue) for issue in comparison.warnings],
            "rows": [asdict(row) for row in comparison.rows],
        },
    }


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _now() -> str:
    return datetime.now(UTC).isoformat()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Record and compare trend history from PDF candidate and crop-refine "
            "benchmark JSON outputs without rerunning PDF extraction."
        )
    )
    parser.add_argument("--candidate-json", action="append", default=[])
    parser.add_argument("--crop-refine-json", action="append", default=[])
    parser.add_argument(
        "--history-json",
        default="out/pdf_benchmark_trend_history.json",
    )
    parser.add_argument("--output-json", default="")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--update-history", action="store_true")
    parser.add_argument("--allow-missing-inputs", action="store_true")
    parser.add_argument("--fail-on-trend-regression", action="store_true")
    parser.add_argument("--retained-run-limit", type=int, default=20)
    parser.add_argument("--min-runs", type=int, default=3)
    parser.add_argument("--trend-warn-percent", type=float, default=10.0)
    parser.add_argument("--trend-fail-percent", type=float, default=25.0)
    args = parser.parse_args(argv)

    run_id = args.run_id or f"pdf-benchmark-trend:{_now()}"
    candidate_paths = tuple((ROOT / path).resolve() for path in args.candidate_json)
    crop_paths = tuple((ROOT / path).resolve() for path in args.crop_refine_json)
    history_path = (ROOT / args.history_json).resolve()
    output_json = (ROOT / args.output_json).resolve() if args.output_json else None
    comparison, payload = run_trend_check(
        candidate_json_paths=candidate_paths,
        crop_refine_json_paths=crop_paths,
        history_path=history_path,
        output_json=output_json,
        run_id=run_id,
        retained_run_limit=max(1, int(args.retained_run_limit)),
        min_runs=max(1, int(args.min_runs)),
        trend_warn_percent=float(args.trend_warn_percent),
        trend_fail_percent=float(args.trend_fail_percent),
        update_history=bool(args.update_history),
        allow_missing_inputs=bool(args.allow_missing_inputs),
        fail_on_trend_regression=bool(args.fail_on_trend_regression),
    )
    print(json.dumps(payload["comparison"], ensure_ascii=True, indent=2))
    return 0 if comparison.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
