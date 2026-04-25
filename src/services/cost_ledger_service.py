from __future__ import annotations

import json
import logging
import hashlib
import threading
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

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
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.cost_ledger_service")
_LEDGER_LOCK = threading.Lock()


def _raise_cost_report_validation_error(
    *, code: str, message: str, context: dict[str, Any] | None = None
) -> None:
    raise AppError(
        code=code,
        message=message,
        retryable=False,
        context=context or {},
    )


def _empty_metrics() -> Dict[str, float | int]:
    return {
        "estimated_cost_usd": 0.0,
        "input_tokens": 0,
        "output_tokens": 0,
        "tool_calls": 0,
    }


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


def _load_rows_from_offset(path: Path, offset: int) -> List[dict]:
    if not path.exists():
        return []
    rows: List[dict] = []
    with path.open("rb") as f:
        f.seek(max(0, offset))
        for line in f:
            chunk = line.strip()
            if not chunk:
                continue
            try:
                row = json.loads(chunk.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            rows.append(row)
    return rows


def _file_sha256(path: Path) -> str:
    if not path.exists():
        return ""
    hasher = hashlib.sha256()
    with path.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


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
        estimated_cost_usd=round(
            float(metrics.get("estimated_cost_usd", 0.0) or 0.0), 6
        ),
    )


def _metrics_from_cost_totals(total: CostTotals) -> Dict[str, float | int]:
    return {
        "estimated_cost_usd": float(total.estimated_cost_usd or 0.0),
        "input_tokens": int(total.total_input_tokens or 0),
        "output_tokens": int(total.total_output_tokens or 0),
        "tool_calls": int(total.total_tool_calls or 0),
    }


def _metrics_from_daily_total(total: DailyCostTotal) -> Dict[str, float | int]:
    return {
        "estimated_cost_usd": float(total.total_usd or 0.0),
        "input_tokens": int(total.input_tokens or 0),
        "output_tokens": int(total.output_tokens or 0),
        "tool_calls": int(total.tool_calls or 0),
    }


def _daily_total_from_metrics(
    day: str, metrics: Dict[str, float | int]
) -> DailyCostTotal:
    return DailyCostTotal(
        schema_version="1.0",
        date_utc=day,
        total_usd=round(float(metrics.get("estimated_cost_usd", 0.0) or 0.0), 6),
        input_tokens=int(metrics.get("input_tokens", 0) or 0),
        output_tokens=int(metrics.get("output_tokens", 0) or 0),
        tool_calls=int(metrics.get("tool_calls", 0) or 0),
    )


def _build_rollup_from_metrics(
    *,
    daily_metrics: Dict[str, Dict[str, float | int]],
    run_metrics: Dict[str, Dict[str, float | int]],
    task_metrics: Dict[str, Dict[str, float | int]],
) -> tuple[Dict[str, DailyCostTotal], Dict[str, CostTotals], Dict[str, CostTotals]]:
    totals_by_date = {
        day: _daily_total_from_metrics(day, metrics)
        for day, metrics in sorted(daily_metrics.items())
    }
    totals_by_run = {
        run_id: _to_cost_totals(metrics)
        for run_id, metrics in sorted(run_metrics.items())
    }
    totals_by_task = {
        task_id: _to_cost_totals(metrics)
        for task_id, metrics in sorted(task_metrics.items())
    }
    return totals_by_date, totals_by_run, totals_by_task


def _build_rollup_from_rows(
    rows: List[dict],
) -> tuple[Dict[str, DailyCostTotal], Dict[str, CostTotals], Dict[str, CostTotals]]:
    if not rows:
        return {}, {}, {}
    daily_agg = _aggregate_rows(rows, _date_key)
    run_agg = _aggregate_rows(rows, lambda row: str(row.get("run_id") or "unknown"))
    task_agg = _aggregate_rows(rows, lambda row: str(row.get("task_id") or "unknown"))
    return _build_rollup_from_metrics(
        daily_metrics=daily_agg,
        run_metrics=run_agg,
        task_metrics=task_agg,
    )


def _serialize_rollup(
    *,
    ledger_path: Path,
    out_path: Path,
    ledger_size_bytes: int,
    ledger_mtime_ns: int,
    ledger_sha256: str,
    totals_by_date: Dict[str, DailyCostTotal],
    totals_by_run: Dict[str, CostTotals],
    totals_by_task: Dict[str, CostTotals],
) -> dict[str, Any]:
    del out_path
    return {
        "schema_version": "1.2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ledger_state": {
            "schema_version": "1.0",
            "ledger_path": str(ledger_path),
            "size_bytes": int(ledger_size_bytes),
            "mtime_ns": int(ledger_mtime_ns),
            "sha256": ledger_sha256,
        },
        "totals": {day: total.__dict__ for day, total in totals_by_date.items()},
        "totals_by_date": {
            day: total.__dict__ for day, total in totals_by_date.items()
        },
        "totals_by_run": {
            run_id: total.__dict__ for run_id, total in totals_by_run.items()
        },
        "totals_by_task": {
            task_id: total.__dict__ for task_id, total in totals_by_task.items()
        },
    }


