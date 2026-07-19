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

from .shared import WorkflowQueueHandlerResult, _digest


def _publisher_discovery_handler(
    job: WorkflowJob, payload: QueuePayload, ctx: RunContext
) -> WorkflowQueueHandlerResult:
    assert isinstance(payload, PublisherDiscoveryPayload)
    if not payload.insights_url:
        raise AppError(
            code="workflow_queue_discovery_input_incomplete",
            message="Publisher discovery requires an insights URL",
            retryable=False,
        )
    app = load_settings(ConfigLoadRequest(schema_version="1.0", path=""), ctx)
    result = run_publisher_inventory_discovery(
        PublisherInventoryDiscoveryRequest(
            schema_version="1.0",
            insights_url=payload.insights_url,
            reports_db=app.reports_db,
            settings=load_publisher_inventory_settings(
                ConfigLoadRequest(schema_version="1.0", path=""), ctx
            ),
            state_db=app.state_db,
        ),
        ctx=ctx,
    )
    children = [
        WorkflowJobSubmission(
            schema_version="1.0",
            queue_name="report_acquisition",
            job_type="report_acquisition.v1",
            payload=ReportAcquisitionPayload(
                source_identity_id=_digest(item.canonical_url),
                source_url=item.canonical_url,
                publisher_id=payload.publisher_id,
                acquisition_policy_version="publisher-discovery-v1",
                report_title=item.title,
                publisher_name=result.publisher_name,
                input_reference=item.canonical_url,
                input_content_hash=_digest(item.canonical_url),
                processing_version=payload.processing_version,
            ),
            idempotency_key=f"{_digest(item.canonical_url)}:acquisition:publisher-discovery-v1",
            deduplication_scope="report-acquisition-source",
            root_workflow_id=job.root_workflow_id or job.job_id,
            parent_job_id=job.job_id,
            trigger_event_id=job.trigger_event_id or job.job_id,
            correlation_id=job.correlation_id or job.root_workflow_id or job.job_id,
            publisher_id=payload.publisher_id,
            source_identity_id=_digest(item.canonical_url),
            budget_profile="browser_acquisition",
        )
        for item in result.new_report_urls
    ]
    snapshot_hash = _digest(
        result.normalized_insights_url,
        *sorted(item.canonical_url for item in result.new_report_urls),
    )
    return WorkflowQueueHandlerResult(
        result=WorkflowStageResult(
            output_reference=result.normalized_insights_url,
            output_content_hash=snapshot_hash,
            execution_plan_hash=job.execution_plan_hash,
            output_verified=True,
            summary={
                "new_reports": len(children),
                "snapshot_changed": result.snapshot_changed,
            },
        ),
        downstream=children,
    )


def _report_acquisition_handler(
    job: WorkflowJob, payload: QueuePayload, ctx: RunContext
) -> WorkflowQueueHandlerResult:
    assert isinstance(payload, ReportAcquisitionPayload)
    if not payload.source_url:
        raise AppError(
            code="workflow_queue_acquisition_input_incomplete",
            message="Report acquisition requires a source URL",
            retryable=False,
        )
    app = load_settings(ConfigLoadRequest(schema_version="1.0", path=""), ctx)
    delivery_email = payload.delivery_email_reference or str(
        payload.attributes.get("delivery_email", "")
    )
    result = run_report_download(
        ReportDownloadOrchestratorRequest(
            schema_version="1.0",
            url=payload.source_url,
            settings=load_browser_download_settings(
                ConfigLoadRequest(schema_version="1.0", path=""), ctx
            ),
            state_db=app.state_db,
            reports_db=app.reports_db,
            delivery_email=delivery_email or None,
            publisher_insights_url=str(
                payload.attributes.get("publisher_insights_url", "")
            )
            or None,
            publisher_google_folder=str(
                payload.attributes.get("publisher_google_folder", "")
            )
            or None,
            report_title=payload.report_title,
            publisher_name=payload.publisher_name,
            mailbox_settings=load_mailbox_acquisition_settings(
                ConfigLoadRequest(schema_version="1.0", path=""), ctx
            ),
        ),
        ctx=ctx,
    )
    artifact = result.downloaded_file_path or result.onsite_capture_path or ""
    source_hash = _digest(artifact or payload.source_url)
    if artifact:
        child = build_source_ingest_submission_from_verified_acquisition(
            VerifiedAcquisitionIngestHandoffRequest(
                reports_db=app.reports_db,
                source_artifact_reference=artifact,
                source_url=payload.source_url,
                report_title=payload.report_title,
                publisher_name=payload.publisher_name,
                publisher_id=payload.publisher_id,
                acquisition_route=result.route_family or result.route_kind,
                processing_version=payload.processing_version or "acquisition-v1",
                report_id=_report_id_for_acquisition(result.drive_uploads, artifact),
            ),
            parent_job=job,
            ctx=ctx,
        )
        assert isinstance(child.payload, SourceIngestPayload)
        source_hash = child.payload.source_content_hash
        children = [child]
    elif result.outcome in {"email_requested", "email_required"}:
        children = [
            WorkflowJobSubmission(
                schema_version="1.0",
                queue_name="mailbox_delivery",
                job_type="mailbox_delivery.v1",
                payload=MailboxDeliveryPayload(
                    delivery_request_id=payload.source_identity_id
                    or _digest(payload.source_url),
                    source_url=payload.source_url,
                    publisher_id=payload.publisher_id,
                    report_title=payload.report_title,
                    request_watermark="",
                    retry_policy_version="mailbox-v1",
                    input_reference=payload.source_url,
                    input_content_hash=payload.input_content_hash
                    or _digest(payload.source_url),
                    processing_version=payload.processing_version,
                    attributes={
                        "publisher_name": payload.publisher_name,
                        "delivery_email": delivery_email,
                    },
                ),
                idempotency_key=f"{payload.source_identity_id or _digest(payload.source_url)}:mailbox:v1",
                deduplication_scope="mailbox-delivery-source",
                root_workflow_id=job.root_workflow_id or job.job_id,
                parent_job_id=job.job_id,
                trigger_event_id=job.trigger_event_id or job.job_id,
                correlation_id=job.correlation_id or job.root_workflow_id or job.job_id,
                publisher_id=payload.publisher_id,
                source_identity_id=payload.source_identity_id,
                budget_profile="mailbox_delivery",
            )
        ]
    else:
        raise AppError(
            code="workflow_queue_acquisition_no_verified_artifact",
            message="Acquisition completed without a verified source or mail delivery request",
            retryable=False,
        )
    return WorkflowQueueHandlerResult(
        result=WorkflowStageResult(
            output_reference=artifact or payload.source_url,
            output_content_hash=source_hash,
            execution_plan_hash=job.execution_plan_hash,
            output_verified=bool(artifact),
            summary={"outcome": result.outcome},
        ),
        downstream=children,
    )


