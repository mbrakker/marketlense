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
from collections.abc import Mapping, Sequence
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

from .publishing import _persist_queue_publish_package
from .shared import (
    WorkflowQueueHandlerResult,
    _boolean_attribute,
    _digest,
    _positive_float_attribute,
    _positive_int_attribute,
    _string_list_attribute,
)


def _signal_generation_input_hash(
    *,
    manifest_sha256: str,
    model_routing_policy_version: str,
    processing_version: str,
    attributes: Mapping[str, object],
) -> str:
    return _digest(
        "signal-generation-input.v1",
        manifest_sha256,
        model_routing_policy_version,
        processing_version,
        json.dumps(attributes, sort_keys=True, separators=(",", ":")),
    )


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
    requested_publisher_filters = _string_list_attribute(payload, "publisher_filters")
    publisher_filters = list(requested_publisher_filters)
    category_filters = _string_list_attribute(payload, "category_filters")
    tag_filters = _string_list_attribute(payload, "tag_filters")
    max_source_reports = _positive_int_attribute(payload, "max_source_reports", 6)
    max_evidence_items = _positive_int_attribute(payload, "max_evidence_items", 48)
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
            minimum_source_reports=minimum_source_reports,
            minimum_evidence_items=minimum_evidence_items,
            state_db=app.state_db,
        ),
        ctx,
    )
    held_groups = [
        group
        for group in outcome.batch.groups
        if group.validation_status == "approved" and group.publication_status == "held"
    ]
    publication_hold_reason_counts: dict[str, int] = {}
    for group in held_groups:
        reason = group.publication_hold_reason
        publication_hold_reason_counts[reason] = (
            publication_hold_reason_counts.get(reason, 0) + 1
        )

    downstream: list[WorkflowJobSubmission] = []
    manifest_hashes = outcome.stored_response.manifest_hashes
    if any(
        len(manifest_hashes.get(group.group_id, "")) != 64
        or any(
            character not in "0123456789abcdef"
            for character in manifest_hashes.get(group.group_id, "")
        )
        for group in outcome.batch.groups
    ):
        raise AppError(
            code="signal_candidate_manifest_missing",
            message="Stored Signal candidate snapshot checksums are incomplete",
            retryable=False,
            severity="error",
        )
    for group in outcome.batch.groups:
        if not (
            generate_signals
            and group.validation_status == "approved"
            and group.publication_status == "eligible"
        ):
            continue
        manifest_sha256 = manifest_hashes[group.group_id]
        attributes: dict[str, str | int | bool | list[str]] = {
            "config_path": config_path,
            "category_filters": category_filters,
            "date_range_end": str(payload.attributes.get("date_range_end", "")),
            "date_range_start": str(payload.attributes.get("date_range_start", "")),
            "max_evidence_items": max_evidence_items,
            "max_source_reports": max_source_reports,
            "minimum_evidence_items": minimum_evidence_items,
            "minimum_source_reports": minimum_source_reports,
            "override_publishability": True,
            "publisher_filters": publisher_filters,
            "tag_filters": tag_filters,
        }
        generation_input_hash = _signal_generation_input_hash(
            manifest_sha256=manifest_sha256,
            model_routing_policy_version=payload.signal_selection_policy_version,
            processing_version=payload.processing_version,
            attributes=attributes,
        )
        downstream.append(
            WorkflowJobSubmission(
                schema_version="1.0",
                queue_name="signal_generation",
                job_type="signal_generation.v1",
                payload=SignalGenerationPayload(
                    candidate_group_id=group.group_id,
                    frozen_evidence_manifest=(
                        f"signal-candidate-manifests:{group.extraction_request_id}:"
                        f"{group.group_id}:{manifest_sha256}"
                    ),
                    frozen_manifest_sha256=manifest_sha256,
                    model_routing_policy_version=payload.signal_selection_policy_version,
                    extraction_request_id=group.extraction_request_id,
                    topic=group.topic,
                    candidate_ids=list(group.candidate_ids),
                    source_report_ids=list(group.source_report_ids),
                    evidence_ids=list(group.evidence_ids),
                    topic_ids=list(group.topic_ids),
                    source_category_ids={
                        report_id: list(category_ids)
                        for report_id, category_ids in group.source_category_ids.items()
                    },
                    input_reference=app.signal_store_db or app.reports_db,
                    input_content_hash=generation_input_hash,
                    processing_version=payload.processing_version,
                    attributes=attributes,
                ),
                idempotency_key=_digest(
                    "signal-generation",
                    group.group_id,
                    generation_input_hash,
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
        )
    return WorkflowQueueHandlerResult(
        result=WorkflowStageResult(
            output_reference=f"signal-candidates:{outcome.extraction_request_id}",
            output_content_hash=_digest(
                "signal-candidate-batch.v1",
                outcome.extraction_request_id,
                *sorted(
                    f"{group.group_id}:{manifest_hashes[group.group_id]}"
                    for group in outcome.batch.groups
                ),
            ),
            execution_plan_hash=job.execution_plan_hash,
            output_verified=outcome.status == "stored",
            summary={
                "candidate_count": outcome.candidate_count,
                "group_count": outcome.group_count,
                "publication_hold_group_count": len(held_groups),
                "publication_hold_reason_counts": json.dumps(
                    publication_hold_reason_counts,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
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
    publisher_by_report_id = {
        item.report_id: item.publisher for item in signal.source_attributions
    }
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
        selected_theme_id=signal.candidate_group_id or group_id,
        selected_report_ids=source_report_ids,
        source_metadata=[
            {
                "report_id": report_id,
                "publisher": publisher_by_report_id.get(report_id, ""),
            }
            for report_id in source_report_ids
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
    missing_manifest_fields = [
        field_name
        for field_name, value in (
            ("candidate_group_id", payload.candidate_group_id),
            ("frozen_evidence_manifest", payload.frozen_evidence_manifest),
            ("frozen_manifest_sha256", payload.frozen_manifest_sha256),
            ("extraction_request_id", payload.extraction_request_id),
            ("topic", payload.topic),
            ("candidate_ids", payload.candidate_ids),
            ("source_report_ids", payload.source_report_ids),
            ("evidence_ids", payload.evidence_ids),
            ("topic_ids", payload.topic_ids),
            ("source_category_ids", payload.source_category_ids),
            ("input_content_hash", payload.input_content_hash),
        )
        if not value
    ]
    if missing_manifest_fields:
        raise AppError(
            code="signal_frozen_manifest_incomplete",
            message="Signal generation requires the complete frozen candidate manifest",
            retryable=False,
            severity="error",
            context={"missing_fields": missing_manifest_fields},
        )
    expected_manifest_reference = (
        f"signal-candidate-manifests:{payload.extraction_request_id}:"
        f"{payload.candidate_group_id}:{payload.frozen_manifest_sha256}"
    )
    expected_input_hash = _signal_generation_input_hash(
        manifest_sha256=payload.frozen_manifest_sha256,
        model_routing_policy_version=payload.model_routing_policy_version,
        processing_version=payload.processing_version,
        attributes=payload.attributes,
    )
    if (
        len(payload.frozen_manifest_sha256) != 64
        or any(
            character not in "0123456789abcdef"
            for character in payload.frozen_manifest_sha256
        )
        or payload.frozen_evidence_manifest != expected_manifest_reference
        or payload.input_content_hash != expected_input_hash
    ):
        raise AppError(
            code="signal_frozen_manifest_changed",
            message="Queued Signal manifest reference or checksum has changed",
            retryable=False,
            severity="error",
            context={"candidate_group_id": payload.candidate_group_id},
        )
    topic = str(payload.topic or "").strip()
    config_path = str(payload.attributes.get("config_path", "")).strip()
    app = load_settings(ConfigLoadRequest(schema_version="1.0", path=config_path), ctx)
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
                candidate_manifest_sha256=payload.frozen_manifest_sha256,
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
                candidate_group_id=payload.candidate_group_id,
                extraction_request_id=payload.extraction_request_id,
                candidate_ids=list(payload.candidate_ids),
                source_report_ids=list(payload.source_report_ids),
                evidence_ids=list(payload.evidence_ids),
                topic_ids=list(payload.topic_ids),
                source_category_ids={
                    report_id: list(category_ids)
                    for report_id, category_ids in payload.source_category_ids.items()
                },
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
            attributes={
                "config_path": config_path,
                "override_publishability": _boolean_attribute(
                    payload, "override_publishability", True
                ),
            },
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
