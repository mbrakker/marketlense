from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.quality.build_ci_performance_benchmark import (
    REQUIRED_QUALITY_STAGES as BENCHMARK_REQUIRED_QUALITY_STAGES,
)
from scripts.quality.build_ci_performance_benchmark import (
    build_benchmark,
    main,
)

REQUIRED_QUALITY_STAGES = (
    "coverage",
    "mutation",
    "quality_non_regression",
    "pdf_candidate_benchmark",
    "pdf_crop_refine_benchmark",
    "pdf_benchmark_trends",
    "public_report_quality",
    "llm_routing_retained_benchmark",
    "workflow_queue_evidence",
    "prompt_fixture_regression",
)


def _test_telemetry(**updates: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "repository_commit_sha": "a" * 40,
        "evidence_run_id": "release-123",
        "test_count": 2,
        "total_run_duration_ms": 100,
        "pytest_exit_code": 0,
        "tests": [
            {
                "nodeid": "tests/test_one.py::test_one",
                "duration_ms": 40,
                "outcome": "passed",
                "resource_status": "unavailable",
            },
            {
                "nodeid": "tests/test_two.py::test_two",
                "duration_ms": 60,
                "outcome": "passed",
                "resource_status": "unavailable",
            },
        ],
    }
    payload.update(updates)
    return payload


def _command_telemetry(
    stages: list[dict[str, object]] | None = None, *, stage_count: object = None
) -> dict[str, object]:
    resolved_stages = (
        stages
        if stages is not None
        else [
            {
                "stage": stage,
                "wall_time_ms": 25,
                "exit_code": 0,
                "outcome": "passed",
                "resource_status": "unavailable",
            }
            for stage in REQUIRED_QUALITY_STAGES
        ]
    )
    return {
        "schema_version": "1.0",
        "stage_count": len(resolved_stages) if stage_count is None else stage_count,
        "stages": resolved_stages,
    }


def test_benchmark_combines_pytest_and_passed_quality_stages() -> None:
    result = build_benchmark(
        test_telemetry=_test_telemetry(),
        command_telemetry=_command_telemetry(),
    )

    assert result["schema_version"] == "1.0"
    assert result["measurement_profile_hash"] == "ci:pytest-and-quality-gates:v2"
    assert result["total_run_duration_ms"] == 100
    assert result["pytest_duration_ms"] == 100
    assert result["quality_command_duration_ms"] == len(REQUIRED_QUALITY_STAGES) * 25
    assert (
        result["aggregate_command_duration_ms"]
        == 100 + len(REQUIRED_QUALITY_STAGES) * 25
    )
    assert result["workflow_elapsed_ms"] is None
    assert result["workflow_critical_path_ms"] is None
    assert result["estimated_cost_usd"] is None
    assert result["quality_validation_errors"] == []
    assert result["quality_passed"] is True
    assert result["passed"] is True
    assert result["repository_commit_sha"] == "a" * 40
    assert result["evidence_run_id"] == "release-123"
    assert result["test_summary"] == {"failed": 0, "passed": 2, "total": 2}
    assert {stage["stage"] for stage in result["quality_stage_summaries"]} == set(
        REQUIRED_QUALITY_STAGES
    )


@pytest.mark.parametrize("invalid_exit_code", [None, True, False, "0", 0.0])
def test_benchmark_fails_closed_for_missing_or_invalid_pytest_exit_code(
    invalid_exit_code: object,
) -> None:
    telemetry = _test_telemetry(pytest_exit_code=invalid_exit_code)

    result = build_benchmark(
        test_telemetry=telemetry,
        command_telemetry=_command_telemetry(),
    )

    assert result["quality_passed"] is False
    assert result["passed"] is False
    assert any(
        "pytest_exit_code" in issue for issue in result["quality_validation_errors"]
    )


def test_benchmark_fails_closed_when_pytest_exit_code_is_missing() -> None:
    telemetry = _test_telemetry()
    del telemetry["pytest_exit_code"]

    result = build_benchmark(
        test_telemetry=telemetry,
        command_telemetry=_command_telemetry(),
    )

    assert result["passed"] is False


def test_benchmark_fails_quality_when_pytest_exits_unsuccessfully() -> None:
    result = build_benchmark(
        test_telemetry=_test_telemetry(pytest_exit_code=1),
        command_telemetry=_command_telemetry(),
    )

    assert result["quality_passed"] is False
    assert result["passed"] is False
    assert "pytest_exit_code_nonzero" in result["quality_validation_errors"]


@pytest.mark.parametrize(
    "test_updates",
    [
        {"test_count": 1},
        {"test_count": True},
        {"tests": [{"nodeid": "test", "duration_ms": 1, "outcome": "unknown"}]},
        {"tests": [{"nodeid": "test", "duration_ms": 1, "outcome": []}]},
        {"tests": [{"nodeid": "test", "duration_ms": 1, "outcome": "failed"}]},
        {"tests": [{"nodeid": "test", "duration_ms": -1, "outcome": "passed"}]},
        {"tests": ["malformed"]},
    ],
)
def test_benchmark_fails_closed_for_incomplete_or_contradictory_test_records(
    test_updates: dict[str, object],
) -> None:
    telemetry = _test_telemetry(**test_updates)

    result = build_benchmark(
        test_telemetry=telemetry,
        command_telemetry=_command_telemetry(),
    )

    assert result["quality_passed"] is False
    assert result["passed"] is False


