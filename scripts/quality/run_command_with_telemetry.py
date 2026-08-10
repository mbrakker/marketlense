"""Run one quality command and retain its bounded wall-time telemetry."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path
from typing import Any


def parse_runner_args(argv: list[str] | None = None) -> tuple[str, str, list[str]]:
    """Parse a single command without retaining its arguments in telemetry."""

    parser = argparse.ArgumentParser(
        description="Run one quality command and retain scalar timing telemetry."
    )
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--stage", required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = list(args.command)
    if command[:1] == ["--"]:
        command = command[1:]
    if not command:
        parser.error("a command is required after --")
    stage = str(args.stage).strip()
    if not stage or len(stage) > 96:
        parser.error("--stage must contain at most 96 non-whitespace characters")
    return str(args.output_json), stage, command


def main(argv: list[str] | None = None) -> int:
    """Execute one command and write its timing record even when it fails."""

    output_json, stage, command = parse_runner_args(argv)
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


def _write_stage(output: Path, stage_record: dict[str, int | str]) -> None:
    payload = _load_payload(output)
    retained = [
        item for item in payload["stages"] if item.get("stage") != stage_record["stage"]
    ]
    retained.append(stage_record)
    payload["stages"] = sorted(retained, key=lambda item: str(item["stage"]))
    payload["stage_count"] = len(payload["stages"])
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
