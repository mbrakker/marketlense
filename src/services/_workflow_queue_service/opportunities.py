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

from .schema import _json, _now
from .submission import _submission_to_json


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
