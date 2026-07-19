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

from .schema import _future, _now
from .submission import _submission_from_json, enqueue_workflow_job


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
