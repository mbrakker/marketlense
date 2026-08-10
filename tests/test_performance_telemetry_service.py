from __future__ import annotations

import sqlite3

import pytest

from src.contracts.performance_telemetry import (
    PerformanceTelemetryMeasurement,
    PerformanceTelemetrySpan,
)
from src.contracts.run_context import RunContext
from src.services.performance_telemetry_service import (
    build_performance_run_artifact,
    record_performance_measurement,
    record_performance_span,
)
from src.utils.errors import AppError


def _ctx() -> RunContext:
    return RunContext(
        schema_version="1.0",
        run_id="telemetry-test-run",
        task_id="telemetry-test-task",
        span_id="telemetry-test-span",
    )


def _span(span_id: str) -> PerformanceTelemetrySpan:
    return PerformanceTelemetrySpan(
        schema_version="1.0",
        span_id=span_id,
        run_id="run-1",
        stage="report_analysis",
        status="completed",
        measurement_profile_hash="profile-1",
        queue_name="report_analysis",
        started_at_utc="2026-08-10T10:00:00.000+00:00",
        completed_at_utc="2026-08-10T10:00:01.000+00:00",
    )


def test_persists_idempotent_measurements_and_builds_stage_rollup(tmp_path) -> None:
    db_path = str(tmp_path / "state.sqlite")
    record_performance_span(db_path, _span("span-1"), _ctx())
    measurement = PerformanceTelemetryMeasurement(
        schema_version="1.0",
        span_id="span-1",
        metric="wall_time_ms",
        status="observed",
        integer_value=1000,
    )

    first = record_performance_measurement(db_path, measurement, _ctx())
    repeated = record_performance_measurement(db_path, measurement, _ctx())
    artifact = build_performance_run_artifact(db_path, "run-1", _ctx())

    assert first.inserted is True
    assert repeated.inserted is False
    assert artifact.total_run_duration_ms == 1000
    assert artifact.stage_summaries[0].stage == "report_analysis"
    assert artifact.stage_summaries[0].p50_wall_time_ms == 1000
    assert artifact.stage_summaries[0].p95_wall_time_ms == 1000
    assert artifact.stage_summaries[0].metric_summaries[0].metric == "wall_time_ms"
    assert artifact.stage_summaries[0].metric_summaries[0].total_integer_value == 1000


def test_rollup_rejects_corrupt_persisted_integer_value(tmp_path) -> None:
    db_path = str(tmp_path / "state.sqlite")
    record_performance_span(db_path, _span("span-corrupt"), _ctx())
    record_performance_measurement(
        db_path,
        PerformanceTelemetryMeasurement(
            schema_version="1.0",
            span_id="span-corrupt",
            metric="wall_time_ms",
            status="observed",
            integer_value=1,
        ),
        _ctx(),
    )
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE performance_telemetry_measurements SET integer_value='bad' "
            "WHERE span_id='span-corrupt'"
        )

    with pytest.raises(AppError) as error:
        build_performance_run_artifact(db_path, "run-1", _ctx())

    assert error.value.code == "performance_telemetry_state_corrupt"
