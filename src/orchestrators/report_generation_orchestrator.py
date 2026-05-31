from __future__ import annotations

from dataclasses import asdict, replace
from datetime import datetime, timezone
import logging
from typing import Callable, Optional

from src.contracts.analytics_projection import (
    AnalyticsProjectionRunRequest,
    PROJECTION_SCHEMA_VERSION,
)
from src.contracts.drive import DriveFile
from src.contracts.files import (
    PipelineCheckpointReadRequest,
    PipelineCheckpointWriteRequest,
    PipelineStageCheckpoint,
)
from src.contracts.ingest import IngestOutcome, IngestSettings
from src.contracts.pdf_text import PdfTextExtractResponse
from src.contracts.pdf_utils import PdfInfoResponse
from src.contracts.regeneration import (
    RegenerationAttemptResult,
    RegenerationLoopState,
)
from src.contracts.report_assets import PreviewResponse
from src.contracts.report_generation import (
    ReportAnalysisState,
    ReportRuntimeState,
    ReportSelectionState,
    ReportSourceState,
)
from src.contracts.report_models import Figure, Quote, ReportFigureAsset, ReportPayload
from src.contracts.run_context import RunContext
from src.contracts.validation import ValidationIssue, ValidationReport
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
from src.services.file_service import (
    read_pipeline_checkpoint,
    write_pipeline_checkpoint,
)
from src.utils.errors import AppError
from src.utils.logging import child_context, log_event

logger = logging.getLogger("market_lense.report_generation_orchestrator")

REPORT_PIPELINE_NAME = "report_generation"
STAGE_SOURCE_PREPARED = "source_prepared"
STAGE_SELECTION_COMPLETE = "selection_complete"
STAGE_ANALYSIS_COMPLETE = "analysis_complete"
STAGE_RENDER_COMPLETE = "render_complete"


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


