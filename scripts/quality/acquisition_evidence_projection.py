"""Build committed, sanitized views of a retained acquisition replay.

This utility is deliberately read-only with respect to acquisition state.  It
projects only scalar evidence from an existing JSONL replay and its baseline;
URLs, browser artefact paths, route prose, and identity values are omitted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0"
_NON_ACTIONABLE_RESOURCE_REASONS = {
    "",
    "failed",
    "inferred",
    "observed",
    "success",
    "verified",
}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError("JSONL evidence records must be objects")
            records.append(payload)
    return records


def _read_baseline(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload.get("records") if isinstance(payload, dict) else None
    if not isinstance(records, list) or not all(
        isinstance(record, dict) for record in records
    ):
        raise ValueError("Baseline evidence must contain an object records list")
    return records


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _mapping(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _number(value: object) -> int | float:
    return value if isinstance(value, (int, float)) else 0


def _resource_totals(record: dict[str, Any]) -> dict[str, int | float]:
    totals: dict[str, int | float] = {
        "browser_launches": 0,
        "agent_calls": 0,
        "input": 0,
        "cached_input": 0,
        "output": 0,
        "cost_usd": 0.0,
        "mailbox_reads": 0,
    }
    resources = record.get("resource_attempts")
    for resource in resources if isinstance(resources, list) else []:
        if not isinstance(resource, dict):
            continue
        totals["browser_launches"] += int(_number(resource.get("browser_launches")))
        totals["agent_calls"] += int(_number(resource.get("browser_model_calls")))
        totals["input"] += int(_number(resource.get("input_tokens")))
        totals["cached_input"] += int(_number(resource.get("cached_input_tokens")))
        totals["output"] += int(_number(resource.get("output_tokens")))
        totals["cost_usd"] += float(_number(resource.get("estimated_cost_usd")))
        totals["mailbox_reads"] += int(_number(resource.get("mailbox_reads")))
    totals["cost_usd"] = round(float(totals["cost_usd"]), 6)
    return totals


def _route(record: dict[str, Any]) -> str:
    result = _mapping(record.get("acquisition_result"))
    route = str(result.get("route_family") or "").strip()
    if route:
        return route
    resources = record.get("resource_attempts")
    if isinstance(resources, list):
        for resource in resources:
            if isinstance(resource, dict) and str(resource.get("route_family") or ""):
                return str(resource["route_family"])
    return "unresolved"


def _terminal_reason(record: dict[str, Any]) -> str:
    error_code = str(_mapping(record.get("acquisition_error")).get("error_code") or "")
    if error_code:
        return error_code
    resources = record.get("resource_attempts")
    if isinstance(resources, list):
        for resource in resources:
            if not isinstance(resource, dict):
                continue
            reason = str(resource.get("terminal_reason") or "")
            if reason.casefold() not in _NON_ACTIONABLE_RESOURCE_REASONS:
                return reason
    outcome = str(_mapping(record.get("acquisition_result")).get("outcome") or "")
    if outcome:
        return outcome
    return "unknown"


def sanitize_record(record: dict[str, Any]) -> dict[str, Any]:
    """Return the public scalar projection for one retained attempt."""
    verification = _mapping(record.get("artifact_verification"))
    resources = _resource_totals(record)
    return {
        "candidate_id": str(record.get("failure_candidate_id") or ""),
        "publisher_id": str(record.get("publisher_id") or ""),
        "tested_commit": str(record.get("producer_git_sha") or ""),
        "configuration_hash": str(record.get("configuration_hash") or ""),
        "route": _route(record),
        "terminal_reason": _terminal_reason(record),
        "verified_artifact": bool(verification.get("verified_usable_artifact")),
        "source_kind": str(verification.get("source_kind") or "unknown"),
        "retained_format": str(verification.get("retained_artifact_format") or "none"),
        "duration_seconds": round(float(_number(record.get("duration_seconds"))), 3),
        "browser_launches": resources["browser_launches"],
        "agent_calls": resources["agent_calls"],
        "tokens": {
            "input": resources["input"],
            "cached_input": resources["cached_input"],
            "output": resources["output"],
        },
        "cost_usd": resources["cost_usd"],
        "mailbox_reads": resources["mailbox_reads"],
        "drive_persistence": bool(verification.get("drive_persisted")),
    }


def _metrics(attempts: list[dict[str, Any]]) -> dict[str, int | float]:
    verified = [item for item in attempts if item["verified_artifact"]]
    return {
        "attempted_reports": len(attempts),
        "verified_acquisitions": len(verified),
        "acquisition_success_rate": round(
            len(verified) / len(attempts) if attempts else 0.0, 6
        ),
        "agent_reports": sum(1 for item in attempts if item["agent_calls"] > 0),
        "agent_calls": sum(int(item["agent_calls"]) for item in attempts),
        "input_tokens": sum(int(item["tokens"]["input"]) for item in attempts),
        "cached_input_tokens": sum(
            int(item["tokens"]["cached_input"]) for item in attempts
        ),
        "output_tokens": sum(int(item["tokens"]["output"]) for item in attempts),
        "browser_launches": sum(int(item["browser_launches"]) for item in attempts),
        "total_cost_usd": round(sum(float(item["cost_usd"]) for item in attempts), 6),
        "duration_seconds": round(
            sum(float(item["duration_seconds"]) for item in attempts), 3
        ),
        "mailbox_reads": sum(int(item["mailbox_reads"]) for item in attempts),
        "drive_persisted": sum(1 for item in attempts if item["drive_persistence"]),
    }


def _failure_pareto(attempts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for attempt in attempts:
        if not attempt["verified_artifact"]:
            grouped[str(attempt["terminal_reason"])].append(attempt)
    return [
        {
            "terminal_reason": reason,
            "candidate_count": len(items),
            "duration_seconds": round(
                sum(float(item["duration_seconds"]) for item in items), 3
            ),
            "browser_launches": sum(int(item["browser_launches"]) for item in items),
            "agent_calls": sum(int(item["agent_calls"]) for item in items),
            "cost_usd": round(sum(float(item["cost_usd"]) for item in items), 6),
        }
        for reason, items in sorted(
            grouped.items(), key=lambda item: (-len(item[1]), item[0])
        )
    ]


def _route_metrics(attempts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for attempt in attempts:
        grouped[str(attempt["route"])].append(attempt)
    return [
        {"route": route, **_metrics(items)}
        for route, items in sorted(grouped.items())
    ]


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def build_projection(
    *,
    current_jsonl: Path,
    baseline_json: Path,
    output_dir: Path,
    expected_current_sha256: str = "",
) -> dict[str, Any]:
    current_sha256 = _sha256(current_jsonl)
    baseline_sha256 = _sha256(baseline_json)
    if (
        expected_current_sha256
        and current_sha256.casefold() != expected_current_sha256.casefold()
    ):
        raise ValueError("Current JSONL SHA-256 does not match the expected hash")
    current_attempts = sorted(
        (sanitize_record(record) for record in _read_jsonl(current_jsonl)),
        key=lambda item: item["candidate_id"],
    )
    baseline_attempts = sorted(
        (sanitize_record(record) for record in _read_baseline(baseline_json)),
        key=lambda item: item["candidate_id"],
    )
    current_ids = [item["candidate_id"] for item in current_attempts]
    baseline_ids = [item["candidate_id"] for item in baseline_attempts]
    if not all(current_ids) or len(set(current_ids)) != len(current_ids):
        raise ValueError("Current evidence contains missing or duplicate candidate IDs")
    if not all(baseline_ids) or len(set(baseline_ids)) != len(baseline_ids):
        raise ValueError(
            "Baseline evidence contains missing or duplicate candidate IDs"
        )
    current_metrics = _metrics(current_attempts)
    baseline_metrics = _metrics(baseline_attempts)
    projection = {
        "schema_version": SCHEMA_VERSION,
        "attempts": current_attempts,
        "failure_pareto": _failure_pareto(current_attempts),
        "route_metrics": _route_metrics(current_attempts),
        "before_after": {
            "baseline": baseline_metrics,
            "current": current_metrics,
            "change": {
                key: round(
                    float(current_metrics[key]) - float(baseline_metrics[key]), 6
                )
                for key in current_metrics
            },
        },
        "remaining_failures": [
            item for item in current_attempts if not item["verified_artifact"]
        ],
        "consistency": {
            "current_jsonl_sha256": current_sha256,
            "baseline_json_sha256": baseline_sha256,
            "expected_current_jsonl_sha256": expected_current_sha256,
            "expected_current_hash_matches": bool(expected_current_sha256),
            "candidate_sets_match": current_ids == baseline_ids,
            "current_candidate_count": len(current_attempts),
            "baseline_candidate_count": len(baseline_attempts),
            "current_failures_match_metrics": len(
                projection_failures := [
                    item for item in current_attempts if not item["verified_artifact"]
                ]
            )
            == len(current_attempts) - int(current_metrics["verified_acquisitions"]),
            "remaining_failure_count": len(projection_failures),
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / "acquisition_evidence_projection.json", projection)
    _write_json(output_dir / "sanitized_attempts.json", current_attempts)
    _write_json(output_dir / "failure_pareto.json", projection["failure_pareto"])
    _write_json(output_dir / "route_metrics.json", projection["route_metrics"])
    _write_json(output_dir / "before_after.json", projection["before_after"])
    _write_json(
        output_dir / "remaining_failures.json", projection["remaining_failures"]
    )
    _write_json(output_dir / "consistency.json", projection["consistency"])
    return projection


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current-jsonl", required=True)
    parser.add_argument("--baseline-json", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--expected-current-sha256", default="")
    args = parser.parse_args()
    projection = build_projection(
        current_jsonl=Path(args.current_jsonl),
        baseline_json=Path(args.baseline_json),
        output_dir=Path(args.output_dir),
        expected_current_sha256=args.expected_current_sha256,
    )
    print(
        json.dumps(
            {
                "attempt_count": len(projection["attempts"]),
                "remaining_failure_count": len(projection["remaining_failures"]),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
