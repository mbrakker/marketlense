from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from scripts.quality.run_command_with_telemetry import main


def _stage_record(
    stage: str,
    *,
    wall_time_ms: int = 4321,
    exit_code: int = 0,
    outcome: str = "passed",
) -> dict[str, object]:
    return {
        "stage": stage,
        "wall_time_ms": wall_time_ms,
        "exit_code": exit_code,
        "outcome": outcome,
        "resource_status": "unavailable",
    }


def _telemetry_payload(
    *stages: dict[str, object], schema_version: str = "1.0"
) -> dict[str, object]:
    return {
        "schema_version": schema_version,
        "stage_count": len(stages),
        "stages": list(stages),
    }


def _import_candidate_stage(output: Path, source: Path) -> int:
    return main(
        [
            "--output-json",
            str(output),
            "--stage",
            "pdf_candidate_benchmark",
            "--merge-stage-json",
            str(source),
        ]
    )


def test_command_runner_records_one_successful_quality_stage(tmp_path: Path) -> None:
    output = tmp_path / "quality-telemetry.json"

    exit_code = main(
        [
            "--output-json",
            str(output),
            "--stage",
            "prompt_fixture_regression",
            "--",
            sys.executable,
            "-c",
            "raise SystemExit(0)",
        ]
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload["stage_count"] == 1
    assert payload["stages"] == [
        {
            "exit_code": 0,
            "outcome": "passed",
            "resource_status": "unavailable",
            "stage": "prompt_fixture_regression",
            "wall_time_ms": payload["stages"][0]["wall_time_ms"],
        }
    ]
    assert payload["stages"][0]["wall_time_ms"] >= 0


def test_command_runner_imports_parallel_stage_telemetry(tmp_path: Path) -> None:
    output = tmp_path / "quality-telemetry.json"
    output.write_text(
        json.dumps(_telemetry_payload(_stage_record("coverage", wall_time_ms=1200))),
        encoding="utf-8",
    )
    parallel_stage = tmp_path / "parallel-stage.json"
    parallel_stage.write_text(
        json.dumps(_telemetry_payload(_stage_record("pdf_candidate_benchmark"))),
        encoding="utf-8",
    )

    exit_code = _import_candidate_stage(output, parallel_stage)

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload["stage_count"] == 2
    assert [stage["stage"] for stage in payload["stages"]] == [
        "coverage",
        "pdf_candidate_benchmark",
    ]
    assert payload["stages"][1]["wall_time_ms"] == 4321


def test_command_runner_retains_failed_parallel_stage_and_fails(tmp_path: Path) -> None:
    output = tmp_path / "quality-telemetry.json"
    output.write_text(
        json.dumps(_telemetry_payload()),
        encoding="utf-8",
    )
    parallel_stage = tmp_path / "parallel-stage.json"
    parallel_stage.write_text(
        json.dumps(
            _telemetry_payload(
                _stage_record("pdf_candidate_benchmark", exit_code=1, outcome="failed")
            )
        ),
        encoding="utf-8",
    )

    exit_code = _import_candidate_stage(output, parallel_stage)

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code == 1
    assert payload["stages"] == [
        {
            "stage": "pdf_candidate_benchmark",
            "wall_time_ms": 4321,
            "exit_code": 1,
            "outcome": "failed",
            "resource_status": "unavailable",
        }
    ]


def test_command_runner_fails_when_parallel_stage_artifact_is_missing(
    tmp_path: Path,
) -> None:
    output = tmp_path / "quality-telemetry.json"
    output.write_text(json.dumps(_telemetry_payload()), encoding="utf-8")
    original_output = output.read_text(encoding="utf-8")

    with pytest.raises(FileNotFoundError):
        _import_candidate_stage(output, tmp_path / "missing-stage.json")

    assert output.read_text(encoding="utf-8") == original_output


@pytest.mark.parametrize(
    ("source_payload", "existing_stage", "message"),
    [
        (
            _telemetry_payload(
                _stage_record("pdf_candidate_benchmark"), schema_version="2.0"
            ),
            None,
            "schema 1.0",
        ),
        (
            _telemetry_payload(),
            None,
            "exactly one stage",
        ),
        (
            {**_telemetry_payload(), "stage_count": True},
            None,
            "exactly one stage",
        ),
        (
            _telemetry_payload(_stage_record("pdf_crop_refine_benchmark")),
            None,
            "does not match",
        ),
        (
            _telemetry_payload(
                {
                    **_stage_record("pdf_candidate_benchmark"),
                    "outcome": ["passed"],
                }
            ),
            None,
            "invalid outcome",
        ),
        (
            _telemetry_payload(_stage_record("pdf_candidate_benchmark", exit_code=1)),
            None,
            "contradictory status",
        ),
        (
            _telemetry_payload(_stage_record("pdf_candidate_benchmark")),
            "pdf_candidate_benchmark",
            "already contains",
        ),
    ],
)
def test_command_runner_rejects_invalid_or_duplicate_parallel_stage(
    tmp_path: Path,
    source_payload: dict[str, object],
    existing_stage: str | None,
    message: str,
) -> None:
    output = tmp_path / "quality-telemetry.json"
    stages = (
        [_stage_record(existing_stage, wall_time_ms=1200)] if existing_stage else []
    )
    output.write_text(json.dumps(_telemetry_payload(*stages)), encoding="utf-8")
    original_output = output.read_text(encoding="utf-8")
    parallel_stage = tmp_path / "parallel-stage.json"
    parallel_stage.write_text(json.dumps(source_payload), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        _import_candidate_stage(output, parallel_stage)

    assert output.read_text(encoding="utf-8") == original_output