def _coerce_cost_totals_map(payload: Any) -> Dict[str, CostTotals]:
    if not isinstance(payload, dict):
        return {}
    totals: Dict[str, CostTotals] = {}
    for key, value in payload.items():
        if not isinstance(value, dict):
            continue
        totals[str(key)] = CostTotals(
            schema_version=str(value.get("schema_version") or "1.0"),
            total_input_tokens=int(value.get("total_input_tokens", 0) or 0),
            total_output_tokens=int(value.get("total_output_tokens", 0) or 0),
            total_tool_calls=int(value.get("total_tool_calls", 0) or 0),
            estimated_cost_usd=round(
                float(value.get("estimated_cost_usd", 0.0) or 0.0), 6
            ),
        )
    return totals


def _coerce_daily_totals_map(payload: Any) -> Dict[str, DailyCostTotal]:
    if not isinstance(payload, dict):
        return {}
    totals: Dict[str, DailyCostTotal] = {}
    for key, value in payload.items():
        if not isinstance(value, dict):
            continue
        totals[str(key)] = DailyCostTotal(
            schema_version=str(value.get("schema_version") or "1.0"),
            date_utc=str(value.get("date_utc") or key),
            total_usd=round(float(value.get("total_usd", 0.0) or 0.0), 6),
            input_tokens=int(value.get("input_tokens", 0) or 0),
            output_tokens=int(value.get("output_tokens", 0) or 0),
            tool_calls=int(value.get("tool_calls", 0) or 0),
        )
    return totals


def _log_rollup_cache_status(
    *,
    ctx: RunContext,
    out_path: Path,
    status_code: str,
    recovery_policy: str,
    detail: str = "",
) -> None:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="cost_rollup_cache_status",
            module=logger.name,
            fields={
                "artifact_kind": "cost_rollup",
                "path": str(out_path),
                "status_code": status_code,
                "recovery_policy": recovery_policy,
                "detail": detail,
            },
        )
    )


def _load_rollup_cache(out_path: Path, ctx: RunContext) -> dict[str, Any] | None:
    if not out_path.exists():
        _log_rollup_cache_status(
            ctx=ctx,
            out_path=out_path,
            status_code="missing",
            recovery_policy="full_rebuild",
        )
        return None
    try:
        data = json.loads(out_path.read_text(encoding="utf-8"))
    except OSError as exc:
        _log_rollup_cache_status(
            ctx=ctx,
            out_path=out_path,
            status_code="read_failed",
            recovery_policy="full_rebuild",
            detail=str(exc),
        )
        return None
    except json.JSONDecodeError as exc:
        _log_rollup_cache_status(
            ctx=ctx,
            out_path=out_path,
            status_code="invalid_json",
            recovery_policy="full_rebuild",
            detail=str(exc),
        )
        return None
    if not isinstance(data, dict):
        _log_rollup_cache_status(
            ctx=ctx,
            out_path=out_path,
            status_code="invalid_schema",
            recovery_policy="full_rebuild",
            detail=type(data).__name__,
        )
        return None
    ledger_state = data.get("ledger_state")
    if not isinstance(ledger_state, dict):
        _log_rollup_cache_status(
            ctx=ctx,
            out_path=out_path,
            status_code="invalid_schema",
            recovery_policy="full_rebuild",
            detail="ledger_state_missing",
        )
        return None
    totals_by_date = _coerce_daily_totals_map(
        data.get("totals_by_date") or data.get("totals")
    )
    totals_by_run = _coerce_cost_totals_map(data.get("totals_by_run"))
    totals_by_task = _coerce_cost_totals_map(data.get("totals_by_task"))
    try:
        ledger_size_bytes = int(ledger_state.get("size_bytes", 0) or 0)
        ledger_mtime_ns = int(ledger_state.get("mtime_ns", 0) or 0)
        ledger_sha256 = str(ledger_state.get("sha256") or "")
    except (TypeError, ValueError) as exc:
        _log_rollup_cache_status(
            ctx=ctx,
            out_path=out_path,
            status_code="invalid_schema",
            recovery_policy="full_rebuild",
            detail=str(exc),
        )
        return None
    return {
        "ledger_path": str(ledger_state.get("ledger_path") or ""),
        "ledger_size_bytes": ledger_size_bytes,
        "ledger_mtime_ns": ledger_mtime_ns,
        "ledger_sha256": ledger_sha256,
        "totals_by_date": totals_by_date,
        "totals_by_run": totals_by_run,
        "totals_by_task": totals_by_task,
    }


