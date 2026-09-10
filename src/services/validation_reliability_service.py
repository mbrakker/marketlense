"""Canonical deterministic reliability telemetry for immutable validation runs."""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any

from src.contracts.run_context import RunContext
from src.contracts.validation_reliability import (
    ValidationFailureParetoEntry,
    ValidationReliabilityArtifact,
    ValidationReliabilityBuildRequest,
    ValidationReliabilityFailureCode,
    ValidationReliabilityFailureTransition,
    ValidationReliabilityFirstAttemptEntity,
    ValidationReliabilityFirstAttemptStage,
    ValidationReliabilityFirstAttemptTransition,
    ValidationReliabilityTransition,
    ValidationReliabilityWriteRequest,
    ValidationReliabilityWriteResponse,
)
from src.services._report_store_service.connection import _metadata_conn
from src.utils.errors import AppError
from src.utils.logging import log_event

_SCHEMA_VERSION = "1.0"
_STATE_SEQUENCE: tuple[str, ...] = (
    "admitted",
    "source_prepared",
    "evidence_complete",
    "analysis_complete",
    "validation_complete",
    "rendered",
    "publish_ready",
    "published",
    "readback_verified",
)
_STATE_STAGE_GROUPS: dict[str, tuple[str, ...]] = {
    "admitted": ("admission_preflight",),
    "source_prepared": ("source_preparation", "source_validation"),
    "evidence_complete": ("evidence_generation",),
    "analysis_complete": (
        "taxonomy",
        "category_fit",
        "artifact_generation",
    ),
    "validation_complete": (
        "regeneration",
        "grounding_validation",
        "semantic_validation",
    ),
    "rendered": ("rendering", "final_html_validation"),
    "publish_ready": ("ingestion",),
    "published": ("wordpress_lookup", "wordpress_write"),
    "readback_verified": ("authenticated_readback",),
}
_A21_STATE_SEQUENCE: tuple[str, ...] = (
    "admitted",
    "source_prepared",
    "evidence_complete",
    "analysis_complete",
    "validation_complete",
    "rendered",
    "awaiting_review",
)
_A21_STATE_STAGE_GROUPS: dict[str, tuple[str, ...]] = {
    **{
        state: stages
        for state, stages in _STATE_STAGE_GROUPS.items()
        if state in _A21_STATE_SEQUENCE
    },
    "awaiting_review": ("publication_preflight",),
}
_SUCCESS_OUTCOMES = {"succeeded", "publish_ready", "published_verified"}
_COMPLETED_OUTCOMES = _SUCCESS_OUTCOMES | {"skipped"}
_FAILURE_OUTCOMES = {"failed", "blocked", "permanent_failure"}
_TERMINAL_FAILURE_OUTCOMES = {"blocked", "permanent_failure", "cancelled"}
_AUTOMATIC_RECOVERY_DISPOSITIONS = {
    "not_required",
    "none",
    "targeted_repair",
    "full_rerun",
    "structured_output_repair",
    "queue_redelivery",
    "process_restart",
}
_REPAIR_CAUSAL_CODES = {
    "targeted_repair": "targeted_repair",
    "structured_output_repair": "structured_output_repair",
    "full_rerun": "full_rerun",
    "queue_redelivery": "queue_redelivery",
    "process_restart": "process_restart",
}
_EXPLICIT_REPAIR_STAGES = {"structured_output_repair"}
_REQUIRED_USAGE_ATTRIBUTION = (
    "validation_run_id",
    "cohort_id",
    "workflow_run_id",
    "report_id",
    "publisher_id",
    "workflow",
    "stage",
    "artifact_family",
    "action",
    "semantic_task",
    "prompt_namespace",
    "policy_namespace",
    "provider",
    "model",
    "cache_decision",
    "configuration_hash",
    "policy_hash",
    "producer_build_identity",
)


@dataclass(frozen=True)
class _A21StateEvidence:
    """Read-only canonical queue evidence associated with report identities."""

    awaiting_review_report_ids: frozenset[str] = frozenset()
    operator_requeue_report_ids: frozenset[str] = frozenset()
    automatic_queue_failure_codes: tuple[tuple[str, str], ...] = ()


