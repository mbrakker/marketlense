from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class PdfBenchmarkScorecardIssue:
    gate: str
    key: str
    reason: str
    detail: str


@dataclass(frozen=True)
class PdfBenchmarkScorecardRow:
    gate: str
    key: str
    report_name: str
    metric_name: str | None
    status: str
    runtime_seconds: float | None
    runtime_delta_percent: float | None
    candidate_count: int | None
    degraded_page_count: int | None
    crop_artifact_count: int | None
    refine_decision_count: int | None
    estimated_model_call_count: int | None
    estimated_model_call_delta: int | None
    trend_delta_percent: float | None
    trend_sample_count: int | None


@dataclass(frozen=True)
class PdfBenchmarkScorecard:
    schema_version: str
    evidence_complete: bool
    passed: bool
    source_files: tuple[str, ...]
    candidate_row_count: int
    crop_refine_row_count: int
    trend_row_count: int
    rows: tuple[PdfBenchmarkScorecardRow, ...]
    failures: tuple[PdfBenchmarkScorecardIssue, ...]
    warnings: tuple[PdfBenchmarkScorecardIssue, ...]


@dataclass(frozen=True)
class RunHealthScorecard:
    schema_version: str
    run_id: str
    event_count: int
    error_count: int
    retry_count: int
    validation_failure_count: int
    cost_usd: float
    latency_seconds: float | None
    warnings: tuple[str, ...]
    pdf_benchmark_scorecard: PdfBenchmarkScorecard | None = None


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _event_payloads(lines: Iterable[str]) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for line in lines:
        text = line.strip()
        if not text:
            continue
        start = text.find("{")
        if start < 0:
            continue
        try:
            payload = json.loads(text[start:])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            payloads.append(payload)
    return payloads


def build_scorecard(
    payloads: Iterable[dict[str, Any]],
    *,
    run_id: str | None = None,
    max_errors: int = 0,
    max_retries: int = 3,
    max_cost_usd: float | None = None,
    pdf_candidate_payloads: Iterable[dict[str, Any]] | None = None,
    pdf_crop_refine_payloads: Iterable[dict[str, Any]] | None = None,
    pdf_trend_payloads: Iterable[dict[str, Any]] | None = None,
    pdf_benchmark_source_files: Iterable[str] = (),
    missing_pdf_benchmark_sources: Iterable[str] = (),
    require_pdf_benchmark_evidence: bool = False,
) -> RunHealthScorecard:
    events = list(payloads)
    selected_run_id = str(run_id or (events[0].get("run_id") if events else "") or "")
    if selected_run_id:
        events = [
            event
            for event in events
            if str(event.get("run_id") or "") == selected_run_id
        ]

    timestamps = [
        parsed
        for parsed in (_parse_timestamp(event.get("timestamp")) for event in events)
        if parsed is not None
    ]
    fields = [
        event.get("fields") if isinstance(event.get("fields"), dict) else {}
        for event in events
    ]
    error_count = sum(
        1
        for event in events
        if str(event.get("level") or "").lower() in {"error", "critical"}
        or "error" in str(event.get("event") or "").lower()
        or str((event.get("fields") or {}).get("severity") or "").lower() == "error"
    )
    retry_count = sum(
        1 for event in events if "retry" in str(event.get("event") or "").lower()
    )
    validation_failure_count = sum(
        1
        for event in events
        if "validation" in str(event.get("event") or "").lower()
        and any(
            token in str(event.get("event") or "").lower()
            for token in ("fail", "error")
        )
    )
    cost_usd = sum(float(item.get("cost_usd") or 0.0) for item in fields)
    latency_seconds = None
    if len(timestamps) >= 2:
        latency_seconds = (max(timestamps) - min(timestamps)).total_seconds()

    warnings: list[str] = []
    if error_count > max_errors:
        warnings.append(f"error_count {error_count} exceeds {max_errors}")
    if retry_count > max_retries:
        warnings.append(f"retry_count {retry_count} exceeds {max_retries}")
    if max_cost_usd is not None and cost_usd > max_cost_usd:
        warnings.append(f"cost_usd {cost_usd:.6f} exceeds {max_cost_usd:.6f}")

    missing_pdf_sources = tuple(missing_pdf_benchmark_sources)
    pdf_payload_inputs = (
        tuple(pdf_candidate_payloads or ()),
        tuple(pdf_crop_refine_payloads or ()),
        tuple(pdf_trend_payloads or ()),
    )
    include_pdf_scorecard = (
        require_pdf_benchmark_evidence
        or any(pdf_payload_inputs)
        or bool(tuple(pdf_benchmark_source_files))
        or bool(missing_pdf_sources)
    )
    pdf_benchmark_scorecard = None
    if include_pdf_scorecard:
        pdf_benchmark_scorecard = build_pdf_benchmark_scorecard(
            candidate_payloads=pdf_payload_inputs[0],
            crop_refine_payloads=pdf_payload_inputs[1],
            trend_payloads=pdf_payload_inputs[2],
            source_files=tuple(pdf_benchmark_source_files),
            missing_sources=missing_pdf_sources,
        )
        if not pdf_benchmark_scorecard.evidence_complete:
            detail = "; ".join(
                issue.detail for issue in pdf_benchmark_scorecard.failures
            )
            warnings.append(f"pdf_benchmark_evidence incomplete: {detail}")
        elif not pdf_benchmark_scorecard.passed:
            detail = "; ".join(
                issue.detail for issue in pdf_benchmark_scorecard.failures
            )
            warnings.append(f"pdf_benchmark_evidence failed: {detail}")
        elif pdf_benchmark_scorecard.warnings:
            detail = "; ".join(
                issue.detail for issue in pdf_benchmark_scorecard.warnings
            )
            warnings.append(f"pdf_benchmark_evidence warnings: {detail}")

    return RunHealthScorecard(
        schema_version="1.0",
        run_id=selected_run_id,
        event_count=len(events),
        error_count=error_count,
        retry_count=retry_count,
        validation_failure_count=validation_failure_count,
        cost_usd=round(cost_usd, 6),
        latency_seconds=latency_seconds,
        warnings=tuple(warnings),
        pdf_benchmark_scorecard=pdf_benchmark_scorecard,
    )


