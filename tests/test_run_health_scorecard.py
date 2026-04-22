from __future__ import annotations

from scripts.quality.run_health_scorecard import build_scorecard


def test_run_health_scorecard_summarizes_retries_errors_cost_and_latency() -> None:
    scorecard = build_scorecard(
        [
            {
                "timestamp": "2026-04-22T10:00:00+00:00",
                "run_id": "run-1",
                "event": "pipeline_start",
                "fields": {"cost_usd": 0.10},
            },
            {
                "timestamp": "2026-04-22T10:00:03+00:00",
                "run_id": "run-1",
                "event": "retry_decision",
                "fields": {"cost_usd": 0.20},
            },
            {
                "timestamp": "2026-04-22T10:00:05+00:00",
                "run_id": "run-1",
                "event": "validation_failed",
                "level": "error",
                "fields": {},
            },
        ],
        max_errors=0,
        max_retries=0,
        max_cost_usd=0.25,
    )

    assert scorecard.event_count == 3
    assert scorecard.error_count == 1
    assert scorecard.retry_count == 1
    assert scorecard.validation_failure_count == 1
    assert scorecard.cost_usd == 0.3
    assert scorecard.latency_seconds == 5.0
    assert scorecard.warnings == (
        "error_count 1 exceeds 0",
        "retry_count 1 exceeds 0",
        "cost_usd 0.300000 exceeds 0.250000",
    )