def _write_rollup_cache(
    *,
    ledger_path: Path,
    out_path: Path,
    ledger_size_bytes: int,
    ledger_mtime_ns: int,
    ledger_sha256: str,
    totals_by_date: Dict[str, DailyCostTotal],
    totals_by_run: Dict[str, CostTotals],
    totals_by_task: Dict[str, CostTotals],
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    serialized = _serialize_rollup(
        ledger_path=ledger_path,
        out_path=out_path,
        ledger_size_bytes=ledger_size_bytes,
        ledger_mtime_ns=ledger_mtime_ns,
        ledger_sha256=ledger_sha256,
        totals_by_date=totals_by_date,
        totals_by_run=totals_by_run,
        totals_by_task=totals_by_task,
    )
    out_path.write_text(
        json.dumps(serialized, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _step_totals(step_name: str, metrics: Dict[str, float | int]) -> StepCostTotal:
    return StepCostTotal(
        schema_version="1.0",
        step_name=step_name,
        total_input_tokens=int(metrics.get("input_tokens", 0) or 0),
        total_output_tokens=int(metrics.get("output_tokens", 0) or 0),
        total_tool_calls=int(metrics.get("tool_calls", 0) or 0),
        estimated_cost_usd=round(
            float(metrics.get("estimated_cost_usd", 0.0) or 0.0), 6
        ),
    )


def append_entry(
    request: CostLedgerAppendRequest, ctx: RunContext
) -> CostLedgerAppendResponse:
    path = Path(request.path)
    with _LEDGER_LOCK:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="cost_ledger_append_start",
                module=logger.name,
                fields={"path": str(path)},
            )
        )
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(request.entry.__dict__, ensure_ascii=False) + "\n")
        except Exception as exc:
            raise AppError(
                code="cost_ledger_append_failed",
                message=f"Failed to append entry to cost ledger at {path}",
                cause=exc,
                retryable=False,
                context={"path": str(path)},
            ) from exc
        logger.info(
            log_event(
                ctx,
                role="service",
                event="cost_ledger_append_complete",
                module=logger.name,
                fields={"path": str(path)},
            )
        )
        return CostLedgerAppendResponse(schema_version="1.0", path=str(path))


