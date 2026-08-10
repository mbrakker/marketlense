from __future__ import annotations

from scripts.quality.run_pytest_with_telemetry import (
    PytestTelemetryCollector,
    parse_runner_args,
)


def test_collector_writes_one_bounded_duration_record_per_test() -> None:
    collector = PytestTelemetryCollector()
    assert isinstance(hash(collector), int)
    collector.record(
        nodeid="tests/test_one.py::test_fast", duration_seconds=0.012, outcome="passed"
    )
    collector.record(
        nodeid="tests/test_one.py::test_slow", duration_seconds=0.125, outcome="failed"
    )

    payload = collector.payload()

    assert payload["test_count"] == 2
    assert payload["tests"][0]["duration_ms"] == 12
    assert payload["tests"][0]["resource_status"] == "unavailable"
    assert payload["tests"][1]["outcome"] == "failed"


def test_collector_retains_total_pytest_wall_time() -> None:
    collector = PytestTelemetryCollector()

    payload = collector.payload(total_run_duration_ms=321)

    assert payload["total_run_duration_ms"] == 321


def test_runner_accepts_pytest_options_after_separator() -> None:
    output, pytest_args = parse_runner_args(
        ["--output-json", "out/tests.json", "--", "--cov=src", "-q"]
    )

    assert output == "out/tests.json"
    assert pytest_args == ["--cov=src", "-q"]
