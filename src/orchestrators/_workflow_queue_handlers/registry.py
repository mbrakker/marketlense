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

from .acquisition import (
    _mailbox_delivery_handler,
    _publisher_discovery_handler,
    _report_acquisition_handler,
)
from .analytics import _analytics_projection_handler, _claim_embedding_handler
from .briefings import _briefing_generation_handler, _briefing_opportunity_handler
from .publishing import (
    _cover_generation_handler,
    _publication_readiness_handler,
    _wordpress_projection_handler,
    _wordpress_publish_handler,
)
from .report_pipeline import _report_stage_handler
from .shared import (
    WorkflowQueueHandler,
    WorkflowQueueHandlerRegistration,
    WorkflowQueueHandlerResult,
    _verified_reference_handler,
)
from .signals import _signal_candidate_handler, _signal_generation_handler


def _registration(
    queue_name: str,
    payload_type: type,
    result_type: type,
    *,
    handler: WorkflowQueueHandler = _verified_reference_handler,
    downstream: tuple[str, ...] = (),
    effects: tuple[str, ...] = (),
    budget_profile: str = "default",
    retry_policy: str = "workflow_queue.default.v1",
    lease_seconds: int = 900,
) -> WorkflowQueueHandlerRegistration:
    return WorkflowQueueHandlerRegistration(
        queue_name=queue_name,
        job_type=f"{queue_name}.v1",
        payload_type=payload_type,
        result_type=result_type,
        handler=handler,
        default_retry_policy=retry_policy,
        default_lease_seconds=lease_seconds,
        budget_profile=budget_profile,
        expected_external_effects=effects,
        allowed_downstream_job_types=downstream,
    )


def default_workflow_queue_registry() -> dict[
    tuple[str, str], WorkflowQueueHandlerRegistration
]:
    """Return the fixed, typed MarketLense workflow graph."""
    registrations = (
        _registration(
            "publisher_discovery",
            PublisherDiscoveryPayload,
            PublisherDiscoveryResult,
            handler=_publisher_discovery_handler,
            downstream=("report_acquisition.v1",),
            effects=("browser", "drive"),
            budget_profile="publisher_inventory",
        ),
        _registration(
            "report_acquisition",
            ReportAcquisitionPayload,
            ReportAcquisitionResult,
            handler=_report_acquisition_handler,
            downstream=("mailbox_delivery.v1", "source_ingest.v1"),
            effects=("browser", "drive"),
            budget_profile="browser_acquisition",
            lease_seconds=1200,
        ),
        _registration(
            "mailbox_delivery",
            MailboxDeliveryPayload,
            MailboxDeliveryResult,
            handler=_mailbox_delivery_handler,
            downstream=("source_ingest.v1",),
            effects=("mailbox", "browser", "drive"),
            budget_profile="mailbox_delivery",
        ),
        _registration(
            "source_ingest",
            SourceIngestPayload,
            SourceIngestResult,
            handler=_report_stage_handler(
                resume_from_stage="",
                stop_after_stage="source_prepared",
                next_queue="report_selection",
            ),
            downstream=("report_selection.v1",),
            effects=("pdf", "ocr"),
            budget_profile="report_ingest",
            lease_seconds=1800,
        ),
        _registration(
            "report_selection",
            ReportSelectionPayload,
            ReportSelectionResult,
            handler=_report_stage_handler(
                resume_from_stage="source_prepared",
                stop_after_stage="selection_complete",
                next_queue="report_analysis",
            ),
            downstream=("report_analysis.v1",),
            effects=("pdf", "vision"),
            budget_profile="report_ingest",
            lease_seconds=1800,
        ),
        _registration(
            "report_analysis",
            ReportAnalysisPayload,
            ReportAnalysisResult,
            handler=_report_stage_handler(
                resume_from_stage="selection_complete",
                stop_after_stage="analysis_complete",
                next_queue="report_render",
            ),
            downstream=("artifact_repair.v1", "report_render.v1"),
            effects=("model", "vector"),
            budget_profile="high_quality",
            retry_policy="report_generation.report_pipeline.v1",
            lease_seconds=3600,
        ),
        _registration(
            "report_render",
            ReportRenderPayload,
            ReportRenderResult,
            handler=_report_stage_handler(
                resume_from_stage="analysis_complete",
                stop_after_stage="render_complete",
                next_queue="analytics_projection",
            ),
            downstream=(
                "analytics_projection.v1",
                "cover_generation.v1",
                "publication_readiness.v1",
            ),
            effects=("filesystem",),
            budget_profile="report_render",
        ),
        _registration(
            "analytics_projection",
            AnalyticsProjectionPayload,
            AnalyticsProjectionResult,
            handler=_analytics_projection_handler,
            downstream=(
                "claim_embedding.v1",
                "signal_candidate.v1",
                "briefing_opportunity.v1",
            ),
            budget_profile="analytics_projection",
        ),
        _registration(
            "claim_embedding",
            ClaimEmbeddingPayload,
            ClaimEmbeddingResult,
            handler=_claim_embedding_handler,
            effects=("embedding",),
            budget_profile="embedding",
        ),
        _registration(
            "signal_candidate",
            SignalCandidatePayload,
            SignalCandidateResult,
            handler=_signal_candidate_handler,
            downstream=("signal_generation.v1",),
            budget_profile="signal_candidate",
        ),
        _registration(
            "signal_generation",
            SignalGenerationPayload,
            SignalGenerationResult,
            handler=_signal_generation_handler,
            downstream=("cover_generation.v1",),
            budget_profile="high_quality",
            lease_seconds=3600,
        ),
        _registration(
            "briefing_opportunity",
            BriefingOpportunityPayload,
            BriefingOpportunityResult,
            handler=_briefing_opportunity_handler,
            downstream=("briefing_generation.v1",),
            budget_profile="briefing_opportunity",
        ),
        _registration(
            "briefing_generation",
            BriefingGenerationPayload,
            BriefingGenerationResult,
            handler=_briefing_generation_handler,
            downstream=("cover_generation.v1",),
            effects=("model",),
            budget_profile="cross_report_analysis",
            lease_seconds=3600,
        ),
        _registration(
            "cover_generation",
            CoverGenerationPayload,
            CoverGenerationResult,
            handler=_cover_generation_handler,
            downstream=("publication_readiness.v1",),
            budget_profile="cover_generation",
        ),
        _registration(
            "publication_readiness",
            PublicationReadinessPayload,
            PublicationReadinessResult,
            handler=_publication_readiness_handler,
            downstream=("wordpress_publish.v1",),
            budget_profile="publishing",
        ),
        _registration(
            "wordpress_publish",
            WordPressPublishPayload,
            WordPressPublishResult,
            handler=_wordpress_publish_handler,
            downstream=("wordpress_projection.v1",),
            effects=("wordpress",),
            budget_profile="publishing",
        ),
        _registration(
            "wordpress_projection",
            WordPressProjectionPayload,
            WordPressProjectionResult,
            handler=_wordpress_projection_handler,
            effects=("wordpress",),
            budget_profile="wordpress_projection",
        ),
        _registration(
            "artifact_repair",
            MaintenancePayload,
            WorkflowStageResult,
            downstream=("report_analysis.v1",),
            budget_profile="maintenance",
        ),
        _registration(
            "source_revalidation",
            MaintenancePayload,
            WorkflowStageResult,
            downstream=("report_acquisition.v1",),
            effects=("browser",),
            budget_profile="maintenance",
        ),
        _registration(
            "malformed_pdf_revalidation",
            MaintenancePayload,
            WorkflowStageResult,
            downstream=("source_ingest.v1",),
            effects=("pdf",),
            budget_profile="maintenance",
        ),
        _registration(
            "recategorization",
            MaintenancePayload,
            WorkflowStageResult,
            downstream=("analytics_projection.v1",),
            budget_profile="maintenance",
        ),
        _registration(
            "vector_retention",
            MaintenancePayload,
            WorkflowStageResult,
            budget_profile="maintenance",
        ),
        _registration(
            "wordpress_category_update",
            MaintenancePayload,
            WorkflowStageResult,
            effects=("wordpress",),
            budget_profile="maintenance",
        ),
        _registration(
            "public_render_repair",
            MaintenancePayload,
            WorkflowStageResult,
            downstream=("report_render.v1",),
            budget_profile="maintenance",
        ),
        _registration(
            "cost_reconciliation",
            MaintenancePayload,
            WorkflowStageResult,
            budget_profile="maintenance",
        ),
        _registration(
            "release_evidence_generation",
            MaintenancePayload,
            WorkflowStageResult,
            budget_profile="maintenance",
        ),
    )
    registry = {(item.queue_name, item.job_type): item for item in registrations}
    if len(registry) != len(registrations):
        raise RuntimeError(
            "Workflow queue registry contains duplicate queue/job registrations"
        )
    return registry


