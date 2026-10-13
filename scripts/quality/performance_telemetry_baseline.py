"""Compare bounded performance artifacts without masking quality or cost regressions."""

from __future__ import annotations

import argparse
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


def compare_artifacts(
    *, baseline: dict[str, Any], candidate: dict[str, Any]
) -> dict[str, Any]:
    """Return a deterministic before/after decision for compatible artifacts."""

    reasons: list[str] = []
    baseline_profile = str(baseline.get("measurement_profile_hash") or "")
    candidate_profile = str(candidate.get("measurement_profile_hash") or "")
    if not baseline_profile or baseline_profile != candidate_profile:
        reasons.append("incomparable_measurement_profile")
    ci_workflow_profile = candidate_profile == "ci:pytest-and-quality-gates:v2"
    duration_field = (
        "workflow_elapsed_ms" if ci_workflow_profile else "total_run_duration_ms"
    )
    if ci_workflow_profile and (
        baseline.get("workflow_timing_status") != "completed_github_actions_timestamps"
        or candidate.get("workflow_timing_status")
        != "completed_github_actions_timestamps"
    ):
        reasons.append("workflow_timing_not_completed")
    baseline_duration = _non_negative_int(baseline.get(duration_field))
    candidate_duration = _non_negative_int(candidate.get(duration_field))
    if baseline_duration is None or candidate_duration is None:
        reasons.append("duration_unavailable")
    baseline_critical_path = (
        _non_negative_int(baseline.get("workflow_critical_path_ms"))
        if ci_workflow_profile
        else None
    )
    candidate_critical_path = (
        _non_negative_int(candidate.get("workflow_critical_path_ms"))
        if ci_workflow_profile
        else None
    )
    critical_path_delta = (
        candidate_critical_path - baseline_critical_path
        if baseline_critical_path is not None and candidate_critical_path is not None
        else None
    )
    if ci_workflow_profile and critical_path_delta is None:
        reasons.append("critical_path_duration_unavailable")
    if candidate.get("quality_passed") is not True:
        reasons.append("quality_regression")
    baseline_cost = _decimal(baseline.get("estimated_cost_usd"))
    candidate_cost = _decimal(candidate.get("estimated_cost_usd"))
    if baseline_cost is None or candidate_cost is None:
        reasons.append("cost_unavailable")
    elif candidate_cost > baseline_cost:
        reasons.append("cost_regression")
    duration_delta = (
        candidate_duration - baseline_duration
        if baseline_duration is not None and candidate_duration is not None
        else None
    )
    if duration_delta is None or duration_delta >= 0:
        reasons.append("not_faster")
    return {
        "schema_version": "1.0",
        "measurement_profile_hash": candidate_profile,
        "duration_metric": duration_field,
        "duration_delta_ms": duration_delta,
        "baseline_duration_ms": baseline_duration,
        "candidate_duration_ms": candidate_duration,
        "critical_path_metric": (
            "workflow_critical_path_ms" if ci_workflow_profile else ""
        ),
        "baseline_critical_path_ms": baseline_critical_path,
        "candidate_critical_path_ms": candidate_critical_path,
        "critical_path_delta_ms": critical_path_delta,
        "baseline_estimated_cost_usd": str(baseline_cost) if baseline_cost else "",
        "candidate_estimated_cost_usd": str(candidate_cost) if candidate_cost else "",
        "quality_passed": bool(candidate.get("quality_passed")),
        "blocking_reasons": reasons,
        "speed_improvement_proven": not reasons,
    }


def _non_negative_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _decimal(value: Any) -> Decimal | None:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return parsed if parsed.is_finite() and parsed >= 0 else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare compatible MarketLense performance telemetry artifacts."
    )
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--output-json", required=True)
    args = parser.parse_args(argv)
    baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    candidate = json.loads(Path(args.candidate).read_text(encoding="utf-8"))
    result = compare_artifacts(baseline=baseline, candidate=candidate)
    output = Path(args.output_json)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0 if result["speed_improvement_proven"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
