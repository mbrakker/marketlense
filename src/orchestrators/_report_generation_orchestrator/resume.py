from __future__ import annotations
from dataclasses import asdict, replace
from datetime import datetime, timezone
import logging
from typing import Callable, Optional
from urllib.parse import urlsplit
from src.contracts.analytics_projection import (
    AnalyticsProjectionRunRequest,
    PROJECTION_SCHEMA_VERSION,
)
from src.contracts.report_analysis import AnalysisStorePackRequest
from src.contracts.files import (
    PipelineCheckpointReadRequest,
)
from src.contracts.ingest import IngestOutcome
from src.contracts.report_generation import (
    ReportAnalysisState,
    ReportRuntimeState,
)
from src.contracts.semantic_ids import ReportId
from src.contracts.report_store import (
    ReportMetadataGetRequest,
    ReportMetadataUpsertRequest,
    ReportSourceRecordRequest,
    ReportValueScoreRecordRequest,
    ReportValueScoreRequest,
    ReportValueScoreResponse,
)
from src.contracts.vector_store import VectorStoreDeleteRequest
from src.generators.report_generation_dependencies import ReportGenerationDependencies
from src.generators.report_render_generator import (
    render_report_output,
)
from src.generators.report_signal_artifact_generator import (
    SIGNAL_ARTIFACT_PACK_NAME,
    build_ingestion_signal_artifact_payload,
    build_ingestion_signal_extraction_request,
    planned_signal_artifact_path,
)
from src.orchestrators.analytics_projection_orchestrator import run_analytics_projection
from src.services.file_service import (
    read_pipeline_checkpoint,
)
from src.utils.errors import AppError
from src.utils.logging import child_context, log_event

from .checkpoints import (
    _analysis_state_from_checkpoint,
    _preview_from_checkpoint,
    _render_checkpoint_refs,
    _selection_state_from_checkpoint,
    _source_state_from_checkpoint,
    _write_stage_checkpoint,
)

logger = logging.getLogger("market_lense.report_generation_orchestrator")
REPORT_PIPELINE_NAME = "report_generation"
STAGE_SOURCE_PREPARED = "source_prepared"
STAGE_SELECTION_COMPLETE = "selection_complete"
STAGE_ANALYSIS_COMPLETE = "analysis_complete"
STAGE_RENDER_COMPLETE = "render_complete"


