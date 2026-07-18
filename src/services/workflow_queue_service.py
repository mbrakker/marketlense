"""SQLite-backed durable queue storage for all MarketLense workflows.

This service owns queue persistence and no domain generation.  It uses the
canonical state database so queue transitions, remediation and workflow-control
observations survive the same host restart.  The public functions intentionally
use typed contracts and immutable references rather than a generic task blob.
"""

# ruff: noqa: E501

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable, cast

from src.contracts.run_context import RunContext
from src.contracts.workflow_queue import (
    WORKFLOW_QUEUE_NAMES,
    AnalyticsProjectionPayload,
    BriefingGenerationPayload,
    BriefingOpportunity,
    BriefingOpportunityPayload,
    ClaimEmbeddingPayload,
    CoverGenerationPayload,
    MailboxDeliveryPayload,
    MaintenancePayload,
    PublicationApprovalRecord,
    PublicationReadinessPayload,
    PublicationReadinessRecord,
    PublisherDiscoveryPayload,
    QueuePayload,
    ReportAcquisitionPayload,
    ReportAnalysisPayload,
    ReportRenderPayload,
    ReportSelectionPayload,
    SignalCandidatePayload,
    SignalGenerationPayload,
    SourceIngestPayload,
    WordPressProjectionPayload,
    WordPressPublishPayload,
    WorkflowArtifactReference,
    WorkflowJob,
    WorkflowJobAttempt,
    WorkflowJobStatus,
    WorkflowJobSubmission,
    WorkflowQueueControl,
    WorkflowQueueHealth,
    WorkflowStageResult,
)
from src.services._state_service.common import _state_conn
from src.utils.clock import utc_now_seconds_iso
from src.utils.errors import AppError

_ACTIVE_STATUSES = {
    "pending",
    "leased",
    "running",
    "retry_wait",
    "budget_deferred",
    "blocked",
}
_CLAIMABLE_STATUSES = {"pending", "retry_wait", "budget_deferred"}
_LEASED_STATUSES = {"leased", "running"}
_TERMINAL_STATUSES = {"succeeded", "dead_letter", "cancelled"}
_ALLOWED_TRANSITIONS = {
    "pending": {"leased", "cancelled"},
    "leased": {"running", "pending"},
    "running": {"succeeded", "retry_wait", "budget_deferred", "blocked", "dead_letter"},
    "retry_wait": {"leased", "cancelled"},
    "budget_deferred": {"leased"},
    "blocked": {"pending"},
    "dead_letter": {"pending"},
    "succeeded": set(),
    "cancelled": set(),
}
_PAYLOAD_TYPES: dict[str, type[QueuePayload]] = {
    "publisher_discovery": PublisherDiscoveryPayload,
    "report_acquisition": ReportAcquisitionPayload,
    "mailbox_delivery": MailboxDeliveryPayload,
    "source_ingest": SourceIngestPayload,
    "report_selection": ReportSelectionPayload,
    "report_analysis": ReportAnalysisPayload,
    "report_render": ReportRenderPayload,
    "analytics_projection": AnalyticsProjectionPayload,
    "claim_embedding": ClaimEmbeddingPayload,
    "signal_candidate": SignalCandidatePayload,
    "signal_generation": SignalGenerationPayload,
    "briefing_opportunity": BriefingOpportunityPayload,
    "briefing_generation": BriefingGenerationPayload,
    "cover_generation": CoverGenerationPayload,
    "publication_readiness": PublicationReadinessPayload,
    "wordpress_publish": WordPressPublishPayload,
    "wordpress_projection": WordPressProjectionPayload,
    "artifact_repair": MaintenancePayload,
    "source_revalidation": MaintenancePayload,
    "malformed_pdf_revalidation": MaintenancePayload,
    "recategorization": MaintenancePayload,
    "vector_retention": MaintenancePayload,
    "wordpress_category_update": MaintenancePayload,
    "public_render_repair": MaintenancePayload,
    "cost_reconciliation": MaintenancePayload,
    "release_evidence_generation": MaintenancePayload,
}


def _now(value: str = "") -> str:
    return value.strip() or utc_now_seconds_iso()


def _row_int(value: object) -> int:
    """Decode SQLite integer cells without treating malformed state as zero."""

    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise AppError(
            code="workflow_queue_state_corrupt",
            message="Workflow queue integer state is malformed",
            retryable=False,
        )
    return int(value)


def _parse_time(value: str) -> datetime:
    token = str(value or "").strip().replace("Z", "+00:00")
    if not token:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(token)
    except ValueError as exc:
        raise AppError(
            code="workflow_queue_time_invalid",
            message="Workflow queue time must be ISO-8601 UTC-compatible",
            cause=exc,
            retryable=False,
            context={"value": value},
        ) from exc
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _future(now_utc: str, seconds: int) -> str:
    return (
        (_parse_time(now_utc) + timedelta(seconds=max(1, seconds)))
        .replace(microsecond=0)
        .isoformat()
    )


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _bounded_summary(value: str, limit: int = 512) -> str:
    return str(value or "").strip().replace("\n", " ")[:limit]


def _require_queue(queue_name: str) -> str:
    queue = str(queue_name or "").strip()
    if queue not in WORKFLOW_QUEUE_NAMES:
        raise AppError(
            code="workflow_queue_unknown",
            message="Workflow queue is not registered",
            retryable=False,
            context={"queue_name": queue},
        )
    return queue


def _payload_dict(payload: QueuePayload) -> dict[str, object]:
    raw = asdict(payload)
    raw["payload_type"] = type(payload).__name__
    encoded = _json(raw)
    if len(encoded.encode("utf-8")) > 16_384:
        raise AppError(
            code="workflow_queue_payload_too_large",
            message="Queue payload must contain bounded references, not domain content",
            retryable=False,
            context={"payload_type": type(payload).__name__},
        )
    for reference in payload.required_artifact_references:
        if len(reference.reference) > 2048 or len(reference.content_hash) > 256:
            raise AppError(
                code="workflow_queue_artifact_reference_invalid",
                message="Workflow queue artifact reference exceeds the bounded contract",
                retryable=False,
            )
    return raw


def _payload_from_json(queue_name: str, raw: str) -> QueuePayload:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AppError(
            code="workflow_queue_payload_invalid",
            message="Persisted workflow queue payload is not valid JSON",
            cause=exc,
            retryable=False,
            context={"queue_name": queue_name},
        ) from exc
    if not isinstance(data, dict):
        raise AppError(
            code="workflow_queue_payload_invalid",
            message="Persisted workflow queue payload must be an object",
            retryable=False,
            context={"queue_name": queue_name},
        )
    data.pop("payload_type", None)
    references_raw = data.get("required_artifact_references", [])
    if not isinstance(references_raw, list):
        raise AppError(
            code="workflow_queue_payload_invalid",
            message="Workflow payload artifact references must be a list",
            retryable=False,
        )
    data["required_artifact_references"] = [
        WorkflowArtifactReference(**item)
        for item in references_raw
        if isinstance(item, dict)
    ]
    payload_type = _PAYLOAD_TYPES[_require_queue(queue_name)]
    payload_constructor = cast(Callable[..., QueuePayload], payload_type)
    try:
        return payload_constructor(**data)
    except TypeError as exc:
        raise AppError(
            code="workflow_queue_payload_incompatible",
            message="Persisted payload is incompatible with the typed queue contract",
            cause=exc,
            retryable=False,
            context={"queue_name": queue_name},
        ) from exc


def _control_from_row(row: tuple[object, ...]) -> WorkflowQueueControl:
    return WorkflowQueueControl(
        schema_version=str(row[1]),
        queue_name=str(row[0]),
        mode=str(row[2]),  # type: ignore[arg-type]
        enabled=bool(row[3]),
        worker_concurrency_limit=_row_int(row[4]),
        maximum_pending=_row_int(row[5]),
        maximum_fanout=_row_int(row[6]),
        max_attempts=_row_int(row[7]),
        lease_seconds=_row_int(row[8]),
        budget_profile=str(row[9]),
        retry_delay_seconds=_row_int(row[10]),
        emergency_stop_reason=str(row[11]),
        updated_at_utc=str(row[12]),
        updated_by=str(row[13]),
    )


