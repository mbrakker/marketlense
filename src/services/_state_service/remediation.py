from __future__ import annotations

import json
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from typing import Any, cast

from src.contracts.remediation import (
    RemediationArtifactReference,
    RemediationCheckpointReference,
    RemediationClaimRequest,
    RemediationClaimResponse,
    RemediationExpiredLeaseReleaseRequest,
    RemediationExpiredLeaseReleaseResponse,
    RemediationIdempotencyKey,
    RemediationListRequest,
    RemediationListResponse,
    RemediationSoakReportRequest,
    RemediationSoakReportResponse,
    RemediationActionCode,
    RemediationRecord,
    RemediationStatus,
    RemediationTransitionRequest,
    RemediationTransitionResponse,
    RemediationUpsertRequest,
    RemediationUpsertResponse,
)
from src.contracts.retry_decision import RetryDecision
from src.contracts.run_context import RunContext
from src.services._state_service.common import _state_conn, logger
from src.utils.clock import utc_now_seconds_z
from src.utils.errors import AppError
from src.utils.logging import log_event

_ACTIVE_STATUSES = {"pending", "leased", "retrying", "deferred"}
_CLAIMABLE_STATUSES = {"pending", "deferred"}
_REMEDIATION_ACTIONS = {
    "resume_valid_checkpoint",
    "retry_transient_service_call",
    "rerun_targeted_artifact_family",
    "revalidate_replaced_source",
    "poll_mailbox_delivery",
    "retry_idempotent_publication",
    "defer_for_budget",
    "escalate_credentials",
    "mark_terminal_blocker",
}
_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "pending": {
        "leased",
        "deferred",
        "operator_action_required",
        "terminal",
        "resolved",
        "superseded",
    },
    "leased": {
        "retrying",
        "pending",
        "deferred",
        "operator_action_required",
        "terminal",
        "resolved",
        "superseded",
    },
    "retrying": {
        "pending",
        "deferred",
        "operator_action_required",
        "terminal",
        "resolved",
        "superseded",
    },
    "deferred": {
        "leased",
        "pending",
        "operator_action_required",
        "terminal",
        "resolved",
        "superseded",
    },
    "operator_action_required": {"resolved", "terminal", "superseded"},
    "terminal": {"resolved", "superseded"},
    "resolved": {"pending", "superseded"},
    "superseded": set(),
}


def _status_from_row(value: object) -> RemediationStatus:
    status = str(value or "")
    if status not in _ALLOWED_TRANSITIONS:
        raise AppError(
            code="remediation_record_read_invalid",
            message="Persisted remediation record has an unsupported status",
            retryable=False,
            context={"status": status},
        )
    return cast(RemediationStatus, status)


def _action_from_row(value: object) -> RemediationActionCode:
    action = str(value or "")
    if action not in _REMEDIATION_ACTIONS:
        raise AppError(
            code="remediation_record_read_invalid",
            message="Persisted remediation record has an unsupported action",
            retryable=False,
            context={"action_code": action},
        )
    return cast(RemediationActionCode, action)


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _load_object(raw: object) -> dict[str, Any]:
    try:
        value = json.loads(str(raw or "{}"))
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _load_list(raw: object) -> list[Any]:
    try:
        value = json.loads(str(raw or "[]"))
    except json.JSONDecodeError:
        return []
    return value if isinstance(value, list) else []


def _retry_decision_from_raw(raw: object) -> RetryDecision | None:
    payload = _load_object(raw)
    if not payload:
        return None
    try:
        return RetryDecision(**payload)
    except TypeError:
        return None


def _checkpoint_from_raw(raw: object) -> RemediationCheckpointReference | None:
    payload = _load_object(raw)
    if not payload:
        return None
    try:
        return RemediationCheckpointReference(**payload)
    except TypeError:
        return None


def _artifact_refs_from_raw(raw: object) -> list[RemediationArtifactReference]:
    records: list[RemediationArtifactReference] = []
    for payload in _load_list(raw):
        if not isinstance(payload, dict):
            continue
        try:
            records.append(RemediationArtifactReference(**payload))
        except TypeError:
            continue
    return records