def build_pdf_benchmark_scorecard(
    *,
    candidate_payloads: Iterable[dict[str, Any]],
    crop_refine_payloads: Iterable[dict[str, Any]],
    trend_payloads: Iterable[dict[str, Any]],
    source_files: Iterable[str] = (),
    missing_sources: Iterable[str] = (),
) -> PdfBenchmarkScorecard:
    candidate_payload_list = tuple(candidate_payloads)
    crop_payload_list = tuple(crop_refine_payloads)
    trend_payload_list = tuple(trend_payloads)
    candidate_rows = _benchmark_rows(candidate_payload_list)
    crop_rows = _benchmark_rows(crop_payload_list)
    trend_rows = _benchmark_rows(trend_payload_list)

    rows: list[PdfBenchmarkScorecardRow] = []
    for row in candidate_rows:
        key = str(row.get("pdf_path") or row.get("report_name") or "").strip()
        rows.append(
            PdfBenchmarkScorecardRow(
                gate="candidate",
                key=key,
                report_name=str(row.get("report_name") or key),
                metric_name=None,
                status=str(row.get("status") or "unknown"),
                runtime_seconds=_float_or_none(row.get("actual_median_seconds")),
                runtime_delta_percent=_float_or_none(row.get("runtime_delta_percent")),
                candidate_count=_int_or_none(row.get("actual_candidate_count")),
                degraded_page_count=_int_or_none(row.get("actual_degraded_page_count")),
                crop_artifact_count=None,
                refine_decision_count=None,
                estimated_model_call_count=None,
                estimated_model_call_delta=None,
                trend_delta_percent=None,
                trend_sample_count=None,
            )
        )
    for row in crop_rows:
        key = str(row.get("report_root") or row.get("report_name") or "").strip()
        actual_calls = _int_or_none(row.get("actual_estimated_model_call_count"))
        expected_calls = _int_or_none(row.get("expected_estimated_model_call_count"))
        rows.append(
            PdfBenchmarkScorecardRow(
                gate="crop_refine",
                key=key,
                report_name=str(row.get("report_name") or key),
                metric_name=None,
                status=str(row.get("status") or "unknown"),
                runtime_seconds=_float_or_none(row.get("actual_median_seconds")),
                runtime_delta_percent=_float_or_none(row.get("runtime_delta_percent")),
                candidate_count=None,
                degraded_page_count=None,
                crop_artifact_count=_int_or_none(row.get("actual_crop_artifact_count")),
                refine_decision_count=_int_or_none(
                    row.get("actual_refine_decision_count")
                ),
                estimated_model_call_count=actual_calls,
                estimated_model_call_delta=(
                    actual_calls - expected_calls
                    if actual_calls is not None and expected_calls is not None
                    else None
                ),
                trend_delta_percent=None,
                trend_sample_count=None,
            )
        )
    for row in trend_rows:
        key = str(row.get("key") or row.get("report_name") or "").strip()
        rows.append(
            PdfBenchmarkScorecardRow(
                gate=str(row.get("gate") or "trend"),
                key=key,
                report_name=str(row.get("report_name") or key),
                metric_name=str(row.get("metric_name") or ""),
                status=str(row.get("status") or "unknown"),
                runtime_seconds=None,
                runtime_delta_percent=None,
                candidate_count=None,
                degraded_page_count=None,
                crop_artifact_count=None,
                refine_decision_count=None,
                estimated_model_call_count=None,
                estimated_model_call_delta=None,
                trend_delta_percent=_float_or_none(row.get("delta_percent")),
                trend_sample_count=_int_or_none(row.get("sample_count")),
            )
        )

    failures: list[PdfBenchmarkScorecardIssue] = []
    warnings: list[PdfBenchmarkScorecardIssue] = []
    for gate, payloads in (
        ("candidate", candidate_payload_list),
        ("crop_refine", crop_payload_list),
        ("trend", trend_payload_list),
    ):
        failures.extend(_benchmark_issues(gate, payloads, issue_type="failures"))
        warnings.extend(_benchmark_issues(gate, payloads, issue_type="warnings"))
        failures.extend(_comparison_passed_issues(gate, payloads))
    for row in rows:
        status = row.status.lower()
        if status in {"failed", "failure"}:
            failures.append(
                PdfBenchmarkScorecardIssue(
                    gate=row.gate,
                    key=row.key,
                    reason="benchmark_row_failed",
                    detail=f"{row.gate} benchmark row failed for {row.report_name}",
                )
            )
        elif status in {"warned", "warning"}:
            warnings.append(
                PdfBenchmarkScorecardIssue(
                    gate=row.gate,
                    key=row.key,
                    reason="benchmark_row_warning",
                    detail=f"{row.gate} benchmark row warned for {row.report_name}",
                )
            )
    for gate, count in (
        ("candidate", len(candidate_rows)),
        ("crop_refine", len(crop_rows)),
        ("trend", len(trend_rows)),
    ):
        if count == 0:
            failures.append(
                PdfBenchmarkScorecardIssue(
                    gate=gate,
                    key="",
                    reason="missing_benchmark_evidence",
                    detail=f"missing {gate} benchmark evidence",
                )
            )
    for source in missing_sources:
        failures.append(
            PdfBenchmarkScorecardIssue(
                gate="pdf_benchmark",
                key=str(source),
                reason="missing_benchmark_source",
                detail=f"missing benchmark source {source}",
            )
        )

    evidence_complete = (
        len(candidate_rows) > 0
        and len(crop_rows) > 0
        and len(trend_rows) > 0
        and not tuple(missing_sources)
    )
    return PdfBenchmarkScorecard(
        schema_version="1.0",
        evidence_complete=evidence_complete,
        passed=evidence_complete and not failures,
        source_files=tuple(source_files),
        candidate_row_count=len(candidate_rows),
        crop_refine_row_count=len(crop_rows),
        trend_row_count=len(trend_rows),
        rows=tuple(rows),
        failures=tuple(failures),
        warnings=tuple(warnings),
    )


