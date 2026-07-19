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

from .publishing import _cross_report_package_from_artifact
from .shared import (
    WorkflowQueueHandlerResult,
    _boolean_attribute,
    _digest,
    _positive_float_attribute,
    _positive_int_attribute,
    _string_list_attribute,
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
