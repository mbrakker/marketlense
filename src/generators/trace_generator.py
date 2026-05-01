from __future__ import annotations

from datetime import datetime
from typing import Any

from src.contracts.tracing import (
    TraceBuildRequest,
    TraceBuildResult,
    TraceSpanSummary,
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _parse_timestamp(value: Any) -> datetime | None:
    text = _text(value)
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _duration_ms(start: str, end: str) -> float:
    start_dt = _parse_timestamp(start)
    end_dt = _parse_timestamp(end)
    if start_dt is None or end_dt is None:
        return 0.0
    return max(0.0, (end_dt - start_dt).total_seconds() * 1000.0)


def _event_matches(request: TraceBuildRequest, event: dict[str, Any]) -> bool:
    if request.trace_id and _text(event.get("trace_id")) != request.trace_id:
        return False
    if request.run_id and _text(event.get("run_id")) != request.run_id:
        return False
    if request.task_id and _text(event.get("task_id")) != request.task_id:
        return False
    if not _text(event.get("span_id")):
        return False
    return True


def _span_sort_key(span: TraceSpanSummary) -> tuple[str, str]:
    return (span.start_utc, span.span_id)


def build_trace_summary(request: TraceBuildRequest) -> TraceBuildResult:
    filtered_events = [
        event
        for event in request.events
        if isinstance(event, dict) and _event_matches(request, event)
    ]
    spans_by_id: dict[str, dict[str, Any]] = {}
    for event in filtered_events:
        span_id = _text(event.get("span_id"))
        timestamp = _text(event.get("timestamp_utc"))
        current = spans_by_id.setdefault(
            span_id,
            {
                "trace_id": _text(event.get("trace_id")),
                "span_id": span_id,
                "parent_span_id": _text(event.get("parent_span_id")),
                "span_name": _text(event.get("span_name"))
                or _text(event.get("task_id")),
                "span_depth": int(event.get("span_depth") or 0),
                "task_id": _text(event.get("task_id")),
                "role": _text(event.get("role")),
                "module": _text(event.get("module")),
                "event_count": 0,
                "start_utc": timestamp,
                "end_utc": timestamp,
            },
        )
        current["event_count"] = int(current["event_count"]) + 1
        current["role"] = _text(event.get("role")) or current["role"]
        current["module"] = _text(event.get("module")) or current["module"]
        if timestamp and (
            not current["start_utc"] or timestamp < str(current["start_utc"])
        ):
            current["start_utc"] = timestamp
        if timestamp and timestamp > str(current["end_utc"]):
            current["end_utc"] = timestamp

    child_ids_by_parent: dict[str, list[str]] = {}
    for span_id, span in spans_by_id.items():
        parent_span_id = _text(span.get("parent_span_id"))
        if parent_span_id:
            child_ids_by_parent.setdefault(parent_span_id, []).append(span_id)

    summaries: list[TraceSpanSummary] = []
    for span in spans_by_id.values():
        start_utc = _text(span.get("start_utc"))
        end_utc = _text(span.get("end_utc"))
        child_span_ids = sorted(
            child_ids_by_parent.get(_text(span.get("span_id")), []),
            key=lambda child_id: (
                _text(spans_by_id.get(child_id, {}).get("start_utc")),
                child_id,
            ),
        )
        summaries.append(
            TraceSpanSummary(
                schema_version="1.0",
                trace_id=_text(span.get("trace_id")),
                span_id=_text(span.get("span_id")),
                parent_span_id=_text(span.get("parent_span_id")),
                span_name=_text(span.get("span_name")),
                span_depth=int(span.get("span_depth") or 0),
                task_id=_text(span.get("task_id")),
                role=_text(span.get("role")),
                module=_text(span.get("module")),
                event_count=int(span.get("event_count") or 0),
                start_utc=start_utc,
                end_utc=end_utc,
                duration_ms=_duration_ms(start_utc, end_utc),
                child_span_ids=child_span_ids,
            )
        )

    summaries = sorted(summaries, key=_span_sort_key)
    span_ids = {span.span_id for span in summaries}
    root_span_ids = [
        span.span_id
        for span in summaries
        if not span.parent_span_id or span.parent_span_id not in span_ids
    ]
    resolved_trace_id = request.trace_id or (
        summaries[0].trace_id if summaries else ""
    )
    resolved_run_id = request.run_id or (
        _text(filtered_events[0].get("run_id")) if filtered_events else ""
    )
    return TraceBuildResult(
        schema_version="1.0",
        trace_id=resolved_trace_id,
        run_id=resolved_run_id,
        task_id=request.task_id,
        event_count=len(filtered_events),
        span_count=len(summaries),
        root_span_ids=root_span_ids,
        spans=summaries,
    )
