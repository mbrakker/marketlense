from __future__ import annotations

import logging
from typing import Callable, Optional
from dataclasses import replace

from src.contracts.analytics_projection import (
    AnalyticsProjectionRunRequest,
    PROJECTION_SCHEMA_VERSION,
)
from src.contracts.drive import DriveFile
from src.contracts.ingest import IngestOutcome, IngestSettings
from src.contracts.report_generation import ReportRuntimeState
from src.contracts.run_context import RunContext
from src.contracts.vector_store import VectorStoreDeleteRequest
from src.generators.report_analysis_generator import start_vector_store_indexing
from src.generators.report_generation_dependencies import ReportGenerationDependencies
from src.generators.report_generation_shared import derive_title, report_slug
from src.generators.report_render_generator import (
    render_preview_asset,
    render_report_output,
)
from src.generators.report_selection_generator import select_report_figures
from src.generators.report_source_generator import prepare_report_source
from src.orchestrators.analytics_projection_orchestrator import run_analytics_projection
from src.orchestrators.report_analysis_orchestrator import run_report_analysis
from src.utils.errors import AppError
from src.utils.logging import child_context, log_event

logger = logging.getLogger("market_lense.report_generation_orchestrator")


def _build_runtime_state(
    file: DriveFile,
    local_pdf_path: str,
    settings: IngestSettings,
    md5: Optional[str],
    ctx: RunContext,
) -> ReportRuntimeState:
    report_worker_limit = getattr(settings, "report_worker_limit", 1)
    try:
        report_worker_limit = int(report_worker_limit)
    except (TypeError, ValueError):
        report_worker_limit = 1
    if report_worker_limit < 1:
        report_worker_limit = 1
    file_name = file.name or file.file_id
    return ReportRuntimeState(
        schema_version="1.0",
        file=file,
        local_pdf_path=local_pdf_path,
        settings=settings,
        md5=md5,
        ctx=ctx,
        file_name=file_name,
        report_name=report_slug(file_name, file.file_id),
        report_title=derive_title(file_name),
        analysis_mode="vector_store",
        analysis_modes=["vector_store"],
        report_worker_limit=report_worker_limit,
        parallel_within_file=report_worker_limit > 1,
    )


def _pdf_text_unextractable_outcome(
    runtime: ReportRuntimeState,
    exc: AppError,
) -> IngestOutcome:
    context = exc.context if isinstance(exc.context, dict) else {}
    return IngestOutcome(
        schema_version="1.0",
        file_id=runtime.file.file_id,
        name=runtime.file_name,
        md5=runtime.md5,
        html_path=None,
        status="error",
        error="pdf_text_unextractable",
        text_validation_status=str(context.get("text_validation_status") or "fail"),
        text_validation_reason=str(
            context.get("text_validation_reason") or "pdf_text_unextractable"
        ),
        text_validation_pages=list(context.get("text_validation_pages") or []),
    )


def _pdf_text_ocr_failed_outcome(
    runtime: ReportRuntimeState,
    exc: AppError,
) -> IngestOutcome:
    context = exc.context if isinstance(exc.context, dict) else {}
    return IngestOutcome(
        schema_version="1.0",
        file_id=runtime.file.file_id,
        name=runtime.file_name,
        md5=runtime.md5,
        html_path=None,
        status="error",
        error="pdf_text_ocr_failed",
        text_validation_status=str(context.get("text_validation_status") or "fail"),
        text_validation_reason=str(
            context.get("text_validation_reason") or "pdf_text_ocr_failed"
        ),
        text_validation_pages=list(context.get("text_validation_pages") or []),
        ocr_fallback_used=True,
        ocr_pdf_path=str(context.get("ocr_pdf_path") or "") or None,
    )