def _job_from_row(row: tuple[object, ...]) -> WorkflowJob:
    try:
        refs_raw = json.loads(str(row[17] or "[]"))
    except json.JSONDecodeError:
        refs_raw = []
    references = [
        WorkflowArtifactReference(**item) for item in refs_raw if isinstance(item, dict)
    ]
    return WorkflowJob(
        job_id=str(row[0]),
        schema_version=str(row[1]),
        queue_name=str(row[2]),
        job_type=str(row[3]),
        job_schema_version=str(row[4]),
        workflow_version=str(row[5]),
        root_workflow_id=str(row[6]),
        parent_job_id=str(row[7]),
        trigger_event_id=str(row[8]),
        correlation_id=str(row[9]),
        entity_type=str(row[10]),
        entity_id=str(row[11]),
        publisher_id=str(row[12]),
        source_identity_id=str(row[13]),
        report_id=str(row[14]),
        input_reference=str(row[15]),
        input_content_hash=str(row[16]),
        required_artifact_references=references,
        output_reference=str(row[19]),
        output_content_hash=str(row[20]),
        idempotency_key=str(row[21]),
        deduplication_scope=str(row[22]),
        priority=_row_int(row[23]),
        status=cast(WorkflowJobStatus, str(row[24])),
        available_at_utc=str(row[25]),
        attempt_count=_row_int(row[26]),
        max_attempts=_row_int(row[27]),
        lease_owner=str(row[28]),
        lease_expires_at_utc=str(row[29]),
        heartbeat_at_utc=str(row[30]),
        budget_profile=str(row[31]),
        execution_plan_hash=str(row[32]),
        prompt_policy_version=str(row[33]),
        processing_version=str(row[34]),
        created_at_utc=str(row[35]),
        updated_at_utc=str(row[36]),
        started_at_utc=str(row[37]),
        completed_at_utc=str(row[38]),
        error_code=str(row[39]),
        error_message_summary=str(row[40]),
        error_retryable=bool(row[41]),
        terminal_reason=str(row[42]),
        remediation_id=str(row[43]),
        payload_json=str(row[18]),
    )


_JOB_COLUMNS = """
job_id,schema_version,queue_name,job_type,job_schema_version,workflow_version,
root_workflow_id,parent_job_id,trigger_event_id,correlation_id,entity_type,entity_id,
publisher_id,source_identity_id,report_id,input_reference,input_content_hash,
required_artifact_references_json,payload_json,output_reference,output_content_hash,
idempotency_key,deduplication_scope,priority,status,available_at_utc,attempt_count,
max_attempts,lease_owner,lease_expires_at_utc,heartbeat_at_utc,budget_profile,
execution_plan_hash,prompt_policy_version,processing_version,created_at_utc,
updated_at_utc,started_at_utc,completed_at_utc,error_code,error_message_summary,
error_retryable,terminal_reason,remediation_id
""".replace("\n", "")


def _record_transition(
    conn,
    *,
    job_id: str,
    from_status: str,
    to_status: str,
    reason: str,
    actor: str,
    now_utc: str,
    details: dict[str, str | int | bool] | None = None,
) -> None:
    conn.execute(
        """INSERT INTO workflow_job_transitions(
        job_id,from_status,to_status,reason,actor,created_at_utc,details_json
        ) VALUES(?,?,?,?,?,?,?)""",
        (job_id, from_status, to_status, reason, actor, now_utc, _json(details or {})),
    )


def _ensure_control(conn, queue_name: str, now_utc: str) -> WorkflowQueueControl:
    row = conn.execute(
        "SELECT queue_name,schema_version,mode,enabled,worker_concurrency_limit,"
        "maximum_pending,maximum_fanout,max_attempts,lease_seconds,budget_profile,"
        "retry_delay_seconds,emergency_stop_reason,updated_at_utc,updated_by "
        "FROM workflow_queue_controls WHERE queue_name=?",
        (queue_name,),
    ).fetchone()
    if row is None:
        conn.execute(
            """INSERT INTO workflow_queue_controls(
            queue_name,schema_version,updated_at_utc
            ) VALUES(?,?,?)""",
            (queue_name, "1.0", now_utc),
        )
        row = conn.execute(
            "SELECT queue_name,schema_version,mode,enabled,worker_concurrency_limit,"
            "maximum_pending,maximum_fanout,max_attempts,lease_seconds,budget_profile,"
            "retry_delay_seconds,emergency_stop_reason,updated_at_utc,updated_by "
            "FROM workflow_queue_controls WHERE queue_name=?",
            (queue_name,),
        ).fetchone()
    assert row is not None
    return _control_from_row(row)


def seed_workflow_queue_controls(
    state_db: str, controls: Iterable[WorkflowQueueControl], ctx: RunContext
) -> list[WorkflowQueueControl]:
    """Persist configuration defaults without overwriting operator-set controls."""
    now_utc = _now()
    written: list[WorkflowQueueControl] = []
    with _state_conn(state_db, ctx) as conn:
        conn.execute("BEGIN IMMEDIATE")
        for control in controls:
            queue_name = _require_queue(control.queue_name)
            conn.execute(
                """INSERT INTO workflow_queue_controls(
                queue_name,schema_version,mode,enabled,worker_concurrency_limit,
                maximum_pending,maximum_fanout,max_attempts,lease_seconds,budget_profile,
                retry_delay_seconds,emergency_stop_reason,updated_at_utc,updated_by
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(queue_name) DO NOTHING""",
                (
                    queue_name,
                    control.schema_version,
                    control.mode,
                    1 if control.enabled else 0,
                    max(1, control.worker_concurrency_limit),
                    max(1, control.maximum_pending),
                    max(1, control.maximum_fanout),
                    max(1, control.max_attempts),
                    max(1, control.lease_seconds),
                    control.budget_profile,
                    max(1, control.retry_delay_seconds),
                    control.emergency_stop_reason,
                    now_utc,
                    control.updated_by,
                ),
            )
            written.append(_ensure_control(conn, queue_name, now_utc))
        conn.commit()
    return written


def get_workflow_queue_control(
    state_db: str, queue_name: str, ctx: RunContext
) -> WorkflowQueueControl:
    with _state_conn(state_db, ctx) as conn:
        return _ensure_control(conn, _require_queue(queue_name), _now())


def set_workflow_queue_control(
    state_db: str,
    control: WorkflowQueueControl,
    ctx: RunContext,
) -> WorkflowQueueControl:
    queue_name = _require_queue(control.queue_name)
    if control.mode not in {"active", "paused", "draining"}:
        raise AppError(
            code="workflow_queue_control_mode_invalid",
            message="Queue control mode is invalid",
            retryable=False,
        )
    now_utc = _now()
    with _state_conn(state_db, ctx) as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """INSERT INTO workflow_queue_controls(
            queue_name,schema_version,mode,enabled,worker_concurrency_limit,
            maximum_pending,maximum_fanout,max_attempts,lease_seconds,budget_profile,
            retry_delay_seconds,emergency_stop_reason,updated_at_utc,updated_by
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(queue_name) DO UPDATE SET
            schema_version=excluded.schema_version,mode=excluded.mode,enabled=excluded.enabled,
            worker_concurrency_limit=excluded.worker_concurrency_limit,
            maximum_pending=excluded.maximum_pending,maximum_fanout=excluded.maximum_fanout,
            max_attempts=excluded.max_attempts,lease_seconds=excluded.lease_seconds,
            budget_profile=excluded.budget_profile,retry_delay_seconds=excluded.retry_delay_seconds,
            emergency_stop_reason=excluded.emergency_stop_reason,updated_at_utc=excluded.updated_at_utc,
            updated_by=excluded.updated_by""",
            (
                queue_name,
                control.schema_version,
                control.mode,
                1 if control.enabled else 0,
                max(1, control.worker_concurrency_limit),
                max(1, control.maximum_pending),
                max(1, control.maximum_fanout),
                max(1, control.max_attempts),
                max(1, control.lease_seconds),
                control.budget_profile,
                max(1, control.retry_delay_seconds),
                control.emergency_stop_reason,
                now_utc,
                control.updated_by,
            ),
        )
        saved = _ensure_control(conn, queue_name, now_utc)
        conn.commit()
        return saved


