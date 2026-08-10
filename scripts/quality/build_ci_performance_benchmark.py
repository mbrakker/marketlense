"""Build one bounded CI performance artifact from test and quality telemetry."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


MEASUREMENT_PROFILE_HASH = "ci:pytest-and-quality-gates:v1"


def build_benchmark(
    *, test_telemetry: dict[str, Any], command_telemetry: dict[str, Any]
) -> dict[str, Any]:
    """Combine scalar CI telemetry without inferring live resource measurements."""

    tests = _list_value(test_telemetry, "tests")
    stages = _list_value(command_telemetry, "stages")
    total_test_duration = _non_negative_int(test_telemetry.get("total_run_duration_ms"))
    quality_stages = [
        {
            "stage": str(stage.get("stage", "")),
            "wall_time_ms": _non_negative_int(stage.get("wall_time_ms")) or 0,
            "outcome": str(stage.get("outcome", "failed")),
        }
        for stage in stages
    ]
    quality_stages.sort(key=lambda stage: stage["stage"])
    test_summary = {
        "total": len(tests),
        "passed": sum(1 for test in tests if test.get("outcome") == "passed"),
        "failed": sum(1 for test in tests if test.get("outcome") == "failed"),
    }
    quality_passed = (
        test_summary["failed"] == 0
        and all(stage["outcome"] == "passed" for stage in quality_stages)
        and _non_negative_int(test_telemetry.get("pytest_exit_code")) == 0
    )
    return {
        "schema_version": "1.0",
        "measurement_profile_hash": MEASUREMENT_PROFILE_HASH,
        "total_run_duration_ms": total_test_duration
        + sum(stage["wall_time_ms"] for stage in quality_stages),
        "quality_passed": quality_passed,
        "estimated_cost_usd": "0",
        "test_summary": test_summary,
        "quality_stage_summaries": quality_stages,
    }


def _list_value(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = payload.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError(f"Telemetry field {key} must be a list of objects")
    return value


def _non_negative_int(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return 0
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a comparable CI performance benchmark artifact."
    )
    parser.add_argument("--test-telemetry", required=True)
    parser.add_argument("--command-telemetry", required=True)
    parser.add_argument("--output-json", required=True)
    args = parser.parse_args(argv)
    result = build_benchmark(
        test_telemetry=_load_json(Path(args.test_telemetry)),
        command_telemetry=_load_json_or_empty_stages(Path(args.command_telemetry)),
    )
    output = Path(args.output_json)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Telemetry artifact {path} must contain an object")
    return payload


def _load_json_or_empty_stages(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": "1.0", "stage_count": 0, "stages": []}
    return _load_json(path)


if __name__ == "__main__":
    raise SystemExit(main())
