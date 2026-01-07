from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

from src.contracts.costs import (
    CostLedgerAppendRequest,
    CostLedgerAppendResponse,
    CostRollupRequest,
    CostRollupResponse,
    DailyCostTotal,
)
from src.contracts.run_context import RunContext
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.cost_ledger_service")


def append_entry(request: CostLedgerAppendRequest, ctx: RunContext) -> CostLedgerAppendResponse:
    path = Path(request.path)
    path.parent.mkdir(parents=True, exist_ok=True)
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
    totals: Dict[str, DailyCostTotal] = {}
    logger.info(log_event(
        ctx,
        role="service",
        event="cost_ledger_rollup_start",
        module=logger.name,
        fields={"ledger_path": str(ledger_path), "out_path": str(out_path)},
    ))
    if ledger_path.exists():
        agg = defaultdict(lambda: {"total_usd": 0.0, "input_tokens": 0, "output_tokens": 0, "tool_calls": 0})
        with ledger_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = row.get("timestamp_utc")
                try:
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00")) if ts else None
                except ValueError:
                    dt = None
                day_key = dt.date().isoformat() if dt else "unknown"
                agg[day_key]["total_usd"] += float(row.get("estimated_cost_usd", 0.0))
                agg[day_key]["input_tokens"] += int(row.get("input_tokens", 0) or 0)
                agg[day_key]["output_tokens"] += int(row.get("output_tokens", 0) or 0)
                agg[day_key]["tool_calls"] += int(row.get("tool_calls", 0) or 0)
        totals = {
            day: DailyCostTotal(
                schema_version="1.0",
                date_utc=day,
                total_usd=round(metrics["total_usd"], 6),
                input_tokens=metrics["input_tokens"],
                output_tokens=metrics["output_tokens"],
                tool_calls=metrics["tool_calls"],
            )
            for day, metrics in sorted(agg.items())
        }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    serialized = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "totals": {day: total.__dict__ for day, total in totals.items()},
    }
    out_path.write_text(json.dumps(serialized, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(log_event(
        ctx,
        role="service",
        event="cost_ledger_rollup_complete",
        module=logger.name,
        fields={"out_path": str(out_path), "days": len(totals)},
    ))
    return CostRollupResponse(schema_version="1.0", out_path=str(out_path), totals=totals)
