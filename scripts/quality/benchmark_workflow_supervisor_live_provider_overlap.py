"""Controlled live-provider overlap canary through the production supervisor."""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path
from threading import Lock
from types import SimpleNamespace

import yaml
from dotenv import find_dotenv, load_dotenv

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.contracts.openai import OpenAIJSONPromptRequest
from src.contracts.run_context import RunContext
from src.contracts.workflow_control import (
    SupervisorRunRequest,
    WorkflowSupervisorSettings,
)
from src.orchestrators.workflow_supervisor_orchestrator import (
    SupervisorDependencies,
    run_supervisor_once,
)
from src.services import llm_service

_MODEL = "gpt-5-mini"
_TASKS_PER_SAMPLE = 3
_MAX_OUTPUT_TOKENS = 512
_REQUEST_TIMEOUT_SECONDS = 30.0


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    index = (len(ordered) - 1) * percentile
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] * (1 - (index - lower)) + ordered[upper] * (index - lower)


def _load_environment() -> tuple[str, dict, dict]:
    load_dotenv(find_dotenv(filename=".env", usecwd=True))
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for the live provider canary")
    pricing = yaml.safe_load(
        Path("src/config/llm-costs.yaml").read_text(encoding="utf-8")
    )["pricing"]
    return api_key, pricing, pricing[_MODEL]


def _call_provider(
    *,
    api_key: str,
    pricing: dict,
    rate: dict,
    state_root: Path,
    case_id: str,
    submitted_at: float,
) -> dict[str, object]:
    expected = {"case_id": case_id, "status": "ok"}
    started = time.perf_counter()
    case_root = state_root / hashlib.sha256(case_id.encode("utf-8")).hexdigest()[:16]
    ctx = RunContext(
        schema_version="1.0",
        run_id="workflow-supervisor-live",
        task_id=case_id,
        span_id=case_id,
    )
    request = OpenAIJSONPromptRequest(
        schema_version="1.0",
        system_prompt="Return strict JSON only. Do not add fields or prose.",
        user_prompt="Return exactly this JSON object: "
        + json.dumps(expected, separators=(",", ":"), ensure_ascii=True),
        model=_MODEL,
        temperature=0.0,
        api_key=api_key,
        seed=7,
        max_output_tokens=_MAX_OUTPUT_TOKENS,
        timeout_seconds=_REQUEST_TIMEOUT_SECONDS,
        cost_ledger_path=str(case_root / "cost-ledger.jsonl"),
        cost_daily_path=str(case_root / "cost-daily.json"),
        model_pricing=pricing,
        response_cache_enabled=False,
        prompt_namespace="quality/workflow_supervisor_live_provider_overlap",
        prompt_hash="workflow-supervisor-live-provider-overlap-v1",
        usage_db_path=str(case_root / "llm_usage.sqlite"),
    )
    try:
        response = llm_service.openai_chat_json(request, ctx)
        input_tokens = response.input_tokens
        output_tokens = response.output_tokens
        cost = None
        if input_tokens is not None and output_tokens is not None:
            cost = (input_tokens / 1_000 * float(rate["input_tokens_per_1k_usd"])) + (
                output_tokens / 1_000 * float(rate["output_tokens_per_1k_usd"])
            )
        return {
            "case_id_sha256": hashlib.sha256(case_id.encode("utf-8")).hexdigest(),
            "queue_wait_ms": round((started - submitted_at) * 1_000, 3),
            "provider_wall_ms": round((time.perf_counter() - started) * 1_000, 3),
            "quality_passed": response.parsed_json == expected,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "estimated_cost_usd": cost,
            "error_type": "",
        }
    except Exception as exc:
        return {
            "case_id_sha256": hashlib.sha256(case_id.encode("utf-8")).hexdigest(),
            "queue_wait_ms": round((started - submitted_at) * 1_000, 3),
            "provider_wall_ms": round((time.perf_counter() - started) * 1_000, 3),
            "quality_passed": False,
            "input_tokens": None,
            "output_tokens": None,
            "estimated_cost_usd": None,
            "error_type": type(exc).__name__,
        }


