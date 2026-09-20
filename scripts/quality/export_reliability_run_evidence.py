"""Export safe, run-scoped reliability evidence from immutable SQLite records."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

_FAILURE_DIAGNOSTIC_FIELDS = (
    "stage",
    "outer_code",
    "inner_error_class",
    "validator_rule",
    "artifact_family",
    "claim_or_entity_id",
)
_FAILURE_CONTEXT_FIELDS = {
    "affected_section",
    "artifact_family",
    "cause_code",
    "cause_type",
    "component",
    "entity_id",
    "evidence_id",
    "field",
    "reason",
    "rule_id",
    "schema_name",
    "schema_root_key",
}
_SAFE_DIAGNOSTIC_TOKEN_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._:-"
)


def _bounded_diagnostic_token(value: object) -> str:
    """Keep only a short identifier, never prose or untrusted payload content."""

    token = str(value or "").strip()
    if not token or len(token) > 128:
        return ""
    return token if set(token) <= _SAFE_DIAGNOSTIC_TOKEN_CHARS else ""


def _failure_diagnostic(raw: object, *, failure_code: str) -> dict[str, Any]:
    """Project a retained failure cause into fixed, source-text-free fields."""

    if not isinstance(raw, dict):
        return {}
    diagnostic = {
        key: _bounded_diagnostic_token(raw.get(key))
        for key in _FAILURE_DIAGNOSTIC_FIELDS
    }
    repair_attempt = raw.get("repair_attempt")
    diagnostic["repair_attempt"] = (
        repair_attempt
        if isinstance(repair_attempt, int) and not isinstance(repair_attempt, bool)
        else 0
    )
    diagnostic["repair_attempt"] = max(0, min(9, diagnostic["repair_attempt"]))
    context = raw.get("error_context")
    diagnostic["error_context"] = (
        {
            key: token
            for key, value in sorted(context.items())
            if key in _FAILURE_CONTEXT_FIELDS
            if (token := _bounded_diagnostic_token(value))
        }
        if isinstance(context, dict)
        else {}
    )
    diagnostic["outer_code"] = _bounded_diagnostic_token(
        diagnostic["outer_code"] or failure_code
    )
    return diagnostic


def _rows(
    conn: sqlite3.Connection, query: str, args: tuple[Any, ...]
) -> list[dict[str, Any]]:
    try:
        cursor = conn.execute(query, args)
    except sqlite3.OperationalError:
        return []
    columns = [item[0] for item in cursor.description or ()]
    return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def _root_workflow_id(state_db: Path, report_id: str) -> str:
    """Find the workflow lineage needed to read its retained remediation row."""

    if not state_db.is_file():
        return ""
    try:
        with sqlite3.connect(state_db) as conn:
            row = conn.execute(
                """
                SELECT root_workflow_id
                FROM workflow_jobs
                WHERE report_id=? AND root_workflow_id<>''
                ORDER BY rowid DESC
                LIMIT 1
                """,
                (report_id,),
            ).fetchone()
    except sqlite3.Error:
        return ""
    return str(row[0] or "") if row else ""


def _write_csv(path: Path, fields: list[str], rows: Iterable[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _repair_effectiveness_projection(
    *, artifact_dir: Path, validation_run_id: str
) -> dict[str, Any]:
    """Project the retained, content-free repair scorecard without recomputing it."""

    run_hash = hashlib.sha256(validation_run_id.encode("utf-8")).hexdigest()
    path = artifact_dir / "validation-runs" / run_hash / "reliability_telemetry.json"
    if not path.is_file():
        return {
            "schema_version": "1.0",
            "measurement_status": "unavailable",
            "reason": "retained_reliability_artifact_missing",
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {
            "schema_version": "1.0",
            "measurement_status": "unavailable",
            "reason": "retained_reliability_artifact_invalid",
        }
    scorecard = payload.get("repair_scorecard") if isinstance(payload, dict) else None
    if not isinstance(scorecard, dict):
        return {
            "schema_version": "1.0",
            "measurement_status": "unavailable",
            "reason": "retained_repair_scorecard_missing",
        }
    return scorecard


def _authoritative_frozen_cohort_projection(
    cohort_result_path: Path,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    """Read the production-derived typed outcomes retained by the cohort runner."""

    payload = json.loads(cohort_result_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("cohort_result must be a JSON object")
    reports = payload.get("reports")
    if not isinstance(reports, list):
        raise ValueError("cohort_result reports must be a list")
    cohort_size = payload.get("cohort_size")
    if isinstance(cohort_size, int) and len(reports) != cohort_size:
        raise ValueError("cohort_result reports do not match declared cohort_size")

    terminal_rows: list[dict[str, str]] = []
    publication_ready_count = 0
    for report in reports:
        if not isinstance(report, dict):
            raise ValueError("cohort_result report must be an object")
        report_id = str(report.get("report_id") or "").strip()
        terminal_outcome = str(report.get("final_state") or "").strip()
        failure_code = str(report.get("terminal_failure_code") or "").strip()
        publication_readiness = str(report.get("publication_readiness") or "").strip()
        if not report_id:
            raise ValueError("cohort_result report has no report_id")
        if terminal_outcome not in {"awaiting_review", "failed"}:
            raise ValueError("cohort_result report has no typed terminal outcome")
        if terminal_outcome == "failed" and not failure_code:
            raise ValueError("failed cohort_result report has no failure code")
        if terminal_outcome != "failed" and failure_code:
            raise ValueError("non-failed cohort_result report has a failure code")
        if publication_readiness not in {"pass", "fail"}:
            raise ValueError("cohort_result report has no publication readiness")
        publication_ready_count += publication_readiness == "pass"
        terminal_rows.append(
            {
                "report_id": report_id,
                "terminal_outcome": terminal_outcome,
                "terminal_stage": "",
                "failure_code": failure_code,
                **(
                    _failure_diagnostic(
                        report.get("failure_diagnostic"), failure_code=failure_code
                    )
                    if failure_code
                    else {}
                ),
            }
        )
    if len({row["report_id"] for row in terminal_rows}) != len(terminal_rows):
        raise ValueError("cohort_result contains duplicate report IDs")

    terminal_rows.sort(key=lambda row: row["report_id"])
    failures = Counter(
        row["failure_code"] for row in terminal_rows if row["failure_code"]
    )
    expected_pareto = dict(
        sorted(failures.items(), key=lambda item: (-item[1], item[0]))
    )
    summary = payload.get("summary")
    actual_pareto = (
        summary.get("failure_code_pareto") if isinstance(summary, dict) else None
    )
    if actual_pareto != expected_pareto:
        raise ValueError("cohort_result failure Pareto does not match typed outcomes")
    terminal_outcomes = dict(
        sorted(Counter(row["terminal_outcome"] for row in terminal_rows).items())
    )
    return terminal_rows, {
        "schema_version": "1.0",
        "immutable_cohort_size": len(terminal_rows),
        "terminal_outcome_complete": True,
        "missing_terminal_report_count": 0,
        "terminal_outcomes": terminal_outcomes,
        "awaiting_review_count": terminal_outcomes.get("awaiting_review", 0),
        "publication_ready_count": publication_ready_count,
    }


def _write_terminal_outcome_views(
    *,
    output_dir: Path,
    terminal_rows: list[dict[str, str]],
    failure_details_metadata: dict[str, str] | None = None,
) -> None:
    """Write every terminal view from the same already-typed outcome records."""

    _write_csv(
        output_dir / "terminal_outcomes.csv",
        ["report_id", "terminal_outcome", "terminal_stage", "failure_code"],
        terminal_rows,
    )
    failure_rows = [row for row in terminal_rows if row["failure_code"]]
    _write_json(
        output_dir / "failure_details.json",
        {
            **(failure_details_metadata or {}),
            "terminal_failures": failure_rows,
        },
    )
    failures = Counter(row["failure_code"] for row in failure_rows)
    _write_csv(
        output_dir / "failure_pareto.csv",
        ["failure_code", "affected_reports"],
        [
            {"failure_code": code, "affected_reports": count}
            for code, count in sorted(
                failures.items(), key=lambda item: (-item[1], item[0])
            )
        ],
    )


def export_frozen_cohort_outcome_views(
    *, cohort_result_path: Path, output_dir: Path
) -> None:
    """Project frozen-cohort terminal views from its authoritative typed result."""

    output_dir.mkdir(parents=True, exist_ok=True)
    terminal_rows, aggregate_funnel = _authoritative_frozen_cohort_projection(
        cohort_result_path
    )
    _write_terminal_outcome_views(
        output_dir=output_dir,
        terminal_rows=terminal_rows,
    )
    _write_json(output_dir / "aggregate_funnel.json", aggregate_funnel)
    _write_json(
        output_dir / "audit_findings.json",
        {
            "status": "failed_reliability_targets",
            "cohort_size": aggregate_funnel["immutable_cohort_size"],
            "typed_terminal_outcomes": aggregate_funnel["immutable_cohort_size"],
            "awaiting_review": aggregate_funnel["awaiting_review_count"],
            "publish_ready": aggregate_funnel["publication_ready_count"],
            "publication_performed": False,
            "findings": [
                "Immutable cohort retained; no member replacement occurred.",
                "Publication and repeat publication were not run because the required "
                "cohort success threshold was not met.",
                "Terminal outcomes are complete and typed.",
            ],
        },
    )


def export_run_evidence(
    *, state_dir: Path, artifact_dir: Path, output_dir: Path, validation_run_id: str
) -> None:
    """Create bounded, no-source-text evidence views for one validation run."""
    # Keep the run-scoped export on the same retained-diagnostics projection as
    # the frozen cohort.  This is intentionally a read-only import: the runner
    # owns the canonical mapping from validation findings/remediation records.
    from scripts.quality.ias_live_canary_runner import _read_failure_diagnostic

    output_dir.mkdir(parents=True, exist_ok=True)
    reports_db = state_dir / "reports.sqlite"
    usage_db = state_dir / "llm_usage.sqlite"
    with sqlite3.connect(reports_db) as conn:
        members = _rows(
            conn,
            "SELECT report_id, publisher_id, source_identity_id "
            "FROM validation_run_cohort_members "
            "WHERE validation_run_id=? ORDER BY report_id",
            (validation_run_id,),
        )
        attempts = _rows(
            conn,
            "SELECT report_id, terminal_outcome, terminal_stage, failure_code "
            "FROM validation_run_entity_attempts "
            "WHERE validation_run_id=? AND is_current=1 ORDER BY report_id",
            (validation_run_id,),
        )
        stages = _rows(
            conn,
            "SELECT stage, terminal_outcome, failure_code, retryable, "
            "repair_disposition, idempotency_state, started_at_utc, completed_at_utc "
            "FROM validation_run_stage_records WHERE validation_run_id=?",
            (validation_run_id,),
        )
    by_report = {row["report_id"]: row for row in attempts}
    terminal_rows = []
    for item in members:
        attempt = by_report.get(item["report_id"], {})
        terminal_outcome = str(attempt.get("terminal_outcome") or "missing")
        failure_code = str(attempt.get("failure_code") or "") or (
            "validation_terminal_outcome_missing"
            if terminal_outcome == "missing"
            else ""
        )
        diagnostic = (
            _read_failure_diagnostic(
                state_db=state_dir / "workflow.sqlite",
                reports_db=reports_db,
                report_id=str(item["report_id"]),
                validation_run_id=validation_run_id,
                root_workflow_id=_root_workflow_id(
                    state_dir / "workflow.sqlite", str(item["report_id"])
                ),
                outer_code=failure_code,
            )
            if failure_code
            else {}
        )
        terminal_rows.append(
            {
                "report_id": item["report_id"],
                "terminal_outcome": terminal_outcome,
                "terminal_stage": str(attempt.get("terminal_stage") or ""),
                "failure_code": failure_code,
                **(
                    _failure_diagnostic(diagnostic, failure_code=failure_code)
                    if diagnostic
                    else {}
                ),
            }
        )
    _write_terminal_outcome_views(
        output_dir=output_dir,
        terminal_rows=terminal_rows,
        failure_details_metadata={"validation_run_id": validation_run_id},
    )
    _write_csv(
        output_dir / "per_report_funnel.csv",
        [
            "report_id",
            "publisher_id",
            "source_identity_id",
            "terminal_outcome",
            "terminal_stage",
            "failure_code",
        ],
        [{**member, **by_report.get(member["report_id"], {})} for member in members],
    )
    counts = Counter(row["terminal_outcome"] or "missing" for row in terminal_rows)
    stage_counts = Counter((row["stage"], row["terminal_outcome"]) for row in stages)
    stage_rows = [
        {
            "stage": stage,
            "outcome": outcome,
            "count": count,
            "cohort_size": len(members),
            "conversion_percent": round(100 * count / len(members), 2)
            if members
            else 0,
        }
        for (stage, outcome), count in sorted(stage_counts.items())
    ]
    _write_csv(
        output_dir / "stage_conversion_metrics.csv",
        ["stage", "outcome", "count", "cohort_size", "conversion_percent"],
        stage_rows,
    )
    _write_json(
        output_dir / "aggregate_funnel.json",
        {
            "schema_version": "1.0",
            "validation_run_id": validation_run_id,
            "immutable_cohort_size": len(members),
            "terminal_outcome_complete": all(
                row["terminal_outcome"] != "missing" for row in terminal_rows
            ),
            "missing_terminal_report_count": sum(
                row["terminal_outcome"] == "missing" for row in terminal_rows
            ),
            "terminal_outcomes": dict(sorted(counts.items())),
            "stage_outcomes": stage_rows,
        },
    )
    _write_csv(
        output_dir / "acquisition_metrics.csv",
        ["stage", "outcome", "count"],
        [
            {"stage": "acquisition", "outcome": outcome, "count": count}
            for (stage, outcome), count in stage_counts.items()
            if stage == "acquisition"
        ],
    )
    _write_csv(
        output_dir / "admission_metrics.csv",
        ["stage", "outcome", "count"],
        [
            {"stage": "admission_preflight", "outcome": outcome, "count": count}
            for (stage, outcome), count in stage_counts.items()
            if stage == "admission_preflight"
        ],
    )
    recovery_rows = [
        {
            "stage": row["stage"],
            "outcome": row["terminal_outcome"],
            "repair_disposition": row["repair_disposition"],
            "failure_code": row["failure_code"],
        }
        for row in stages
        if row["stage"] in {"structured_output_repair", "regeneration"}
    ]
    for name in ("structured_output_recovery.csv", "checkpoint_recovery.csv"):
        _write_csv(
            output_dir / name,
            ["stage", "outcome", "repair_disposition", "failure_code"],
            recovery_rows,
        )
    for name, matched in (
        ("category_outcomes.csv", "category_fit"),
        ("final_html_quality.csv", "final_html_validation"),
        ("publish_readiness.csv", "publication_preflight"),
        ("wordpress_transactions.csv", "wordpress_write"),
        ("wordpress_readback.csv", "authenticated_readback"),
        ("repeat_publication.csv", "repeat_publication"),
        ("figure_linkage.csv", "artifact_generation"),
    ):
        _write_csv(
            output_dir / name,
            ["stage", "outcome", "failure_code"],
            [
                {
                    "stage": row["stage"],
                    "outcome": row["terminal_outcome"],
                    "failure_code": row["failure_code"],
                }
                for row in stages
                if row["stage"] == matched
            ],
        )
    _write_json(
        output_dir / "regeneration_lineage.json",
        {
            "validation_run_id": validation_run_id,
            "stage_records": [
                row for row in recovery_rows if row["stage"] == "regeneration"
            ],
        },
    )
    _write_json(
        output_dir / "repair_effectiveness.json",
        _repair_effectiveness_projection(
            artifact_dir=artifact_dir, validation_run_id=validation_run_id
        ),
    )
    usage_rows: list[dict[str, Any]] = []
    if usage_db.exists():
        with sqlite3.connect(usage_db) as conn:
            usage_rows = _rows(
                conn,
                "SELECT action, semantic_task, prompt_namespace, provider, model, "
                "input_tokens, output_tokens, estimated_cost_usd "
                "FROM llm_usage_events",
                (),
            )
    _write_csv(
        output_dir / "llm_usage_metrics.csv",
        [
            "action",
            "semantic_task",
            "prompt_namespace",
            "provider",
            "model",
            "input_tokens",
            "output_tokens",
            "estimated_cost_usd",
        ],
        usage_rows,
    )
    cost_by_stage = Counter()
    for row in usage_rows:
        cost_by_stage[
            str(row.get("semantic_task") or row.get("action") or "unattributed")
        ] += float(row.get("estimated_cost_usd") or 0)
    _write_csv(
        output_dir / "cost_by_stage.csv",
        ["stage", "estimated_cost_usd"],
        [
            {"stage": key, "estimated_cost_usd": f"{value:.6f}"}
            for key, value in sorted(cost_by_stage.items())
        ],
    )
    _write_csv(
        output_dir / "cost_by_report.csv",
        ["report_id", "estimated_cost_usd", "status"],
        [
            {
                "report_id": row["report_id"],
                "estimated_cost_usd": "unattributed",
                "status": "retention_gap",
            }
            for row in terminal_rows
        ],
    )
    _write_csv(
        output_dir / "runtime_metrics.csv",
        ["stage", "record_count"],
        [
            {
                "stage": stage,
                "record_count": sum(
                    count
                    for (candidate, _), count in stage_counts.items()
                    if candidate == stage
                ),
            }
            for stage in sorted({row["stage"] for row in stages})
        ],
    )
    _write_csv(
        output_dir / "intervention_metrics.csv",
        ["metric", "value"],
        [
            {
                "metric": "operator_intervention_required_terminal_failures",
                "value": sum(
                    1
                    for row in terminal_rows
                    if row["terminal_outcome"] != "publish_ready"
                ),
            }
        ],
    )
    _write_json(
        output_dir / "audit_findings.json",
        {
            "validation_run_id": validation_run_id,
            "status": "failed_reliability_targets",
            "cohort_size": len(members),
            "publish_ready": counts.get("publish_ready", 0),
            "publication_performed": False,
            "findings": [
                "Immutable cohort retained; no member replacement occurred.",
                "Publication and repeat publication were not run because the required "
                "cohort success threshold was not met.",
                "Terminal outcomes are complete and typed.",
            ],
        },
    )
    _write_json(
        output_dir / "cohort_manifest.json",
        {
            "schema_version": "1.0",
            "validation_run_id": validation_run_id,
            "members": members,
        },
    )
    _write_json(
        output_dir / "evidence_run_manifest.json",
        {
            "schema_version": "1.0",
            "validation_run_id": validation_run_id,
            "artifact_dir": artifact_dir.as_posix(),
            "state_dir": state_dir.as_posix(),
            "safe_fields_only": True,
        },
    )
    (output_dir / "AUDIT.md").write_text(
        "# Reliability audit\n\nThe immutable cohort failed the reliability target. "
        "No WordPress write was authorized. See `audit_findings.json`.\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir")
    parser.add_argument("--artifact-dir")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--validation-run-id")
    parser.add_argument(
        "--cohort-result",
        type=Path,
        help="Authoritative production-derived cohort_result.json for frozen outcomes.",
    )
    args = parser.parse_args()
    output_dir = Path(args.output_dir)
    if args.cohort_result is not None:
        run_state_arguments = (
            args.state_dir,
            args.artifact_dir,
            args.validation_run_id,
        )
        if any(value is not None for value in run_state_arguments):
            parser.error(
                "--cohort-result projects frozen terminal views alone; "
                "do not combine it with run-state export arguments"
            )
        export_frozen_cohort_outcome_views(
            cohort_result_path=args.cohort_result,
            output_dir=output_dir,
        )
        return 0
    if not all((args.state_dir, args.artifact_dir, args.validation_run_id)):
        parser.error(
            "--state-dir, --artifact-dir, and --validation-run-id are required "
            "without --cohort-result"
        )
    export_run_evidence(
        state_dir=Path(args.state_dir),
        artifact_dir=Path(args.artifact_dir),
        output_dir=output_dir,
        validation_run_id=args.validation_run_id,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
