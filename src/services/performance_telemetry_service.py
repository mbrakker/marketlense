"""Canonical persistence and deterministic rollups for performance telemetry."""

from __future__ import annotations

import json
from datetime import datetime
from typing import cast

from src.contracts.performance_telemetry import (
    PerformanceMetric,
    PerformanceTelemetryMeasurement,
    PerformanceTelemetryMeasurementRecordResponse,
    PerformanceTelemetryMetricSummary,
    PerformanceTelemetryRunArtifact,
    PerformanceTelemetrySpan,
    PerformanceTelemetryStageSummary,
)
from src.contracts.run_context import RunContext
from src.services._state_service.common import _state_conn
from src.utils.errors import AppError


def record_performance_span(
    state_db: str, span: PerformanceTelemetrySpan, ctx: RunContext
) -> bool:
    """Persist one span, converging only for an identical retry."""

    values = (
        span.schema_version,
        span.run_id,
        span.stage,
        span.status,
        span.measurement_profile_hash,
        span.queue_name,
        span.worker_id,
        span.queued_at_utc,
        span.started_at_utc,
        span.completed_at_utc,
        json.dumps(span.attributes, ensure_ascii=True, sort_keys=True),
    )
    with _state_conn(state_db, ctx) as conn:
        existing = conn.execute(
            "SELECT schema_version,run_id,stage,status,measurement_profile_hash,"
            "queue_name,worker_id,queued_at_utc,started_at_utc,completed_at_utc,"
            "attributes_json FROM performance_telemetry_spans WHERE span_id=?",
            (span.span_id,),
        ).fetchone()
        if existing is None:
            conn.execute(
                "INSERT INTO performance_telemetry_spans("
                "span_id,schema_version,run_id,stage,status,measurement_profile_hash,"
                "queue_name,worker_id,queued_at_utc,started_at_utc,completed_at_utc,"
                "attributes_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (span.span_id, *values),
            )
            return True
        if tuple(existing) != values:
            raise AppError(
                code="performance_telemetry_conflict",
                message="Telemetry span retry conflicts with retained telemetry",
                retryable=False,
                context={"span_id": span.span_id},
            )
        return False


def record_performance_measurement(
    state_db: str, measurement: PerformanceTelemetryMeasurement, ctx: RunContext
) -> PerformanceTelemetryMeasurementRecordResponse:
    """Persist one scalar metric, converging only for an identical retry."""

    values = (
        measurement.status,
        measurement.integer_value,
        measurement.decimal_value,
    )
    key = (
        measurement.span_id,
        measurement.metric,
        measurement.cache_family,
        measurement.database_role,
    )
    with _state_conn(state_db, ctx) as conn:
        if (
            conn.execute(
                "SELECT 1 FROM performance_telemetry_spans WHERE span_id=?",
                (measurement.span_id,),
            ).fetchone()
            is None
        ):
            raise AppError(
                code="performance_telemetry_span_missing",
                message="Telemetry measurement requires a persisted span",
                retryable=False,
                context={"span_id": measurement.span_id},
            )
        existing = conn.execute(
            "SELECT status,integer_value,decimal_value FROM performance_telemetry_measurements "
            "WHERE span_id=? AND metric=? AND cache_family=? AND database_role=?",
            key,
        ).fetchone()
        if existing is None:
            conn.execute(
                "INSERT INTO performance_telemetry_measurements("
                "span_id,metric,status,integer_value,decimal_value,cache_family,database_role) "
                "VALUES(?,?,?,?,?,?,?)",
                (*key[:2], *values, *key[2:]),
            )
            return PerformanceTelemetryMeasurementRecordResponse(
                schema_version="1.0", inserted=True
            )
        if tuple(existing) != values:
            raise AppError(
                code="performance_telemetry_conflict",
                message="Telemetry measurement retry conflicts with retained telemetry",
                retryable=False,
                context={"span_id": measurement.span_id, "metric": measurement.metric},
            )
        return PerformanceTelemetryMeasurementRecordResponse(
            schema_version="1.0", inserted=False
        )


