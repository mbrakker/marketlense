"""Typed, bounded contracts for persisted performance telemetry."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Literal

from src.utils.errors import AppError

MeasurementStatus = Literal["unavailable", "not_applicable", "observed"]
PerformanceSpanStatus = Literal["queued", "running", "completed", "failed"]
PerformanceMetric = Literal[
    "queue_wait_ms",
    "wall_time_ms",
    "db_wait_ms",
    "llm_latency_ms",
    "browser_latency_ms",
    "cache_hits",
    "cache_misses",
    "worker_utilisation",
    "total_run_duration_ms",
]

_METRICS = {
    "queue_wait_ms",
    "wall_time_ms",
    "db_wait_ms",
    "llm_latency_ms",
    "browser_latency_ms",
    "cache_hits",
    "cache_misses",
    "worker_utilisation",
    "total_run_duration_ms",
}
_ATTRIBUTE_KEYS = {
    "attempt_id",
    "cache_family",
    "cohort_id",
    "configuration_hash",
    "database_role",
    "job_id",
    "outcome",
    "policy_hash",
    "producer_build_identity",
    "queue_name",
    "validation_run_id",
    "worker_id",
    "workflow",
}


def _validate_identifier(value: str, field_name: str) -> None:
    if not str(value).strip() or len(str(value)) > 256:
        raise AppError(
            code="performance_telemetry_identifier_invalid",
            message="Performance telemetry identifiers must be bounded non-empty strings",
            retryable=False,
            context={"field": field_name},
        )


def _validate_attributes(attributes: dict[str, str | int | bool]) -> None:
    if len(attributes) > 12:
        raise AppError(
            code="performance_telemetry_attribute_invalid",
            message="Performance telemetry attributes exceed the bounded allowlist",
            retryable=False,
        )
    for key, value in attributes.items():
        if key not in _ATTRIBUTE_KEYS or not isinstance(value, (str, int, bool)):
            raise AppError(
                code="performance_telemetry_attribute_invalid",
                message="Performance telemetry attributes must be approved scalar values",
                retryable=False,
                context={"attribute": str(key)[:64]},
            )
        if isinstance(value, str) and len(value) > 256:
            raise AppError(
                code="performance_telemetry_attribute_invalid",
                message="Performance telemetry attribute values must be bounded",
                retryable=False,
                context={"attribute": key},
            )


@dataclass(frozen=True)
class PerformanceTelemetrySpan:
    """One bounded stage or queue-attempt correlation record."""

    schema_version: str = field(metadata={"doc": "Telemetry contract schema version."})
    span_id: str = field(metadata={"doc": "Unique telemetry span identifier."})
    run_id: str = field(metadata={"doc": "Owning workflow run identifier."})
    stage: str = field(metadata={"doc": "Existing workflow or validation stage name."})
    status: PerformanceSpanStatus = field(metadata={"doc": "Current span status."})
    measurement_profile_hash: str = field(
        metadata={"doc": "Immutable measurement environment/profile identity."}
    )
    queue_name: str = field(default="", metadata={"doc": "Owning queue, when queued."})
    worker_id: str = field(
        default="", metadata={"doc": "Worker identity, when claimed."}
    )
    queued_at_utc: str = field(default="", metadata={"doc": "UTC queue timestamp."})
    started_at_utc: str = field(default="", metadata={"doc": "UTC start timestamp."})
    completed_at_utc: str = field(
        default="", metadata={"doc": "UTC completion timestamp."}
    )
    attributes: dict[str, str | int | bool] = field(
        default_factory=dict,
        metadata={"doc": "Bounded scalar correlation attributes only."},
    )

    def __post_init__(self) -> None:
        for field_name in (
            "schema_version",
            "span_id",
            "run_id",
            "stage",
            "measurement_profile_hash",
        ):
            _validate_identifier(str(getattr(self, field_name)), field_name)
        _validate_attributes(self.attributes)


@dataclass(frozen=True)
class PerformanceTelemetryMeasurement:
    """One observed or explicitly unavailable scalar metric for a span."""

    schema_version: str = field(metadata={"doc": "Telemetry contract schema version."})
    span_id: str = field(metadata={"doc": "Owning telemetry span identifier."})
    metric: PerformanceMetric = field(
        metadata={"doc": "Registered scalar metric name."}
    )
    status: MeasurementStatus = field(
        metadata={"doc": "Measurement availability status."}
    )
    integer_value: int | None = field(
        default=None, metadata={"doc": "Observed non-negative integer value."}
    )
    decimal_value: str = field(
        default="", metadata={"doc": "Observed non-negative decimal value."}
    )
    cache_family: str = field(
        default="", metadata={"doc": "Cache family for cache counters."}
    )
    database_role: str = field(
        default="", metadata={"doc": "Database role for database wait."}
    )

    def __post_init__(self) -> None:
        _validate_identifier(self.schema_version, "schema_version")
        _validate_identifier(self.span_id, "span_id")
        if self.metric not in _METRICS:
            raise AppError(
                code="performance_telemetry_measurement_invalid",
                message="Performance telemetry metric is not registered",
                retryable=False,
                context={"metric": str(self.metric)[:64]},
            )
        if self.status not in {"observed", "not_applicable", "unavailable"}:
            raise AppError(
                code="performance_telemetry_measurement_invalid",
                message="Performance telemetry measurement status is invalid",
                retryable=False,
            )
        has_integer = self.integer_value is not None
        has_decimal = bool(self.decimal_value)
        if self.status != "observed" and (has_integer or has_decimal):
            raise AppError(
                code="performance_telemetry_measurement_invalid",
                message="Unavailable telemetry measurements cannot carry numeric values",
                retryable=False,
            )
        if self.status == "observed" and has_integer == has_decimal:
            raise AppError(
                code="performance_telemetry_measurement_invalid",
                message="Observed telemetry measurements require exactly one numeric value",
                retryable=False,
            )
        if has_integer and (
            not isinstance(self.integer_value, int) or self.integer_value < 0
        ):
            raise AppError(
                code="performance_telemetry_measurement_invalid",
                message="Telemetry integer values must be non-negative integers",
                retryable=False,
            )
        if has_decimal:
            try:
                decimal = Decimal(self.decimal_value)
            except (InvalidOperation, ValueError) as exc:
                raise AppError(
                    code="performance_telemetry_measurement_invalid",
                    message="Telemetry decimal values must be valid decimals",
                    cause=exc,
                    retryable=False,
                ) from exc
            if not decimal.is_finite() or decimal < 0:
                raise AppError(
                    code="performance_telemetry_measurement_invalid",
                    message="Telemetry decimal values must be non-negative finite values",
                    retryable=False,
                )
        if len(self.cache_family) > 128 or len(self.database_role) > 128:
            raise AppError(
                code="performance_telemetry_measurement_invalid",
                message="Telemetry measurement dimensions must be bounded",
                retryable=False,
            )


@dataclass(frozen=True)
class PerformanceTelemetryMeasurementRecordResponse:
    schema_version: str = field(metadata={"doc": "Telemetry contract schema version."})
    inserted: bool = field(
        metadata={"doc": "Whether this measurement was newly persisted."}
    )


@dataclass(frozen=True)
class PerformanceTelemetryMetricSummary:
    schema_version: str = field(metadata={"doc": "Telemetry contract schema version."})
    metric: PerformanceMetric = field(
        metadata={"doc": "Registered scalar metric name."}
    )
    observed_sample_count: int = field(
        metadata={"doc": "Number of observed values in this stage."}
    )
    unavailable_count: int = field(
        metadata={"doc": "Number of explicitly unavailable values in this stage."}
    )
    not_applicable_count: int = field(
        metadata={"doc": "Number of not-applicable values in this stage."}
    )
    total_integer_value: int | None = field(
        metadata={"doc": "Sum of observed integer values, or null when none exist."}
    )
    p50_integer_value: int | None = field(
        metadata={"doc": "Median observed integer value, or null when none exist."}
    )
    p95_integer_value: int | None = field(
        metadata={
            "doc": "95th-percentile observed integer value, or null when none exist."
        }
    )


@dataclass(frozen=True)
class PerformanceTelemetryStageSummary:
    schema_version: str = field(metadata={"doc": "Telemetry contract schema version."})
    stage: str = field(metadata={"doc": "Existing workflow or validation stage name."})
    sample_count: int = field(metadata={"doc": "Completed observed wall-time samples."})
    p50_wall_time_ms: int | None = field(
        metadata={"doc": "Median observed wall time, or null when unavailable."}
    )
    p95_wall_time_ms: int | None = field(
        metadata={
            "doc": "95th-percentile observed wall time, or null when unavailable."
        }
    )
    metric_summaries: tuple[PerformanceTelemetryMetricSummary, ...] = field(
        default=(), metadata={"doc": "Per-metric stage resource rollups."}
    )


@dataclass(frozen=True)
class PerformanceTelemetryRunArtifact:
    schema_version: str = field(metadata={"doc": "Telemetry artifact schema version."})
    run_id: str = field(metadata={"doc": "Owning workflow run identifier."})
    measurement_profile_hash: str = field(
        metadata={"doc": "Shared measurement profile identity for this artifact."}
    )
    total_run_duration_ms: int | None = field(
        metadata={
            "doc": "UTC run duration, or null when span timestamps are incomplete."
        }
    )
    stage_summaries: tuple[PerformanceTelemetryStageSummary, ...] = field(
        metadata={"doc": "Deterministic per-stage wall-time rollups."}
    )
