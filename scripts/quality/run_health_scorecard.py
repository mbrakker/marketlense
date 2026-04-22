from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class RunHealthScorecard:
    schema_version: str
    run_id: str
    event_count: int
    error_count: int
    retry_count: int
    validation_failure_count: int
    cost_usd: float
    latency_seconds: float | None
    warnings: tuple[str, ...]


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _event_payloads(lines: Iterable[str]) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for line in lines:
        text = line.strip()
        if not text:
            continue
        start = text.find("{")
        if start < 0:
            continue
        try:
            payload = json.loads(text[start:])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            payloads.append(payload)
    return payloads


def build_scorecard(
    payloads: Iterable[dict[str, Any]],
    *,
    run_id: str | None = None,
    max_errors: int = 0,
    max_retries: int = 3,
    max_cost_usd: float | None = None,
) -> RunHealthScorecard:
    events = list(payloads)
    selected_run_id = str(run_id or (events[0].get("run_id") if events else "") or "")
    if selected_run_id:
        events = [
            event
            for event in events
            if str(event.get("run_id") or "") == selected_run_id
        ]

    timestamps = [
        parsed
        for parsed in (_parse_timestamp(event.get("timestamp")) for event in events)
        if parsed is not None
    ]
    fields = [
        event.get("fields") if isinstance(event.get("fields"), dict) else {}
        for event in events
    ]
    error_count = sum(
        1
        for event in events
        if str(event.get("level") or "").lower() in {"error", "critical"}
        or "error" in str(event.get("event") or "").lower()
        or str((event.get("fields") or {}).get("severity") or "").lower() == "error"
    )
    retry_count = sum(
        1 for event in events if "retry" in str(event.get("event") or "").lower()
    )
    validation_failure_count = sum(
        1
        for event in events
        if "validation" in str(event.get("event") or "").lower()
        and any(
            token in str(event.get("event") or "").lower()
            for token in ("fail", "error")
        )
    )
    cost_usd = sum(float(item.get("cost_usd") or 0.0) for item in fields)
    latency_seconds = None
    if len(timestamps) >= 2:
        latency_seconds = (max(timestamps) - min(timestamps)).total_seconds()

    warnings: list[str] = []
    if error_count > max_errors:
        warnings.append(f"error_count {error_count} exceeds {max_errors}")
    if retry_count > max_retries:
        warnings.append(f"retry_count {retry_count} exceeds {max_retries}")
    if max_cost_usd is not None and cost_usd > max_cost_usd:
        warnings.append(f"cost_usd {cost_usd:.6f} exceeds {max_cost_usd:.6f}")

    return RunHealthScorecard(
        schema_version="1.0",
        run_id=selected_run_id,
        event_count=len(events),
        error_count=error_count,
        retry_count=retry_count,
        validation_failure_count=validation_failure_count,
        cost_usd=round(cost_usd, 6),
        latency_seconds=latency_seconds,
        warnings=tuple(warnings),
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a run health scorecard from JSON logs."
    )
    parser.add_argument("log_path", help="Log file containing structured JSON events.")
    parser.add_argument("--run-id", default=None, help="Optional run_id to filter.")
    parser.add_argument("--max-errors", type=int, default=0)
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--max-cost-usd", type=float, default=None)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    path = Path(args.log_path)
    payloads = _event_payloads(path.read_text(encoding="utf-8").splitlines())
    scorecard = build_scorecard(
        payloads,
        run_id=args.run_id,
        max_errors=args.max_errors,
        max_retries=args.max_retries,
        max_cost_usd=args.max_cost_usd,
    )
    print(json.dumps(asdict(scorecard), ensure_ascii=True, indent=2, sort_keys=True))
    return 1 if scorecard.warnings else 0


if __name__ == "__main__":
    raise SystemExit(main())
