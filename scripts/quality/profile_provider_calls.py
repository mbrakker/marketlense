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
    return round(parsed, 3) if math.isfinite(parsed) and parsed >= 0 else None


def aggregate_report_provider_calls(
    *, usage_db: Path, report_id: str, top_n: int = 10
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
    calls: list[dict[str, Any]] = []
    token_totals = {
        "input_tokens": 0,
        "cached_input_tokens": 0,
        "output_tokens": 0,
        "reasoning_tokens": 0,
    }
    reasoning_reported_call_count = 0
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
            "stage": stage,
            "prompt_namespace": namespace,
            "reasoning_effort": effort,
            "model": record.get("model"),
            "provider_operation": metadata.get("provider_operation"),
            "provider_elapsed_ms": elapsed_ms,
            "limiter_wait_ms": round(limiter_wait_ms, 3),
            "in_flight_wait_ms": round(in_flight_wait_ms, 3),
            "rate_spacing_wait_ms": round(rate_spacing_wait_ms, 3),
            "input_tokens": int(record.get("input_tokens") or 0),
            "cached_input_tokens": int(record.get("cached_input_tokens") or 0),
            "output_tokens": int(record.get("output_tokens") or 0),
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
        status_counts[str(call["provider_call_status"])] += 1
        total_limiter_wait_ms += limiter_wait_ms
        total_in_flight_wait_ms += in_flight_wait_ms
        total_rate_spacing_wait_ms += rate_spacing_wait_ms
        if elapsed_ms is not None:
            total_elapsed_ms += elapsed_ms
            timed_call_count += 1
        for token_name in ("input_tokens", "cached_input_tokens", "output_tokens"):
            token_totals[token_name] += call[token_name]
        if reasoning_tokens is not None:
            token_totals["reasoning_tokens"] += reasoning_tokens
            reasoning_reported_call_count += 1

    grouped: list[dict[str, Any]] = []
    for (namespace, stage, effort), members in groups.items():
        elapsed_values = [
            call["provider_elapsed_ms"]
            for call in members
            if call["provider_elapsed_ms"] is not None
        ]
        grouped.append(
            {
                "prompt_namespace": namespace,
                "stage": stage,
                "reasoning_effort": effort,
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
                    call["cached_input_tokens"] for call in members
                ),
                "output_tokens": sum(call["output_tokens"] for call in members),
                "reasoning_tokens": sum(
                    call["reasoning_tokens"] or 0 for call in members
                ),
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
            }
        )
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

    return {
        "schema_version": "1.0",
        "report_id": report_id,
        "usage_event_count": len(calls),
        "timed_call_count": timed_call_count,
        "untimed_call_count": len(calls) - timed_call_count,
        "provider_call_status_counts": dict(sorted(status_counts.items())),
        "provider_elapsed_ms_total": round(total_elapsed_ms, 3),
        "limiter_wait_ms_total": round(total_limiter_wait_ms, 3),
        "in_flight_wait_ms_total": round(total_in_flight_wait_ms, 3),
        "rate_spacing_wait_ms_total": round(total_rate_spacing_wait_ms, 3),
        **token_totals,
        "reasoning_token_reported_call_count": reasoning_reported_call_count,
        "estimated_cost_usd": round(
            sum(call["estimated_cost_usd"] for call in calls), 6
        ),
        "groups_by_provider_elapsed": grouped,
        "slowest_provider_calls": slowest,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--usage-db", required=True, type=Path)
    parser.add_argument("--report-id", required=True)
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args()
    result = aggregate_report_provider_calls(
        usage_db=args.usage_db,
        report_id=args.report_id,
        top_n=args.top,
    )
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output_json is None:
        print(rendered, end="")
    else:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    main()
