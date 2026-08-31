from __future__ import annotations

import logging
from dataclasses import replace
from typing import Callable, Optional

from src.contracts.analytics_projection import (
    AnalyticsProjectionRunRequest,
)
from src.contracts.drive import DriveFile
from src.contracts.ingest import IngestOutcome, IngestSettings
from src.contracts.minimal_execution_plan import MinimalExecutionPlan
from src.contracts.report_generation import (
    ReportGenerationClientBundle,
    require_report_generation_client_bundle,
)
from src.contracts.report_store import (
    ReportPublicationMetadataGetRequest,
    ReportSourceIdentityGetRequest,
    ReportSourceIdentityResolveRequest,
    SourceIdentityResolution,
    SourcePublicationMetadata,
)
from src.contracts.run_context import RunContext
from src.generators.report_analysis_generator import start_vector_store_indexing
from src.generators.report_generation_dependencies import (
    ReportGenerationDependencies,
    ReportSignalDependencies,
)
from src.generators.report_render_generator import (
    render_preview_asset,
    render_report_output,
)
from src.generators.report_selection_generator import select_report_figures
from src.generators.report_source_generator import prepare_report_source
from src.orchestrators.report_analysis_orchestrator import run_report_analysis
from src.orchestrators._report_analysis_orchestrator.manifest import (
    record_validation_manifest_stage,
)
from src.orchestrators.signal_candidate_orchestrator import (
    run_signal_candidate_extraction,
)
from src.services import llm_service
from src.utils.errors import AppError
from src.utils.logging import log_event

from .checkpoints import (
    _analysis_checkpoint_payload,
    _analysis_checkpoint_refs,
    _build_runtime_state,
    _render_checkpoint_payload,
    _render_checkpoint_refs,
    _selection_checkpoint_payload,
    _source_checkpoint_payload,
    _vector_indexing_checkpoint_payload,
    _write_stage_checkpoint,
)
from .resume import (
    _analysis_with_report_value_score,
    _checkpoint_stage_outcome,
    _cleanup_transient_vector_store,
    _doc_map_empty_outcome,
    _pdf_text_ocr_failed_outcome,
    _pdf_text_unextractable_outcome,
    _resume_crop_from_source_checkpoint,
    _resume_from_checkpoint_stage,
    _resume_prompt_family_repair,
    _run_projection,
    _run_signal_artifact_generation,
    _score_ingested_report_source,
    _select_latest_safe_restart_stage,
)

logger = logging.getLogger("market_lense.report_generation_orchestrator")
REPORT_PIPELINE_NAME = "report_generation"
STAGE_SOURCE_PREPARED = "source_prepared"
STAGE_SELECTION_COMPLETE = "selection_complete"
STAGE_ANALYSIS_COMPLETE = "analysis_complete"
STAGE_RENDER_COMPLETE = "render_complete"
_UNATTRIBUTED_PUBLISHER_IDS = frozenset(
    {"", "unattributed", "drive_unattributed", "unknown", "unknown publisher"}
)


def _should_fresh_start_after_latest_safe_rejection(error: AppError) -> bool:
    """Allow a clean retained-source rebuild only after lineage rejection."""

    return error.code == "report_pipeline_checkpoint_lineage_not_reusable"


def _default_report_generation_dependencies() -> ReportGenerationDependencies:
    return _with_signal_candidate_orchestrator(ReportGenerationDependencies.default())


def _with_signal_candidate_orchestrator(
    deps: ReportGenerationDependencies,
) -> ReportGenerationDependencies:
    default_signal = ReportSignalDependencies.default().run_signal_candidate_extraction
    if deps.signal.run_signal_candidate_extraction is not default_signal:
        return deps
    return replace(
        deps,
        signal=replace(
            deps.signal,
            run_signal_candidate_extraction=run_signal_candidate_extraction,
        ),
    )


def _build_model_client(
    settings: IngestSettings,
    *,
    scope: str,
    provided_client=None,
    openai_chat_json_with_images=None,
    openai_ocr_pdf=None,
):
    if provided_client is not None:
        return provided_client
    if openai_chat_json_with_images is not None or openai_ocr_pdf is not None:
        return llm_service.build_client_from_callables(
            policy=llm_service.client_policy_from_settings(settings, scope=scope),
            openai_chat_json_with_images=openai_chat_json_with_images,
            openai_ocr_pdf=openai_ocr_pdf,
        )
    return llm_service.build_client_for_settings(settings, scope=scope)