def _run_sample(
    *,
    workers: int,
    phase: str,
    sequence: int,
    api_key: str,
    pricing: dict,
    rate: dict,
    state_root: Path,
) -> dict[str, object]:
    sample_started = time.perf_counter()
    lock = Lock()
    task_index = 0
    calls: list[dict[str, object]] = []

    def worker(**kwargs):
        nonlocal task_index
        with lock:
            index = task_index
            task_index += 1
        queue_name = str(kwargs["queue_name"])
        case_id = (
            f"ws-live-{workers}-{phase[:1]}-{sequence:02d}-{index:02d}-{queue_name}"
        )
        call = _call_provider(
            api_key=api_key,
            pricing=pricing,
            rate=rate,
            state_root=state_root,
            case_id=case_id,
            submitted_at=sample_started,
        )
        with lock:
            calls.append(call)
        return SimpleNamespace(
            released_lease_job_ids=[],
            terminal_status="succeeded" if call["quality_passed"] else "dead_letter",
        )

    result = run_supervisor_once(
        SupervisorRunRequest(
            schema_version="1.0",
            state_db="live-provider-canary.sqlite",
            usage_db_path="live-provider-canary-usage.sqlite",
            worker_id="live-provider-supervisor",
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
                max_total_jobs=_TASKS_PER_SAMPLE,
                max_runtime_seconds=120,
            ),
        ),
        RunContext(
            schema_version="1.0",
            run_id=f"workflow-supervisor-live-{workers}-{phase}-{sequence}",
            task_id="supervisor",
            span_id="supervisor",
        ),
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
    costs = [call["estimated_cost_usd"] for call in calls]
    return {
        "phase": phase,
        "sequence": sequence,
        "workers": workers,
        "wall_ms": round((time.perf_counter() - sample_started) * 1_000, 3),
        "quality_passed": result.status == "healthy"
        and all(bool(call["quality_passed"]) for call in calls),
        "cost_known": all(cost is not None for cost in costs),
        "estimated_cost_usd": round(
            sum(float(cost) for cost in costs if cost is not None), 8
        ),
        "calls": calls,
    }


def _summarize(samples: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    summaries: dict[str, dict[str, object]] = {}
    for workers in (1, 3):
        selected = [sample for sample in samples if sample["workers"] == workers]
        walls = [float(sample["wall_ms"]) for sample in selected]
        queue_waits = [
            float(call["queue_wait_ms"])
            for sample in selected
            for call in sample["calls"]
        ]
        provider_walls = [
            float(call["provider_wall_ms"])
            for sample in selected
            for call in sample["calls"]
        ]
        costs = [float(sample["estimated_cost_usd"]) for sample in selected]
        summaries[str(workers)] = {
            "sample_count": len(selected),
            "median_wall_ms": round(statistics.median(walls), 3),
            "p95_wall_ms": round(_percentile(walls, 0.95), 3),
            "cv_wall": round(statistics.pstdev(walls) / statistics.mean(walls), 4),
            "median_queue_wait_ms": round(statistics.median(queue_waits), 3),
            "median_provider_wall_ms": round(statistics.median(provider_walls), 3),
            "median_cost_usd": round(statistics.median(costs), 8),
            "quality_passed": all(
                bool(sample["quality_passed"]) for sample in selected
            ),
            "cost_known": all(bool(sample["cost_known"]) for sample in selected),
        }
    return summaries


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--warmups", type=int, default=2)
    parser.add_argument("--runs", type=int, default=7)
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path("outputs/workflow-supervisor-live-provider-overlap.json"),
    )
    args = parser.parse_args()
    api_key, pricing, rate = _load_environment()
    state_root = Path(tempfile.mkdtemp(prefix="marketlense-supervisor-live-"))
    preflight = _call_provider(
        api_key=api_key,
        pricing=pricing,
        rate=rate,
        state_root=state_root,
        case_id="ws-live-preflight",
        submitted_at=time.perf_counter(),
    )
    samples: list[dict[str, object]] = []
    if preflight["quality_passed"]:
        phases = (("warmup", max(0, args.warmups)), ("measured", max(1, args.runs)))
        for phase, count in phases:
            for sequence in range(count):
                order = (1, 3) if sequence % 2 == 0 else (3, 1)
                for workers in order:
                    samples.append(
                        _run_sample(
                            workers=workers,
                            phase=phase,
                            sequence=sequence,
                            api_key=api_key,
                            pricing=pricing,
                            rate=rate,
                            state_root=state_root,
                        )
                    )
    measured = [sample for sample in samples if sample["phase"] == "measured"]
    summaries = _summarize(measured) if measured else {}
    serial = summaries.get("1", {})
    parallel = summaries.get("3", {})
    serial_median = float(serial.get("median_wall_ms", 0))
    parallel_median = float(parallel.get("median_wall_ms", 1))
    speedup = serial_median / parallel_median
    quality_ok = (
        bool(preflight["quality_passed"])
        and bool(serial.get("quality_passed"))
        and bool(parallel.get("quality_passed"))
    )
    cost_ok = (
        bool(serial.get("cost_known"))
        and bool(parallel.get("cost_known"))
        and float(parallel.get("median_cost_usd", 0))
        <= float(serial.get("median_cost_usd", 0)) * 1.01
    )
    artifact = {
        "schema_version": "1.0",
        "classification": (
            "PROVEN" if quality_ok and cost_ok and speedup > 1 else "INCONCLUSIVE"
        ),
        "scope": (
            "live provider overlap through production run_supervisor_once; "
            "no queue mutation or publication"
        ),
        "request_shape": {
            "maximum_calls": 55,
            "max_parallel_workers": 3,
            "max_output_tokens": _MAX_OUTPUT_TOKENS,
        },
        "preflight": preflight,
        "summary": summaries,
        "comparison": {
            "speedup_ratio": round(speedup, 4),
            "speedup_percent": round((speedup - 1) * 100, 2),
            "quality_non_regression": quality_ok,
            "cost_non_regression": cost_ok,
        },
        "samples": samples,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(artifact["comparison"], sort_keys=True))


if __name__ == "__main__":
    main()
