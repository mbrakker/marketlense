from __future__ import annotations

from src.contracts.run_context import RunContext
from src.utils.logging import child_context, log_event, new_run_context, validate_log_event_payload


def test_log_event_matches_unified_schema() -> None:
    ctx = RunContext(
        schema_version="1.0",
        run_id="run-1",
        task_id="task-1",
        span_id="span-1",
    )

    payload = log_event(
        ctx,
        role="service",
        event="service_started",
        module="src.services.example",
        fields={"authorization": "Bearer secret-token", "count": 1},
    )
    result = validate_log_event_payload(payload)

    assert result.valid is True
    assert result.missing_fields == ()
    assert result.invalid_fields == ()
    assert '"trace_id": "run-1"' in payload
    assert '"span_name": "task-1"' in payload
    assert "secret-token" not in payload


def test_child_context_preserves_trace_and_parent_span() -> None:
    root = new_run_context(task_id="root")
    child = child_context(root, task_id="child")

    assert child.trace_id == root.trace_id
    assert child.parent_span_id == root.span_id
    assert child.span_name == "child"
    assert child.span_depth == root.span_depth + 1


def test_log_event_schema_reports_missing_and_invalid_fields() -> None:
    result = validate_log_event_payload(
        {"run_id": "", "role": "controller", "fields": "not-a-dict"}
    )

    assert result.valid is False
    assert result.missing_fields == (
        "event",
        "module",
        "parent_span_id",
        "span_depth",
        "span_id",
        "span_name",
        "task_id",
        "timestamp_utc",
        "trace_id",
    )
    assert result.invalid_fields == ("fields", "role", "run_id")
