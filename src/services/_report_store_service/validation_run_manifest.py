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
    ("structured_output_repair",),
    ("taxonomy",),
    ("category_fit",),
    ("artifact_generation",),
    ("regeneration",),
    ("grounding_validation",),
    ("semantic_validation",),
    ("rendering",),
    ("final_html_validation",),
    ("ingestion",),
    ("publication_preflight",),
    ("wordpress_lookup",),
    ("wordpress_write",),
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
        record.publisher_id,
        record.report_id,
        record.source_identity_id,
        record.stage,
        record.started_at_utc,
        record.completed_at_utc,
        record.configuration_hash,
        record.policy_hash,
        record.producer_build_identity,
    )
    if (
        record.attempt_number < 1
        or record.parent_attempt_number < 0
        or record.parent_attempt_number >= record.attempt_number
    ):
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
    if (
        record.terminal_outcome
        in {
            "failed",
            "blocked",
            "permanent_failure",
        }
        and not str(record.failure_code or "").strip()
    ):
        raise AppError(
            code="validation_manifest_failure_code_missing",
            message="Failed or blocked validation-manifest stages require a typed failure code",
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
        run_row = conn.execute(
            """
            SELECT cohort_id, configuration_hash, policy_hash, producer_build_identity
            FROM validation_runs WHERE validation_run_id=?
            """,
            (str(record.validation_run_id),),
        ).fetchone()
        if run_row is None:
            raise AppError(
                code="validation_manifest_run_missing",
                message="Validation manifest stage requires a created validation run",
                retryable=False,
            )
        if tuple(str(value) for value in run_row) != (
            str(record.cohort_id),
            str(record.configuration_hash),
            str(record.policy_hash),
            str(record.producer_build_identity),
        ):
            raise AppError(
                code="validation_manifest_stage_provenance_conflict",
                message="Validation manifest stage provenance differs from its run",
                retryable=False,
            )
        if record.attempt_number > 1 and (
            conn.execute(
                """
                SELECT 1 FROM validation_run_entity_attempts
                WHERE validation_run_id=? AND entity_key=? AND attempt_number=?
                """,
                (
                    str(record.validation_run_id),
                    entity_key,
                    record.parent_attempt_number,
                ),
            ).fetchone()
            is None
        ):
            raise AppError(
                code="validation_manifest_parent_attempt_missing",
                message="Validation manifest retry requires its declared parent attempt",
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
        if (
            record.stage == "discovery"
            and record.cohort_disposition == "final_validation"
        ):
            member_row = conn.execute(
                """
                SELECT entity_type, publisher_id, source_identity_id
                FROM validation_run_cohort_members
                WHERE validation_run_id=? AND report_id=?
                """,
                (str(record.validation_run_id), record.report_id),
            ).fetchone()
            member_identity = (
                record.entity_type,
                record.publisher_id,
                record.source_identity_id,
            )
            if member_row is None:
                conn.execute(
                    """
                    INSERT INTO validation_run_cohort_members(
                        validation_run_id, cohort_id, entity_type, publisher_id,
                        report_id, source_identity_id, discovered_at_utc
                    ) VALUES(?,?,?,?,?,?,?)
                    """,
                    (
                        str(record.validation_run_id),
                        record.cohort_id,
                        record.entity_type,
                        record.publisher_id,
                        record.report_id,
                        record.source_identity_id,
                        record.started_at_utc,
                    ),
                )
            elif tuple(str(value) for value in member_row) != member_identity:
                raise AppError(
                    code="validation_manifest_cohort_member_conflict",
                    message="Discovery changed the immutable identity of a cohort report",
                    retryable=False,
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
            SELECT entity_key, report_id, source_identity_id, terminal_outcome,
                   cohort_disposition
            FROM validation_run_entity_attempts
            WHERE validation_run_id=? AND is_current=1 ORDER BY entity_key
            """,
            (str(request.validation_run_id),),
        ).fetchall()
        current_final = [row for row in current if str(row[4]) == "final_validation"]
        incomplete = tuple(
            str(row[0])
            for row in current_final
            if str(row[3] or "") not in _TERMINAL_OUTCOMES
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
        member_rows = conn.execute(
            """
            SELECT report_id, source_identity_id
            FROM validation_run_cohort_members
            WHERE validation_run_id=?
            ORDER BY report_id
            """,
            (str(request.validation_run_id),),
        ).fetchall()
        discovery_rows = conn.execute(
            """
            SELECT DISTINCT attempts.report_id, attempts.source_identity_id
            FROM validation_run_entity_attempts AS attempts
            JOIN validation_run_stage_records AS stages
              ON stages.attempt_id = attempts.attempt_id
            WHERE attempts.validation_run_id=?
              AND attempts.cohort_disposition='final_validation'
              AND stages.stage='discovery'
            ORDER BY attempts.report_id, attempts.source_identity_id
            """,
            (str(request.validation_run_id),),
        ).fetchall()
        stage_rows = conn.execute(
            """
            SELECT attempts.entity_key, stages.stage, stages.terminal_outcome,
                   stages.idempotency_state
            FROM validation_run_entity_attempts AS attempts
            JOIN validation_run_stage_records AS stages
              ON stages.attempt_id = attempts.attempt_id
            WHERE attempts.validation_run_id=?
              AND attempts.is_current=1
              AND attempts.cohort_disposition='final_validation'
            """,
            (str(request.validation_run_id),),
        ).fetchall()
        wordpress_multiple_post_rows = conn.execute(
            """
            SELECT DISTINCT attempts.report_id
            FROM validation_run_entity_attempts AS attempts
            JOIN validation_run_stage_records AS stages
              ON stages.attempt_id = attempts.attempt_id
            WHERE attempts.validation_run_id=?
              AND attempts.is_current=1
              AND attempts.cohort_disposition='final_validation'
              AND stages.failure_code='wp_post_lookup_ambiguous'
            ORDER BY attempts.report_id
            """,
            (str(request.validation_run_id),),
        ).fetchall()
        marked_missing_rows = conn.execute(
            """
            SELECT DISTINCT attempts.report_id
            FROM validation_run_entity_attempts AS attempts
            JOIN validation_run_stage_records AS stages
              ON stages.attempt_id = attempts.attempt_id
            WHERE attempts.validation_run_id=?
              AND attempts.is_current=1
              AND attempts.cohort_disposition='final_validation'
              AND stages.failure_code='cohort_report_missing'
            ORDER BY attempts.report_id
            """,
            (str(request.validation_run_id),),
        ).fetchall()
    expected_rows = (
        member_rows or discovery_rows or [(row[1], row[2]) for row in current_final]
    )
    expected_by_report: dict[str, set[str]] = {}
    for row in expected_rows:
        report_id = str(row[0])
        if report_id:
            expected_by_report.setdefault(report_id, set()).add(str(row[1]))
    cohort = tuple(sorted(expected_by_report))
    current_by_report: dict[str, list[tuple[str, str, str, str, str]]] = {}
    for row in current_final:
        current_by_report.setdefault(str(row[1]), []).append(
            (
                str(row[0]),
                str(row[1]),
                str(row[2]),
                str(row[3] or ""),
                str(row[4]),
            )
        )
    missing_cohort_reports = tuple(
        sorted(
            {
                *(
                    report_id
                    for report_id in cohort
                    if report_id not in current_by_report
                ),
                *(
                    str(row[0])
                    for row in marked_missing_rows
                    if str(row[0]) in expected_by_report
                ),
            }
        )
    )
    overlapping_reports = tuple(
        sorted(
            report_id
            for report_id, rows in current_by_report.items()
            if (
                len(rows) != 1
                or report_id not in expected_by_report
                or str(rows[0][2]) not in expected_by_report[report_id]
            )
        )
    )
    source_to_reports: dict[str, set[str]] = {}
    for report_id, source_identity_ids in expected_by_report.items():
        for source_identity_id in source_identity_ids:
            if source_identity_id:
                source_to_reports.setdefault(source_identity_id, set()).add(report_id)
    for report_id, rows in current_by_report.items():
        for row in rows:
            source_identity_id = str(row[2])
            if source_identity_id:
                source_to_reports.setdefault(source_identity_id, set()).add(report_id)
    duplicate_source_identities = tuple(
        sorted(
            source_identity_id
            for source_identity_id, report_ids in source_to_reports.items()
            if len(report_ids) > 1
        )
    )
    wordpress_multiple_posts = tuple(
        str(row[0]) for row in wordpress_multiple_post_rows
    )
    terminal_report_ids = {
        str(row[1]) for row in current_final if str(row[3] or "") in _TERMINAL_OUTCOMES
    }
    totals_reconciled = (
        not missing_cohort_reports
        and not overlapping_reports
        and not duplicate_source_identities
        and len(current_final) == len(cohort)
        and terminal_report_ids == set(cohort)
    )
    stages_by_entity: dict[str, list[tuple[str, str, str]]] = {}
    for row in stage_rows:
        stages_by_entity.setdefault(str(row[0]), []).append(
            (str(row[1]), str(row[2]), str(row[3]))
        )
    missing_required: list[str] = []
    if request.require_full_workflow:
        for entity_key in sorted(str(row[0]) for row in current_final):
            actual = stages_by_entity.get(entity_key, [])
            for alternatives in _FULL_WORKFLOW_REQUIRED_STAGE_GROUPS:
                if not any(stage in alternatives for stage, _, _ in actual):
                    missing_required.append(f"{entity_key}:{'|'.join(alternatives)}")
            current_outcome = next(
                str(row[3] or "") for row in current_final if str(row[0]) == entity_key
            )
            if current_outcome == "published_verified" and not any(
                stage == "repeat_publication"
                and outcome == "succeeded"
                and idempotency == "reused"
                for stage, outcome, idempotency in actual
            ):
                missing_required.append(
                    f"{entity_key}:repeat_publication_verified_reuse"
                )
    return ValidationRunManifestAuditResponse(
        schema_version="1.0",
        validation_run_id=request.validation_run_id,
        complete=(
            not incomplete
            and not duplicates
            and not missing_cohort_reports
            and not overlapping_reports
            and not duplicate_source_identities
            and not wordpress_multiple_posts
            and totals_reconciled
            and (not request.require_full_workflow or not missing_required)
        ),
        final_cohort_report_ids=cohort,
        stage_totals=totals,
        incomplete_entity_ids=incomplete,
        duplicate_current_entity_ids=duplicates,
        missing_cohort_report_ids=missing_cohort_reports,
        overlapping_current_report_ids=overlapping_reports,
        duplicate_source_identity_ids=duplicate_source_identities,
        multiple_wordpress_post_report_ids=wordpress_multiple_posts,
        totals_reconciled=totals_reconciled,
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
