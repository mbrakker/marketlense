"""Aggregate per-call provider latency from the canonical LLM usage ledger."""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
from collections import defaultdict
from pathlib import Path
from statistics import median
from typing import Any


def _number(value: Any) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    return parsed if math.isfinite(parsed) and parsed > 0 else 0.0


def _optional_nonnegative(value: Any) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return (
        round(parsed, 3)
        if math.isfinite(parsed) and 0 <= parsed <= 2**53 - 1
        else None
    )


def _interval_summary(
    members: list[dict[str, Any]],
    *,
    exposure_members: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    events: dict[float, list[int]] = defaultdict(lambda: [0, 0])
    interval_count = 0
    member_ids = {id(call) for call in members}
    all_calls = exposure_members if exposure_members is not None else members
    for call in all_calls:
        started = call.get("provider_request_start_monotonic_ms")
        finished = call.get("provider_request_finish_monotonic_ms")
        if started is None or finished is None or finished < started:
            continue
        selected = id(call) in member_ids
        events[started][0] += int(selected)
        events[started][1] += 1
        events[finished][0] -= int(selected)
        events[finished][1] -= 1
        interval_count += int(selected)

    active = 0
    report_active = 0
    maximum = 0
    union_ms = 0.0
    exclusive_ms = 0.0
    previous: float | None = None
    for timestamp, deltas in sorted(events.items()):
        if previous is not None:
            exposed_ms = timestamp - previous
            if active > 0:
                union_ms += exposed_ms
            if active > 0 and report_active == 1:
                exclusive_ms += exposed_ms
        active += deltas[0]
        report_active += deltas[1]
        maximum = max(maximum, active)
        previous = timestamp
    return {
        "interval_timed_call_count": interval_count,
        "provider_active_wall_ms": round(union_ms, 3),
        "exclusive_exposed_wall_time_ms": round(exclusive_ms, 3),
        "max_simultaneous_calls": maximum,
    }


def _group_summary(
    members: list[dict[str, Any]],
    *,
    exposure_members: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    elapsed_values = [
        call["provider_elapsed_ms"]
        for call in members
        if call["provider_elapsed_ms"] is not None
    ]
    return {
        **_interval_summary(members, exposure_members=exposure_members),
        "call_count": len(members),
        "timed_call_count": len(elapsed_values),
        "untimed_call_count": len(members) - len(elapsed_values),
        "provider_elapsed_ms_total": round(sum(elapsed_values), 3),
        "provider_elapsed_ms_max": (
            round(max(elapsed_values), 3) if elapsed_values else None
        ),
        "provider_elapsed_ms_median": (
            round(median(elapsed_values), 3) if elapsed_values else None
        ),
        "limiter_wait_ms_total": round(
            sum(call["limiter_wait_ms"] for call in members), 3
        ),
        "in_flight_wait_ms_total": round(
            sum(call["in_flight_wait_ms"] for call in members), 3
        ),
        "rate_spacing_wait_ms_total": round(
            sum(call["rate_spacing_wait_ms"] for call in members), 3
        ),
        "input_tokens": sum(call["input_tokens"] for call in members),
        "cached_input_tokens": sum(
            call["cached_input_tokens"] or 0 for call in members
        ),
        "cached_input_token_reported_call_count": sum(
            call["cached_input_tokens"] is not None for call in members
        ),
        "output_tokens": sum(call["output_tokens"] for call in members),
        "total_tokens": sum(call["total_tokens"] for call in members),
        "reasoning_tokens": sum(call["reasoning_tokens"] or 0 for call in members),
        "reasoning_token_reported_call_count": sum(
            call["reasoning_tokens"] is not None for call in members
        ),
        "tool_calls": sum(call["tool_calls"] for call in members),
        "file_search_call_count": sum(
            call["file_search_call_count"] for call in members
        ),
        "estimated_cost_usd": round(
            sum(call["estimated_cost_usd"] for call in members), 6
        ),
        "workflows": sorted({call["workflow"] for call in members if call["workflow"]}),
        "artifact_families": sorted(
            {call["artifact_family"] for call in members if call["artifact_family"]}
        ),
        "prompt_namespaces": sorted({call["prompt_namespace"] for call in members}),
        "stages": sorted({call["stage"] for call in members}),
        "reasoning_efforts": sorted({call["reasoning_effort"] for call in members}),
    }


def aggregate_report_provider_calls(
    *,
    usage_db: Path,
    report_id: str,
    top_n: int = 10,
    workflow_db: Path | None = None,
    run_result_json: Path | None = None,
) -> dict[str, Any]:
    """Return deterministic latency groups and slow calls for one report."""

    database_uri = f"{usage_db.resolve().as_uri()}?mode=ro"
    with sqlite3.connect(database_uri, uri=True) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT rowid AS ledger_rowid, * FROM llm_usage_events "
            "WHERE report_id = ? ORDER BY rowid",
            (report_id,),
        ).fetchall()

    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    groups_by_namespace: dict[str, list[dict[str, Any]]] = defaultdict(list)
    groups_by_stage: dict[str, list[dict[str, Any]]] = defaultdict(list)
    groups_by_effort: dict[str, list[dict[str, Any]]] = defaultdict(list)
    calls: list[dict[str, Any]] = []
    token_totals = {
        "input_tokens": 0,
        "cached_input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "reasoning_tokens": 0,
    }
    reasoning_reported_call_count = 0
    cached_input_reported_call_count = 0
    status_counts: dict[str, int] = defaultdict(int)
    total_elapsed_ms = 0.0
    total_limiter_wait_ms = 0.0
    total_rate_spacing_wait_ms = 0.0
    total_in_flight_wait_ms = 0.0
    timed_call_count = 0

    for row in rows:
        record = dict(row)
        metadata = json.loads(str(record.get("metadata_json") or "{}"))
        if not isinstance(metadata, dict):
            metadata = {}
        elapsed_ms = _optional_nonnegative(metadata.get("provider_elapsed_ms"))
        interval_start_ms = _optional_nonnegative(
            metadata.get("provider_request_start_monotonic_ms")
        )
        interval_finish_ms = _optional_nonnegative(
            metadata.get("provider_request_finish_monotonic_ms")
        )
        if (
            interval_start_ms is None
            or interval_finish_ms is None
            or interval_finish_ms < interval_start_ms
        ):
            interval_start_ms = None
            interval_finish_ms = None
        limiter_wait_ms = _number(metadata.get("limiter_wait_ms"))
        in_flight_wait_ms = _number(metadata.get("in_flight_wait_ms"))
        rate_spacing_wait_ms = _number(metadata.get("rate_spacing_wait_ms"))
        reasoning_tokens_raw = metadata.get("reasoning_tokens")
        reasoning_tokens = (
            max(0, int(reasoning_tokens_raw))
            if isinstance(reasoning_tokens_raw, (int, float))
            and math.isfinite(float(reasoning_tokens_raw))
            else None
        )
        cached_input_tokens_raw = record.get("cached_input_tokens")
        cached_input_tokens = (
            max(0, int(cached_input_tokens_raw))
            if isinstance(cached_input_tokens_raw, (int, float))
            and math.isfinite(float(cached_input_tokens_raw))
            else None
        )
        namespace = str(record.get("prompt_namespace") or "")
        stage = str(record.get("stage") or metadata.get("stage") or "")
        effort = str(metadata.get("reasoning_effort") or "")
        call = {
            "ledger_rowid": int(record["ledger_rowid"]),
            "request_id": record.get("request_id"),
            "timestamp_utc": record.get("timestamp_utc"),
            "provider": record.get("provider"),
            "provider_call_status": record.get("provider_call_status") or "completed",
            "report_id": record.get("report_id"),
            "workflow": str(record.get("workflow") or metadata.get("workflow") or ""),
            "stage": stage,
            "artifact_family": str(
                record.get("artifact_family") or metadata.get("artifact_family") or ""
            ),
            "prompt_namespace": namespace,
            "reasoning_effort": effort,
            "model": record.get("model"),
            "provider_operation": metadata.get("provider_operation"),
            "provider_elapsed_ms": elapsed_ms,
            "provider_request_start_monotonic_ms": interval_start_ms,
            "provider_request_finish_monotonic_ms": interval_finish_ms,
            "limiter_wait_ms": round(limiter_wait_ms, 3),
            "in_flight_wait_ms": round(in_flight_wait_ms, 3),
            "rate_spacing_wait_ms": round(rate_spacing_wait_ms, 3),
            "input_tokens": int(record.get("input_tokens") or 0),
            "cached_input_tokens": cached_input_tokens,
            "output_tokens": int(record.get("output_tokens") or 0),
            "total_tokens": int(record.get("total_tokens") or 0),
            "reasoning_tokens": reasoning_tokens,
            "tool_calls": int(record.get("tool_calls") or 0),
            "file_search_call_count": int(metadata.get("file_search_call_count") or 0),
            "repair_attempt": int(metadata.get("repair_attempt") or 0),
            "estimated_cost_usd": round(
                _number(record.get("estimated_cost_usd")), 6
            ),
            "provider_error_type": metadata.get("provider_error_type"),
            "provider_http_status": metadata.get("provider_http_status"),
            "provider_retryable": metadata.get("provider_retryable"),
        }
        calls.append(call)
        groups[(namespace, stage, effort)].append(call)
        groups_by_namespace[namespace].append(call)
        groups_by_stage[stage].append(call)
        groups_by_effort[effort].append(call)
        status_counts[str(call["provider_call_status"])] += 1
        total_limiter_wait_ms += limiter_wait_ms
        total_in_flight_wait_ms += in_flight_wait_ms
        total_rate_spacing_wait_ms += rate_spacing_wait_ms
        if elapsed_ms is not None:
            total_elapsed_ms += elapsed_ms
            timed_call_count += 1
        for token_name in ("input_tokens", "output_tokens", "total_tokens"):
            token_totals[token_name] += call[token_name]
        if cached_input_tokens is not None:
            token_totals["cached_input_tokens"] += cached_input_tokens
            cached_input_reported_call_count += 1
        if reasoning_tokens is not None:
            token_totals["reasoning_tokens"] += reasoning_tokens
            reasoning_reported_call_count += 1

    def _rank(
        groups_to_rank: dict[Any, list[dict[str, Any]]], *, key_name: str
    ) -> list[dict[str, Any]]:
        ranked = []
        for key, members in groups_to_rank.items():
            item = {
                key_name: key,
                **_group_summary(members, exposure_members=calls),
            }
            ranked.append(item)
        return sorted(
            ranked,
            key=lambda item: (
                -item["provider_elapsed_ms_total"],
                str(item[key_name]),
            ),
        )

    grouped = [
        {
            "prompt_namespace": namespace,
            "stage": stage,
            "reasoning_effort": effort,
            **_group_summary(members, exposure_members=calls),
        }
        for (namespace, stage, effort), members in groups.items()
    ]
    grouped.sort(
        key=lambda group: (
            -group["provider_elapsed_ms_total"],
            group["prompt_namespace"],
            group["stage"],
            group["reasoning_effort"],
        )
    )
    slowest = sorted(
        (call for call in calls if call["provider_elapsed_ms"] is not None),
        key=lambda call: (
            -float(call["provider_elapsed_ms"]),
            int(call["ledger_rowid"]),
        ),
    )[: max(0, int(top_n))]

    overall_intervals = _interval_summary(calls)
    analysis_calls = [call for call in calls if call["workflow"] == "report_analysis"]
    analysis_intervals = _interval_summary(analysis_calls)
    report_wall_seconds = _report_wall_seconds(run_result_json, report_id)
    analysis_execution_seconds = _report_analysis_execution_seconds(
        workflow_db, report_id
    )
    wall_clock_exposure = [
        {
            "prompt_namespace": group["prompt_namespace"],
            "provider_active_wall_ms": group["provider_active_wall_ms"],
            "exclusive_exposed_wall_time_ms": group[
                "exclusive_exposed_wall_time_ms"
            ],
            "max_simultaneous_calls": group["max_simultaneous_calls"],
            "call_count": group["call_count"],
            "provider_elapsed_ms_total": group["provider_elapsed_ms_total"],
            "reasoning_efforts": group["reasoning_efforts"],
            "reasoning_tokens": group["reasoning_tokens"],
            "limiter_wait_ms_total": group["limiter_wait_ms_total"],
            "stages": group["stages"],
        }
        for group in _rank(groups_by_namespace, key_name="prompt_namespace")
        if group["interval_timed_call_count"]
    ]
    wall_clock_exposure.sort(
        key=lambda group: (
            -group["provider_active_wall_ms"],
            -group["exclusive_exposed_wall_time_ms"],
            group["prompt_namespace"],
        )
    )
    report_wall_ms = (
        round(report_wall_seconds * 1000, 3)
        if report_wall_seconds is not None
        else None
    )
    analysis_execution_ms = (
        round(analysis_execution_seconds * 1000, 3)
        if analysis_execution_seconds is not None
        else None
    )

    return {
        "schema_version": "1.0",
        "report_id": report_id,
        "usage_event_count": len(calls),
        "timed_call_count": timed_call_count,
        "untimed_call_count": len(calls) - timed_call_count,
        "provider_call_status_counts": dict(sorted(status_counts.items())),
        "provider_elapsed_ms_total": round(total_elapsed_ms, 3),
        "provider_active_wall_ms": overall_intervals["provider_active_wall_ms"],
        "provider_interval_timed_call_count": overall_intervals[
            "interval_timed_call_count"
        ],
        "max_provider_concurrency": overall_intervals[
            "max_simultaneous_calls"
        ],
        "report_analysis_provider_active_wall_ms": analysis_intervals[
            "provider_active_wall_ms"
        ],
        "report_analysis_max_provider_concurrency": analysis_intervals[
            "max_simultaneous_calls"
        ],
        "report_wall_clock_seconds": report_wall_seconds,
        "report_analysis_execution_seconds": analysis_execution_seconds,
        "report_wall_non_provider_residual_ms": (
            round(report_wall_ms - overall_intervals["provider_active_wall_ms"], 3)
            if report_wall_ms is not None
            else None
        ),
        "report_analysis_non_provider_residual_ms": (
            round(
                analysis_execution_ms
                - analysis_intervals["provider_active_wall_ms"],
                3,
            )
            if analysis_execution_ms is not None
            else None
        ),
        "aggregate_provider_work_semantics": (
            "sum of per-call elapsed time; not critical-path duration"
        ),
        "provider_active_wall_semantics": (
            "union of persisted monotonic provider-request intervals"
        ),
        "exclusive_exposed_wall_semantics": (
            "group-active intervals with no other provider call active in the report"
        ),
        "provider_interval_clock_scope": (
            "time.monotonic readings in milliseconds; intervals require a "
            "shared host clock domain"
        ),
        "critical_path_attribution": "not_reconstructed",
        "wall_clock_exposure_ranking_basis": (
            "per-prompt-family interval union; families can overlap and are "
            "not additive"
        ),
        "wall_clock_exposure_ranking": wall_clock_exposure[:5],
        "limiter_wait_ms_total": round(total_limiter_wait_ms, 3),
        "in_flight_wait_ms_total": round(total_in_flight_wait_ms, 3),
        "rate_spacing_wait_ms_total": round(total_rate_spacing_wait_ms, 3),
        **token_totals,
        "reasoning_token_reported_call_count": reasoning_reported_call_count,
        "cached_input_token_reported_call_count": cached_input_reported_call_count,
        "estimated_cost_usd": round(
            sum(call["estimated_cost_usd"] for call in calls), 6
        ),
        "groups_by_prompt_namespace": _rank(
            groups_by_namespace, key_name="prompt_namespace"
        ),
        "groups_by_stage": _rank(groups_by_stage, key_name="stage"),
        "groups_by_reasoning_effort": _rank(
            groups_by_effort, key_name="reasoning_effort"
        ),
        "groups_by_provider_elapsed": grouped,
        "slowest_provider_calls": slowest,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--usage-db", required=True, type=Path)
    parser.add_argument("--report-id", required=True)
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--workflow-db", type=Path)
    parser.add_argument("--run-result-json", type=Path)
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args()
    result = aggregate_report_provider_calls(
        usage_db=args.usage_db,
        report_id=args.report_id,
        top_n=args.top,
        workflow_db=args.workflow_db,
        run_result_json=args.run_result_json,
    )
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output_json is None:
        print(rendered, end="")
    else:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(rendered, encoding="utf-8")


def _report_wall_seconds(path: Path | None, report_id: str) -> float | None:
    if path is None:
        return None
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    candidates = result.get("reports", []) if isinstance(result, dict) else []
    if isinstance(result, dict) and result.get("report_id") == report_id:
        candidates = [result, *candidates]
    for candidate in candidates:
        if not isinstance(candidate, dict) or candidate.get("report_id") != report_id:
            continue
        duration = _optional_nonnegative(candidate.get("total_duration_seconds"))
        if duration is not None:
            return round(duration, 3)
    return None


def _report_analysis_execution_seconds(
    workflow_db: Path | None, report_id: str
) -> float | None:
    if workflow_db is None:
        return None
    try:
        database_uri = f"{workflow_db.resolve().as_uri()}?mode=ro"
        with sqlite3.connect(database_uri, uri=True) as connection:
            connection.row_factory = sqlite3.Row
            job_ids = {
                str(row["job_id"])
                for row in connection.execute(
                    "SELECT job_id FROM workflow_jobs "
                    "WHERE report_id=? AND queue_name='report_analysis'",
                    (report_id,),
                )
            }
            if not job_ids:
                return None
            wall_values: list[int] = []
            rows = connection.execute(
                "SELECT spans.attributes_json,measurements.metric,"
                "measurements.status,measurements.integer_value "
                "FROM performance_telemetry_spans AS spans "
                "JOIN performance_telemetry_measurements AS measurements "
                "ON measurements.span_id=spans.span_id "
                "WHERE measurements.metric='wall_time_ms' "
                "AND measurements.status='observed' "
                "AND measurements.integer_value IS NOT NULL"
            )
            for row in rows:
                try:
                    job_id = str(
                        json.loads(row["attributes_json"] or "{}").get("job_id")
                        or ""
                    )
                except (TypeError, json.JSONDecodeError):
                    continue
                if job_id in job_ids:
                    wall_values.append(max(0, int(row["integer_value"])))
    except (OSError, sqlite3.Error):
        return None
    return round(sum(wall_values) / 1000, 3) if wall_values else None


if __name__ == "__main__":
    main()