def _mailbox_delivery_handler(
    job: WorkflowJob, payload: QueuePayload, ctx: RunContext
) -> WorkflowQueueHandlerResult:
    assert isinstance(payload, MailboxDeliveryPayload)
    publisher_name = str(payload.attributes.get("publisher_name", "")).strip()
    if not payload.source_url or not payload.report_title or not publisher_name:
        raise AppError(
            code="workflow_queue_mailbox_input_incomplete",
            message="Mailbox delivery requires source, title, and publisher context",
            retryable=False,
        )
    app = load_settings(ConfigLoadRequest(schema_version="1.0", path=""), ctx)
    result = run_mail_report_acquisition(
        MailReportAcquisitionRequest(
            schema_version="1.0",
            source_url=payload.source_url,
            report_title=payload.report_title,
            publisher_name=publisher_name,
            delivery_email=str(payload.attributes.get("delivery_email", "")) or None,
            reports_db=app.reports_db,
            mailbox_settings=load_mailbox_acquisition_settings(
                ConfigLoadRequest(schema_version="1.0", path=""), ctx
            ),
            browser_download_settings=load_browser_download_settings(
                ConfigLoadRequest(schema_version="1.0", path=""), ctx
            ),
            requested_after_utc=payload.request_watermark or None,
            workflow_request_id=int(payload.delivery_request_id or 0)
            if payload.delivery_request_id.isdigit()
            else 0,
        ),
        ctx=ctx,
    )
    artifact = result.downloaded_file_path or ""
    if not artifact:
        raise AppError(
            code="workflow_queue_mailbox_not_arrived",
            message="Mailbox delivery has not produced a verified source artifact yet",
            retryable=True,
        )
    download_result = result.report_download_result
    child = build_source_ingest_submission_from_verified_acquisition(
        VerifiedAcquisitionIngestHandoffRequest(
            reports_db=app.reports_db,
            source_artifact_reference=artifact,
            source_url=payload.source_url,
            report_title=payload.report_title,
            publisher_name=publisher_name,
            publisher_id=payload.publisher_id,
            acquisition_route=(
                result.acquisition_result_taxonomy or "mailbox_delivery"
            ),
            processing_version=payload.processing_version or "mailbox-v1",
            report_id=_report_id_for_acquisition(
                download_result.drive_uploads if download_result else [], artifact
            ),
        ),
        parent_job=job,
        ctx=ctx,
    )
    assert isinstance(child.payload, SourceIngestPayload)
    return WorkflowQueueHandlerResult(
        result=WorkflowStageResult(
            output_reference=artifact,
            output_content_hash=child.payload.source_content_hash,
            execution_plan_hash=job.execution_plan_hash,
            output_verified=True,
            summary={"mailbox_polls": result.mailbox_poll_count},
        ),
        downstream=[child],
    )


def _report_id_for_acquisition(
    drive_uploads: Sequence[ReportDownloadDriveUpload], artifact_reference: str
) -> str:
    """Prefer the retained Drive file ID; otherwise retain a hash-derived report ID."""
    normalized_artifact = str(Path(artifact_reference).resolve())
    for upload in drive_uploads:
        if str(Path(upload.local_path).resolve()) != normalized_artifact:
            continue
        drive_file_id = str(upload.drive_file.file_id or "").strip()
        if drive_file_id:
            return drive_file_id
    return ""