def rollup_daily(request: CostRollupRequest, ctx: RunContext) -> CostRollupResponse:
    ledger_path = Path(request.ledger_path)
    out_path = Path(request.out_path)
    with _LEDGER_LOCK:
        totals_by_date: Dict[str, DailyCostTotal] = {}
        totals_by_run: Dict[str, CostTotals] = {}
        totals_by_task: Dict[str, CostTotals] = {}
        mode = "full_rebuild"
        rows_processed = 0
        logger.info(
            log_event(
                ctx,
                role="service",
                event="cost_ledger_rollup_start",
                module=logger.name,
                fields={"ledger_path": str(ledger_path), "out_path": str(out_path)},
            )
        )
        try:
            cached = _load_rollup_cache(out_path, ctx)
            if ledger_path.exists():
                ledger_stat = ledger_path.stat()
                ledger_size_bytes = int(ledger_stat.st_size)
                ledger_mtime_ns = int(
                    getattr(
                        ledger_stat,
                        "st_mtime_ns",
                        int(ledger_stat.st_mtime * 1_000_000_000),
                    )
                )
                ledger_sha256 = _file_sha256(ledger_path)
            else:
                ledger_size_bytes = 0
                ledger_mtime_ns = 0
                ledger_sha256 = ""

            if (
                cached
                and cached["ledger_path"] == str(ledger_path)
                and ledger_size_bytes == cached["ledger_size_bytes"]
                and ledger_mtime_ns == cached["ledger_mtime_ns"]
                and ledger_sha256 == cached["ledger_sha256"]
            ):
                totals_by_date = cached["totals_by_date"]
                totals_by_run = cached["totals_by_run"]
                totals_by_task = cached["totals_by_task"]
                mode = "cached"
            elif (
                cached
                and cached["ledger_path"] == str(ledger_path)
                and ledger_size_bytes > cached["ledger_size_bytes"]
                and ledger_mtime_ns >= cached["ledger_mtime_ns"]
            ):
                appended_rows = _load_rows_from_offset(
                    ledger_path, cached["ledger_size_bytes"]
                )
                rows_processed = len(appended_rows)
                daily_metrics = {
                    day: _metrics_from_daily_total(total)
                    for day, total in cached["totals_by_date"].items()
                }
                run_metrics = {
                    run_id: _metrics_from_cost_totals(total)
                    for run_id, total in cached["totals_by_run"].items()
                }
                task_metrics = {
                    task_id: _metrics_from_cost_totals(total)
                    for task_id, total in cached["totals_by_task"].items()
                }
                for row in appended_rows:
                    day_key = _date_key(row) or "unknown"
                    _update_metrics(
                        daily_metrics.setdefault(day_key, _empty_metrics()), row
                    )
                    run_key = str(row.get("run_id") or "unknown")
                    _update_metrics(
                        run_metrics.setdefault(run_key, _empty_metrics()), row
                    )
                    task_key = str(row.get("task_id") or "unknown")
                    _update_metrics(
                        task_metrics.setdefault(task_key, _empty_metrics()), row
                    )
                totals_by_date, totals_by_run, totals_by_task = (
                    _build_rollup_from_metrics(
                        daily_metrics=daily_metrics,
                        run_metrics=run_metrics,
                        task_metrics=task_metrics,
                    )
                )
                _write_rollup_cache(
                    ledger_path=ledger_path,
                    out_path=out_path,
                    ledger_size_bytes=ledger_size_bytes,
                    ledger_mtime_ns=ledger_mtime_ns,
                    ledger_sha256=ledger_sha256,
                    totals_by_date=totals_by_date,
                    totals_by_run=totals_by_run,
                    totals_by_task=totals_by_task,
                )
                mode = "incremental"
            else:
                if cached and cached["ledger_path"] != str(ledger_path):
                    _log_rollup_cache_status(
                        ctx=ctx,
                        out_path=out_path,
                        status_code="key_mismatch",
                        recovery_policy="full_rebuild",
                        detail="ledger_path",
                    )
                rows = _load_rows(ledger_path)
                rows_processed = len(rows)
                totals_by_date, totals_by_run, totals_by_task = _build_rollup_from_rows(
                    rows
                )
                _write_rollup_cache(
                    ledger_path=ledger_path,
                    out_path=out_path,
                    ledger_size_bytes=ledger_size_bytes,
                    ledger_mtime_ns=ledger_mtime_ns,
                    ledger_sha256=ledger_sha256,
                    totals_by_date=totals_by_date,
                    totals_by_run=totals_by_run,
                    totals_by_task=totals_by_task,
                )
        except Exception as exc:
            raise AppError(
                code="cost_ledger_rollup_failed",
                message=f"Failed to roll up cost ledger from {ledger_path} to {out_path}",
                cause=exc,
                retryable=False,
                context={"ledger_path": str(ledger_path), "out_path": str(out_path)},
            ) from exc
        logger.info(
            log_event(
                ctx,
                role="service",
                event="cost_ledger_rollup_complete",
                module=logger.name,
                fields={
                    "out_path": str(out_path),
                    "days": len(totals_by_date),
                    "runs": len(totals_by_run),
                    "tasks": len(totals_by_task),
                    "mode": mode,
                    "rows_processed": rows_processed,
                },
            )
        )
        return CostRollupResponse(
            schema_version="1.1",
            out_path=str(out_path),
            totals_by_date=totals_by_date,
            totals_by_run=totals_by_run,
            totals_by_task=totals_by_task,
        )


def generate_cost_report(
    request: CostReportRequest, ctx: RunContext
) -> CostReportResponse:
    with _LEDGER_LOCK:
        ledger_path = Path(request.ledger_path)
        if (request.date_utc and request.run_id) or (
            not request.date_utc and not request.run_id
        ):
            _raise_cost_report_validation_error(
                code="cost_report_filter_invalid",
                message="Provide exactly one of date_utc or run_id for cost reporting.",
                context={
                    "date_utc": request.date_utc or "",
                    "run_id": request.run_id or "",
                },
            )
        if request.top_n <= 0:
            _raise_cost_report_validation_error(
                code="cost_report_top_n_invalid",
                message="top_n must be greater than zero.",
                context={"top_n": request.top_n},
            )

        logger.info(
            log_event(
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
            )
        )

        rows = _load_rows(ledger_path)
        filtered: List[dict] = []
        filter_type = "date" if request.date_utc else "run_id"
        filter_value = request.date_utc or request.run_id or ""
        if request.date_utc:
            try:
                target_date = datetime.fromisoformat(request.date_utc).date()
            except ValueError as exc:
                raise AppError(
                    code="cost_report_date_invalid",
                    message="date_utc must be YYYY-MM-DD",
                    cause=exc,
                    retryable=False,
                    context={"date_utc": request.date_utc},
                ) from exc
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
        step_agg = _aggregate_rows(
            filtered, lambda row: str(row.get("step_name") or "unknown")
        )
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
        logger.info(
            log_event(
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
            )
        )
        return response
