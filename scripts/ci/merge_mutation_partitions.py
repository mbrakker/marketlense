"""Fail-closed merge for isolated CI mutation target reports."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ci.run_mutation_gate import (  # noqa: E402
    MutationTarget,
    configured_mutation_targets,
    partition_targets,
)


def _integer(value: object, *, field: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{field} must be an integer >= {minimum}")
    return value


def _number(value: object, *, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{field} must be finite")
    return number


def merge_partition_reports(
    reports: Sequence[dict[str, Any]],
    *,
    targets: Sequence[MutationTarget],
    partition_count: int,
    expected_sha: str,
    expected_run_id: str,
    worker_conclusion: str,
) -> dict[str, Any]:
    """Validate every worker and merge its exact assigned targets once."""

    if worker_conclusion != "success":
        raise ValueError(
            f"mutation partition worker matrix result was {worker_conclusion}"
        )
    if not expected_sha or not expected_run_id:
        raise ValueError("expected commit SHA and evidence run ID are required")
    if len(reports) != partition_count:
        raise ValueError(
            f"expected {partition_count} mutation reports, received {len(reports)}"
        )
    partitions = partition_targets(targets, partition_count=partition_count)
    by_index: dict[int, dict[str, Any]] = {}
    for report in reports:
        if not isinstance(report, dict):
            raise ValueError("mutation partition report must be an object")
        index = _integer(report.get("partition_index"), field="partition_index")
        if index >= partition_count or index in by_index:
            raise ValueError(
                f"mutation partition index is unexpected or duplicated: {index}"
            )
        by_index[index] = report
    if set(by_index) != set(range(partition_count)):
        raise ValueError("mutation partition reports are incomplete")

    expected_by_module = {
        target.report_module or target.module_path.relative_to(ROOT).as_posix(): target
        for target in targets
    }
    if len(expected_by_module) != len(targets):
        raise ValueError("mutation target inventory contains duplicate report modules")
    merged_rows: dict[str, dict[str, Any]] = {}
    defaults: set[float] = set()
    worker_durations: list[int] = []

    for index, partition_targets_for_worker in enumerate(partitions):
        report = by_index[index]
        if report.get("schema_version") != "1.0":
            raise ValueError(f"mutation partition {index} has an unsupported schema")
        if report.get("partition_count") != partition_count:
            raise ValueError(
                f"mutation partition {index} has the wrong partition count"
            )
        if report.get("repository_commit_sha") != expected_sha:
            raise ValueError(f"mutation partition {index} has the wrong commit SHA")
        if report.get("evidence_run_id") != expected_run_id:
            raise ValueError(f"mutation partition {index} has the wrong run identity")

        worker_elapsed_ms = _integer(
            report.get("worker_elapsed_ms"),
            field=f"partition {index} worker_elapsed_ms",
            minimum=1,
        )
        worker_durations.append(worker_elapsed_ms)
        default_score = _number(
            report.get("min_score_default"),
            field=f"partition {index} min_score_default",
        )
        if not 0 <= default_score <= 100:
            raise ValueError(f"mutation partition {index} has an invalid score floor")
        defaults.add(default_score)

        rows = report.get("targets")
        if not isinstance(rows, list) or not rows:
            raise ValueError(f"mutation partition {index} has no target rows")
        expected_modules = {
            target.report_module or target.module_path.relative_to(ROOT).as_posix()
            for target in partition_targets_for_worker
        }
        seen_in_partition: set[str] = set()
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError(f"mutation partition {index} contains a malformed row")
            module = row.get("module")
            if not isinstance(module, str) or not module.strip():
                raise ValueError(f"mutation partition {index} contains an empty module")
            if module in seen_in_partition or module in merged_rows:
                raise ValueError(f"duplicate mutation target result: {module}")
            if module not in expected_modules or module not in expected_by_module:
                raise ValueError(
                    f"unexpected target in mutation partition {index}: {module}"
                )
            seen_in_partition.add(module)

            target = expected_by_module[module]
            total = _integer(row.get("total"), field=f"{module} total", minimum=1)
            killed = _integer(row.get("killed"), field=f"{module} killed")
            if killed > total or total > target.max_mutants:
                raise ValueError(f"mutation counts are invalid for target: {module}")
            score = _number(row.get("score"), field=f"{module} score")
            required_score = max(default_score, target.min_score)
            reported_minimum = _number(
                row.get("min_score"), field=f"{module} min_score"
            )
            if round(score, 4) != round(killed / total * 100.0, 4):
                raise ValueError(
                    f"mutation score does not match counts for target: {module}"
                )
            if round(reported_minimum, 4) != round(required_score, 4):
                raise ValueError(f"mutation score floor is wrong for target: {module}")
            if score < required_score:
                raise ValueError(
                    f"mutation score is below its floor for target: {module}"
                )
            elapsed_ms = _integer(
                row.get("elapsed_ms"), field=f"{module} elapsed_ms", minimum=0
            )
            if elapsed_ms > worker_elapsed_ms:
                raise ValueError(f"target timing exceeds its worker duration: {module}")
            merged_rows[module] = {
                "module": module,
                "killed": killed,
                "total": total,
                "score": round(score, 4),
                "min_score": round(required_score, 4),
                "elapsed_ms": elapsed_ms,
            }
        if seen_in_partition != expected_modules:
            raise ValueError(f"mutation partition {index} is missing assigned targets")

    if len(defaults) != 1:
        raise ValueError("mutation partitions disagree on the global score floor")
    if set(merged_rows) != set(expected_by_module):
        raise ValueError("merged mutation inventory is incomplete")
    ordered_rows = [
        merged_rows[
            target.report_module or target.module_path.relative_to(ROOT).as_posix()
        ]
        for target in targets
    ]
    mutation_wall_time_ms = max(worker_durations)
    return {
        "schema_version": "1.0",
        "min_score_default": defaults.pop(),
        "repository_commit_sha": expected_sha,
        "evidence_run_id": expected_run_id,
        "targets": ordered_rows,
        "execution": {
            "mode": "parallel_target_partitions",
            "partition_count": partition_count,
            "partition_durations_ms": worker_durations,
            "mutation_wall_time_ms": mutation_wall_time_ms,
        },
    }


def record_parallel_mutation_stage(telemetry_path: Path, *, wall_time_ms: int) -> None:
    """Add the longest successful worker duration to existing stage telemetry."""

    if not telemetry_path.is_file():
        raise ValueError("pytest command telemetry is missing before mutation merge")
    payload = json.loads(telemetry_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != "1.0":
        raise ValueError("quality command telemetry must be a schema 1.0 object")
    stages = payload.get("stages")
    if not isinstance(stages, list) or any(not isinstance(row, dict) for row in stages):
        raise ValueError("quality command telemetry stages must be a list of objects")
    if any(row.get("stage") == "mutation" for row in stages):
        raise ValueError("quality command telemetry already contains a mutation stage")
    stages.append(
        {
            "stage": "mutation",
            "wall_time_ms": _integer(
                wall_time_ms, field="mutation wall_time_ms", minimum=0
            ),
            "exit_code": 0,
            "outcome": "passed",
            "resource_status": "unavailable",
        }
    )
    stages.sort(key=lambda row: str(row.get("stage", "")))
    payload["stage_count"] = len(stages)
    temporary = telemetry_path.with_suffix(f"{telemetry_path.suffix}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(telemetry_path)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate and merge exact-SHA mutation partition reports."
    )
    parser.add_argument("--partition-dir", required=True)
    parser.add_argument("--partition-count", type=int, required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--expected-run-id", required=True)
    parser.add_argument("--worker-conclusion", required=True)
    parser.add_argument("--quality-command-telemetry", required=True)
    parser.add_argument("--output-json", default="mutation_results.json")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    paths = sorted(Path(args.partition_dir).glob("*/mutation-partition.json"))
    reports: list[dict[str, Any]] = []
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"mutation partition report must be an object: {path}")
        reports.append(payload)
    try:
        merged = merge_partition_reports(
            reports,
            targets=configured_mutation_targets(),
            partition_count=args.partition_count,
            expected_sha=args.expected_sha,
            expected_run_id=args.expected_run_id,
            worker_conclusion=args.worker_conclusion,
        )
        record_parallel_mutation_stage(
            Path(args.quality_command_telemetry),
            wall_time_ms=int(merged["execution"]["mutation_wall_time_ms"]),
        )
    except ValueError as exc:
        print(f"Mutation partition merge failed: {exc}", file=sys.stderr)
        return 1
    output = Path(args.output_json)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        "Mutation partition merge passed: "
        f"{len(merged['targets'])} targets, "
        f"{merged['execution']['partition_count']} partitions, "
        f"{merged['execution']['mutation_wall_time_ms']} ms critical worker"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
