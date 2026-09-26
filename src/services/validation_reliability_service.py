"""Canonical deterministic reliability telemetry for immutable validation runs."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, TypedDict

from src.contracts.regeneration import FailureFingerprint
from src.contracts.run_context import RunContext
from src.contracts.validation_reliability import (
    ValidationFailureParetoEntry,
    ValidationReliabilityArtifact,
    ValidationReliabilityBenchmarkCaseAttribution,
    ValidationReliabilityBuildRequest,
    ValidationReliabilityFailureCode,
    ValidationReliabilityFailureTransition,
    ValidationReliabilityFirstAttemptEntity,
    ValidationReliabilityFirstAttemptStage,
    ValidationReliabilityFirstAttemptTransition,
    ValidationReliabilityRepairAttempt,
    ValidationReliabilityRepairFailureClass,
    ValidationReliabilityRepairModeMetric,
    ValidationReliabilityRepairScorecard,
    ValidationReliabilityTransition,
    ValidationReliabilityWriteRequest,
    ValidationReliabilityWriteResponse,
)
from src.services._report_store_service.connection import _metadata_conn
from src.utils.errors import AppError
from src.utils.logging import log_event

_SCHEMA_VERSION = "1.2"
_REQUEST_SCHEMA_VERSION = "1.0"
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
_SAFE_REPAIR_TOKEN = re.compile(r"^[A-Za-z0-9._:-]{1,160}$")
_SAFE_REPAIR_PATH = re.compile(r"^[A-Za-z0-9._:/\[\]-]{1,256}$")


@dataclass(frozen=True)
class _A21StateEvidence:
    """Read-only canonical queue evidence associated with report identities."""

    awaiting_review_report_ids: frozenset[str] = frozenset()
    operator_requeue_report_ids: frozenset[str] = frozenset()
    automatic_queue_failure_codes: tuple[tuple[str, str], ...] = ()


class _RepairUsage(TypedDict):
    calls: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost: float


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
        repair_scorecard=_repair_scorecard(
            request=request,
            run=run,
            attempts=attempts,
            usage_events=usage_events,
            usage_attribution_available=usage_attribution_available,
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

    if (
        request.schema_version != _REQUEST_SCHEMA_VERSION
        or not request.artifact_path.strip()
    ):
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
        schema_version=_REQUEST_SCHEMA_VERSION,
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
    if request.schema_version != _REQUEST_SCHEMA_VERSION:
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
            for candidate_report_id, failure_code in (
                evidence.automatic_queue_failure_codes
            )
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
                       action, semantic_task, prompt_namespace, prompt_hash,
                       policy_namespace,
                       provider, model, input_tokens, output_tokens, total_tokens,
                       estimated_cost_usd, cache_decision, repair_attempt,
                       configuration_hash, policy_hash, producer_build_identity,
                       model_policy_namespace
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


def _repair_scorecard(
    *,
    request: ValidationReliabilityBuildRequest,
    run: dict[str, Any],
    attempts: list[dict[str, Any]],
    usage_events: list[dict[str, Any]],
    usage_attribution_available: bool,
) -> ValidationReliabilityRepairScorecard:
    """Aggregate only cohort-bound, content-free candidate audit records."""

    benchmark_manifest = None
    benchmark_manifest_sha256 = ""
    if request.repair_benchmark_manifest_path.strip():
        benchmark_manifest, benchmark_manifest_sha256 = _read_repair_benchmark_manifest(
            Path(request.repair_benchmark_manifest_path)
        )
        if benchmark_manifest is None:
            return _unavailable_repair_scorecard(
                incompatible_audit_count=1,
                benchmark_comparison_status="incompatible",
            )

    benchmark_baseline_identity_sha256 = (
        hashlib.sha256(
            _canonical_bytes(benchmark_manifest["baseline_identity"])
        ).hexdigest()
        if benchmark_manifest is not None
        else ""
    )
    benchmark_case_count = (
        len(benchmark_manifest["cases"]) if benchmark_manifest is not None else None
    )
    benchmark_case_attributions = tuple(request.repair_benchmark_case_attributions)
    if benchmark_case_attributions and (
        benchmark_manifest is None
        or not _benchmark_case_attributions_valid(
            benchmark_case_attributions,
            manifest=benchmark_manifest,
            run=run,
        )
    ):
        return _unavailable_repair_scorecard(
            incompatible_audit_count=1,
            benchmark_case_count=benchmark_case_count,
            benchmark_manifest_sha256=benchmark_manifest_sha256,
            baseline_identity_sha256=benchmark_baseline_identity_sha256,
            benchmark_comparison_status="incompatible",
        )

    root_text = request.repair_evidence_root.strip()
    if not root_text:
        return _unavailable_repair_scorecard(
            incompatible_audit_count=0,
            benchmark_case_count=benchmark_case_count,
            benchmark_manifest_sha256=benchmark_manifest_sha256,
            baseline_identity_sha256=benchmark_baseline_identity_sha256,
        )
    root = Path(root_text)
    if not root.is_dir():
        return _unavailable_repair_scorecard(
            incompatible_audit_count=0,
            benchmark_case_count=benchmark_case_count,
            benchmark_manifest_sha256=benchmark_manifest_sha256,
            baseline_identity_sha256=benchmark_baseline_identity_sha256,
        )

    cohort_report_ids = {
        str(row["report_id"])
        for row in attempts
        if str(row.get("cohort_disposition") or "") == "final_validation"
    }
    raw_audits: list[tuple[Path, dict[str, Any]]] = []
    incompatible_count = 0
    for path in sorted(root.rglob("regeneration_candidate_audit_*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            incompatible_count += 1
            continue
        if not isinstance(payload, dict):
            incompatible_count += 1
            continue
        if not _audit_matches_reliability_run(
            payload=payload,
            run=run,
            cohort_report_ids=cohort_report_ids,
        ):
            incompatible_count += 1
            continue
        raw_audits.append((path, payload))

    if benchmark_case_attributions:
        attribution_by_report = {
            case.report_id: case for case in benchmark_case_attributions
        }
        for _, audit in raw_audits:
            attribution = attribution_by_report.get(str(audit.get("report_id") or ""))
            expected_identity = (
                attribution.candidate_validation_identity
                if attribution is not None
                else None
            )
            observed_identity = (audit.get("repair_delta") or {}).get(
                "validator_identity"
            )
            if (
                expected_identity is None
                or str(observed_identity or "") != expected_identity.validator_identity
            ):
                incompatible_count += 1

    if incompatible_count:
        return _unavailable_repair_scorecard(
            incompatible_audit_count=incompatible_count,
            benchmark_case_count=benchmark_case_count,
            benchmark_manifest_sha256=benchmark_manifest_sha256,
            baseline_identity_sha256=benchmark_baseline_identity_sha256,
            benchmark_comparison_status="incompatible",
        )
    if not raw_audits and not benchmark_case_attributions:
        if benchmark_manifest is not None and benchmark_manifest.get("cases"):
            return _unavailable_repair_scorecard(
                incompatible_audit_count=0,
                benchmark_case_count=benchmark_case_count,
                benchmark_manifest_sha256=benchmark_manifest_sha256,
                baseline_identity_sha256=benchmark_baseline_identity_sha256,
            )
        return ValidationReliabilityRepairScorecard(
            schema_version=_SCHEMA_VERSION,
            measurement_status="available",
            cohort_compatible=True,
            repair_chain_count=0,
            repair_attempt_count=0,
            success_at_1_count=None,
            success_at_1_rate=None,
            success_at_3_count=None,
            success_at_3_rate=None,
            rolled_back_attempt_count=0,
            abstention_or_removal_attempt_count=0,
            out_of_scope_mutation_attempt_count=0,
            repeated_failed_strategy_evidence_attempt_count=0,
            repeated_failed_candidate_attempt_count=0,
            incompatible_audit_count=0,
            hard_failure_introduction_count=0,
            benchmark_case_count=None,
            benchmark_denominator_complete=False,
            benchmark_manifest_sha256="",
            baseline_identity_sha256="",
            current_identity_sha256="",
            hard_failure_introduction_attempt_count=0,
            hard_failure_introduction_rate=None,
            unsupported_evidence_introduction_attempt_count=0,
            deterministic_repair_share=None,
            model_repair_share=None,
            usage_attribution="unavailable",
            model_call_count=None,
            input_tokens=None,
            output_tokens=None,
            total_tokens=None,
            estimated_cost_usd=None,
            latency_ms=None,
            current_residual_failure_odds=None,
            current_residual_failure_odds_state="unavailable",
            baseline_success_at_3_count=None,
            baseline_success_at_3_rate=None,
            baseline_usage_attribution="unavailable",
            baseline_model_call_count=None,
            baseline_input_tokens=None,
            baseline_output_tokens=None,
            baseline_total_tokens=None,
            baseline_estimated_cost_usd=None,
            baseline_latency_ms=None,
            baseline_residual_failure_odds=None,
            baseline_residual_failure_odds_state="unavailable",
            residual_odds_reduction_factor=None,
            residual_odds_reduction_state="unavailable",
            benchmark_comparison_status="unavailable",
            failure_class_distribution=(),
            baseline_failure_class_distribution=(),
            attempts=(),
            mode_metrics=(),
        )

    repair_attempts: list[ValidationReliabilityRepairAttempt] = []
    seen_attempt_keys: set[tuple[str, int, str]] = set()
    for _, audit in raw_audits:
        attempt = _repair_attempt_from_audit(
            audit=audit,
            usage_events=usage_events,
            usage_attribution_available=usage_attribution_available,
        )
        key = (attempt.report_id, attempt.attempt_index, attempt.candidate_fingerprint)
        if key in seen_attempt_keys:
            return _unavailable_repair_scorecard(
                incompatible_audit_count=1,
                benchmark_case_count=benchmark_case_count,
                benchmark_manifest_sha256=benchmark_manifest_sha256,
                baseline_identity_sha256=benchmark_baseline_identity_sha256,
                benchmark_comparison_status="incompatible",
            )
        seen_attempt_keys.add(key)
        repair_attempts.append(attempt)
    repair_attempts.sort(
        key=lambda item: (
            item.report_id,
            item.attempt_index,
            item.candidate_fingerprint,
        )
    )
    if benchmark_manifest is not None:
        scope_limits = {
            str(case["report_id"]): set(case["expected_legal_mutation_scope"])
            for case in benchmark_manifest["cases"]
        }
        audit_by_attempt_key = {
            (
                str(audit["report_id"]),
                int(audit["attempt_index"]),
                _safe_hash(audit.get("after_sha256")),
            ): audit
            for _, audit in raw_audits
        }
        scoped_attempts: list[ValidationReliabilityRepairAttempt] = []
        for item in repair_attempts:
            audit = audit_by_attempt_key[
                (item.report_id, item.attempt_index, item.candidate_fingerprint)
            ]
            if not _audit_scope_within_limit(
                audit, scope_limits.get(item.report_id, set())
            ):
                item = replace(item, successful=False, out_of_scope_mutation=True)
            scoped_attempts.append(item)
        repair_attempts = scoped_attempts
    chains: dict[str, list[ValidationReliabilityRepairAttempt]] = defaultdict(list)
    for attempt in repair_attempts:
        chains[attempt.report_id].append(attempt)
    if benchmark_case_attributions:
        for case in benchmark_case_attributions:
            if case.reproducibility_status == "reproducible":
                chains.setdefault(case.report_id, [])
    for entries in chains.values():
        entries.sort(key=lambda item: item.attempt_index)
    chain_count = len(chains)
    success_at_1 = sum(
        any(item.successful for item in values[:1]) for values in chains.values()
    )
    success_at_3 = sum(
        any(item.successful for item in values[:3]) for values in chains.values()
    )
    usage_complete = bool(repair_attempts) and all(
        item.usage_attribution == "available" for item in repair_attempts
    )
    latency_complete = bool(repair_attempts) and all(
        item.latency_ms is not None for item in repair_attempts
    )
    repair_modes_complete = bool(repair_attempts) and all(
        item.repair_mode in {"deterministic", "model"} for item in repair_attempts
    )
    hard_failure_attribution_complete = bool(repair_attempts) and all(
        item.introduced_hard_failure_count is not None for item in repair_attempts
    )
    hard_failure_introduction_count = (
        sum(item.introduced_hard_failure_count or 0 for item in repair_attempts)
        if hard_failure_attribution_complete
        else None
    )
    hard_failure_introduction_attempt_count = (
        sum((item.introduced_hard_failure_count or 0) > 0 for item in repair_attempts)
        if hard_failure_attribution_complete
        else None
    )
    unsupported_evidence_attribution_complete = bool(raw_audits) and all(
        isinstance((audit.get("repair_delta") or {}).get("introduced"), list)
        for _, audit in raw_audits
    )
    unsupported_evidence_introductions = (
        sum(
            any(
                _unsupported_evidence_rule(rule_id)
                for rule_id in _failure_rule_ids_from_attempt(audit)
            )
            for _, audit in raw_audits
        )
        if unsupported_evidence_attribution_complete
        else None
    )
    scope_attribution_complete = bool(raw_audits) and all(
        _scope_outcome_attributable(audit) for _, audit in raw_audits
    )
    out_of_scope_mutation_count = (
        sum(item.out_of_scope_mutation for item in repair_attempts)
        if scope_attribution_complete
        else None
    )
    repeat_attribution_complete = bool(raw_audits) and all(
        _repeat_outcome_attributable(audit) for _, audit in raw_audits
    )
    failure_class_counts = Counter(
        rule_id for item in repair_attempts for rule_id in item.failure_rule_ids
    )
    current_odds, current_odds_state = _residual_failure_odds(
        denominator=chain_count, successes=success_at_3
    )
    benchmark_metrics = _benchmark_comparison_metrics(
        manifest=benchmark_manifest,
        current_attempts=repair_attempts,
        current_audits=[audit for _, audit in raw_audits],
        run=run,
        manifest_sha256=benchmark_manifest_sha256,
        current_schema_identity_sha256=request.current_schema_identity_sha256,
        case_attributions=benchmark_case_attributions,
    )
    attempt_by_key = {
        (item.report_id, item.attempt_index, item.candidate_fingerprint): item
        for item in repair_attempts
    }
    failed_audits = [
        audit
        for _, audit in raw_audits
        if not attempt_by_key[
            (
                str(audit["report_id"]),
                int(audit["attempt_index"]),
                _safe_hash(audit.get("after_sha256")),
            )
        ].successful
    ]
    repeated_strategy = _repeated_failed_attempt_count(
        failed_audits,
        key=lambda audit: _failed_strategy_evidence_key(audit, attempt_by_key),
    )
    repeated_candidate = _repeated_failed_attempt_count(
        failed_audits,
        key=lambda audit: _failed_candidate_key(audit),
    )
    return ValidationReliabilityRepairScorecard(
        schema_version=_SCHEMA_VERSION,
        measurement_status="available",
        cohort_compatible=True,
        repair_chain_count=chain_count,
        repair_attempt_count=len(repair_attempts),
        success_at_1_count=success_at_1,
        success_at_1_rate=(_rate(success_at_1, chain_count) if chain_count else None),
        success_at_3_count=success_at_3,
        success_at_3_rate=(_rate(success_at_3, chain_count) if chain_count else None),
        rolled_back_attempt_count=sum(
            item.promotion_outcome == "rolled_back" for item in repair_attempts
        ),
        abstention_or_removal_attempt_count=sum(
            item.abstention_or_removal for item in repair_attempts
        ),
        out_of_scope_mutation_attempt_count=out_of_scope_mutation_count,
        repeated_failed_strategy_evidence_attempt_count=(
            repeated_strategy if repeat_attribution_complete else None
        ),
        repeated_failed_candidate_attempt_count=(
            repeated_candidate if repeat_attribution_complete else None
        ),
        incompatible_audit_count=0,
        hard_failure_introduction_count=hard_failure_introduction_count,
        benchmark_case_count=benchmark_metrics["benchmark_case_count"],
        benchmark_denominator_complete=benchmark_metrics[
            "benchmark_denominator_complete"
        ],
        benchmark_manifest_sha256=benchmark_metrics["benchmark_manifest_sha256"],
        baseline_identity_sha256=benchmark_metrics["baseline_identity_sha256"],
        current_identity_sha256=benchmark_metrics["current_identity_sha256"],
        hard_failure_introduction_attempt_count=hard_failure_introduction_attempt_count,
        hard_failure_introduction_rate=(
            _rate(hard_failure_introduction_attempt_count, len(repair_attempts))
            if hard_failure_introduction_attempt_count is not None and repair_attempts
            else None
        ),
        unsupported_evidence_introduction_attempt_count=unsupported_evidence_introductions,
        deterministic_repair_share=(
            _rate(
                sum(item.repair_mode == "deterministic" for item in repair_attempts),
                len(repair_attempts),
            )
            if repair_modes_complete
            else None
        ),
        model_repair_share=(
            _rate(
                sum(item.repair_mode == "model" for item in repair_attempts),
                len(repair_attempts),
            )
            if repair_modes_complete
            else None
        ),
        usage_attribution="available" if usage_complete else "unavailable",
        model_call_count=(
            sum(item.model_call_count or 0 for item in repair_attempts)
            if usage_complete
            else None
        ),
        input_tokens=(
            sum(item.input_tokens or 0 for item in repair_attempts)
            if usage_complete
            else None
        ),
        output_tokens=(
            sum(item.output_tokens or 0 for item in repair_attempts)
            if usage_complete
            else None
        ),
        total_tokens=(
            sum(item.total_tokens or 0 for item in repair_attempts)
            if usage_complete
            else None
        ),
        estimated_cost_usd=(
            round(sum(item.estimated_cost_usd or 0.0 for item in repair_attempts), 6)
            if usage_complete
            else None
        ),
        latency_ms=(
            sum(item.latency_ms or 0 for item in repair_attempts)
            if latency_complete
            else None
        ),
        current_residual_failure_odds=current_odds,
        current_residual_failure_odds_state=current_odds_state,
        baseline_success_at_3_count=benchmark_metrics["baseline_success_at_3_count"],
        baseline_success_at_3_rate=benchmark_metrics["baseline_success_at_3_rate"],
        baseline_usage_attribution=benchmark_metrics["baseline_usage_attribution"],
        baseline_model_call_count=benchmark_metrics["baseline_model_call_count"],
        baseline_input_tokens=benchmark_metrics["baseline_input_tokens"],
        baseline_output_tokens=benchmark_metrics["baseline_output_tokens"],
        baseline_total_tokens=benchmark_metrics["baseline_total_tokens"],
        baseline_estimated_cost_usd=benchmark_metrics["baseline_estimated_cost_usd"],
        baseline_latency_ms=benchmark_metrics["baseline_latency_ms"],
        baseline_residual_failure_odds=benchmark_metrics[
            "baseline_residual_failure_odds"
        ],
        baseline_residual_failure_odds_state=benchmark_metrics[
            "baseline_residual_failure_odds_state"
        ],
        residual_odds_reduction_factor=benchmark_metrics[
            "residual_odds_reduction_factor"
        ],
        residual_odds_reduction_state=benchmark_metrics[
            "residual_odds_reduction_state"
        ],
        benchmark_comparison_status=benchmark_metrics["benchmark_comparison_status"],
        failure_class_distribution=tuple(
            ValidationReliabilityRepairFailureClass(
                schema_version=_SCHEMA_VERSION,
                failure_class=rule_id,
                attempt_count=count,
            )
            for rule_id, count in sorted(failure_class_counts.items())
        ),
        baseline_failure_class_distribution=benchmark_metrics[
            "baseline_failure_class_distribution"
        ],
        attempts=tuple(repair_attempts),
        mode_metrics=_repair_mode_metrics(repair_attempts),
        reproducible_case_count=(
            sum(
                case.reproducibility_status == "reproducible"
                for case in benchmark_case_attributions
            )
            if benchmark_case_attributions
            else None
        ),
        no_longer_reproducible_case_count=(
            sum(
                case.reproducibility_status == "no_longer_reproducible"
                for case in benchmark_case_attributions
            )
            if benchmark_case_attributions
            else None
        ),
        success_denominator=(chain_count if benchmark_case_attributions else None),
        benchmark_case_attributions=benchmark_case_attributions,
    )


def _unavailable_repair_scorecard(
    *,
    incompatible_audit_count: int,
    benchmark_case_count: int | None = None,
    benchmark_manifest_sha256: str = "",
    baseline_identity_sha256: str = "",
    benchmark_comparison_status: str = "unavailable",
) -> ValidationReliabilityRepairScorecard:
    return ValidationReliabilityRepairScorecard(
        schema_version=_SCHEMA_VERSION,
        measurement_status="unavailable",
        cohort_compatible=False,
        repair_chain_count=None,
        repair_attempt_count=None,
        success_at_1_count=None,
        success_at_1_rate=None,
        success_at_3_count=None,
        success_at_3_rate=None,
        rolled_back_attempt_count=None,
        abstention_or_removal_attempt_count=None,
        out_of_scope_mutation_attempt_count=None,
        repeated_failed_strategy_evidence_attempt_count=None,
        repeated_failed_candidate_attempt_count=None,
        incompatible_audit_count=incompatible_audit_count,
        hard_failure_introduction_count=None,
        benchmark_case_count=benchmark_case_count,
        benchmark_denominator_complete=False,
        benchmark_manifest_sha256=benchmark_manifest_sha256,
        baseline_identity_sha256=baseline_identity_sha256,
        current_identity_sha256="",
        hard_failure_introduction_attempt_count=None,
        hard_failure_introduction_rate=None,
        unsupported_evidence_introduction_attempt_count=None,
        deterministic_repair_share=None,
        model_repair_share=None,
        usage_attribution="unavailable",
        model_call_count=None,
        input_tokens=None,
        output_tokens=None,
        total_tokens=None,
        estimated_cost_usd=None,
        latency_ms=None,
        current_residual_failure_odds=None,
        current_residual_failure_odds_state="unavailable",
        baseline_success_at_3_count=None,
        baseline_success_at_3_rate=None,
        baseline_usage_attribution="unavailable",
        baseline_model_call_count=None,
        baseline_input_tokens=None,
        baseline_output_tokens=None,
        baseline_total_tokens=None,
        baseline_estimated_cost_usd=None,
        baseline_latency_ms=None,
        baseline_residual_failure_odds=None,
        baseline_residual_failure_odds_state="unavailable",
        residual_odds_reduction_factor=None,
        residual_odds_reduction_state="unavailable",
        benchmark_comparison_status=benchmark_comparison_status,
        failure_class_distribution=(),
        baseline_failure_class_distribution=(),
        attempts=(),
        mode_metrics=(),
    )


def _read_repair_benchmark_manifest(path: Path) -> tuple[dict[str, Any] | None, str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None, ""
    if not isinstance(payload, dict) or payload.get("schema_version") not in {
        "1.0",
        "2.0",
    }:
        return None, ""
    declared_hash = _safe_hash(payload.get("manifest_sha256"))
    body = {key: value for key, value in payload.items() if key != "manifest_sha256"}
    actual_hash = hashlib.sha256(_canonical_bytes(body)).hexdigest()
    cases = payload.get("cases")
    baseline_identity = payload.get("baseline_identity")
    if (
        not declared_hash
        or declared_hash != actual_hash
        or payload.get("frozen") is not True
        or not isinstance(cases, list)
        or not cases
        or not isinstance(baseline_identity, dict)
    ):
        return None, ""
    report_ids: set[str] = set()
    for case in cases:
        if not isinstance(case, dict):
            return None, ""
        report_id = _safe_repair_token(case.get("report_id"))
        artifact_hash = _safe_hash(case.get("original_artifact_canonical_sha256"))
        initial_failures = case.get("initial_failure_fingerprints")
        baseline_attempts = case.get("baseline_attempts")
        evidence_hashes = case.get("evidence_pack_sha256")
        legal_scope = case.get("expected_legal_mutation_scope")
        identities = case.get("identities")
        historical_outcome = case.get("historical_outcome")
        if (
            not report_id
            or report_id in report_ids
            or not artifact_hash
            or not _safe_hash(case.get("initial_validation_sha256"))
            or not isinstance(initial_failures, list)
            or not initial_failures
            or not all(_safe_hash(item) for item in initial_failures)
            or not isinstance(evidence_hashes, dict)
            or not evidence_hashes
            or any(
                not _SAFE_REPAIR_TOKEN.fullmatch(str(name)) or not _safe_hash(value)
                for name, value in evidence_hashes.items()
            )
            or not isinstance(legal_scope, list)
            or not legal_scope
            or not all(
                isinstance(value, str) and _SAFE_REPAIR_PATH.fullmatch(value)
                for value in legal_scope
            )
            or not isinstance(identities, dict)
            or any(
                not _safe_repair_token(identities.get(name))
                for name in (
                    "prompt_identity_sha256",
                    "artifact_schema_identity",
                    "validator_identity",
                    "configuration_hash",
                    "policy_hash",
                    "producer_build_identity",
                )
            )
            or not _safe_repair_token(historical_outcome)
            or not isinstance(baseline_attempts, list)
            or not baseline_attempts
        ):
            return None, ""
        report_ids.add(report_id)
        for audit in baseline_attempts:
            if (
                not isinstance(audit, dict)
                or str(audit.get("report_id") or "") != report_id
                or not _audit_has_safe_benchmark_fields(audit)
            ):
                return None, ""
        first = min(baseline_attempts, key=lambda item: int(item["attempt_index"]))
        first_allowed_scope = first.get("allowed_paths")
        if (
            str(first.get("before_sha256") or "") != artifact_hash
            or not isinstance(first_allowed_scope, list)
            or not all(
                isinstance(value, str) and _SAFE_REPAIR_PATH.fullmatch(value)
                for value in first_allowed_scope
            )
            or sorted(set(first_allowed_scope)) != sorted(set(legal_scope))
            or str(identities.get("configuration_hash") or "")
            != str(first.get("configuration_hash") or "")
            or str(identities.get("policy_hash") or "")
            != str(first.get("policy_hash") or "")
            or str(identities.get("validator_identity") or "")
            != str(
                (first.get("repair_delta") or {}).get("validator_identity")
                or "unavailable"
            )
            or any(
                str(identities.get(field_name) or "")
                != str(baseline_identity.get(field_name) or "")
                for field_name in (
                    "configuration_hash",
                    "policy_hash",
                    "validator_identity",
                    "producer_build_identity",
                )
            )
            or str(identities.get("producer_build_identity") or "")
            != str(
                first.get("attested_producer_build_identity")
                or first.get("producer_build_identity")
                or ""
            )
            or identities.get("artifact_schema_identity")
            != f"schema-{baseline_identity.get('schema_identity_sha256')}"
        ):
            return None, ""
    for field_name in (
        "configuration_hash",
        "policy_hash",
        "producer_build_identity",
        "validator_identity",
    ):
        if not _safe_repair_token(baseline_identity.get(field_name)):
            return None, ""
    if not _safe_hash(baseline_identity.get("schema_identity_sha256")):
        return None, ""
    return payload, declared_hash


def _benchmark_case_attributions_valid(
    attributions: tuple[ValidationReliabilityBenchmarkCaseAttribution, ...],
    *,
    manifest: dict[str, Any],
    run: dict[str, Any],
) -> bool:
    expected_cases = {
        str(case["report_id"]): case for case in manifest.get("cases", [])
    }
    if len(attributions) != len(expected_cases):
        return False
    observed_reports: set[str] = set()
    for case in attributions:
        report_id = str(case.report_id)
        frozen_case = expected_cases.get(report_id)
        if (
            frozen_case is None
            or report_id in observed_reports
            or case.schema_version != "1.0"
            or str(case.case_id) != str(frozen_case.get("case_id") or report_id)
            or case.reproducibility_status
            not in {"reproducible", "no_longer_reproducible"}
            or any(
                isinstance(count, bool) or not isinstance(count, int) or count < 0
                for count in (
                    case.candidate_validation_attempt_count,
                    case.candidate_audit_count,
                )
            )
            or case.candidate_audit_count > case.candidate_validation_attempt_count
        ):
            return False
        observed_reports.add(report_id)
        historical = tuple(
            sorted(
                {str(value) for value in frozen_case["initial_failure_fingerprints"]}
            )
        )
        current = tuple(
            sorted({str(value) for value in case.current_baseline_failure_fingerprints})
        )
        current_issues = tuple(
            sorted({str(value) for value in case.current_baseline_issue_fingerprints})
        )
        if (
            tuple(sorted(set(case.historical_failure_fingerprints))) != historical
            or len(current) != len(case.current_baseline_failure_fingerprints)
            or len(current_issues) != len(case.current_baseline_issue_fingerprints)
            or not set(current).issubset(current_issues)
            or any(not _safe_hash(value) for value in (*current, *current_issues))
        ):
            return False
        reproduced = bool(set(historical) & set(current))
        if (case.reproducibility_status == "reproducible") != reproduced:
            return False
        identity = case.baseline_validation_identity
        if (
            identity.schema_version != "1.0"
            or not _safe_repair_token(identity.validator_identity)
            or not _safe_repair_token(identity.configuration_hash)
            or not _safe_repair_token(identity.policy_hash)
            or not _safe_repair_token(identity.producer_build_identity)
            or identity.configuration_hash != str(run.get("configuration_hash") or "")
            or identity.policy_hash != str(run.get("policy_hash") or "")
            or identity.producer_build_identity
            != str(run.get("producer_build_identity") or "")
        ):
            return False
        candidate_identity = case.candidate_validation_identity
        if case.candidate_validation_attempt_count == 0:
            if candidate_identity is not None:
                return False
        elif (
            case.reproducibility_status != "reproducible"
            or candidate_identity is None
            or candidate_identity.schema_version != "1.0"
            or candidate_identity != identity
        ):
            return False
    return observed_reports == set(expected_cases)


def _audit_has_safe_benchmark_fields(audit: dict[str, Any]) -> bool:
    delta = audit.get("repair_delta")
    return bool(
        isinstance(audit.get("attempt_index"), int)
        and not isinstance(audit.get("attempt_index"), bool)
        and int(audit["attempt_index"]) > 0
        and _safe_hash(audit.get("before_sha256"))
        and _safe_hash(audit.get("after_sha256"))
        and _safe_repair_token(audit.get("strategy_fingerprint"))
        and isinstance(delta, dict)
        and all(
            isinstance(delta.get(key, []), list)
            for key in ("resolved", "persisting", "introduced")
        )
        and all(
            _safe_repair_token(audit.get(field_name))
            for field_name in (
                "configuration_hash",
                "policy_hash",
                "producer_build_identity",
            )
        )
    )


def _benchmark_comparison_metrics(
    *,
    manifest: dict[str, Any] | None,
    current_attempts: list[ValidationReliabilityRepairAttempt],
    current_audits: list[dict[str, Any]],
    run: dict[str, Any],
    manifest_sha256: str,
    current_schema_identity_sha256: str,
    case_attributions: tuple[ValidationReliabilityBenchmarkCaseAttribution, ...] = (),
) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "benchmark_case_count": None,
        "benchmark_denominator_complete": False,
        "benchmark_manifest_sha256": manifest_sha256,
        "baseline_identity_sha256": "",
        "current_identity_sha256": "",
        "baseline_success_at_3_count": None,
        "baseline_success_at_3_rate": None,
        "baseline_usage_attribution": "unavailable",
        "baseline_model_call_count": None,
        "baseline_input_tokens": None,
        "baseline_output_tokens": None,
        "baseline_total_tokens": None,
        "baseline_estimated_cost_usd": None,
        "baseline_latency_ms": None,
        "baseline_residual_failure_odds": None,
        "baseline_residual_failure_odds_state": "unavailable",
        "residual_odds_reduction_factor": None,
        "residual_odds_reduction_state": "unavailable",
        "benchmark_comparison_status": "unavailable",
        "baseline_failure_class_distribution": (),
    }
    if manifest is None:
        return defaults

    cases = manifest["cases"]
    report_ids = {str(case["report_id"]) for case in cases}
    attribution_by_report = {case.report_id: case for case in case_attributions}
    attributed_replay = bool(case_attributions)
    reproducible_report_ids = (
        {
            case.report_id
            for case in case_attributions
            if case.reproducibility_status == "reproducible"
        }
        if attributed_replay
        else report_ids
    )
    baseline_attempts: list[ValidationReliabilityRepairAttempt] = []
    baseline_identity = manifest["baseline_identity"]
    baseline_ids_compatible = True
    for case in cases:
        raw_attempts = sorted(
            case["baseline_attempts"], key=lambda item: int(item["attempt_index"])
        )
        for audit in raw_attempts:
            observed_identity = {
                "configuration_hash": audit.get("configuration_hash"),
                "policy_hash": audit.get("policy_hash"),
                "producer_build_identity": audit.get(
                    "attested_producer_build_identity",
                    audit.get("producer_build_identity"),
                ),
                "validator_identity": (audit.get("repair_delta") or {}).get(
                    "validator_identity"
                ),
            }
            if any(
                str(observed_identity.get(key) or "")
                != str(baseline_identity.get(key) or "")
                for key in (
                    "configuration_hash",
                    "policy_hash",
                    "producer_build_identity",
                    "validator_identity",
                )
            ):
                baseline_ids_compatible = False
            baseline_attempts.append(
                _repair_attempt_from_audit(
                    audit=audit,
                    usage_events=[],
                    usage_attribution_available=False,
                )
            )

    baseline_chains: dict[str, list[ValidationReliabilityRepairAttempt]] = defaultdict(
        list
    )
    for item in baseline_attempts:
        baseline_chains[item.report_id].append(item)
    for values in baseline_chains.values():
        values.sort(key=lambda item: item.attempt_index)
    baseline_case_reports = {item.report_id for item in baseline_attempts}
    baseline_success_at_3 = sum(
        any(item.successful for item in values[:3])
        for values in baseline_chains.values()
    )
    baseline_odds, baseline_odds_state = _residual_failure_odds(
        denominator=len(baseline_chains), successes=baseline_success_at_3
    )
    baseline_class_counts = Counter(
        rule_id for item in baseline_attempts for rule_id in item.failure_rule_ids
    )
    baseline_latency_complete = bool(baseline_attempts) and all(
        item.latency_ms is not None for item in baseline_attempts
    )

    current_by_report: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for audit in current_audits:
        current_by_report[str(audit.get("report_id") or "")].append(audit)
    current_report_ids = set(current_by_report)
    expected_audit_report_ids = (
        {case.report_id for case in case_attributions if case.candidate_audit_count > 0}
        if attributed_replay
        else report_ids
    )
    input_hashes_match = current_report_ids == expected_audit_report_ids
    fingerprints_match = current_report_ids == expected_audit_report_ids
    for case in cases:
        report_id = str(case["report_id"])
        audits = sorted(
            current_by_report.get(report_id, []),
            key=lambda item: int(item.get("attempt_index") or 0),
        )
        attribution = attribution_by_report.get(report_id)
        if attributed_replay and attribution is not None:
            if len(audits) != attribution.candidate_audit_count:
                input_hashes_match = False
                fingerprints_match = False
            if not audits:
                continue
        elif not audits:
            input_hashes_match = False
            fingerprints_match = False
            continue
        first = audits[0]
        if str(first.get("before_sha256") or "") != str(
            case["original_artifact_canonical_sha256"]
        ):
            input_hashes_match = False
        delta = first.get("repair_delta")
        if not isinstance(delta, dict):
            fingerprints_match = False
        elif attributed_replay and attribution is not None:
            observed = tuple(
                sorted(
                    set(_fingerprints_from_delta(delta.get("resolved")))
                    | set(_fingerprints_from_delta(delta.get("persisting")))
                )
            )
            expected = tuple(
                sorted(set(attribution.current_baseline_issue_fingerprints))
            )
            fingerprints_match = fingerprints_match and observed == expected
        else:
            observed = tuple(
                sorted(
                    set(_fingerprints_from_delta(delta.get("resolved")))
                    | set(_fingerprints_from_delta(delta.get("persisting")))
                )
            )
            expected = tuple(sorted(set(case["initial_failure_fingerprints"])))
            fingerprints_match = fingerprints_match and observed == expected

    case_count = len(cases)
    current_case_attempts_complete = True
    for report_id in reproducible_report_ids:
        indexes = sorted(
            item.attempt_index
            for item in current_attempts
            if item.report_id == report_id
        )
        if indexes and indexes != list(range(1, len(indexes) + 1)):
            current_case_attempts_complete = False
    baseline_case_attempts_complete = True
    for report_id in report_ids:
        indexes = sorted(
            item.attempt_index
            for item in baseline_attempts
            if item.report_id == report_id
        )
        if not indexes or indexes != list(range(1, len(indexes) + 1)):
            baseline_case_attempts_complete = False
    current_validator_identities = (
        {
            case.baseline_validation_identity.validator_identity
            for case in case_attributions
        }
        if attributed_replay
        else {
            str((audit.get("repair_delta") or {}).get("validator_identity") or "")
            for audit in current_audits
        }
    )
    current_identity_compatible = (
        str(run.get("configuration_hash") or "")
        == str(baseline_identity.get("configuration_hash") or "")
        and str(run.get("policy_hash") or "")
        == str(baseline_identity.get("policy_hash") or "")
        and _safe_hash(current_schema_identity_sha256)
        == str(baseline_identity.get("schema_identity_sha256") or "")
        and current_validator_identities
        == {str(baseline_identity.get("validator_identity") or "")}
    )
    if attributed_replay:
        denominator_complete = (
            len(attribution_by_report) == case_count
            and set(attribution_by_report) == report_ids
            and len(baseline_case_reports) == case_count
            and current_report_ids == expected_audit_report_ids
            and {item.report_id for item in current_attempts} <= reproducible_report_ids
            and current_case_attempts_complete
            and baseline_case_attempts_complete
            and input_hashes_match
            and fingerprints_match
        )
    else:
        denominator_complete = (
            baseline_ids_compatible
            and current_identity_compatible
            and len(baseline_case_reports) == case_count
            and current_report_ids == report_ids
            and len({item.report_id for item in current_attempts}) == case_count
            and current_case_attempts_complete
            and baseline_case_attempts_complete
            and input_hashes_match
            and fingerprints_match
        )
    baseline_usage = manifest.get("baseline_usage")
    baseline_usage_metrics: dict[str, Any] = {}
    usage_status = "unavailable"
    if (
        isinstance(baseline_usage, dict)
        and baseline_usage.get("attribution") == "available"
    ):
        fields = (
            "model_call_count",
            "input_tokens",
            "output_tokens",
            "total_tokens",
            "estimated_cost_usd",
        )
        valid = all(
            isinstance(baseline_usage.get(name), (int, float))
            and not isinstance(baseline_usage.get(name), bool)
            and baseline_usage[name] >= 0
            for name in fields
        )
        if valid:
            usage_status = "available"
            baseline_usage_metrics = {
                f"baseline_{name}": (
                    round(float(baseline_usage[name]), 6)
                    if name == "estimated_cost_usd"
                    else int(baseline_usage[name])
                )
                for name in fields
            }

    current_identity_values = {
        "configuration_hash": str(run.get("configuration_hash") or ""),
        "policy_hash": str(run.get("policy_hash") or ""),
        "producer_build_identity": str(run.get("producer_build_identity") or ""),
        "schema_identity_sha256": current_schema_identity_sha256,
        "validator_identities": sorted(current_validator_identities),
    }
    baseline_identity_hash = hashlib.sha256(
        _canonical_bytes(baseline_identity)
    ).hexdigest()
    current_identity_hash = hashlib.sha256(
        _canonical_bytes(current_identity_values)
    ).hexdigest()
    result = {
        **defaults,
        "benchmark_case_count": case_count,
        "benchmark_denominator_complete": denominator_complete,
        "baseline_identity_sha256": baseline_identity_hash,
        "current_identity_sha256": current_identity_hash,
        "baseline_success_at_3_count": baseline_success_at_3,
        "baseline_success_at_3_rate": (
            _rate(baseline_success_at_3, len(baseline_chains))
            if baseline_chains
            else None
        ),
        "baseline_usage_attribution": usage_status,
        "baseline_latency_ms": (
            sum(item.latency_ms or 0 for item in baseline_attempts)
            if baseline_latency_complete
            else None
        ),
        "baseline_residual_failure_odds": baseline_odds,
        "baseline_residual_failure_odds_state": baseline_odds_state,
        "baseline_failure_class_distribution": tuple(
            ValidationReliabilityRepairFailureClass(
                schema_version=_SCHEMA_VERSION,
                failure_class=rule_id,
                attempt_count=count,
            )
            for rule_id, count in sorted(baseline_class_counts.items())
        ),
        "benchmark_comparison_status": (
            "paired"
            if (
                denominator_complete
                and baseline_ids_compatible
                and current_identity_compatible
                and len(reproducible_report_ids) == case_count
            )
            else "incompatible"
        ),
        **baseline_usage_metrics,
    }
    if (
        denominator_complete
        and baseline_ids_compatible
        and current_identity_compatible
        and len(reproducible_report_ids) == case_count
    ):
        result.update(
            _residual_odds_reduction(
                baseline=baseline_odds,
                baseline_state=baseline_odds_state,
                current_successes=sum(
                    any(item.successful for item in values[:3])
                    for values in _group_repair_attempts(current_attempts).values()
                ),
                current_denominator=(
                    len(reproducible_report_ids)
                    if attributed_replay
                    else len(_group_repair_attempts(current_attempts))
                ),
            )
        )
    return result


def _group_repair_attempts(
    attempts: list[ValidationReliabilityRepairAttempt],
) -> dict[str, list[ValidationReliabilityRepairAttempt]]:
    chains: dict[str, list[ValidationReliabilityRepairAttempt]] = defaultdict(list)
    for item in attempts:
        # One report has one atomic repair chain per validation run. Failure
        # fingerprints legitimately change as issues are resolved or introduced,
        # so they cannot be used to split the chain.
        chains[item.report_id].append(item)
    for values in chains.values():
        values.sort(key=lambda item: item.attempt_index)
    return chains


def _residual_odds_reduction(
    *,
    baseline: float | None,
    baseline_state: str,
    current_successes: int,
    current_denominator: int,
) -> dict[str, Any]:
    current, current_state = _residual_failure_odds(
        denominator=current_denominator, successes=current_successes
    )
    if baseline_state == "unbounded" and current_state == "available":
        return {
            "residual_odds_reduction_factor": None,
            "residual_odds_reduction_state": "unbounded",
        }
    if (
        baseline_state != "available"
        or current_state != "available"
        or baseline is None
        or current is None
    ):
        return {
            "residual_odds_reduction_factor": None,
            "residual_odds_reduction_state": (
                "baseline_ceiling"
                if baseline_state == "available" and baseline == 0
                else "unavailable"
            ),
        }
    if current == 0:
        return {
            "residual_odds_reduction_factor": None,
            "residual_odds_reduction_state": "unbounded",
        }
    if baseline == 0:
        return {
            "residual_odds_reduction_factor": None,
            "residual_odds_reduction_state": "baseline_ceiling",
        }
    return {
        "residual_odds_reduction_factor": baseline / current,
        "residual_odds_reduction_state": "available",
    }


def _audit_matches_reliability_run(
    *, payload: dict[str, Any], run: dict[str, Any], cohort_report_ids: set[str]
) -> bool:
    required_identity = {
        "validation_run_id": str(run["validation_run_id"]),
        "cohort_id": str(run["cohort_id"]),
        "workflow_run_id": str(run["workflow_run_id"]),
        "configuration_hash": str(run["configuration_hash"]),
        "policy_hash": str(run["policy_hash"]),
        "producer_build_identity": str(run["producer_build_identity"]),
    }
    if any(
        str(payload.get(key) or "") != value for key, value in required_identity.items()
    ):
        return False
    report_id = str(payload.get("report_id") or "")
    if not report_id or report_id not in cohort_report_ids:
        return False
    delta = payload.get("repair_delta")
    return bool(
        _safe_repair_token(payload.get("strategy_fingerprint"))
        and _safe_hash(payload.get("after_sha256"))
        and isinstance(delta, dict)
        and all(
            isinstance(delta.get(field_name), list)
            for field_name in ("resolved", "persisting", "introduced")
        )
        and isinstance(payload.get("attempt_index"), int)
        and int(payload["attempt_index"]) > 0
    )


def _scope_outcome_attributable(audit: dict[str, Any]) -> bool:
    delta = audit.get("repair_delta")
    return bool(
        isinstance(delta, dict)
        and delta.get("mutation_scope_result")
        in {
            "pass",
            "fail",
        }
    )


def _repeat_outcome_attributable(audit: dict[str, Any]) -> bool:
    delta = audit.get("repair_delta")
    return bool(
        isinstance(delta, dict)
        and _safe_hash(audit.get("before_sha256"))
        and _safe_hash(audit.get("after_sha256"))
        and _safe_repair_token(audit.get("strategy_fingerprint"))
        and isinstance(audit.get("selected_evidence_ids"), list)
        and _safe_repair_token(delta.get("validator_identity"))
        and all(
            isinstance(delta.get(field_name), list)
            for field_name in ("resolved", "persisting", "introduced")
        )
    )


def _repair_attempt_from_audit(
    *,
    audit: dict[str, Any],
    usage_events: list[dict[str, Any]],
    usage_attribution_available: bool,
) -> ValidationReliabilityRepairAttempt:
    delta = audit["repair_delta"]
    resolved = _fingerprints_from_delta(delta.get("resolved"))
    persisting = _fingerprints_from_delta(delta.get("persisting"))
    introduced = _fingerprints_from_delta(delta.get("introduced"))
    failures = tuple(sorted(set(resolved) | set(persisting)))
    failure_rule_ids = _failure_rule_ids_from_delta(
        delta.get("resolved"), delta.get("persisting"), delta.get("introduced")
    )
    validation_issues = tuple(
        token
        for item in list(audit.get("validation_issues") or [])
        if (token := _safe_repair_token(item))
    )
    repair_action = _safe_repair_token(audit.get("repair_action"))
    repair_strategy = _safe_repair_token(audit.get("repair_strategy"))
    abstention_or_removal = any(
        marker in f"{repair_action}:{repair_strategy}".lower()
        for marker in ("remove", "abstain")
    )
    introduced_rule_ids = _failure_rule_ids_from_delta(delta.get("introduced"))
    out_of_scope_mutation = (
        any(
            value.startswith("regeneration_scope_violation:")
            for value in validation_issues
        )
        or "regeneration_scope_violation" in introduced_rule_ids
        or (delta.get("mutation_scope_result") == "fail")
    )
    report_usage = [
        event
        for event in usage_events
        if str(event.get("report_id") or "") == str(audit["report_id"])
        and _is_regeneration_usage_event(event)
    ]
    matching_usage = [
        event
        for event in report_usage
        if int(event.get("repair_attempt") or 0) == int(audit["attempt_index"])
    ]
    has_unattributed_regeneration_usage = any(
        int(event.get("repair_attempt") or 0) <= 0 for event in report_usage
    )
    attribution_valid = (
        usage_attribution_available
        and not has_unattributed_regeneration_usage
        and all(
            str(event.get(field) or "") == str(audit[field])
            for event in matching_usage
            for field in (
                "validation_run_id",
                "cohort_id",
                "workflow_run_id",
                "configuration_hash",
                "policy_hash",
                "producer_build_identity",
            )
        )
    )
    usage = _repair_usage(matching_usage) if attribution_valid else None
    latency_raw = audit.get("latency_ms")
    latency_ms = (
        int(latency_raw)
        if isinstance(latency_raw, int)
        and not isinstance(latency_raw, bool)
        and latency_raw >= 0
        else None
    )
    raw_hard_failure_count = (audit.get("repair_delta") or {}).get(
        "introduced_hard_failure_count"
    )
    hard_failure_count = (
        int(raw_hard_failure_count)
        if isinstance(raw_hard_failure_count, int)
        and not isinstance(raw_hard_failure_count, bool)
        and raw_hard_failure_count >= 0
        else None
    )
    return ValidationReliabilityRepairAttempt(
        schema_version=_SCHEMA_VERSION,
        report_id=str(audit["report_id"]),
        attempt_index=int(audit["attempt_index"]),
        failure_rule_ids=failure_rule_ids,
        failure_fingerprints=failures,
        resolved_failure_fingerprints=resolved,
        persisting_failure_fingerprints=persisting,
        introduced_failure_fingerprints=introduced,
        introduced_hard_failure_count=hard_failure_count,
        strategy_fingerprint=_safe_repair_token(audit.get("strategy_fingerprint")),
        candidate_fingerprint=_safe_hash(audit.get("after_sha256")),
        repair_action=repair_action,
        repair_strategy=repair_strategy,
        evidence_fingerprints=_evidence_fingerprints(
            audit.get("selected_evidence_ids")
        ),
        validation_status=_safe_repair_token(audit.get("validation_status")),
        promotion_outcome=_safe_repair_token(audit.get("promotion_outcome")),
        successful=(
            str(audit.get("promotion_outcome") or "") == "promoted"
            and str(audit.get("validation_status") or "") == "pass"
            and bool(resolved)
            and not persisting
            and not introduced
            and not abstention_or_removal
            and not out_of_scope_mutation
        ),
        abstention_or_removal=abstention_or_removal,
        out_of_scope_mutation=out_of_scope_mutation,
        repair_mode=(
            "unavailable"
            if usage is None
            else "model"
            if usage["calls"]
            else "deterministic"
        ),
        usage_attribution="available" if usage is not None else "unavailable",
        model_call_count=usage["calls"] if usage is not None else None,
        input_tokens=usage["input_tokens"] if usage is not None else None,
        output_tokens=usage["output_tokens"] if usage is not None else None,
        total_tokens=usage["total_tokens"] if usage is not None else None,
        estimated_cost_usd=usage["cost"] if usage is not None else None,
        latency_ms=latency_ms,
        prompt_identities=_prompt_identities(matching_usage)
        if usage is not None
        else (),
        configuration_hash=str(audit["configuration_hash"]),
        policy_hash=str(audit["policy_hash"]),
        producer_build_identity=str(audit["producer_build_identity"]),
    )


def _audit_scope_within_limit(audit: dict[str, Any], allowed_scope: set[str]) -> bool:
    declared = audit.get("allowed_paths")
    return bool(
        isinstance(declared, list)
        and all(
            isinstance(path, str)
            and any(
                path == allowed
                or path.startswith(f"{allowed}.")
                or path.startswith(f"{allowed}[")
                for allowed in allowed_scope
            )
            for path in declared
        )
    )


def _fingerprints_from_delta(raw_items: object) -> tuple[str, ...]:
    if not isinstance(raw_items, list):
        return ()
    fingerprints: set[str] = set()
    for item in raw_items:
        if isinstance(item, dict):
            try:
                fingerprints.add(
                    FailureFingerprint(
                        rule_id=str(item.get("rule_id") or "validation"),
                        affected_section=str(item.get("affected_section") or ""),
                        entity_id=str(item.get("entity_id") or ""),
                        evidence_ids=[
                            str(value)
                            for value in list(item.get("evidence_ids") or [])
                            if str(value)
                        ],
                    ).key
                )
            except (TypeError, ValueError):
                continue
    return tuple(sorted(fingerprints))


def _failure_rule_ids_from_delta(*raw_item_groups: object) -> tuple[str, ...]:
    """Expose validator classes without retaining issue text or source content."""

    return tuple(
        sorted(
            {
                rule_id
                for raw_items in raw_item_groups
                if isinstance(raw_items, list)
                for item in raw_items
                if isinstance(item, dict)
                if (rule_id := _safe_repair_token(item.get("rule_id")))
            }
        )
    )


def _safe_repair_token(value: object) -> str:
    token = str(value or "").strip()
    return token if _SAFE_REPAIR_TOKEN.fullmatch(token) else ""


def _safe_hash(value: object) -> str:
    token = str(value or "").strip().lower()
    return token if re.fullmatch(r"[a-f0-9]{64}", token) else ""


def _evidence_fingerprints(raw_items: object) -> tuple[str, ...]:
    if not isinstance(raw_items, list):
        return ()
    return tuple(
        sorted(
            {
                hashlib.sha256(str(value).strip().encode("utf-8")).hexdigest()
                for value in raw_items
                if str(value).strip()
            }
        )
    )


def _repair_usage(events: list[dict[str, Any]]) -> _RepairUsage:
    return {
        "calls": len(events),
        "input_tokens": sum(int(event["input_tokens"] or 0) for event in events),
        "output_tokens": sum(int(event["output_tokens"] or 0) for event in events),
        "total_tokens": sum(int(event["total_tokens"] or 0) for event in events),
        "cost": round(
            sum(float(event["estimated_cost_usd"] or 0.0) for event in events), 6
        ),
    }


def _is_regeneration_usage_event(event: dict[str, Any]) -> bool:
    """Exclude validation and structured-output recovery calls from repair cost."""

    return (
        str(event.get("semantic_task") or "") == "artifact_regeneration"
        or str(event.get("action") or "") == "artifact_regeneration"
        or str(event.get("action") or "").startswith("artifacts:regenerate:")
    )


def _failure_rule_ids_from_attempt(audit: dict[str, Any]) -> tuple[str, ...]:
    delta = audit.get("repair_delta")
    if not isinstance(delta, dict):
        return ()
    return _failure_rule_ids_from_delta(delta.get("introduced"))


def _unsupported_evidence_rule(rule_id: str) -> bool:
    normalized = rule_id.lower()
    return (
        normalized in {"grounding", "claim_support", "numbers"}
        or normalized.startswith("retained_claim.")
        or normalized.startswith("public_editorial_quality.unsupported")
    )


def _residual_failure_odds(
    *, denominator: int, successes: int
) -> tuple[float | None, str]:
    if denominator <= 0:
        return None, "unavailable"
    failures = denominator - successes
    if successes == 0:
        return None, "unbounded"
    return failures / successes, "available"


def _prompt_identities(events: list[dict[str, Any]]) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                f"{namespace}:{prompt_hash}"
                for event in events
                if (namespace := _safe_repair_token(event.get("prompt_namespace")))
                and (prompt_hash := _safe_hash(event.get("prompt_hash")))
            }
        )
    )


def _repeated_failed_attempt_count(attempts: list[dict[str, Any]], *, key) -> int:
    counts = Counter(key(item) for item in attempts if key(item))
    return sum(count for count in counts.values() if count > 1)


def _failed_strategy_evidence_key(
    audit: dict[str, Any],
    attempts: dict[tuple[str, int, str], ValidationReliabilityRepairAttempt],
) -> tuple[Any, ...] | None:
    attempt = attempts.get(
        (
            str(audit.get("report_id") or ""),
            int(audit.get("attempt_index") or 0),
            _safe_hash(audit.get("after_sha256")),
        )
    )
    if (
        attempt is None
        or not attempt.strategy_fingerprint
        or not attempt.failure_fingerprints
    ):
        return None
    delta = audit.get("repair_delta")
    validator_identity = (
        _safe_repair_token(delta.get("validator_identity"))
        if isinstance(delta, dict)
        else ""
    )
    return (
        attempt.failure_fingerprints,
        attempt.strategy_fingerprint,
        attempt.evidence_fingerprints,
        _safe_hash(audit.get("before_sha256")),
        validator_identity or "unavailable",
    )


def _failed_candidate_key(audit: dict[str, Any]) -> tuple[str, str, str] | None:
    candidate = _safe_hash(audit.get("after_sha256"))
    before = _safe_hash(audit.get("before_sha256"))
    if not candidate or not before:
        return None
    delta = audit.get("repair_delta")
    validator_identity = (
        _safe_repair_token(delta.get("validator_identity"))
        if isinstance(delta, dict)
        else ""
    )
    return candidate, before, validator_identity or "unavailable"


def _repair_mode_metrics(
    attempts: list[ValidationReliabilityRepairAttempt],
) -> tuple[ValidationReliabilityRepairModeMetric, ...]:
    metrics: list[ValidationReliabilityRepairModeMetric] = []
    for mode in ("deterministic", "model", "unavailable"):
        entries = [item for item in attempts if item.repair_mode == mode]
        if not entries:
            continue
        attributable = mode != "unavailable" and all(
            item.latency_ms is not None for item in entries
        )
        successful = sum(item.successful for item in entries)
        metrics.append(
            ValidationReliabilityRepairModeMetric(
                schema_version=_SCHEMA_VERSION,
                repair_mode=mode,
                attempt_count=len(entries),
                successful_attempt_count=successful,
                success_rate=_rate(successful, len(entries)),
                metric_attribution="available" if attributable else "unavailable",
                model_call_count=(
                    sum(item.model_call_count or 0 for item in entries)
                    if attributable
                    else None
                ),
                input_tokens=(
                    sum(item.input_tokens or 0 for item in entries)
                    if attributable
                    else None
                ),
                output_tokens=(
                    sum(item.output_tokens or 0 for item in entries)
                    if attributable
                    else None
                ),
                total_tokens=(
                    sum(item.total_tokens or 0 for item in entries)
                    if attributable
                    else None
                ),
                estimated_cost_usd=(
                    round(sum(item.estimated_cost_usd or 0.0 for item in entries), 6)
                    if attributable
                    else None
                ),
                latency_ms=(
                    sum(item.latency_ms or 0 for item in entries)
                    if attributable
                    else None
                ),
            )
        )
    return tuple(metrics)


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