def _doc_map_empty_outcome(
    runtime: ReportRuntimeState,
    source,
    vector_state,
    exc: AppError,
) -> IngestOutcome:
    doc_map_summary = exc.context if isinstance(exc.context, dict) else None
    return IngestOutcome(
        schema_version="1.0",
        file_id=runtime.file.file_id,
        name=runtime.file_name,
        md5=runtime.md5,
        html_path=None,
        status="error",
        error=exc.message or exc.code,
        vector_store_id=vector_state.vector_store_id,
        vector_store_status=vector_state.vector_store_status,
        indexed_at_utc=vector_state.indexed_at_utc,
        openai_file_id=vector_state.openai_file_id,
        vector_store_last_error=vector_state.last_error,
        text_validation_status=source.text_validation_status,
        text_validation_reason=source.text_validation_reason,
        text_validation_pages=source.text_validation_pages,
        doc_map_summary=doc_map_summary,
        ocr_fallback_used=source.ocr_fallback_used,
        ocr_pdf_path=source.ocr_pdf_path or None,
    )


def _cleanup_transient_vector_store(
    outcome: IngestOutcome,
    runtime: ReportRuntimeState,
    dependencies: ReportGenerationDependencies,
) -> IngestOutcome:
    vector_store_id = str(outcome.vector_store_id or "").strip()
    if runtime.settings.vector_store_keep or not vector_store_id:
        return outcome
    cleanup_ctx = child_context(
        runtime.ctx, task_id=f"{runtime.ctx.task_id}:vector_store_cleanup"
    )
    logger.info(
        log_event(
            cleanup_ctx,
            role="orchestrator",
            event="vector_store_cleanup_retention_disabled_start",
            module=logger.name,
            fields={"file_id": runtime.file.file_id, "vector_store_id": vector_store_id},
        )
    )
    response = dependencies.analysis.vector_store_delete(
        VectorStoreDeleteRequest(
            schema_version="1.0",
            vector_store_id=vector_store_id,
            missing_ok=True,
        ),
        cleanup_ctx,
    )
    logger.info(
        log_event(
            cleanup_ctx,
            role="orchestrator",
            event="vector_store_cleanup_retention_disabled_complete",
            module=logger.name,
            fields={
                "file_id": runtime.file.file_id,
                "vector_store_id": vector_store_id,
                "deleted": bool(response.deleted),
                "missing_remote": bool(response.missing_remote),
            },
        )
    )
    return replace(
        outcome,
        vector_store_id=None,
        vector_store_status="deleted",
        vector_store_last_error=None,
    )


def run_report_generation(
    file: DriveFile,
    local_pdf_path: str,
    settings: IngestSettings,
    md5: Optional[str],
    ctx: RunContext,
    *,
    evidence_pack_openai_client=None,
    artifact_openai_client=None,
    dependencies: Optional[ReportGenerationDependencies] = None,
    analytics_projection_fn: Optional[
        Callable[[AnalyticsProjectionRunRequest], object]
    ] = None,
) -> IngestOutcome:
    deps = dependencies or ReportGenerationDependencies.default()
    runtime = _build_runtime_state(file, local_pdf_path, settings, md5, ctx)
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
        source = prepare_report_source(runtime, deps.source)
        vector_state = start_vector_store_indexing(runtime, source, deps.analysis)
        selection = select_report_figures(runtime, source, deps.selection)
        preview_resp = render_preview_asset(runtime, source, deps.render)
        analysis = run_report_analysis(
            runtime,
            source,
            selection,
            vector_state,
            deps.analysis,
            evidence_pack_openai_client=evidence_pack_openai_client,
            artifact_openai_client=artifact_openai_client,
        )
        outcome = render_report_output(
            runtime,
            source,
            selection,
            analysis,
            deps.render,
            preview_resp=preview_resp,
        )
        project = analytics_projection_fn or run_analytics_projection
        try:
            project(
                AnalyticsProjectionRunRequest(
                    schema_version=PROJECTION_SCHEMA_VERSION,
                    db_path=runtime.settings.reports_db,
                    analysis=analysis,
                    rendered_html_path=outcome.html_path or "",
                    ctx=runtime.ctx,
                )
            )
        except AppError as projection_error:
            logger.error(
                log_event(
                    runtime.ctx,
                    role="orchestrator",
                    event="analytics_projection_failed_nonblocking",
                    module=logger.name,
                    fields={
                        "file_id": runtime.file.file_id,
                        "error_code": projection_error.code,
                        "error_retryable": projection_error.retryable,
                        "error_message": projection_error.message,
                    },
                )
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
