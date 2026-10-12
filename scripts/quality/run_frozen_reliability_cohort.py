"""Run selected frozen report members through isolated production workflows."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
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
STAGING_FROZEN_COHORT_MANIFEST_SHA256 = (
    "744de32ef0d200ced0904b4f44868084b29e4d923f75e78ca106c3c3549d22a7"
)
STAGING_FROZEN_COHORT_CONTENT_MD5S = frozenset(
    {
        "81af3890cd84ece81ef16e1aabda8027",
        "cbb6e7df67412186b8bc094a424ac890",
        "2acb4a56e14add5d7717f34c378f9091",
        "4b763ae2286ca69fe8acb63b17508dfb",
        "b638414df0b1fccea1cd8a93eaf8f5aa",
    }
)
STAGING_FROZEN_COHORT_REPORT_IDS = frozenset(
    f"cohort-{content_md5[:20]}" for content_md5 in STAGING_FROZEN_COHORT_CONTENT_MD5S
)


def _load_members(
    manifest_path: Path,
    *,
    sources_root: Path | None = None,
    manifest_bytes: bytes | None = None,
) -> list[dict[str, Any]]:
    payload = json.loads(
        manifest_path.read_bytes() if manifest_bytes is None else manifest_bytes
    )
    members = payload.get("members") if isinstance(payload, dict) else None
    if not isinstance(members, list) or len(members) not in {5, 10, 20}:
        raise ValueError(
            "Frozen reliability cohort must contain exactly 5, 10, or 20 members"
        )
    root = (
        Path(__file__).resolve().parents[2]
        if sources_root is None
        else sources_root.expanduser().resolve()
    )
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
    paths = []
    for item in members:
        source_path = Path(str(item["source_path"])).expanduser()
        paths.append(
            source_path.resolve()
            if source_path.is_absolute()
            else (root / source_path).resolve()
        )
    if any(not path.is_relative_to(root) for path in paths):
        raise ValueError("Frozen cohort source is outside the configured sources root")
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
    sources_root: Path | None = None,
    shared_batch: bool = False,
    publish_to_wordpress_staging: bool = False,
    staging_hostname: str = "",
    allow_insecure_staging_http: bool = False,
    enable_cross_report_analysis: bool = False,
    run_cohort_once: Callable[..., dict[str, Any]] = run_frozen_cohort_once,
) -> dict[str, Any]:
    """Run each selected frozen member with an independent isolated deadline."""

    if (
        publish_to_wordpress_staging or enable_cross_report_analysis
    ) and not shared_batch:
        raise ValueError(
            "Staging publication and cross-report analysis require --shared-batch"
        )
    if publish_to_wordpress_staging and not enable_cross_report_analysis:
        raise ValueError(
            "Staging publication requires cross-report handoff verification"
        )
    if staging_hostname and not publish_to_wordpress_staging:
        raise ValueError("--staging-host requires staging publication to be enabled")
    if allow_insecure_staging_http and not publish_to_wordpress_staging:
        raise ValueError(
            "--allow-insecure-staging-http requires staging publication to be enabled"
        )
    manifest_bytes = sources_manifest.read_bytes()
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    if (
        publish_to_wordpress_staging
        and manifest_sha256 != STAGING_FROZEN_COHORT_MANIFEST_SHA256
    ):
        raise ValueError("WordPress staging requires the pinned five-report manifest")
    members = _load_members(
        sources_manifest,
        sources_root=sources_root,
        manifest_bytes=manifest_bytes,
    )
    selected_members = _select_members(members, report_ids)
    if publish_to_wordpress_staging:
        _require_exact_staging_members(members, selected_members)
    runs_root.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="frozen-reliability-", dir=runs_root))
    root.joinpath("frozen_cohort.json").write_bytes(manifest_bytes)
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

    if shared_batch:
        run_kwargs: dict[str, Any] = {
            "runs_root": root / "members",
            "sources": selected_members,
            "max_duration_seconds": max_duration_seconds,
        }
        if publish_to_wordpress_staging:
            run_kwargs.update(
                {
                    "publish_to_wordpress_staging": True,
                    "staging_hostname": staging_hostname,
                }
            )
            if allow_insecure_staging_http:
                run_kwargs["allow_insecure_staging_http"] = True
        if enable_cross_report_analysis:
            run_kwargs["enable_cross_report_analysis"] = True
        execution = run_cohort_once(**run_kwargs)
        report_results = list(execution.get("reports") or [])
        if len(report_results) != len(selected_members):
            raise RuntimeError("Shared frozen cohort execution omitted a report")
        git_sha = str(execution.get("git_sha") or "")
        if len(git_sha) != 40 or any(
            character not in "0123456789abcdef" for character in git_sha
        ):
            raise RuntimeError("Shared frozen cohort execution lacks a clean git SHA")
        result = {
            "schema_version": "1.0",
            "git_sha": git_sha,
            "source_manifest_sha256": manifest_sha256,
            "cohort_size": len(report_results),
            "shared_batch": True,
            "cohort_directory": str(root),
            "production_run_directory": str(execution.get("run_directory") or ""),
            "cohort_metrics": dict(execution.get("cohort_metrics") or {}),
            "reports": report_results,
            "summary": summarize_frozen_cohort_results(
                report_results,
                cohort_metrics=dict(execution.get("cohort_metrics") or {}),
            ),
        }
        root.joinpath("cohort_result.json").write_text(
            json.dumps(result, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        return result

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
            raise RuntimeError(f"Isolated frozen report execution omitted {report_id}")
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
                **(
                    {
                        "validation_reuse_telemetry": metrics[
                            "validation_reuse_telemetry"
                        ]
                    }
                    if isinstance(metrics.get("validation_reuse_telemetry"), dict)
                    else {}
                ),
                "bounded_automatic_repair": metrics.get("bounded_automatic_repair"),
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


def _require_exact_staging_members(
    members: list[dict[str, Any]], selected_members: list[dict[str, Any]]
) -> None:
    member_hashes = {str(member["content_md5"]).lower() for member in members}
    selected_hashes = {
        str(member["content_md5"]).lower() for member in selected_members
    }
    if (
        len(members) != 5
        or member_hashes != STAGING_FROZEN_COHORT_CONTENT_MD5S
        or len(selected_members) != 5
        or selected_hashes != STAGING_FROZEN_COHORT_CONTENT_MD5S
    ):
        raise ValueError("WordPress staging requires all five pinned frozen reports")


def _shared_batch_passes(result: dict[str, Any]) -> bool:
    """Require all five first-attempt draft creates, readbacks, and safe replay."""

    reports = list(result.get("reports") or [])
    if (
        result.get("shared_batch") is not True
        or result.get("cohort_size") != 5
        or len(reports) != 5
        or result.get("source_manifest_sha256") != STAGING_FROZEN_COHORT_MANIFEST_SHA256
        or {
            str(report.get("report_id") or "")
            for report in reports
            if isinstance(report, dict)
        }
        != STAGING_FROZEN_COHORT_REPORT_IDS
    ):
        return False
    for report in reports:
        report_repair_count = report.get("automatic_repair_count")
        if (
            report.get("admission_outcome") != "admitted"
            or report.get("final_state") != "published"
            or report.get("terminal_failure_code")
            or report.get("workflow_attempt_count") != 1
            or report.get("workflow_retry_count") != 0
            or report.get("operator_intervention") is not False
            or not isinstance(report.get("bounded_automatic_repair"), bool)
            or not isinstance(report_repair_count, int)
            or isinstance(report_repair_count, bool)
            or report_repair_count < 0
            or report.get("validation") != "pass"
            or report.get("publication_readiness") != "pass"
            or report.get("wordpress_post_type") != "ml_report"
            or report.get("wordpress_created_this_run") is not True
            or report.get("wordpress_authenticated_readback") is not True
        ):
            return False
    metrics = dict(result.get("cohort_metrics") or {})
    automatic_repair_count = metrics.get("automatic_repair_count")
    bounded_automatic_repair = metrics.get("bounded_automatic_repair")
    if (
        not isinstance(bounded_automatic_repair, bool)
        or not isinstance(automatic_repair_count, int)
        or isinstance(automatic_repair_count, bool)
        or automatic_repair_count
        != sum(int(report["automatic_repair_count"]) for report in reports)
        or bounded_automatic_repair
        != any(bool(report["bounded_automatic_repair"]) for report in reports)
        or metrics.get("workflow_retry_count") != 0
        or metrics.get("operator_intervention_count") != 0
    ):
        return False
    preflight = dict(metrics.get("wordpress_staging_preflight") or {})
    capabilities = set(preflight.get("verified_capabilities") or [])
    if not (
        preflight.get("hostname") == "marketlense.medianewsonline.com"
        and preflight.get("scheme") in {"http", "https"}
        and (
            preflight.get("scheme") == "https"
            or preflight.get("insecure_http_opt_in") is True
        )
        and preflight.get("reachable") is True
        and preflight.get("authenticated") is True
        and preflight.get("post_status") == "draft"
        and preflight.get("post_type") == "ml_report"
        and "create_posts" in capabilities
    ):
        return False
    replay = dict(metrics.get("wordpress_replay") or {})
    cross_report = dict(metrics.get("cross_report_handoffs") or {})
    briefing_usage = dict(
        cross_report.get("briefing_validated_multireport_provider_usage") or {}
    )
    briefing_cost = briefing_usage.get("estimated_cost_usd")
    briefing_duration = cross_report.get(
        "briefing_validated_multireport_execution_seconds"
    )
    briefing_cost_valid = (
        isinstance(briefing_cost, (int, float))
        and not isinstance(briefing_cost, bool)
        and briefing_cost >= 0
        and (not isinstance(briefing_cost, float) or math.isfinite(briefing_cost))
    )
    briefing_duration_valid = (
        isinstance(briefing_duration, (int, float))
        and not isinstance(briefing_duration, bool)
        and math.isfinite(float(briefing_duration))
        and briefing_duration > 0
    )
    expected_policy_hold_count = cross_report.get("queue_expected_policy_hold_count")
    queue_terminal_failure_count = cross_report.get("queue_terminal_failure_count")
    unclassified_terminal_failure_count = cross_report.get(
        "queue_unclassified_terminal_failure_count"
    )
    publication_job_count = cross_report.get("signal_or_briefing_publication_job_count")
    publication_policy_hold_count = cross_report.get(
        "signal_or_briefing_publication_policy_hold_count"
    )
    unexpected_publication_job_count = cross_report.get(
        "signal_or_briefing_publication_unexpected_job_count"
    )
    publication_status_counts = cross_report.get(
        "signal_or_briefing_publication_status_counts"
    )
    safety_counts = (
        expected_policy_hold_count,
        queue_terminal_failure_count,
        unclassified_terminal_failure_count,
        publication_job_count,
        publication_policy_hold_count,
        unexpected_publication_job_count,
    )
    if any(
        not isinstance(value, int) or isinstance(value, bool) or value < 0
        for value in safety_counts
    ):
        return False
    if not isinstance(publication_status_counts, dict) or any(
        not isinstance(status, str)
        or not isinstance(count, int)
        or isinstance(count, bool)
        or count < 0
        for status, count in publication_status_counts.items()
    ):
        return False
    expected_publication_status_counts = (
        {"blocked": expected_policy_hold_count} if expected_policy_hold_count else {}
    )
    return bool(
        replay.get("status") == "verified"
        and replay.get("duplicate_submissions") == 5
        and replay.get("first_attempt_publication_jobs") == 5
        and replay.get("created_duplicate_jobs") == 0
        and replay.get("attempt_counts_unchanged") is True
        and replay.get("published_rows_unchanged") is True
        and replay.get("additional_wordpress_writes") == 0
        and cross_report.get("enabled") is True
        and cross_report.get("queue_terminal") is True
        and queue_terminal_failure_count == expected_policy_hold_count
        and unclassified_terminal_failure_count == 0
        and cross_report.get("queue_nonterminal_outbox_count") == 0
        and cross_report.get("queue_dead_letter_outbox_count", 0) == 0
        and cross_report.get("briefing_validated_multireport_count", 0) >= 1
        and briefing_duration_valid
        and isinstance(briefing_usage.get("provider_calls"), int)
        and briefing_usage.get("provider_calls", 0) > 0
        and briefing_usage.get("cost_available") is True
        and briefing_cost_valid
        and cross_report.get("signal_manifest_count", 0) > 0
        and cross_report.get("signal_manifest_readback_verified_count")
        == cross_report.get("signal_manifest_count")
        and cross_report.get("signal_manifest_replay_verified_count")
        == cross_report.get("signal_manifest_count")
        and cross_report.get("signal_manifest_mutation_probe_count")
        == cross_report.get("signal_manifest_count")
        and cross_report.get("signal_manifest_mutation_verified_count")
        == cross_report.get("signal_manifest_count")
        and cross_report.get("signal_manifest_mutation_preserved") is True
        and cross_report.get("signal_manifest_mutation_probe_scope") == "every_manifest"
        and cross_report.get("signal_single_source_group_count", 0) > 0
        and cross_report.get(
            "signal_single_source_insufficient_grounding_hold_count", 0
        )
        > 0
        and cross_report.get("signal_single_source_unsafe_group_count") == 0
        and publication_job_count == expected_policy_hold_count
        and publication_policy_hold_count == expected_policy_hold_count
        and unexpected_publication_job_count == 0
        and publication_status_counts == expected_publication_status_counts
    )


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
    *, sources_manifest: Path, runs_root: Path, sources_root: Path | None = None
) -> dict[str, Any]:
    """Validate frozen provenance and production admission before live work."""
    members = _load_members(sources_manifest, sources_root=sources_root)
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
        "--sources-root",
        type=Path,
        default=None,
        help="Workspace root containing relative source paths from the manifest",
    )
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
        help=("Optional stable report IDs to run; defaults to every manifest member"),
    )
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument(
        "--shared-batch",
        action="store_true",
        help="Submit all selected reports together through one isolated workflow",
    )
    parser.add_argument(
        "--enable-wordpress-staging",
        action="store_true",
        help="Enable autonomous approval and WordPress drafts for the confirmed staging host",
    )
    parser.add_argument("--staging-host", default="")
    parser.add_argument(
        "--allow-insecure-staging-http",
        action="store_true",
        help="Allow HTTP only for the explicitly confirmed staging host",
    )
    parser.add_argument("--enable-cross-report-analysis", action="store_true")
    args = parser.parse_args()
    try:
        if (
            args.enable_wordpress_staging or args.enable_cross_report_analysis
        ) and not args.shared_batch:
            parser.error(
                "staging publication and cross-report analysis require --shared-batch"
            )
        if args.staging_host and not args.enable_wordpress_staging:
            parser.error("--staging-host requires --enable-wordpress-staging")
        if args.allow_insecure_staging_http and not args.enable_wordpress_staging:
            parser.error(
                "--allow-insecure-staging-http requires --enable-wordpress-staging"
            )
        result = (
            preflight_frozen_reliability_cohort(
                sources_manifest=args.sources_manifest,
                runs_root=args.runs_root,
                sources_root=args.sources_root,
            )
            if args.preflight_only
            else run_frozen_reliability_cohort(
                sources_manifest=args.sources_manifest,
                runs_root=args.runs_root,
                max_duration_seconds=args.max_duration,
                report_ids=(tuple(args.report_ids) if args.report_ids else None),
                sources_root=args.sources_root,
                shared_batch=args.shared_batch,
                publish_to_wordpress_staging=args.enable_wordpress_staging,
                staging_hostname=args.staging_host,
                allow_insecure_staging_http=args.allow_insecure_staging_http,
                enable_cross_report_analysis=args.enable_cross_report_analysis,
            )
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"terminal_failure_code": "frozen_cohort_input_invalid"}))
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    if args.shared_batch and args.enable_wordpress_staging:
        return 0 if _shared_batch_passes(result) else 1
    if args.shared_batch:
        reports = list(result.get("reports") or [])
        passed = (
            bool(reports)
            and len(reports) == result.get("cohort_size")
            and all(
                report.get("final_state") in {"published", "awaiting_review"}
                and not report.get("terminal_failure_code")
                for report in reports
            )
        )
        return 0 if passed else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
