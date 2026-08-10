from __future__ import annotations

import pytest

from src.contracts.performance_telemetry import (
    PerformanceTelemetryMeasurement,
    PerformanceTelemetrySpan,
)
from src.utils.errors import AppError


def test_measurement_retains_explicit_unavailable_status() -> None:
    measurement = PerformanceTelemetryMeasurement(
        schema_version="1.0",
        span_id="span-1",
        metric="browser_latency_ms",
        status="unavailable",
    )

    assert measurement.status == "unavailable"
    assert measurement.integer_value is None


def test_measurement_rejects_zero_as_substitute_for_unavailable() -> None:
    with pytest.raises(AppError) as error:
        PerformanceTelemetryMeasurement(
            schema_version="1.0",
            span_id="span-1",
            metric="browser_latency_ms",
            status="unavailable",
            integer_value=0,
        )

    assert error.value.code == "performance_telemetry_measurement_invalid"


def test_span_rejects_unbounded_content_attributes() -> None:
    with pytest.raises(AppError) as error:
        PerformanceTelemetrySpan(
            schema_version="1.0",
            span_id="span-1",
            run_id="run-1",
            stage="report_analysis",
            status="running",
            measurement_profile_hash="profile-1",
            attributes={"prompt": "secret prompt content"},
        )

    assert error.value.code == "performance_telemetry_attribute_invalid"