def _admission_context_identity(
    ctx: RunContext,
    *,
    fallback_report_name: str,
) -> SourceIdentityResolution | None:
    """Project a retained, admitted source identity into a fresh runtime.

    A frozen validation replay intentionally does not re-run source discovery or
    admission. Its signed admission decision is therefore the canonical source
    identity available before the report store has any source rows. Do not
    manufacture an identity from an MD5-only context or an unattributed
    publisher: those states remain subject to the normal fail-closed metadata
    governance path.
    """

    identity_id = str(ctx.source_identity_id or "").strip()
    publisher = str(ctx.publisher_id or "").strip()
    if (
        not str(ctx.admission_decision_hash or "").strip()
        or not identity_id
        or publisher.casefold() in _UNATTRIBUTED_PUBLISHER_IDS
    ):
        return None
    return SourceIdentityResolution(
        schema_version="1.0",
        source_identity_id=identity_id,
        canonical_title=fallback_report_name,
        title_evidence_locator="admission_preflight.decision",
        publisher_id=publisher,
        publisher_name=publisher,
        resolution_method="admission_preflight_context",
        identity_confidence="high",
        identity_status="resolved",
    )


def _resolve_runtime_source_identity(
    *,
    file: DriveFile,
    settings: IngestSettings,
    md5: Optional[str],
    ctx: RunContext,
    deps: ReportGenerationDependencies,
) -> tuple[str, str, str, SourcePublicationMetadata, SourceIdentityResolution]:
    fallback_report_name = file.name or file.file_id
    try:
        identity = deps.render.resolve_report_source_identity(
            ReportSourceIdentityResolveRequest(
                schema_version="1.0",
                db_path=settings.reports_db,
                report_title=fallback_report_name,
                md5=md5,
            ),
            ctx,
        )
    except Exception as exc:
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="report_source_identity_resolve_failed",
                module=logger.name,
                fields={
                    "file_id": file.file_id,
                    "error_type": type(exc).__name__,
                    "error_code": exc.code if isinstance(exc, AppError) else "",
                },
            )
        )
        # A retained admission decision can still provide a verified identity
        # for a fresh isolated replay when the optional report-store lookup is
        # temporarily unavailable. Continue to the normal observation lookup
        # and the narrowly scoped admission-context fallback below.
        identity = SourceIdentityResolution(
            schema_version="1.0",
            identity_status="unknown",
            identity_issues=("identity_resolution_failed",),
        )
    publisher_name = str(getattr(identity, "publisher_name", "") or "").strip()
    source_report_name = (
        str(getattr(identity, "report_name", "") or "").strip() or fallback_report_name
    )
    source_url = str(getattr(identity, "source_url", "") or "").strip()
    source_identity = SourceIdentityResolution(
        schema_version="1.0",
        canonical_title=source_report_name,
        publisher_name=publisher_name,
        canonical_landing_page_url=source_url,
        identity_status="unknown",
        identity_issues=("identity_observation_missing",),
    )
    try:
        source_identity_response = deps.render.get_report_source_identity(
            ReportSourceIdentityGetRequest(
                schema_version="1.0",
                db_path=settings.reports_db,
                report_title=source_report_name,
                md5=md5,
                publisher_name=publisher_name or None,
            ),
            ctx,
        )
        source_identity = source_identity_response.resolution
        publisher_name = source_identity.publisher_name or publisher_name
        source_report_name = source_identity.canonical_title or source_report_name
        source_url = source_identity.canonical_landing_page_url or source_url
    except Exception as exc:
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="report_source_identity_observation_resolve_failed",
                module=logger.name,
                fields={
                    "file_id": file.file_id,
                    "error_type": type(exc).__name__,
                    "error_code": exc.code if isinstance(exc, AppError) else "",
                },
            )
        )
    admitted_identity = _admission_context_identity(
        ctx,
        fallback_report_name=fallback_report_name,
    )
    if (
        admitted_identity is not None
        and str(getattr(source_identity, "identity_status", "") or "").casefold()
        != "resolved"
    ):
        source_identity = admitted_identity
        publisher_name = admitted_identity.publisher_name
        source_report_name = admitted_identity.canonical_title
    publication_resolution = "unresolved"
    try:
        publication_response = deps.render.get_report_publication_metadata(
            ReportPublicationMetadataGetRequest(
                schema_version="1.0",
                db_path=settings.reports_db,
                report_title=source_report_name,
                md5=md5,
                publisher_name=publisher_name or None,
            ),
            ctx,
        )
        publication_metadata = publication_response.metadata
        publication_resolution = str(
            getattr(publication_response, "resolution_source", "unresolved")
            or "unresolved"
        )
    except Exception as exc:
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="report_publication_metadata_resolve_failed",
                module=logger.name,
                fields={
                    "file_id": file.file_id,
                    "error_type": type(exc).__name__,
                    "error_code": exc.code if isinstance(exc, AppError) else "",
                },
            )
        )
        publication_metadata = SourcePublicationMetadata(
            schema_version="1.0", evidence_status="unknown"
        )
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="report_source_identity_resolved",
            module=logger.name,
            fields={
                "file_id": file.file_id,
                "publisher_name": publisher_name,
                "source_report_name": source_report_name,
                "has_source_url": bool(source_url),
                "resolution_source": str(
                    getattr(identity, "resolution_source", "") or ""
                ),
                "publication_metadata_status": publication_metadata.evidence_status,
                "publication_metadata_resolution": publication_resolution,
                "source_identity_status": source_identity.identity_status,
                "source_metadata_hash": source_identity.source_metadata_hash,
            },
        )
    )
    return (
        publisher_name,
        source_report_name,
        source_url,
        publication_metadata,
        source_identity,
    )


