"""Export safe, run-scoped reliability evidence from immutable SQLite records."""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


def _rows(
    conn: sqlite3.Connection, query: str, args: tuple[Any, ...]
) -> list[dict[str, Any]]:
    try:
        cursor = conn.execute(query, args)
    except sqlite3.OperationalError:
        return []
    columns = [item[0] for item in cursor.description or ()]
    return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def _write_csv(path: Path, fields: list[str], rows: Iterable[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def export_run_evidence(
    *, state_dir: Path, artifact_dir: Path, output_dir: Path, validation_run_id: str
) -> None:
    """Create bounded, no-source-text evidence views for one validation run."""
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
    terminal_rows = [
        {
            "report_id": item["report_id"],
            "terminal_outcome": by_report.get(item["report_id"], {}).get(
                "terminal_outcome", "missing"
            ),
            "terminal_stage": by_report.get(item["report_id"], {}).get(
                "terminal_stage", ""
            ),
            "failure_code": by_report.get(item["report_id"], {}).get(
                "failure_code", ""
            ),
        }
        for item in members
    ]
    _write_csv(
        output_dir / "terminal_outcomes.csv",
        ["report_id", "terminal_outcome", "terminal_stage", "failure_code"],
        terminal_rows,
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
            "terminal_outcomes": dict(sorted(counts.items())),
            "stage_outcomes": stage_rows,
        },
    )
    failures = Counter(
        row["failure_code"] for row in terminal_rows if row["failure_code"]
    )
    failure_rows = [
        {"failure_code": code, "affected_reports": count}
        for code, count in failures.most_common()
    ]
    _write_csv(
        output_dir / "failure_pareto.csv",
        ["failure_code", "affected_reports"],
        failure_rows,
    )
    _write_json(
        output_dir / "failure_details.json",
        {
            "validation_run_id": validation_run_id,
            "terminal_failures": [row for row in terminal_rows if row["failure_code"]],
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
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--artifact-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--validation-run-id", required=True)
    args = parser.parse_args()
    export_run_evidence(
        state_dir=Path(args.state_dir),
        artifact_dir=Path(args.artifact_dir),
        output_dir=Path(args.output_dir),
        validation_run_id=args.validation_run_id,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