def enqueue_workflow_job(
    state_db: str,
    submission: WorkflowJobSubmission,
    ctx: RunContext,
    *,
    now_utc: str = "",
) -> tuple[WorkflowJob, bool]:
    """Insert one effective job or return its existing idempotent equivalent."""
    queue_name = _require_queue(submission.queue_name)
    if not submission.job_type.strip() or not submission.idempotency_key.strip():
        raise AppError(
            code="workflow_queue_submission_invalid",
            message="Job type and idempotency key are required",
            retryable=False,
        )
    if not submission.deduplication_scope.strip():
        raise AppError(
            code="workflow_queue_submission_invalid",
            message="A deterministic deduplication scope is required",
            retryable=False,
        )
    if not isinstance(submission.payload, _PAYLOAD_TYPES[queue_name]):
        raise AppError(
            code="workflow_queue_payload_type_invalid",
            message="Queue submission payload does not match its typed queue contract",
            retryable=False,
            context={
                "queue_name": queue_name,
                "payload_type": type(submission.payload).__name__,
            },
        )
    now = _now(now_utc)
    payload_data = _payload_dict(submission.payload)
    available = submission.available_at_utc.strip() or now
    _parse_time(available)
    with _state_conn(state_db, ctx) as conn:
        conn.execute("BEGIN IMMEDIATE")
        control = _ensure_control(conn, queue_name, now)
        existing = conn.execute(
            f"SELECT {_JOB_COLUMNS} FROM workflow_jobs WHERE deduplication_scope=? AND idempotency_key=?",
            (submission.deduplication_scope, submission.idempotency_key),
        ).fetchone()
        if existing is not None:
            conn.commit()
            return _job_from_row(existing), False
        depth = conn.execute(
            "SELECT COUNT(*) FROM workflow_jobs WHERE queue_name=? AND status IN "
            "('pending','leased','running','retry_wait','budget_deferred','blocked')",
            (queue_name,),
        ).fetchone()[0]
        if int(depth) >= control.maximum_pending:
            conn.rollback()
            raise AppError(
                code="workflow_queue_at_capacity",
                message="Workflow queue reached its configured pending-work limit",
                retryable=True,
                context={
                    "queue_name": queue_name,
                    "maximum_pending": control.maximum_pending,
                },
            )
        job_id = str(uuid.uuid4())
        root_workflow_id = submission.root_workflow_id.strip() or job_id
        max_attempts = submission.max_attempts or control.max_attempts
        payload_json = _json(payload_data)
        conn.execute(
            """INSERT INTO workflow_jobs(
            job_id,schema_version,queue_name,job_type,job_schema_version,workflow_version,
            root_workflow_id,parent_job_id,trigger_event_id,correlation_id,entity_type,entity_id,
            publisher_id,source_identity_id,report_id,input_reference,input_content_hash,
            required_artifact_references_json,payload_json,idempotency_key,deduplication_scope,
            priority,status,available_at_utc,max_attempts,budget_profile,execution_plan_hash,
            prompt_policy_version,processing_version,created_at_utc,updated_at_utc
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                job_id,
                submission.schema_version,
                queue_name,
                submission.job_type,
                submission.payload.schema_version,
                submission.workflow_version,
                root_workflow_id,
                submission.parent_job_id,
                submission.trigger_event_id,
                submission.correlation_id,
                submission.entity_type,
                submission.entity_id,
                submission.publisher_id,
                submission.source_identity_id,
                submission.report_id,
                submission.payload.input_reference,
                submission.payload.input_content_hash,
                _json(
                    [
                        asdict(item)
                        for item in submission.payload.required_artifact_references
                    ]
                ),
                payload_json,
                submission.idempotency_key,
                submission.deduplication_scope,
                submission.priority,
                "pending",
                available,
                max(1, int(max_attempts)),
                submission.budget_profile or control.budget_profile,
                submission.execution_plan_hash,
                submission.payload.prompt_policy_version,
                submission.payload.processing_version,
                now,
                now,
            ),
        )
        _record_transition(
            conn,
            job_id=job_id,
            from_status="",
            to_status="pending",
            reason="enqueued",
            actor=str(ctx.run_id),
            now_utc=now,
        )
        row = conn.execute(
            f"SELECT {_JOB_COLUMNS} FROM workflow_jobs WHERE job_id=?", (job_id,)
        ).fetchone()
        conn.commit()
    assert row is not None
    return _job_from_row(row), True


def get_workflow_job(state_db: str, job_id: str, ctx: RunContext) -> WorkflowJob | None:
    with _state_conn(state_db, ctx) as conn:
        row = conn.execute(
            f"SELECT {_JOB_COLUMNS} FROM workflow_jobs WHERE job_id=?", (job_id,)
        ).fetchone()
    return _job_from_row(row) if row is not None else None


def load_workflow_job_payload(job: WorkflowJob) -> QueuePayload:
    return _payload_from_json(job.queue_name, job.payload_json)


def release_expired_workflow_leases(
    state_db: str, ctx: RunContext, *, now_utc: str = "", actor: str = "lease_reaper"
) -> list[str]:
    now = _now(now_utc)
    released: list[str] = []
    with _state_conn(state_db, ctx) as conn:
        conn.execute("BEGIN IMMEDIATE")
        rows = conn.execute(
            "SELECT job_id,status FROM workflow_jobs WHERE status IN ('leased','running') "
            "AND lease_expires_at_utc<>'' AND lease_expires_at_utc<=? ORDER BY job_id",
            (now,),
        ).fetchall()
        for job_id, status in rows:
            conn.execute(
                """UPDATE workflow_jobs SET status='pending',available_at_utc=?,lease_owner='',
                lease_expires_at_utc='',heartbeat_at_utc='',updated_at_utc=?,
                error_code='workflow_queue_lease_expired',error_message_summary='Lease expired before completion',
                error_retryable=1 WHERE job_id=? AND status=?""",
                (now, now, job_id, status),
            )
            _record_transition(
                conn,
                job_id=str(job_id),
                from_status=str(status),
                to_status="pending",
                reason="lease_expired",
                actor=actor,
                now_utc=now,
            )
            released.append(str(job_id))
        conn.commit()
    return released


def claim_next_workflow_job(
    state_db: str,
    queue_name: str,
    worker_id: str,
    ctx: RunContext,
    *,
    now_utc: str = "",
) -> WorkflowJob | None:
    queue = _require_queue(queue_name)
    if not worker_id.strip():
        raise AppError(
            code="workflow_queue_worker_missing",
            message="Worker ID is required",
            retryable=False,
        )
    now = _now(now_utc)
    with _state_conn(state_db, ctx) as conn:
        conn.execute("BEGIN IMMEDIATE")
        control = _ensure_control(conn, queue, now)
        if (
            not control.enabled
            or control.mode != "active"
            or control.emergency_stop_reason
        ):
            conn.commit()
            return None
        running = conn.execute(
            "SELECT COUNT(*) FROM workflow_jobs WHERE queue_name=? AND status IN ('leased','running')",
            (queue,),
        ).fetchone()[0]
        if int(running) >= control.worker_concurrency_limit:
            conn.commit()
            return None
        candidate = conn.execute(
            f"SELECT {_JOB_COLUMNS} FROM workflow_jobs WHERE queue_name=? "
            "AND status IN ('pending','retry_wait','budget_deferred') AND available_at_utc<=? "
            "AND attempt_count < max_attempts "
            "ORDER BY priority DESC,available_at_utc ASC,created_at_utc ASC,job_id ASC LIMIT 1",
            (queue, now),
        ).fetchone()
        if candidate is None:
            conn.commit()
            return None
        job = _job_from_row(candidate)
        expiry = _future(now, control.lease_seconds)
        updated = conn.execute(
            """UPDATE workflow_jobs SET status='leased',lease_owner=?,lease_expires_at_utc=?,
            heartbeat_at_utc=?,updated_at_utc=? WHERE job_id=? AND status=?""",
            (worker_id, expiry, now, now, job.job_id, job.status),
        ).rowcount
        if updated != 1:
            conn.rollback()
            return None
        _record_transition(
            conn,
            job_id=job.job_id,
            from_status=job.status,
            to_status="leased",
            reason="claimed",
            actor=worker_id,
            now_utc=now,
        )
        row = conn.execute(
            f"SELECT {_JOB_COLUMNS} FROM workflow_jobs WHERE job_id=?", (job.job_id,)
        ).fetchone()
        conn.commit()
    assert row is not None
    return _job_from_row(row)


def start_workflow_job(
    state_db: str, job_id: str, worker_id: str, ctx: RunContext, *, now_utc: str = ""
) -> WorkflowJob:
    now = _now(now_utc)
    with _state_conn(state_db, ctx) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            f"SELECT {_JOB_COLUMNS} FROM workflow_jobs WHERE job_id=?", (job_id,)
        ).fetchone()
        if row is None:
            raise AppError(
                code="workflow_queue_job_missing",
                message="Workflow job was not found",
                retryable=False,
            )
        job = _job_from_row(row)
        _assert_lease(job, worker_id, now, required_status="leased")
        attempt_number = job.attempt_count + 1
        if attempt_number > job.max_attempts:
            conn.execute(
                "UPDATE workflow_jobs SET status='dead_letter',completed_at_utc=?,updated_at_utc=?,"
                "lease_owner='',lease_expires_at_utc='',heartbeat_at_utc='',"
                "error_code='workflow_queue_attempts_exhausted',terminal_reason='attempts_exhausted' "
                "WHERE job_id=? AND status='leased' AND lease_owner=?",
                (now, now, job_id, worker_id),
            )
            _record_transition(
                conn,
                job_id=job_id,
                from_status="leased",
                to_status="dead_letter",
                reason="attempts_exhausted_before_start",
                actor=worker_id,
                now_utc=now,
            )
            conn.commit()
            raise AppError(
                code="workflow_queue_attempts_exhausted",
                message="Workflow job exhausted its automatic attempt budget",
                retryable=False,
                context={"job_id": job.job_id},
            )
        conn.execute(
            """UPDATE workflow_jobs SET status='running',attempt_count=?,started_at_utc=?,
            updated_at_utc=?,heartbeat_at_utc=? WHERE job_id=? AND status='leased' AND lease_owner=?""",
            (attempt_number, now, now, now, job_id, worker_id),
        )
        conn.execute(
            """INSERT INTO workflow_job_attempts(
            attempt_id,job_id,attempt_number,worker_id,started_at_utc,input_content_hash,
            execution_plan_hash,budget_decision
            ) VALUES(?,?,?,?,?,?,?,?)""",
            (
                str(uuid.uuid4()),
                job_id,
                attempt_number,
                worker_id,
                now,
                job.input_content_hash,
                job.execution_plan_hash,
                "approved",
            ),
        )
        _record_transition(
            conn,
            job_id=job_id,
            from_status="leased",
            to_status="running",
            reason="started",
            actor=worker_id,
            now_utc=now,
        )
        result = conn.execute(
            f"SELECT {_JOB_COLUMNS} FROM workflow_jobs WHERE job_id=?", (job_id,)
        ).fetchone()
        conn.commit()
    assert result is not None
    return _job_from_row(result)


def heartbeat_workflow_job(
    state_db: str, job_id: str, worker_id: str, ctx: RunContext, *, now_utc: str = ""
) -> WorkflowJob:
    now = _now(now_utc)
    with _state_conn(state_db, ctx) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            f"SELECT {_JOB_COLUMNS} FROM workflow_jobs WHERE job_id=?", (job_id,)
        ).fetchone()
        if row is None:
            raise AppError(
                code="workflow_queue_job_missing",
                message="Workflow job was not found",
                retryable=False,
            )
        job = _job_from_row(row)
        _assert_lease(job, worker_id, now)
        control = _ensure_control(conn, job.queue_name, now)
        expiry = _future(now, control.lease_seconds)
        changed = conn.execute(
            """UPDATE workflow_jobs SET heartbeat_at_utc=?,lease_expires_at_utc=?,updated_at_utc=?
            WHERE job_id=? AND lease_owner=? AND status IN ('leased','running')
            AND lease_expires_at_utc>?""",
            (now, expiry, now, job_id, worker_id, now),
        ).rowcount
        if changed != 1:
            raise AppError(
                code="workflow_queue_lease_lost",
                message="Worker no longer owns the job lease",
                retryable=False,
            )
        result = conn.execute(
            f"SELECT {_JOB_COLUMNS} FROM workflow_jobs WHERE job_id=?", (job_id,)
        ).fetchone()
        conn.commit()
    assert result is not None
    return _job_from_row(result)


def _assert_lease(
    job: WorkflowJob, worker_id: str, now: str, required_status: str = ""
) -> None:
    if required_status and job.status != required_status:
        raise AppError(
            code="workflow_queue_status_invalid",
            message="Workflow job is not in the required lifecycle state",
            retryable=False,
            context={
                "job_id": job.job_id,
                "status": job.status,
                "required_status": required_status,
            },
        )
    if (
        job.lease_owner != worker_id
        or not job.lease_expires_at_utc
        or _parse_time(job.lease_expires_at_utc) <= _parse_time(now)
    ):
        raise AppError(
            code="workflow_queue_lease_lost",
            message="Worker no longer owns an unexpired job lease",
            retryable=False,
            context={"job_id": job.job_id},
        )


def _submission_to_json(submission: WorkflowJobSubmission) -> str:
    return _json(
        {
            "schema_version": submission.schema_version,
            "queue_name": submission.queue_name,
            "job_type": submission.job_type,
            "payload": _payload_dict(submission.payload),
            "idempotency_key": submission.idempotency_key,
            "deduplication_scope": submission.deduplication_scope,
            "workflow_version": submission.workflow_version,
            "root_workflow_id": submission.root_workflow_id,
            "parent_job_id": submission.parent_job_id,
            "trigger_event_id": submission.trigger_event_id,
            "correlation_id": submission.correlation_id,
            "entity_type": submission.entity_type,
            "entity_id": submission.entity_id,
            "publisher_id": submission.publisher_id,
            "source_identity_id": submission.source_identity_id,
            "report_id": submission.report_id,
            "priority": submission.priority,
            "available_at_utc": submission.available_at_utc,
            "max_attempts": submission.max_attempts,
            "budget_profile": submission.budget_profile,
            "execution_plan_hash": submission.execution_plan_hash,
        }
    )


def _submission_from_json(raw: str) -> WorkflowJobSubmission:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AppError(
            code="workflow_queue_outbox_invalid",
            message="Outbox submission is not valid JSON",
            cause=exc,
            retryable=False,
        ) from exc
    if not isinstance(data, dict):
        raise AppError(
            code="workflow_queue_outbox_invalid",
            message="Outbox submission must be an object",
            retryable=False,
        )
    queue_name = _require_queue(str(data.get("queue_name") or ""))
    payload = _payload_from_json(queue_name, _json(data.get("payload") or {}))
    fields: dict[str, Any] = {
        name: data.get(name)
        for name in WorkflowJobSubmission.__dataclass_fields__
        if name not in {"payload"}
    }
    fields["payload"] = payload
    return WorkflowJobSubmission(**cast(Any, fields))


def complete_workflow_job(
    state_db: str,
    job_id: str,
    worker_id: str,
    result: WorkflowStageResult,
    downstream: list[WorkflowJobSubmission],
    ctx: RunContext,
    *,
    now_utc: str = "",
    provider_usage: dict[str, int | float | str] | None = None,
    external_effects: list[str] | None = None,
) -> WorkflowJob:
    """Commit success, attempt audit, transition and downstream outbox atomically."""
    if not result.output_verified:
        raise AppError(
            code="workflow_queue_output_unverified",
            message="A queue job cannot complete before its retained output is verified",
            retryable=False,
        )
    now = _now(now_utc)
    with _state_conn(state_db, ctx) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            f"SELECT {_JOB_COLUMNS} FROM workflow_jobs WHERE job_id=?", (job_id,)
        ).fetchone()
        if row is None:
            raise AppError(
                code="workflow_queue_job_missing",
                message="Workflow job was not found",
                retryable=False,
            )
        job = _job_from_row(row)
        _assert_lease(job, worker_id, now, required_status="running")
        control = _ensure_control(conn, job.queue_name, now)
        if len(downstream) > control.maximum_fanout:
            raise AppError(
                code="workflow_queue_fanout_exceeded",
                message="Job exceeds its bounded downstream fan-out",
                retryable=False,
                context={"job_id": job_id, "maximum_fanout": control.maximum_fanout},
            )
        for child in downstream:
            _require_queue(child.queue_name)
            if not child.parent_job_id or child.parent_job_id != job_id:
                raise AppError(
                    code="workflow_queue_child_lineage_invalid",
                    message="Downstream job must preserve direct parent lineage",
                    retryable=False,
                )
            if child.root_workflow_id != job.root_workflow_id:
                raise AppError(
                    code="workflow_queue_child_lineage_invalid",
                    message="Downstream job must preserve root workflow lineage",
                    retryable=False,
                )
        changed = conn.execute(
            """UPDATE workflow_jobs SET status='succeeded',output_reference=?,output_content_hash=?,
            execution_plan_hash=?,completed_at_utc=?,updated_at_utc=?,lease_owner='',
            lease_expires_at_utc='',heartbeat_at_utc='',error_code='',error_message_summary='',
            error_retryable=0,terminal_reason='' WHERE job_id=? AND status='running' AND lease_owner=?
            AND lease_expires_at_utc>?""",
            (
                result.output_reference,
                result.output_content_hash,
                result.execution_plan_hash or job.execution_plan_hash,
                now,
                now,
                job_id,
                worker_id,
                now,
            ),
        ).rowcount
        if changed != 1:
            raise AppError(
                code="workflow_queue_lease_lost",
                message="Stale worker cannot complete job",
                retryable=False,
            )
        conn.execute(
            """UPDATE workflow_job_attempts SET completed_at_utc=?,output_content_hash=?,
            execution_plan_hash=?,provider_usage_json=?,external_effects_json=?,outcome='succeeded'
            WHERE job_id=? AND attempt_number=? AND worker_id=?""",
            (
                now,
                result.output_content_hash,
                result.execution_plan_hash or job.execution_plan_hash,
                _json(provider_usage or {}),
                _json(external_effects or []),
                job_id,
                job.attempt_count,
                worker_id,
            ),
        )
        _record_transition(
            conn,
            job_id=job_id,
            from_status="running",
            to_status="succeeded",
            reason="output_verified",
            actor=worker_id,
            now_utc=now,
        )
        for child in downstream:
            event_key = ":".join(
                (
                    child.queue_name,
                    child.job_type,
                    child.deduplication_scope,
                    child.idempotency_key,
                )
            )
            conn.execute(
                """INSERT INTO workflow_outbox(
                event_id,event_key,parent_job_id,root_workflow_id,queue_name,job_type,submission_json,
                available_at_utc,created_at_utc,updated_at_utc
                ) VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(event_key) DO NOTHING""",
                (
                    str(uuid.uuid4()),
                    event_key,
                    job_id,
                    job.root_workflow_id,
                    child.queue_name,
                    child.job_type,
                    _submission_to_json(child),
                    child.available_at_utc or now,
                    now,
                    now,
                ),
            )
        completed = conn.execute(
            f"SELECT {_JOB_COLUMNS} FROM workflow_jobs WHERE job_id=?", (job_id,)
        ).fetchone()
        conn.commit()
    assert completed is not None
    return _job_from_row(completed)


def fail_workflow_job(
    state_db: str,
    job_id: str,
    worker_id: str,
    error: AppError,
    ctx: RunContext,
    *,
    now_utc: str = "",
    retry_at_utc: str = "",
    budget_deferred: bool = False,
    blocked: bool = False,
    remediation_id: str = "",
    external_effects: list[str] | None = None,
) -> WorkflowJob:
    """Record a classified outcome; retries remain bounded by the job contract."""
    now = _now(now_utc)
    with _state_conn(state_db, ctx) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            f"SELECT {_JOB_COLUMNS} FROM workflow_jobs WHERE job_id=?", (job_id,)
        ).fetchone()
        if row is None:
            raise AppError(
                code="workflow_queue_job_missing",
                message="Workflow job was not found",
                retryable=False,
            )
        job = _job_from_row(row)
        _assert_lease(job, worker_id, now, required_status="running")
        control = _ensure_control(conn, job.queue_name, now)
        if budget_deferred:
            target = "budget_deferred"
        elif blocked:
            target = "blocked"
        elif error.retryable and job.attempt_count < job.max_attempts:
            target = "retry_wait"
        else:
            target = "dead_letter"
        available = retry_at_utc.strip() or _future(now, control.retry_delay_seconds)
        if target in {"blocked", "dead_letter"}:
            available = job.available_at_utc
        changed = conn.execute(
            """UPDATE workflow_jobs SET status=?,available_at_utc=?,updated_at_utc=?,lease_owner='',
            lease_expires_at_utc='',heartbeat_at_utc='',error_code=?,error_message_summary=?,
            error_retryable=?,terminal_reason=?,remediation_id=? WHERE job_id=? AND status='running'
            AND lease_owner=? AND lease_expires_at_utc>?""",
            (
                target,
                available,
                now,
                error.code,
                _bounded_summary(error.message),
                1 if error.retryable else 0,
                error.code if target == "dead_letter" else "",
                remediation_id,
                job_id,
                worker_id,
                now,
            ),
        ).rowcount
        if changed != 1:
            raise AppError(
                code="workflow_queue_lease_lost",
                message="Stale worker cannot record failure",
                retryable=False,
            )
        conn.execute(
            """UPDATE workflow_job_attempts SET completed_at_utc=?,external_effects_json=?,outcome=?,error_code=?
            WHERE job_id=? AND attempt_number=? AND worker_id=?""",
            (
                now,
                _json(external_effects or []),
                target,
                error.code,
                job_id,
                job.attempt_count,
                worker_id,
            ),
        )
        _record_transition(
            conn,
            job_id=job_id,
            from_status="running",
            to_status=target,
            reason=error.code,
            actor=worker_id,
            now_utc=now,
            details={"retryable": error.retryable},
        )
        failed = conn.execute(
            f"SELECT {_JOB_COLUMNS} FROM workflow_jobs WHERE job_id=?", (job_id,)
        ).fetchone()
        conn.commit()
    assert failed is not None
    return _job_from_row(failed)


def cancel_workflow_job(
    state_db: str, job_id: str, actor: str, ctx: RunContext, *, now_utc: str = ""
) -> WorkflowJob:
    now = _now(now_utc)
    with _state_conn(state_db, ctx) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            f"SELECT {_JOB_COLUMNS} FROM workflow_jobs WHERE job_id=?", (job_id,)
        ).fetchone()
        if row is None:
            raise AppError(
                code="workflow_queue_job_missing",
                message="Workflow job was not found",
                retryable=False,
            )
        job = _job_from_row(row)
        if job.status not in {"pending", "retry_wait"}:
            raise AppError(
                code="workflow_queue_cancel_invalid",
                message="Only pending or retry-wait jobs can be cancelled",
                retryable=False,
            )
        conn.execute(
            "UPDATE workflow_jobs SET status='cancelled',updated_at_utc=?,terminal_reason='operator_cancelled' WHERE job_id=?",
            (now, job_id),
        )
        _record_transition(
            conn,
            job_id=job_id,
            from_status=job.status,
            to_status="cancelled",
            reason="operator_cancelled",
            actor=actor,
            now_utc=now,
        )
        result = conn.execute(
            f"SELECT {_JOB_COLUMNS} FROM workflow_jobs WHERE job_id=?", (job_id,)
        ).fetchone()
        conn.commit()
    assert result is not None
    return _job_from_row(result)


def requeue_workflow_job(
    state_db: str, job_id: str, actor: str, ctx: RunContext, *, now_utc: str = ""
) -> WorkflowJob:
    now = _now(now_utc)
    with _state_conn(state_db, ctx) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            f"SELECT {_JOB_COLUMNS} FROM workflow_jobs WHERE job_id=?", (job_id,)
        ).fetchone()
        if row is None:
            raise AppError(
                code="workflow_queue_job_missing",
                message="Workflow job was not found",
                retryable=False,
            )
        job = _job_from_row(row)
        if job.status not in {"blocked", "dead_letter"}:
            raise AppError(
                code="workflow_queue_requeue_invalid",
                message="Only blocked or dead-letter jobs require explicit requeue",
                retryable=False,
            )
        _payload_from_json(job.queue_name, job.payload_json)
        conn.execute(
            """UPDATE workflow_jobs SET status='pending',available_at_utc=?,updated_at_utc=?,
            lease_owner='',lease_expires_at_utc='',heartbeat_at_utc='',error_code='',
            error_message_summary='',error_retryable=0,terminal_reason='',remediation_id='' WHERE job_id=?""",
            (now, now, job_id),
        )
        _record_transition(
            conn,
            job_id=job_id,
            from_status=job.status,
            to_status="pending",
            reason="operator_requeue",
            actor=actor,
            now_utc=now,
        )
        result = conn.execute(
            f"SELECT {_JOB_COLUMNS} FROM workflow_jobs WHERE job_id=?", (job_id,)
        ).fetchone()
        conn.commit()
    assert result is not None
    return _job_from_row(result)


def materialize_workflow_outbox(
    state_db: str,
    worker_id: str,
    ctx: RunContext,
    *,
    limit: int = 50,
    now_utc: str = "",
) -> list[str]:
    """Turn committed downstream events into effective jobs without in-memory chaining."""
    now = _now(now_utc)
    materialised: list[str] = []
    for _ in range(max(1, limit)):
        with _state_conn(state_db, ctx) as conn:
            conn.execute("BEGIN IMMEDIATE")
            event = conn.execute(
                "SELECT event_id,parent_job_id,submission_json,attempt_count,max_attempts FROM workflow_outbox "
                "WHERE status IN ('pending','retry_wait') AND available_at_utc<=? "
                "ORDER BY available_at_utc,created_at_utc,event_id LIMIT 1",
                (now,),
            ).fetchone()
            if event is None:
                conn.commit()
                break
            event_id, parent_job_id, raw_submission, attempts, max_attempts = event
            changed = conn.execute(
                "UPDATE workflow_outbox SET status='leased',lease_owner=?,lease_expires_at_utc=?,updated_at_utc=? "
                "WHERE event_id=? AND status IN ('pending','retry_wait')",
                (worker_id, _future(now, 60), now, event_id),
            ).rowcount
            conn.commit()
        if changed != 1:
            continue
        try:
            submission = _submission_from_json(str(raw_submission))
            job, _created = enqueue_workflow_job(state_db, submission, ctx, now_utc=now)
        except AppError as exc:
            with _state_conn(state_db, ctx) as conn:
                conn.execute("BEGIN IMMEDIATE")
                target = (
                    "dead_letter"
                    if int(attempts) + 1 >= int(max_attempts) or not exc.retryable
                    else "retry_wait"
                )
                conn.execute(
                    """UPDATE workflow_outbox SET status=?,attempt_count=attempt_count+1,error_code=?,
                    available_at_utc=?,lease_owner='',lease_expires_at_utc='',updated_at_utc=?
                    WHERE event_id=? AND status='leased' AND lease_owner=?""",
                    (target, exc.code, _future(now, 60), now, event_id, worker_id),
                )
                conn.commit()
            continue
        with _state_conn(state_db, ctx) as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """UPDATE workflow_outbox SET status='materialised',materialised_job_id=?,
                lease_owner='',lease_expires_at_utc='',updated_at_utc=?
                WHERE event_id=? AND status='leased' AND lease_owner=?""",
                (job.job_id, now, event_id, worker_id),
            )
            if str(parent_job_id).startswith("briefing_opportunity:"):
                conn.execute(
                    "UPDATE workflow_briefing_opportunities SET generation_job_id=?,"
                    "updated_at_utc=? WHERE opportunity_id=? AND status='frozen' "
                    "AND generation_job_id=''",
                    (
                        job.job_id,
                        now,
                        str(parent_job_id).removeprefix("briefing_opportunity:"),
                    ),
                )
            conn.commit()
        materialised.append(job.job_id)
    return materialised


def list_workflow_job_attempts(
    state_db: str, job_id: str, ctx: RunContext
) -> list[WorkflowJobAttempt]:
    with _state_conn(state_db, ctx) as conn:
        rows = conn.execute(
            """SELECT attempt_id,job_id,attempt_number,worker_id,started_at_utc,completed_at_utc,
            input_content_hash,output_content_hash,execution_plan_hash,budget_decision,
            provider_usage_json,external_effects_json,outcome,error_code
            FROM workflow_job_attempts WHERE job_id=? ORDER BY attempt_number""",
            (job_id,),
        ).fetchall()
    return [
        WorkflowJobAttempt(
            schema_version="1.0",
            attempt_id=str(row[0]),
            job_id=str(row[1]),
            attempt_number=int(row[2]),
            worker_id=str(row[3]),
            started_at_utc=str(row[4]),
            completed_at_utc=str(row[5]),
            input_content_hash=str(row[6]),
            output_content_hash=str(row[7]),
            execution_plan_hash=str(row[8]),
            budget_decision=str(row[9]),
            provider_usage_json=str(row[10]),
            external_effects_json=str(row[11]),
            outcome=str(row[12]),
            error_code=str(row[13]),
        )
        for row in rows
    ]


def read_workflow_queue_health(
    state_db: str, ctx: RunContext, *, now_utc: str = ""
) -> list[WorkflowQueueHealth]:
    now = _now(now_utc)
    now_value = _parse_time(now)
    result: list[WorkflowQueueHealth] = []
    with _state_conn(state_db, ctx) as conn:
        for queue in WORKFLOW_QUEUE_NAMES:
            _ensure_control(conn, queue, now)
            counts = {
                str(status): int(count)
                for status, count in conn.execute(
                    "SELECT status,COUNT(*) FROM workflow_jobs WHERE queue_name=? GROUP BY status",
                    (queue,),
                ).fetchall()
            }
            pending_times = [
                str(row[0])
                for row in conn.execute(
                    "SELECT created_at_utc FROM workflow_jobs WHERE queue_name=? AND status='pending' ORDER BY created_at_utc LIMIT 1",
                    (queue,),
                ).fetchall()
            ]
            due_times = [
                str(row[0])
                for row in conn.execute(
                    "SELECT available_at_utc FROM workflow_jobs WHERE queue_name=? AND status IN ('pending','retry_wait','budget_deferred') AND available_at_utc<=? ORDER BY available_at_utc LIMIT 1",
                    (queue, now),
                ).fetchall()
            ]
            expired = int(
                conn.execute(
                    "SELECT COUNT(*) FROM workflow_jobs WHERE queue_name=? AND status IN ('leased','running') AND lease_expires_at_utc<=?",
                    (queue, now),
                ).fetchone()[0]
            )
            completed, terminal, retries, total_attempts, mean_attempts = conn.execute(
                """SELECT
                SUM(CASE WHEN status='succeeded' THEN 1 ELSE 0 END),
                SUM(CASE WHEN status='dead_letter' THEN 1 ELSE 0 END),
                SUM(CASE WHEN status='retry_wait' THEN 1 ELSE 0 END),COUNT(*),AVG(attempt_count)
                FROM workflow_jobs WHERE queue_name=?""",
                (queue,),
            ).fetchone()
            runtimes = [
                (_parse_time(str(end)) - _parse_time(str(start))).total_seconds()
                for start, end in conn.execute(
                    "SELECT a.started_at_utc,a.completed_at_utc FROM workflow_job_attempts a "
                    "JOIN workflow_jobs j ON j.job_id=a.job_id WHERE j.queue_name=? AND a.completed_at_utc<>'' "
                    "ORDER BY a.completed_at_utc DESC LIMIT 200",
                    (queue,),
                ).fetchall()
                if str(start) and str(end)
            ]
            runtimes.sort()
            p95 = (
                runtimes[min(len(runtimes) - 1, max(0, int(len(runtimes) * 0.95) - 1))]
                if runtimes
                else 0.0
            )
            outbox_pending = int(
                conn.execute(
                    "SELECT COUNT(*) FROM workflow_outbox WHERE queue_name=? AND status IN ('pending','leased','retry_wait')",
                    (queue,),
                ).fetchone()[0]
            )
            denominator = max(1, int(total_attempts or 0))
            result.append(
                WorkflowQueueHealth(
                    schema_version="1.0",
                    queue_name=queue,
                    status_counts=counts,
                    oldest_pending_age_seconds=max(
                        0,
                        int(
                            (now_value - _parse_time(pending_times[0])).total_seconds()
                        ),
                    )
                    if pending_times
                    else 0,
                    oldest_due_age_seconds=max(
                        0, int((now_value - _parse_time(due_times[0])).total_seconds())
                    )
                    if due_times
                    else 0,
                    lease_expiry_count=expired,
                    throughput_24h=sum(1 for value in runtimes if value >= 0),
                    completion_rate=float(completed or 0) / denominator,
                    retry_rate=float(retries or 0) / denominator,
                    terminal_rate=float(terminal or 0) / denominator,
                    mean_runtime_seconds=(sum(runtimes) / len(runtimes))
                    if runtimes
                    else 0.0,
                    p95_runtime_seconds=p95,
                    mean_attempts=float(mean_attempts or 0.0),
                    outbox_pending_count=outbox_pending,
                    reconciliation_anomaly_count=0,
                )
            )
    return result


def reconcile_workflow_queue(
    state_db: str, ctx: RunContext, *, now_utc: str = ""
) -> dict[str, list[str]]:
    """Repair only deterministic queue-store inconsistencies; report the rest."""
    now = _now(now_utc)
    released = release_expired_workflow_leases(state_db, ctx, now_utc=now)
    repaired_outbox: list[str] = []
    anomalies: list[str] = []
    with _state_conn(state_db, ctx) as conn:
        conn.execute("BEGIN IMMEDIATE")
        rows = conn.execute(
            "SELECT event_id,materialised_job_id FROM workflow_outbox WHERE status='materialised'"
        ).fetchall()
        for event_id, job_id in rows:
            found = conn.execute(
                "SELECT 1 FROM workflow_jobs WHERE job_id=?", (job_id,)
            ).fetchone()
            if found is None:
                conn.execute(
                    "UPDATE workflow_outbox SET status='pending',materialised_job_id='',available_at_utc=?,updated_at_utc=? WHERE event_id=?",
                    (now, now, event_id),
                )
                repaired_outbox.append(str(event_id))
        for job_id, _output_reference in conn.execute(
            "SELECT job_id,output_reference FROM workflow_jobs WHERE status='succeeded' AND output_reference=''"
        ).fetchall():
            anomalies.append(f"succeeded_job_missing_output_reference:{job_id}")
        conn.commit()
    return {
        "released_leases": released,
        "repaired_outbox_events": repaired_outbox,
        "anomalies": anomalies,
    }


def _readiness_from_row(row: tuple[object, ...]) -> PublicationReadinessRecord:
    return PublicationReadinessRecord(
        schema_version="1.0",
        package_checksum=str(row[0]),
        entity_type=str(row[1]),
        package_reference=str(row[2]),
        validation_reference=str(row[3]),
        lineage_reference=str(row[4]),
        required_asset_status=str(row[5]),
        readiness_status=str(row[6]),
        reason=str(row[7]),
        created_at_utc=str(row[8]),
        updated_at_utc=str(row[9]),
    )


def record_publication_readiness(
    state_db: str,
    *,
    package_checksum: str,
    entity_type: str,
    package_reference: str,
    validation_reference: str,
    lineage_reference: str,
    required_asset_status: str,
    readiness_status: str,
    reason: str,
    ctx: RunContext,
    now_utc: str = "",
) -> PublicationReadinessRecord:
    """Persist immutable readiness for a package checksum, never a mutable draft."""
    if readiness_status not in {
        "awaiting_review",
        "approved",
        "rejected",
        "repair_required",
        "not_publishable",
    }:
        raise AppError(
            code="workflow_publication_readiness_invalid",
            message="Publication readiness status is invalid",
            retryable=False,
        )
    if not package_checksum or not package_reference or not entity_type:
        raise AppError(
            code="workflow_publication_readiness_invalid",
            message="Publication package checksum, reference and entity type are required",
            retryable=False,
        )
    now = _now(now_utc)
    with _state_conn(state_db, ctx) as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """INSERT INTO workflow_publication_readiness(
            package_checksum,entity_type,package_reference,validation_reference,
            lineage_reference,required_asset_status,readiness_status,reason,
            created_at_utc,updated_at_utc
            ) VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(package_checksum) DO NOTHING""",
            (
                package_checksum,
                entity_type,
                package_reference,
                validation_reference,
                lineage_reference,
                required_asset_status,
                readiness_status,
                _bounded_summary(reason),
                now,
                now,
            ),
        )
        row = conn.execute(
            "SELECT package_checksum,entity_type,package_reference,validation_reference,"
            "lineage_reference,required_asset_status,readiness_status,reason,created_at_utc,"
            "updated_at_utc FROM workflow_publication_readiness WHERE package_checksum=?",
            (package_checksum,),
        ).fetchone()
        conn.commit()
    assert row is not None
    return _readiness_from_row(row)


def approve_publication_package(
    state_db: str,
    *,
    package_checksum: str,
    actor_id: str,
    note: str,
    publish_submission: WorkflowJobSubmission,
    ctx: RunContext,
    now_utc: str = "",
) -> PublicationApprovalRecord:
    """Approve a fixed package and durably schedule, never execute, publication."""
    if publish_submission.queue_name != "wordpress_publish":
        raise AppError(
            code="workflow_publication_approval_submission_invalid",
            message="Approval may enqueue only the WordPress publication queue",
            retryable=False,
        )
    payload = publish_submission.payload
    if (
        not isinstance(payload, WordPressPublishPayload)
        or payload.package_checksum != package_checksum
    ):
        raise AppError(
            code="workflow_publication_approval_checksum_invalid",
            message="Publication submission does not reference the approved package checksum",
            retryable=False,
        )
    now = _now(now_utc)
    with _state_conn(state_db, ctx) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT package_checksum,entity_type,package_reference,validation_reference,"
            "lineage_reference,required_asset_status,readiness_status,reason,created_at_utc,"
            "updated_at_utc FROM workflow_publication_readiness WHERE package_checksum=?",
            (package_checksum,),
        ).fetchone()
        if row is None:
            raise AppError(
                code="workflow_publication_readiness_missing",
                message="Publication package has no retained readiness result",
                retryable=False,
            )
        readiness = _readiness_from_row(row)
        if readiness.readiness_status == "approved":
            prior = conn.execute(
                "SELECT approval_id,package_checksum,actor_id,note,action,created_at_utc "
                "FROM workflow_publication_approvals WHERE package_checksum=? AND action='approved' "
                "ORDER BY created_at_utc LIMIT 1",
                (package_checksum,),
            ).fetchone()
            if prior is not None:
                conn.commit()
                return PublicationApprovalRecord(
                    schema_version="1.0",
                    approval_id=str(prior[0]),
                    package_checksum=str(prior[1]),
                    actor_id=str(prior[2]),
                    note=str(prior[3]),
                    action=str(prior[4]),
                    created_at_utc=str(prior[5]),
                )
        if readiness.readiness_status != "awaiting_review":
            raise AppError(
                code="workflow_publication_approval_invalid",
                message="Only an awaiting-review package can be approved",
                retryable=False,
                context={"status": readiness.readiness_status},
            )
        approval_id = str(uuid.uuid4())
        conn.execute(
            "UPDATE workflow_publication_readiness SET readiness_status='approved',"
            "updated_at_utc=? WHERE package_checksum=? AND readiness_status='awaiting_review'",
            (now, package_checksum),
        )
        conn.execute(
            """INSERT INTO workflow_publication_approvals(
            approval_id,package_checksum,actor_id,note,action,created_at_utc
            ) VALUES(?,?,?,?,?,?)""",
            (
                approval_id,
                package_checksum,
                actor_id,
                _bounded_summary(note),
                "approved",
                now,
            ),
        )
        approved_payload = replace(payload, approval_id=approval_id)
        approved_submission = replace(publish_submission, payload=approved_payload)
        event_key = ":".join(
            (
                approved_submission.queue_name,
                approved_submission.job_type,
                approved_submission.deduplication_scope,
                approved_submission.idempotency_key,
            )
        )
        conn.execute(
            """INSERT INTO workflow_outbox(
            event_id,event_key,parent_job_id,root_workflow_id,queue_name,job_type,
            submission_json,available_at_utc,created_at_utc,updated_at_utc
            ) VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(event_key) DO NOTHING""",
            (
                str(uuid.uuid4()),
                event_key,
                "publication_approval:" + approval_id,
                approved_submission.root_workflow_id or package_checksum,
                approved_submission.queue_name,
                approved_submission.job_type,
                _submission_to_json(approved_submission),
                approved_submission.available_at_utc or now,
                now,
                now,
            ),
        )
        conn.commit()
    return PublicationApprovalRecord(
        schema_version="1.0",
        approval_id=approval_id,
        package_checksum=package_checksum,
        actor_id=actor_id,
        note=_bounded_summary(note),
        action="approved",
        created_at_utc=now,
    )


def _opportunity_from_row(row: tuple[object, ...]) -> BriefingOpportunity:
    def _strings(raw: object) -> list[str]:
        try:
            parsed = json.loads(str(raw or "[]"))
        except json.JSONDecodeError:
            return []
        return (
            sorted({str(item) for item in parsed if str(item).strip()})
            if isinstance(parsed, list)
            else []
        )

    return BriefingOpportunity(
        schema_version="1.0",
        opportunity_id=str(row[0]),
        opportunity_key=str(row[1]),
        topic=str(row[2]),
        geography=str(row[3]),
        rolling_window=str(row[4]),
        briefing_policy_version=str(row[5]),
        source_hashes=_strings(row[6]),
        publisher_ids=_strings(row[7]),
        frozen_source_manifest=str(row[8]),
        frozen_source_hashes=_strings(row[9]),
        status=str(row[10]),
        generation_job_id=str(row[11]),
        last_generated_at_utc=str(row[12]),
        created_at_utc=str(row[13]),
        updated_at_utc=str(row[14]),
    )


def upsert_briefing_opportunity(
    state_db: str,
    *,
    topic: str,
    geography: str,
    rolling_window: str,
    briefing_policy_version: str,
    source_hashes: list[str],
    publisher_ids: list[str],
    minimum_distinct_reports: int,
    minimum_publisher_diversity: int,
    ctx: RunContext,
    now_utc: str = "",
) -> BriefingOpportunity:
    """Aggregate deterministic source membership; frozen work is deliberately immutable."""
    normalized_hashes = sorted({item.strip() for item in source_hashes if item.strip()})
    normalized_publishers = sorted(
        {item.strip() for item in publisher_ids if item.strip()}
    )
    if (
        not topic.strip()
        or not rolling_window.strip()
        or not briefing_policy_version.strip()
    ):
        raise AppError(
            code="workflow_briefing_opportunity_invalid",
            message="Briefing opportunity identity is incomplete",
            retryable=False,
        )
    opportunity_key = ":".join(
        (
            topic.strip().lower(),
            geography.strip().lower(),
            rolling_window.strip(),
            briefing_policy_version.strip(),
        )
    )
    now = _now(now_utc)
    with _state_conn(state_db, ctx) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT opportunity_id,opportunity_key,topic,geography,rolling_window,"
            "briefing_policy_version,source_hashes_json,publisher_ids_json,frozen_source_manifest,"
            "frozen_source_hashes_json,status,generation_job_id,last_generated_at_utc,"
            "created_at_utc,updated_at_utc FROM workflow_briefing_opportunities "
            "WHERE opportunity_key=?",
            (opportunity_key,),
        ).fetchone()
        if row is None:
            opportunity_id = str(uuid.uuid4())
            status = (
                "eligible"
                if len(normalized_hashes) >= max(1, minimum_distinct_reports)
                and len(normalized_publishers) >= max(1, minimum_publisher_diversity)
                else "collecting"
            )
            conn.execute(
                """INSERT INTO workflow_briefing_opportunities(
                opportunity_id,opportunity_key,topic,geography,rolling_window,
                briefing_policy_version,source_hashes_json,publisher_ids_json,status,
                created_at_utc,updated_at_utc
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    opportunity_id,
                    opportunity_key,
                    topic.strip(),
                    geography.strip(),
                    rolling_window.strip(),
                    briefing_policy_version.strip(),
                    _json(normalized_hashes),
                    _json(normalized_publishers),
                    status,
                    now,
                    now,
                ),
            )
        else:
            existing = _opportunity_from_row(row)
            if existing.status not in {"frozen", "generated"}:
                merged_hashes = sorted(
                    set(existing.source_hashes) | set(normalized_hashes)
                )
                merged_publishers = sorted(
                    set(existing.publisher_ids) | set(normalized_publishers)
                )
                status = (
                    "eligible"
                    if len(merged_hashes) >= max(1, minimum_distinct_reports)
                    and len(merged_publishers) >= max(1, minimum_publisher_diversity)
                    else "collecting"
                )
                conn.execute(
                    "UPDATE workflow_briefing_opportunities SET source_hashes_json=?,"
                    "publisher_ids_json=?,status=?,updated_at_utc=? WHERE opportunity_id=?",
                    (
                        _json(merged_hashes),
                        _json(merged_publishers),
                        status,
                        now,
                        existing.opportunity_id,
                    ),
                )
        fresh = conn.execute(
            "SELECT opportunity_id,opportunity_key,topic,geography,rolling_window,"
            "briefing_policy_version,source_hashes_json,publisher_ids_json,frozen_source_manifest,"
            "frozen_source_hashes_json,status,generation_job_id,last_generated_at_utc,"
            "created_at_utc,updated_at_utc FROM workflow_briefing_opportunities "
            "WHERE opportunity_key=?",
            (opportunity_key,),
        ).fetchone()
        conn.commit()
    assert fresh is not None
    return _opportunity_from_row(fresh)


