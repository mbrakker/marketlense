"""Run one quality command and retain its bounded wall-time telemetry."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path
from typing import Any


def parse_runner_args(
    argv: list[str] | None = None,
) -> tuple[str, str, list[str], str | None]:
    """Parse a command or import one parallel stage without retaining arguments."""

    parser = argparse.ArgumentParser(
        description=(
            "Run one quality command or merge one run-scoped stage record into "
            "quality telemetry."
        )
    )
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--stage", required=True)
    parser.add_argument("--merge-stage-json")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = list(args.command)
    if command[:1] == ["--"]:
        command = command[1:]
    stage = str(args.stage).strip()
    if not stage or len(stage) > 96:
        parser.error("--stage must contain at most 96 non-whitespace characters")

    if args.merge_stage_json:
        if command:
            parser.error("a command cannot be combined with --merge-stage-json")
        return str(args.output_json), stage, [], str(args.merge_stage_json)
    if not command:
        parser.error("a command is required after --")
    return str(args.output_json), stage, command, None


def main(argv: list[str] | None = None) -> int:
    """Execute a command or import a recorded stage, retaining failure telemetry."""

    output_json, stage, command, merge_stage_json = parse_runner_args(argv)
    if merge_stage_json is not None:
        return _merge_stage(Path(output_json), Path(merge_stage_json), stage)

    started_ns = time.monotonic_ns()
    completed = subprocess.run(command, check=False)
    wall_time_ms = max(0, round((time.monotonic_ns() - started_ns) / 1_000_000))
    _write_stage(
        Path(output_json),
        {
            "stage": stage,
            "wall_time_ms": wall_time_ms,
            "exit_code": int(completed.returncode),
            "outcome": "passed" if completed.returncode == 0 else "failed",
            "resource_status": "unavailable",
        },
    )
    return int(completed.returncode)


def _merge_stage(output: Path, source: Path, expected_stage: str) -> int:
    source_payload = json.loads(source.read_text(encoding="utf-8"))
    if (
        not isinstance(source_payload, dict)
        or source_payload.get("schema_version") != "1.0"
    ):
        raise ValueError("Imported command telemetry must use schema 1.0")
    source_stages = source_payload.get("stages")
    if (
        not isinstance(source_stages, list)
        or type(source_payload.get("stage_count")) is not int
        or source_payload.get("stage_count") != 1
        or len(source_stages) != 1
        or not isinstance(source_stages[0], dict)
    ):
        raise ValueError("Imported command telemetry must contain exactly one stage")
    stage_record = source_stages[0]
    if stage_record.get("stage") != expected_stage:
        raise ValueError("Imported command telemetry stage does not match --stage")
    _validate_stage_record(stage_record)

    payload = _load_payload(output)
    if payload.get("schema_version") != "1.0":
        raise ValueError("Existing command telemetry must use schema 1.0")
    stages = payload["stages"]
    if (
        type(payload.get("stage_count")) is not int
        or payload["stage_count"] != len(stages)
        or any(not isinstance(row, dict) for row in stages)
    ):
        raise ValueError("Existing command telemetry has an invalid stage list")
    if any(row.get("stage") == expected_stage for row in stages):
        raise ValueError(f"Command telemetry already contains stage: {expected_stage}")

    stages.append(stage_record)
    stages.sort(key=lambda item: str(item.get("stage", "")))
    payload["stage_count"] = len(stages)
    _write_payload(output, payload)
    return int(stage_record["exit_code"])


def _validate_stage_record(stage: dict[str, Any]) -> None:
    if (
        not isinstance(stage.get("stage"), str)
        or not stage["stage"].strip()
        or len(stage["stage"]) > 96
    ):
        raise ValueError("Imported command telemetry has an invalid stage name")
    wall_time_ms = stage.get("wall_time_ms")
    if type(wall_time_ms) is not int or wall_time_ms < 0:
        raise ValueError("Imported command telemetry has an invalid wall time")
    exit_code = stage.get("exit_code")
    if type(exit_code) is not int or exit_code < 0:
        raise ValueError("Imported command telemetry has an invalid exit code")
    outcome = stage.get("outcome")
    if not isinstance(outcome, str) or outcome not in {"passed", "failed"}:
        raise ValueError("Imported command telemetry has an invalid outcome")
    if (exit_code == 0) != (outcome == "passed"):
        raise ValueError("Imported command telemetry has contradictory status")
    resource_status = stage.get("resource_status")
    if not isinstance(resource_status, str) or resource_status not in {
        "unavailable",
        "not_applicable",
        "observed",
    }:
        raise ValueError("Imported command telemetry has an invalid resource status")


def _write_stage(output: Path, stage_record: dict[str, int | str]) -> None:
    payload = _load_payload(output)
    retained = [
        item for item in payload["stages"] if item.get("stage") != stage_record["stage"]
    ]
    retained.append(stage_record)
    payload["stages"] = sorted(retained, key=lambda item: str(item["stage"]))
    payload["stage_count"] = len(payload["stages"])
    _write_payload(output, payload)


def _write_payload(output: Path, payload: dict[str, Any]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(f"{output.suffix}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(output)


def _load_payload(output: Path) -> dict[str, Any]:
    if not output.exists():
        return {"schema_version": "1.0", "stage_count": 0, "stages": []}
    payload = json.loads(output.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("stages"), list):
        raise ValueError("Existing command telemetry artifact is malformed")
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
