"""Build a bounded, read-only effectiveness view from recovery telemetry."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any

_CURRENT_EVENT = "structured_output_recovery_outcome"
_LEGACY_EVENT = "structured_output_attempt"
_UNKNOWN = "unavailable"


def _event_records(
    paths: Iterable[Path], *, run_id: str | None = None
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in paths:
        with path.open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                start = line.find("{")
                if start < 0:
                    continue
                try:
                    record = json.loads(line[start:])
                except json.JSONDecodeError:
                    continue
                if record.get("event") not in {_CURRENT_EVENT, _LEGACY_EVENT}:
                    continue
                if run_id is not None and record.get("run_id") != run_id:
                    continue
                records.append(record)
    return records


def _context_key(record: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(record.get("run_id") or ""),
        str(record.get("task_id") or ""),
        str(record.get("span_id") or ""),
    )


def _current_outcomes(
    records: Iterable[dict[str, Any]],
) -> tuple[list[dict[str, Any]], set[tuple[str, str, str]]]:
    outcomes: dict[str, dict[str, Any]] = {}
    contexts: set[tuple[str, str, str]] = set()
    for record in records:
        if record.get("event") != _CURRENT_EVENT:
            continue
        fields = dict(record.get("fields") or {})
        outcome_id = str(fields.get("outcome_id") or "")
        if not outcome_id or outcome_id in outcomes:
            continue
        contexts.add(_context_key(record))
        strategy = str(fields.get("repair_strategy") or _UNKNOWN)
        outcomes[outcome_id] = {
            "source": "current",
            "workflow": str(fields.get("workflow") or _UNKNOWN),
            "prompt_model_family": str(
                fields.get("prompt_namespace")
                or fields.get("artifact_family")
                or _UNKNOWN
            ),
            "schema_name": str(fields.get("schema_name") or _UNKNOWN),
            "provider_model": str(fields.get("provider_model") or _UNKNOWN),
            "failure_reason": str(fields.get("failure_reason") or ""),
            "repair_strategy": strategy,
            "retry_attempt": _integer(fields.get("retry_attempt")),
            "provider_attempts": max(1, _integer(fields.get("provider_attempts"))),
            "repair_input_tokens": _integer(fields.get("repair_input_tokens")),
            "repair_output_tokens": _integer(fields.get("repair_output_tokens")),
            "repair_cost_usd": _number(fields.get("repair_cost_usd")),
            "elapsed_repair_ms": _number(fields.get("elapsed_repair_ms")),
            "terminal": str(fields.get("terminal") or "failure"),
            "first_pass_valid": _flag(
                fields, "first_pass_valid", strategy == "first_pass"
            ),
            "deterministic_repair_attempted": _flag(
                fields,
                "deterministic_repair_attempted",
                strategy not in {"first_pass", "provider_error"},
            ),
            "deterministic_repair_succeeded": _flag(
                fields,
                "deterministic_repair_succeeded",
                strategy == "deterministic_repair",
            ),
            "model_repair_attempted": _flag(
                fields,
                "model_repair_attempted",
                _integer(fields.get("provider_attempts")) > 1,
            ),
            "model_repair_succeeded": _flag(
                fields, "model_repair_succeeded", strategy == "model_repair"
            ),
        }
    return list(outcomes.values()), contexts


def _legacy_outcomes(
    records: Iterable[dict[str, Any]], contexts_with_current: set[tuple[str, str, str]]
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str, str, str], list[dict[str, Any]]] = defaultdict(
        list
    )
    for record in records:
        if (
            record.get("event") != _LEGACY_EVENT
            or _context_key(record) in contexts_with_current
        ):
            continue
        fields = dict(record.get("fields") or {})
        grouped[
            _context_key(record)
            + (
                str(fields.get("report_id") or ""),
                str(fields.get("artifact_family") or ""),
            )
        ].append(fields)

    outcomes: list[dict[str, Any]] = []
    for events in grouped.values():
        terminal = events[-1]
        disposition = str(terminal.get("final_disposition") or "")
        strategy = {
            "generated": "first_pass",
            "abstained": "first_pass",
            "deterministic_repair": "deterministic_repair",
            "model_repair": "model_repair",
            "regeneration": "regeneration",
            "recovery_exhausted": "retry_exhaustion",
        }.get(disposition, "terminal_failure")
        repair_events = [
            event for event in events if _integer(event.get("attempt")) > 0
        ]
        outcomes.append(
            {
                "source": "legacy",
                "workflow": _UNKNOWN,
                "prompt_model_family": str(
                    events[-1].get("artifact_family") or _UNKNOWN
                ),
                "schema_name": _UNKNOWN,
                "provider_model": _UNKNOWN,
                "failure_reason": str(terminal.get("error_class") or ""),
                "repair_strategy": strategy,
                "retry_attempt": max(
                    (_integer(event.get("attempt")) for event in events), default=0
                ),
                "provider_attempts": max(
                    (_integer(event.get("attempt")) + 1 for event in events), default=1
                ),
                "repair_input_tokens": sum(
                    _integer(event.get("input_tokens")) for event in repair_events
                ),
                "repair_output_tokens": sum(
                    _integer(event.get("output_tokens")) for event in repair_events
                ),
                "repair_cost_usd": sum(
                    _number(event.get("cost_usd") or event.get("cost"))
                    for event in repair_events
                ),
                "elapsed_repair_ms": None,
                "terminal": "failure"
                if strategy in {"retry_exhaustion", "terminal_failure"}
                else "success",
                "first_pass_valid": strategy == "first_pass",
                "deterministic_repair_attempted": strategy
                not in {
                    "first_pass",
                    "provider_error",
                },
                "deterministic_repair_succeeded": strategy == "deterministic_repair",
                "model_repair_attempted": strategy
                in {"model_repair", "regeneration", "retry_exhaustion"},
                "model_repair_succeeded": strategy == "model_repair",
            }
        )
    return outcomes


def _integer(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _number(value: Any) -> float:
    try:
        return max(0.0, float(value or 0))
    except (TypeError, ValueError):
        return 0.0


def _flag(fields: dict[str, Any], name: str, default: bool) -> bool:
    value = fields.get(name)
    return value if isinstance(value, bool) else default


def build_report(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate records deterministically without reading runtime state."""

    source_records = list(records)
    current, current_contexts = _current_outcomes(source_records)
    outcomes = current + _legacy_outcomes(source_records, current_contexts)
    output_count = len(outcomes)

    def count(name: str) -> int:
        return sum(bool(outcome[name]) for outcome in outcomes)

    terminal_failures = sum(outcome["terminal"] == "failure" for outcome in outcomes)
    model_repair_attempts = count("model_repair_attempted")
    model_repair_successes = count("model_repair_succeeded")
    deterministic_repair_attempts = count("deterministic_repair_attempted")
    deterministic_repair_successes = count("deterministic_repair_succeeded")
    repair_attempts = sum(
        max(0, outcome["provider_attempts"] - 1) for outcome in outcomes
    )
    elapsed_values = [
        float(outcome["elapsed_repair_ms"])
        for outcome in outcomes
        if outcome["elapsed_repair_ms"] is not None
    ]
    metrics = {
        "output_count": output_count,
        "first_pass_valid_rate": _rate(count("first_pass_valid"), output_count),
        "deterministic_repair_success_rate": _rate(
            deterministic_repair_successes, deterministic_repair_attempts
        ),
        "model_repair_success_rate": _rate(
            model_repair_successes, model_repair_attempts
        ),
        "terminal_failure_rate": _rate(terminal_failures, output_count),
        "repair_attempts_per_output": _rate(repair_attempts, output_count),
        "repair_input_tokens": sum(
            outcome["repair_input_tokens"] for outcome in outcomes
        ),
        "repair_output_tokens": sum(
            outcome["repair_output_tokens"] for outcome in outcomes
        ),
        "repair_estimated_cost_usd": round(
            sum(outcome["repair_cost_usd"] for outcome in outcomes), 6
        ),
        "elapsed_repair_ms": round(sum(elapsed_values), 3),
    }
    groups = _groups(outcomes)
    return {
        "schema_version": "1.0",
        "metrics": metrics,
        "availability": {
            "legacy_attribution": "partial"
            if any(o["source"] == "legacy" for o in outcomes)
            else "available",
            "elapsed_repair_ms": "partial"
            if len(elapsed_values) != output_count
            else "available",
        },
        "groups": groups,
    }


