"""Durable canonical manifest for bounded validation and release canaries."""

from __future__ import annotations

import hashlib
import json

from src.contracts.run_context import RunContext
from src.contracts.validation_run_manifest import (
    ValidationRunManifestAuditRequest,
    ValidationRunManifestAuditResponse,
    ValidationRunManifestCreateRequest,
    ValidationRunManifestRecordRequest,
    ValidationRunManifestRecordResponse,
    ValidationRunManifestStageTotal,
)
from src.utils.errors import AppError

from .connection import _metadata_conn

_STAGE_OUTCOMES = {"succeeded", "failed", "skipped", "abstained", "blocked"}
_TERMINAL_OUTCOMES = {
    "published_verified",
    "publish_ready",
    "blocked",
    "permanent_failure",
    "abstained",
    "cancelled",
    "superseded",
}
_COHORTS = {"final_validation", "repair_attempt", "out_of_cohort"}
_SUPERSESSION_STATES = {"current", "superseded"}
_IDEMPOTENCY_STATES = {"new", "replayed", "reused", "verified"}

# Full-run closure is intentionally stricter than an intermediate ingest or
# first-publication audit.  Each tuple is one required stage group: every final
# cohort report must retain at least one stage in the group before a canary can
# claim an end-to-end result.  The WordPress transaction has valid alternative
# paths (a verified existing post needs no write), hence its grouped form.
_FULL_WORKFLOW_REQUIRED_STAGE_GROUPS: tuple[tuple[str, ...], ...] = (
    ("discovery",),
    ("candidate_qualification",),
    ("acquisition",),
    ("admission_preflight",),
    ("source_preparation",),
    ("source_validation",),
    ("evidence_generation",),
    ("taxonomy",),
    ("category_fit",),
    ("artifact_generation",),
    ("grounding_validation",),
    ("semantic_validation",),
    ("rendering",),
    ("final_html_validation",),
    ("ingest",),
    ("publication_preflight",),
    ("wordpress_lookup", "wordpress_write"),
    ("authenticated_readback",),
    ("repeat_publication",),
)


def create_validation_run_manifest(
    request: ValidationRunManifestCreateRequest, ctx: RunContext
) -> None:
    _require_schema(request.schema_version)
    _require_fields(
        request.db_path,
        str(request.validation_run_id),
        request.cohort_id,
        str(request.workflow_run_id),
        request.configuration_hash,
        request.policy_hash,
        request.producer_build_identity,
        request.created_at_utc,
    )
    with _metadata_conn(request.db_path, ctx) as conn:
        existing = conn.execute(
            "SELECT workflow_run_id, cohort_id, configuration_hash, policy_hash, "
            "producer_build_identity FROM validation_runs WHERE validation_run_id=?",
            (str(request.validation_run_id),),
        ).fetchone()
        identity = (
            request.cohort_id,
            request.configuration_hash,
            request.policy_hash,
            request.producer_build_identity,
        )
        if existing is not None:
            existing_identity = tuple(str(existing[index]) for index in range(1, 5))
            if existing_identity != identity:
                raise AppError(
                    code="validation_manifest_run_identity_conflict",
                    message=(
                        "Validation run ID is already bound to different provenance"
                    ),
                    retryable=False,
                )
            return
        conn.execute(
            """
            INSERT INTO validation_runs(
                validation_run_id, schema_version, cohort_id, workflow_run_id,
                configuration_hash,
                policy_hash, producer_build_identity, created_at_utc
            ) VALUES(?,?,?,?,?,?,?,?)
            """,
            (
                str(request.validation_run_id),
                request.schema_version,
                request.cohort_id,
                str(request.workflow_run_id),
                request.configuration_hash,
                request.policy_hash,
                request.producer_build_identity,
                request.created_at_utc,
            ),
        )


