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
