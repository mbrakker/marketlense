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
