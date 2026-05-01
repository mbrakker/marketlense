from __future__ import annotations

from src.contracts.tracing import TraceBuildRequest
from src.generators.trace_generator import build_trace_summary


def test_build_trace_summary_reconstructs_nested_spans() -> None:
    events = [
        {
            "run_id": "run-1",
            "trace_id": "trace-1",
            "task_id": "root",
            "span_id": "span-root",
            "parent_span_id": "",
            "span_name": "root",
            "span_depth": 0,
            "role": "orchestrator",
            "module": "m.root",
            "event": "root_start",
            "timestamp_utc": "2026-05-01T20:00:00+00:00",
            "fields": {},
        },
        {
            "run_id": "run-1",
            "trace_id": "trace-1",
            "task_id": "child",
            "span_id": "span-child",
            "parent_span_id": "span-root",
            "span_name": "child",
            "span_depth": 1,
            "role": "service",
            "module": "m.child",
            "event": "child_start",
            "timestamp_utc": "2026-05-01T20:00:01+00:00",
            "fields": {},
        },
        {
            "run_id": "run-1",
            "trace_id": "trace-1",
            "task_id": "child",
            "span_id": "span-child",
            "parent_span_id": "span-root",
            "span_name": "child",
            "span_depth": 1,
            "role": "service",
            "module": "m.child",
            "event": "child_complete",
            "timestamp_utc": "2026-05-01T20:00:03+00:00",
            "fields": {},
        },
    ]

    result = build_trace_summary(
        TraceBuildRequest(schema_version="1.0", events=events, trace_id="trace-1")
    )

    assert result.event_count == 3
    assert result.span_count == 2
    assert result.root_span_ids == ["span-root"]
    root = next(span for span in result.spans if span.span_id == "span-root")
    child = next(span for span in result.spans if span.span_id == "span-child")
    assert root.child_span_ids == ["span-child"]
    assert child.parent_span_id == "span-root"
    assert child.duration_ms == 2000.0


def test_build_trace_summary_filters_by_run_and_task() -> None:
    events = [
        {
            "run_id": "run-1",
            "trace_id": "trace-1",
            "task_id": "keep",
            "span_id": "span-keep",
            "parent_span_id": "",
            "span_name": "keep",
            "span_depth": 0,
            "role": "generator",
            "module": "m.keep",
            "event": "kept",
            "timestamp_utc": "2026-05-01T20:00:00+00:00",
            "fields": {},
        },
        {
            "run_id": "run-2",
            "trace_id": "trace-2",
            "task_id": "drop",
            "span_id": "span-drop",
            "parent_span_id": "",
            "span_name": "drop",
            "span_depth": 0,
            "role": "generator",
            "module": "m.drop",
            "event": "dropped",
            "timestamp_utc": "2026-05-01T20:00:00+00:00",
            "fields": {},
        },
    ]

    result = build_trace_summary(
        TraceBuildRequest(
            schema_version="1.0",
            events=events,
            run_id="run-1",
            task_id="keep",
        )
    )

    assert result.event_count == 1
    assert result.span_count == 1
    assert result.spans[0].span_id == "span-keep"
