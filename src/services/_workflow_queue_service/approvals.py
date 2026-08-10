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

from .schema import _bounded_summary, _now
from .submission import _submission_to_json


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
        if (
            readiness.entity_type != payload.entity_type
            or readiness.package_reference != payload.entity_package_reference
        ):
            raise AppError(
                code="workflow_publication_approval_reference_mismatch",
                message="Publication submission must use the exact readiness package reference",
                retryable=False,
            )
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
        approved_payload = replace(
            payload,
            approval_id=approval_id,
            readiness_reference=(
                readiness.validation_reference
                if payload.entity_type == "report"
                else payload.readiness_reference
            ),
        )
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
