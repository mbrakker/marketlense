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

WorkflowQueueHandler = Callable[
    [WorkflowJob, QueuePayload, RunContext], "WorkflowQueueHandlerResult"
]


@dataclass(frozen=True)
class WorkflowQueueHandlerResult:
    result: WorkflowStageResult
    downstream: list[WorkflowJobSubmission] = field(default_factory=list)
    provider_usage: dict[str, int | float | str] = field(default_factory=dict)
    external_effects: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class WorkflowQueueHandlerRegistration:
    queue_name: str
    job_type: str
    payload_type: type
    result_type: type
    handler: WorkflowQueueHandler
    default_retry_policy: str
    default_lease_seconds: int
    budget_profile: str
    expected_external_effects: tuple[str, ...]
    allowed_downstream_job_types: tuple[str, ...]


def _verified_reference_handler(
    job: WorkflowJob,
    payload: QueuePayload,
    ctx: RunContext,
) -> WorkflowQueueHandlerResult:
    """Compatibility bridge for a pre-verified canonical domain artifact.

    This is intentionally narrow: it accepts only a retained reference with a
    content hash.  It never manufactures an output or directly chains a later
    workflow.  Newly submitted operational work is routed through a stage
    adapter rather than this bridge.
    """
    del ctx
    if not payload.input_reference or not payload.input_content_hash:
        raise AppError(
            code="workflow_queue_reference_unverified",
            message="Queue compatibility execution requires a retained reference and content hash",
            retryable=False,
            context={"job_id": job.job_id, "queue_name": job.queue_name},
        )
    return WorkflowQueueHandlerResult(
        result=WorkflowStageResult(
            output_reference=payload.input_reference,
            output_content_hash=payload.input_content_hash,
            execution_plan_hash=job.execution_plan_hash,
            output_verified=True,
            summary={"mode": "verified_reference_compatibility"},
        )
    )


def _digest(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def _requested_budget_override(payload: QueuePayload) -> BudgetOverrideContext | None:
    actor = str(payload.attributes.get("budget_override_actor", "")).strip()
    reason = str(payload.attributes.get("budget_override_reason", "")).strip()
    expiry = str(payload.attributes.get("budget_override_expires_at_utc", "")).strip()
    if not any((actor, reason, expiry)):
        return None
    if not all((actor, reason, expiry)):
        raise AppError(
            code="workflow_queue_budget_override_incomplete",
            message="Queue budget override requires actor, reason, and expiry",
            retryable=False,
        )
    return BudgetOverrideContext(
        schema_version="1.0",
        actor=actor,
        reason=reason,
        scope=str(payload.attributes.get("budget_override_scope", "all")),
        expires_at_utc=expiry,
        policy_version=str(
            payload.attributes.get(
                "budget_override_policy_version", "budget-authority-v2"
            )
        ),
    )


def _string_list_attribute(payload: QueuePayload, name: str) -> list[str]:
    value = payload.attributes.get(name, [])
    if not isinstance(value, list):
        raise AppError(
            code="workflow_queue_attribute_invalid",
            message="Workflow queue list attributes must be lists of strings",
            retryable=False,
            context={"attribute": name},
        )
    return [str(item).strip() for item in value if str(item).strip()]


def _positive_int_attribute(payload: QueuePayload, name: str, default: int) -> int:
    raw = payload.attributes.get(name, default)
    if isinstance(raw, bool) or not isinstance(raw, (int, str)):
        raise AppError(
            code="workflow_queue_attribute_invalid",
            message="Workflow queue numeric attributes must be positive integers",
            retryable=False,
            context={"attribute": name},
        )
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise AppError(
            code="workflow_queue_attribute_invalid",
            message="Workflow queue numeric attributes must be positive integers",
            cause=exc,
            retryable=False,
            context={"attribute": name},
        ) from exc
    if value < 1:
        raise AppError(
            code="workflow_queue_attribute_invalid",
            message="Workflow queue numeric attributes must be positive integers",
            retryable=False,
            context={"attribute": name},
        )
    return value


def _positive_float_attribute(
    payload: QueuePayload, name: str, default: float
) -> float:
    raw = payload.attributes.get(name, default)
    if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
        raise AppError(
            code="workflow_queue_attribute_invalid",
            message="Workflow queue numeric attributes must be positive numbers",
            retryable=False,
            context={"attribute": name},
        )
    try:
        value = float(raw)
    except ValueError as exc:
        raise AppError(
            code="workflow_queue_attribute_invalid",
            message="Workflow queue numeric attributes must be positive numbers",
            cause=exc,
            retryable=False,
            context={"attribute": name},
        ) from exc
    if value <= 0:
        raise AppError(
            code="workflow_queue_attribute_invalid",
            message="Workflow queue numeric attributes must be positive numbers",
            retryable=False,
            context={"attribute": name},
        )
    return value


def _boolean_attribute(payload: QueuePayload, name: str, default: bool) -> bool:
    raw = payload.attributes.get(name, default)
    if not isinstance(raw, bool):
        raise AppError(
            code="workflow_queue_attribute_invalid",
            message="Workflow queue boolean attributes must be booleans",
            retryable=False,
            context={"attribute": name},
        )
    return raw