def _idempotency_keys_from_raw(raw: object) -> list[RemediationIdempotencyKey]:
    records: list[RemediationIdempotencyKey] = []
    for payload in _load_list(raw):
        if not isinstance(payload, dict):
            continue
        try:
            records.append(RemediationIdempotencyKey(**payload))
        except TypeError:
            continue
    return records


def _record_from_row(row) -> RemediationRecord:
    budget = _load_object(row[21])
    from src.contracts.remediation import RemediationBudgetSummary

    return RemediationRecord(
        schema_version=str(row[2] or "1.0"),
        remediation_id=str(row[0]),
        dedupe_key=str(row[1]),
        workflow=str(row[3]),
        run_id=str(row[4]),
        task_id=str(row[5]),
        span_id=str(row[6]),
        report_id=str(row[7] or ""),
        source_id=str(row[8] or ""),
        publisher_id=str(row[9] or ""),
        input_checksum=str(row[10] or ""),
        failed_stage=str(row[11] or ""),
        operation=str(row[12] or ""),
        error_code=str(row[13] or ""),
        error_classification=str(row[14] or "unknown"),
        retry_decision=_retry_decision_from_raw(row[15]),
        status=_status_from_row(row[16]),
        checkpoint=_checkpoint_from_raw(row[17]),
        reusable_artifacts=_artifact_refs_from_raw(row[18]),
        committed_side_effects=[str(value) for value in _load_list(row[19])],
        idempotency_keys=_idempotency_keys_from_raw(row[20]),
        budget=RemediationBudgetSummary(
            schema_version=str(budget.get("schema_version") or "1.0"),
            consumed=dict(budget.get("consumed") or {}),
            reserved=dict(budget.get("reserved") or {}),
            remaining=dict(budget.get("remaining") or {}),
            decision=str(budget.get("decision") or "allow"),
        ),
        attempt_count=int(row[22] or 0),
        max_attempts=int(row[23] or 1),
        cooldown_seconds=int(row[24] or 0),
        next_eligible_at_utc=str(row[25] or ""),
        action_code=_action_from_row(row[26]),
        operator_next_action=str(row[27] or ""),
        runbook_ref=str(row[28] or ""),
        created_at_utc=str(row[29] or ""),
        updated_at_utc=str(row[30] or ""),
        resolved_at_utc=str(row[31] or ""),
        lease_owner=str(row[32] or ""),
        lease_expires_at_utc=str(row[33] or ""),
        diagnostics=_load_object(row[34]),
    )


def _record_values(record: RemediationRecord) -> tuple[object, ...]:
    return (
        record.remediation_id,
        record.dedupe_key,
        record.schema_version,
        record.workflow,
        record.run_id,
        record.task_id,
        record.span_id,
        record.report_id,
        record.source_id,
        record.publisher_id,
        record.input_checksum,
        record.failed_stage,
        record.operation,
        record.error_code,
        record.error_classification,
        _json(asdict(record.retry_decision)) if record.retry_decision else "{}",
        record.status,
        _json(asdict(record.checkpoint)) if record.checkpoint else "{}",
        _json([asdict(item) for item in record.reusable_artifacts]),
        _json(record.committed_side_effects),
        _json([asdict(item) for item in record.idempotency_keys]),
        _json(asdict(record.budget)),
        max(0, int(record.attempt_count)),
        max(1, int(record.max_attempts)),
        max(0, int(record.cooldown_seconds)),
        record.next_eligible_at_utc,
        record.action_code,
        record.operator_next_action,
        record.runbook_ref,
        record.created_at_utc,
        record.updated_at_utc,
        record.resolved_at_utc,
        record.lease_owner,
        record.lease_expires_at_utc,
        _json(record.diagnostics),
    )