def freeze_briefing_opportunity(
    state_db: str,
    *,
    opportunity_id: str,
    frozen_source_manifest: str,
    generation_submission: WorkflowJobSubmission,
    ctx: RunContext,
    now_utc: str = "",
) -> BriefingOpportunity:
    """Freeze an eligible source set and enqueue exactly one effective generation job."""
    if generation_submission.queue_name != "briefing_generation":
        raise AppError(
            code="workflow_briefing_generation_submission_invalid",
            message="A Briefing opportunity may enqueue only briefing generation",
            retryable=False,
        )
    payload = generation_submission.payload
    if not isinstance(payload, BriefingGenerationPayload):
        raise AppError(
            code="workflow_briefing_generation_submission_invalid",
            message="Briefing generation requires its typed frozen-manifest payload",
            retryable=False,
        )
    now = _now(now_utc)
    with _state_conn(state_db, ctx) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT opportunity_id,opportunity_key,topic,geography,rolling_window,"
            "briefing_policy_version,source_hashes_json,publisher_ids_json,frozen_source_manifest,"
            "frozen_source_hashes_json,status,generation_job_id,last_generated_at_utc,"
            "created_at_utc,updated_at_utc FROM workflow_briefing_opportunities "
            "WHERE opportunity_id=?",
            (opportunity_id,),
        ).fetchone()
        if row is None:
            raise AppError(
                code="workflow_briefing_opportunity_missing",
                message="Briefing opportunity was not found",
                retryable=False,
            )
        opportunity = _opportunity_from_row(row)
        if opportunity.status == "generated":
            conn.commit()
            return opportunity
        if opportunity.status not in {"eligible", "frozen"}:
            raise AppError(
                code="workflow_briefing_opportunity_not_eligible",
                message="Briefing opportunity does not meet deterministic eligibility",
                retryable=False,
                context={"status": opportunity.status},
            )
        selected_hashes = sorted(set(payload.sorted_source_hashes))
        if not selected_hashes or not set(selected_hashes).issubset(
            set(opportunity.source_hashes)
        ):
            raise AppError(
                code="workflow_briefing_source_set_invalid",
                message="Frozen Briefing source set must be a non-empty opportunity subset",
                retryable=False,
            )
        if (
            opportunity.status == "frozen"
            and selected_hashes != opportunity.frozen_source_hashes
        ):
            raise AppError(
                code="workflow_briefing_source_set_immutable",
                message="A frozen Briefing opportunity cannot change its source manifest",
                retryable=False,
            )
        event_key = ":".join(
            (
                generation_submission.queue_name,
                generation_submission.job_type,
                generation_submission.deduplication_scope,
                generation_submission.idempotency_key,
            )
        )
        if opportunity.status == "eligible":
            conn.execute(
                "UPDATE workflow_briefing_opportunities SET status='frozen',"
                "frozen_source_manifest=?,frozen_source_hashes_json=?,updated_at_utc=? "
                "WHERE opportunity_id=? AND status='eligible'",
                (
                    frozen_source_manifest,
                    _json(selected_hashes),
                    now,
                    opportunity_id,
                ),
            )
        conn.execute(
            """INSERT INTO workflow_outbox(
            event_id,event_key,parent_job_id,root_workflow_id,queue_name,job_type,
            submission_json,available_at_utc,created_at_utc,updated_at_utc
            ) VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(event_key) DO NOTHING""",
            (
                str(uuid.uuid4()),
                event_key,
                "briefing_opportunity:" + opportunity_id,
                generation_submission.root_workflow_id or opportunity_id,
                generation_submission.queue_name,
                generation_submission.job_type,
                _submission_to_json(generation_submission),
                generation_submission.available_at_utc or now,
                now,
                now,
            ),
        )
        fresh = conn.execute(
            "SELECT opportunity_id,opportunity_key,topic,geography,rolling_window,"
            "briefing_policy_version,source_hashes_json,publisher_ids_json,frozen_source_manifest,"
            "frozen_source_hashes_json,status,generation_job_id,last_generated_at_utc,"
            "created_at_utc,updated_at_utc FROM workflow_briefing_opportunities "
            "WHERE opportunity_id=?",
            (opportunity_id,),
        ).fetchone()
        conn.commit()
    assert fresh is not None
    return _opportunity_from_row(fresh)


def publication_approval_is_valid(
    state_db: str,
    *,
    package_checksum: str,
    approval_id: str,
    ctx: RunContext,
) -> bool:
    """Read-only preflight used by WordPress workers before every write."""
    with _state_conn(state_db, ctx) as conn:
        row = conn.execute(
            """SELECT 1 FROM workflow_publication_readiness r
            JOIN workflow_publication_approvals a ON a.package_checksum=r.package_checksum
            WHERE r.package_checksum=? AND r.readiness_status='approved'
            AND a.approval_id=? AND a.action='approved'""",
            (package_checksum, approval_id),
        ).fetchone()
    return row is not None
