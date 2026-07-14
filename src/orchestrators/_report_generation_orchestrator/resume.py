from __future__ import annotations

import logging
from dataclasses import asdict, replace
from datetime import datetime, timezone
from typing import Callable, Optional
from urllib.parse import urlsplit

from src.contracts.analytics_projection import (
    PROJECTION_SCHEMA_VERSION,
    AnalyticsProjectionRunRequest,
)
from src.contracts.artifact_lineage import (
    ARTIFACT_LINEAGE_SCHEMA_VERSION,
    ArtifactReuseCheckRequest,
)
from src.contracts.files import (
    FileStatRequest,
    PipelineCheckpointReadRequest,
    PipelineStageCheckpoint,
)
from src.contracts.ingest import IngestOutcome
from src.contracts.report_analysis import AnalysisStorePackRequest
from src.contracts.report_artifacts import artifact_registry_from_payload
from src.contracts.report_generation import (
    ReportAnalysisState,
    ReportRuntimeState,
)
from src.contracts.report_store import (
    ReportMetadataGetRequest,
    ReportMetadataUpsertRequest,
    ReportSourceRecordRequest,
    ReportValueScoreRecordRequest,
    ReportValueScoreRequest,
    ReportValueScoreResponse,
)
from src.contracts.semantic_ids import ReportId
from src.contracts.vector_store import VectorStoreDeleteRequest
from src.generators.report_analysis_generator import start_vector_store_indexing
from src.generators.report_generation_dependencies import ReportGenerationDependencies
from src.generators.report_render_generator import (
    render_preview_asset,
    render_report_output,
)
from src.generators.report_selection_generator import select_report_figures
from src.generators.report_signal_artifact_generator import (
    SIGNAL_ARTIFACT_PACK_NAME,
    build_ingestion_signal_artifact_payload,
    build_ingestion_signal_extraction_request,
    planned_signal_artifact_path,
)
from src.orchestrators.analytics_projection_orchestrator import run_analytics_projection
from src.orchestrators.report_analysis_orchestrator import run_report_analysis
from src.services.file_service import (
    file_stat,
    read_pipeline_checkpoint,
)
from src.services.report_store_service import check_artifact_reuse
from src.utils.clock import utc_now_iso as _utc_now_iso
from src.utils.errors import AppError
from src.utils.logging import child_context, log_event

