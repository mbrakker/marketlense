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
    _ensure_control,
    _future,
    _job_from_row,
    _now,
    _parse_time,
    _record_transition,
    _require_queue,
)


def acquire_workflow_supervisor_lease(
    state_db: str,
    *,
    owner_id: str,
    now_utc: str,
    lease_seconds: int,
    ctx: RunContext,
) -> bool:
    """Atomically acquire the one active supervisor lease or return busy."""

    if not owner_id.strip():
        raise AppError(
            code="workflow_supervisor_owner_missing",
            message="Supervisor owner identity is required",
            retryable=False,
        )
    now = _now(now_utc)
    expiry = _future(now, lease_seconds)
    with _state_conn(state_db, ctx) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT owner_id,lease_expires_at_utc FROM workflow_supervisor_lease "
            "WHERE lease_name='default'"
        ).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO workflow_supervisor_lease(lease_name,owner_id,lease_expires_at_utc,updated_at_utc) "
                "VALUES('default',?,?,?)",
                (owner_id, expiry, now),
            )
            conn.commit()
            return True
        current_owner, current_expiry = str(row[0] or ""), str(row[1] or "")
        if (
            current_owner
            and current_owner != owner_id
            and _parse_time(current_expiry) > _parse_time(now)
        ):
            conn.commit()
            return False
        updated = conn.execute(
            "UPDATE workflow_supervisor_lease SET owner_id=?,lease_expires_at_utc=?,updated_at_utc=? "
            "WHERE lease_name='default'",
            (owner_id, expiry, now),
        ).rowcount
        conn.commit()
    return updated == 1


def release_workflow_supervisor_lease(
    state_db: str, *, owner_id: str, now_utc: str, ctx: RunContext
) -> None:
    """Release only the caller's lease; another supervisor cannot be cleared."""

    with _state_conn(state_db, ctx) as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "UPDATE workflow_supervisor_lease SET owner_id='',lease_expires_at_utc='',updated_at_utc=? "
            "WHERE lease_name='default' AND owner_id=?",
            (_now(now_utc), owner_id),
        )
        conn.commit()


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
