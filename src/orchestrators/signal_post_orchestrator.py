from __future__ import annotations

import logging
from dataclasses import replace
from typing import Callable, Protocol, cast

from src.contracts.cross_report_analysis import (
    CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
    CrossReportProjectedDataReadRequest,
    CrossReportProjectedDataReadResponse,
    CrossReportPublishResultSummary,
    CrossReportPublishStatus,
    PublicationMode,
)
from src.contracts.cover_images import CoverImageGenerationRequest, CoverImageReport
from src.contracts.publish import PublishSettings
from src.contracts.remediation import RemediationArtifactReference
from src.contracts.run_context import RunContext
from src.contracts.signal_candidates import (
    SIGNAL_CANDIDATE_SCHEMA_VERSION,
    SignalCandidateReadRequest,
    SignalCandidateReadResponse,
)
from src.contracts.wordpress import WordPressAuthSettings
from src.contracts.wordpress_entities import (
    WORDPRESS_ENTITY_SCHEMA_VERSION,
    SignalPostWorkflowRequest,
    SignalPostWorkflowResult,
    SignalPublishProjection,
)
from src.generators.signal_post_generator import build_signal_publish_projection
from src.generators.cover_image_generator import generate_cover_images
from src.orchestrators.publish_orchestrator import publish_signal_projection
from src.orchestrators.remediation_orchestrator import (
    record_workflow_failure,
    remediation_input_checksum,
)
from src.services import analytics_store_service
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.signal_post_orchestrator")


class _PublishSignalFn(Protocol):
    def __call__(
        self,
        projection: SignalPublishProjection,
        signal_card: dict[str, object],
        settings: PublishSettings,
        ctx: RunContext,
        *,
        dry_run: bool,
    ) -> CrossReportPublishResultSummary: ...


def _projected_data_request(
    request: SignalPostWorkflowRequest,
) -> CrossReportProjectedDataReadRequest:
    generation = request.generation_request
    return CrossReportProjectedDataReadRequest(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        db_path=request.db_path,
        publisher_filters=list(generation.publisher_filters),
        date_range_start=generation.date_range_start,
        date_range_end=generation.date_range_end,
        category_filters=list(generation.category_filters),
        tag_filters=list(generation.tag_filters),
        content_classes=["claim", "finding", "quote"],
        minimum_projection_status="projected",
    )


def _dry_run_publish_settings(request: SignalPostWorkflowRequest) -> PublishSettings:
    return PublishSettings(
        schema_version="1.0",
        output_dir=request.output_root,
        state_db="",
        reports_db=request.db_path,
        category_mapping_path="",
        wp=WordPressAuthSettings(
            schema_version="1.0",
            site_url="",
            username=None,
            app_password=None,
            bearer_token=None,
            post_status="draft",
            post_type="ml_report",
        ),
        validation_policy="warn",
    )


def _signal_not_requested_result(
    *,
    request: SignalPostWorkflowRequest,
    projection: SignalPublishProjection,
) -> CrossReportPublishResultSummary:
    return CrossReportPublishResultSummary(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        publication_mode=cast(PublicationMode, request.publication_mode),
        status=cast(CrossReportPublishStatus, "not_requested"),
        target_route=projection.target_route,
        idempotency_reused=False,
        target_post_type="ml_signal",
        target_slug=projection.slug,
        category_slugs=list(projection.topic_ids),
        tag_slugs=[],
        taxonomy_term_slugs={},
    )


def _signal_card_payload(
    request: SignalPostWorkflowRequest,
    projection: SignalPublishProjection,
    ctx: RunContext,
) -> dict[str, object]:
    outcomes = generate_cover_images(
        CoverImageGenerationRequest(
            schema_version="2.0",
            output_dir=request.output_root,
            style_config_path=request.cover_style_path,
            reports=[
                CoverImageReport(
                    schema_version="2.0",
                    file_id=projection.file_id,
                    title=projection.card_content.summary,
                    publisher="Market Lens Signal",
                    report_slug=projection.slug,
                    categories=list(projection.topic_ids),
                    time_period=None,
                    region=None,
                    fingerprint=projection.card_content.fingerprint,
                    cover_profile="signal",
                )
            ],
        ),
        ctx,
    )
    outcome = outcomes[0] if outcomes else None
    if outcome is None or outcome.status != "generated" or outcome.assets is None:
        raise AppError(
            code="signal_card_cover_generation_failed",
            message="Signal card covers could not be generated.",
            retryable=False,
            severity="error",
            context={
                "request_id": request.request_id,
                "slug": projection.slug,
                "error": outcome.error if outcome else "no cover outcome returned",
            },
        )
    card = projection.card_content
    return {
        "schema_version": card.schema_version,
        "summary": card.summary,
        "confidence": card.confidence,
        "source_count": card.source_count,
        "evidence_count": card.evidence_count,
        "uncertainty": card.uncertainty,
        "covers": {
            "small": outcome.assets.small.output_path,
            "medium": outcome.assets.medium.output_path,
            "large": outcome.assets.large.output_path,
        },
    }