def resolve_workflow_queue_handler(
    queue_name: str,
    job_type: str,
    *,
    registry: dict[tuple[str, str], WorkflowQueueHandlerRegistration] | None = None,
) -> WorkflowQueueHandlerRegistration:
    item = (registry or default_workflow_queue_registry()).get((queue_name, job_type))
    if item is None:
        raise AppError(
            code="workflow_queue_handler_unregistered",
            message="Workflow queue and job type are not registered together",
            retryable=False,
            context={"queue_name": queue_name, "job_type": job_type},
        )
    return item


def execute_workflow_queue_handler(
    job: WorkflowJob,
    payload: QueuePayload,
    ctx: RunContext,
    *,
    registry: dict[tuple[str, str], WorkflowQueueHandlerRegistration] | None = None,
) -> WorkflowQueueHandlerResult:
    registration = resolve_workflow_queue_handler(
        job.queue_name, job.job_type, registry=registry
    )
    if not isinstance(payload, registration.payload_type):
        raise AppError(
            code="workflow_queue_handler_payload_invalid",
            message="Worker payload does not match the registered typed handler",
            retryable=False,
            context={"queue_name": job.queue_name, "job_type": job.job_type},
        )
    execution = registration.handler(job, payload, ctx)
    if not isinstance(execution.result, registration.result_type):
        execution = replace(
            execution,
            result=registration.result_type(**asdict(execution.result)),
        )
    disallowed = sorted(
        child.job_type
        for child in execution.downstream
        if child.job_type not in registration.allowed_downstream_job_types
    )
    if disallowed:
        raise AppError(
            code="workflow_queue_downstream_unregistered",
            message="Handler attempted an unapproved downstream queue transition",
            retryable=False,
            context={"job_id": job.job_id, "job_types": disallowed},
        )
    return execution