def test_benchmark_fails_closed_for_missing_command_telemetry() -> None:
    result = build_benchmark(
        test_telemetry=_test_telemetry(),
        command_telemetry={},
    )

    assert result["quality_passed"] is False
    assert result["passed"] is False
    assert result["quality_stage_summaries"] == []
    assert any("stages" in issue for issue in result["quality_validation_errors"])


@pytest.mark.parametrize(
    "stages,stage_count",
    [
        (_command_telemetry()["stages"][:-1], len(REQUIRED_QUALITY_STAGES) - 1),
        (
            [*_command_telemetry()["stages"], _command_telemetry()["stages"][0]],
            len(REQUIRED_QUALITY_STAGES) + 1,
        ),
        (_command_telemetry()["stages"], len(REQUIRED_QUALITY_STAGES) - 1),
    ],
)
def test_benchmark_rejects_missing_duplicate_or_mismatched_stage_count(
    stages: list[dict[str, object]], stage_count: int
) -> None:
    result = build_benchmark(
        test_telemetry=_test_telemetry(),
        command_telemetry=_command_telemetry(stages, stage_count=stage_count),
    )

    assert result["quality_passed"] is False
    assert result["passed"] is False


@pytest.mark.parametrize(
    "stage_updates",
    [
        {"exit_code": 1},
        {"exit_code": 1, "outcome": "failed"},
        {"exit_code": True},
        {"outcome": "failed"},
        {"outcome": "unknown"},
        {"outcome": []},
        {"wall_time_ms": -1},
        {"resource_status": None},
        {"resource_status": []},
    ],
)
def test_benchmark_rejects_invalid_or_unsuccessful_quality_stage(
    stage_updates: dict[str, object],
) -> None:
    stages = _command_telemetry()["stages"]
    assert isinstance(stages, list)
    first_stage = dict(stages[0])
    first_stage.update(stage_updates)
    stages[0] = first_stage

    result = build_benchmark(
        test_telemetry=_test_telemetry(),
        command_telemetry=_command_telemetry(stages),
    )

    assert result["quality_passed"] is False
    assert result["passed"] is False


def test_ci_workflow_stage_inventory_matches_benchmark_contract() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    workflow_stages = set(re.findall(r"--stage ([a-z_]+)", workflow)) | {"mutation"}

    assert BENCHMARK_REQUIRED_QUALITY_STAGES == REQUIRED_QUALITY_STAGES
    assert workflow_stages == set(BENCHMARK_REQUIRED_QUALITY_STAGES)


def test_builder_writes_failed_benchmark_when_command_telemetry_is_missing(
    tmp_path: Path,
) -> None:
    test_telemetry = tmp_path / "tests.json"
    output = tmp_path / "benchmark.json"
    test_telemetry.write_text(
        json.dumps(_test_telemetry()),
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

    benchmark = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert benchmark["quality_passed"] is False
    assert benchmark["passed"] is False
    assert benchmark["test_summary"]["passed"] == 2


def test_builder_writes_failed_diagnostic_when_test_telemetry_is_missing(
    tmp_path: Path,
) -> None:
    output = tmp_path / "benchmark.json"

    exit_code = main(
        [
            "--test-telemetry",
            str(tmp_path / "missing-tests.json"),
            "--command-telemetry",
            str(tmp_path / "missing-commands.json"),
            "--output-json",
            str(output),
        ]
    )

    benchmark = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert benchmark["passed"] is False
    assert benchmark["quality_passed"] is False


def test_builder_writes_failed_diagnostic_when_command_telemetry_is_malformed(
    tmp_path: Path,
) -> None:
    test_telemetry = tmp_path / "tests.json"
    command_telemetry = tmp_path / "commands.json"
    output = tmp_path / "benchmark.json"
    test_telemetry.write_text(json.dumps(_test_telemetry()), encoding="utf-8")
    command_telemetry.write_text("not-json", encoding="utf-8")

    exit_code = main(
        [
            "--test-telemetry",
            str(test_telemetry),
            "--command-telemetry",
            str(command_telemetry),
            "--output-json",
            str(output),
        ]
    )

    benchmark = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert benchmark["passed"] is False
    assert "command_telemetry_invalid_json" in benchmark["quality_validation_errors"]


def test_ci_builds_benchmark_even_when_test_telemetry_is_absent() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    builder_step = workflow.split("- name: Build CI performance benchmark\n", 1)[1]
    builder_step = builder_step.split("      - name:", 1)[0]

    assert (
        "if: ${{ always() && steps.check_full_ci_prerequisites.outcome == 'success' }}"
        in builder_step
    )
    assert "hashFiles('out/test_telemetry_ci.json')" not in builder_step


@pytest.mark.parametrize(
    "script_path",
    [
        "scripts/quality/build_release_evidence_summary.py",
        "scripts/quality/release_evidence_review.py",
    ],
)
def test_release_evidence_consumers_start_as_direct_scripts(script_path: str) -> None:
    completed = subprocess.run(
        [sys.executable, script_path, "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