def _run_signal_post_workflow(
    request: SignalPostWorkflowRequest,
    ctx: RunContext,
    *,
    publish_settings: PublishSettings | None = None,
    read_projected_data_fn: Callable[
        [CrossReportProjectedDataReadRequest, RunContext],
        CrossReportProjectedDataReadResponse,
    ] = analytics_store_service.read_cross_report_projected_data,
    read_signal_candidates_fn: Callable[
        [SignalCandidateReadRequest, RunContext],
        SignalCandidateReadResponse,
    ] = analytics_store_service.read_signal_candidates,
    publish_signal_fn: _PublishSignalFn = publish_signal_projection,
) -> SignalPostWorkflowResult:
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="signal_post_workflow_start",
            module=logger.name,
            fields={
                "request_id": request.request_id,
                "publication_mode": request.publication_mode,
                "db_path": request.db_path,
            },
        )
    )
    projected_request = _projected_data_request(request)
    projected_data = read_projected_data_fn(projected_request, ctx)
    generation = request.generation_request
    candidate_data = read_signal_candidates_fn(
        SignalCandidateReadRequest(
            schema_version=SIGNAL_CANDIDATE_SCHEMA_VERSION,
            db_path=request.signal_store_db or request.db_path,
            validation_statuses=["approved"],
            source_report_ids=[],
            evidence_ids=[],
            topic_filters=[
                generation.topic,
                *generation.tag_filters,
                *generation.category_filters,
            ],
            limit=max(1, generation.max_source_reports),
        ),
        ctx,
    )
    projection = build_signal_publish_projection(
        request.generation_request,
        projected_data,
        ctx,
        candidate_data=candidate_data,
    )
    signal_card = _signal_card_payload(request, projection, ctx)

    if request.publication_mode in {"generate_only", "validate_only"}:
        publish_result = _signal_not_requested_result(
            request=request,
            projection=projection,
        )
    else:
        dry_run = request.publication_mode == "publish_dry_run"
        if publish_settings is None and dry_run:
            resolved_publish_settings = _dry_run_publish_settings(request)
        elif publish_settings is None:
            raise AppError(
                code="signal_publish_settings_missing",
                message="Live Signal publication requires publish settings.",
                retryable=False,
                severity="error",
                context={
                    "request_id": request.request_id,
                    "publication_mode": request.publication_mode,
                },
            )
        else:
            resolved_publish_settings = publish_settings

        publish_result = publish_signal_fn(
            projection,
            signal_card,
            replace(resolved_publish_settings, output_dir=request.output_root),
            ctx,
            dry_run=dry_run,
        )

    result = SignalPostWorkflowResult(
        schema_version=WORDPRESS_ENTITY_SCHEMA_VERSION,
        request_id=request.request_id,
        projected_data_request=projected_request,
        projection=projection,
        publish_result=publish_result,
    )
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="signal_post_workflow_complete",
            module=logger.name,
            fields={
                "request_id": request.request_id,
                "publication_mode": request.publication_mode,
                "slug": projection.slug,
                "publish_status": publish_result.status,
                "target_route": publish_result.target_route,
                "target_post_type": publish_result.target_post_type or "",
            },
        )
    )
    return result


def run_signal_post_workflow(
    request: SignalPostWorkflowRequest,
    ctx: RunContext,
    *,
    publish_settings: PublishSettings | None = None,
    read_projected_data_fn: Callable[
        [CrossReportProjectedDataReadRequest, RunContext],
        CrossReportProjectedDataReadResponse,
    ] = analytics_store_service.read_cross_report_projected_data,
    read_signal_candidates_fn: Callable[
        [SignalCandidateReadRequest, RunContext], SignalCandidateReadResponse
    ] = analytics_store_service.read_signal_candidates,
    publish_signal_fn: _PublishSignalFn = publish_signal_projection,
) -> SignalPostWorkflowResult:
    """Run Signal publishing with an explicit terminal-failure ledger hook."""

    try:
        return _run_signal_post_workflow(
            request,
            ctx,
            publish_settings=publish_settings,
            read_projected_data_fn=read_projected_data_fn,
            read_signal_candidates_fn=read_signal_candidates_fn,
            publish_signal_fn=publish_signal_fn,
        )
    except Exception as exc:
        record_workflow_failure(
            state_db=request.state_db,
            workflow="signal_post",
            stage="workflow",
            operation="run_signal_post_workflow",
            error=exc,
            ctx=ctx,
            input_checksum=remediation_input_checksum(
                {
                    "request_id": request.request_id,
                    "publication_mode": request.publication_mode,
                    "db_path": request.db_path,
                    "signal_store_db": request.signal_store_db,
                }
            ),
            source_id=request.db_path,
            reusable_artifacts=[
                RemediationArtifactReference(
                    schema_version="1.0",
                    name="signal_output_root",
                    reference=request.output_root,
                )
            ],
        )
        raise