def _report_payload_from_dict(raw_payload: object) -> ReportPayload:
    if not isinstance(raw_payload, dict):
        raise AppError(
            code="report_pipeline_checkpoint_invalid",
            message="Checkpoint report payload must be an object",
            retryable=False,
        )
    try:
        quote_payload = raw_payload["quote"]
        figure_payload = raw_payload["figure"]
        if not isinstance(quote_payload, dict) or not isinstance(figure_payload, dict):
            raise TypeError("quote and figure must be objects")
        figure_assets: list[ReportFigureAsset] = []
        for raw_asset in raw_payload.get("_figure_assets", []):
            if not isinstance(raw_asset, dict):
                raise TypeError("figure asset must be an object")
            figure_assets.append(
                ReportFigureAsset(
                    image_path=str(raw_asset["image_path"]),
                    page=int(raw_asset["page"]),
                    candidate_id=str(raw_asset["candidate_id"]),
                    kind=str(raw_asset["kind"]),
                    is_primary=bool(raw_asset["is_primary"]),
                    detected_caption=str(raw_asset.get("detected_caption") or ""),
                    preview_text=str(raw_asset.get("preview_text") or ""),
                    generated_caption=str(raw_asset.get("generated_caption") or ""),
                    display_caption=str(raw_asset.get("display_caption") or ""),
                    caption_source=str(raw_asset.get("caption_source") or ""),
                    schema_version=str(raw_asset.get("schema_version") or "1.0"),
                )
            )
        return ReportPayload(
            tldr=str(raw_payload["tldr"]),
            title=str(raw_payload["title"]),
            insights=[str(item) for item in raw_payload["insights"]],
            quote=Quote(
                text=str(quote_payload["text"]),
                author=str(quote_payload.get("author") or "Unknown"),
                schema_version=str(quote_payload.get("schema_version") or "1.0"),
            ),
            figure=Figure(
                title=str(figure_payload["title"]),
                evidence=str(figure_payload["evidence"]),
                schema_version=str(figure_payload.get("schema_version") or "1.0"),
            ),
            commentary=str(raw_payload["commentary"]),
            source=str(raw_payload["source"]),
            publisher=str(raw_payload.get("publisher") or ""),
            taxonomy=[str(item) for item in raw_payload.get("taxonomy", [])],
            categories=[str(item) for item in raw_payload.get("categories", [])],
            region=str(raw_payload.get("region") or ""),
            time_period=str(raw_payload.get("time_period") or ""),
            contents_page_number=int(raw_payload.get("contents_page_number") or 0),
            contents_heading=str(raw_payload.get("contents_heading") or ""),
            _figure_image=str(raw_payload.get("_figure_image") or ""),
            _figure_gallery=[
                str(item) for item in raw_payload.get("_figure_gallery", [])
            ],
            _figure_top=str(raw_payload.get("_figure_top") or ""),
            _figure_assets=figure_assets,
            _figure_section_enabled=bool(
                raw_payload.get("_figure_section_enabled", True)
            ),
            _contents_image=str(raw_payload.get("_contents_image") or ""),
            _vector_store_id=str(raw_payload.get("_vector_store_id") or ""),
            _evidence_packs=dict(raw_payload.get("_evidence_packs") or {}),
            _text_density=float(raw_payload.get("_text_density") or 0.0),
            _text_pages_sampled=int(raw_payload.get("_text_pages_sampled") or 0),
            _text_char_count=int(raw_payload.get("_text_char_count") or 0),
            _text_not_available=bool(raw_payload.get("_text_not_available", False)),
            schema_version=str(raw_payload.get("schema_version") or "1.1"),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise AppError(
            code="report_pipeline_checkpoint_invalid",
            message="Checkpoint report payload is incomplete",
            cause=exc,
            retryable=False,
        ) from exc


def _validation_report_from_dict(raw_report: object) -> Optional[ValidationReport]:
    if raw_report is None:
        return None
    if not isinstance(raw_report, dict):
        raise AppError(
            code="report_pipeline_checkpoint_invalid",
            message="Checkpoint validation report must be an object",
            retryable=False,
        )
    issues: list[ValidationIssue] = []
    for raw_issue in raw_report.get("issues", []):
        if not isinstance(raw_issue, dict):
            raise AppError(
                code="report_pipeline_checkpoint_invalid",
                message="Checkpoint validation issue must be an object",
                retryable=False,
            )
        issues.append(
            ValidationIssue(
                message=str(raw_issue["message"]),
                severity=str(raw_issue["severity"]),
                affected_section=str(raw_issue["affected_section"]),
                rule_id=str(raw_issue.get("rule_id") or ""),
                repair_target=str(raw_issue.get("repair_target") or ""),
                entity_id=str(raw_issue.get("entity_id") or ""),
                schema_version=str(raw_issue.get("schema_version") or "1.0"),
            )
        )
    return ValidationReport(
        schema_version=str(raw_report["schema_version"]),
        status=str(raw_report["status"]),
        issues=issues,
        severity=str(raw_report.get("severity") or "pass"),
        source_path=str(raw_report.get("source_path") or ""),
    )


def _regeneration_loop_from_dict(raw_state: object) -> Optional[RegenerationLoopState]:
    if raw_state is None:
        return None
    if not isinstance(raw_state, dict):
        raise AppError(
            code="report_pipeline_checkpoint_invalid",
            message="Checkpoint regeneration loop state must be an object",
            retryable=False,
        )
    return RegenerationLoopState(
        attempt_count=int(raw_state["attempt_count"]),
        max_attempts=int(raw_state["max_attempts"]),
        final_status=str(raw_state["final_status"]),
        max_reached=bool(raw_state["max_reached"]),
        schema_version=str(raw_state.get("schema_version") or "1.0"),
    )


def _regeneration_attempts_from_list(
    raw_attempts: object,
) -> list[RegenerationAttemptResult]:
    if raw_attempts is None:
        return []
    if not isinstance(raw_attempts, list):
        raise AppError(
            code="report_pipeline_checkpoint_invalid",
            message="Checkpoint regeneration attempts must be a list",
            retryable=False,
        )
    attempts: list[RegenerationAttemptResult] = []
    for raw_attempt in raw_attempts:
        if not isinstance(raw_attempt, dict):
            raise AppError(
                code="report_pipeline_checkpoint_invalid",
                message="Checkpoint regeneration attempt must be an object",
                retryable=False,
            )
        attempts.append(
            RegenerationAttemptResult(
                attempt_index=int(raw_attempt["attempt_index"]),
                plan_mode=str(raw_attempt["plan_mode"]),
                validation_before_status=str(raw_attempt["validation_before_status"]),
                validation_after_status=str(raw_attempt["validation_after_status"]),
                regenerated_sections=[
                    str(item) for item in raw_attempt.get("regenerated_sections", [])
                ],
                artifacts_path=str(raw_attempt.get("artifacts_path") or ""),
                artifacts_snapshot_path=str(
                    raw_attempt.get("artifacts_snapshot_path") or ""
                ),
                validation_path=str(raw_attempt.get("validation_path") or ""),
                validation_snapshot_path=str(
                    raw_attempt.get("validation_snapshot_path") or ""
                ),
                schema_version=str(raw_attempt.get("schema_version") or "1.0"),
            )
        )
    return attempts


def _write_stage_checkpoint(
    runtime: ReportRuntimeState,
    *,
    stage_name: str,
    artifact_refs: dict[str, str],
    payload: dict,
) -> str:
    response = write_pipeline_checkpoint(
        PipelineCheckpointWriteRequest(
            schema_version="1.0",
            checkpoint_root=runtime.settings.output_dir,
            checkpoint=PipelineStageCheckpoint(
                schema_version="1.0",
                pipeline_name=REPORT_PIPELINE_NAME,
                file_id=runtime.file.file_id,
                report_slug=runtime.report_name,
                stage_name=stage_name,
                stage_status="completed",
                artifact_refs=dict(artifact_refs),
                payload=payload,
                completed_at_utc=datetime.now(timezone.utc).isoformat(),
                source_run_id=str(runtime.ctx.run_id),
                source_task_id=str(runtime.ctx.task_id),
            ),
        ),
        runtime.ctx,
    )
    logger.info(
        log_event(
            runtime.ctx,
            role="orchestrator",
            event="report_pipeline_checkpoint_recorded",
            module=logger.name,
            fields={
                "file_id": runtime.file.file_id,
                "stage_name": stage_name,
                "checkpoint_path": response.checkpoint_path,
                "artifact_ref_count": len(artifact_refs),
            },
        )
    )
    return response.checkpoint_path


def _source_checkpoint_payload(source: ReportSourceState) -> dict:
    return {
        "schema_version": "1.0",
        "info_response": _source_info_payload(source),
        "contents_page_number": source.contents_page_number,
        "contents_heading": source.contents_heading,
        "contents_image": source.contents_image,
        "text_response": _source_text_payload(source),
        "text_status": dict(source.text_status),
        "text_validation_status": source.text_validation_status,
        "text_validation_reason": source.text_validation_reason,
        "text_validation_pages": list(source.text_validation_pages),
        "payload": source.payload.to_dict(),
        "analysis_pdf_path": source.analysis_pdf_path,
        "ocr_fallback_used": source.ocr_fallback_used,
        "ocr_pdf_path": source.ocr_pdf_path,
    }


def _selection_checkpoint_payload(selection: ReportSelectionState) -> dict:
    return {
        "schema_version": "1.0",
        "payload": selection.payload.to_dict(),
        "rank_usage": dict(selection.rank_usage),
        "candidate_count": selection.candidate_count,
    }


def _source_info_payload(source: ReportSourceState) -> dict:
    info = source.info_response
    return {
        "schema_version": str(getattr(info, "schema_version", "1.0")),
        "path": str(getattr(info, "path", source.runtime.local_pdf_path)),
        "page_count": int(getattr(info, "page_count", 0) or 0),
        "metadata": dict(getattr(info, "metadata", {}) or {}),
    }


def _source_text_payload(source: ReportSourceState) -> dict:
    text = source.text_response
    return {
        "schema_version": str(getattr(text, "schema_version", "1.0")),
        "text": str(getattr(text, "text", "") or ""),
        "pages_extracted": int(getattr(text, "pages_extracted", 0) or 0),
        "char_count": int(getattr(text, "char_count", 0) or 0),
        "text_density": float(getattr(text, "text_density", 0.0) or 0.0),
    }


def _preview_checkpoint_payload(preview_resp) -> dict:
    return {
        "schema_version": getattr(preview_resp, "schema_version", "1.1"),
        "image_path": str(getattr(preview_resp, "image_path", "") or ""),
        "page_number": int(getattr(preview_resp, "page_number", 0) or 0),
    }


def _analysis_checkpoint_payload(
    source: ReportSourceState,
    selection: ReportSelectionState,
    analysis: ReportAnalysisState,
    preview_resp,
) -> dict:
    validation_report = (
        analysis.validation_report.to_dict() if analysis.validation_report else None
    )
    return {
        "schema_version": "1.0",
        "source": _source_checkpoint_payload(source),
        "selection": _selection_checkpoint_payload(selection),
        "preview": _preview_checkpoint_payload(preview_resp),
        "analysis": {
            "schema_version": analysis.schema_version,
            "payload": analysis.payload.to_dict(),
            "normalized_payload": analysis.normalized_payload.to_dict(),
            "data_dict": dict(analysis.data_dict),
            "evidence_paths": dict(analysis.evidence_paths),
            "evidence_packs": dict(analysis.evidence_packs),
            "artifacts_payload": analysis.artifacts_payload,
            "validation_report": validation_report,
            "category_labels": list(analysis.category_labels),
            "vector_store_id": analysis.vector_store_id,
            "vector_store_status": analysis.vector_store_status,
            "indexed_at_utc": analysis.indexed_at_utc,
            "openai_file_id": analysis.openai_file_id,
            "last_error": analysis.last_error,
            "regeneration_loop_state": asdict(analysis.regeneration_loop_state)
            if analysis.regeneration_loop_state
            else None,
            "regeneration_attempts": [
                asdict(attempt) for attempt in analysis.regeneration_attempts
            ],
        },
    }


def _analysis_checkpoint_refs(
    runtime: ReportRuntimeState,
    source: ReportSourceState,
    analysis: ReportAnalysisState,
    preview_resp,
) -> dict[str, str]:
    refs = {
        "source_pdf": runtime.local_pdf_path,
        "analysis_pdf": source.analysis_pdf_path or runtime.local_pdf_path,
        "preview_image": str(getattr(preview_resp, "image_path", "") or ""),
    }
    refs.update(
        {str(key): str(value) for key, value in analysis.evidence_paths.items()}
    )
    return {key: value for key, value in refs.items() if value}


def _source_state_from_checkpoint(
    runtime: ReportRuntimeState,
    raw_source: object,
) -> ReportSourceState:
    if not isinstance(raw_source, dict):
        raise AppError(
            code="report_pipeline_checkpoint_invalid",
            message="Checkpoint source state must be an object",
            retryable=False,
        )
    info_raw = raw_source.get("info_response")
    text_raw = raw_source.get("text_response")
    if not isinstance(info_raw, dict) or not isinstance(text_raw, dict):
        raise AppError(
            code="report_pipeline_checkpoint_invalid",
            message="Checkpoint source info/text state is incomplete",
            retryable=False,
        )
    return ReportSourceState(
        schema_version="1.0",
        runtime=runtime,
        info_response=PdfInfoResponse(
            schema_version=str(info_raw["schema_version"]),
            path=str(info_raw["path"]),
            page_count=int(info_raw["page_count"]),
            metadata={
                str(k): str(v) for k, v in dict(info_raw.get("metadata") or {}).items()
            },
        ),
        contents_page_number=int(raw_source["contents_page_number"]),
        contents_heading=str(raw_source["contents_heading"]),
        contents_image=str(raw_source["contents_image"]),
        text_response=PdfTextExtractResponse(
            schema_version=str(text_raw["schema_version"]),
            text=str(text_raw["text"]),
            pages_extracted=int(text_raw["pages_extracted"]),
            char_count=int(text_raw["char_count"]),
            text_density=float(text_raw.get("text_density") or 0.0),
        ),
        text_status=dict(raw_source["text_status"]),
        text_validation_status=str(raw_source["text_validation_status"]),
        text_validation_reason=str(raw_source["text_validation_reason"]),
        text_validation_pages=[
            int(item) for item in raw_source["text_validation_pages"]
        ],
        payload=_report_payload_from_dict(raw_source["payload"]),
        analysis_pdf_path=str(raw_source.get("analysis_pdf_path") or ""),
        ocr_fallback_used=bool(raw_source.get("ocr_fallback_used", False)),
        ocr_pdf_path=str(raw_source.get("ocr_pdf_path") or ""),
        pdf_context=None,
        pdf_context_for_tasks=None,
    )


def _selection_state_from_checkpoint(
    runtime: ReportRuntimeState,
    source: ReportSourceState,
    raw_selection: object,
) -> ReportSelectionState:
    if not isinstance(raw_selection, dict):
        raise AppError(
            code="report_pipeline_checkpoint_invalid",
            message="Checkpoint selection state must be an object",
            retryable=False,
        )
    return ReportSelectionState(
        schema_version="1.0",
        runtime=runtime,
        source=source,
        payload=_report_payload_from_dict(raw_selection["payload"]),
        rank_usage=dict(raw_selection["rank_usage"]),
        candidate_count=int(raw_selection["candidate_count"]),
    )


def _analysis_state_from_checkpoint(
    runtime: ReportRuntimeState,
    source: ReportSourceState,
    selection: ReportSelectionState,
    raw_analysis: object,
) -> ReportAnalysisState:
    if not isinstance(raw_analysis, dict):
        raise AppError(
            code="report_pipeline_checkpoint_invalid",
            message="Checkpoint analysis state must be an object",
            retryable=False,
        )
    return ReportAnalysisState(
        schema_version=str(raw_analysis["schema_version"]),
        runtime=runtime,
        source=source,
        selection=selection,
        payload=_report_payload_from_dict(raw_analysis["payload"]),
        normalized_payload=_report_payload_from_dict(
            raw_analysis["normalized_payload"]
        ),
        data_dict=dict(raw_analysis["data_dict"]),
        evidence_paths={
            str(k): str(v) for k, v in dict(raw_analysis["evidence_paths"]).items()
        },
        evidence_packs=dict(raw_analysis["evidence_packs"]),
        artifacts_payload=raw_analysis.get("artifacts_payload")
        if isinstance(raw_analysis.get("artifacts_payload"), dict)
        else None,
        validation_report=_validation_report_from_dict(
            raw_analysis.get("validation_report")
        ),
        category_labels=[str(item) for item in raw_analysis.get("category_labels", [])],
        vector_store_id=raw_analysis.get("vector_store_id"),
        vector_store_status=raw_analysis.get("vector_store_status"),
        indexed_at_utc=raw_analysis.get("indexed_at_utc"),
        openai_file_id=raw_analysis.get("openai_file_id"),
        last_error=raw_analysis.get("last_error"),
        regeneration_loop_state=_regeneration_loop_from_dict(
            raw_analysis.get("regeneration_loop_state")
        ),
        regeneration_attempts=_regeneration_attempts_from_list(
            raw_analysis.get("regeneration_attempts")
        ),
    )


def _preview_from_checkpoint(raw_preview: object) -> PreviewResponse:
    if not isinstance(raw_preview, dict):
        raise AppError(
            code="report_pipeline_checkpoint_invalid",
            message="Checkpoint preview state must be an object",
            retryable=False,
        )
    return PreviewResponse(
        schema_version=str(raw_preview.get("schema_version") or "1.1"),
        image_path=str(raw_preview["image_path"]),
        page_number=int(raw_preview["page_number"]),
    )


def _run_projection(
    runtime: ReportRuntimeState,
    analysis: ReportAnalysisState,
    outcome: IngestOutcome,
    analytics_projection_fn: Optional[
        Callable[[AnalyticsProjectionRunRequest], object]
    ],
) -> None:
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
            "rendered_html": outcome.html_path or "",
        },
        payload={"schema_version": "1.0", "outcome": asdict(outcome)},
    )
    _run_projection(runtime, analysis, outcome, analytics_projection_fn)
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
    resume_from_stage: Optional[str] = None,
) -> IngestOutcome:
    deps = dependencies or ReportGenerationDependencies.default()
    runtime = _build_runtime_state(file, local_pdf_path, settings, md5, ctx)
    requested_resume_stage = str(resume_from_stage or "").strip()
    if requested_resume_stage:
        if requested_resume_stage != STAGE_ANALYSIS_COMPLETE:
            raise AppError(
                code="report_pipeline_restart_stage_invalid",
                message="Unsupported report pipeline restart stage",
                retryable=False,
                context={
                    "file_id": runtime.file.file_id,
                    "stage_name": requested_resume_stage,
                    "supported_stages": [STAGE_ANALYSIS_COMPLETE],
                },
            )
        return _resume_from_analysis_checkpoint(
            runtime,
            deps,
            analytics_projection_fn,
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
        source = prepare_report_source(runtime, deps.source)
        _write_stage_checkpoint(
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
        selection = select_report_figures(runtime, source, deps.selection)
        _write_stage_checkpoint(
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
            },
        )
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
        outcome = render_report_output(
            runtime,
            source,
            selection,
            analysis,
            deps.render,
            preview_resp=preview_resp,
        )
        _write_stage_checkpoint(
            runtime,
            stage_name=STAGE_RENDER_COMPLETE,
            artifact_refs={
                **_analysis_checkpoint_refs(runtime, source, analysis, preview_resp),
                "rendered_html": outcome.html_path or "",
            },
            payload={"schema_version": "1.0", "outcome": asdict(outcome)},
        )
        _run_projection(runtime, analysis, outcome, analytics_projection_fn)
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
