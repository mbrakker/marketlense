"""Code-reviewed typed handler registry for the durable workflow queue.

The registry is deliberately not a DAG authoring system.  It defines the fixed
MarketLense graph, payload/result contracts, and the only downstream queue types
that a handler may request.  Domain adapters can be replaced incrementally while
the queue lifecycle remains unchanged.
"""

# ruff: noqa: E501, F401

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Callable

from src.contracts.acquisition_handoff import VerifiedAcquisitionIngestHandoffRequest
from src.contracts.analytics_projection import (
    PROJECTION_SCHEMA_VERSION,
    ClaimEmbeddingWorkflowRequest,
)
from src.contracts.browser_download import (
    ReportDownloadDriveUpload,
    ReportDownloadOrchestratorRequest,
)
from src.contracts.config import ConfigLoadRequest, IngestSettingsBuildRequest
from src.contracts.cover_images import CoverImageGenerationRequest, CoverImageReport
from src.contracts.cross_report_analysis import (
    CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
    CrossReportAnalysisOrchestratorRequest,
    CrossReportAnalysisRequest,
    CrossReportProjectedDataReadRequest,
    CrossReportPublishPackage,
)
from src.contracts.drive import DriveFile
from src.contracts.files import ReadBytesRequest, WriteBytesRequest
from src.contracts.mailbox_acquisition import MailReportAcquisitionRequest
from src.contracts.publisher_inventory import PublisherInventoryDiscoveryRequest
from src.contracts.report_cards import CoverFingerprint
from src.contracts.run_budget import BudgetOverrideContext
from src.contracts.run_context import RunContext
from src.contracts.signal_candidates import (
    SIGNAL_CANDIDATE_SCHEMA_VERSION,
    SignalCandidateExtractionRequest,
)
from src.contracts.wordpress_entities import (
    WORDPRESS_ENTITY_SCHEMA_VERSION,
    SignalPostGenerationRequest,
    SignalPostWorkflowRequest,
    SignalPublishProjection,
)
from src.contracts.wordpress_intelligence_projection import (
    WORDPRESS_INTELLIGENCE_SCHEMA_VERSION,
    WordPressIntelligenceSourceReadRequest,
    WordPressIntelligenceSyncRequest,
)
from src.contracts.workflow_queue import (
    AnalyticsProjectionPayload,
    AnalyticsProjectionResult,
    BriefingGenerationPayload,
    BriefingGenerationResult,
    BriefingOpportunityPayload,
    BriefingOpportunityResult,
    ClaimEmbeddingPayload,
    ClaimEmbeddingResult,
    CoverGenerationPayload,
    CoverGenerationResult,
    MailboxDeliveryPayload,
    MailboxDeliveryResult,
    MaintenancePayload,
    PublicationReadinessPayload,
    PublicationReadinessResult,
    PublisherDiscoveryPayload,
    PublisherDiscoveryResult,
    QueuePayload,
    ReportAcquisitionPayload,
    ReportAcquisitionResult,
    ReportAnalysisPayload,
    ReportAnalysisResult,
    ReportRenderPayload,
    ReportRenderResult,
    ReportSelectionPayload,
    ReportSelectionResult,
    SignalCandidatePayload,
    SignalCandidateResult,
    SignalGenerationPayload,
    SignalGenerationResult,
    SourceIngestPayload,
    SourceIngestResult,
    WordPressProjectionPayload,
    WordPressProjectionResult,
    WordPressPublishPayload,
    WordPressPublishResult,
    WorkflowJob,
    WorkflowJobSubmission,
    WorkflowStageResult,
)
from src.generators.cover_image_generator import generate_cover_images
from src.orchestrators.acquisition_ingest_handoff_orchestrator import (
    build_source_ingest_submission_from_verified_acquisition,
)
from src.orchestrators.claim_embedding_orchestrator import (
    run_claim_embedding_workflow,
)
from src.orchestrators.cross_report_analysis_orchestrator import (
    run_cross_report_analysis,
)
from src.orchestrators.mail_report_acquisition_orchestrator import (
    run_mail_report_acquisition,
)
from src.orchestrators.publish_orchestrator import publish_cross_report_package
from src.orchestrators.publisher_inventory_orchestrator import (
    run_publisher_inventory_discovery,
)
from src.orchestrators.report_download_orchestrator import run_report_download
from src.orchestrators.report_pipeline_orchestrator import run_report_pipeline
from src.orchestrators.signal_candidate_orchestrator import (
    run_signal_candidate_extraction,
)
from src.orchestrators.signal_post_orchestrator import (
    generate_signal_post_projection,
)
from src.orchestrators.wordpress_intelligence_projection_orchestrator import (
    sync_wordpress_intelligence_projection,
)
from src.services import analytics_store_service
from src.services.config_service import (
    build_ingest_settings,
    load_browser_download_settings,
    load_mailbox_acquisition_settings,
    load_publish_settings,
    load_publisher_inventory_settings,
    load_settings,
)
from src.services.file_service import read_bytes, write_bytes
from src.services.workflow_queue_service import (
    freeze_briefing_opportunity,
    publication_approval_is_valid,
    record_publication_readiness,
    upsert_briefing_opportunity,
)
from src.utils.clock import utc_now_iso
from src.utils.errors import AppError
from src.utils.wp_auth import build_auth_header

