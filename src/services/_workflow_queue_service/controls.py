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

from .schema import _ensure_control, _now, _require_queue


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
