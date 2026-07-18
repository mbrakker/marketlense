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
from dataclasses import asdict, dataclass, field, replace
from typing import Callable

from src.contracts.analytics_projection import (
    PROJECTION_SCHEMA_VERSION,
    ClaimEmbeddingWorkflowRequest,
)
from src.contracts.browser_download import ReportDownloadOrchestratorRequest
from src.contracts.config import ConfigLoadRequest, IngestSettingsBuildRequest
from src.contracts.cross_report_analysis import (
    CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
    CrossReportAnalysisRequest,
    CrossReportProjectedDataReadRequest,
    CrossReportPublishPackage,
)
from src.contracts.drive import DriveFile
from src.contracts.files import FileStatRequest, ReadBytesRequest
from src.contracts.mailbox_acquisition import MailReportAcquisitionRequest
from src.contracts.publisher_inventory import PublisherInventoryDiscoveryRequest
from src.contracts.run_budget import BudgetOverrideContext
from src.contracts.run_context import RunContext
from src.contracts.signal_candidates import (
    SIGNAL_CANDIDATE_SCHEMA_VERSION,
    SignalCandidateExtractionRequest,
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
from src.orchestrators.claim_embedding_orchestrator import (
    run_claim_embedding_workflow,
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
from src.services.config_service import (
    build_ingest_settings,
    load_browser_download_settings,
    load_mailbox_acquisition_settings,
    load_publish_settings,
    load_publisher_inventory_settings,
    load_settings,
)
from src.services.file_service import file_stat, read_bytes
from src.services.workflow_queue_service import (
    freeze_briefing_opportunity,
    publication_approval_is_valid,
    record_publication_readiness,
    upsert_briefing_opportunity,
)
from src.utils.errors import AppError

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
            payload.attributes.get("budget_override_policy_version", "budget-authority-v2")
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
            summary={"new_reports": len(children), "snapshot_changed": result.snapshot_changed},
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
            settings=load_browser_download_settings(ConfigLoadRequest(schema_version="1.0", path=""), ctx),
            state_db=app.state_db,
            reports_db=app.reports_db,
            delivery_email=delivery_email or None,
            publisher_insights_url=str(payload.attributes.get("publisher_insights_url", "")) or None,
            publisher_google_folder=str(payload.attributes.get("publisher_google_folder", "")) or None,
            report_title=payload.report_title,
            publisher_name=payload.publisher_name,
            mailbox_settings=load_mailbox_acquisition_settings(ConfigLoadRequest(schema_version="1.0", path=""), ctx),
        ),
        ctx=ctx,
    )
    artifact = result.downloaded_file_path or result.onsite_capture_path or ""
    if artifact:
        source_hash = _verified_file_hash(artifact, ctx)
        child = _source_ingest_submission(
            job=job, artifact_reference=artifact, source_hash=source_hash,
            source_identity_id=payload.source_identity_id or _digest(payload.source_url),
            report_id=payload.source_identity_id or _digest(payload.source_url),
            processing_version=payload.processing_version or "acquisition-v1",
        )
        children = [child]
    elif result.outcome in {"email_requested", "email_required"}:
        children = [WorkflowJobSubmission(
            schema_version="1.0", queue_name="mailbox_delivery", job_type="mailbox_delivery.v1",
            payload=MailboxDeliveryPayload(
                delivery_request_id=payload.source_identity_id or _digest(payload.source_url),
                source_url=payload.source_url, publisher_id=payload.publisher_id,
                report_title=payload.report_title, request_watermark="", retry_policy_version="mailbox-v1",
                input_reference=payload.source_url, input_content_hash=payload.input_content_hash or _digest(payload.source_url),
                processing_version=payload.processing_version,
                attributes={"publisher_name": payload.publisher_name, "delivery_email": delivery_email},
            ),
            idempotency_key=f"{payload.source_identity_id or _digest(payload.source_url)}:mailbox:v1",
            deduplication_scope="mailbox-delivery-source", root_workflow_id=job.root_workflow_id or job.job_id,
            parent_job_id=job.job_id, trigger_event_id=job.trigger_event_id or job.job_id,
            correlation_id=job.correlation_id or job.root_workflow_id or job.job_id,
            publisher_id=payload.publisher_id, source_identity_id=payload.source_identity_id,
            budget_profile="mailbox_delivery",
        )]
    else:
        raise AppError(code="workflow_queue_acquisition_no_verified_artifact", message="Acquisition completed without a verified source or mail delivery request", retryable=False)
    return WorkflowQueueHandlerResult(
        result=WorkflowStageResult(output_reference=artifact or payload.source_url, output_content_hash=_digest(artifact or payload.source_url), execution_plan_hash=job.execution_plan_hash, output_verified=bool(artifact), summary={"outcome": result.outcome}),
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
    status = "awaiting_review" if required_assets in {"ready", "optional"} else "not_publishable"
    app = load_settings(ConfigLoadRequest(schema_version="1.0", path=""), ctx)
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


def _briefing_package_from_artifact(
    package_reference: str, ctx: RunContext
) -> CrossReportPublishPackage:
    """Load the retained Briefing package without putting HTML in a queue row."""

    response = read_bytes(
        ReadBytesRequest(schema_version="1.0", path=package_reference), ctx
    )
    try:
        artifact = json.loads(response.content.decode("utf-8"))
        package = artifact["publish_package"]
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise AppError(
            code="workflow_queue_publish_package_invalid",
            message="Publication queue package is not a valid retained Briefing artifact",
            cause=exc,
            retryable=False,
        ) from exc
    if not isinstance(package, dict):
        raise AppError(
            code="workflow_queue_publish_package_invalid",
            message="Publication queue package is not a valid retained Briefing artifact",
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


def _wordpress_publish_handler(
    job: WorkflowJob, payload: QueuePayload, ctx: RunContext
) -> WorkflowQueueHandlerResult:
    """Perform an approval-gated, idempotent WordPress Briefing publication."""

    assert isinstance(payload, WordPressPublishPayload)
    if payload.entity_type != "briefing":
        raise AppError(
            code="workflow_queue_publish_entity_unsupported",
            message="WordPress queue currently supports retained Briefing packages only",
            retryable=False,
            context={"entity_type": payload.entity_type},
        )
    app = load_settings(ConfigLoadRequest(schema_version="1.0", path=""), ctx)
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
    package = _briefing_package_from_artifact(payload.entity_package_reference, ctx)
    if package.artifact_sha256 != payload.package_checksum:
        raise AppError(
            code="workflow_queue_publish_package_checksum_mismatch",
            message="Approved package checksum does not match the retained Briefing package",
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
        load_publish_settings(ConfigLoadRequest(schema_version="1.0", path=""), ctx),
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
                    "wordpress-projection", payload.package_checksum, str(result.post_id)
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
    opportunity = upsert_briefing_opportunity(
        load_settings(ConfigLoadRequest(schema_version="1.0", path=""), ctx).state_db,
        topic=payload.topic,
        geography=payload.geography,
        rolling_window=payload.rolling_window,
        briefing_policy_version=payload.briefing_policy_version,
        source_hashes=payload.source_hashes,
        publisher_ids=[str(item) for item in publisher_ids],
        minimum_distinct_reports=int(payload.attributes.get("minimum_distinct_reports", 2)),
        minimum_publisher_diversity=int(payload.attributes.get("minimum_publisher_diversity", 2)),
        ctx=ctx,
    )

    if opportunity.status == "eligible":
        source_set_hash = _digest(*opportunity.source_hashes)
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
                generation_configuration_hash=payload.processing_version,
                input_reference=f"workflow-opportunity:{opportunity.opportunity_id}",
                input_content_hash=source_set_hash,
                processing_version=payload.processing_version,
                prompt_policy_version=payload.prompt_policy_version,
            ),
            idempotency_key=_digest(
                opportunity.topic,
                *opportunity.source_hashes,
                payload.prompt_policy_version,
                payload.processing_version,
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
            load_settings(ConfigLoadRequest(schema_version="1.0", path=""), ctx).state_db,
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
            summary={"opportunity_status": opportunity.status, "source_count": len(opportunity.source_hashes)},
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


def _signal_candidate_handler(
    job: WorkflowJob, payload: QueuePayload, ctx: RunContext
) -> WorkflowQueueHandlerResult:
    """Create canonical Signal candidates from existing projected evidence."""

    assert isinstance(payload, SignalCandidatePayload)
    app = load_settings(ConfigLoadRequest(schema_version="1.0", path=""), ctx)
    topic = str(payload.attributes.get("topic", "")).strip()
    if not topic:
        raise AppError(
            code="workflow_queue_signal_topic_missing",
            message="Signal candidate extraction requires an explicit topic",
            retryable=False,
        )
    request_id = _digest(
        "signal-candidate",
        payload.report_id or job.report_id,
        payload.projection_reference or payload.input_reference,
        payload.signal_selection_policy_version,
        topic,
    )
    publisher_filters = _string_list_attribute(payload, "publisher_filters")
    if job.publisher_id and job.publisher_id not in publisher_filters:
        publisher_filters.append(job.publisher_id)
    analysis_request = CrossReportAnalysisRequest(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        request_id=request_id,
        topic=topic,
        auto_theme=False,
        category_filters=_string_list_attribute(payload, "category_filters"),
        tag_filters=_string_list_attribute(payload, "tag_filters"),
        publisher_filters=publisher_filters,
        date_range_start=str(payload.attributes.get("date_range_start", "")) or None,
        date_range_end=str(payload.attributes.get("date_range_end", "")) or None,
        max_source_reports=_positive_int_attribute(payload, "max_source_reports", 6),
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
            max_evidence_items=_positive_int_attribute(
                payload, "max_evidence_items", 48
            ),
            max_signals=_positive_int_attribute(payload, "max_signals", 8),
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
                attributes={"topic": topic, "source_report_ids": group.source_report_ids},
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
        if group.validation_status == "approved"
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


def _claim_embedding_handler(
    job: WorkflowJob, payload: QueuePayload, ctx: RunContext
) -> WorkflowQueueHandlerResult:
    """Run the existing bounded claim-embedding queue for canonical rows only."""

    assert isinstance(payload, ClaimEmbeddingPayload)
    app = load_settings(ConfigLoadRequest(schema_version="1.0", path=""), ctx)
    model = payload.model_version or str(
        payload.attributes.get("model", "text-embedding-3-small")
    )
    dry_run = bool(payload.attributes.get("dry_run", False))
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
            limit=_positive_int_attribute(payload, "limit", 1),
            timeout_seconds=None,
            ctx=ctx,
            cost_ledger_path=app.cost_ledger_path,
            cost_daily_path=app.cost_daily_path,
            model_pricing=getattr(app, "model_pricing", {}),
            max_reports=_positive_int_attribute(payload, "max_reports", 1),
            max_estimated_tokens=_positive_int_attribute(
                payload, "max_estimated_tokens", 8_000
            ),
            max_estimated_cost_usd=float(
                payload.attributes.get("max_estimated_cost_usd", 1.0)
            ),
            max_runtime_seconds=float(payload.attributes.get("max_runtime_seconds", 120)),
            max_retries=_positive_int_attribute(payload, "max_retries", 3),
            max_concurrent_provider_calls=1,
            publisher_fairness_limit=_positive_int_attribute(
                payload, "publisher_fairness_limit", 3
            ),
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
    source_hash = payload.input_content_hash or getattr(payload, "source_content_hash", "")
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
            getattr(payload, "source_artifact_reference", "")
            or payload.input_reference
        ).strip()
        source_hash = str(
            getattr(payload, "source_content_hash", "")
            or payload.input_content_hash
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
            next_payload_types: dict[str, type[QueuePayload]] = {
                "report_selection": ReportSelectionPayload,
                "report_analysis": ReportAnalysisPayload,
                "report_render": ReportRenderPayload,
                "analytics_projection": AnalyticsProjectionPayload,
            }
            next_payload_type = next_payload_types[next_queue]
            common = {
                "input_reference": artifact_reference,
                "input_content_hash": source_hash,
                "processing_version": payload.processing_version,
                "attributes": payload.attributes,
                "report_id": report_id,
            }
            if next_queue == "report_selection":
                next_payload = next_payload_type(
                    **common,
                    source_prepared_checkpoint="source_prepared",
                )
            elif next_queue == "report_analysis":
                next_payload = next_payload_type(
                    **common,
                    selection_checkpoint="selection_complete",
                )
            elif next_queue == "report_render":
                next_payload = next_payload_type(
                    **common,
                    analysis_checkpoint="analysis_complete",
                )
            else:
                next_payload = next_payload_type(
                    **common,
                    validated_artifact_reference="analysis_complete",
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
                output_verified=outcome.status in {"processed", "skipped", "checkpointed"},
                summary={
                    "pipeline_status": outcome.status,
                    "checkpoint": stop_after_stage or "analytics_projected",
                },
            ),
            downstream=downstream,
        )

    return handler


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
                resume_from_stage="", stop_after_stage="source_prepared", next_queue="report_selection"
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
                resume_from_stage="source_prepared", stop_after_stage="selection_complete", next_queue="report_analysis"
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
                resume_from_stage="selection_complete", stop_after_stage="analysis_complete", next_queue="report_render"
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
                resume_from_stage="analysis_complete", stop_after_stage="render_complete", next_queue="analytics_projection"
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
            handler=_report_stage_handler(
                resume_from_stage="analysis_complete", projection_only=True
            ),
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
            downstream=("cover_generation.v1", "publication_readiness.v1"),
            effects=("model",),
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
            downstream=("cover_generation.v1", "publication_readiness.v1"),
            effects=("model",),
            budget_profile="cross_report_analysis",
            lease_seconds=3600,
        ),
        _registration(
            "cover_generation",
            CoverGenerationPayload,
            CoverGenerationResult,
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
            "vector_retention", MaintenancePayload, WorkflowStageResult, budget_profile="maintenance"
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
            "cost_reconciliation", MaintenancePayload, WorkflowStageResult, budget_profile="maintenance"
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
