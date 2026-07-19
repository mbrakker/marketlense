"""SQLite-backed durable queue storage for all MarketLense workflows.

This service owns queue persistence and no domain generation.  It uses the
canonical state database so queue transitions, remediation and workflow-control
observations survive the same host restart.  The public functions intentionally
use typed contracts and immutable references rather than a generic task blob.
"""

# ruff: noqa: E501, F401

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
    WorkflowQueueEvidenceSummary,
    WorkflowQueueHealth,
    WorkflowStageResult,
)
from src.services._state_service.common import _state_conn
from src.utils.clock import utc_now_seconds_iso
from src.utils.errors import AppError

from .schema import (
    _JOB_COLUMNS,
    _PAYLOAD_TYPES,
    _ensure_control,
    _job_from_row,
    _json,
    _now,
    _parse_time,
    _payload_dict,
    _payload_from_json,
    _record_transition,
    _require_queue,
)


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
