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

from .leasing import _assert_lease
from .schema import (
    _JOB_COLUMNS,
    _bounded_summary,
    _ensure_control,
    _future,
    _job_from_row,
    _json,
    _now,
    _payload_from_json,
    _record_transition,
    _require_queue,
)
from .submission import _submission_to_json


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