def _rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _groups(outcomes: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str, str, str, str, int], list[dict[str, Any]]] = (
        defaultdict(list)
    )
    for outcome in outcomes:
        grouped[
            (
                outcome["workflow"],
                outcome["prompt_model_family"],
                outcome["schema_name"],
                outcome["provider_model"],
                outcome["failure_reason"],
                outcome["repair_strategy"],
                outcome["retry_attempt"],
            )
        ].append(outcome)
    return [
        {
            "workflow": key[0],
            "prompt_model_family": key[1],
            "schema_name": key[2],
            "provider_model": key[3],
            "failure_reason": key[4],
            "repair_strategy": key[5],
            "retry_attempt": key[6],
            "output_count": len(rows),
            "terminal_failure_count": sum(row["terminal"] == "failure" for row in rows),
            "repair_input_tokens": sum(row["repair_input_tokens"] for row in rows),
            "repair_output_tokens": sum(row["repair_output_tokens"] for row in rows),
            "repair_estimated_cost_usd": round(
                sum(row["repair_cost_usd"] for row in rows), 6
            ),
            "elapsed_repair_ms": round(
                sum(float(row["elapsed_repair_ms"] or 0) for row in rows), 3
            ),
        }
        for key, rows in sorted(grouped.items())
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", action="append", type=Path, required=True)
    parser.add_argument(
        "--run-id",
        help="Include only recovery events emitted by this workflow run.",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = build_report(_event_records(args.log, run_id=args.run_id))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
