"""Run selected frozen report members through isolated production workflows."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.quality.ias_live_canary_runner import (
    preflight_frozen_cohort_member,
    run_frozen_cohort_once,
    summarize_frozen_cohort_results,
)

DEFAULT_SOURCES_MANIFEST = Path(__file__).with_name("frozen_reliability_cohort_10.json")


def _load_members(manifest_path: Path) -> list[dict[str, Any]]:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    members = payload.get("members") if isinstance(payload, dict) else None
    if not isinstance(members, list) or len(members) not in {5, 10, 20}:
        raise ValueError(
            "Frozen reliability cohort must contain exactly 5, 10, or 20 members"
        )
    root = Path(__file__).resolve().parents[2]
    required = {
        "source_path",
        "content_md5",
        "source_domain",
        "report_name",
        "landing_page_url",
        "source_page_url",
        "publisher_name",
        "downloaded_at_utc",
    }
    if any(not isinstance(item, dict) or required - set(item) for item in members):
        raise ValueError("Frozen reliability cohort has incomplete source provenance")
    if any(not str(item[key]).strip() for item in members for key in required):
        raise ValueError("Frozen reliability cohort has blank source provenance")
    if any(
        len(str(item["content_md5"])) != 32
        or any(
            character not in "0123456789abcdefABCDEF"
            for character in str(item["content_md5"])
        )
        for item in members
    ):
        raise ValueError("Frozen reliability cohort has an invalid source checksum")
    paths = [root / str(item["source_path"]) for item in members]
    if any(not path.is_file() for path in paths):
        raise ValueError("Frozen reliability cohort has a missing source artifact")
    if any(
        hashlib.md5(path.read_bytes(), usedforsecurity=False).hexdigest()
        != str(item["content_md5"]).lower()
        for path, item in zip(paths, members, strict=True)
    ):
        raise ValueError("Frozen reliability cohort source checksum changed")
    return [
        {**item, "resolved_source_path": str(path)}
        for item, path in zip(members, paths, strict=True)
    ]


def run_frozen_reliability_cohort(
    *,
    sources_manifest: Path,
    runs_root: Path,
    max_duration_seconds: int = 7_200,
    report_ids: tuple[str, ...] | None = None,
    run_cohort_once: Callable[..., dict[str, Any]] = run_frozen_cohort_once,
) -> dict[str, Any]:
    """Run each selected frozen member with an independent isolated deadline."""

    members = _load_members(sources_manifest)
    selected_members = _select_members(members, report_ids)
    runs_root.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="frozen-reliability-", dir=runs_root))
    root.joinpath("frozen_cohort.json").write_text(
        sources_manifest.read_text(encoding="utf-8"), encoding="utf-8"
    )
    selected_ids = [
        f"cohort-{str(member['content_md5']).lower()[:20]}"
        for member in selected_members
    ]
    root.joinpath("selected_cohort.json").write_text(
        json.dumps(
            {"report_ids": selected_ids, "members": selected_members},
            sort_keys=True,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )

    results: list[dict[str, Any]] = []
    executions: list[dict[str, Any]] = []
    for report_id, member in zip(selected_ids, selected_members, strict=True):
        execution = run_cohort_once(
            runs_root=root / "members" / report_id,
            sources=[member],
            max_duration_seconds=max_duration_seconds,
        )
        report_results = list(execution["reports"])
        if len(report_results) != 1:
            raise RuntimeError(
                f"Isolated frozen report execution omitted {report_id}"
            )
        git_sha = str(execution.get("git_sha") or "")
        if len(git_sha) != 40 or any(
            character not in "0123456789abcdef" for character in git_sha
        ):
            raise RuntimeError(
                f"Isolated frozen report execution lacks a clean git SHA: {report_id}"
            )
        if executions and git_sha != executions[0]["git_sha"]:
            raise RuntimeError("Frozen report executions used different git revisions")
        executions.append(execution)
        report = report_results[0]
        metrics = dict(execution.get("cohort_metrics") or {})
        report.update(
            {
                "model_provider_calls": metrics.get("model_provider_calls"),
                "input_tokens": metrics.get("input_tokens"),
                "output_tokens": metrics.get("output_tokens"),
                "cost": metrics.get("cost_usd"),
                "total_duration_seconds": metrics.get("duration_seconds"),
                "bounded_automatic_repair": metrics.get(
                    "bounded_automatic_repair"
                ),
                "operator_intervention": (
                    bool(metrics["operator_intervention_count"])
                    if metrics.get("operator_intervention_count") is not None
                    else None
                ),
                "metric_attribution": "per_report_isolated_workflow",
            }
        )
        results.append(report)

    git_sha = executions[0]["git_sha"]
    cohort_metrics = _aggregate_per_report_metrics(executions)
    result = {
        "schema_version": "1.0",
        "git_sha": git_sha,
        "cohort_size": len(results),
        "cohort_directory": str(root),
        "production_run_directory": str(root / "members"),
        "cohort_metrics": cohort_metrics,
        "reports": results,
        "summary": summarize_frozen_cohort_results(
            results, cohort_metrics=cohort_metrics
        ),
    }
    root.joinpath("cohort_result.json").write_text(
        json.dumps(result, sort_keys=True, separators=(",", ":")), encoding="utf-8"
    )
    return result


def _select_members(
    members: list[dict[str, Any]], report_ids: tuple[str, ...] | None
) -> list[dict[str, Any]]:
    if report_ids is None:
        return members
    requested = tuple(str(report_id).strip() for report_id in report_ids)
    if not requested or any(not report_id for report_id in requested):
        raise ValueError("At least one non-empty frozen report ID is required")
    if len(set(requested)) != len(requested):
        raise ValueError("Frozen report selection contains duplicate report IDs")
    requested_set = set(requested)
    by_id = {
        f"cohort-{str(member['content_md5']).lower()[:20]}": member
        for member in members
    }
    missing = sorted(requested_set - set(by_id))
    if missing:
        raise ValueError(f"Frozen report selection contains unknown IDs: {missing}")
    return [by_id[report_id] for report_id in requested]


def _aggregate_per_report_metrics(
    executions: list[dict[str, Any]],
) -> dict[str, Any]:
    metrics = [dict(execution.get("cohort_metrics") or {}) for execution in executions]

    def total(key: str) -> int | float | None:
        values = [item.get(key) for item in metrics]
        if not values or any(value is None for value in values):
            return None
        return round(sum(values), 6)

    repairs = [item.get("bounded_automatic_repair") for item in metrics]
    interventions = [item.get("operator_intervention_count") for item in metrics]
    return {
        "model_provider_calls": total("model_provider_calls"),
        "input_tokens": total("input_tokens"),
        "output_tokens": total("output_tokens"),
        "cost_usd": total("cost_usd"),
        "duration_seconds": total("duration_seconds"),
        "bounded_automatic_repair": (
            any(bool(value) for value in repairs)
            if repairs and all(value is not None for value in repairs)
            else None
        ),
        "operator_intervention_count": (
            int(sum(interventions))
            if interventions and all(value is not None for value in interventions)
            else None
        ),
        "metric_attribution": "per_report_isolated_workflow",
    }


def preflight_frozen_reliability_cohort(
    *, sources_manifest: Path, runs_root: Path
) -> dict[str, Any]:
    """Validate frozen provenance and production admission before live work."""
    members = _load_members(sources_manifest)
    runs_root.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="frozen-reliability-preflight-", dir=runs_root))
    results = [
        preflight_frozen_cohort_member(
            runs_root=root / "members",
            source_path=Path(str(member["resolved_source_path"])),
            source_metadata=member,
        )
        for member in members
    ]
    result = {
        "schema_version": "1.0",
        "cohort_size": len(results),
        "admitted_count": sum(
            item["admission_outcome"] == "admitted" for item in results
        ),
        "cohort_admission_rate": sum(
            item["admission_outcome"] == "admitted" for item in results
        )
        / len(results),
        "cohort_directory": str(root),
        "reports": results,
    }
    root.joinpath("cohort_preflight.json").write_text(
        json.dumps(result, sort_keys=True, separators=(",", ":")), encoding="utf-8"
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--sources-manifest",
        type=Path,
        default=DEFAULT_SOURCES_MANIFEST,
    )
    parser.add_argument("--runs-root", type=Path, required=True)
    parser.add_argument(
        "--max-duration",
        type=int,
        default=7_200,
        help="Maximum workflow seconds allowed per selected report",
    )
    parser.add_argument(
        "--report-ids",
        nargs="+",
        default=None,
        help=(
            "Optional stable report IDs to run; defaults to every manifest member"
        ),
    )
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    try:
        result = (
            preflight_frozen_reliability_cohort(
                sources_manifest=args.sources_manifest, runs_root=args.runs_root
            )
            if args.preflight_only
            else run_frozen_reliability_cohort(
                sources_manifest=args.sources_manifest,
                runs_root=args.runs_root,
                max_duration_seconds=args.max_duration,
                report_ids=(tuple(args.report_ids) if args.report_ids else None),
            )
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"terminal_failure_code": "frozen_cohort_input_invalid"}))
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
