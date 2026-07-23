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
from src.orchestrators.admission_preflight_orchestrator import (
    AdmissionPreflightRequest,
    admission_configuration_hash,
    admission_policy_hash,
    persist_admission_funnel,
    pipeline_preflight_decision_hash,
    run_admission_preflight,
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
from src.orchestrators.pipeline_preflight_orchestrator import (
    preflight_report_pipeline,
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

from .shared import (
    WorkflowQueueHandler,
    WorkflowQueueHandlerResult,
    _requested_budget_override,
)


def _stage_child_submission(
    *,
    job: WorkflowJob,
    payload: QueuePayload,
    next_queue: str,
    next_payload: QueuePayload,
) -> WorkflowJobSubmission:
    """Create the one deterministic report-stage handoff for a checkpoint."""
    source_hash = payload.input_content_hash or getattr(
        payload, "source_content_hash", ""
    )
    report_id = getattr(payload, "report_id", "") or job.report_id
    return WorkflowJobSubmission(
        schema_version="1.0",
        queue_name=next_queue,
        job_type=f"{next_queue}.v1",
        payload=next_payload,
        idempotency_key=f"{report_id}:{next_queue}:{source_hash}:{payload.processing_version}",
        deduplication_scope=f"report-stage:{next_queue}",
        root_workflow_id=job.root_workflow_id or job.job_id,
        parent_job_id=job.job_id,
        trigger_event_id=job.trigger_event_id or job.job_id,
        correlation_id=job.correlation_id or job.root_workflow_id or job.job_id,
        entity_type="report",
        entity_id=report_id,
        publisher_id=job.publisher_id,
        source_identity_id=job.source_identity_id,
        report_id=report_id,
        budget_profile="report_ingest",
    )


def _report_stage_handler(
    *,
    resume_from_stage: str,
    stop_after_stage: str | None = None,
    projection_only: bool = False,
    next_queue: str = "",
) -> WorkflowQueueHandler:
    """Adapt one retained report checkpoint to the established pipeline.

    The queue payload contains the immutable source reference only.  The report
    pipeline remains the owner of checkpoint, lineage, provider, retry and
    domain-generation decisions.
    """

    def handler(
        job: WorkflowJob, payload: QueuePayload, ctx: RunContext
    ) -> WorkflowQueueHandlerResult:
        artifact_reference = str(
            getattr(payload, "source_artifact_reference", "") or payload.input_reference
        ).strip()
        source_hash = str(
            getattr(payload, "source_content_hash", "") or payload.input_content_hash
        ).strip()
        report_id = str(getattr(payload, "report_id", "") or job.report_id).strip()
        if not artifact_reference or not source_hash or not report_id:
            raise AppError(
                code="workflow_queue_report_stage_input_incomplete",
                message="Report stage requires a report id and immutable source artifact hash",
                retryable=False,
                context={"job_id": job.job_id, "queue_name": job.queue_name},
            )
        config_path = str(payload.attributes.get("config_path", "")).strip()
        app_settings = load_settings(
            ConfigLoadRequest(schema_version="1.0", path=config_path), ctx
        )
        settings = build_ingest_settings(
            IngestSettingsBuildRequest(schema_version="1.0", app_settings=app_settings),
            ctx,
        )
        admission_ctx = replace(
            ctx,
            workflow="report_generation",
            stage="admission_preflight",
            artifact_family="report",
            configuration_hash=admission_configuration_hash(settings),
            policy_hash=admission_policy_hash(settings),
        )
        source_file = DriveFile(
            schema_version="1.0",
            file_id=report_id,
            name=artifact_reference.replace("\\", "/").rsplit("/", 1)[-1],
            modified_time=None,
            md5_checksum=source_hash,
            mime_type="application/pdf",
        )
        carried_admission_hash = str(
            payload.attributes.get("admission_decision_hash", "")
        ).strip()
        runtime_preflight = (
            None
            if carried_admission_hash
            else preflight_report_pipeline(settings, admission_ctx)
        )
        downstream_attributes = dict(payload.attributes)
        if carried_admission_hash:
            report_ctx = replace(
                admission_ctx,
                source_identity_id=str(
                    payload.attributes.get("admission_source_identity_id", "")
                    or source_hash
                ),
                publisher_id=str(
                    payload.attributes.get("admission_publisher_id", "")
                    or "drive_unattributed"
                ),
                admission_decision_hash=carried_admission_hash,
            )
            preflight_fn = None
        else:
            assert runtime_preflight is not None
            admission = run_admission_preflight(
                AdmissionPreflightRequest(
                    file=source_file,
                    source_artifact_path=artifact_reference,
                    settings=settings,
                    runtime_preflight_passed=runtime_preflight.passed,
                    runtime_preflight_hash=pipeline_preflight_decision_hash(
                        runtime_preflight
                    ),
                    configuration_hash=admission_ctx.configuration_hash,
                    policy_hash=admission_ctx.policy_hash,
                    known_source_identities={},
                    known_title_keys={},
                ),
                admission_ctx,
            )
            persist_admission_funnel(
                [admission.decision],
                settings=settings,
                ctx=admission_ctx,
                configuration_hash=admission_ctx.configuration_hash,
                policy_hash=admission_ctx.policy_hash,
            )
            if not admission.admitted:
                raise AppError(
                    code=f"source_admission_{admission.decision.outcome}",
                    message="Report source did not pass deterministic admission preflight",
                    retryable=False,
                    context={
                        "report_id": report_id,
                        "outcome": admission.decision.outcome,
                        "admission_decision_hash": admission.decision.decision_hash,
                    },
                )
            report_ctx = replace(
                admission_ctx,
                source_identity_id=admission.decision.source_identity_id,
                publisher_id=admission.decision.publisher_id,
                admission_decision_hash=admission.decision.decision_hash,
            )
            downstream_attributes.update(
                {
                    "admission_decision_hash": admission.decision.decision_hash,
                    "admission_source_identity_id": admission.decision.source_identity_id,
                    "admission_publisher_id": admission.decision.publisher_id,
                }
            )

            def _admission_runtime_preflight(_settings, _ctx):
                return runtime_preflight

            preflight_fn = _admission_runtime_preflight
        outcome = run_report_pipeline(
            source_file,
            artifact_reference,
            settings,
            source_hash,
            report_ctx,
            resume_from_stage=resume_from_stage,
            stop_after_stage=stop_after_stage,
            projection_only=projection_only,
            budget_override=_requested_budget_override(payload),
            preflight_fn=preflight_fn,
        )
        if outcome.status == "error":
            raise AppError(
                code="workflow_queue_report_stage_failed",
                message="The retained report pipeline returned an error outcome",
                retryable=True,
                context={"job_id": job.job_id, "report_id": report_id},
            )
        downstream: list[WorkflowJobSubmission] = []
        if next_queue:
            if next_queue == "report_selection":
                next_payload: QueuePayload = ReportSelectionPayload(
                    input_reference=artifact_reference,
                    input_content_hash=source_hash,
                    processing_version=payload.processing_version,
                    attributes=downstream_attributes,
                    report_id=report_id,
                    source_prepared_checkpoint="source_prepared",
                )
            elif next_queue == "report_analysis":
                next_payload = ReportAnalysisPayload(
                    input_reference=artifact_reference,
                    input_content_hash=source_hash,
                    processing_version=payload.processing_version,
                    attributes=downstream_attributes,
                    report_id=report_id,
                    selection_checkpoint="selection_complete",
                )
            elif next_queue == "report_render":
                next_payload = ReportRenderPayload(
                    input_reference=artifact_reference,
                    input_content_hash=source_hash,
                    processing_version=payload.processing_version,
                    attributes=downstream_attributes,
                    report_id=report_id,
                    analysis_checkpoint="analysis_complete",
                )
            elif next_queue == "analytics_projection":
                next_payload = AnalyticsProjectionPayload(
                    input_reference=artifact_reference,
                    input_content_hash=source_hash,
                    processing_version=payload.processing_version,
                    attributes=downstream_attributes,
                    report_id=report_id,
                    validated_artifact_reference="analysis_complete",
                )
            else:
                raise AppError(
                    code="workflow_queue_report_stage_unknown_downstream",
                    message="Report stage requested an unknown downstream queue",
                    retryable=False,
                    context={"next_queue": next_queue},
                )
            downstream.append(
                _stage_child_submission(
                    job=job,
                    payload=payload,
                    next_queue=next_queue,
                    next_payload=next_payload,
                )
            )
        return WorkflowQueueHandlerResult(
            result=WorkflowStageResult(
                output_reference=str(outcome.html_path or artifact_reference),
                output_content_hash=source_hash,
                execution_plan_hash=job.execution_plan_hash,
                output_verified=outcome.status
                in {"processed", "skipped", "checkpointed"},
                summary={
                    "pipeline_status": outcome.status,
                    "checkpoint": stop_after_stage or "analytics_projected",
                },
            ),
            downstream=downstream,
        )

    return handler