def _benchmark_rows(payloads: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for payload in payloads:
        comparison = payload.get("comparison")
        comparison_rows = (
            comparison.get("rows") if isinstance(comparison, dict) else None
        )
        if isinstance(comparison_rows, list):
            rows.extend(row for row in comparison_rows if isinstance(row, dict))
    return rows


def _benchmark_issues(
    gate: str,
    payloads: Iterable[dict[str, Any]],
    *,
    issue_type: str,
) -> tuple[PdfBenchmarkScorecardIssue, ...]:
    issues: list[PdfBenchmarkScorecardIssue] = []
    for payload in payloads:
        comparison = payload.get("comparison")
        if not isinstance(comparison, dict):
            continue
        source_issues = comparison.get(issue_type)
        if not isinstance(source_issues, list):
            continue
        for item in source_issues:
            if not isinstance(item, dict):
                continue
            issues.append(
                PdfBenchmarkScorecardIssue(
                    gate=str(item.get("gate") or gate),
                    key=str(
                        item.get("key")
                        or item.get("pdf_path")
                        or item.get("report_root")
                        or ""
                    ),
                    reason=str(item.get("reason") or issue_type),
                    detail=str(item.get("detail") or item.get("reason") or issue_type),
                )
            )
    return tuple(issues)


def _comparison_passed_issues(
    gate: str,
    payloads: Iterable[dict[str, Any]],
) -> tuple[PdfBenchmarkScorecardIssue, ...]:
    issues: list[PdfBenchmarkScorecardIssue] = []
    for payload in payloads:
        comparison = payload.get("comparison")
        if not isinstance(comparison, dict):
            continue
        if comparison.get("passed") is False:
            issues.append(
                PdfBenchmarkScorecardIssue(
                    gate=gate,
                    key="",
                    reason="benchmark_comparison_failed",
                    detail=f"{gate} benchmark comparison failed",
                )
            )
    return tuple(issues)


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


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a run health scorecard from JSON logs."
    )
    parser.add_argument("log_path", help="Log file containing structured JSON events.")
    parser.add_argument("--run-id", default=None, help="Optional run_id to filter.")
    parser.add_argument("--max-errors", type=int, default=0)
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--max-cost-usd", type=float, default=None)
    parser.add_argument("--pdf-candidate-json", action="append", default=[])
    parser.add_argument("--pdf-crop-refine-json", action="append", default=[])
    parser.add_argument("--pdf-trend-json", action="append", default=[])
    parser.add_argument("--require-pdf-benchmark-evidence", action="store_true")
    parser.add_argument("--output-json", default="")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    path = Path(args.log_path)
    payloads = _event_payloads(path.read_text(encoding="utf-8").splitlines())
    candidate_payloads, candidate_sources, missing_candidate = _load_json_payloads(
        args.pdf_candidate_json
    )
    crop_payloads, crop_sources, missing_crop = _load_json_payloads(
        args.pdf_crop_refine_json
    )
    trend_payloads, trend_sources, missing_trend = _load_json_payloads(
        args.pdf_trend_json
    )
    scorecard = build_scorecard(
        payloads,
        run_id=args.run_id,
        max_errors=args.max_errors,
        max_retries=args.max_retries,
        max_cost_usd=args.max_cost_usd,
        pdf_candidate_payloads=candidate_payloads,
        pdf_crop_refine_payloads=crop_payloads,
        pdf_trend_payloads=trend_payloads,
        pdf_benchmark_source_files=(*candidate_sources, *crop_sources, *trend_sources),
        missing_pdf_benchmark_sources=(
            *missing_candidate,
            *missing_crop,
            *missing_trend,
        ),
        require_pdf_benchmark_evidence=args.require_pdf_benchmark_evidence,
    )
    encoded = json.dumps(asdict(scorecard), ensure_ascii=True, indent=2, sort_keys=True)
    if args.output_json:
        output_path = Path(args.output_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(encoded, encoding="utf-8")
    print(encoded)
    return 1 if scorecard.warnings else 0


def _load_json_payloads(
    paths: Iterable[str],
) -> tuple[
    tuple[dict[str, Any], ...],
    tuple[str, ...],
    tuple[str, ...],
]:
    payloads: list[dict[str, Any]] = []
    sources: list[str] = []
    missing: list[str] = []
    for raw_path in paths:
        path = Path(raw_path)
        if not path.is_file():
            missing.append(raw_path)
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"PDF benchmark JSON input must be an object: {raw_path}")
        payloads.append(payload)
        sources.append(raw_path)
    return tuple(payloads), tuple(sources), tuple(missing)


if __name__ == "__main__":
    raise SystemExit(main())
