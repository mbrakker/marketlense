"""Canonical deterministic reliability telemetry for immutable validation runs."""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from collections import Counter, defaultdict
from dataclasses import asdict, replace
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
_SUCCESS_OUTCOMES = {"succeeded", "publish_ready", "published_verified"}
_COMPLETED_OUTCOMES = _SUCCESS_OUTCOMES | {"skipped"}
_FAILURE_OUTCOMES = {"failed", "blocked", "permanent_failure"}
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


def build_validation_reliability_artifact(
    request: ValidationReliabilityBuildRequest, ctx: RunContext
) -> ValidationReliabilityArtifact:
    """Build a stable funnel and failure Pareto from canonical SQLite records."""

    _validate_build_request(request)
    run, attempts, stages = _read_manifest_rows(request, ctx)
    usage_events = _read_usage_events(request, ctx)
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
    failed_transitions = _failure_transition_metrics(failures)
    pareto = _failure_pareto(failures)
    artifact = ValidationReliabilityArtifact(
        schema_version=_SCHEMA_VERSION,
        validation_run_id=request.validation_run_id,
        cohort_id=str(run["cohort_id"]),
        workflow_run_id=str(run["workflow_run_id"]),
        configuration_hash=str(run["configuration_hash"]),
        policy_hash=str(run["policy_hash"]),
        producer_build_identity=str(run["producer_build_identity"]),
        transitions=transitions,
        failed_transitions=failed_transitions,
        failure_pareto=pareto,
    )
    artifact = replace(artifact, artifact_hash=_artifact_hash(artifact))
    log_event_payload = {
        "validation_run_id": str(artifact.validation_run_id),
        "cohort_id": artifact.cohort_id,
        "workflow_run_id": artifact.workflow_run_id,
        "transition_count": len(artifact.transitions),
        "failed_transition_count": len(artifact.failed_transitions),
        "pareto_entry_count": len(artifact.failure_pareto),
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
                       idempotency_state
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


def _read_usage_events(
    request: ValidationReliabilityBuildRequest, ctx: RunContext
) -> list[dict[str, Any]]:
    try:
        with sqlite3.connect(request.usage_db_path) as conn:
            conn.row_factory = sqlite3.Row
            columns = {
                str(row[1])
                for row in conn.execute("PRAGMA table_info(llm_usage_events)")
            }
            if not columns:
                return []
            if "validation_run_id" not in columns:
                return []
            event_count = int(
                conn.execute(
                    "SELECT COUNT(*) FROM llm_usage_events WHERE validation_run_id=?",
                    (str(request.validation_run_id),),
                ).fetchone()[0]
            )
            if event_count == 0:
                return []
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
    return [dict(row) for row in rows]


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