def build_validation_reliability_artifact(
    request: ValidationReliabilityBuildRequest, ctx: RunContext
) -> ValidationReliabilityArtifact:
    """Build a stable funnel and failure Pareto from canonical SQLite records."""

    _validate_build_request(request)
    run, attempts, stages = _read_manifest_rows(request, ctx)
    usage_events, usage_attribution_available = _read_usage_events(request, ctx)
    _validate_usage_attribution(
        usage_events=usage_events,
        validation_run_id=str(request.validation_run_id),
        cohort_id=str(run["cohort_id"]),
    )
    current_attempts = [
        row
        for row in attempts
        if int(row["is_current"] or 0) == 1
        and str(row["cohort_disposition"]) == "final_validation"
    ]
    stages_by_attempt: dict[str, list[dict[str, Any]]] = defaultdict(list)
    all_attempts_by_entity: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for attempt in attempts:
        all_attempts_by_entity[str(attempt["entity_key"])].append(attempt)
    for records in all_attempts_by_entity.values():
        records.sort(key=lambda row: int(row["attempt_number"]))
    for row in stages:
        stages_by_attempt[str(row["attempt_id"])].append(row)
    for records in stages_by_attempt.values():
        records.sort(key=lambda row: (str(row["started_at_utc"]), str(row["stage"])))
    workflow_run_id = str(run["workflow_run_id"]).strip()
    a21_stages_by_attempt: dict[str, list[dict[str, Any]]] = defaultdict(list)
    if workflow_run_id:
        for row in stages:
            if str(row["workflow_run_id"]) == workflow_run_id:
                a21_stages_by_attempt[str(row["attempt_id"])].append(row)
    for records in a21_stages_by_attempt.values():
        records.sort(key=lambda row: (str(row["started_at_utc"]), str(row["stage"])))
    state_evidence = _read_a21_state_evidence(
        request=request,
        report_ids={str(attempt["report_id"]) for attempt in attempts},
        workflow_run_id=workflow_run_id,
    )

    complete_states: dict[str, set[str]] = {state: set() for state in _STATE_SEQUENCE}
    failures: list[dict[str, Any]] = []
    for attempt in current_attempts:
        attempt_id = str(attempt["attempt_id"])
        entity_key = str(attempt["entity_key"])
        records = stages_by_attempt.get(attempt_id, [])
        state_status = _state_statuses(records)
        prior_completed = True
        for state in _STATE_SEQUENCE:
            completed = state_status[state] and prior_completed
            if completed:
                complete_states[state].add(entity_key)
            prior_completed = completed
    for attempt in attempts:
        if str(attempt["cohort_disposition"]) != "final_validation":
            continue
        attempt_id = str(attempt["attempt_id"])
        entity_key = str(attempt["entity_key"])
        records = stages_by_attempt.get(attempt_id, [])
        failures.extend(
            _failed_transitions(
                entity_key=entity_key,
                attempt=attempt,
                records=records,
                all_attempts=all_attempts_by_entity[entity_key],
                stages_by_attempt=stages_by_attempt,
                usage_events=usage_events,
            )
        )

    transitions = tuple(
        _transition_metric(
            from_state=from_state,
            to_state=to_state,
            completed_states=complete_states,
        )
        for from_state, to_state in zip(
            _STATE_SEQUENCE, _STATE_SEQUENCE[1:], strict=False
        )
    )
    first_attempt_entities = _first_attempt_entities(
        current_attempts=current_attempts,
        all_attempts_by_entity=all_attempts_by_entity,
        stages_by_attempt=a21_stages_by_attempt,
        usage_events=usage_events,
        usage_attribution_available=usage_attribution_available,
        state_evidence=state_evidence,
    )
    failed_transitions = _failure_transition_metrics(failures)
    pareto = _failure_pareto(failures)
    artifact = ValidationReliabilityArtifact(
        schema_version=_SCHEMA_VERSION,
        validation_run_id=request.validation_run_id,
        cohort_id=str(run["cohort_id"]),
        workflow_run_id=workflow_run_id,
        configuration_hash=str(run["configuration_hash"]),
        policy_hash=str(run["policy_hash"]),
        producer_build_identity=str(run["producer_build_identity"]),
        transitions=transitions,
        failed_transitions=failed_transitions,
        failure_pareto=pareto,
        first_attempt_entities=first_attempt_entities,
        first_attempt_transitions=_first_attempt_transition_metrics(
            first_attempt_entities
        ),
        first_attempt_failure_pareto=_first_attempt_failure_pareto(
            first_attempt_entities
        ),
    )
    artifact = replace(artifact, artifact_hash=_artifact_hash(artifact))
    log_event_payload = {
        "validation_run_id": str(artifact.validation_run_id),
        "cohort_id": artifact.cohort_id,
        "workflow_run_id": artifact.workflow_run_id,
        "transition_count": len(artifact.transitions),
        "failed_transition_count": len(artifact.failed_transitions),
        "pareto_entry_count": len(artifact.failure_pareto),
        "first_attempt_entity_count": len(artifact.first_attempt_entities),
        "first_attempt_pareto_entry_count": len(artifact.first_attempt_failure_pareto),
        "artifact_hash": artifact.artifact_hash,
    }
    logging.getLogger("market_lense.validation_reliability_service").info(
        log_event(
            ctx,
            role="service",
            event="validation_reliability_artifact_built",
            module="market_lense.validation_reliability_service",
            fields=log_event_payload,
        )
    )
    return artifact


def write_validation_reliability_artifact(
    request: ValidationReliabilityWriteRequest, ctx: RunContext
) -> ValidationReliabilityWriteResponse:
    """Atomically retain the canonical artifact without adding a second ledger."""

    if request.schema_version != _SCHEMA_VERSION or not request.artifact_path.strip():
        raise AppError(
            code="validation_reliability_write_request_invalid",
            message="Reliability artifact writing requires a supported schema and path",
            retryable=False,
        )
    expected_hash = _artifact_hash(request.artifact)
    if request.artifact.artifact_hash != expected_hash:
        raise AppError(
            code="validation_reliability_artifact_hash_invalid",
            message="Reliability artifact hash does not match its canonical payload",
            retryable=False,
        )
    path = Path(request.artifact_path)
    payload = _canonical_bytes(asdict(request.artifact))
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{expected_hash[:12]}.tmp")
        temporary.write_bytes(payload)
        temporary.replace(path)
    except OSError as exc:
        raise AppError(
            code="validation_reliability_artifact_write_failed",
            message="Failed to retain validation reliability artifact",
            cause=exc,
            retryable=False,
            context={"artifact_path": str(path)},
        ) from exc
    logging.getLogger("market_lense.validation_reliability_service").info(
        log_event(
            ctx,
            role="service",
            event="validation_reliability_artifact_written",
            module="market_lense.validation_reliability_service",
            fields={
                "artifact_path": str(path),
                "validation_run_id": str(request.artifact.validation_run_id),
                "artifact_hash": expected_hash,
            },
        )
    )
    return ValidationReliabilityWriteResponse(
        schema_version=_SCHEMA_VERSION,
        artifact_path=str(path),
        artifact_hash=expected_hash,
    )


def validation_reliability_artifact_path(
    *, output_dir: str, validation_run_id: str
) -> str:
    """Return the stable retained-artifact location for one validation run."""

    run_hash = hashlib.sha256(validation_run_id.encode("utf-8")).hexdigest()
    return str(
        Path(output_dir) / "validation-runs" / run_hash / "reliability_telemetry.json"
    )


def _validate_build_request(request: ValidationReliabilityBuildRequest) -> None:
    if request.schema_version != _SCHEMA_VERSION:
        raise AppError(
            code="validation_reliability_schema_version_invalid",
            message="Validation reliability telemetry schema version is unsupported",
            retryable=False,
        )
    if not all(
        str(value or "").strip()
        for value in (
            request.reports_db_path,
            request.usage_db_path,
            request.validation_run_id,
        )
    ):
        raise AppError(
            code="validation_reliability_request_invalid",
            message=(
                "Reliability telemetry requires report, usage, and validation-run "
                "identity"
            ),
            retryable=False,
        )


