from __future__ import annotations

import json
import sys
from pathlib import Path

from scripts.quality.run_command_with_telemetry import main


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
