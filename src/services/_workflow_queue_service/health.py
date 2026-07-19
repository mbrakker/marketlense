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

from .leasing import release_expired_workflow_leases
from .schema import _ensure_control, _now, _parse_time


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


def read_workflow_queue_evidence_summary(
    state_db: str, ctx: RunContext
) -> WorkflowQueueEvidenceSummary:
    """Return bounded scalar queue evidence without exposing job payloads."""
    with _state_conn(state_db, ctx) as conn:
        schema_row = conn.execute(
            "SELECT current_version FROM schema_version WHERE database_key='state_db'"
        ).fetchone()
        job_count = int(
            conn.execute("SELECT COUNT(*) FROM workflow_jobs").fetchone()[0]
        )
        transition_counts = {
            str(status): int(count)
            for status, count in conn.execute(
                "SELECT to_status,COUNT(*) FROM workflow_job_transitions "
                "GROUP BY to_status ORDER BY to_status"
            ).fetchall()
        }
        status_counts = {
            str(status): int(count)
            for status, count in conn.execute(
                "SELECT status,COUNT(*) FROM workflow_jobs GROUP BY status ORDER BY status"
            ).fetchall()
        }
        outbox_status_counts = {
            str(status): int(count)
            for status, count in conn.execute(
                "SELECT status,COUNT(*) FROM workflow_outbox GROUP BY status ORDER BY status"
            ).fetchall()
        }
        publication_readiness_counts = {
            str(status): int(count)
            for status, count in conn.execute(
                "SELECT readiness_status,COUNT(*) FROM workflow_publication_readiness "
                "GROUP BY readiness_status ORDER BY readiness_status"
            ).fetchall()
        }
        approval_count = int(
            conn.execute(
                "SELECT COUNT(*) FROM workflow_publication_approvals"
            ).fetchone()[0]
        )
        external_effect_count = 0
        for (raw_effects,) in conn.execute(
            "SELECT external_effects_json FROM workflow_job_attempts"
        ).fetchall():
            try:
                effects = json.loads(str(raw_effects or "[]"))
            except json.JSONDecodeError as exc:
                raise AppError(
                    code="workflow_queue_attempt_effects_invalid",
                    message="Workflow attempt external-effects metadata is invalid",
                    cause=exc,
                    retryable=False,
                ) from exc
            if not isinstance(effects, list) or not all(
                isinstance(effect, str) for effect in effects
            ):
                raise AppError(
                    code="workflow_queue_attempt_effects_invalid",
                    message="Workflow attempt external-effects metadata must be a string list",
                    retryable=False,
                )
            external_effect_count += len(effects)
    return WorkflowQueueEvidenceSummary(
        state_schema_version=int(schema_row[0]) if schema_row is not None else 0,
        job_count=job_count,
        transition_counts=transition_counts,
        status_counts=status_counts,
        outbox_status_counts=outbox_status_counts,
        publication_readiness_counts=publication_readiness_counts,
        approval_count=approval_count,
        external_effect_count=external_effect_count,
    )


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