def _validate_record(record: RemediationRecord) -> None:
    missing = [
        name
        for name, value in (
            ("remediation_id", record.remediation_id),
            ("dedupe_key", record.dedupe_key),
            ("workflow", record.workflow),
            ("run_id", record.run_id),
            ("task_id", record.task_id),
            ("span_id", record.span_id),
        )
        if not str(value or "").strip()
    ]
    if missing:
        raise AppError(
            code="remediation_record_invalid",
            message="Remediation record is missing required identity fields",
            retryable=False,
            context={"missing": missing},
        )
    if record.status not in _ALLOWED_TRANSITIONS:
        raise AppError(
            code="remediation_status_invalid",
            message="Remediation status is not supported",
            retryable=False,
            context={"status": record.status},
        )
    if record.action_code not in _REMEDIATION_ACTIONS:
        raise AppError(
            code="remediation_action_invalid",
            message="Remediation action is not approved by policy",
            retryable=False,
            context={"action_code": record.action_code},
        )


def _insert_transition(
    conn,
    *,
    remediation_id: str,
    from_status: str,
    to_status: str,
    reason: str,
    actor: str,
    at_utc: str,
) -> None:
    conn.execute(
        """
        INSERT INTO remediation_transitions(
          remediation_id, from_status, to_status, reason, actor, created_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (remediation_id, from_status, to_status, reason, actor, at_utc),
    )


def upsert_remediation_record(
    request: RemediationUpsertRequest,
    ctx: RunContext,
) -> RemediationUpsertResponse:
    _validate_record(request.record)
    now = request.record.updated_at_utc or utc_now_seconds_z()
    with _state_conn(request.state_db, ctx) as conn:
        row = conn.execute(
            "SELECT * FROM remediation_records WHERE dedupe_key=?",
            (request.record.dedupe_key,),
        ).fetchone()
        if row is None:
            record = replace(
                request.record,
                created_at_utc=request.record.created_at_utc or now,
                updated_at_utc=now,
            )
            conn.execute(
                """
                INSERT INTO remediation_records VALUES (
                  ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
                )
                """,
                _record_values(record),
            )
            _insert_transition(
                conn,
                remediation_id=record.remediation_id,
                from_status="",
                to_status=record.status,
                reason="remediation_created",
                actor="workflow",
                at_utc=now,
            )
            created = True
        else:
            existing = _record_from_row(row)
            record = replace(
                request.record,
                remediation_id=existing.remediation_id,
                created_at_utc=existing.created_at_utc,
                updated_at_utc=now,
                status=existing.status,
                attempt_count=existing.attempt_count,
                max_attempts=max(existing.max_attempts, request.record.max_attempts),
                lease_owner=existing.lease_owner,
                lease_expires_at_utc=existing.lease_expires_at_utc,
                resolved_at_utc=existing.resolved_at_utc,
            )
            conn.execute(
                """
                UPDATE remediation_records SET
                  schema_version=?, workflow=?, run_id=?, task_id=?,
                  span_id=?, report_id=?, source_id=?, publisher_id=?,
                  input_checksum=?, failed_stage=?, operation=?, error_code=?,
                  error_classification=?, retry_decision_json=?, checkpoint_json=?,
                  reusable_artifacts_json=?, committed_side_effects_json=?,
                  idempotency_keys_json=?, budget_json=?, max_attempts=?,
                  cooldown_seconds=?, next_eligible_at_utc=?, action_code=?,
                  operator_next_action=?, runbook_ref=?, updated_at_utc=?,
                  diagnostics_json=?
                WHERE remediation_id=?
                """,
                (
                    record.schema_version,
                    record.workflow,
                    record.run_id,
                    record.task_id,
                    record.span_id,
                    record.report_id,
                    record.source_id,
                    record.publisher_id,
                    record.input_checksum,
                    record.failed_stage,
                    record.operation,
                    record.error_code,
                    record.error_classification,
                    _json(asdict(record.retry_decision))
                    if record.retry_decision
                    else "{}",
                    _json(asdict(record.checkpoint)) if record.checkpoint else "{}",
                    _json([asdict(item) for item in record.reusable_artifacts]),
                    _json(record.committed_side_effects),
                    _json([asdict(item) for item in record.idempotency_keys]),
                    _json(asdict(record.budget)),
                    record.max_attempts,
                    record.cooldown_seconds,
                    record.next_eligible_at_utc,
                    record.action_code,
                    record.operator_next_action,
                    record.runbook_ref,
                    record.updated_at_utc,
                    _json(record.diagnostics),
                    record.remediation_id,
                ),
            )
            _insert_transition(
                conn,
                remediation_id=record.remediation_id,
                from_status=existing.status,
                to_status=existing.status,
                reason="remediation_deduplicated",
                actor="workflow",
                at_utc=now,
            )
            created = False
    event = "remediation_created" if created else "remediation_deduplicated"
    logger.info(
        log_event(
            ctx,
            role="service",
            event=event,
            module=logger.name,
            fields={
                "state_db": request.state_db,
                "remediation_id": record.remediation_id,
                "dedupe_key": record.dedupe_key,
                "workflow": record.workflow,
                "status": record.status,
                "failed_stage": record.failed_stage,
                "error_code": record.error_code,
                "lease_owner": record.lease_owner,
                "lease_expires_at_utc": record.lease_expires_at_utc,
                "cooldown_seconds": record.cooldown_seconds,
                "attempt_count": record.attempt_count,
                "max_attempts": record.max_attempts,
                "checkpoint_status": (
                    record.checkpoint.validation_status
                    if record.checkpoint
                    else "absent"
                ),
                "idempotency_key_count": len(record.idempotency_keys),
                "transition_reason": "remediation_created"
                if created
                else "same_failure",
            },
        )
    )
    return RemediationUpsertResponse(
        schema_version="1.0", record=record, created=created, deduplicated=not created
    )


def list_remediation_records(
    request: RemediationListRequest,
    ctx: RunContext,
) -> RemediationListResponse:
    where: list[str] = []
    params: list[object] = []
    statuses = [item for item in request.statuses if item in _ALLOWED_TRANSITIONS]
    if statuses:
        where.append("status IN (" + ",".join("?" for _ in statuses) + ")")
        params.extend(statuses)
    if request.workflow.strip():
        where.append("workflow=?")
        params.append(request.workflow.strip())
    query = "SELECT * FROM remediation_records"
    if where:
        query += " WHERE " + " AND ".join(where)
    query += " ORDER BY updated_at_utc DESC, remediation_id DESC LIMIT ?"
    params.append(max(1, int(request.limit)))
    with _state_conn(request.state_db, ctx) as conn:
        rows = conn.execute(query, tuple(params)).fetchall()
    return RemediationListResponse(
        schema_version="1.0", records=[_record_from_row(row) for row in rows]
    )


def read_remediation_soak_report(
    request: RemediationSoakReportRequest,
    ctx: RunContext,
) -> RemediationSoakReportResponse:
    """Return retained remediation evidence without changing records or leases."""

    with _state_conn(request.state_db, ctx) as conn:
        created_rows = conn.execute(
            """
            SELECT DISTINCT remediation_id FROM remediation_transitions
            WHERE reason='remediation_created'
            ORDER BY remediation_id ASC
            """
        ).fetchall()
        deduplicated_rows = conn.execute(
            """
            SELECT DISTINCT remediation_id FROM remediation_transitions
            WHERE reason='remediation_deduplicated'
            ORDER BY remediation_id ASC
            """
        ).fetchall()
        stale_rows = conn.execute(
            """
            SELECT remediation_id FROM remediation_records
            WHERE status IN ('leased','retrying')
              AND lease_expires_at_utc<>'' AND lease_expires_at_utc<=?
            ORDER BY remediation_id ASC
            """,
            (request.now_utc,),
        ).fetchall()
        eligible_rows = conn.execute(
            """
            SELECT remediation_id FROM remediation_records
            WHERE status IN ('pending','deferred')
              AND action_code<>'mark_terminal_blocker'
              AND (next_eligible_at_utc='' OR next_eligible_at_utc<=?)
              AND (lease_expires_at_utc='' OR lease_expires_at_utc<=?)
            ORDER BY next_eligible_at_utc ASC, created_at_utc ASC, remediation_id ASC
            """,
            (request.now_utc, request.now_utc),
        ).fetchall()
        held_rows = conn.execute(
            """
            SELECT remediation_id FROM remediation_records
            WHERE status IN ('operator_action_required','terminal')
               OR action_code='mark_terminal_blocker'
            ORDER BY remediation_id ASC
            """
        ).fetchall()
        observed_error_rows = conn.execute(
            """
            SELECT DISTINCT error_code FROM remediation_records
            WHERE error_code<>''
            ORDER BY error_code ASC
            """
        ).fetchall()
    mapped_codes = {
        code.strip() for code in request.runbook_error_codes if code.strip()
    }
    response = RemediationSoakReportResponse(
        schema_version="1.0",
        created_record_ids=[str(row[0]) for row in created_rows],
        deduplicated_record_ids=[str(row[0]) for row in deduplicated_rows],
        stale_lease_ids=[str(row[0]) for row in stale_rows],
        eligible_record_ids=[str(row[0]) for row in eligible_rows],
        held_record_ids=[str(row[0]) for row in held_rows],
        missing_runbook_error_codes=sorted(
            str(row[0])
            for row in observed_error_rows
            if str(row[0]) not in mapped_codes
        ),
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="remediation_soak_report_read",
            module=logger.name,
            fields={
                "created_count": len(response.created_record_ids),
                "deduplicated_count": len(response.deduplicated_record_ids),
                "stale_lease_count": len(response.stale_lease_ids),
                "eligible_count": len(response.eligible_record_ids),
                "held_count": len(response.held_record_ids),
                "missing_runbook_mapping_count": len(
                    response.missing_runbook_error_codes
                ),
            },
        )
    )
    return response


def _lease_expiry(now_utc: str, lease_seconds: int) -> str:
    normalized = now_utc[:-1] + "+00:00" if now_utc.endswith("Z") else now_utc
    try:
        now = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise AppError(
            code="remediation_time_invalid",
            message="Remediation lease time must be an ISO-8601 UTC timestamp",
            cause=exc,
            retryable=False,
        ) from exc
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return (
        (now.astimezone(timezone.utc) + timedelta(seconds=max(1, lease_seconds)))
        .isoformat()
        .replace("+00:00", "Z")
    )


def claim_next_remediation(
    request: RemediationClaimRequest,
    ctx: RunContext,
) -> RemediationClaimResponse:
    if not request.worker_id.strip():
        raise AppError(
            code="remediation_worker_id_missing",
            message="Bounded remediation reaper requires a worker ID",
            retryable=False,
        )
    expiry = _lease_expiry(request.now_utc, request.lease_seconds)
    record: RemediationRecord | None = None
    with _state_conn(request.state_db, ctx) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            """
            SELECT * FROM remediation_records
            WHERE status IN ('pending','deferred')
              AND (next_eligible_at_utc='' OR next_eligible_at_utc<=?)
              AND (lease_expires_at_utc='' OR lease_expires_at_utc<=?)
            ORDER BY next_eligible_at_utc ASC, created_at_utc ASC, remediation_id ASC
            LIMIT 1
            """,
            (request.now_utc, request.now_utc),
        ).fetchone()
        if row is not None:
            candidate = _record_from_row(row)
            updated = conn.execute(
                """
                UPDATE remediation_records
                SET status='leased', lease_owner=?, lease_expires_at_utc=?,
                    updated_at_utc=?
                WHERE remediation_id=? AND status IN ('pending','deferred')
                  AND (lease_expires_at_utc='' OR lease_expires_at_utc<=?)
                """,
                (
                    request.worker_id,
                    expiry,
                    request.now_utc,
                    candidate.remediation_id,
                    request.now_utc,
                ),
            )
            if updated.rowcount == 1:
                _insert_transition(
                    conn,
                    remediation_id=candidate.remediation_id,
                    from_status=candidate.status,
                    to_status="leased",
                    reason="lease_acquired",
                    actor=request.worker_id,
                    at_utc=request.now_utc,
                )
                record = replace(
                    candidate,
                    status="leased",
                    lease_owner=request.worker_id,
                    lease_expires_at_utc=expiry,
                    updated_at_utc=request.now_utc,
                )
    if record is not None:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="remediation_lease_acquired",
                module=logger.name,
                fields={
                    "remediation_id": record.remediation_id,
                    "worker_id": request.worker_id,
                    "lease_expires_at_utc": record.lease_expires_at_utc,
                    "transition_reason": "lease_acquired",
                },
            )
        )
    return RemediationClaimResponse(schema_version="1.0", record=record)


def transition_remediation(
    request: RemediationTransitionRequest,
    ctx: RunContext,
) -> RemediationTransitionResponse:
    with _state_conn(request.state_db, ctx) as conn:
        row = conn.execute(
            "SELECT * FROM remediation_records WHERE remediation_id=?",
            (request.remediation_id,),
        ).fetchone()
        if row is None:
            raise AppError(
                code="remediation_not_found",
                message="Remediation record was not found",
                retryable=False,
                context={"remediation_id": request.remediation_id},
            )
        current = _record_from_row(row)
        if request.status not in _ALLOWED_TRANSITIONS.get(current.status, set()):
            raise AppError(
                code="remediation_transition_invalid",
                message="Remediation state transition is not allowed",
                retryable=False,
                context={"from_status": current.status, "to_status": request.status},
            )
        now = utc_now_seconds_z()
        attempts = current.attempt_count + (1 if request.increment_attempt else 0)
        resolved = now if request.status == "resolved" else current.resolved_at_utc
        lease_owner = (
            current.lease_owner if request.status in {"leased", "retrying"} else ""
        )
        lease_expiry = (
            current.lease_expires_at_utc
            if request.status in {"leased", "retrying"}
            else ""
        )
        conn.execute(
            """
            UPDATE remediation_records
            SET status=?, attempt_count=?, next_eligible_at_utc=?, updated_at_utc=?,
                resolved_at_utc=?, lease_owner=?, lease_expires_at_utc=?
            WHERE remediation_id=?
            """,
            (
                request.status,
                attempts,
                request.next_eligible_at_utc or current.next_eligible_at_utc,
                now,
                resolved,
                lease_owner,
                lease_expiry,
                current.remediation_id,
            ),
        )
        _insert_transition(
            conn,
            remediation_id=current.remediation_id,
            from_status=current.status,
            to_status=request.status,
            reason=request.reason,
            actor=request.actor,
            at_utc=now,
        )
        record = replace(
            current,
            status=request.status,
            attempt_count=attempts,
            next_eligible_at_utc=request.next_eligible_at_utc
            or current.next_eligible_at_utc,
            updated_at_utc=now,
            resolved_at_utc=resolved,
            lease_owner=lease_owner,
            lease_expires_at_utc=lease_expiry,
        )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="remediation_transition",
            module=logger.name,
            fields={
                "remediation_id": record.remediation_id,
                "from_status": current.status,
                "to_status": record.status,
                "transition_reason": request.reason,
                "actor": request.actor,
            },
        )
    )
    return RemediationTransitionResponse(schema_version="1.0", record=record)


def release_expired_remediation_leases(
    request: RemediationExpiredLeaseReleaseRequest,
    ctx: RunContext,
) -> RemediationExpiredLeaseReleaseResponse:
    released_ids: list[str] = []
    with _state_conn(request.state_db, ctx) as conn:
        rows = conn.execute(
            """
            SELECT remediation_id, status FROM remediation_records
            WHERE status IN ('leased','retrying')
              AND lease_expires_at_utc<>'' AND lease_expires_at_utc<=?
            """,
            (request.now_utc,),
        ).fetchall()
        for remediation_id, current_status in rows:
            conn.execute(
                """
                UPDATE remediation_records
                SET status='pending', lease_owner='', lease_expires_at_utc=?,
                    updated_at_utc=?
                WHERE remediation_id=?
                """,
                ("", request.now_utc, remediation_id),
            )
            _insert_transition(
                conn,
                remediation_id=str(remediation_id),
                from_status=str(current_status),
                to_status="pending",
                reason="lease_expired",
                actor="reaper",
                at_utc=request.now_utc,
            )
            released_ids.append(str(remediation_id))
    for remediation_id in released_ids:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="remediation_lease_expired",
                module=logger.name,
                fields={
                    "remediation_id": remediation_id,
                    "transition_reason": "lease_expired",
                },
            )
        )
    return RemediationExpiredLeaseReleaseResponse(
        schema_version="1.0", released_ids=released_ids
    )


__all__ = [
    "claim_next_remediation",
    "list_remediation_records",
    "read_remediation_soak_report",
    "release_expired_remediation_leases",
    "transition_remediation",
    "upsert_remediation_record",
]