from .checkpoints import (
    _analysis_checkpoint_payload,
    _analysis_checkpoint_refs,
    _analysis_state_from_checkpoint,
    _preview_from_checkpoint,
    _render_checkpoint_refs,
    _selection_checkpoint_payload,
    _selection_state_from_checkpoint,
    _source_checkpoint_payload,
    _source_state_from_checkpoint,
    _vector_indexing_checkpoint_payload,
    _vector_indexing_state_from_checkpoint,
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


SUPPORTED_RESTART_STAGES = (
    STAGE_SOURCE_PREPARED,
    STAGE_SELECTION_COMPLETE,
    STAGE_ANALYSIS_COMPLETE,
    STAGE_RENDER_COMPLETE,
)
LATEST_SAFE_RESTART_STAGE = "latest_safe"


def _read_validated_checkpoint(
    runtime: ReportRuntimeState,
    *,
    stage_name: str,
    require_artifact_lineage: bool = False,
) -> tuple[PipelineStageCheckpoint, str]:
    response = read_pipeline_checkpoint(
        PipelineCheckpointReadRequest(
            schema_version="1.0",
            checkpoint_root=runtime.settings.output_dir,
            pipeline_name=REPORT_PIPELINE_NAME,
            file_id=runtime.file.file_id,
            stage_name=stage_name,
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
                "stage_name": stage_name,
                "checkpoint_path": response.checkpoint_path,
            },
        )
    checkpoint = response.checkpoint
    if checkpoint.stage_status != "completed":
        raise AppError(
            code="report_pipeline_checkpoint_invalid",
            message="Requested report pipeline checkpoint is not completed",
            retryable=False,
            context={
                "file_id": runtime.file.file_id,
                "stage_name": stage_name,
                "stage_status": checkpoint.stage_status,
                "checkpoint_path": response.checkpoint_path,
            },
        )
    _validate_checkpoint_artifacts(
        runtime,
        checkpoint,
        response.checkpoint_path,
        require_artifact_lineage=require_artifact_lineage,
    )
    return checkpoint, response.checkpoint_path


def _validate_checkpoint_artifacts(
    runtime: ReportRuntimeState,
    checkpoint: PipelineStageCheckpoint,
    checkpoint_path: str,
    *,
    require_artifact_lineage: bool = False,
) -> None:
    _validate_checkpoint_artifact_registry(runtime, checkpoint, checkpoint_path)
    _validate_checkpoint_artifact_lineage(
        runtime,
        checkpoint,
        checkpoint_path,
        require_artifact_lineage=require_artifact_lineage,
    )
    raw_integrity = checkpoint.payload.get("artifact_integrity")
    if not isinstance(raw_integrity, dict):
        return
    raw_files = raw_integrity.get("files")
    if not isinstance(raw_files, dict):
        raise AppError(
            code="report_pipeline_checkpoint_invalid",
            message="Checkpoint artifact integrity payload must contain a files object",
            retryable=False,
            context={
                "file_id": runtime.file.file_id,
                "stage_name": checkpoint.stage_name,
                "checkpoint_path": checkpoint_path,
            },
        )
    logger.info(
        log_event(
            runtime.ctx,
            role="orchestrator",
            event="report_pipeline_checkpoint_artifact_validation_start",
            module=logger.name,
            fields={
                "file_id": runtime.file.file_id,
                "stage_name": checkpoint.stage_name,
                "checkpoint_path": checkpoint_path,
                "artifact_count": len(raw_files),
            },
        )
    )
    for name, raw_meta in raw_files.items():
        if not isinstance(raw_meta, dict):
            raise AppError(
                code="report_pipeline_checkpoint_invalid",
                message="Checkpoint artifact integrity entry must be an object",
                retryable=False,
                context={
                    "file_id": runtime.file.file_id,
                    "stage_name": checkpoint.stage_name,
                    "artifact_name": str(name),
                    "checkpoint_path": checkpoint_path,
                },
            )
        expected_path = str(raw_meta.get("path") or "").strip()
        expected_md5 = str(raw_meta.get("md5") or "").strip()
        current_path = str(checkpoint.artifact_refs.get(str(name)) or "").strip()
        if not expected_path or current_path != expected_path:
            raise AppError(
                code="report_pipeline_checkpoint_artifact_missing",
                message="Checkpoint artifact reference is missing or changed",
                retryable=False,
                context={
                    "file_id": runtime.file.file_id,
                    "stage_name": checkpoint.stage_name,
                    "artifact_name": str(name),
                    "expected_path": expected_path,
                    "current_path": current_path,
                    "checkpoint_path": checkpoint_path,
                },
            )
        stat = file_stat(
            FileStatRequest(schema_version="1.0", path=expected_path, compute_md5=True),
            runtime.ctx,
        )
        if not stat.exists or not stat.is_file:
            raise AppError(
                code="report_pipeline_checkpoint_artifact_missing",
                message="Checkpoint artifact file is missing",
                retryable=False,
                context={
                    "file_id": runtime.file.file_id,
                    "stage_name": checkpoint.stage_name,
                    "artifact_name": str(name),
                    "path": expected_path,
                    "checkpoint_path": checkpoint_path,
                },
            )
        if expected_md5 and stat.md5 != expected_md5:
            raise AppError(
                code="report_pipeline_checkpoint_artifact_hash_mismatch",
                message="Checkpoint artifact hash does not match persisted metadata",
                retryable=False,
                context={
                    "file_id": runtime.file.file_id,
                    "stage_name": checkpoint.stage_name,
                    "artifact_name": str(name),
                    "path": expected_path,
                    "expected_md5": expected_md5,
                    "actual_md5": stat.md5 or "",
                    "checkpoint_path": checkpoint_path,
                },
            )
    logger.info(
        log_event(
            runtime.ctx,
            role="orchestrator",
            event="report_pipeline_checkpoint_artifact_validation_complete",
            module=logger.name,
            fields={
                "file_id": runtime.file.file_id,
                "stage_name": checkpoint.stage_name,
                "checkpoint_path": checkpoint_path,
                "artifact_count": len(raw_files),
            },
        )
    )


def _validate_checkpoint_artifact_lineage(
    runtime: ReportRuntimeState,
    checkpoint: PipelineStageCheckpoint,
    checkpoint_path: str,
    *,
    require_artifact_lineage: bool = False,
) -> None:
    raw_lineage = checkpoint.payload.get("artifact_lineage")
    if raw_lineage is None:
        if require_artifact_lineage:
            raise AppError(
                code="report_pipeline_checkpoint_lineage_missing",
                message="Selective regeneration requires retained artifact lineage",
                retryable=False,
                context={
                    "file_id": runtime.file.file_id,
                    "stage_name": checkpoint.stage_name,
                    "checkpoint_path": checkpoint_path,
                },
            )
        return
    if not isinstance(raw_lineage, dict):
        raise AppError(
            code="report_pipeline_checkpoint_invalid",
            message="Checkpoint artifact lineage payload must be an object",
            retryable=False,
            context={"checkpoint_path": checkpoint_path},
        )
    for artifact_name, artifact_id in raw_lineage.items():
        reuse = check_artifact_reuse(
            ArtifactReuseCheckRequest(
                schema_version=ARTIFACT_LINEAGE_SCHEMA_VERSION,
                db_path=runtime.settings.reports_db,
                artifact_id=str(artifact_id or "").strip(),
                expected_schema_version="1.0",
                expected_processing_version="report_generation_checkpoint_v1",
            ),
            runtime.ctx,
        )
        if reuse.reusable:
            continue
        raise AppError(
            code="report_pipeline_checkpoint_lineage_not_reusable",
            message="Checkpoint artifact lineage cannot be reused",
            retryable=False,
            context={
                "file_id": runtime.file.file_id,
                "stage_name": checkpoint.stage_name,
                "artifact_name": str(artifact_name),
                "artifact_id": str(artifact_id or ""),
                "reason": reuse.reason,
                "checkpoint_path": checkpoint_path,
            },
        )


def _validate_checkpoint_artifact_registry(
    runtime: ReportRuntimeState,
    checkpoint: PipelineStageCheckpoint,
    checkpoint_path: str,
) -> None:
    registry = artifact_registry_from_payload(
        checkpoint.payload.get("artifact_registry")
    )
    if registry is None:
        return
    logger.info(
        log_event(
            runtime.ctx,
            role="orchestrator",
            event="report_pipeline_checkpoint_artifact_registry_validation_start",
            module=logger.name,
            fields={
                "file_id": runtime.file.file_id,
                "stage_name": checkpoint.stage_name,
                "checkpoint_path": checkpoint_path,
                "artifact_count": len(registry.refs),
            },
        )
    )
    for ref in registry.refs:
        expected_path = str(ref.path or "").strip()
        current_path = str(checkpoint.artifact_refs.get(ref.artifact_id) or "").strip()
        if current_path and current_path != expected_path:
            raise AppError(
                code="report_pipeline_checkpoint_artifact_missing",
                message="Checkpoint artifact registry path differs from artifact_refs",
                retryable=False,
                context={
                    "file_id": runtime.file.file_id,
                    "stage_name": checkpoint.stage_name,
                    "artifact_id": ref.artifact_id,
                    "expected_path": expected_path,
                    "current_path": current_path,
                    "checkpoint_path": checkpoint_path,
                },
            )
        stat = file_stat(
            FileStatRequest(schema_version="1.0", path=expected_path, compute_md5=True),
            runtime.ctx,
        )
        if not stat.exists or not stat.is_file:
            if ref.required:
                raise AppError(
                    code="report_pipeline_checkpoint_artifact_missing",
                    message="Required checkpoint artifact is missing",
                    retryable=False,
                    context={
                        "file_id": runtime.file.file_id,
                        "stage_name": checkpoint.stage_name,
                        "artifact_id": ref.artifact_id,
                        "path": expected_path,
                        "checkpoint_path": checkpoint_path,
                    },
                )
            continue
        if ref.content_hash and stat.md5 != ref.content_hash:
            raise AppError(
                code="report_pipeline_checkpoint_artifact_hash_mismatch",
                message="Checkpoint artifact registry hash does not match current file",
                retryable=False,
                context={
                    "file_id": runtime.file.file_id,
                    "stage_name": checkpoint.stage_name,
                    "artifact_id": ref.artifact_id,
                    "path": expected_path,
                    "expected_md5": ref.content_hash,
                    "actual_md5": stat.md5 or "",
                    "checkpoint_path": checkpoint_path,
                },
            )
    logger.info(
        log_event(
            runtime.ctx,
            role="orchestrator",
            event="report_pipeline_checkpoint_artifact_registry_validation_complete",
            module=logger.name,
            fields={
                "file_id": runtime.file.file_id,
                "stage_name": checkpoint.stage_name,
                "checkpoint_path": checkpoint_path,
                "artifact_count": len(registry.refs),
            },
        )
    )


def _log_semantic_restart(
    runtime: ReportRuntimeState,
    checkpoint: PipelineStageCheckpoint,
    checkpoint_path: str,
) -> None:
    logger.info(
        log_event(
            runtime.ctx,
            role="orchestrator",
            event="report_pipeline_semantic_restart",
            module=logger.name,
            fields={
                "file_id": runtime.file.file_id,
                "stage_name": checkpoint.stage_name,
                "checkpoint_path": checkpoint_path,
                "artifact_ref_count": len(checkpoint.artifact_refs),
            },
        )
    )


def _render_project_and_cleanup(
    runtime: ReportRuntimeState,
    source,
    selection,
    analysis: ReportAnalysisState,
    preview_resp,
    dependencies: ReportGenerationDependencies,
    analytics_projection_fn: Optional[
        Callable[[AnalyticsProjectionRunRequest], object]
    ],
    *,
    existing_artifact_refs: dict[str, str],
) -> IngestOutcome:
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
            **dict(existing_artifact_refs),
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
                **dict(existing_artifact_refs),
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


def _outcome_from_render_checkpoint(raw_outcome: object) -> IngestOutcome:
    if not isinstance(raw_outcome, dict):
        raise AppError(
            code="report_pipeline_checkpoint_invalid",
            message="Checkpoint render outcome must be an object",
            retryable=False,
        )
    try:
        return IngestOutcome(**raw_outcome)
    except TypeError as exc:
        raise AppError(
            code="report_pipeline_checkpoint_invalid",
            message="Checkpoint render outcome is incomplete",
            cause=exc,
            retryable=False,
        ) from exc


def _resume_from_analysis_checkpoint(
    runtime: ReportRuntimeState,
    dependencies: ReportGenerationDependencies,
    analytics_projection_fn: Optional[
        Callable[[AnalyticsProjectionRunRequest], object]
    ],
) -> IngestOutcome:
    checkpoint, checkpoint_path = _read_validated_checkpoint(
        runtime, stage_name=STAGE_ANALYSIS_COMPLETE
    )
    checkpoint_payload = checkpoint.payload
    _log_semantic_restart(runtime, checkpoint, checkpoint_path)
    source = _source_state_from_checkpoint(runtime, checkpoint_payload.get("source"))
    selection = _selection_state_from_checkpoint(
        runtime, source, checkpoint_payload.get("selection")
    )
    analysis = _analysis_state_from_checkpoint(
        runtime, source, selection, checkpoint_payload.get("analysis")
    )
    preview_resp = _preview_from_checkpoint(checkpoint_payload.get("preview"))
    return _render_project_and_cleanup(
        runtime,
        source,
        selection,
        analysis,
        preview_resp,
        dependencies,
        analytics_projection_fn,
        existing_artifact_refs=dict(checkpoint.artifact_refs),
    )


def _resume_from_source_checkpoint(
    runtime: ReportRuntimeState,
    dependencies: ReportGenerationDependencies,
    analytics_projection_fn: Optional[
        Callable[[AnalyticsProjectionRunRequest], object]
    ],
    *,
    taxonomy_openai_client=None,
    category_fit_openai_client=None,
    evidence_pack_openai_client=None,
    artifact_openai_client=None,
    validation_openai_client=None,
    regeneration_openai_client=None,
    figure_caption_openai_client=None,
) -> IngestOutcome:
    checkpoint, checkpoint_path = _read_validated_checkpoint(
        runtime, stage_name=STAGE_SOURCE_PREPARED
    )
    _log_semantic_restart(runtime, checkpoint, checkpoint_path)
    source = _source_state_from_checkpoint(runtime, checkpoint.payload.get("source"))
    vector_state = start_vector_store_indexing(runtime, source, dependencies.analysis)
    selection = select_report_figures(
        runtime,
        source,
        dependencies.selection,
        crop_qa_llm_client=figure_caption_openai_client,
    )
    _write_stage_checkpoint(
        runtime,
        stage_name=STAGE_SELECTION_COMPLETE,
        artifact_refs={
            **dict(checkpoint.artifact_refs),
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
    preview_resp = render_preview_asset(runtime, source, dependencies.render)
    analysis = run_report_analysis(
        runtime,
        source,
        selection,
        vector_state,
        dependencies.analysis,
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
        payload=_analysis_checkpoint_payload(source, selection, analysis, preview_resp),
    )
    return _render_project_and_cleanup(
        runtime,
        source,
        selection,
        analysis,
        preview_resp,
        dependencies,
        analytics_projection_fn,
        existing_artifact_refs=_analysis_checkpoint_refs(
            runtime, source, analysis, preview_resp
        ),
    )


def _resume_from_selection_checkpoint(
    runtime: ReportRuntimeState,
    dependencies: ReportGenerationDependencies,
    analytics_projection_fn: Optional[
        Callable[[AnalyticsProjectionRunRequest], object]
    ],
    *,
    taxonomy_openai_client=None,
    category_fit_openai_client=None,
    evidence_pack_openai_client=None,
    artifact_openai_client=None,
    validation_openai_client=None,
    regeneration_openai_client=None,
    figure_caption_openai_client=None,
) -> IngestOutcome:
    checkpoint, checkpoint_path = _read_validated_checkpoint(
        runtime, stage_name=STAGE_SELECTION_COMPLETE
    )
    checkpoint_payload = checkpoint.payload
    _log_semantic_restart(runtime, checkpoint, checkpoint_path)
    source = _source_state_from_checkpoint(runtime, checkpoint_payload.get("source"))
    selection = _selection_state_from_checkpoint(
        runtime, source, checkpoint_payload.get("selection")
    )
    vector_state = _vector_indexing_state_from_checkpoint(
        checkpoint_payload.get("vector_indexing")
    )
    preview_resp = render_preview_asset(runtime, source, dependencies.render)
    analysis = run_report_analysis(
        runtime,
        source,
        selection,
        vector_state,
        dependencies.analysis,
        taxonomy_openai_client=taxonomy_openai_client,
        category_fit_openai_client=category_fit_openai_client,
        evidence_pack_openai_client=evidence_pack_openai_client,
        artifact_openai_client=artifact_openai_client,
        validation_openai_client=validation_openai_client,
        regeneration_openai_client=regeneration_openai_client,
        figure_caption_openai_client=figure_caption_openai_client,
    )
    analysis_refs = _analysis_checkpoint_refs(runtime, source, analysis, preview_resp)
    _write_stage_checkpoint(
        runtime,
        stage_name=STAGE_ANALYSIS_COMPLETE,
        artifact_refs=analysis_refs,
        payload=_analysis_checkpoint_payload(source, selection, analysis, preview_resp),
    )
    return _render_project_and_cleanup(
        runtime,
        source,
        selection,
        analysis,
        preview_resp,
        dependencies,
        analytics_projection_fn,
        existing_artifact_refs=analysis_refs,
    )


def _resume_from_render_checkpoint(
    runtime: ReportRuntimeState,
) -> IngestOutcome:
    checkpoint, checkpoint_path = _read_validated_checkpoint(
        runtime, stage_name=STAGE_RENDER_COMPLETE
    )
    _log_semantic_restart(runtime, checkpoint, checkpoint_path)
    return _outcome_from_render_checkpoint(checkpoint.payload.get("outcome"))


def _select_latest_safe_restart_stage(runtime: ReportRuntimeState) -> str:
    last_error: AppError | None = None
    for stage_name in (
        STAGE_RENDER_COMPLETE,
        STAGE_ANALYSIS_COMPLETE,
        STAGE_SELECTION_COMPLETE,
        STAGE_SOURCE_PREPARED,
    ):
        try:
            _read_validated_checkpoint(runtime, stage_name=stage_name)
        except AppError as exc:
            last_error = exc
            logger.info(
                log_event(
                    runtime.ctx,
                    role="orchestrator",
                    event="report_pipeline_latest_safe_checkpoint_rejected",
                    module=logger.name,
                    fields={
                        "file_id": runtime.file.file_id,
                        "stage_name": stage_name,
                        "error_code": exc.code,
                        "error_retryable": exc.retryable,
                    },
                )
            )
            continue
        logger.info(
            log_event(
                runtime.ctx,
                role="orchestrator",
                event="report_pipeline_latest_safe_checkpoint_selected",
                module=logger.name,
                fields={"file_id": runtime.file.file_id, "stage_name": stage_name},
            )
        )
        return stage_name
    if last_error is not None:
        raise last_error
    raise AppError(
        code="report_pipeline_checkpoint_missing",
        message="No report pipeline checkpoint was found",
        retryable=False,
        context={"file_id": runtime.file.file_id},
    )


def _resume_from_checkpoint_stage(
    runtime: ReportRuntimeState,
    dependencies: ReportGenerationDependencies,
    analytics_projection_fn: Optional[
        Callable[[AnalyticsProjectionRunRequest], object]
    ],
    *,
    requested_resume_stage: str,
    require_artifact_lineage: bool = False,
    taxonomy_openai_client=None,
    category_fit_openai_client=None,
    evidence_pack_openai_client=None,
    artifact_openai_client=None,
    validation_openai_client=None,
    regeneration_openai_client=None,
    figure_caption_openai_client=None,
) -> IngestOutcome:
    stage_name = str(requested_resume_stage or "").strip()
    if stage_name == LATEST_SAFE_RESTART_STAGE:
        stage_name = _select_latest_safe_restart_stage(runtime)
    if stage_name not in SUPPORTED_RESTART_STAGES:
        raise AppError(
            code="report_pipeline_restart_stage_invalid",
            message="Unsupported report pipeline restart stage",
            retryable=False,
            context={
                "file_id": runtime.file.file_id,
                "stage_name": stage_name,
                "supported_stages": [
                    *SUPPORTED_RESTART_STAGES,
                    LATEST_SAFE_RESTART_STAGE,
                ],
            },
        )
    if require_artifact_lineage:
        _read_validated_checkpoint(
            runtime,
            stage_name=stage_name,
            require_artifact_lineage=True,
        )
    if stage_name == STAGE_SOURCE_PREPARED:
        return _resume_from_source_checkpoint(
            runtime,
            dependencies,
            analytics_projection_fn,
            taxonomy_openai_client=taxonomy_openai_client,
            category_fit_openai_client=category_fit_openai_client,
            evidence_pack_openai_client=evidence_pack_openai_client,
            artifact_openai_client=artifact_openai_client,
            validation_openai_client=validation_openai_client,
            regeneration_openai_client=regeneration_openai_client,
            figure_caption_openai_client=figure_caption_openai_client,
        )
    if stage_name == STAGE_SELECTION_COMPLETE:
        return _resume_from_selection_checkpoint(
            runtime,
            dependencies,
            analytics_projection_fn,
            taxonomy_openai_client=taxonomy_openai_client,
            category_fit_openai_client=category_fit_openai_client,
            evidence_pack_openai_client=evidence_pack_openai_client,
            artifact_openai_client=artifact_openai_client,
            validation_openai_client=validation_openai_client,
            regeneration_openai_client=regeneration_openai_client,
            figure_caption_openai_client=figure_caption_openai_client,
        )
    if stage_name == STAGE_ANALYSIS_COMPLETE:
        return _resume_from_analysis_checkpoint(
            runtime,
            dependencies,
            analytics_projection_fn,
        )
    return _resume_from_render_checkpoint(runtime)


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
    "SUPPORTED_RESTART_STAGES",
    "LATEST_SAFE_RESTART_STAGE",
    "_read_validated_checkpoint",
    "_validate_checkpoint_artifacts",
    "_validate_checkpoint_artifact_registry",
    "_resume_from_checkpoint_stage",
    "_resume_from_source_checkpoint",
    "_resume_from_selection_checkpoint",
    "_resume_from_analysis_checkpoint",
    "_resume_from_render_checkpoint",
    "_pdf_text_unextractable_outcome",
    "_pdf_text_ocr_failed_outcome",
    "_doc_map_empty_outcome",
    "_cleanup_transient_vector_store",
]