from .report_pipeline import _report_stage_handler
from .shared import (
    WorkflowQueueHandlerResult,
    _boolean_attribute,
    _digest,
    _positive_float_attribute,
    _positive_int_attribute,
)


def _claim_embedding_handler(
    job: WorkflowJob, payload: QueuePayload, ctx: RunContext
) -> WorkflowQueueHandlerResult:
    """Run the existing bounded claim-embedding queue for canonical rows only."""

    assert isinstance(payload, ClaimEmbeddingPayload)
    model = payload.model_version or str(
        payload.attributes.get("model", "text-embedding-3-small")
    )
    dry_run = _boolean_attribute(payload, "dry_run", False)
    limit = _positive_int_attribute(payload, "limit", 1)
    max_reports = _positive_int_attribute(payload, "max_reports", 1)
    max_estimated_tokens = _positive_int_attribute(
        payload, "max_estimated_tokens", 8_000
    )
    max_estimated_cost_usd = _positive_float_attribute(
        payload, "max_estimated_cost_usd", 1.0
    )
    max_runtime_seconds = _positive_float_attribute(
        payload, "max_runtime_seconds", 120.0
    )
    max_retries = _positive_int_attribute(payload, "max_retries", 3)
    publisher_fairness_limit = _positive_int_attribute(
        payload, "publisher_fairness_limit", 3
    )
    config_path = str(payload.attributes.get("config_path", ""))
    app = load_settings(ConfigLoadRequest(schema_version="1.0", path=config_path), ctx)
    if not dry_run and not app.openai_api_key:
        raise AppError(
            code="credentials_required",
            message="Claim embedding work requires configured provider credentials",
            retryable=False,
        )
    response = run_claim_embedding_workflow(
        ClaimEmbeddingWorkflowRequest(
            schema_version=PROJECTION_SCHEMA_VERSION,
            db_path=app.reports_db,
            api_key="" if dry_run else app.openai_api_key,
            provider=str(payload.attributes.get("provider", "openai")),
            model=model,
            embedding_version=str(
                payload.attributes.get("embedding_version", "claim-embedding.v1")
            ),
            limit=limit,
            timeout_seconds=None,
            ctx=ctx,
            cost_ledger_path=app.cost_ledger_path,
            cost_daily_path=app.cost_daily_path,
            model_pricing=getattr(app, "model_pricing", {}),
            max_reports=max_reports,
            max_estimated_tokens=max_estimated_tokens,
            max_estimated_cost_usd=max_estimated_cost_usd,
            max_runtime_seconds=max_runtime_seconds,
            max_retries=max_retries,
            max_concurrent_provider_calls=1,
            publisher_fairness_limit=publisher_fairness_limit,
            report_ids=[job.report_id] if job.report_id else [],
            publishers=[job.publisher_id] if job.publisher_id else [],
            dry_run=dry_run,
            state_db=app.state_db,
        )
    )
    return WorkflowQueueHandlerResult(
        result=WorkflowStageResult(
            output_reference=(
                payload.embedding_row_id
                or payload.claim_id
                or f"claim-embedding:{job.job_id}"
            ),
            output_content_hash=_digest(
                payload.embedding_row_id,
                payload.claim_id,
                str(response.embedded_count),
                str(response.failed_count),
            ),
            execution_plan_hash=job.execution_plan_hash,
            output_verified=response.failed_count == 0,
            summary={
                "embedded_count": response.embedded_count,
                "failed_count": response.failed_count,
                "skipped_count": response.skipped_count,
            },
        ),
        provider_usage={
            "input_tokens": response.actual_input_tokens,
            "estimated_cost_usd": response.actual_cost_usd,
            "provider_calls": response.embedded_count,
        },
        external_effects=["embedding"] if response.embedded_count else [],
    )