def record_validation_run_manifest_stage(
    request: ValidationRunManifestRecordRequest, ctx: RunContext
) -> ValidationRunManifestRecordResponse:
    _require_schema(request.schema_version)
    record = request.record
    _require_schema(record.schema_version)
    _require_fields(
        request.db_path,
        str(record.validation_run_id),
        record.cohort_id,
        str(record.workflow_run_id),
        record.entity_type,
        record.stage,
        record.started_at_utc,
        record.completed_at_utc,
        record.configuration_hash,
        record.policy_hash,
        record.producer_build_identity,
    )
    if record.attempt_number < 1 or record.parent_attempt_number < 0:
        raise AppError(
            code="validation_manifest_stage_invalid",
            message="Validation manifest stage has an invalid attempt or outcome",
            retryable=False,
        )
    if record.entity_terminal:
        valid_outcome = record.terminal_outcome in _TERMINAL_OUTCOMES
    else:
        valid_outcome = record.terminal_outcome in _STAGE_OUTCOMES
    if not valid_outcome:
        raise AppError(
            code="validation_manifest_stage_invalid",
            message="Validation manifest stage has an invalid outcome",
            retryable=False,
        )
    if record.cohort_disposition not in _COHORTS:
        raise AppError(
            code="validation_manifest_cohort_invalid",
            message="Validation manifest cohort disposition is invalid",
            retryable=False,
        )
    if record.supersession_state not in _SUPERSESSION_STATES:
        raise AppError(
            code="validation_manifest_supersession_invalid",
            message="Validation manifest supersession state is invalid",
            retryable=False,
        )
    if record.idempotency_state not in _IDEMPOTENCY_STATES:
        raise AppError(
            code="validation_manifest_idempotency_invalid",
            message="Validation manifest idempotency state is invalid",
            retryable=False,
        )
    entity_key = _entity_key(
        record.entity_type, record.report_id, record.source_identity_id
    )
    attempt_id = _digest(
        str(record.validation_run_id), entity_key, str(record.attempt_number)
    )
    stage_record_id = _digest(attempt_id, record.stage)
    with _metadata_conn(request.db_path, ctx) as conn:
        if (
            conn.execute(
                "SELECT 1 FROM validation_runs WHERE validation_run_id=?",
                (str(record.validation_run_id),),
            ).fetchone()
            is None
        ):
            raise AppError(
                code="validation_manifest_run_missing",
                message="Validation manifest stage requires a created validation run",
                retryable=False,
            )
        if (
            conn.execute(
                "SELECT 1 FROM validation_run_stage_records WHERE stage_record_id=?",
                (stage_record_id,),
            ).fetchone()
            is not None
        ):
            return ValidationRunManifestRecordResponse(
                schema_version="1.0",
                stage_record_id=stage_record_id,
                inserted=False,
                superseded_attempts=0,
            )
        superseded = conn.execute(
            """
            UPDATE validation_run_entity_attempts SET is_current=0
            WHERE validation_run_id=? AND entity_key=? AND attempt_number<?
              AND is_current=1
            """,
            (str(record.validation_run_id), entity_key, record.attempt_number),
        ).rowcount
        conn.execute(
            """
            INSERT INTO validation_run_entity_attempts(
                attempt_id, validation_run_id, entity_key, entity_type, publisher_id,
                report_id, source_identity_id, cohort_id, attempt_number,
                parent_attempt_number, cohort_disposition,
                is_current, created_at_utc
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(validation_run_id, entity_key, attempt_number) DO UPDATE SET
                cohort_disposition=excluded.cohort_disposition,
                parent_attempt_number=excluded.parent_attempt_number, is_current=1
            """,
            (
                attempt_id,
                str(record.validation_run_id),
                entity_key,
                record.entity_type,
                record.publisher_id,
                record.report_id,
                record.source_identity_id,
                record.cohort_id,
                record.attempt_number,
                record.parent_attempt_number,
                record.cohort_disposition,
                1,
                record.started_at_utc,
            ),
        )
        conn.execute(
            """
            INSERT INTO validation_run_stage_records(
                stage_record_id, attempt_id, validation_run_id, workflow_run_id, stage,
                cohort_id, input_artifact_ids_json, output_artifact_ids_json,
                started_at_utc,
                completed_at_utc, terminal_outcome, failure_code, retryable,
                repair_disposition, duplicate_disposition, configuration_hash,
                policy_hash, producer_build_identity, supersession_state,
                idempotency_state, entity_terminal, created_at_utc
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                stage_record_id,
                attempt_id,
                str(record.validation_run_id),
                str(record.workflow_run_id),
                record.stage,
                record.cohort_id,
                _json(record.input_artifact_ids),
                _json(record.output_artifact_ids),
                record.started_at_utc,
                record.completed_at_utc,
                record.terminal_outcome,
                record.failure_code,
                int(record.retryable),
                record.repair_disposition,
                record.duplicate_disposition,
                record.configuration_hash,
                record.policy_hash,
                record.producer_build_identity,
                record.supersession_state,
                record.idempotency_state,
                int(record.entity_terminal),
                record.completed_at_utc,
            ),
        )
        if record.entity_terminal:
            conn.execute(
                """
                UPDATE validation_run_entity_attempts
                SET terminal_outcome=?, terminal_stage=?, failure_code=?,
                    completed_at_utc=?
                WHERE attempt_id=?
                """,
                (
                    record.terminal_outcome,
                    record.stage,
                    record.failure_code,
                    record.completed_at_utc,
                    attempt_id,
                ),
            )
    return ValidationRunManifestRecordResponse(
        schema_version="1.0",
        stage_record_id=stage_record_id,
        inserted=True,
        superseded_attempts=max(0, int(superseded or 0)),
    )


def audit_validation_run_manifest(
    request: ValidationRunManifestAuditRequest, ctx: RunContext
) -> ValidationRunManifestAuditResponse:
    _require_schema(request.schema_version)
    with _metadata_conn(request.db_path, ctx) as conn:
        if (
            conn.execute(
                "SELECT 1 FROM validation_runs WHERE validation_run_id=?",
                (str(request.validation_run_id),),
            ).fetchone()
            is None
        ):
            raise AppError(
                code="validation_manifest_run_missing",
                message="Validation manifest audit requires a created validation run",
                retryable=False,
            )
        current = conn.execute(
            """
            SELECT entity_key, report_id, terminal_outcome, cohort_disposition
            FROM validation_run_entity_attempts
            WHERE validation_run_id=? AND is_current=1 ORDER BY entity_key
            """,
            (str(request.validation_run_id),),
        ).fetchall()
        incomplete = tuple(
            str(row[0])
            for row in current
            if str(row[2] or "") not in _TERMINAL_OUTCOMES
        )
        duplicates = tuple(
            str(row[0])
            for row in conn.execute(
                """
                SELECT entity_key FROM validation_run_entity_attempts
                WHERE validation_run_id=? AND is_current=1
                GROUP BY entity_key HAVING COUNT(*) != 1
                """,
                (str(request.validation_run_id),),
            ).fetchall()
        )
        totals = tuple(
            ValidationRunManifestStageTotal(
                schema_version="1.0",
                stage=str(row[0]),
                terminal_outcome=str(row[1]),
                entity_count=int(row[2]),
            )
            for row in conn.execute(
                """
                SELECT stage, terminal_outcome, COUNT(DISTINCT attempt_id)
                FROM validation_run_stage_records WHERE validation_run_id=?
                GROUP BY stage, terminal_outcome ORDER BY stage, terminal_outcome
                """,
                (str(request.validation_run_id),),
            ).fetchall()
        )
        stage_rows = conn.execute(
            """
            SELECT attempts.entity_key, stages.stage
            FROM validation_run_entity_attempts AS attempts
            JOIN validation_run_stage_records AS stages
              ON stages.attempt_id = attempts.attempt_id
            WHERE attempts.validation_run_id=?
              AND attempts.is_current=1
              AND attempts.cohort_disposition='final_validation'
            """,
            (str(request.validation_run_id),),
        ).fetchall()
    cohort = tuple(
        sorted(
            {str(row[1]) for row in current if row[1] and row[3] == "final_validation"}
        )
    )
    stages_by_entity: dict[str, set[str]] = {}
    for row in stage_rows:
        stages_by_entity.setdefault(str(row[0]), set()).add(str(row[1]))
    missing_required: list[str] = []
    if request.require_full_workflow:
        for entity_key in sorted(
            str(row[0]) for row in current if str(row[3]) == "final_validation"
        ):
            actual = stages_by_entity.get(entity_key, set())
            for alternatives in _FULL_WORKFLOW_REQUIRED_STAGE_GROUPS:
                if not any(stage in actual for stage in alternatives):
                    missing_required.append(f"{entity_key}:{'|'.join(alternatives)}")
    return ValidationRunManifestAuditResponse(
        schema_version="1.0",
        validation_run_id=request.validation_run_id,
        complete=(
            not incomplete
            and not duplicates
            and (not request.require_full_workflow or not missing_required)
        ),
        final_cohort_report_ids=cohort,
        stage_totals=totals,
        incomplete_entity_ids=incomplete,
        duplicate_current_entity_ids=duplicates,
        missing_required_stage_entity_ids=tuple(missing_required),
    )


def _entity_key(entity_type: str, report_id: str, source_identity_id: str) -> str:
    key = "|".join((entity_type.strip(), report_id.strip(), source_identity_id.strip()))
    if key == "||":
        raise AppError(
            code="validation_manifest_entity_missing",
            message="Validation manifest stage requires an entity identity",
            retryable=False,
        )
    return key


def _digest(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def _json(values: tuple[str, ...]) -> str:
    return json.dumps(sorted(set(values)), separators=(",", ":"))


def _require_schema(schema_version: str) -> None:
    if schema_version != "1.0":
        raise AppError(
            code="validation_manifest_schema_version_invalid",
            message="Validation manifest requires schema version 1.0",
            retryable=False,
        )


def _require_fields(*values: str) -> None:
    if any(not str(value or "").strip() for value in values):
        raise AppError(
            code="validation_manifest_required_field_missing",
            message="Validation manifest requires complete provenance fields",
            retryable=False,
        )
