"""Measure bounded provider-wait overlap through the production supervisor."""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.contracts.run_context import RunContext
from src.contracts.workflow_control import (
    SupervisorRunRequest,
    WorkflowSupervisorSettings,
)
from src.orchestrators.workflow_supervisor_orchestrator import (
    SupervisorDependencies,
    run_supervisor_once,
)


def _ctx() -> RunContext:
    return RunContext(
        schema_version="1.0",
        run_id="workflow-supervisor-parallelism-benchmark",
        task_id="benchmark",
        span_id="benchmark",
    )


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    index = (len(ordered) - 1) * percentile
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] * (1 - (index - lower)) + ordered[upper] * (index - lower)


def _run_sample(*, workers: int, provider_latency_ms: int) -> dict[str, object]:
    calls: list[str] = []

    def worker(**kwargs):
        calls.append(str(kwargs["queue_name"]))
        time.sleep(provider_latency_ms / 1_000)
        return SimpleNamespace(released_lease_job_ids=[], terminal_status="succeeded")

    started = time.perf_counter()
    result = run_supervisor_once(
        SupervisorRunRequest(
            schema_version="1.0",
            state_db="benchmark.sqlite",
            usage_db_path="benchmark-usage.sqlite",
            worker_id="benchmark-supervisor",
            now_utc="2026-08-11T00:00:00Z",
            settings=WorkflowSupervisorSettings(
                schema_version="1.0",
                enabled=True,
                materialize_outbox_enabled=False,
                recover_expired_leases_enabled=False,
                worker_batches_enabled=True,
                reconcile_enabled=False,
                evidence_enabled=False,
                max_parallel_workers=workers,
                max_jobs_per_queue=1,
                max_total_jobs=3,
                max_runtime_seconds=60,
            ),
        ),
        _ctx(),
        dependencies=SupervisorDependencies(
            acquire_lease=lambda *args, **kwargs: True,
            release_lease=lambda *args, **kwargs: None,
            materialize_outbox=lambda *args, **kwargs: [],
            recover_leases=lambda *args, **kwargs: [],
            run_worker=worker,
            reconcile=lambda *args, **kwargs: {},
            queue_health=lambda *args, **kwargs: [],
        ),
    )
    return {
        "wall_ms": round((time.perf_counter() - started) * 1_000, 3),
        "completed_job_count": result.completed_job_count,
        "terminal_status": result.status,
        "queue_names": sorted(calls),
        "quality_passed": (
            result.status == "healthy"
            and result.completed_job_count == 3
            and len(calls) == 3
        ),
        "estimated_cost_usd": 0.0,
    }


def run_matrix(
    *,
    warmups: int,
    runs: int,
    provider_latency_ms: int,
) -> dict[str, object]:
    profiles: dict[str, dict[str, object]] = {}
    for workers in (1, 3):
        for _ in range(warmups):
            _run_sample(workers=workers, provider_latency_ms=provider_latency_ms)
        samples = [
            _run_sample(workers=workers, provider_latency_ms=provider_latency_ms)
            for _ in range(runs)
        ]
        walls = [float(sample["wall_ms"]) for sample in samples]
        profiles[str(workers)] = {
            "samples": samples,
            "median_wall_ms": round(statistics.median(walls), 3),
            "p95_wall_ms": round(_percentile(walls, 0.95), 3),
            "cv_wall": round(statistics.pstdev(walls) / statistics.mean(walls), 4),
            "quality_passed": all(bool(sample["quality_passed"]) for sample in samples),
            "estimated_cost_usd": 0.0,
        }
    serial = profiles["1"]
    parallel = profiles["3"]
    speedup = float(serial["median_wall_ms"]) / float(parallel["median_wall_ms"])
    quality_ok = bool(serial["quality_passed"]) and bool(parallel["quality_passed"])
    return {
        "schema_version": "1.0",
        "classification": "PROVEN" if quality_ok and speedup > 1 else "REGRESSION",
        "workload": {
            "provider_latency_ms": provider_latency_ms,
            "tasks_per_sample": 3,
            "warmups": warmups,
            "runs": runs,
            "model_calls": 0,
        },
        "profiles": profiles,
        "comparison": {
            "baseline_workers": 1,
            "parallel_workers": 3,
            "speedup_ratio": round(speedup, 4),
            "speedup_percent": round((speedup - 1) * 100, 2),
            "quality_non_regression": quality_ok,
            "cost_non_regression": True,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--warmups", type=int, default=2)
    parser.add_argument("--runs", type=int, default=7)
    parser.add_argument("--provider-latency-ms", type=int, default=3_200)
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path("outputs/workflow-supervisor-parallelism.json"),
    )
    args = parser.parse_args()
    artifact = run_matrix(
        warmups=max(0, args.warmups),
        runs=max(1, args.runs),
        provider_latency_ms=max(1, args.provider_latency_ms),
    )
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(artifact["comparison"], sort_keys=True))


if __name__ == "__main__":
    main()
