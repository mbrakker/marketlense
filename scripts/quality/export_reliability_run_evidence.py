"""Export safe, run-scoped reliability evidence from immutable SQLite records."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Literal

from src.orchestrators.remediation_orchestrator import _bounded_failure_context

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
_REPAIR_SCORECARD_FIELDS = (
    "schema_version",
    "measurement_status",
    "cohort_compatible",
    "repair_chain_count",
    "repair_attempt_count",
    "success_at_1_count",
    "success_at_1_rate",
    "success_at_3_count",
    "success_at_3_rate",
    "rolled_back_attempt_count",
    "abstention_or_removal_attempt_count",
    "out_of_scope_mutation_attempt_count",
    "repeated_failed_strategy_evidence_attempt_count",
    "repeated_failed_candidate_attempt_count",
    "incompatible_audit_count",
    "benchmark_case_count",
    "benchmark_denominator_complete",
    "benchmark_manifest_sha256",
    "baseline_identity_sha256",
    "current_identity_sha256",
    "hard_failure_introduction_count",
    "hard_failure_introduction_attempt_count",
    "hard_failure_introduction_rate",
    "unsupported_evidence_introduction_attempt_count",
    "deterministic_repair_share",
    "model_repair_share",
    "usage_attribution",
    "model_call_count",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "estimated_cost_usd",
    "latency_ms",
    "current_residual_failure_odds",
    "current_residual_failure_odds_state",
    "baseline_success_at_3_count",
    "baseline_success_at_3_rate",
    "baseline_usage_attribution",
    "baseline_model_call_count",
    "baseline_input_tokens",
    "baseline_output_tokens",
    "baseline_total_tokens",
    "baseline_estimated_cost_usd",
    "baseline_latency_ms",
    "baseline_residual_failure_odds",
    "baseline_residual_failure_odds_state",
    "residual_odds_reduction_factor",
    "residual_odds_reduction_state",
    "benchmark_comparison_status",
)
_REPAIR_FAILURE_CLASS_FIELDS = ("schema_version", "failure_class", "attempt_count")
_REPAIR_ATTEMPT_FIELDS = (
    "schema_version",
    "report_id",
    "attempt_index",
    "failure_rule_ids",
    "failure_fingerprints",
    "resolved_failure_fingerprints",
    "persisting_failure_fingerprints",
    "introduced_failure_fingerprints",
    "introduced_hard_failure_count",
    "strategy_fingerprint",
    "candidate_fingerprint",
    "repair_action",
    "repair_strategy",
    "evidence_fingerprints",
    "validation_status",
    "promotion_outcome",
    "successful",
    "abstention_or_removal",
    "out_of_scope_mutation",
    "repair_mode",
    "usage_attribution",
    "model_call_count",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "estimated_cost_usd",
    "latency_ms",
    "prompt_identities",
    "configuration_hash",
    "policy_hash",
    "producer_build_identity",
)
_REPAIR_MODE_FIELDS = (
    "schema_version",
    "repair_mode",
    "attempt_count",
    "successful_attempt_count",
    "success_rate",
    "metric_attribution",
    "model_call_count",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "estimated_cost_usd",
    "latency_ms",
)
RunDisposition = Literal["pass", "fail", "not_evaluated", "insufficient_evidence"]
_SUCCESS_TERMINAL_OUTCOMES = frozenset(
    {
        "awaiting_review",
        "completed",
        "publish_ready",
        "published_verified",
        "success",
        "succeeded",
    }
)
_FAILURE_TERMINAL_OUTCOMES = frozenset({"blocked", "failed", "permanent_failure"})
_NOT_EVALUATED_TERMINAL_OUTCOMES = frozenset(
    {"not_evaluated", "not_required", "skipped", "suppressed"}
)


def _terminal_disposition(
    outcomes: Iterable[str], *, expected_count: int
) -> RunDisposition:
    """Classify only complete, typed terminal outcomes for the exported scope."""

    normalized = [str(outcome or "").strip().casefold() for outcome in outcomes]
    if expected_count < 1 or len(normalized) != expected_count:
        return "insufficient_evidence"
    if any(outcome in _FAILURE_TERMINAL_OUTCOMES for outcome in normalized):
        return "fail"
    if all(outcome in _SUCCESS_TERMINAL_OUTCOMES for outcome in normalized):
        return "pass"
    if all(outcome in _NOT_EVALUATED_TERMINAL_OUTCOMES for outcome in normalized):
        return "not_evaluated"
    return "insufficient_evidence"


def _disposition_status(disposition: RunDisposition) -> str:
    return {
        "pass": "passed_reliability_targets",
        "fail": "failed_reliability_targets",
        "not_evaluated": "not_evaluated",
        "insufficient_evidence": "insufficient_evidence",
    }[disposition]


def _usage_rows_for_validation_run(
    usage_db: Path, *, validation_run_id: str
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Read LLM accounting only when the ledger can prove run attribution."""

    def unavailable(reason: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        return [], {
            "status": "unavailable",
            "reason": reason,
            "matching_event_count": None,
        }

    if not usage_db.is_file():
        return unavailable("usage_database_missing")
    try:
        database_uri = f"file:{usage_db.resolve().as_posix()}?mode=ro"
        with sqlite3.connect(database_uri, uri=True) as connection:
            columns = {
                str(row[1])
                for row in connection.execute("PRAGMA table_info(llm_usage_events)")
            }
            if not columns:
                return unavailable("usage_table_missing")
            if "validation_run_id" not in columns:
                return unavailable("validation_run_id_not_retained")
            query = (
                "SELECT action, semantic_task, prompt_namespace, provider, model, "
                "input_tokens, output_tokens, estimated_cost_usd "
                "FROM llm_usage_events WHERE validation_run_id=?"
            )
            cursor = connection.execute(query, (validation_run_id,))
            names = [str(column[0]) for column in cursor.description or ()]
            rows = [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]
    except sqlite3.Error:
        return unavailable("usage_query_unavailable")
    return rows, {
        "status": "available",
        "scope": "validation_run_id",
        "matching_event_count": len(rows),
    }


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
    if isinstance(context, dict):
        bounded_context = _bounded_failure_context(context)
        diagnostic["error_context"] = {
            key: (
                value if isinstance(value, dict) else _bounded_diagnostic_token(value)
            )
            for key, value in sorted(bounded_context.items())
            if key in _FAILURE_CONTEXT_FIELDS or key == "coverage_diagnostics"
            if isinstance(value, dict) or _bounded_diagnostic_token(value)
        }
    else:
        diagnostic["error_context"] = {}
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


def _write_artifact_manifest(*, output_dir: Path, scope: str) -> None:
    """Hash the finalized export without creating a self-referential entry."""

    entries = []
    for path in sorted(output_dir.rglob("*")):
        if not path.is_file() or path.name == "artifact_manifest.json":
            continue
        relative_path = path.relative_to(output_dir).as_posix()
        content = path.read_bytes()
        entries.append(
            {
                "relative_path": relative_path,
                "size_bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )
    _write_json(
        output_dir / "artifact_manifest.json",
        {
            "schema_version": "1.0",
            "scope": scope,
            "manifest_self_reference": (
                "artifact_manifest.json is the inventory itself and is intentionally "
                "not self-listed to avoid a self-hash cycle."
            ),
            "entries": entries,
        },
    )


def _repair_effectiveness_projection(
    *, artifact_dir: Path, validation_run_id: str
) -> dict[str, Any]:
    """Project only the typed content-free scorecard fields without recomputing it."""

    candidate_audit_attempts = _candidate_audit_projection(artifact_dir)

    def unavailable(reason: str) -> dict[str, Any]:
        projection: dict[str, Any] = {
            "schema_version": "1.0",
            "measurement_status": "unavailable",
            "reason": reason,
        }
        if candidate_audit_attempts:
            projection["candidate_audit_attempts"] = candidate_audit_attempts
        return projection

    run_hash = hashlib.sha256(validation_run_id.encode("utf-8")).hexdigest()
    path = artifact_dir / "validation-runs" / run_hash / "reliability_telemetry.json"
    if not path.is_file():
        return unavailable("retained_reliability_artifact_missing")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return unavailable("retained_reliability_artifact_invalid")
    scorecard = payload.get("repair_scorecard") if isinstance(payload, dict) else None
    if not isinstance(scorecard, dict):
        return unavailable("retained_repair_scorecard_missing")
    projection = {
        key: scorecard[key] for key in _REPAIR_SCORECARD_FIELDS if key in scorecard
    }
    for field_name in (
        "failure_class_distribution",
        "baseline_failure_class_distribution",
    ):
        values = scorecard.get(field_name)
        if isinstance(values, list):
            projection[field_name] = [
                {key: item[key] for key in _REPAIR_FAILURE_CLASS_FIELDS if key in item}
                for item in values
                if isinstance(item, dict)
            ]
    for field_name, allowed_fields in (
        ("attempts", _REPAIR_ATTEMPT_FIELDS),
        ("mode_metrics", _REPAIR_MODE_FIELDS),
    ):
        values = scorecard.get(field_name)
        if isinstance(values, list):
            projection[field_name] = [
                {key: item[key] for key in allowed_fields if key in item}
                for item in values
                if isinstance(item, dict)
            ]
    if candidate_audit_attempts:
        projection["candidate_audit_attempts"] = candidate_audit_attempts
    return projection


_CANDIDATE_AUDIT_HASH_FIELDS = (
    "before_sha256",
    "after_sha256",
    "strategy_fingerprint",
    "configuration_hash",
    "policy_hash",
    "producer_build_identity",
)
_CANDIDATE_AUDIT_LIST_FIELDS = (
    "allowed_paths",
    "verified_dependent_paths",
    "selected_evidence_ids",
    "quarantined_evidence_ids",
)
_CANDIDATE_AUDIT_SCOPE_FIELDS = ("transformation_scope", "validation_issues")
_CANDIDATE_AUDIT_TOKEN_FIELDS = (
    "repair_action",
    "repair_strategy",
    "validation_status",
    "promotion_outcome",
)
_CANDIDATE_AUDIT_REPAIR_DELTA_TOKEN_FIELDS = (
    "mutation_scope_result",
    "evidence_lineage_result",
    "semantic_grounding_validation_status",
    "repair_action",
    "repair_strategy",
)
_CANDIDATE_AUDIT_REPAIR_DELTA_LIST_FIELDS = ("evidence_ids_used",)
_CANDIDATE_AUDIT_PATH_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._:-=[]"
)


def _candidate_audit_projection(artifact_dir: Path) -> list[dict[str, Any]]:
    """Retain bounded candidate identity/status lineage from existing audit packs."""

    paths = sorted(artifact_dir.rglob("regeneration_candidate_audit_*.json"))
    projected: list[dict[str, Any]] = []
    for path in paths[:32]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        attempt = payload.get("attempt_index")
        if (
            not isinstance(attempt, int)
            or isinstance(attempt, bool)
            or not 0 <= attempt <= 9
        ):
            continue
        item: dict[str, Any] = {"attempt_index": attempt}
        for field_name in _CANDIDATE_AUDIT_HASH_FIELDS:
            value = str(payload.get(field_name) or "").strip().lower()
            if len(value) == 64 and set(value) <= frozenset("0123456789abcdef"):
                item[field_name] = value
        for field_name in _CANDIDATE_AUDIT_TOKEN_FIELDS:
            value = str(payload.get(field_name) or "").strip()
            if (
                value
                and len(value) <= 128
                and set(value) <= _SAFE_DIAGNOSTIC_TOKEN_CHARS
            ):
                item[field_name] = value
        for field_name in _CANDIDATE_AUDIT_LIST_FIELDS:
            values = payload.get(field_name)
            if not isinstance(values, list):
                continue
            bounded = [
                value
                for raw_value in values
                if (value := str(raw_value or "").strip())
                and len(value) <= 256
                and set(value) <= _CANDIDATE_AUDIT_PATH_CHARS
            ]
            if bounded:
                item[field_name] = list(dict.fromkeys(bounded))[:32]
        for field_name in _CANDIDATE_AUDIT_SCOPE_FIELDS:
            values = payload.get(field_name)
            if not isinstance(values, list):
                continue
            bounded = [
                value
                for raw_value in values
                if (value := str(raw_value or "").strip())
                and len(value) <= 128
                and set(value) <= _SAFE_DIAGNOSTIC_TOKEN_CHARS
            ]
            if bounded:
                item[field_name] = list(dict.fromkeys(bounded))[:32]
        lineage = payload.get("evidence_lineage")
        if isinstance(lineage, list):
            lineage_projection: list[dict[str, Any]] = []
            for raw_lineage in lineage[:32]:
                if not isinstance(raw_lineage, dict):
                    continue
                projected_lineage: dict[str, Any] = {}
                for field_name in ("entity_kind", "entity_id"):
                    value = _bounded_diagnostic_token(raw_lineage.get(field_name))
                    if value:
                        projected_lineage[field_name] = value
                for field_name in (
                    "original_evidence_ids",
                    "candidate_evidence_ids",
                ):
                    values = raw_lineage.get(field_name)
                    if isinstance(values, list):
                        bounded = [
                            value
                            for raw_value in values
                            if (value := str(raw_value or "").strip())
                            and len(value) <= 256
                            and set(value) <= _CANDIDATE_AUDIT_PATH_CHARS
                        ]
                        if bounded:
                            projected_lineage[field_name] = list(
                                dict.fromkeys(bounded)
                            )[:32]
                for field_name in (
                    "original_source_pages",
                    "candidate_source_pages",
                ):
                    values = raw_lineage.get(field_name)
                    if isinstance(values, list):
                        pages = [
                            value
                            for value in values
                            if isinstance(value, int)
                            and not isinstance(value, bool)
                            and 1 <= value <= 10_000
                        ]
                        if pages:
                            projected_lineage[field_name] = list(dict.fromkeys(pages))[
                                :32
                            ]
                if projected_lineage:
                    lineage_projection.append(projected_lineage)
            if lineage_projection:
                item["evidence_lineage"] = lineage_projection
        repair_delta = payload.get("repair_delta")
        if isinstance(repair_delta, dict):
            delta_projection: dict[str, Any] = {}
            for field_name in ("candidate_sha256", "input_sha256"):
                value = str(repair_delta.get(field_name) or "").strip().lower()
                if len(value) == 64 and set(value) <= frozenset("0123456789abcdef"):
                    delta_projection[field_name] = value
            for field_name in _CANDIDATE_AUDIT_REPAIR_DELTA_TOKEN_FIELDS:
                value = _bounded_diagnostic_token(repair_delta.get(field_name))
                if value:
                    delta_projection[field_name] = value
            for field_name in _CANDIDATE_AUDIT_REPAIR_DELTA_LIST_FIELDS:
                values = repair_delta.get(field_name)
                if isinstance(values, list):
                    bounded = [
                        value
                        for raw_value in values
                        if (value := str(raw_value or "").strip())
                        and len(value) <= 256
                        and set(value) <= _CANDIDATE_AUDIT_PATH_CHARS
                    ]
                    if bounded:
                        delta_projection[field_name] = list(dict.fromkeys(bounded))[:32]
            if delta_projection:
                item["repair_delta"] = delta_projection
        family_hashes = payload.get("unchanged_family_sha256")
        if isinstance(family_hashes, dict):
            bounded_family_hashes = {
                str(key): str(value).lower()
                for key, value in family_hashes.items()
                if str(key) in {"summary", "insights_candidates", "quotes_final"}
                and isinstance(value, str)
                and len(value) == 64
                and set(value.lower()) <= frozenset("0123456789abcdef")
            }
            if bounded_family_hashes:
                item["unchanged_family_sha256"] = bounded_family_hashes
        if len(item) > 1:
            projected.append(item)
    return projected


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
        diagnostic = (
            _failure_diagnostic(
                report.get("failure_diagnostic"), failure_code=failure_code
            )
            if failure_code
            else {}
        )
        terminal_rows.append(
            {
                "report_id": report_id,
                "terminal_outcome": terminal_outcome,
                "terminal_stage": str(diagnostic.get("stage") or ""),
                "failure_code": failure_code,
                **diagnostic,
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
    disposition = _terminal_disposition(
        (row["terminal_outcome"] for row in terminal_rows),
        expected_count=int(aggregate_funnel["immutable_cohort_size"]),
    )
    if disposition == "pass" and int(
        aggregate_funnel["publication_ready_count"]
    ) != int(aggregate_funnel["immutable_cohort_size"]):
        disposition = "fail"
    findings = [
        "Immutable cohort retained; no member replacement occurred.",
        "Publication and repeat publication were not performed; "
        "publication was not evaluated.",
        "Terminal outcomes are complete and typed.",
    ]
    findings.append(
        {
            "pass": (
                "All scoped terminal outcomes and publication-readiness results passed."
            ),
            "fail": (
                "At least one required terminal outcome or publication-readiness "
                "result failed."
            ),
            "not_evaluated": "No scoped terminal outcome was evaluated.",
            "insufficient_evidence": (
                "The scoped terminal outcome evidence is incomplete or unavailable."
            ),
        }[disposition]
    )
    _write_json(
        output_dir / "audit_findings.json",
        {
            "status": _disposition_status(disposition),
            "disposition": disposition,
            "scope": {
                "terminal_outcomes": "in_scope",
                "publication": "not_evaluated",
            },
            "cohort_size": aggregate_funnel["immutable_cohort_size"],
            "typed_terminal_outcomes": aggregate_funnel["immutable_cohort_size"],
            "awaiting_review": aggregate_funnel["awaiting_review_count"],
            "publish_ready": aggregate_funnel["publication_ready_count"],
            "publication_performed": False,
            "publication_disposition": "not_evaluated",
            "findings": findings,
        },
    )
    _write_artifact_manifest(
        output_dir=output_dir,
        scope="frozen-cohort-terminal-outcomes",
    )


def export_run_evidence(
    *,
    state_dir: Path,
    artifact_dir: Path,
    output_dir: Path,
    validation_run_id: str,
    authoritative_cohort_result_path: Path | None = None,
) -> None:
    """Create bounded, no-source-text evidence views for one validation run."""
    # Keep the run-scoped export on the same retained-diagnostics projection as
    # the frozen cohort.  This is intentionally a read-only import: the runner
    # owns the canonical mapping from validation findings/remediation records.
    from scripts.quality.ias_live_canary_runner import _read_failure_diagnostic

    output_dir.mkdir(parents=True, exist_ok=True)
    reports_db = state_dir / "reports.sqlite"
    usage_db = state_dir / "llm_usage.sqlite"
    authoritative_terminal_rows: dict[str, dict[str, Any]] = {}
    if authoritative_cohort_result_path is not None:
        rows, _aggregate = _authoritative_frozen_cohort_projection(
            authoritative_cohort_result_path
        )
        authoritative_terminal_rows = {row["report_id"]: row for row in rows}
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
    if authoritative_terminal_rows and {
        str(member["report_id"]) for member in members
    } != set(authoritative_terminal_rows):
        raise ValueError(
            "authoritative cohort result does not match validation-run members"
        )
    terminal_rows = []
    for item in members:
        authoritative = authoritative_terminal_rows.get(str(item["report_id"]))
        if authoritative is not None:
            terminal_rows.append(dict(authoritative))
            continue
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
        [
            {
                **member,
                **{
                    key: terminal_row[key]
                    for key in ("terminal_outcome", "terminal_stage", "failure_code")
                },
            }
            for member, terminal_row in zip(
                members,
                terminal_rows,
                strict=True,
            )
        ],
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
    usage_rows, usage_attribution = _usage_rows_for_validation_run(
        usage_db, validation_run_id=validation_run_id
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
    cost_by_stage: dict[str, float] = {}
    stages_with_incomplete_cost: set[str] = set()
    missing_cost_event_count = 0
    for row in usage_rows:
        stage = str(row.get("semantic_task") or row.get("action") or "unattributed")
        raw_cost = row.get("estimated_cost_usd")
        if not isinstance(raw_cost, (int, float, str)):
            stages_with_incomplete_cost.add(stage)
            missing_cost_event_count += 1
            continue
        try:
            cost = float(raw_cost)
        except (TypeError, ValueError):
            stages_with_incomplete_cost.add(stage)
            missing_cost_event_count += 1
            continue
        if not math.isfinite(cost):
            stages_with_incomplete_cost.add(stage)
            missing_cost_event_count += 1
            continue
        cost_by_stage[stage] = cost_by_stage.get(stage, 0.0) + cost
    if usage_attribution["status"] == "unavailable":
        cost_attribution = {
            "status": "unavailable",
            "reason": usage_attribution["reason"],
            "missing_cost_event_count": None,
        }
    else:
        cost_attribution = {
            "status": "partial" if missing_cost_event_count else "available",
            "scope": "validation_run_id",
            "missing_cost_event_count": missing_cost_event_count,
        }
    cost_stages = sorted(set(cost_by_stage) | stages_with_incomplete_cost)
    _write_csv(
        output_dir / "cost_by_stage.csv",
        ["stage", "estimated_cost_usd"],
        [
            {
                "stage": stage,
                "estimated_cost_usd": (
                    "unavailable"
                    if stage in stages_with_incomplete_cost
                    else f"{cost_by_stage[stage]:.6f}"
                ),
            }
            for stage in cost_stages
        ],
    )
    _write_csv(
        output_dir / "cost_by_report.csv",
        ["report_id", "estimated_cost_usd", "status"],
        [
            {
                "report_id": row["report_id"],
                "estimated_cost_usd": (
                    "unattributed"
                    if usage_attribution["status"] == "available"
                    else "unavailable"
                ),
                "status": (
                    "retention_gap"
                    if usage_attribution["status"] == "available"
                    else "unavailable"
                ),
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
                    if str(row["terminal_outcome"] or "").casefold()
                    in _FAILURE_TERMINAL_OUTCOMES
                ),
            }
        ],
    )
    disposition = _terminal_disposition(
        (row["terminal_outcome"] for row in terminal_rows),
        expected_count=len(members),
    )
    findings = [
        "Immutable cohort retained; no member replacement occurred.",
        "Publication and repeat publication were not performed; "
        "publication was not evaluated.",
        "Terminal outcomes are typed and attributed to each member's current attempt.",
        {
            "pass": "All scoped terminal outcomes passed.",
            "fail": "At least one scoped terminal outcome failed.",
            "not_evaluated": "No scoped terminal outcome was evaluated.",
            "insufficient_evidence": (
                "The scoped terminal outcome evidence is incomplete or unavailable."
            ),
        }[disposition],
    ]
    _write_json(
        output_dir / "audit_findings.json",
        {
            "validation_run_id": validation_run_id,
            "status": _disposition_status(disposition),
            "disposition": disposition,
            "scope": {
                "terminal_outcomes": "in_scope",
                "publication": "not_evaluated",
            },
            "cohort_size": len(members),
            "publish_ready": counts.get("publish_ready", 0),
            "publication_performed": False,
            "publication_disposition": "not_evaluated",
            "usage_attribution": usage_attribution,
            "cost_attribution": cost_attribution,
            "findings": findings,
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
            "usage_attribution": usage_attribution,
            "cost_attribution": cost_attribution,
        },
    )
    (output_dir / "AUDIT.md").write_text(
        "# Reliability audit\n\n"
        + {
            "pass": "The immutable scoped cohort passed the reliability target.",
            "fail": "The immutable scoped cohort failed the reliability target.",
            "not_evaluated": "The immutable scoped cohort was not evaluated.",
            "insufficient_evidence": (
                "The immutable scoped cohort has insufficient "
                "terminal-outcome evidence."
            ),
        }[disposition]
        + " Publication was not evaluated. See `audit_findings.json`.\n",
        encoding="utf-8",
    )
    _write_artifact_manifest(
        output_dir=output_dir,
        scope=f"validation-run:{validation_run_id}",
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
    parser.add_argument(
        "--authoritative-cohort-result",
        type=Path,
        help=(
            "Use a frozen cohort result to reconcile member outcomes while "
            "retaining local run-stage evidence."
        ),
    )
    args = parser.parse_args()
    output_dir = Path(args.output_dir)
    if args.cohort_result is not None:
        run_state_arguments = (
            args.state_dir,
            args.artifact_dir,
            args.validation_run_id,
            args.authoritative_cohort_result,
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
        authoritative_cohort_result_path=args.authoritative_cohort_result,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