def _run_projection(
    runtime: ReportRuntimeState,
    analysis: ReportAnalysisState,
    outcome: IngestOutcome,
    analytics_projection_fn: Optional[
        Callable[[AnalyticsProjectionRunRequest], object]
    ],
) -> object | None:
    project = analytics_projection_fn or run_analytics_projection
    try:
        return project(
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
    return None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _utc_now_year() -> int:
    return datetime.now(timezone.utc).year


def _source_domain_for_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    return (parsed.hostname or "").lower()


def _drive_file_landing_url(file_id: str) -> str:
    clean_file_id = str(file_id or "").strip()
    if not clean_file_id:
        return ""
    return f"https://drive.google.com/file/d/{clean_file_id}/view"


def _first_nonempty(*values: object) -> str:
    for value in values:
        token = str(value or "").strip()
        if token:
            return token
    return ""


def _score_ingested_report_source(
    runtime: ReportRuntimeState,
    analysis: ReportAnalysisState,
    dependencies: ReportGenerationDependencies,
) -> ReportValueScoreResponse | None:
    score_ctx = child_context(
        runtime.ctx, task_id=f"{runtime.ctx.task_id}:report_source_score"
    )
    dependencies.render.upsert_report_metadata(
        ReportMetadataUpsertRequest(
            schema_version="1.1",
            db_path=runtime.settings.reports_db,
            file_id=runtime.file.file_id,
            title=analysis.payload.title or runtime.report_title,
            file_name=runtime.file_name,
            publisher=analysis.payload.publisher or None,
            taxonomy=analysis.payload.taxonomy,
            categories=analysis.payload.categories,
            region=analysis.payload.region or None,
            time_period=analysis.payload.time_period or None,
            source_url=analysis.payload.source,
            html_path=None,
            md5=runtime.md5,
            page_count=None,
            contents_page_number=analysis.payload.contents_page_number,
            pdf_metadata={},
            analysis_mode=runtime.analysis_mode,
            vector_store_id=analysis.vector_store_id,
            evidence_pack_paths=analysis.evidence_paths,
        ),
        score_ctx,
    )
    report_metadata = dependencies.render.get_report_metadata(
        ReportMetadataGetRequest(
            schema_version="1.0",
            db_path=runtime.settings.reports_db,
            file_id=runtime.file.file_id,
        ),
        score_ctx,
    )
    title = _first_nonempty(
        getattr(report_metadata, "title", ""),
        analysis.normalized_payload.title,
        analysis.payload.title,
        runtime.report_title,
    )
    publisher_name = _first_nonempty(
        getattr(report_metadata, "publisher", ""),
        analysis.normalized_payload.publisher,
        analysis.payload.publisher,
    )
    landing_page_url = _first_nonempty(
        getattr(report_metadata, "source_url", ""),
        analysis.normalized_payload.source,
        analysis.payload.source,
    )
    source_url_fallback = ""
    if not landing_page_url:
        landing_page_url = _drive_file_landing_url(runtime.file.file_id)
        source_url_fallback = "drive_file_url" if landing_page_url else ""
    md5 = _first_nonempty(getattr(report_metadata, "md5", ""), runtime.md5)
    source_domain = _source_domain_for_url(landing_page_url)
    if not landing_page_url or not source_domain or not md5:
        logger.info(
            log_event(
                score_ctx,
                role="orchestrator",
                event="report_source_value_score_skipped",
                module=logger.name,
                fields={
                    "file_id": runtime.file.file_id,
                    "has_landing_page_url": bool(landing_page_url),
                    "has_source_domain": bool(source_domain),
                    "has_md5": bool(md5),
                    "source_url_fallback": source_url_fallback,
                },
            )
        )
        return None
    downloaded_at_utc = _utc_now_iso()
    source_record = dependencies.source_scoring.record_report_source(
        ReportSourceRecordRequest(
            schema_version="1.0",
            db_path=runtime.settings.reports_db,
            source_domain=source_domain,
            report_name=title,
            landing_page_url=landing_page_url,
            downloaded_at_utc=downloaded_at_utc,
            md5=md5,
            publisher_name=publisher_name,
            source_page_url="",
        ),
        score_ctx,
    )
    report_value_score = dependencies.source_scoring.score_report_value(
        ReportValueScoreRequest(
            schema_version="1.0",
            publisher_name=publisher_name,
            source_domain=source_record.source_domain,
            report_name=source_record.report_name,
            landing_page_url=source_record.landing_page_url,
            source_page_url=landing_page_url,
            source_status="downloaded",
            discovered_at_utc="",
            downloaded_at_utc=source_record.downloaded_at_utc,
            md5=source_record.md5,
            evaluation_year=_utc_now_year(),
        ),
        score_ctx,
    )
    dependencies.source_scoring.record_report_value_score(
        ReportValueScoreRecordRequest(
            schema_version="1.0",
            db_path=runtime.settings.reports_db,
            record_id=source_record.record_id,
            score=report_value_score,
            scored_at_utc=_utc_now_iso(),
        ),
        score_ctx,
    )
    logger.info(
        log_event(
            score_ctx,
            role="orchestrator",
            event="report_source_value_scored",
            module=logger.name,
            fields={
                "file_id": runtime.file.file_id,
                "record_id": source_record.record_id,
                "publisher_name": publisher_name,
                "landing_page_url": source_record.landing_page_url,
                "source_url_fallback": source_url_fallback,
                "overall_score": report_value_score.overall_score,
                "value_band": report_value_score.value_band,
                "component_scores": {
                    component.dimension: component.score
                    for component in report_value_score.components
                },
            },
        )
    )
    return report_value_score


def _analysis_with_report_value_score(
    analysis: ReportAnalysisState,
    report_value_score: ReportValueScoreResponse | None,
) -> ReportAnalysisState:
    if report_value_score is None:
        return analysis
    render_data = dict(analysis.data_dict)
    render_data["_report_value_score"] = asdict(report_value_score)
    return replace(analysis, data_dict=render_data)


def _run_signal_artifact_generation(
    runtime: ReportRuntimeState,
    analysis: ReportAnalysisState,
    outcome: IngestOutcome,
    dependencies: ReportGenerationDependencies,
) -> IngestOutcome:
    signal_ctx = child_context(runtime.ctx, task_id=f"{runtime.ctx.task_id}:signals")
    extraction_request = build_ingestion_signal_extraction_request(runtime, analysis)
    logger.info(
        log_event(
            signal_ctx,
            role="orchestrator",
            event="report_signal_artifact_start",
            module=logger.name,
            fields={
                "file_id": runtime.file.file_id,
                "reports_db": extraction_request.projected_data_request.db_path,
                "signal_store_db": extraction_request.db_path,
                "extraction_request_id": extraction_request.extraction_request_id,
            },
        )
    )
    extraction = dependencies.signal.run_signal_candidate_extraction(
        extraction_request,
        signal_ctx,
    )
    artifact_path = planned_signal_artifact_path(runtime)
    payload = build_ingestion_signal_artifact_payload(
        runtime,
        analysis,
        extraction,
        artifact_path=artifact_path,
    )
    stored = dependencies.signal.analysis_store_pack(
        AnalysisStorePackRequest(
            schema_version="1.0",
            output_dir=runtime.settings.output_dir,
            report_id=ReportId(runtime.file.file_id),
            pack_name=SIGNAL_ARTIFACT_PACK_NAME,
            payload=payload,
            report_slug=runtime.report_name,
        ),
        signal_ctx,
    )
    stored_path = str(getattr(stored, "output_path", "") or artifact_path)
    evidence_packs = dict(outcome.evidence_packs or {})
    evidence_packs[SIGNAL_ARTIFACT_PACK_NAME] = stored_path
    logger.info(
        log_event(
            signal_ctx,
            role="orchestrator",
            event="report_signal_artifact_complete",
            module=logger.name,
            fields={
                "file_id": runtime.file.file_id,
                "artifact_path": stored_path,
                "candidate_count": extraction.candidate_count,
                "group_count": extraction.group_count,
                "signal_store_db": extraction_request.db_path,
            },
        )
    )
    return replace(outcome, evidence_packs=evidence_packs)


def _resume_from_analysis_checkpoint(
    runtime: ReportRuntimeState,
    dependencies: ReportGenerationDependencies,
    analytics_projection_fn: Optional[
        Callable[[AnalyticsProjectionRunRequest], object]
    ],
) -> IngestOutcome:
    response = read_pipeline_checkpoint(
        PipelineCheckpointReadRequest(
            schema_version="1.0",
            checkpoint_root=runtime.settings.output_dir,
            pipeline_name=REPORT_PIPELINE_NAME,
            file_id=runtime.file.file_id,
            stage_name=STAGE_ANALYSIS_COMPLETE,
        ),
        runtime.ctx,
    )
    if not response.found or response.checkpoint is None:
        raise AppError(
            code="report_pipeline_checkpoint_missing",
            message="Requested report pipeline checkpoint was not found",
            retryable=False,
            context={
                "file_id": runtime.file.file_id,
                "stage_name": STAGE_ANALYSIS_COMPLETE,
                "checkpoint_path": response.checkpoint_path,
            },
        )
    checkpoint_payload = response.checkpoint.payload
    logger.info(
        log_event(
            runtime.ctx,
            role="orchestrator",
            event="report_pipeline_semantic_restart",
            module=logger.name,
            fields={
                "file_id": runtime.file.file_id,
                "stage_name": STAGE_ANALYSIS_COMPLETE,
                "checkpoint_path": response.checkpoint_path,
                "artifact_ref_count": len(response.checkpoint.artifact_refs),
            },
        )
    )
    source = _source_state_from_checkpoint(runtime, checkpoint_payload.get("source"))
    selection = _selection_state_from_checkpoint(
        runtime, source, checkpoint_payload.get("selection")
    )
    analysis = _analysis_state_from_checkpoint(
        runtime, source, selection, checkpoint_payload.get("analysis")
    )
    preview_resp = _preview_from_checkpoint(checkpoint_payload.get("preview"))
    report_value_score = _score_ingested_report_source(runtime, analysis, dependencies)
    analysis = _analysis_with_report_value_score(analysis, report_value_score)
    outcome = render_report_output(
        runtime,
        source,
        selection,
        analysis,
        dependencies.render,
        preview_resp=preview_resp,
    )
    _write_stage_checkpoint(
        runtime,
        stage_name=STAGE_RENDER_COMPLETE,
        artifact_refs={
            **dict(response.checkpoint.artifact_refs),
            **_render_checkpoint_refs(
                runtime,
                source,
                analysis,
                preview_resp,
                outcome,
            ),
        },
        payload={"schema_version": "1.0", "outcome": asdict(outcome)},
    )
    if _run_projection(runtime, analysis, outcome, analytics_projection_fn) is not None:
        outcome = _run_signal_artifact_generation(
            runtime,
            analysis,
            outcome,
            dependencies,
        )
        _write_stage_checkpoint(
            runtime,
            stage_name=STAGE_RENDER_COMPLETE,
            artifact_refs={
                **dict(response.checkpoint.artifact_refs),
                **_render_checkpoint_refs(
                    runtime,
                    source,
                    analysis,
                    preview_resp,
                    outcome,
                ),
            },
            payload={"schema_version": "1.0", "outcome": asdict(outcome)},
        )
    return _cleanup_transient_vector_store(outcome, runtime, dependencies)


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
            fields={
                "file_id": runtime.file.file_id,
                "vector_store_id": vector_store_id,
            },
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


__all__ = [
    "_run_projection",
    "_utc_now_iso",
    "_utc_now_year",
    "_source_domain_for_url",
    "_drive_file_landing_url",
    "_first_nonempty",
    "_score_ingested_report_source",
    "_analysis_with_report_value_score",
    "_run_signal_artifact_generation",
    "_resume_from_analysis_checkpoint",
    "_pdf_text_unextractable_outcome",
    "_pdf_text_ocr_failed_outcome",
    "_doc_map_empty_outcome",
    "_cleanup_transient_vector_store",
]
