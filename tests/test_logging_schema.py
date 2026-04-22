from __future__ import annotations

from src.contracts.run_context import RunContext
from src.utils.logging import log_event, validate_log_event_payload


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
    assert "secret-token" not in payload


def test_log_event_schema_reports_missing_and_invalid_fields() -> None:
    result = validate_log_event_payload(
        {"run_id": "", "role": "controller", "fields": "not-a-dict"}
    )

    assert result.valid is False
    assert result.missing_fields == ("event", "module", "span_id", "task_id")
    assert result.invalid_fields == ("fields", "role", "run_id")