def run_report_generation(
    file: DriveFile,
    local_pdf_path: str,
    settings: IngestSettings,
    md5: Optional[str],
    ctx: RunContext,
    *,
    source_openai_client=None,
    taxonomy_openai_client=None,
    category_fit_openai_client=None,
    evidence_pack_openai_client=None,
    artifact_openai_client=None,
    validation_openai_client=None,
    regeneration_openai_client=None,
    figure_caption_openai_client=None,
    client_bundle: Optional[ReportGenerationClientBundle] = None,
    dependencies: Optional[ReportGenerationDependencies] = None,
    analytics_projection_fn: Optional[
        Callable[[AnalyticsProjectionRunRequest], object]
    ] = None,
    resume_from_stage: Optional[str] = None,
    require_artifact_lineage: bool = False,
    execution_compatibility: Optional[dict[str, object]] = None,
    minimal_execution_plan: Optional[MinimalExecutionPlan] = None,
    enforce_minimal_execution: bool = False,
    stop_after_stage: Optional[str] = None,
    projection_only: bool = False,
) -> IngestOutcome:
    deps = (
        _with_signal_candidate_orchestrator(dependencies)
        if dependencies is not None
        else _default_report_generation_dependencies()
    )
    (
        publisher_name,
        source_report_name,
        source_url,
        source_publication_metadata,
        source_identity,
    ) = _resolve_runtime_source_identity(
        file=file,
        settings=settings,
        md5=md5,
        ctx=ctx,
        deps=deps,
    )
    runtime = _build_runtime_state(
        file,
        local_pdf_path,
        settings,
        md5,
        ctx,
        publisher_name=publisher_name,
        source_report_name=source_report_name,
        source_url=source_url,
        source_publication_metadata=source_publication_metadata,
        source_identity=source_identity,
        execution_compatibility=execution_compatibility,
        execution_plan_hash=(
            minimal_execution_plan.plan_hash
            if minimal_execution_plan is not None
            else ""
        ),
        execution_plan_intent=(
            minimal_execution_plan.execution_intent
            if minimal_execution_plan is not None
            else ""
        ),
        planned_stages=(
            minimal_execution_plan.required_stages
            if minimal_execution_plan is not None
            else None
        ),
    )
    if minimal_execution_plan is not None:
        logger.info(
            log_event(
                runtime.ctx,
                role="orchestrator",
                event="minimal_execution_plan_consumed",
                module=logger.name,
                fields={
                    "plan_hash": minimal_execution_plan.plan_hash,
                    "intent": minimal_execution_plan.execution_intent,
                    "required_stages": minimal_execution_plan.required_stages,
                    "file_id": runtime.file.file_id,
                },
            )
        )
    requested_resume_stage = str(resume_from_stage or "").strip()
    if requested_resume_stage == "latest_safe":
        try:
            requested_resume_stage = _select_latest_safe_restart_stage(runtime)
        except AppError as exc:
            if not _should_fresh_start_after_latest_safe_rejection(exc):
                raise
            requested_resume_stage = ""
            logger.info(
                log_event(
                    runtime.ctx,
                    role="orchestrator",
                    event="report_pipeline_latest_safe_fresh_start_selected",
                    module=logger.name,
                    fields={
                        "file_id": runtime.file.file_id,
                        "error_code": exc.code,
                    },
                )
            )
    requested_stop_stage = str(stop_after_stage or "").strip()
    if projection_only and requested_resume_stage != STAGE_ANALYSIS_COMPLETE:
        raise AppError(
            code="report_pipeline_projection_stage_invalid",
            message="Analytics projection requires the validated analysis checkpoint",
            retryable=False,
        )
    if requested_stop_stage and requested_stop_stage not in {
        STAGE_SOURCE_PREPARED,
        STAGE_SELECTION_COMPLETE,
        STAGE_ANALYSIS_COMPLETE,
        STAGE_RENDER_COMPLETE,
    }:
        raise AppError(
            code="report_pipeline_stop_stage_invalid",
            message="Queue stage stop boundary is not supported",
            retryable=False,
            context={"stop_after_stage": requested_stop_stage},
        )
    enforced_render_only = (
        enforce_minimal_execution
        and minimal_execution_plan is not None
        and minimal_execution_plan.required_stages == [STAGE_RENDER_COMPLETE]
    )
    enforced_crop_only = (
        enforce_minimal_execution
        and minimal_execution_plan is not None
        and minimal_execution_plan.required_stages
        == [STAGE_SELECTION_COMPLETE, STAGE_RENDER_COMPLETE]
    )
    if (
        enforce_minimal_execution
        and requested_resume_stage in {STAGE_ANALYSIS_COMPLETE, STAGE_RENDER_COMPLETE}
        and client_bundle is None
        and all(
            client is None
            for client in (
                source_openai_client,
                taxonomy_openai_client,
                category_fit_openai_client,
                evidence_pack_openai_client,
                artifact_openai_client,
                validation_openai_client,
                regeneration_openai_client,
                figure_caption_openai_client,
            )
        )
    ):
        logger.info(
            log_event(
                runtime.ctx,
                role="orchestrator",
                event="report_generation_model_clients_avoided",
                module=logger.name,
                fields={
                    "file_id": runtime.file.file_id,
                    "resume_from_stage": requested_resume_stage,
                },
            )
        )
        return _resume_from_checkpoint_stage(
            runtime,
            deps,
            analytics_projection_fn,
            requested_resume_stage=requested_resume_stage,
            require_artifact_lineage=require_artifact_lineage,
            skip_post_render_projection=enforced_render_only,
            stop_after_stage=requested_stop_stage,
            projection_only=projection_only,
        )
    if enforced_crop_only:
        return _resume_crop_from_source_checkpoint(
            runtime,
            deps,
            analytics_projection_fn,
        )
    if (
        enforce_minimal_execution
        and minimal_execution_plan is not None
        and minimal_execution_plan.required_prompt_families
    ):
        if client_bundle is not None:
            bundle = require_report_generation_client_bundle(client_bundle)
            validation_openai_client = bundle.validation_client
            regeneration_openai_client = bundle.regeneration_client
        else:
            validation_openai_client = _build_model_client(
                settings,
                scope="validation",
                provided_client=validation_openai_client,
            )
            regeneration_openai_client = _build_model_client(
                settings,
                scope="artifact_regeneration",
                provided_client=regeneration_openai_client,
            )
        return _resume_prompt_family_repair(
            runtime,
            deps,
            analytics_projection_fn,
            prompt_families=minimal_execution_plan.required_prompt_families,
            regeneration_openai_client=regeneration_openai_client,
            validation_openai_client=validation_openai_client,
            stop_after_stage=requested_stop_stage,
        )
    if client_bundle is not None:
        bundle = require_report_generation_client_bundle(client_bundle)
        source_openai_client = bundle.source_ocr_client
        taxonomy_openai_client = bundle.taxonomy_client
        category_fit_openai_client = bundle.category_fit_client
        evidence_pack_openai_client = bundle.evidence_pack_client
        artifact_openai_client = bundle.artifact_client
        validation_openai_client = bundle.validation_client
        regeneration_openai_client = bundle.regeneration_client
        figure_caption_openai_client = bundle.figure_caption_client
    else:
        if not requested_resume_stage:
            source_openai_client = _build_model_client(
                settings,
                scope="pdf_text_ocr",
                provided_client=source_openai_client,
                openai_ocr_pdf=deps.source.openai_ocr_pdf,
            )
        if requested_resume_stage != STAGE_RENDER_COMPLETE:
            taxonomy_openai_client = _build_model_client(
                settings,
                scope="taxonomy",
                provided_client=taxonomy_openai_client,
            )
            category_fit_openai_client = _build_model_client(
                settings,
                scope="context_category_fit",
                provided_client=category_fit_openai_client,
            )
            evidence_pack_openai_client = _build_model_client(
                settings,
                scope="evidence_pack_generator",
                provided_client=evidence_pack_openai_client,
            )
            artifact_openai_client = _build_model_client(
                settings,
                scope="artifact_generator",
                provided_client=artifact_openai_client,
            )
            validation_openai_client = _build_model_client(
                settings,
                scope="validation",
                provided_client=validation_openai_client,
            )
            regeneration_openai_client = _build_model_client(
                settings,
                scope="artifact_regeneration",
                provided_client=regeneration_openai_client,
            )
            figure_caption_openai_client = _build_model_client(
                settings,
                scope="figure_caption",
                provided_client=figure_caption_openai_client,
                openai_chat_json_with_images=(
                    deps.analysis.figure_caption.openai_chat_json_with_images
                ),
            )
    if requested_resume_stage:
        return _resume_from_checkpoint_stage(
            runtime,
            deps,
            analytics_projection_fn,
            requested_resume_stage=requested_resume_stage,
            require_artifact_lineage=require_artifact_lineage,
            taxonomy_openai_client=taxonomy_openai_client,
            category_fit_openai_client=category_fit_openai_client,
            evidence_pack_openai_client=evidence_pack_openai_client,
            artifact_openai_client=artifact_openai_client,
            validation_openai_client=validation_openai_client,
            regeneration_openai_client=regeneration_openai_client,
            figure_caption_openai_client=figure_caption_openai_client,
            skip_post_render_projection=(
                enforce_minimal_execution and minimal_execution_plan is not None
            ),
            stop_after_stage=requested_stop_stage,
            projection_only=projection_only,
        )
    logger.info(
        log_event(
            runtime.ctx,
            role="orchestrator",
            event="report_generate_start",
            module=logger.name,
            fields={
                "file_id": runtime.file.file_id,
                "name": runtime.file_name,
                "modes": runtime.analysis_modes,
            },
        )
    )
    logger.info(
        log_event(
            runtime.ctx,
            role="orchestrator",
            event="report_parallel_config",
            module=logger.name,
            fields={
                "report_worker_limit": runtime.report_worker_limit,
                "parallel_within_file": runtime.parallel_within_file,
            },
        )
    )

    source = None
    vector_state = None
    try:
        source = prepare_report_source(
            runtime,
            deps.source,
            ocr_openai_client=source_openai_client,
        )
        analysis_checkpoint_path = _write_stage_checkpoint(
            runtime,
            stage_name=STAGE_SOURCE_PREPARED,
            artifact_refs={
                "source_pdf": runtime.local_pdf_path,
                "analysis_pdf": source.analysis_pdf_path or runtime.local_pdf_path,
                "contents_image": source.contents_image,
            },
            payload={
                "schema_version": "1.0",
                "source": _source_checkpoint_payload(source),
            },
        )
        if requested_stop_stage == STAGE_SOURCE_PREPARED:
            return _checkpoint_stage_outcome(runtime, STAGE_SOURCE_PREPARED)
        vector_state = start_vector_store_indexing(runtime, source, deps.analysis)
        selection = select_report_figures(
            runtime,
            source,
            deps.selection,
            crop_qa_llm_client=figure_caption_openai_client,
        )
        analysis_checkpoint_path = _write_stage_checkpoint(
            runtime,
            stage_name=STAGE_SELECTION_COMPLETE,
            artifact_refs={
                "source_pdf": runtime.local_pdf_path,
                "analysis_pdf": source.analysis_pdf_path or runtime.local_pdf_path,
            },
            payload={
                "schema_version": "1.0",
                "source": _source_checkpoint_payload(source),
                "selection": _selection_checkpoint_payload(selection),
                "vector_indexing": _vector_indexing_checkpoint_payload(vector_state),
            },
        )
        if requested_stop_stage == STAGE_SELECTION_COMPLETE:
            return _checkpoint_stage_outcome(runtime, STAGE_SELECTION_COMPLETE)
        preview_resp = render_preview_asset(runtime, source, deps.render)
        analysis = run_report_analysis(
            runtime,
            source,
            selection,
            vector_state,
            deps.analysis,
            taxonomy_openai_client=taxonomy_openai_client,
            category_fit_openai_client=category_fit_openai_client,
            evidence_pack_openai_client=evidence_pack_openai_client,
            artifact_openai_client=artifact_openai_client,
            validation_openai_client=validation_openai_client,
            regeneration_openai_client=regeneration_openai_client,
            figure_caption_openai_client=figure_caption_openai_client,
        )
        _write_stage_checkpoint(
            runtime,
            stage_name=STAGE_ANALYSIS_COMPLETE,
            artifact_refs=_analysis_checkpoint_refs(
                runtime, source, analysis, preview_resp
            ),
            payload=_analysis_checkpoint_payload(
                source, selection, analysis, preview_resp
            ),
        )
        if requested_stop_stage == STAGE_ANALYSIS_COMPLETE:
            return _checkpoint_stage_outcome(runtime, STAGE_ANALYSIS_COMPLETE)
        report_value_score = _score_ingested_report_source(runtime, analysis, deps)
        analysis = _analysis_with_report_value_score(analysis, report_value_score)
        try:
            outcome = render_report_output(
                runtime,
                source,
                selection,
                analysis,
                deps.render,
                preview_resp=preview_resp,
            )
        except AppError as exc:
            if exc.code != "card_publication_date_invalid":
                raise
            raise AppError(
                code=exc.code,
                message=exc.message,
                cause=exc,
                retryable=False,
                severity=exc.severity,
                context={
                    **dict(exc.context or {}),
                    "file_id": runtime.file.file_id,
                    "analysis_checkpoint_path": analysis_checkpoint_path,
                    "resume_stage": STAGE_ANALYSIS_COMPLETE,
                },
            ) from exc
        manifest_ctx = replace(
            runtime.ctx,
            report_id=runtime.file.file_id,
            source_identity_id=runtime.md5 or runtime.file.file_id,
            publisher_id=runtime.publisher_name or "unattributed",
            workflow="report_generation",
            stage="rendering",
            artifact_family="rendered_html",
        )
        record_validation_manifest_stage(
            settings=runtime.settings,
            ctx=manifest_ctx,
            stage="rendering",
            source_identity_id=runtime.md5 or runtime.file.file_id,
            input_artifact_ids=tuple(analysis.evidence_paths.values()),
            output_artifact_ids=(outcome.html_path or "",),
        )
        record_validation_manifest_stage(
            settings=runtime.settings,
            ctx=manifest_ctx,
            stage="final_html_validation",
            source_identity_id=runtime.md5 or runtime.file.file_id,
            input_artifact_ids=(outcome.html_path or "",),
            output_artifact_ids=(outcome.html_path or "",),
        )
        _write_stage_checkpoint(
            runtime,
            stage_name=STAGE_RENDER_COMPLETE,
            artifact_refs=_render_checkpoint_refs(
                runtime,
                source,
                analysis,
                preview_resp,
                outcome,
            ),
            payload=_render_checkpoint_payload(
                source, selection, analysis, preview_resp, outcome
            ),
        )
        if requested_stop_stage == STAGE_RENDER_COMPLETE:
            return _cleanup_transient_vector_store(outcome, runtime, deps)
        if (
            not (enforce_minimal_execution and minimal_execution_plan is not None)
            and _run_projection(runtime, analysis, outcome, analytics_projection_fn)
            is not None
        ):
            outcome = _run_signal_artifact_generation(runtime, analysis, outcome, deps)
            _write_stage_checkpoint(
                runtime,
                stage_name=STAGE_RENDER_COMPLETE,
                artifact_refs=_render_checkpoint_refs(
                    runtime,
                    source,
                    analysis,
                    preview_resp,
                    outcome,
                ),
                payload=_render_checkpoint_payload(
                    source, selection, analysis, preview_resp, outcome
                ),
            )
        return _cleanup_transient_vector_store(outcome, runtime, deps)
    except AppError as exc:
        if exc.code == "pdf_text_unextractable":
            return _pdf_text_unextractable_outcome(runtime, exc)
        if exc.code == "pdf_text_ocr_failed":
            return _pdf_text_ocr_failed_outcome(runtime, exc)
        if (
            exc.code == "doc_map_empty"
            and source is not None
            and vector_state is not None
        ):
            return _cleanup_transient_vector_store(
                _doc_map_empty_outcome(runtime, source, vector_state, exc),
                runtime,
                deps,
            )
        raise
    finally:
        if source is not None and source.pdf_context is not None:
            source.pdf_context.close()


__all__ = [
    "run_report_generation",
]
