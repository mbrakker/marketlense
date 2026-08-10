from __future__ import annotations

import json
from pathlib import Path

from scripts.quality.build_ci_performance_benchmark import build_benchmark, main


def test_benchmark_combines_pytest_and_passed_quality_stages() -> None:
    result = build_benchmark(
        test_telemetry={
            "schema_version": "1.0",
            "test_count": 2,
            "total_run_duration_ms": 100,
            "tests": [
                {"outcome": "passed"},
                {"outcome": "passed"},
            ],
        },
        command_telemetry={
            "schema_version": "1.0",
            "stage_count": 1,
            "stages": [
                {
                    "stage": "prompt_fixture_regression",
                    "wall_time_ms": 25,
                    "outcome": "passed",
                }
            ],
        },
    )

    assert result["measurement_profile_hash"] == "ci:pytest-and-quality-gates:v1"
    assert result["total_run_duration_ms"] == 125
    assert result["quality_passed"] is True
    assert result["estimated_cost_usd"] == "0"
    assert result["test_summary"] == {"failed": 0, "passed": 2, "total": 2}
    assert result["quality_stage_summaries"] == [
        {
            "outcome": "passed",
            "stage": "prompt_fixture_regression",
            "wall_time_ms": 25,
        }
    ]


def test_benchmark_fails_quality_when_pytest_exits_unsuccessfully() -> None:
    result = build_benchmark(
        test_telemetry={
            "schema_version": "1.0",
            "test_count": 0,
            "total_run_duration_ms": 10,
            "pytest_exit_code": 1,
            "tests": [],
        },
        command_telemetry={"schema_version": "1.0", "stage_count": 0, "stages": []},
    )

    assert result["quality_passed"] is False


def test_builder_writes_failed_benchmark_when_command_telemetry_is_missing(
    tmp_path: Path,
) -> None:
    test_telemetry = tmp_path / "tests.json"
    output = tmp_path / "benchmark.json"
    test_telemetry.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "total_run_duration_ms": 10,
                "pytest_exit_code": 1,
                "tests": [],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "--test-telemetry",
            str(test_telemetry),
            "--command-telemetry",
            str(tmp_path / "missing.json"),
            "--output-json",
            str(output),
        ]
    )

    assert exit_code == 0
    assert json.loads(output.read_text(encoding="utf-8"))["quality_passed"] is False
