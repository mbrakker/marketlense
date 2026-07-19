"""Code-reviewed typed handler registry for the durable workflow queue.

The registry is deliberately not a DAG authoring system.  It defines the fixed
MarketLense graph, payload/result contracts, and the only downstream queue types
that a handler may request.  Domain adapters can be replaced incrementally while
the queue lifecycle remains unchanged.
"""

# ruff: noqa: E501

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Callable

from src.contracts.analytics_projection import (
    PROJECTION_SCHEMA_VERSION,
    ClaimEmbeddingWorkflowRequest,
)
from src.contracts.browser_download import ReportDownloadOrchestratorRequest
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
from src.contracts.files import FileStatRequest, ReadBytesRequest, WriteBytesRequest
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
from src.services.file_service import file_stat, read_bytes, write_bytes
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


def _source_ingest_submission(
    *,
    job: WorkflowJob,
    artifact_reference: str,
    source_hash: str,
    source_identity_id: str,
    report_id: str,
    processing_version: str,
) -> WorkflowJobSubmission:
    return WorkflowJobSubmission(
        schema_version="1.0",
        queue_name="source_ingest",
        job_type="source_ingest.v1",
        payload=SourceIngestPayload(
            source_identity_id=source_identity_id,
            source_artifact_reference=artifact_reference,
            source_content_hash=source_hash,
            report_id=report_id,
            parser_ocr_compatibility_version=processing_version,
            input_reference=artifact_reference,
            input_content_hash=source_hash,
            processing_version=processing_version,
        ),
        idempotency_key=f"{source_hash}:source_ingest:{processing_version}",
        deduplication_scope="source-ingest-content",
        root_workflow_id=job.root_workflow_id or job.job_id,
        parent_job_id=job.job_id,
        trigger_event_id=job.trigger_event_id or job.job_id,
        correlation_id=job.correlation_id or job.root_workflow_id or job.job_id,
        entity_type="report",
        entity_id=report_id,
        publisher_id=job.publisher_id,
        source_identity_id=source_identity_id,
        report_id=report_id,
        budget_profile="report_ingest",
    )


def _verified_file_hash(path: str, ctx: RunContext) -> str:
    stat = file_stat(
        FileStatRequest(schema_version="1.0", path=path, compute_md5=True), ctx
    )
    if not stat.exists or not stat.is_file or not stat.md5:
        raise AppError(
            code="workflow_queue_acquired_artifact_unverified",
            message="A downstream ingest job requires a retained verified file",
            retryable=False,
            context={"artifact_reference": path},
        )
    return stat.md5


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
    if artifact:
        source_hash = _verified_file_hash(artifact, ctx)
        child = _source_ingest_submission(
            job=job,
            artifact_reference=artifact,
            source_hash=source_hash,
            source_identity_id=payload.source_identity_id
            or _digest(payload.source_url),
            report_id=payload.source_identity_id or _digest(payload.source_url),
            processing_version=payload.processing_version or "acquisition-v1",
        )
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
            output_content_hash=_digest(artifact or payload.source_url),
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
    source_hash = _verified_file_hash(artifact, ctx)
    source_identity_id = _digest(payload.source_url)
    return WorkflowQueueHandlerResult(
        result=WorkflowStageResult(
            output_reference=artifact,
            output_content_hash=source_hash,
            execution_plan_hash=job.execution_plan_hash,
            output_verified=True,
            summary={"mailbox_polls": result.mailbox_poll_count},
        ),
        downstream=[
            _source_ingest_submission(
                job=job,
                artifact_reference=artifact,
                source_hash=source_hash,
                source_identity_id=source_identity_id,
                report_id=source_identity_id,
                processing_version=payload.processing_version or "mailbox-v1",
            )
        ],
    )


def _publication_readiness_handler(
    job: WorkflowJob, payload: QueuePayload, ctx: RunContext
) -> WorkflowQueueHandlerResult:
    assert isinstance(payload, PublicationReadinessPayload)
    if (
        not payload.entity_type
        or not payload.entity_package_reference
        or not payload.package_checksum
        or not payload.validation_reference
        or not payload.lineage_reference
    ):
        raise AppError(
            code="workflow_queue_publication_readiness_incomplete",
            message="Publication readiness requires an immutable package, validation, and lineage",
            retryable=False,
        )
    required_assets = str(payload.required_asset_status or "optional").strip().lower()
    status = (
        "awaiting_review"
        if required_assets in {"ready", "optional"}
        else "not_publishable"
    )
    config_path = str(payload.attributes.get("config_path", ""))
    app = load_settings(ConfigLoadRequest(schema_version="1.0", path=config_path), ctx)
    readiness = record_publication_readiness(
        app.state_db,
        package_checksum=payload.package_checksum,
        entity_type=payload.entity_type,
        package_reference=payload.entity_package_reference,
        validation_reference=payload.validation_reference,
        lineage_reference=payload.lineage_reference,
        required_asset_status=required_assets,
        readiness_status=status,
        reason="queue_readiness_deterministic_check",
        ctx=ctx,
    )
    return WorkflowQueueHandlerResult(
        result=WorkflowStageResult(
            output_reference=readiness.package_reference,
            output_content_hash=readiness.package_checksum,
            execution_plan_hash=job.execution_plan_hash,
            output_verified=readiness.readiness_status == "awaiting_review",
            summary={"readiness_status": readiness.readiness_status},
        )
    )