def _analytics_projection_handler(
    job: WorkflowJob, payload: QueuePayload, ctx: RunContext
) -> WorkflowQueueHandlerResult:
    """Project a report, then durably fan out only source-linked derived work."""

    assert isinstance(payload, AnalyticsProjectionPayload)
    stage_result = _report_stage_handler(
        resume_from_stage="analysis_complete", projection_only=True
    )(job, payload, ctx)
    app = load_settings(ConfigLoadRequest(schema_version="1.0", path=""), ctx)
    report_id = payload.report_id or job.report_id
    if not report_id:
        raise AppError(
            code="workflow_queue_projection_report_missing",
            message="Analytics projection fan-out requires a stable report identifier",
            retryable=False,
        )
    projected = analytics_store_service.read_cross_report_projected_data(
        CrossReportProjectedDataReadRequest(
            schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
            db_path=app.reports_db,
            content_classes=["claim", "finding", "quote", "metric"],
            minimum_projection_status="projected",
        ),
        ctx,
    )
    source = next(
        (
            candidate
            for candidate in projected.source_candidates
            if candidate.report_id == report_id
        ),
        None,
    )
    if source is None:
        raise AppError(
            code="workflow_queue_projection_source_missing",
            message="Analytics projection did not retain a projected source candidate",
            retryable=True,
            context={"report_id": report_id},
        )
    root_workflow_id = job.root_workflow_id or job.job_id
    correlation_id = job.correlation_id or root_workflow_id
    downstream: list[WorkflowJobSubmission] = [
        WorkflowJobSubmission(
            schema_version="1.0",
            queue_name="claim_embedding",
            job_type="claim_embedding.v1",
            payload=ClaimEmbeddingPayload(
                model_version="text-embedding-3-small",
                input_reference=f"analytics:report:{report_id}",
                input_content_hash=source.content_hash,
                processing_version=payload.processing_version,
            ),
            idempotency_key=_digest("claim-embedding", report_id, source.content_hash),
            deduplication_scope="report-projected-claims",
            root_workflow_id=root_workflow_id,
            parent_job_id=job.job_id,
            trigger_event_id=job.trigger_event_id or job.job_id,
            correlation_id=correlation_id,
            entity_type="report",
            entity_id=report_id,
            publisher_id=source.publisher_id,
            report_id=report_id,
            budget_profile="embedding",
        )
    ]
    topic = str(payload.attributes.get("topic", "")).strip()
    if not topic and source.category_labels:
        topic = source.category_labels[0]
    if topic:
        downstream.extend(
            [
                WorkflowJobSubmission(
                    schema_version="1.0",
                    queue_name="signal_candidate",
                    job_type="signal_candidate.v1",
                    payload=SignalCandidatePayload(
                        report_id=report_id,
                        projection_reference=f"analytics:report:{report_id}",
                        signal_selection_policy_version=payload.processing_version
                        or "signal-selection.v1",
                        input_reference=f"analytics:report:{report_id}",
                        input_content_hash=source.content_hash,
                        processing_version=payload.processing_version,
                        attributes={"topic": topic},
                    ),
                    idempotency_key=_digest(
                        "signal-candidate", report_id, source.content_hash, topic
                    ),
                    deduplication_scope="projected-report-signal-candidates",
                    root_workflow_id=root_workflow_id,
                    parent_job_id=job.job_id,
                    trigger_event_id=job.trigger_event_id or job.job_id,
                    correlation_id=correlation_id,
                    entity_type="report",
                    entity_id=report_id,
                    publisher_id=source.publisher_id,
                    report_id=report_id,
                    budget_profile="signal_candidate",
                ),
                WorkflowJobSubmission(
                    schema_version="1.0",
                    queue_name="briefing_opportunity",
                    job_type="briefing_opportunity.v1",
                    payload=BriefingOpportunityPayload(
                        report_id=report_id,
                        projection_event_id=job.job_id,
                        topic=topic,
                        geography=str(payload.attributes.get("geography", "")),
                        rolling_window=str(
                            payload.attributes.get("rolling_window", "current")
                        ),
                        source_hashes=[source.content_hash],
                        briefing_policy_version=payload.processing_version
                        or "briefing-opportunity.v1",
                        input_reference=f"analytics:report:{report_id}",
                        input_content_hash=source.content_hash,
                        processing_version=payload.processing_version,
                        attributes={"publisher_ids": [source.publisher_id]},
                    ),
                    idempotency_key=_digest(
                        "briefing-opportunity", topic, source.content_hash
                    ),
                    deduplication_scope="projected-report-briefing-opportunity",
                    root_workflow_id=root_workflow_id,
                    parent_job_id=job.job_id,
                    trigger_event_id=job.trigger_event_id or job.job_id,
                    correlation_id=correlation_id,
                    entity_type="report",
                    entity_id=report_id,
                    publisher_id=source.publisher_id,
                    report_id=report_id,
                    budget_profile="briefing_opportunity",
                ),
            ]
        )
    return replace(
        stage_result,
        downstream=downstream,
        result=replace(
            stage_result.result,
            summary={
                **stage_result.result.summary,
                "fanout_count": len(downstream),
                "source_content_hash": source.content_hash,
                "topic": topic,
            },
        ),
    )