def build_performance_run_artifact(
    state_db: str, run_id: str, ctx: RunContext
) -> PerformanceTelemetryRunArtifact:
    """Build deterministic p50/p95 wall-time rollups from retained spans."""

    with _state_conn(state_db, ctx) as conn:
        spans = conn.execute(
            "SELECT span_id,stage,measurement_profile_hash,started_at_utc,completed_at_utc "
            "FROM performance_telemetry_spans WHERE run_id=? ORDER BY stage,span_id",
            (run_id,),
        ).fetchall()
        measurements = conn.execute(
            "SELECT spans.stage,measurements.span_id,measurements.metric,"
            "measurements.status,measurements.integer_value "
            "FROM performance_telemetry_measurements AS measurements "
            "JOIN performance_telemetry_spans AS spans ON spans.span_id=measurements.span_id "
            "WHERE spans.run_id=? ORDER BY spans.stage,measurements.metric,measurements.span_id",
            (run_id,),
        ).fetchall()
    profile_hashes = {str(row[2]) for row in spans}
    if len(profile_hashes) > 1:
        raise AppError(
            code="performance_telemetry_profile_incompatible",
            message="Run telemetry has incompatible measurement profiles",
            retryable=False,
            context={"run_id": run_id},
        )
    wall_times = {
        str(row[1]): _persisted_integer(row[4])
        for row in measurements
        if str(row[2]) == "wall_time_ms"
        and str(row[3]) == "observed"
        and row[4] is not None
    }
    by_stage: dict[str, list[int]] = {}
    for span_id, stage, *_ in spans:
        value = wall_times.get(str(span_id))
        if value is not None:
            by_stage.setdefault(str(stage), []).append(value)
    summaries = tuple(
        PerformanceTelemetryStageSummary(
            schema_version="1.0",
            stage=stage,
            sample_count=len(values),
            p50_wall_time_ms=_percentile(values, 0.5),
            p95_wall_time_ms=_percentile(values, 0.95),
            metric_summaries=_metric_summaries(stage, measurements),
        )
        for stage, values in sorted(by_stage.items())
    )
    total_duration = _run_duration_ms(spans)
    return PerformanceTelemetryRunArtifact(
        schema_version="1.0",
        run_id=run_id,
        measurement_profile_hash=next(iter(profile_hashes), ""),
        total_run_duration_ms=total_duration,
        stage_summaries=summaries,
    )


def _metric_summaries(
    stage: str, measurements: list[tuple[object, ...]]
) -> tuple[PerformanceTelemetryMetricSummary, ...]:
    grouped: dict[str, list[tuple[str, int | None]]] = {}
    for measurement_stage, _span_id, metric, status, integer_value in measurements:
        if str(measurement_stage) != stage:
            continue
        grouped.setdefault(str(metric), []).append(
            (
                str(status),
                None if integer_value is None else _persisted_integer(integer_value),
            )
        )
    return tuple(
        PerformanceTelemetryMetricSummary(
            schema_version="1.0",
            metric=cast(PerformanceMetric, metric),
            observed_sample_count=sum(
                1 for status, _ in values if status == "observed"
            ),
            unavailable_count=sum(1 for status, _ in values if status == "unavailable"),
            not_applicable_count=sum(
                1 for status, _ in values if status == "not_applicable"
            ),
            total_integer_value=(
                sum(
                    value
                    for status, value in values
                    if status == "observed" and value is not None
                )
                if any(
                    status == "observed" and value is not None
                    for status, value in values
                )
                else None
            ),
            p50_integer_value=_percentile(
                [
                    value
                    for status, value in values
                    if status == "observed" and value is not None
                ],
                0.5,
            ),
            p95_integer_value=_percentile(
                [
                    value
                    for status, value in values
                    if status == "observed" and value is not None
                ],
                0.95,
            ),
        )
        for metric, values in sorted(grouped.items())
    )


def _percentile(values: list[int], percentile: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int((len(ordered) - 1) * percentile)))
    return ordered[index]


def _persisted_integer(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise AppError(
            code="performance_telemetry_state_corrupt",
            message="Persisted telemetry integer value is malformed",
            retryable=False,
        )
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise AppError(
            code="performance_telemetry_state_corrupt",
            message="Persisted telemetry integer value is malformed",
            cause=exc,
            retryable=False,
        ) from exc
    if parsed < 0:
        raise AppError(
            code="performance_telemetry_state_corrupt",
            message="Persisted telemetry integer value is negative",
            retryable=False,
        )
    return parsed


def _run_duration_ms(spans: list[tuple[object, ...]]) -> int | None:
    timestamps = [
        value
        for row in spans
        for value in (str(row[3] or ""), str(row[4] or ""))
        if value
    ]
    if len(timestamps) < 2:
        return None
    try:
        parsed = [
            datetime.fromisoformat(value.replace("Z", "+00:00")) for value in timestamps
        ]
    except ValueError:
        return None
    return max(0, round((max(parsed) - min(parsed)).total_seconds() * 1000))
