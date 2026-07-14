from __future__ import annotations
from dataclasses import asdict
from dataclasses import replace
import logging
from typing import Callable, Optional
from src.contracts.analytics_projection import (
    AnalyticsProjectionRunRequest,
)
from src.contracts.drive import DriveFile
from src.contracts.ingest import IngestOutcome, IngestSettings
from src.contracts.report_generation import (
    ReportGenerationClientBundle,
    require_report_generation_client_bundle,
)
from src.contracts.report_store import ReportSourceIdentityResolveRequest
from src.contracts.run_context import RunContext
from src.generators.report_analysis_generator import start_vector_store_indexing
from src.generators.report_generation_dependencies import ReportGenerationDependencies
from src.generators.report_generation_dependencies import ReportSignalDependencies
from src.generators.report_render_generator import (
    render_preview_asset,
    render_report_output,
)
from src.generators.report_selection_generator import select_report_figures
from src.generators.report_source_generator import prepare_report_source
from src.orchestrators.report_analysis_orchestrator import run_report_analysis
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
    _render_checkpoint_refs,
    _selection_checkpoint_payload,
    _source_checkpoint_payload,
    _vector_indexing_checkpoint_payload,
    _write_stage_checkpoint,
)

from .resume import (
    _analysis_with_report_value_score,
    _cleanup_transient_vector_store,
    _doc_map_empty_outcome,
    _pdf_text_ocr_failed_outcome,
    _pdf_text_unextractable_outcome,
    _resume_from_checkpoint_stage,
    _run_projection,
    _run_signal_artifact_generation,
    _score_ingested_report_source,
)

logger = logging.getLogger("market_lense.report_generation_orchestrator")
REPORT_PIPELINE_NAME = "report_generation"
STAGE_SOURCE_PREPARED = "source_prepared"
STAGE_SELECTION_COMPLETE = "selection_complete"
STAGE_ANALYSIS_COMPLETE = "analysis_complete"
STAGE_RENDER_COMPLETE = "render_complete"


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


def _resolve_runtime_source_identity(
    *,
    file: DriveFile,
    settings: IngestSettings,
    md5: Optional[str],
    ctx: RunContext,
    deps: ReportGenerationDependencies,
) -> tuple[str, str, str]:
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
                    "error": str(exc),
                },
            )
        )
        return "", fallback_report_name, ""
    publisher_name = str(getattr(identity, "publisher_name", "") or "").strip()
    source_report_name = (
        str(getattr(identity, "report_name", "") or "").strip()
        or fallback_report_name
    )
    source_url = str(getattr(identity, "source_url", "") or "").strip()
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
            },
        )
    )
    return publisher_name, source_report_name, source_url


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
) -> IngestOutcome:
    deps = (
        _with_signal_candidate_orchestrator(dependencies)
        if dependencies is not None
        else _default_report_generation_dependencies()
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
        source_openai_client = _build_model_client(
            settings,
            scope="pdf_text_ocr",
            provided_client=source_openai_client,
            openai_ocr_pdf=deps.source.openai_ocr_pdf,
        )
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
    publisher_name, source_report_name, source_url = _resolve_runtime_source_identity(
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
    )
    requested_resume_stage = str(resume_from_stage or "").strip()
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
            payload={"schema_version": "1.0", "outcome": asdict(outcome)},
        )
        if (
            _run_projection(runtime, analysis, outcome, analytics_projection_fn)
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
                payload={"schema_version": "1.0", "outcome": asdict(outcome)},
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
