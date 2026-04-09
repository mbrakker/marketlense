from __future__ import annotations

from types import SimpleNamespace

from src.ui.app_pages import overview


def _run_summary(**overrides):
    payload = {
        "display_name": "Ingest",
        "run_type": "ingest",
        "status": "running",
        "run_id": "abcdef123456",
        "created_at_utc": "2026-04-09T10:00:00Z",
        "started_at_utc": "2026-04-09T10:00:05Z",
        "finished_at_utc": "",
        "error_code": "",
        "pid": 123,
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


def test_build_run_dashboard_metrics_counts_states() -> None:
    active = [_run_summary(status="running"), _run_summary(status="queued")]
    recent = active + [
        _run_summary(status="succeeded"),
        _run_summary(status="failed", error_code="io_failed"),
    ]
    failures = [recent[-1]]
    events = [{"event": "worker_finished"}, {"event": "run_polled"}]

    metrics = overview.build_run_dashboard_metrics(
        active_runs=active,
        recent_runs=recent,
        recent_failures=failures,
        recent_events=events,
    )

    assert metrics[0] == {"label": "Active runs", "value": "2", "delta": "1 running"}
    assert metrics[1]["value"] == "1"
    assert metrics[2]["value"] == "1"
    assert metrics[3]["value"] == "2"


def test_build_run_table_rows_formats_identifiers() -> None:
    rows = overview.build_run_table_rows(
        [
            _run_summary(
                display_name="Publisher discovery",
                run_id="1234567890abcdef",
                finished_at_utc="2026-04-09T10:10:00Z",
                error_code="route_failed",
            )
        ]
    )

    assert rows == [
        {
            "workflow": "Publisher discovery",
            "status": "running",
            "run_id": "12345678",
            "created_at_utc": "2026-04-09T10:00:00Z",
            "started_at_utc": "2026-04-09T10:00:05Z",
            "finished_at_utc": "2026-04-09T10:10:00Z",
            "error_code": "route_failed",
            "pid": "123",
        }
    ]


def test_build_log_event_rows_prefers_message_fields() -> None:
    rows = overview.build_log_event_rows(
        [
            {
                "timestamp": 0,
                "level": "info",
                "event": "run_started",
                "message": "worker launched successfully",
            }
        ]
    )

    assert rows == [
        {
            "ts_utc": "1970-01-01 00:00:00 UTC",
            "level": "info",
            "event": "run_started",
            "message": "worker launched successfully",
        }
    ]