def _cross_report_package_from_artifact(
    package_reference: str, ctx: RunContext
) -> CrossReportPublishPackage:
    """Load a retained Briefing or Signal package without queueing its HTML."""

    response = read_bytes(
        ReadBytesRequest(schema_version="1.0", path=package_reference), ctx
    )
    try:
        artifact = json.loads(response.content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError) as exc:
        raise AppError(
            code="workflow_queue_publish_package_invalid",
            message="Publication queue package is not valid JSON",
            cause=exc,
            retryable=False,
        ) from exc
    package = (
        artifact.get("publish_package", artifact)
        if isinstance(artifact, dict)
        else None
    )
    if not isinstance(package, dict):
        raise AppError(
            code="workflow_queue_publish_package_invalid",
            message="Publication queue package is not a valid retained entity artifact",
            retryable=False,
        )
    try:
        return CrossReportPublishPackage(**package)
    except TypeError as exc:
        raise AppError(
            code="workflow_queue_publish_package_invalid",
            message="Publication queue package is incompatible with the current contract",
            cause=exc,
            retryable=False,
        ) from exc


def _package_checksum(package: CrossReportPublishPackage) -> str:
    """Hash the complete approval package while avoiding a self-referential field."""

    return _digest(
        json.dumps(
            asdict(replace(package, artifact_sha256="")),
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
    )


def _with_package_checksum(
    package: CrossReportPublishPackage,
) -> CrossReportPublishPackage:
    return replace(package, artifact_sha256=_package_checksum(package))


def _persist_queue_publish_package(
    package: CrossReportPublishPackage,
    path: str,
    ctx: RunContext,
) -> CrossReportPublishPackage:
    """Persist and read back one deterministic publish package before handoff."""

    checked = _with_package_checksum(replace(package, canonical_artifact_path=path))
    content = (
        json.dumps(
            asdict(checked),
            ensure_ascii=True,
            sort_keys=True,
            indent=2,
            default=str,
        )
        + "\n"
    ).encode("utf-8")
    write_bytes(
        WriteBytesRequest(
            schema_version="1.0", path=path, content=content, make_parents=True
        ),
        ctx,
    )
    readback = read_bytes(ReadBytesRequest(schema_version="1.0", path=path), ctx)
    if readback.content != content:
        raise AppError(
            code="workflow_queue_publish_package_readback_failed",
            message="Retained publish package did not match its verified write",
            retryable=True,
            context={"path": path},
        )
    return checked


def _wordpress_publish_handler(
    job: WorkflowJob, payload: QueuePayload, ctx: RunContext
) -> WorkflowQueueHandlerResult:
    """Perform an approval-gated, idempotent WordPress entity publication."""

    assert isinstance(payload, WordPressPublishPayload)
    if payload.entity_type not in {"briefing", "signal"}:
        raise AppError(
            code="workflow_queue_publish_entity_unsupported",
            message="WordPress queue supports retained Briefing and Signal packages only",
            retryable=False,
            context={"entity_type": payload.entity_type},
        )
    try:
        uuid.UUID(payload.approval_id)
    except (AttributeError, TypeError, ValueError) as exc:
        raise AppError(
            code="stale_approval",
            message="WordPress publication requires a current approval for this package",
            cause=exc,
            retryable=False,
        ) from exc
    config_path = str(payload.attributes.get("config_path", ""))
    app = load_settings(ConfigLoadRequest(schema_version="1.0", path=config_path), ctx)
    if not payload.approval_id or not publication_approval_is_valid(
        app.state_db,
        package_checksum=payload.package_checksum,
        approval_id=payload.approval_id,
        ctx=ctx,
    ):
        raise AppError(
            code="stale_approval",
            message="WordPress publication requires a current approval for this package",
            retryable=False,
        )
    package = _cross_report_package_from_artifact(payload.entity_package_reference, ctx)
    expected_route = f"wordpress:ml_{payload.entity_type}"
    if package.target_route != expected_route:
        raise AppError(
            code="workflow_queue_publish_entity_mismatch",
            message="Approved queue entity type does not match its retained package route",
            retryable=False,
            context={
                "entity_type": payload.entity_type,
                "target_route": package.target_route,
            },
        )
    if package.artifact_sha256 != payload.package_checksum:
        raise AppError(
            code="workflow_queue_publish_package_checksum_mismatch",
            message="Approved package checksum does not match the retained entity package",
            retryable=False,
        )
    if not payload.dry_run and not bool(
        getattr(app, "cross_report_analysis_publish_enabled", False)
    ):
        raise AppError(
            code="cross_report_publish_live_disabled",
            message="Live Briefing publication remains disabled by configuration",
            retryable=False,
        )
    result = publish_cross_report_package(
        package,
        load_publish_settings(
            ConfigLoadRequest(schema_version="1.0", path=config_path), ctx
        ),
        ctx,
        dry_run=payload.dry_run,
    )
    if result.status == "error":
        raise AppError(
            code=result.error_code or "workflow_queue_wordpress_publish_failed",
            message=result.error_message or "WordPress publish returned an error",
            retryable=False,
        )
    downstream: list[WorkflowJobSubmission] = []
    if result.post_id is not None:
        downstream.append(
            WorkflowJobSubmission(
                schema_version="1.0",
                queue_name="wordpress_projection",
                job_type="wordpress_projection.v1",
                payload=WordPressProjectionPayload(
                    published_entity_reference=payload.entity_package_reference,
                    wordpress_id=str(result.post_id),
                    entity_type=payload.entity_type,
                    input_reference=payload.entity_package_reference,
                    input_content_hash=payload.package_checksum,
                    processing_version=payload.processing_version,
                ),
                idempotency_key=_digest(
                    "wordpress-projection",
                    payload.package_checksum,
                    str(result.post_id),
                ),
                deduplication_scope="wordpress-published-package",
                root_workflow_id=job.root_workflow_id or job.job_id,
                parent_job_id=job.job_id,
                trigger_event_id=job.trigger_event_id or job.job_id,
                correlation_id=job.correlation_id or job.root_workflow_id or job.job_id,
                entity_type=payload.entity_type,
                entity_id=str(result.post_id),
                budget_profile="wordpress_projection",
            )
        )
    return WorkflowQueueHandlerResult(
        result=WorkflowStageResult(
            output_reference=result.post_url or payload.entity_package_reference,
            output_content_hash=payload.package_checksum,
            execution_plan_hash=job.execution_plan_hash,
            output_verified=payload.dry_run or result.post_id is not None,
            summary={
                "publication_status": result.status,
                "wordpress_id": result.post_id or 0,
            },
        ),
        downstream=downstream,
        external_effects=[] if payload.dry_run else ["wordpress"],
    )


def _wordpress_projection_handler(
    job: WorkflowJob, payload: QueuePayload, ctx: RunContext
) -> WorkflowQueueHandlerResult:
    """Refresh retained WordPress intelligence after a verified publication.

    The projection service remains the sole WordPress read/write boundary.  This
    adapter only performs durable queue validation and constructs its typed
    request after live-publication policy has allowed the operation.
    """

    assert isinstance(payload, WordPressProjectionPayload)
    if (
        not payload.wordpress_id.strip()
        or not payload.published_entity_reference.strip()
        or not payload.input_content_hash.strip()
    ):
        raise AppError(
            code="workflow_queue_wordpress_projection_input_incomplete",
            message="WordPress projection requires a verified published entity and package checksum",
            retryable=False,
        )
    config_path = str(payload.attributes.get("config_path", ""))
    app = load_settings(ConfigLoadRequest(schema_version="1.0", path=config_path), ctx)
    if not bool(getattr(app, "cross_report_analysis_publish_enabled", False)):
        raise AppError(
            code="cross_report_publish_live_disabled",
            message="WordPress projection remains disabled while live publication is disabled",
            retryable=False,
        )
    settings = load_publish_settings(
        ConfigLoadRequest(schema_version="1.0", path=""), ctx
    )
    response = sync_wordpress_intelligence_projection(
        WordPressIntelligenceSyncRequest(
            schema_version=WORDPRESS_INTELLIGENCE_SCHEMA_VERSION,
            source_request=WordPressIntelligenceSourceReadRequest(
                schema_version=WORDPRESS_INTELLIGENCE_SCHEMA_VERSION,
                base_url=settings.wp.site_url,
                auth_header=build_auth_header(
                    username=settings.wp.username,
                    app_password=settings.wp.app_password,
                    bearer_token=settings.wp.bearer_token,
                ),
                ssl_verify=settings.wp.ssl_verify,
                ca_bundle_path=settings.wp.ca_bundle_path,
            ),
            generated_at_utc=utc_now_iso(),
            state_db=app.state_db,
        ),
        ctx,
    )
    return WorkflowQueueHandlerResult(
        result=WorkflowStageResult(
            output_reference=(
                f"wordpress-intelligence:{response.write_response.projection_version}:"
                f"{response.write_response.generated_at_utc}"
            ),
            output_content_hash=_digest(
                response.write_response.projection_version,
                response.write_response.generated_at_utc,
                payload.input_content_hash,
            ),
            execution_plan_hash=job.execution_plan_hash,
            output_verified=response.write_response.status == "stored",
            summary={
                "entity_count": response.entity_count,
                "projection_version": response.write_response.projection_version,
                "wordpress_id": payload.wordpress_id,
            },
        ),
        external_effects=["wordpress"],
    )


def _briefing_opportunity_handler(
    job: WorkflowJob, payload: QueuePayload, ctx: RunContext
) -> WorkflowQueueHandlerResult:
    assert isinstance(payload, BriefingOpportunityPayload)
    publisher_ids = payload.attributes.get("publisher_ids", [])
    if not isinstance(publisher_ids, list):
        raise AppError(
            code="workflow_queue_briefing_publishers_invalid",
            message="Briefing opportunity publisher IDs must be a bounded list",
            retryable=False,
        )
    config_path = str(payload.attributes.get("config_path", ""))
    app = load_settings(ConfigLoadRequest(schema_version="1.0", path=config_path), ctx)
    source_hashes = list(payload.source_hashes)
    if not source_hashes and _boolean_attribute(
        payload, "resolve_projected_sources", False
    ):
        projected = analytics_store_service.read_cross_report_projected_data(
            CrossReportProjectedDataReadRequest(
                schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
                db_path=app.reports_db,
                publisher_filters=_string_list_attribute(payload, "publisher_filters"),
                date_range_start=str(payload.attributes.get("date_range_start", ""))
                or None,
                date_range_end=str(payload.attributes.get("date_range_end", ""))
                or None,
                category_filters=_string_list_attribute(payload, "category_filters"),
                tag_filters=_string_list_attribute(payload, "tag_filters"),
                content_classes=["claim", "finding", "quote", "metric"],
                minimum_projection_status="projected",
            ),
            ctx,
        )
        candidates = sorted(
            projected.source_candidates,
            key=lambda candidate: (-candidate.total_score, candidate.report_id),
        )[: _positive_int_attribute(payload, "max_source_reports", 6)]
        source_hashes = [
            candidate.content_hash
            for candidate in candidates
            if candidate.content_hash.strip()
        ]
        publisher_ids = [
            candidate.publisher_id
            for candidate in candidates
            if candidate.publisher_id.strip()
        ]
    opportunity = upsert_briefing_opportunity(
        app.state_db,
        topic=payload.topic,
        geography=payload.geography,
        rolling_window=payload.rolling_window,
        briefing_policy_version=payload.briefing_policy_version,
        source_hashes=source_hashes,
        publisher_ids=[str(item) for item in publisher_ids],
        minimum_distinct_reports=_positive_int_attribute(
            payload, "minimum_distinct_reports", 2
        ),
        minimum_publisher_diversity=_positive_int_attribute(
            payload, "minimum_publisher_diversity", 2
        ),
        ctx=ctx,
    )

    if opportunity.status in {"eligible", "frozen"}:
        source_set_hash = _digest(*opportunity.source_hashes)
        generation_attributes: dict[str, str | int | bool | list[str]] = {
            "auto_theme": _boolean_attribute(payload, "auto_theme", False),
            "category_filters": _string_list_attribute(payload, "category_filters"),
            "date_range_end": str(payload.attributes.get("date_range_end", "")),
            "date_range_start": str(payload.attributes.get("date_range_start", "")),
            "diagnostic": _boolean_attribute(payload, "diagnostic", False),
            "max_evidence_items": _positive_int_attribute(
                payload, "max_evidence_items", 48
            ),
            "max_prompt_chars": _positive_int_attribute(
                payload, "max_prompt_chars", 60_000
            ),
            "max_signals": _positive_int_attribute(payload, "max_signals", 8),
            "override_publishability": _boolean_attribute(
                payload, "override_publishability", False
            ),
            "publisher_filters": _string_list_attribute(payload, "publisher_filters"),
            "tag_filters": _string_list_attribute(payload, "tag_filters"),
        }
        generation_configuration_hash = _digest(
            payload.processing_version,
            json.dumps(generation_attributes, sort_keys=True, separators=(",", ":")),
        )
        submission = WorkflowJobSubmission(
            schema_version="1.0",
            queue_name="briefing_generation",
            job_type="briefing_generation.v1",
            payload=BriefingGenerationPayload(
                opportunity_id=opportunity.opportunity_id,
                frozen_source_manifest=f"workflow-opportunity:{opportunity.opportunity_id}",
                selected_topic=opportunity.topic,
                sorted_source_hashes=opportunity.source_hashes,
                model_routing_policy_version=payload.prompt_policy_version,
                generation_configuration_hash=generation_configuration_hash,
                input_reference=f"workflow-opportunity:{opportunity.opportunity_id}",
                input_content_hash=source_set_hash,
                processing_version=payload.processing_version,
                prompt_policy_version=payload.prompt_policy_version,
                attributes=generation_attributes,
            ),
            idempotency_key=_digest(
                opportunity.topic,
                *opportunity.source_hashes,
                payload.prompt_policy_version,
                generation_configuration_hash,
            ),
            deduplication_scope="briefing-frozen-source-set",
            root_workflow_id=job.root_workflow_id or job.job_id,
            parent_job_id=job.job_id,
            trigger_event_id=job.trigger_event_id or job.job_id,
            correlation_id=job.correlation_id or job.root_workflow_id or job.job_id,
            entity_type="briefing",
            entity_id=opportunity.opportunity_id,
            budget_profile="cross_report_analysis",
        )
        opportunity = freeze_briefing_opportunity(
            app.state_db,
            opportunity_id=opportunity.opportunity_id,
            frozen_source_manifest=f"workflow-opportunity:{opportunity.opportunity_id}",
            generation_submission=submission,
            ctx=ctx,
        )
    return WorkflowQueueHandlerResult(
        result=WorkflowStageResult(
            output_reference=f"workflow-opportunity:{opportunity.opportunity_id}",
            output_content_hash=_digest(*opportunity.source_hashes),
            execution_plan_hash=job.execution_plan_hash,
            output_verified=opportunity.status in {"collecting", "frozen", "generated"},
            summary={
                "opportunity_status": opportunity.status,
                "source_count": len(opportunity.source_hashes),
            },
        )
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


def _signal_candidate_handler(
    job: WorkflowJob, payload: QueuePayload, ctx: RunContext
) -> WorkflowQueueHandlerResult:
    """Create canonical Signal candidates from existing projected evidence."""

    assert isinstance(payload, SignalCandidatePayload)
    topic = str(payload.attributes.get("topic", "")).strip()
    if not topic:
        raise AppError(
            code="workflow_queue_signal_topic_missing",
            message="Signal candidate extraction requires an explicit topic",
            retryable=False,
        )
    requested_publisher_filters = _string_list_attribute(
        payload, "publisher_filters"
    )
    publisher_filters = list(requested_publisher_filters)
    category_filters = _string_list_attribute(payload, "category_filters")
    tag_filters = _string_list_attribute(payload, "tag_filters")
    max_source_reports = _positive_int_attribute(payload, "max_source_reports", 6)
    max_evidence_items = _positive_int_attribute(payload, "max_evidence_items", 48)
    downstream_max_source_reports = _positive_int_attribute(
        payload, "max_source_reports", 3
    )
    downstream_max_evidence_items = _positive_int_attribute(
        payload, "max_evidence_items", 6
    )
    max_signals = _positive_int_attribute(payload, "max_signals", 8)
    minimum_evidence_items = _positive_int_attribute(
        payload, "minimum_evidence_items", 2
    )
    minimum_source_reports = _positive_int_attribute(
        payload, "minimum_source_reports", 2
    )
    generate_signals = _boolean_attribute(payload, "generate_signals", True)
    config_path = str(payload.attributes.get("config_path", ""))
    app = load_settings(ConfigLoadRequest(schema_version="1.0", path=config_path), ctx)
    request_id = _digest(
        "signal-candidate",
        payload.report_id or job.report_id,
        payload.projection_reference or payload.input_reference,
        payload.signal_selection_policy_version,
        topic,
    )
    if job.publisher_id and job.publisher_id not in publisher_filters:
        publisher_filters.append(job.publisher_id)
    analysis_request = CrossReportAnalysisRequest(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        request_id=request_id,
        topic=topic,
        auto_theme=False,
        category_filters=category_filters,
        tag_filters=tag_filters,
        publisher_filters=publisher_filters,
        date_range_start=str(payload.attributes.get("date_range_start", "")) or None,
        date_range_end=str(payload.attributes.get("date_range_end", "")) or None,
        max_source_reports=max_source_reports,
        diagnostic=False,
        override_publishability=True,
        publication_mode="generate_only",
    )
    outcome = run_signal_candidate_extraction(
        SignalCandidateExtractionRequest(
            schema_version=SIGNAL_CANDIDATE_SCHEMA_VERSION,
            extraction_request_id=request_id,
            analysis_request=analysis_request,
            projected_data_request=CrossReportProjectedDataReadRequest(
                schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
                db_path=app.reports_db,
                publisher_filters=publisher_filters,
                date_range_start=analysis_request.date_range_start,
                date_range_end=analysis_request.date_range_end,
                category_filters=analysis_request.category_filters,
                tag_filters=analysis_request.tag_filters,
                content_classes=["claim", "finding", "quote", "metric"],
                minimum_projection_status="projected",
            ),
            db_path=app.signal_store_db or app.reports_db,
            max_evidence_items=max_evidence_items,
            max_signals=max_signals,
            state_db=app.state_db,
        ),
        ctx,
    )
    downstream = [
        WorkflowJobSubmission(
            schema_version="1.0",
            queue_name="signal_generation",
            job_type="signal_generation.v1",
            payload=SignalGenerationPayload(
                candidate_group_id=group.group_id,
                frozen_evidence_manifest=f"signal-candidates:{outcome.extraction_request_id}:{group.group_id}",
                model_routing_policy_version=payload.signal_selection_policy_version,
                input_reference=app.signal_store_db or app.reports_db,
                input_content_hash=_digest(*group.evidence_ids),
                processing_version=payload.processing_version,
                attributes={
                    "category_filters": category_filters,
                    "date_range_end": str(payload.attributes.get("date_range_end", "")),
                    "date_range_start": str(
                        payload.attributes.get("date_range_start", "")
                    ),
                    "max_evidence_items": downstream_max_evidence_items,
                    "max_source_reports": downstream_max_source_reports,
                    "minimum_evidence_items": minimum_evidence_items,
                    "minimum_source_reports": minimum_source_reports,
                    "publisher_filters": requested_publisher_filters,
                    "topic": topic,
                    "source_report_ids": group.source_report_ids,
                    "tag_filters": tag_filters,
                },
            ),
            idempotency_key=_digest(
                "signal-generation", outcome.extraction_request_id, group.group_id
            ),
            deduplication_scope="signal-candidate-group",
            root_workflow_id=job.root_workflow_id or job.job_id,
            parent_job_id=job.job_id,
            trigger_event_id=job.trigger_event_id or job.job_id,
            correlation_id=job.correlation_id or job.root_workflow_id or job.job_id,
            entity_type="signal",
            entity_id=group.group_id,
            budget_profile="high_quality",
        )
        for group in outcome.batch.groups
        if generate_signals and group.validation_status == "approved"
    ]
    return WorkflowQueueHandlerResult(
        result=WorkflowStageResult(
            output_reference=f"signal-candidates:{outcome.extraction_request_id}",
            output_content_hash=_digest(
                outcome.extraction_request_id,
                *[group.group_id for group in outcome.batch.groups],
            ),
            execution_plan_hash=job.execution_plan_hash,
            output_verified=outcome.status == "stored",
            summary={
                "candidate_count": outcome.candidate_count,
                "group_count": outcome.group_count,
            },
        ),
        downstream=downstream,
    )


def _signal_publish_package(
    *,
    group_id: str,
    package_path: str,
    projection: SignalPublishProjection,
) -> CrossReportPublishPackage:
    """Adapt the established Signal projection to the shared publish package."""

    signal = projection
    card = signal.card_content
    signal_card = {
        "schema_version": card.schema_version,
        "summary": card.summary,
        "confidence": card.confidence,
        "source_count": card.source_count,
        "evidence_count": card.evidence_count,
        "uncertainty": card.uncertainty,
    }
    source_report_ids = list(signal.source_report_ids)
    publisher_labels = list(signal.publisher_labels)
    return CrossReportPublishPackage(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        package_id=signal.file_id,
        file_id=signal.file_id,
        target_route="wordpress:ml_signal",
        title=signal.title,
        slug=signal.slug,
        excerpt=str(card.summary),
        body_html=signal.body_html,
        html_text=signal.html_text,
        html_path=str(Path(package_path).with_name("publish.html")),
        canonical_artifact_path=package_path,
        artifact_sha256="",
        validation_sha256=_digest("signal-validation", signal.validation_status),
        selected_theme_id=group_id,
        selected_report_ids=source_report_ids,
        source_metadata=[
            {
                "report_id": report_id,
                "publisher": publisher_labels[index]
                if index < len(publisher_labels)
                else "",
            }
            for index, report_id in enumerate(source_report_ids)
        ],
        category_labels=list(signal.topic_labels),
        tag_labels=list(signal.tag_labels),
        evidence_reference_ids=list(signal.evidence_ids),
        raw_metric_ids=[],
        prompt_hashes={},
        machine_metadata={
            "schema_version": WORDPRESS_ENTITY_SCHEMA_VERSION,
            "signal_cover_fingerprint": asdict(card.fingerprint),
            "signal_validation_status": signal.validation_status,
        },
        signal_card=signal_card,
    )


def _signal_generation_handler(
    job: WorkflowJob, payload: QueuePayload, ctx: RunContext
) -> WorkflowQueueHandlerResult:
    """Build a retained deterministic Signal package, then queue card rendering."""

    assert isinstance(payload, SignalGenerationPayload)
    if not payload.candidate_group_id or not payload.frozen_evidence_manifest:
        raise AppError(
            code="workflow_queue_signal_generation_input_incomplete",
            message="Signal generation requires a candidate group and frozen evidence manifest",
            retryable=False,
        )
    topic = str(payload.attributes.get("topic", "")).strip()
    if not topic:
        raise AppError(
            code="workflow_queue_signal_topic_missing",
            message="Signal generation requires the candidate group's selected topic",
            retryable=False,
        )
    app = load_settings(ConfigLoadRequest(schema_version="1.0", path=""), ctx)
    projection_result = generate_signal_post_projection(
        SignalPostWorkflowRequest(
            schema_version=WORDPRESS_ENTITY_SCHEMA_VERSION,
            request_id=_digest(
                "signal-generation",
                payload.candidate_group_id,
                payload.input_content_hash,
                payload.processing_version,
            ),
            generation_request=SignalPostGenerationRequest(
                schema_version=WORDPRESS_ENTITY_SCHEMA_VERSION,
                request_id=_digest(
                    "signal-generation-request",
                    payload.candidate_group_id,
                    payload.input_content_hash,
                ),
                topic=topic,
                category_filters=_string_list_attribute(payload, "category_filters"),
                tag_filters=_string_list_attribute(payload, "tag_filters"),
                publisher_filters=_string_list_attribute(payload, "publisher_filters"),
                max_source_reports=_positive_int_attribute(
                    payload, "max_source_reports", 3
                ),
                max_evidence_items=_positive_int_attribute(
                    payload, "max_evidence_items", 6
                ),
                minimum_source_reports=_positive_int_attribute(
                    payload, "minimum_source_reports", 2
                ),
                minimum_evidence_items=_positive_int_attribute(
                    payload, "minimum_evidence_items", 2
                ),
            ),
            db_path=app.reports_db,
            signal_store_db=app.signal_store_db or app.reports_db,
            output_root=app.output_dir,
            cover_style_path=app.cover_style_path,
            publication_mode="generate_only",
            state_db=app.state_db,
        ),
        ctx,
    )
    package_path = str(
        Path(app.output_dir)
        / "workflow_queue"
        / "signals"
        / _digest(
            payload.candidate_group_id,
            payload.input_content_hash,
            payload.processing_version,
        )
        / "publish_package.json"
    )
    package = _persist_queue_publish_package(
        _signal_publish_package(
            group_id=payload.candidate_group_id,
            package_path=package_path,
            projection=projection_result.projection,
        ),
        package_path,
        ctx,
    )
    cover_submission = WorkflowJobSubmission(
        schema_version="1.0",
        queue_name="cover_generation",
        job_type="cover_generation.v1",
        payload=CoverGenerationPayload(
            entity_type="signal",
            entity_package_reference=package_path,
            visual_semantics="signal",
            template_version=payload.processing_version or "signal-card-v1",
            input_reference=package_path,
            input_content_hash=package.artifact_sha256,
            processing_version=payload.processing_version,
        ),
        idempotency_key=_digest("signal-cover", package.artifact_sha256),
        deduplication_scope="signal-package-cover",
        root_workflow_id=job.root_workflow_id or job.job_id,
        parent_job_id=job.job_id,
        trigger_event_id=job.trigger_event_id or job.job_id,
        correlation_id=job.correlation_id or job.root_workflow_id or job.job_id,
        entity_type="signal",
        entity_id=payload.candidate_group_id,
        budget_profile="cover_generation",
    )
    return WorkflowQueueHandlerResult(
        result=WorkflowStageResult(
            output_reference=package_path,
            output_content_hash=package.artifact_sha256,
            execution_plan_hash=job.execution_plan_hash,
            output_verified=True,
            summary={
                "candidate_group_id": payload.candidate_group_id,
                "source_report_count": len(package.selected_report_ids),
                "evidence_count": len(package.evidence_reference_ids),
            },
        ),
        downstream=[cover_submission],
    )


def _briefing_generation_handler(
    job: WorkflowJob, payload: QueuePayload, ctx: RunContext
) -> WorkflowQueueHandlerResult:
    """Generate a frozen-source Briefing without rendering covers or publishing."""

    assert isinstance(payload, BriefingGenerationPayload)
    if (
        not payload.opportunity_id
        or not payload.frozen_source_manifest
        or not payload.selected_topic
        or not payload.sorted_source_hashes
    ):
        raise AppError(
            code="workflow_queue_briefing_generation_input_incomplete",
            message="Briefing generation requires an eligible frozen source-set manifest",
            retryable=False,
        )
    app = load_settings(ConfigLoadRequest(schema_version="1.0", path=""), ctx)
    analysis_request = CrossReportAnalysisRequest(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        request_id=_digest(
            "briefing-generation",
            payload.opportunity_id,
            *payload.sorted_source_hashes,
            payload.prompt_policy_version,
            payload.generation_configuration_hash,
        ),
        topic=(
            ""
            if _boolean_attribute(payload, "auto_theme", False)
            else payload.selected_topic
        ),
        auto_theme=_boolean_attribute(payload, "auto_theme", False),
        category_filters=_string_list_attribute(payload, "category_filters"),
        tag_filters=_string_list_attribute(payload, "tag_filters"),
        publisher_filters=_string_list_attribute(payload, "publisher_filters"),
        date_range_start=str(payload.attributes.get("date_range_start", "")) or None,
        date_range_end=str(payload.attributes.get("date_range_end", "")) or None,
        max_source_reports=max(1, len(payload.sorted_source_hashes)),
        diagnostic=_boolean_attribute(payload, "diagnostic", False),
        override_publishability=_boolean_attribute(
            payload, "override_publishability", False
        ),
        publication_mode="generate_only",
    )
    outcome = run_cross_report_analysis(
        CrossReportAnalysisOrchestratorRequest(
            schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
            analysis_request=analysis_request,
            projected_data_request=CrossReportProjectedDataReadRequest(
                schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
                db_path=app.reports_db,
                publisher_filters=analysis_request.publisher_filters,
                date_range_start=analysis_request.date_range_start,
                date_range_end=analysis_request.date_range_end,
                category_filters=analysis_request.category_filters,
                tag_filters=analysis_request.tag_filters,
                content_classes=["claim", "finding", "quote", "metric"],
                minimum_projection_status="projected",
            ),
            idempotency_db_path=app.state_db,
            output_root=app.output_dir,
            max_evidence_items=_positive_int_attribute(
                payload, "max_evidence_items", 48
            ),
            max_signals=_positive_int_attribute(payload, "max_signals", 8),
            max_prompt_chars=_positive_int_attribute(
                payload, "max_prompt_chars", 60_000
            ),
            publish_target_route="wordpress:ml_briefing",
            state_db=app.state_db,
            frozen_source_hashes=list(payload.sorted_source_hashes),
            generate_cover_assets=False,
        ),
        app,
        ctx,
    )
    package = _cross_report_package_from_artifact(outcome.artifact_path, ctx)
    cover_submission = WorkflowJobSubmission(
        schema_version="1.0",
        queue_name="cover_generation",
        job_type="cover_generation.v1",
        payload=CoverGenerationPayload(
            entity_type="briefing",
            entity_package_reference=outcome.artifact_path,
            visual_semantics="briefing",
            template_version=payload.processing_version or "briefing-card-v1",
            input_reference=outcome.artifact_path,
            input_content_hash=package.artifact_sha256,
            processing_version=payload.processing_version,
            prompt_policy_version=payload.prompt_policy_version,
        ),
        idempotency_key=_digest("briefing-cover", package.artifact_sha256),
        deduplication_scope="briefing-package-cover",
        root_workflow_id=job.root_workflow_id or job.job_id,
        parent_job_id=job.job_id,
        trigger_event_id=job.trigger_event_id or job.job_id,
        correlation_id=job.correlation_id or job.root_workflow_id or job.job_id,
        entity_type="briefing",
        entity_id=payload.opportunity_id,
        budget_profile="cover_generation",
    )
    return WorkflowQueueHandlerResult(
        result=WorkflowStageResult(
            output_reference=outcome.artifact_path,
            output_content_hash=package.artifact_sha256,
            execution_plan_hash=job.execution_plan_hash,
            output_verified=outcome.validation_result.passed,
            summary={
                "selected_source_count": len(package.selected_report_ids),
                "validation_status": outcome.validation_result.status,
                "idempotency_reused": outcome.idempotency_reused,
            },
        ),
        downstream=[cover_submission],
        provider_usage={
            key: value
            for key, value in outcome.generated_result.cost_summary.items()
            if isinstance(value, (int, float, str))
        },
        external_effects=["model"],
    )


def _cover_generation_handler(
    job: WorkflowJob, payload: QueuePayload, ctx: RunContext
) -> WorkflowQueueHandlerResult:
    """Render one entity's card assets and freeze the approved publish package."""

    assert isinstance(payload, CoverGenerationPayload)
    if (
        payload.entity_type not in {"briefing", "signal"}
        or not payload.entity_package_reference
    ):
        raise AppError(
            code="workflow_queue_cover_generation_input_incomplete",
            message="Cover generation requires a retained Briefing or Signal package",
            retryable=False,
        )
    package = _cross_report_package_from_artifact(payload.entity_package_reference, ctx)
    expected_route = f"wordpress:ml_{payload.entity_type}"
    if package.target_route != expected_route:
        raise AppError(
            code="workflow_queue_cover_entity_mismatch",
            message="Cover queue entity type does not match the retained package route",
            retryable=False,
        )
    if (
        payload.input_content_hash
        and package.artifact_sha256 != payload.input_content_hash
    ):
        raise AppError(
            code="workflow_queue_cover_package_checksum_mismatch",
            message="Cover generation package no longer matches its queued checksum",
            retryable=False,
        )
    config_path = str(payload.attributes.get("config_path", ""))
    app = load_settings(ConfigLoadRequest(schema_version="1.0", path=config_path), ctx)
    if payload.entity_type == "signal":
        fingerprint_payload = package.machine_metadata.get("signal_cover_fingerprint")
        if not isinstance(fingerprint_payload, dict):
            raise AppError(
                code="workflow_queue_signal_cover_fingerprint_missing",
                message="Signal package does not retain its grounded cover fingerprint",
                retryable=False,
            )
        fingerprint = CoverFingerprint.from_dict(fingerprint_payload)
        card = dict(package.signal_card)
        publisher = "Market Lens Signal"
    else:
        fingerprint = CoverFingerprint(
            schema_version="1.0",
            geometry_family="system_matrix",
            evidence_shape="system",
            direction="neutral",
            geography_scope="unknown",
            evidence_density="balanced",
            domain_layer="forecast",
            seed=int(
                hashlib.sha256(package.package_id.encode("utf-8")).hexdigest()[:8], 16
            ),
            selection_reason="Cross-report briefing synthesizes multiple linked report systems.",
        )
        card = dict(package.briefing_card)
        card.setdefault("schema_version", "1.0")
        card.setdefault("summary_compact", package.excerpt)
        card.setdefault("summary_standard", package.excerpt)
        card.setdefault("decision_focus", package.title)
        card.setdefault("takeaways", [])
        card.setdefault("source_count", len(package.selected_report_ids))
        card.setdefault("evidence_count", len(package.evidence_reference_ids))
        publisher = "Market Lens Briefing"
    outcomes = generate_cover_images(
        CoverImageGenerationRequest(
            schema_version="2.0",
            output_dir=app.output_dir,
            style_config_path=app.cover_style_path,
            reports=[
                CoverImageReport(
                    schema_version="2.0",
                    file_id=package.file_id,
                    title=package.title,
                    publisher=publisher,
                    report_slug=package.slug,
                    categories=list(package.category_labels),
                    time_period=None,
                    region=None,
                    fingerprint=fingerprint,
                    cover_profile=payload.entity_type,
                )
            ],
        ),
        ctx,
    )
    outcome = outcomes[0] if outcomes else None
    if outcome is None or outcome.status != "generated" or outcome.assets is None:
        raise AppError(
            code="cover_asset_set_incomplete",
            message="Cover generation did not produce a complete card asset set",
            retryable=False,
        )
    card["covers"] = {
        size: getattr(outcome.assets, size).output_path
        for size in ("small", "medium", "large")
    }
    final_package = (
        replace(package, signal_card=card)
        if payload.entity_type == "signal"
        else replace(package, briefing_card=card)
    )
    final_path = str(
        Path(payload.entity_package_reference).with_name(
            "approved_publish_package.json"
        )
    )
    final_package = _persist_queue_publish_package(final_package, final_path, ctx)
    readiness_submission = WorkflowJobSubmission(
        schema_version="1.0",
        queue_name="publication_readiness",
        job_type="publication_readiness.v1",
        payload=PublicationReadinessPayload(
            entity_type=payload.entity_type,
            entity_package_reference=final_path,
            package_checksum=final_package.artifact_sha256,
            validation_reference=package.canonical_artifact_path,
            lineage_reference=payload.entity_package_reference,
            required_asset_status="ready",
            input_reference=final_path,
            input_content_hash=final_package.artifact_sha256,
            processing_version=payload.processing_version,
        ),
        idempotency_key=_digest(
            "publication-readiness", payload.entity_type, final_package.artifact_sha256
        ),
        deduplication_scope="validated-publication-package",
        root_workflow_id=job.root_workflow_id or job.job_id,
        parent_job_id=job.job_id,
        trigger_event_id=job.trigger_event_id or job.job_id,
        correlation_id=job.correlation_id or job.root_workflow_id or job.job_id,
        entity_type=payload.entity_type,
        entity_id=package.package_id,
        budget_profile="publishing",
    )
    return WorkflowQueueHandlerResult(
        result=WorkflowStageResult(
            output_reference=final_path,
            output_content_hash=final_package.artifact_sha256,
            execution_plan_hash=job.execution_plan_hash,
            output_verified=True,
            summary={"entity_type": payload.entity_type, "asset_count": 3},
        ),
        downstream=[readiness_submission],
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
        config_path = str(payload.attributes.get("config_path", "src/config/app.yaml"))
        app_settings = load_settings(
            ConfigLoadRequest(schema_version="1.0", path=config_path), ctx
        )
        settings = build_ingest_settings(
            IngestSettingsBuildRequest(schema_version="1.0", app_settings=app_settings),
            ctx,
        )
        outcome = run_report_pipeline(
            DriveFile(
                schema_version="1.0",
                file_id=report_id,
                name=artifact_reference.replace("\\", "/").rsplit("/", 1)[-1],
                modified_time=None,
                md5_checksum=source_hash,
                mime_type="application/pdf",
            ),
            artifact_reference,
            settings,
            source_hash,
            ctx,
            resume_from_stage=resume_from_stage,
            stop_after_stage=stop_after_stage,
            projection_only=projection_only,
            budget_override=_requested_budget_override(payload),
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
                    attributes=payload.attributes,
                    report_id=report_id,
                    source_prepared_checkpoint="source_prepared",
                )
            elif next_queue == "report_analysis":
                next_payload = ReportAnalysisPayload(
                    input_reference=artifact_reference,
                    input_content_hash=source_hash,
                    processing_version=payload.processing_version,
                    attributes=payload.attributes,
                    report_id=report_id,
                    selection_checkpoint="selection_complete",
                )
            elif next_queue == "report_render":
                next_payload = ReportRenderPayload(
                    input_reference=artifact_reference,
                    input_content_hash=source_hash,
                    processing_version=payload.processing_version,
                    attributes=payload.attributes,
                    report_id=report_id,
                    analysis_checkpoint="analysis_complete",
                )
            elif next_queue == "analytics_projection":
                next_payload = AnalyticsProjectionPayload(
                    input_reference=artifact_reference,
                    input_content_hash=source_hash,
                    processing_version=payload.processing_version,
                    attributes=payload.attributes,
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
