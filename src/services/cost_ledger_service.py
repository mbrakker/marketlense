from __future__ import annotations

import json
import logging
import threading
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from src.contracts.costs import (
    CostLedgerAppendRequest,
    CostLedgerAppendResponse,
    CostReportRequest,
    CostReportResponse,
    CostRollupRequest,
    CostRollupResponse,
    CostTotals,
    DailyCostTotal,
    StepCostTotal,
)
from src.contracts.run_context import RunContext
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.cost_ledger_service")
_LEDGER_LOCK = threading.Lock()


def _empty_metrics() -> Dict[str, float | int]:
    return {"estimated_cost_usd": 0.0, "input_tokens": 0, "output_tokens": 0, "tool_calls": 0}


def _update_metrics(metrics: Dict[str, float | int], row: dict) -> None:
    metrics["estimated_cost_usd"] += float(row.get("estimated_cost_usd", 0.0) or 0.0)
    metrics["input_tokens"] += int(row.get("input_tokens", 0) or 0)
    metrics["output_tokens"] += int(row.get("output_tokens", 0) or 0)
    metrics["tool_calls"] += int(row.get("tool_calls", 0) or 0)


def _load_rows(path: Path) -> List[dict]:
    if not path.exists():
        return []
    rows: List[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            rows.append(row)
    return rows


def _date_key(row: dict) -> str | None:
    ts = row.get("timestamp_utc")
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.date().isoformat()


def _aggregate_rows(rows: List[dict], key_func) -> Dict[str, Dict[str, float | int]]:
    agg: Dict[str, Dict[str, float | int]] = defaultdict(_empty_metrics)
    for row in rows:
        key = key_func(row) or "unknown"
        metrics = agg[key]
        _update_metrics(metrics, row)
    return agg


def _to_cost_totals(metrics: Dict[str, float | int]) -> CostTotals:
    return CostTotals(
        schema_version="1.0",
        total_input_tokens=int(metrics.get("input_tokens", 0) or 0),
        total_output_tokens=int(metrics.get("output_tokens", 0) or 0),
        total_tool_calls=int(metrics.get("tool_calls", 0) or 0),
        estimated_cost_usd=round(float(metrics.get("estimated_cost_usd", 0.0) or 0.0), 6),
    )


def _step_totals(step_name: str, metrics: Dict[str, float | int]) -> StepCostTotal:
    return StepCostTotal(
        schema_version="1.0",
        step_name=step_name,
        total_input_tokens=int(metrics.get("input_tokens", 0) or 0),
        total_output_tokens=int(metrics.get("output_tokens", 0) or 0),
        total_tool_calls=int(metrics.get("tool_calls", 0) or 0),
        estimated_cost_usd=round(float(metrics.get("estimated_cost_usd", 0.0) or 0.0), 6),
    )


def append_entry(request: CostLedgerAppendRequest, ctx: RunContext) -> CostLedgerAppendResponse:
    path = Path(request.path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _LEDGER_LOCK:
        logger.info(log_event(
            ctx,
            role="service",
            event="cost_ledger_append_start",
            module=logger.name,
            fields={"path": str(path)},
        ))
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(request.entry.__dict__, ensure_ascii=False) + "\n")
        logger.info(log_event(
            ctx,
            role="service",
            event="cost_ledger_append_complete",
            module=logger.name,
            fields={"path": str(path)},
        ))
        return CostLedgerAppendResponse(schema_version="1.0", path=str(path))


def rollup_daily(request: CostRollupRequest, ctx: RunContext) -> CostRollupResponse:
    ledger_path = Path(request.ledger_path)
    out_path = Path(request.out_path)
    with _LEDGER_LOCK:
        totals_by_date: Dict[str, DailyCostTotal] = {}
        totals_by_run: Dict[str, CostTotals] = {}
        totals_by_task: Dict[str, CostTotals] = {}
        logger.info(log_event(
            ctx,
            role="service",
            event="cost_ledger_rollup_start",
            module=logger.name,
            fields={"ledger_path": str(ledger_path), "out_path": str(out_path)},
        ))
        rows = _load_rows(ledger_path)
        if rows:
            daily_agg = _aggregate_rows(rows, _date_key)
            run_agg = _aggregate_rows(rows, lambda row: str(row.get("run_id") or "unknown"))
            task_agg = _aggregate_rows(rows, lambda row: str(row.get("task_id") or "unknown"))
            totals_by_date = {
                day: DailyCostTotal(
                    schema_version="1.0",
                    date_utc=day,
                    total_usd=round(metrics["estimated_cost_usd"], 6),
                    input_tokens=int(metrics["input_tokens"]),
                    output_tokens=int(metrics["output_tokens"]),
                    tool_calls=int(metrics["tool_calls"]),
                )
                for day, metrics in sorted(daily_agg.items())
            }
            totals_by_run = {run_id: _to_cost_totals(metrics) for run_id, metrics in sorted(run_agg.items())}
            totals_by_task = {task_id: _to_cost_totals(metrics) for task_id, metrics in sorted(task_agg.items())}
        out_path.parent.mkdir(parents=True, exist_ok=True)
        serialized = {
            "schema_version": "1.1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "totals": {day: total.__dict__ for day, total in totals_by_date.items()},
            "totals_by_date": {day: total.__dict__ for day, total in totals_by_date.items()},
            "totals_by_run": {run_id: total.__dict__ for run_id, total in totals_by_run.items()},
            "totals_by_task": {task_id: total.__dict__ for task_id, total in totals_by_task.items()},
        }
        out_path.write_text(json.dumps(serialized, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(log_event(
            ctx,
            role="service",
            event="cost_ledger_rollup_complete",
            module=logger.name,
            fields={
                "out_path": str(out_path),
                "days": len(totals_by_date),
                "runs": len(totals_by_run),
                "tasks": len(totals_by_task),
            },
        ))
        return CostRollupResponse(
            schema_version="1.1",
            out_path=str(out_path),
            totals_by_date=totals_by_date,
            totals_by_run=totals_by_run,
            totals_by_task=totals_by_task,
        )


def generate_cost_report(request: CostReportRequest, ctx: RunContext) -> CostReportResponse:
    with _LEDGER_LOCK:
        ledger_path = Path(request.ledger_path)
        if (request.date_utc and request.run_id) or (not request.date_utc and not request.run_id):
            raise ValueError("Provide exactly one of date_utc or run_id for cost reporting.")
        if request.top_n <= 0:
            raise ValueError("top_n must be greater than zero.")

        logger.info(log_event(
            ctx,
            role="service",
            event="cost_report_generate_start",
            module=logger.name,
            fields={
                "ledger_path": str(ledger_path),
                "date_utc": request.date_utc,
                "run_id": request.run_id,
                "top_n": request.top_n,
            },
        ))

        rows = _load_rows(ledger_path)
        filtered: List[dict] = []
        filter_type = "date" if request.date_utc else "run_id"
        filter_value = request.date_utc or request.run_id or ""
        if request.date_utc:
            try:
                target_date = datetime.fromisoformat(request.date_utc).date()
            except ValueError as exc:
                raise ValueError("date_utc must be YYYY-MM-DD") from exc
            for row in rows:
                day = _date_key(row)
                if day and day == target_date.isoformat():
                    filtered.append(row)
        else:
            for row in rows:
                if str(row.get("run_id") or "") == str(request.run_id):
                    filtered.append(row)

        totals_metrics = _empty_metrics()
        for row in filtered:
            _update_metrics(totals_metrics, row)
        step_agg = _aggregate_rows(filtered, lambda row: str(row.get("step_name") or "unknown"))
        top_steps = sorted(
            (_step_totals(name, metrics) for name, metrics in step_agg.items()),
            key=lambda t: (-t.estimated_cost_usd, t.step_name),
        )[: request.top_n]

        response = CostReportResponse(
            schema_version="1.0",
            filter_type=filter_type,
            filter_value=str(filter_value),
            totals=_to_cost_totals(totals_metrics),
            top_steps=top_steps,
            matched_entries=len(filtered),
        )
        logger.info(log_event(
            ctx,
            role="service",
            event="cost_report_generate_complete",
            module=logger.name,
            fields={
                "filter_type": filter_type,
                "filter_value": filter_value,
                "matched_entries": len(filtered),
                "top_steps": len(top_steps),
            },
        ))
        return response