def _read_manifest_rows(
    request: ValidationReliabilityBuildRequest, ctx: RunContext
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    try:
        with _metadata_conn(request.reports_db_path, ctx) as conn:
            conn.row_factory = sqlite3.Row
            run_row = conn.execute(
                """
                SELECT validation_run_id, cohort_id, workflow_run_id,
                       configuration_hash, policy_hash, producer_build_identity
                FROM validation_runs WHERE validation_run_id=?
                """,
                (str(request.validation_run_id),),
            ).fetchone()
            if run_row is None:
                raise AppError(
                    code="validation_manifest_run_missing",
                    message="Reliability telemetry requires a created validation run",
                    retryable=False,
                )
            attempts = conn.execute(
                """
                SELECT attempt_id, entity_key, report_id, attempt_number, is_current,
                       cohort_disposition
                FROM validation_run_entity_attempts
                WHERE validation_run_id=?
                ORDER BY entity_key, attempt_number
                """,
                (str(request.validation_run_id),),
            ).fetchall()
            stages = conn.execute(
                """
                SELECT attempt_id, stage, started_at_utc, completed_at_utc,
                       terminal_outcome, failure_code, repair_disposition,
                       idempotency_state, entity_terminal, workflow_run_id
                FROM validation_run_stage_records
                WHERE validation_run_id=?
                ORDER BY attempt_id, started_at_utc, stage
                """,
                (str(request.validation_run_id),),
            ).fetchall()
    except AppError:
        raise
    except (OSError, sqlite3.Error) as exc:
        raise AppError(
            code="validation_reliability_manifest_read_failed",
            message="Failed to read validation-run manifest telemetry",
            cause=exc,
            retryable=False,
            context={"reports_db_path": request.reports_db_path},
        ) from exc
    return (
        dict(run_row),
        [dict(row) for row in attempts],
        [dict(row) for row in stages],
    )


def _read_a21_state_evidence(
    *,
    request: ValidationReliabilityBuildRequest,
    report_ids: set[str],
    workflow_run_id: str,
) -> _A21StateEvidence:
    """Read durable readiness and explicit requeue provenance without mutation.

    A validation manifest has no authority to claim publication readiness by
    itself.  The queue service retains that state under the immutable package
    checksum, and joins it to the queue job's report identity.  Missing state
    evidence deliberately produces no A21 success.
    """

    if (
        not workflow_run_id.strip()
        or not request.state_db_path.strip()
        or not Path(request.state_db_path).is_file()
    ):
        return _A21StateEvidence()
    try:
        with sqlite3.connect(
            f"file:{Path(request.state_db_path).resolve().as_posix()}?mode=ro",
            uri=True,
        ) as conn:
            tables = {
                str(row[0])
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            required = {"workflow_publication_readiness", "workflow_jobs"}
            if not required.issubset(tables):
                return _A21StateEvidence()
            placeholders = ",".join("?" for _ in sorted(report_ids))
            if not placeholders:
                return _A21StateEvidence()
            readiness_provenance = "readiness.readiness_status='awaiting_review'"
            if "workflow_publication_approvals" in tables:
                readiness_provenance = """
                    (readiness.readiness_status='awaiting_review'
                     OR EXISTS (
                        SELECT 1
                        FROM workflow_publication_approvals AS approval
                        WHERE approval.package_checksum=readiness.package_checksum
                          AND approval.action='approved'
                     ))
                """
            base = """
                FROM workflow_publication_readiness AS readiness
                JOIN workflow_jobs AS job
                  ON job.queue_name='publication_readiness'
                 AND job.output_content_hash=readiness.package_checksum
                WHERE readiness.entity_type='report'
                  AND {readiness_provenance}
                  AND job.status='succeeded'
                  AND job.root_workflow_id=?
                  AND job.report_id IN ({placeholders})
            """.format(
                readiness_provenance=readiness_provenance,
                placeholders=placeholders,
            )
            params = (workflow_run_id, *sorted(report_ids))
            awaiting_review = frozenset(
                str(row[0])
                for row in conn.execute(
                    "SELECT DISTINCT job.report_id " + base + " ORDER BY job.report_id",
                    params,
                )
            )
            if "workflow_job_transitions" not in tables:
                return _A21StateEvidence(awaiting_review_report_ids=awaiting_review)
            operator_requeue = frozenset(
                str(row[0])
                for row in conn.execute(
                    """
                    SELECT DISTINCT job.report_id
                    {base}
                      AND EXISTS (
                        SELECT 1
                        FROM workflow_job_transitions AS transition
                        WHERE transition.job_id=job.job_id
                          AND transition.reason IN ('operator_requeue','queue-requeue')
                      )
                    ORDER BY job.report_id
                    """.format(base=base),
                    params,
                )
            )
            automatic_queue_failure_codes: tuple[tuple[str, str], ...] = ()
            if "workflow_job_attempts" in tables:
                automatic_rows = conn.execute(
                    """
                    SELECT DISTINCT job.report_id,
                      (
                        SELECT failed.error_code
                        FROM workflow_job_attempts AS failed
                        WHERE failed.job_id=job.job_id
                          AND failed.outcome='retry_wait'
                          AND EXISTS (
                            SELECT 1
                            FROM workflow_job_transitions AS retry_transition
                            WHERE retry_transition.job_id=job.job_id
                              AND retry_transition.to_status='retry_wait'
                              AND retry_transition.reason=failed.error_code
                          )
                          AND EXISTS (
                            SELECT 1
                            FROM workflow_job_attempts AS recovered
                            WHERE recovered.job_id=job.job_id
                              AND recovered.attempt_number>failed.attempt_number
                              AND recovered.outcome='succeeded'
                          )
                        ORDER BY failed.attempt_number, failed.error_code
                        LIMIT 1
                      )
                    {base}
                      AND EXISTS (
                        SELECT 1
                        FROM workflow_job_attempts AS failed
                        WHERE failed.job_id=job.job_id
                          AND failed.outcome='retry_wait'
                          AND EXISTS (
                            SELECT 1
                            FROM workflow_job_transitions AS retry_transition
                            WHERE retry_transition.job_id=job.job_id
                              AND retry_transition.to_status='retry_wait'
                              AND retry_transition.reason=failed.error_code
                          )
                          AND EXISTS (
                            SELECT 1
                            FROM workflow_job_attempts AS recovered
                            WHERE recovered.job_id=job.job_id
                              AND recovered.attempt_number>failed.attempt_number
                              AND recovered.outcome='succeeded'
                          )
                      )
                    ORDER BY job.report_id
                    """.format(base=base),
                    params,
                )
                automatic_queue_failure_codes = tuple(
                    (str(row[0]), str(row[1] or "automatic_queue_retry"))
                    for row in automatic_rows
                )
    except (OSError, sqlite3.Error) as exc:
        raise AppError(
            code="validation_reliability_state_evidence_read_failed",
            message="Failed to read canonical publication-readiness evidence",
            cause=exc,
            retryable=False,
            context={"state_db_path": request.state_db_path},
        ) from exc
    return _A21StateEvidence(
        awaiting_review_report_ids=awaiting_review,
        operator_requeue_report_ids=operator_requeue,
        automatic_queue_failure_codes=automatic_queue_failure_codes,
    )


def _automatic_queue_failure_code(evidence: _A21StateEvidence, report_id: str) -> str:
    """Return the first retained automatic queue cause for one report."""

    return next(
        (
            failure_code
            for candidate_report_id, failure_code in evidence.automatic_queue_failure_codes
            if candidate_report_id == report_id
        ),
        "",
    )


def _read_usage_events(
    request: ValidationReliabilityBuildRequest, ctx: RunContext
) -> tuple[list[dict[str, Any]], bool]:
    try:
        with sqlite3.connect(request.usage_db_path) as conn:
            conn.row_factory = sqlite3.Row
            columns = {
                str(row[1])
                for row in conn.execute("PRAGMA table_info(llm_usage_events)")
            }
            if not columns:
                return [], False
            if "validation_run_id" not in columns:
                return [], False
            event_count = int(
                conn.execute(
                    "SELECT COUNT(*) FROM llm_usage_events WHERE validation_run_id=?",
                    (str(request.validation_run_id),),
                ).fetchone()[0]
            )
            if event_count == 0:
                return [], False
            required = set(_REQUIRED_USAGE_ATTRIBUTION) | {
                "timestamp_utc",
                "input_tokens",
                "output_tokens",
                "total_tokens",
                "estimated_cost_usd",
            }
            missing = sorted(required - columns)
            if missing:
                raise AppError(
                    code="validation_usage_attribution_schema_incomplete",
                    message=(
                        "Usage ledger lacks required validation attribution columns"
                    ),
                    retryable=False,
                    context={"missing_columns": missing},
                )
            rows = conn.execute(
                """
                SELECT timestamp_utc, validation_run_id, cohort_id, workflow_run_id,
                       report_id, publisher_id, workflow, stage, artifact_family,
                       action, semantic_task, prompt_namespace, policy_namespace,
                       provider, model, input_tokens, output_tokens, total_tokens,
                       estimated_cost_usd, cache_decision, repair_attempt,
                       configuration_hash, policy_hash, producer_build_identity
                FROM llm_usage_events
                WHERE validation_run_id=?
                ORDER BY timestamp_utc, id
                """,
                (str(request.validation_run_id),),
            ).fetchall()
    except AppError:
        raise
    except (OSError, sqlite3.Error) as exc:
        raise AppError(
            code="validation_reliability_usage_read_failed",
            message="Failed to read validation-run usage telemetry",
            cause=exc,
            retryable=False,
            context={"usage_db_path": request.usage_db_path},
        ) from exc
    return [dict(row) for row in rows], True


def _validate_usage_attribution(
    *,
    usage_events: list[dict[str, Any]],
    validation_run_id: str,
    cohort_id: str,
) -> None:
    for index, event in enumerate(usage_events, start=1):
        missing = [
            field
            for field in _REQUIRED_USAGE_ATTRIBUTION
            if not str(event.get(field) or "").strip()
        ]
        if int(event.get("repair_attempt") or 0) < 0:
            missing.append("repair_attempt")
        if str(event.get("validation_run_id") or "") != validation_run_id:
            missing.append("validation_run_id_mismatch")
        if str(event.get("cohort_id") or "") != cohort_id:
            missing.append("cohort_id_mismatch")
        if missing:
            raise AppError(
                code="validation_usage_attribution_missing",
                message="Validation-run usage event is missing required attribution",
                retryable=False,
                context={
                    "validation_run_id": validation_run_id,
                    "event_index": index,
                    "missing": sorted(set(missing)),
                },
            )


def _state_statuses(records: list[dict[str, Any]]) -> dict[str, bool]:
    by_stage: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_stage[str(record["stage"])].append(record)
    statuses: dict[str, bool] = {}
    for state, stages in _STATE_STAGE_GROUPS.items():
        if state == "published":
            write_rows = by_stage.get("wordpress_write", [])
            lookup_rows = by_stage.get("wordpress_lookup", [])
            statuses[state] = any(
                str(row["terminal_outcome"]) == "succeeded" for row in write_rows
            ) or any(
                str(row["terminal_outcome"]) == "succeeded"
                and str(row["idempotency_state"]) in {"verified", "reused"}
                for row in lookup_rows
            )
            continue
        if state == "publish_ready":
            statuses[state] = any(
                str(row["terminal_outcome"]) in {"publish_ready", "succeeded"}
                for row in by_stage.get("ingestion", [])
            )
            continue
        if state == "readback_verified":
            statuses[state] = any(
                str(row["terminal_outcome"]) == "published_verified"
                for row in by_stage.get("authenticated_readback", [])
            )
            continue
        statuses[state] = all(
            any(
                str(row["terminal_outcome"]) in _COMPLETED_OUTCOMES
                for row in by_stage[stage]
            )
            for stage in stages
        )
    return statuses


def _failed_transitions(
    *,
    entity_key: str,
    attempt: dict[str, Any],
    records: list[dict[str, Any]],
    all_attempts: list[dict[str, Any]],
    stages_by_attempt: dict[str, list[dict[str, Any]]],
    usage_events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for index, target_state in enumerate(_STATE_SEQUENCE[1:], start=1):
        failure_rows = [
            row
            for row in records
            if str(row["stage"]) in _STATE_STAGE_GROUPS[target_state]
            and str(row["terminal_outcome"]) in _FAILURE_OUTCOMES
        ]
        if not failure_rows:
            continue
        failure_row = sorted(
            failure_rows,
            key=lambda row: (str(row["completed_at_utc"]), str(row["stage"])),
        )[0]
        completed_at = str(failure_row["completed_at_utc"])
        usage = _usage_before_failure(
            usage_events=usage_events,
            report_id=str(attempt["report_id"]),
            completed_at_utc=completed_at,
        )
        recovery = _recovery_dispositions(
            failed_attempt_number=int(attempt["attempt_number"]),
            target_state=target_state,
            all_attempts=all_attempts,
            stages_by_attempt=stages_by_attempt,
        )
        failures.append(
            {
                "from_state": _STATE_SEQUENCE[index - 1],
                "to_state": target_state,
                "failure_code": str(failure_row["failure_code"] or "unknown_failure"),
                "duration_ms": _duration_ms(
                    str(failure_row["started_at_utc"]), completed_at
                ),
                "usage": usage,
                **recovery,
            }
        )
    return failures


def _usage_before_failure(
    *, usage_events: list[dict[str, Any]], report_id: str, completed_at_utc: str
) -> dict[str, int | float]:
    relevant = [
        row
        for row in usage_events
        if str(row["report_id"]) == report_id
        and str(row["timestamp_utc"]) <= completed_at_utc
    ]
    return {
        "calls": len(relevant),
        "input_tokens": sum(int(row["input_tokens"] or 0) for row in relevant),
        "output_tokens": sum(int(row["output_tokens"] or 0) for row in relevant),
        "total_tokens": sum(int(row["total_tokens"] or 0) for row in relevant),
        "cost": round(
            sum(float(row["estimated_cost_usd"] or 0.0) for row in relevant), 6
        ),
    }


def _recovery_dispositions(
    *,
    failed_attempt_number: int,
    target_state: str,
    all_attempts: list[dict[str, Any]],
    stages_by_attempt: dict[str, list[dict[str, Any]]],
) -> dict[str, bool]:
    later_attempts = [
        row
        for row in all_attempts
        if int(row["attempt_number"]) > failed_attempt_number
    ]
    later_records = [
        record
        for attempt in later_attempts
        for record in stages_by_attempt.get(str(attempt["attempt_id"]), [])
    ]
    recovered = any(
        _state_statuses(stages_by_attempt.get(str(attempt["attempt_id"]), [])).get(
            target_state, False
        )
        for attempt in later_attempts
    )
    return {
        "recovered": recovered,
        "operator_intervention": any(
            str(row["repair_disposition"]) == "operator_intervention"
            for row in later_records
        ),
        "full_rerun": any(
            str(row["repair_disposition"]) == "full_rerun" for row in later_records
        ),
    }


def _first_attempt_entities(
    *,
    current_attempts: list[dict[str, Any]],
    all_attempts_by_entity: dict[str, list[dict[str, Any]]],
    stages_by_attempt: dict[str, list[dict[str, Any]]],
    usage_events: list[dict[str, Any]],
    usage_attribution_available: bool,
    state_evidence: _A21StateEvidence,
) -> tuple[ValidationReliabilityFirstAttemptEntity, ...]:
    entities: list[ValidationReliabilityFirstAttemptEntity] = []
    for current_attempt in sorted(
        current_attempts, key=lambda row: str(row["entity_key"])
    ):
        entity_key = str(current_attempt["entity_key"])
        attempts = [
            row
            for row in all_attempts_by_entity[entity_key]
            if str(row["cohort_disposition"]) != "out_of_cohort"
        ]
        if not attempts:
            continue
        first_attempt = attempts[0]
        first_records = stages_by_attempt.get(str(first_attempt["attempt_id"]), [])
        current_records = stages_by_attempt.get(str(current_attempt["attempt_id"]), [])
        report_id = str(first_attempt["report_id"])
        first_statuses = _a21_cascaded_state_statuses(
            first_records,
            report_id=report_id,
            awaiting_review_report_ids=state_evidence.awaiting_review_report_ids,
        )
        eventual_statuses = _a21_cascaded_state_statuses(
            current_records,
            report_id=report_id,
            awaiting_review_report_ids=state_evidence.awaiting_review_report_ids,
        )
        stages = tuple(
            _first_attempt_stage(
                from_state=from_state,
                to_state=to_state,
                first_attempt=first_attempt,
                attempts=attempts,
                first_statuses=first_statuses,
                eventual_statuses=eventual_statuses,
                stages_by_attempt=stages_by_attempt,
                usage_events=usage_events,
                usage_attribution_available=usage_attribution_available,
                operator_requeue=(
                    report_id in state_evidence.operator_requeue_report_ids
                ),
                automatic_queue_failure_code=_automatic_queue_failure_code(
                    state_evidence, report_id
                ),
            )
            for from_state, to_state in zip(
                _A21_STATE_SEQUENCE, _A21_STATE_SEQUENCE[1:], strict=False
            )
        )
        terminal_disposition = _terminal_disposition(
            attempts=attempts,
            stages_by_attempt=stages_by_attempt,
            eventual_success=eventual_statuses["awaiting_review"],
        )
        awaiting_review_stage = next(
            stage for stage in stages if stage.to_state == "awaiting_review"
        )
        entities.append(
            ValidationReliabilityFirstAttemptEntity(
                schema_version=_SCHEMA_VERSION,
                entity_key=entity_key,
                report_id=report_id,
                first_attempt_number=int(first_attempt["attempt_number"]),
                first_attempt_admitted=first_statuses["admitted"],
                eventual_admitted=eventual_statuses["admitted"],
                first_pass=awaiting_review_stage.first_pass,
                eventual_success=awaiting_review_stage.eventual_success,
                bounded_recovery=(
                    not awaiting_review_stage.operator_intervention
                    and any(
                        stage.recovery_type == "bounded_recovery" for stage in stages
                    )
                ),
                operator_intervention=any(
                    stage.operator_intervention for stage in stages
                ),
                terminal_failure=any(stage.terminal_failure for stage in stages),
                verified_replay=any(stage.verified_replay for stage in stages),
                attempts_required=awaiting_review_stage.attempts_required,
                terminal_disposition=terminal_disposition,
                stages=stages,
            )
        )
    return tuple(entities)


def _first_attempt_stage(
    *,
    from_state: str,
    to_state: str,
    first_attempt: dict[str, Any],
    attempts: list[dict[str, Any]],
    first_statuses: dict[str, bool],
    eventual_statuses: dict[str, bool],
    stages_by_attempt: dict[str, list[dict[str, Any]]],
    usage_events: list[dict[str, Any]],
    usage_attribution_available: bool,
    operator_requeue: bool,
    automatic_queue_failure_code: str,
) -> ValidationReliabilityFirstAttemptStage:
    first_records = stages_by_attempt.get(str(first_attempt["attempt_id"]), [])
    first_failure = _causal_first_failure(
        first_records,
        to_state,
        states=_A21_STATE_SEQUENCE,
        stage_groups=_A21_STATE_STAGE_GROUPS,
    )
    successful_attempt = next(
        (
            attempt
            for attempt in attempts
            if _a21_cascaded_state_statuses(
                stages_by_attempt.get(str(attempt["attempt_id"]), []),
                report_id=str(first_attempt["report_id"]),
                awaiting_review_report_ids=frozenset({str(first_attempt["report_id"])})
                if eventual_statuses["awaiting_review"]
                else frozenset(),
            )[to_state]
        ),
        None,
    )
    attempts_through_success = (
        [
            attempt
            for attempt in attempts
            if int(attempt["attempt_number"])
            <= int(successful_attempt["attempt_number"])
        ]
        if successful_attempt is not None
        else attempts
    )
    recovery_records = _recovery_records_through_state(
        attempts=attempts_through_success,
        stages_by_attempt=stages_by_attempt,
        to_state=to_state,
        states=_A21_STATE_SEQUENCE,
        stage_groups=_A21_STATE_STAGE_GROUPS,
    )
    first_attempt_recovery_records = _recovery_records_through_state(
        attempts=[first_attempt],
        stages_by_attempt=stages_by_attempt,
        to_state=to_state,
        states=_A21_STATE_SEQUENCE,
        stage_groups=_A21_STATE_STAGE_GROUPS,
    )
    operator_intervention = any(
        str(record["repair_disposition"]) == "operator_intervention"
        for record in recovery_records
    ) or (to_state == "awaiting_review" and operator_requeue)
    first_pass = (
        first_statuses[to_state]
        and not _has_recovery_disposition(first_attempt_recovery_records)
        and not (to_state == "awaiting_review" and operator_requeue)
        and not (to_state == "awaiting_review" and automatic_queue_failure_code)
    )
    eventual_success = eventual_statuses[to_state]
    recovery_type = _first_attempt_recovery_type(
        first_pass=first_pass,
        successful_attempt=successful_attempt,
        first_attempt=first_attempt,
        recovery_records=recovery_records,
        operator_intervention=operator_intervention,
        automatic_queue_failure_code=automatic_queue_failure_code,
    )
    terminal_disposition = _terminal_disposition(
        attempts=attempts,
        stages_by_attempt=stages_by_attempt,
        eventual_success=eventual_success,
    )
    terminal_failure = (
        not eventual_success and terminal_disposition in _TERMINAL_FAILURE_OUTCOMES
    )
    usage_records = stages_by_attempt.get(
        str((successful_attempt or attempts[-1])["attempt_id"]), []
    )
    usage_until = _stage_completion_time(
        records=usage_records,
        state=to_state,
        fallback=(
            str(first_failure["completed_at_utc"])
            if first_failure is not None
            else max(
                (str(record["completed_at_utc"]) for record in usage_records),
                default="",
            )
        ),
        stage_groups=_A21_STATE_STAGE_GROUPS,
    )
    usage = _usage_through_time(
        usage_events=usage_events,
        report_id=str(first_attempt["report_id"]),
        completed_at_utc=usage_until,
        available=usage_attribution_available,
    )
    first_failure_code, first_failure_stage = _first_attempt_causal_reason(
        first_pass=first_pass,
        first_failure=first_failure,
        first_attempt_recovery_records=first_attempt_recovery_records,
        to_state=to_state,
        operator_intervention=operator_intervention,
        automatic_queue_failure_code=automatic_queue_failure_code,
    )
    return ValidationReliabilityFirstAttemptStage(
        schema_version=_SCHEMA_VERSION,
        from_state=from_state,
        to_state=to_state,
        first_pass=first_pass,
        eventual_success=eventual_success,
        first_failure_code=first_failure_code,
        first_failure_stage=first_failure_stage,
        recovery_type=recovery_type,
        attempts_required=len(attempts_through_success),
        operator_intervention=operator_intervention,
        terminal_failure=terminal_failure,
        verified_replay=_has_verified_repeat_publication(
            attempts=attempts_through_success,
            stages_by_attempt=stages_by_attempt,
        ),
        terminal_disposition=terminal_disposition,
        usage_attribution=("available" if usage is not None else "unavailable"),
        provider_call_count_before_recovery=(int(usage["calls"]) if usage else None),
        input_tokens_before_recovery=(int(usage["input_tokens"]) if usage else None),
        output_tokens_before_recovery=(int(usage["output_tokens"]) if usage else None),
        total_tokens_before_recovery=(int(usage["total_tokens"]) if usage else None),
        estimated_cost_usd_before_recovery=(float(usage["cost"]) if usage else None),
    )


def _cascaded_state_statuses(records: list[dict[str, Any]]) -> dict[str, bool]:
    raw_statuses = _state_statuses(records)
    statuses: dict[str, bool] = {}
    prior_completed = True
    for state in _STATE_SEQUENCE:
        statuses[state] = raw_statuses[state] and prior_completed
        prior_completed = statuses[state]
    return statuses


def _a21_cascaded_state_statuses(
    records: list[dict[str, Any]],
    *,
    report_id: str,
    awaiting_review_report_ids: frozenset[str],
) -> dict[str, bool]:
    raw_statuses = _state_statuses(records)
    preflight_succeeded = any(
        str(record["stage"]) == "publication_preflight"
        and str(record["terminal_outcome"]) in _COMPLETED_OUTCOMES
        for record in records
    )
    raw_statuses["awaiting_review"] = (
        preflight_succeeded and report_id in awaiting_review_report_ids
    )
    statuses: dict[str, bool] = {}
    prior_completed = True
    for state in _A21_STATE_SEQUENCE:
        statuses[state] = raw_statuses[state] and prior_completed
        prior_completed = statuses[state]
    return statuses


def _first_failure_for_state(
    records: list[dict[str, Any]],
    to_state: str,
    *,
    stage_groups: dict[str, tuple[str, ...]] = _STATE_STAGE_GROUPS,
) -> dict[str, Any] | None:
    failures = [
        record
        for record in records
        if str(record["stage"]) in stage_groups[to_state]
        and str(record["terminal_outcome"]) in _FAILURE_OUTCOMES
    ]
    return (
        min(
            failures,
            key=lambda record: (
                str(record["completed_at_utc"]),
                str(record["stage"]),
            ),
        )
        if failures
        else None
    )


def _causal_first_failure(
    records: list[dict[str, Any]],
    to_state: str,
    *,
    states: tuple[str, ...] = _STATE_SEQUENCE,
    stage_groups: dict[str, tuple[str, ...]] = _STATE_STAGE_GROUPS,
) -> dict[str, Any] | None:
    direct_failure = _first_failure_for_state(
        records, to_state, stage_groups=stage_groups
    )
    if direct_failure is not None:
        return direct_failure
    reachable_states = states[1 : states.index(to_state)]
    failures = [
        record
        for state in reachable_states
        for record in records
        if str(record["stage"]) in stage_groups[state]
        and str(record["terminal_outcome"]) in _FAILURE_OUTCOMES
    ]
    return (
        min(
            failures,
            key=lambda record: (
                str(record["completed_at_utc"]),
                next(
                    index
                    for index, state in enumerate(states)
                    if str(record["stage"]) in stage_groups[state]
                ),
                str(record["stage"]),
            ),
        )
        if failures
        else None
    )


def _first_attempt_causal_reason(
    *,
    first_pass: bool,
    first_failure: dict[str, Any] | None,
    first_attempt_recovery_records: list[dict[str, Any]],
    to_state: str,
    operator_intervention: bool,
    automatic_queue_failure_code: str,
) -> tuple[str, str]:
    """Give every lost first pass a retained code or stable generic cause."""

    if first_pass:
        return "", ""
    if first_failure is not None:
        return (
            str(first_failure["failure_code"] or "unknown_failure"),
            str(first_failure["stage"]),
        )
    if operator_intervention:
        return "operator_intervention", "workflow_queue"
    if automatic_queue_failure_code:
        return automatic_queue_failure_code, "publication_readiness"
    for record in first_attempt_recovery_records:
        disposition = str(record["repair_disposition"])
        if disposition in _REPAIR_CAUSAL_CODES:
            return _REPAIR_CAUSAL_CODES[disposition], str(record["stage"])
        if (
            str(record["stage"]) in _EXPLICIT_REPAIR_STAGES
            and str(record["terminal_outcome"]) != "skipped"
        ):
            return "structured_output_repair", str(record["stage"])
    if to_state == "awaiting_review":
        return "awaiting_review_not_reached", "publication_preflight"
    return "first_attempt_transition_incomplete", to_state


def _first_attempt_recovery_type(
    *,
    first_pass: bool,
    successful_attempt: dict[str, Any] | None,
    first_attempt: dict[str, Any],
    recovery_records: list[dict[str, Any]],
    operator_intervention: bool,
    automatic_queue_failure_code: str,
) -> str:
    if first_pass:
        return "not_required"
    if successful_attempt is None:
        return "terminal_failure"
    if operator_intervention:
        return "operator_intervention"
    if automatic_queue_failure_code:
        return "bounded_recovery"
    if int(successful_attempt["attempt_number"]) > int(first_attempt["attempt_number"]):
        return "bounded_recovery"
    if _has_automatic_recovery_disposition(recovery_records):
        return "bounded_recovery"
    return "not_required"


def _recovery_records_through_state(
    *,
    attempts: list[dict[str, Any]],
    stages_by_attempt: dict[str, list[dict[str, Any]]],
    to_state: str,
    states: tuple[str, ...] = _STATE_SEQUENCE,
    stage_groups: dict[str, tuple[str, ...]] = _STATE_STAGE_GROUPS,
) -> list[dict[str, Any]]:
    relevant_stages = {
        stage
        for state in states[1 : states.index(to_state) + 1]
        for stage in stage_groups[state]
    }
    if states.index(to_state) >= states.index("evidence_complete"):
        relevant_stages.update(_EXPLICIT_REPAIR_STAGES)
    return [
        record
        for attempt in attempts
        for record in stages_by_attempt.get(str(attempt["attempt_id"]), [])
        if str(record["stage"]) in relevant_stages
    ]


def _has_recovery_disposition(records: list[dict[str, Any]]) -> bool:
    return any(
        str(record["repair_disposition"]) not in {"", "none", "not_required"}
        or (
            str(record["stage"]) in _EXPLICIT_REPAIR_STAGES
            and str(record["terminal_outcome"]) != "skipped"
        )
        for record in records
    )


def _has_automatic_recovery_disposition(records: list[dict[str, Any]]) -> bool:
    return any(
        (
            str(record["repair_disposition"]) in _AUTOMATIC_RECOVERY_DISPOSITIONS
            and str(record["repair_disposition"]) not in {"none", "not_required"}
        )
        or (
            str(record["stage"]) in _EXPLICIT_REPAIR_STAGES
            and str(record["terminal_outcome"]) != "skipped"
        )
        for record in records
    )


def _has_verified_repeat_publication(
    *,
    attempts: list[dict[str, Any]],
    stages_by_attempt: dict[str, list[dict[str, Any]]],
) -> bool:
    """Accept only the retained zero-write repeat-publication verification."""

    return any(
        str(record["stage"]) == "repeat_publication"
        and str(record["terminal_outcome"]) == "succeeded"
        and str(record["idempotency_state"]) == "reused"
        for attempt in attempts
        for record in stages_by_attempt.get(str(attempt["attempt_id"]), [])
    )


def _terminal_disposition(
    *,
    attempts: list[dict[str, Any]],
    stages_by_attempt: dict[str, list[dict[str, Any]]],
    eventual_success: bool,
) -> str:
    terminal_rows = [
        record
        for attempt in attempts
        for record in stages_by_attempt.get(str(attempt["attempt_id"]), [])
        if int(record.get("entity_terminal") or 0) == 1
    ]
    if terminal_rows:
        latest = max(
            terminal_rows,
            key=lambda record: (
                str(record["completed_at_utc"]),
                str(record["stage"]),
            ),
        )
        return str(latest["terminal_outcome"])
    return "succeeded" if eventual_success else "incomplete"


def _stage_completion_time(
    *,
    records: list[dict[str, Any]],
    state: str,
    fallback: str,
    stage_groups: dict[str, tuple[str, ...]] = _STATE_STAGE_GROUPS,
) -> str:
    completed = [
        str(record["completed_at_utc"])
        for record in records
        if str(record["stage"]) in stage_groups[state]
        and str(record["terminal_outcome"]) in _COMPLETED_OUTCOMES
    ]
    return max(completed, default=fallback)


def _usage_through_time(
    *,
    usage_events: list[dict[str, Any]],
    report_id: str,
    completed_at_utc: str,
    available: bool,
) -> dict[str, int | float] | None:
    if not available:
        return None
    relevant = [
        row
        for row in usage_events
        if str(row["report_id"]) == report_id
        and (not completed_at_utc or str(row["timestamp_utc"]) <= completed_at_utc)
    ]
    return {
        "calls": len(relevant),
        "input_tokens": sum(int(row["input_tokens"] or 0) for row in relevant),
        "output_tokens": sum(int(row["output_tokens"] or 0) for row in relevant),
        "total_tokens": sum(int(row["total_tokens"] or 0) for row in relevant),
        "cost": round(
            sum(float(row["estimated_cost_usd"] or 0.0) for row in relevant), 6
        ),
    }


def _transition_metric(
    *,
    from_state: str,
    to_state: str,
    completed_states: dict[str, set[str]],
) -> ValidationReliabilityTransition:
    eligible = len(completed_states[from_state])
    completed = len(completed_states[from_state] & completed_states[to_state])
    return ValidationReliabilityTransition(
        schema_version=_SCHEMA_VERSION,
        from_state=from_state,
        to_state=to_state,
        eligible_entity_count=eligible,
        completed_entity_count=completed,
        conversion_rate=_rate(completed, eligible),
    )


def _first_attempt_transition_metrics(
    entities: tuple[ValidationReliabilityFirstAttemptEntity, ...],
) -> tuple[ValidationReliabilityFirstAttemptTransition, ...]:
    metrics: list[ValidationReliabilityFirstAttemptTransition] = []
    for from_state, to_state in zip(
        _A21_STATE_SEQUENCE, _A21_STATE_SEQUENCE[1:], strict=False
    ):
        stage_rows = [
            next(stage for stage in entity.stages if stage.to_state == to_state)
            for entity in entities
        ]
        first_eligible = sum(
            _first_attempt_state(entity, from_state) for entity in entities
        )
        eventual_eligible = sum(
            _eventual_state(entity, from_state) for entity in entities
        )
        first_passed = sum(
            stage.first_pass
            for entity, stage in zip(entities, stage_rows, strict=True)
            if _first_attempt_state(entity, from_state)
        )
        eventual_succeeded = sum(
            stage.eventual_success
            for entity, stage in zip(entities, stage_rows, strict=True)
            if _eventual_state(entity, from_state)
        )
        first_eligible_stage_rows = [
            stage
            for entity, stage in zip(entities, stage_rows, strict=True)
            if _first_attempt_state(entity, from_state)
        ]
        metrics.append(
            ValidationReliabilityFirstAttemptTransition(
                schema_version=_SCHEMA_VERSION,
                from_state=from_state,
                to_state=to_state,
                first_attempt_eligible_entity_count=first_eligible,
                first_pass_entity_count=first_passed,
                first_pass_conversion_rate=_rate(first_passed, first_eligible),
                eventual_eligible_entity_count=eventual_eligible,
                eventual_success_entity_count=eventual_succeeded,
                eventual_conversion_rate=_rate(eventual_succeeded, eventual_eligible),
                bounded_recovery_entity_count=sum(
                    stage.recovery_type == "bounded_recovery"
                    for stage in first_eligible_stage_rows
                ),
                bounded_recovery_rate=_rate(
                    sum(
                        stage.recovery_type == "bounded_recovery"
                        for stage in first_eligible_stage_rows
                    ),
                    first_eligible,
                ),
                operator_intervention_entity_count=sum(
                    stage.operator_intervention for stage in first_eligible_stage_rows
                ),
                operator_intervention_rate=_rate(
                    sum(
                        stage.operator_intervention
                        for stage in first_eligible_stage_rows
                    ),
                    first_eligible,
                ),
                terminal_failure_entity_count=sum(
                    stage.terminal_failure for stage in first_eligible_stage_rows
                ),
                terminal_failure_rate=_rate(
                    sum(stage.terminal_failure for stage in first_eligible_stage_rows),
                    first_eligible,
                ),
                verified_replay_entity_count=sum(
                    stage.verified_replay for stage in first_eligible_stage_rows
                ),
                verified_replay_rate=_rate(
                    sum(stage.verified_replay for stage in first_eligible_stage_rows),
                    first_eligible,
                ),
            )
        )
    return tuple(metrics)


def _first_attempt_state(
    entity: ValidationReliabilityFirstAttemptEntity, state: str
) -> bool:
    if state == "admitted":
        return entity.first_attempt_admitted
    return next(stage for stage in entity.stages if stage.to_state == state).first_pass


def _eventual_state(
    entity: ValidationReliabilityFirstAttemptEntity, state: str
) -> bool:
    if state == "admitted":
        return entity.eventual_admitted
    return next(
        stage for stage in entity.stages if stage.to_state == state
    ).eventual_success


def _first_attempt_failure_pareto(
    entities: tuple[ValidationReliabilityFirstAttemptEntity, ...],
) -> tuple[ValidationFailureParetoEntry, ...]:
    failures = []
    for entity in entities:
        if entity.first_pass:
            continue
        final_stage = next(
            stage for stage in entity.stages if stage.to_state == "awaiting_review"
        )
        failures.append(
            {
                "failure_code": final_stage.first_failure_code,
                "from_state": final_stage.from_state,
                "to_state": final_stage.to_state,
            }
        )
    return _failure_pareto(failures)


def _failure_transition_metrics(
    failures: list[dict[str, Any]],
) -> tuple[ValidationReliabilityFailureTransition, ...]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for failure in failures:
        grouped[(failure["from_state"], failure["to_state"])].append(failure)
    result: list[ValidationReliabilityFailureTransition] = []
    for (from_state, to_state), rows in sorted(
        grouped.items(),
        key=lambda item: (
            _STATE_SEQUENCE.index(item[0][0]),
            _STATE_SEQUENCE.index(item[0][1]),
        ),
    ):
        failure_codes = Counter(str(row["failure_code"]) for row in rows)
        durations = [int(row["duration_ms"]) for row in rows]
        result.append(
            ValidationReliabilityFailureTransition(
                schema_version=_SCHEMA_VERSION,
                from_state=from_state,
                to_state=to_state,
                failure_count=len(rows),
                failure_codes=tuple(
                    ValidationReliabilityFailureCode(
                        schema_version=_SCHEMA_VERSION,
                        failure_code=code,
                        failure_count=count,
                    )
                    for code, count in sorted(
                        failure_codes.items(), key=lambda item: (-item[1], item[0])
                    )
                ),
                median_duration_ms=_percentile(durations, 50),
                p95_duration_ms=_percentile(durations, 95),
                provider_call_count_before_failure=sum(
                    int(row["usage"]["calls"]) for row in rows
                ),
                input_tokens_before_failure=sum(
                    int(row["usage"]["input_tokens"]) for row in rows
                ),
                output_tokens_before_failure=sum(
                    int(row["usage"]["output_tokens"]) for row in rows
                ),
                total_tokens_before_failure=sum(
                    int(row["usage"]["total_tokens"]) for row in rows
                ),
                estimated_cost_usd_before_failure=round(
                    sum(float(row["usage"]["cost"]) for row in rows), 6
                ),
                successful_recovery_count=sum(bool(row["recovered"]) for row in rows),
                successful_recovery_rate=_rate(
                    sum(bool(row["recovered"]) for row in rows), len(rows)
                ),
                operator_intervention_count=sum(
                    bool(row["operator_intervention"]) for row in rows
                ),
                operator_intervention_rate=_rate(
                    sum(bool(row["operator_intervention"]) for row in rows), len(rows)
                ),
                full_rerun_count=sum(bool(row["full_rerun"]) for row in rows),
                full_rerun_rate=_rate(
                    sum(bool(row["full_rerun"]) for row in rows), len(rows)
                ),
            )
        )
    return tuple(result)


def _failure_pareto(
    failures: list[dict[str, Any]],
) -> tuple[ValidationFailureParetoEntry, ...]:
    counts = Counter(str(row["failure_code"]) for row in failures)
    transitions: dict[str, set[str]] = defaultdict(set)
    for failure in failures:
        transitions[str(failure["failure_code"])].add(
            f"{failure['from_state']}->{failure['to_state']}"
        )
    total = sum(counts.values())
    cumulative = 0
    entries: list[ValidationFailureParetoEntry] = []
    for rank, (code, count) in enumerate(
        sorted(counts.items(), key=lambda item: (-item[1], item[0])), start=1
    ):
        cumulative += count
        entries.append(
            ValidationFailureParetoEntry(
                schema_version=_SCHEMA_VERSION,
                rank=rank,
                failure_code=code,
                failure_count=count,
                cumulative_failure_count=cumulative,
                cumulative_failure_rate=_rate(cumulative, total),
                transition_pairs=tuple(sorted(transitions[code])),
            )
        )
    return tuple(entries)


def _duration_ms(started_at_utc: str, completed_at_utc: str) -> int:
    try:
        started = datetime.fromisoformat(started_at_utc.replace("Z", "+00:00"))
        completed = datetime.fromisoformat(completed_at_utc.replace("Z", "+00:00"))
    except ValueError:
        return 0
    return max(0, int((completed - started).total_seconds() * 1000))


def _percentile(values: list[int], percentile: int) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = max(0, (len(ordered) * percentile + 99) // 100 - 1)
    return ordered[min(index, len(ordered) - 1)]


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def _artifact_hash(artifact: ValidationReliabilityArtifact) -> str:
    payload = asdict(replace(artifact, artifact_hash=""))
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def _canonical_bytes(payload: object) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
