from __future__ import annotations

import logging
from copy import deepcopy
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
from src.contracts.regeneration import (
    ArtifactRegenerationRequest,
    RegenerationPlan,
    RegenerationTarget,
)
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
from src.contracts.validation import ValidationRequest
from src.contracts.vector_store import VectorStoreDeleteRequest
from src.generators.normalize_generator import normalize_report
from src.generators.report_analysis_generator import start_vector_store_indexing
from src.generators.report_generation_dependencies import ReportGenerationDependencies
from src.generators.report_generation_shared import merge_artifacts_into_payload
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
from src.generators.validation.regeneration_candidate import (
    CandidateIntegrityResult,
    validate_regeneration_candidate,
)
from src.orchestrators._report_analysis_orchestrator.payload import (
    _attach_payload_analysis_metadata,
    _ensure_report_payload_complete,
)
from src.orchestrators._report_analysis_orchestrator.validation import (
    _candidate_artifacts_path,
    _candidate_audit,
    _candidate_validation_report,
    _evaluate_and_store_public_editorial_quality,
    _merge_public_editorial_quality,
    _promote_regeneration_candidate,
    _run_validation_with_fallback,
    _store_regeneration_candidate_audit,
    _store_validation_snapshot,
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
    _render_checkpoint_payload,
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


def _checkpoint_stage_outcome(
    runtime: ReportRuntimeState,
    stage_name: str,
) -> IngestOutcome:
    """Return a checkpoint boundary without silently invoking the next stage."""
    return IngestOutcome(
        schema_version="1.0",
        file_id=runtime.file.file_id,
        name=runtime.file_name,
        md5=runtime.md5,
        html_path=None,
        status="checkpointed",
        error=None,
        evidence_packs={"checkpoint": stage_name},
    )


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
    if stage_name == STAGE_RENDER_COMPLETE:
        _outcome_from_render_checkpoint(checkpoint.payload.get("outcome"))
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
                expected_processing_version="",
            ),
            runtime.ctx,
        )
        if reuse.reusable and (
            not require_artifact_lineage
            or (reuse.record is not None and reuse.record.lineage_status == "complete")
        ):
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
                "reason": (
                    "lineage_incomplete"
                    if require_artifact_lineage
                    and reuse.record is not None
                    and reuse.record.lineage_status != "complete"
                    else reuse.reason
                ),
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
    skip_post_render_projection: bool = False,
) -> IngestOutcome:
    if skip_post_render_projection:
        logger.info(
            log_event(
                runtime.ctx,
                role="orchestrator",
                event="report_generation_render_only_side_effects_avoided",
                module=logger.name,
                fields={
                    "file_id": runtime.file.file_id,
                    "avoided": [
                        "report_source_score",
                        "analytics_projection",
                        "signal_artifact_generation",
                        "vector_store_cleanup",
                    ],
                },
            )
        )
    else:
        report_value_score = _score_ingested_report_source(
            runtime, analysis, dependencies
        )
        analysis = _analysis_with_report_value_score(analysis, report_value_score)
    outcome = render_report_output(
        runtime,
        source,
        selection,
        analysis,
        dependencies.render,
        preview_resp=preview_resp,
        reuse_report_card_assets=skip_post_render_projection,
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
        payload=_render_checkpoint_payload(
            source, selection, analysis, preview_resp, outcome
        ),
    )
    if (
        not skip_post_render_projection
        and _run_projection(runtime, analysis, outcome, analytics_projection_fn)
        is not None
    ):
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
            payload=_render_checkpoint_payload(
                source, selection, analysis, preview_resp, outcome
            ),
        )
    if skip_post_render_projection:
        return outcome
    return _cleanup_transient_vector_store(outcome, runtime, dependencies)


def _outcome_from_render_checkpoint(raw_outcome: object) -> IngestOutcome:
    if not isinstance(raw_outcome, dict):
        raise AppError(
            code="report_pipeline_checkpoint_invalid",
            message="Checkpoint render outcome must be an object",
            retryable=False,
        )
    try:
        outcome = IngestOutcome(**raw_outcome)
    except TypeError as exc:
        raise AppError(
            code="report_pipeline_checkpoint_invalid",
            message="Checkpoint render outcome is incomplete",
            cause=exc,
            retryable=False,
        ) from exc
    if outcome.publish_readiness_status != "pass":
        raise AppError(
            code="report_pipeline_checkpoint_readiness_unverified",
            message=(
                "A render checkpoint cannot be reused without an explicit "
                "passing publish-readiness decision"
            ),
            retryable=False,
            context={"file_id": outcome.file_id},
        )
    return outcome


def _resume_from_analysis_checkpoint(
    runtime: ReportRuntimeState,
    dependencies: ReportGenerationDependencies,
    analytics_projection_fn: Optional[
        Callable[[AnalyticsProjectionRunRequest], object]
    ],
    *,
    skip_post_render_projection: bool = False,
    stop_after_stage: str = "",
    projection_only: bool = False,
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
    if stop_after_stage == STAGE_ANALYSIS_COMPLETE:
        return _checkpoint_stage_outcome(runtime, STAGE_ANALYSIS_COMPLETE)
    if projection_only:
        outcome = _resume_from_render_checkpoint(runtime)
        _run_projection(runtime, analysis, outcome, analytics_projection_fn)
        return outcome
    return _render_project_and_cleanup(
        runtime,
        source,
        selection,
        analysis,
        preview_resp,
        dependencies,
        analytics_projection_fn,
        existing_artifact_refs=dict(checkpoint.artifact_refs),
        skip_post_render_projection=skip_post_render_projection,
    )


_PROMPT_FAMILY_REPAIR_TARGETS = {
    "report_vs/artifacts/summary": "summary",
    "report_vs/artifacts/insights_candidates": "insights_bundle",
    "report_vs/artifacts/insights_final": "insights_bundle",
    "report_vs/artifacts/quotes": "quotes",
    "report_vs/artifacts/cover_semantics": "cover_semantics",
    "report_vs/artifacts/expert_comment": "expert_comment",
    "report_vs/artifacts/linkedin_post": "linkedin_post",
}
_PROMPT_FAMILY_REPAIR_ORDER = (
    "summary",
    "insights_bundle",
    "quotes",
    "cover_semantics",
    "expert_comment",
    "linkedin_post",
)
_PROMPT_FAMILY_VALIDATION_FAMILIES = {
    "report_vs/validate/grounding",
    "report_vs/validate/semantic",
}


def _resume_prompt_family_repair(
    runtime: ReportRuntimeState,
    dependencies: ReportGenerationDependencies,
    analytics_projection_fn: Optional[
        Callable[[AnalyticsProjectionRunRequest], object]
    ],
    *,
    prompt_families: list[str],
    regeneration_openai_client=None,
    validation_openai_client=None,
    stop_after_stage: str = "",
) -> IngestOutcome:
    """Regenerate only approved retained artifact families and validate them.

    This path is intentionally narrower than the analysis resume path: it
    consumes the verified analysis checkpoint, never re-parses the source or
    creates a vector store, and rejects a family that lacks a precise existing
    regeneration handler.  Rendering is deterministic downstream assembly.
    """
    requested = sorted({str(value or "").strip() for value in prompt_families})
    unsupported = sorted(
        set(requested)
        - set(_PROMPT_FAMILY_REPAIR_TARGETS)
        - _PROMPT_FAMILY_VALIDATION_FAMILIES
    )
    if unsupported:
        raise AppError(
            code="minimal_execution_prompt_family_unavailable",
            message="The enforced prompt-family repair has no precise executor",
            retryable=False,
            context={"unsupported_family_count": len(unsupported)},
        )
    targets = [
        RegenerationTarget(
            target_section=target,
            regenerate_steps=[],
            prompt_namespaces=[],
            issues=[],
        )
        for target in _PROMPT_FAMILY_REPAIR_ORDER
        if target
        in {
            _PROMPT_FAMILY_REPAIR_TARGETS[family]
            for family in requested
            if family in _PROMPT_FAMILY_REPAIR_TARGETS
        }
    ]
    if not targets:
        raise AppError(
            code="minimal_execution_prompt_family_unavailable",
            message="The enforced plan did not identify a regenerable prompt family",
            retryable=False,
            context={"requested_family_count": len(requested)},
        )
    # A rendered checkpoint retains the full analysis payload and becomes the
    # canonical active lineage for its shared artifacts.  Prefer it when it is
    # available so a prompt-only repair never rejects a valid completed render
    # merely because its earlier analysis checkpoint is historical.
    try:
        checkpoint, checkpoint_path = _read_validated_checkpoint(
            runtime,
            stage_name=STAGE_RENDER_COMPLETE,
            require_artifact_lineage=True,
        )
    except AppError as exc:
        if exc.code not in {
            "report_pipeline_checkpoint_missing",
            "report_pipeline_checkpoint_readiness_unverified",
        }:
            raise
        checkpoint, checkpoint_path = _read_validated_checkpoint(
            runtime,
            stage_name=STAGE_ANALYSIS_COMPLETE,
            require_artifact_lineage=True,
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
    if not isinstance(analysis.artifacts_payload, dict):
        raise AppError(
            code="minimal_execution_prompt_family_artifacts_missing",
            message="Prompt-family repair requires retained artifacts from analysis",
            retryable=False,
            context={"file_id": runtime.file.file_id},
        )
    repair_ctx = child_context(
        runtime.ctx, task_id=f"{runtime.ctx.task_id}:prompt_repair"
    )
    regeneration_kwargs = (
        {"openai_client": regeneration_openai_client}
        if regeneration_openai_client is not None
        else {}
    )
    regeneration = dependencies.analysis.regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id=ReportId(runtime.file.file_id),
            report_name=runtime.report_name,
            attempt_index=1,
            plan=RegenerationPlan(
                schema_version="1.0",
                mode="targeted",
                targets=targets,
                unmappable_issues=[],
                broad_retry_allowed=False,
            ),
            current_artifacts=analysis.artifacts_payload,
            doc_map=analysis.evidence_packs.get("doc_map", {}),
            evidence_packs=analysis.evidence_packs,
            settings=runtime.settings,
            ctx=repair_ctx,
            source_status=source.text_status,
            categories=analysis.category_labels,
            vector_store_id=analysis.vector_store_id,
            md5=runtime.md5,
            publisher_name=runtime.publisher_name,
            source_url=runtime.source_url,
        ),
        **regeneration_kwargs,
    )
    candidate_artifacts = regeneration.updated_artifacts
    candidate_artifacts_path = _candidate_artifacts_path(regeneration)
    candidate_enforced = bool(candidate_artifacts_path)
    current_artifacts_path = str(analysis.evidence_paths.get("artifacts") or "")
    candidate_result = (
        validate_regeneration_candidate(
            current_artifacts=analysis.artifacts_payload,
            candidate_artifacts=candidate_artifacts,
            evidence_packs=analysis.evidence_packs,
            ctx=repair_ctx,
        )
        if candidate_enforced
        else CandidateIntegrityResult(issues=[], evidence_lineage=[])
    )
    candidate_audit_path = ""
    if candidate_enforced:
        candidate_audit_path = _store_regeneration_candidate_audit(
            runtime=runtime,
            dependencies=dependencies.analysis,
            audit=_candidate_audit(
                attempt_index=1,
                transformation_scope=regeneration.regenerated_sections,
                current_artifacts=analysis.artifacts_payload,
                candidate_artifacts=candidate_artifacts,
                current_artifacts_path=current_artifacts_path,
                candidate_artifacts_path=candidate_artifacts_path,
                candidate_result=candidate_result,
            ),
            ctx=repair_ctx,
        )
    regenerated_payload = _attach_payload_analysis_metadata(
        merge_artifacts_into_payload(
            deepcopy(normalize_report(analysis.payload, runtime.ctx)),
            candidate_artifacts,
        ),
        vector_store_id=analysis.vector_store_id,
        evidence_paths=analysis.evidence_paths,
    )
    _ensure_report_payload_complete(
        regenerated_payload,
        artifacts=candidate_artifacts,
        ctx=repair_ctx,
        file_id=runtime.file.file_id,
        stage="prompt_family_repair",
    )
    validation_pack_name = (
        "validation_regen_candidate_1" if candidate_enforced else "validation"
    )
    validation = _run_validation_with_fallback(
        runtime=runtime,
        mode_ctx=repair_ctx,
        dependencies=dependencies.analysis,
        validation_req=ValidationRequest(
            schema_version="1.0",
            report_id=ReportId(runtime.file.file_id),
            report=regenerated_payload,
            artifacts=candidate_artifacts,
            evidence_packs=analysis.evidence_packs,
            vector_store_id=analysis.vector_store_id,
            deterministic_grounding_passed=candidate_result.passed,
            publisher_name=runtime.publisher_name,
            report_name=runtime.source_report_name or runtime.report_title,
            source_url=runtime.source_url,
        ),
        pack_name=validation_pack_name,
        openai_client=validation_openai_client,
    )
    validation = _candidate_validation_report(validation, candidate_result)
    editorial_validation, editorial_path = _evaluate_and_store_public_editorial_quality(
        runtime=runtime,
        dependencies=dependencies.analysis,
        artifacts=candidate_artifacts,
        pack_name="public_editorial_quality_prompt_repair",
        ctx=repair_ctx,
    )
    validation = _merge_public_editorial_quality(validation, editorial_validation)
    candidate_validation_path = _store_validation_snapshot(
        runtime=runtime,
        dependencies=dependencies.analysis,
        report=validation,
        pack_name=validation_pack_name,
        ctx=repair_ctx,
    )
    validation = replace(validation, source_path=candidate_validation_path)
    if validation.status != "pass":
        if candidate_enforced:
            _store_regeneration_candidate_audit(
                runtime=runtime,
                dependencies=dependencies.analysis,
                audit=_candidate_audit(
                    attempt_index=1,
                    transformation_scope=regeneration.regenerated_sections,
                    current_artifacts=analysis.artifacts_payload,
                    candidate_artifacts=candidate_artifacts,
                    current_artifacts_path=current_artifacts_path,
                    candidate_artifacts_path=candidate_artifacts_path,
                    candidate_result=candidate_result,
                    validation_report=validation,
                    promotion_outcome="rolled_back",
                ),
                ctx=repair_ctx,
            )
        raise AppError(
            code="minimal_execution_prompt_family_validation_failed",
            message="Targeted prompt-family repair did not pass required validation",
            retryable=False,
            context={"file_id": runtime.file.file_id},
        )
    artifacts_path = regeneration.artifacts_path
    if candidate_enforced:
        try:
            artifacts_path = _promote_regeneration_candidate(
                runtime=runtime,
                dependencies=dependencies.analysis,
                candidate_artifacts=candidate_artifacts,
                ctx=repair_ctx,
            )
        except Exception:
            _store_regeneration_candidate_audit(
                runtime=runtime,
                dependencies=dependencies.analysis,
                audit=_candidate_audit(
                    attempt_index=1,
                    transformation_scope=regeneration.regenerated_sections,
                    current_artifacts=analysis.artifacts_payload,
                    candidate_artifacts=candidate_artifacts,
                    current_artifacts_path=current_artifacts_path,
                    candidate_artifacts_path=candidate_artifacts_path,
                    candidate_result=candidate_result,
                    validation_report=validation,
                    promotion_outcome="rolled_back",
                ),
                ctx=repair_ctx,
            )
            raise
        validation_path = _store_validation_snapshot(
            runtime=runtime,
            dependencies=dependencies.analysis,
            report=validation,
            pack_name="validation",
            ctx=repair_ctx,
        )
        validation = replace(validation, source_path=validation_path)
        candidate_audit_path = _store_regeneration_candidate_audit(
            runtime=runtime,
            dependencies=dependencies.analysis,
            audit=_candidate_audit(
                attempt_index=1,
                transformation_scope=regeneration.regenerated_sections,
                current_artifacts=analysis.artifacts_payload,
                candidate_artifacts=candidate_artifacts,
                current_artifacts_path=current_artifacts_path,
                candidate_artifacts_path=candidate_artifacts_path,
                candidate_result=candidate_result,
                validation_report=validation,
                promotion_outcome="promoted",
            ),
            ctx=repair_ctx,
        )
    evidence_paths = dict(analysis.evidence_paths)
    evidence_paths["artifacts"] = artifacts_path
    if regeneration.artifacts_snapshot_path:
        evidence_paths["artifacts_prompt_repair"] = regeneration.artifacts_snapshot_path
    if candidate_artifacts_path:
        evidence_paths["artifacts_regen_candidate_1"] = candidate_artifacts_path
    if candidate_audit_path:
        evidence_paths["regeneration_candidate_audit_1"] = candidate_audit_path
    if validation.source_path:
        evidence_paths["validation"] = validation.source_path
    if editorial_path:
        evidence_paths["public_editorial_quality_prompt_repair"] = editorial_path
    data_dict = regenerated_payload.to_dict()
    data_dict["artifacts"] = candidate_artifacts
    data_dict["evidence_packs"] = analysis.evidence_packs
    data_dict["validation_report"] = validation.to_dict()
    analysis = replace(
        analysis,
        normalized_payload=regenerated_payload,
        data_dict=data_dict,
        evidence_paths=evidence_paths,
        artifacts_payload=candidate_artifacts,
        validation_report=validation,
    )
    preview_resp = _preview_from_checkpoint(checkpoint_payload.get("preview"))
    analysis_refs = _analysis_checkpoint_refs(runtime, source, analysis, preview_resp)
    _write_stage_checkpoint(
        runtime,
        stage_name=STAGE_ANALYSIS_COMPLETE,
        artifact_refs=analysis_refs,
        payload=_analysis_checkpoint_payload(source, selection, analysis, preview_resp),
    )
    if stop_after_stage == STAGE_ANALYSIS_COMPLETE:
        return replace(
            _checkpoint_stage_outcome(runtime, STAGE_ANALYSIS_COMPLETE),
            actual_prompt_families=requested,
        )
    outcome = _render_project_and_cleanup(
        runtime,
        source,
        selection,
        analysis,
        preview_resp,
        dependencies,
        analytics_projection_fn,
        existing_artifact_refs=analysis_refs,
        skip_post_render_projection=True,
    )
    return replace(outcome, actual_prompt_families=requested)


def _resume_crop_from_source_checkpoint(
    runtime: ReportRuntimeState,
    dependencies: ReportGenerationDependencies,
    analytics_projection_fn: Optional[
        Callable[[AnalyticsProjectionRunRequest], object]
    ],
) -> IngestOutcome:
    """Regenerate crop-dependent presentation from proven source and analysis state.

    Crop profiles alter selection and rendering, not report analysis.  The
    source and analysis checkpoints are both validated before their data is
    consumed, so this path never creates a vector store or an analysis client.
    """
    source_checkpoint, source_checkpoint_path = _read_validated_checkpoint(
        runtime, stage_name=STAGE_SOURCE_PREPARED, require_artifact_lineage=True
    )
    analysis_checkpoint, analysis_checkpoint_path = _read_validated_checkpoint(
        runtime, stage_name=STAGE_ANALYSIS_COMPLETE, require_artifact_lineage=True
    )
    _log_semantic_restart(runtime, source_checkpoint, source_checkpoint_path)
    _log_semantic_restart(runtime, analysis_checkpoint, analysis_checkpoint_path)
    source = _source_state_from_checkpoint(
        runtime, source_checkpoint.payload.get("source")
    )
    selection = select_report_figures(runtime, source, dependencies.selection)
    _write_stage_checkpoint(
        runtime,
        stage_name=STAGE_SELECTION_COMPLETE,
        artifact_refs={
            **dict(source_checkpoint.artifact_refs),
            "source_pdf": runtime.local_pdf_path,
            "analysis_pdf": source.analysis_pdf_path or runtime.local_pdf_path,
        },
        payload={
            "schema_version": "1.0",
            "source": _source_checkpoint_payload(source),
            "selection": _selection_checkpoint_payload(selection),
        },
    )
    analysis = _analysis_state_from_checkpoint(
        runtime,
        source,
        selection,
        analysis_checkpoint.payload.get("analysis"),
    )
    preview_resp = render_preview_asset(runtime, source, dependencies.render)
    return _render_project_and_cleanup(
        runtime,
        source,
        selection,
        analysis,
        preview_resp,
        dependencies,
        analytics_projection_fn,
        existing_artifact_refs=dict(analysis_checkpoint.artifact_refs),
        skip_post_render_projection=True,
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
    stop_after_stage: str = "",
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
    if stop_after_stage == STAGE_SELECTION_COMPLETE:
        return _checkpoint_stage_outcome(runtime, STAGE_SELECTION_COMPLETE)
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
    if stop_after_stage == STAGE_ANALYSIS_COMPLETE:
        return _checkpoint_stage_outcome(runtime, STAGE_ANALYSIS_COMPLETE)
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
    stop_after_stage: str = "",
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
    if not vector_state.vector_store_id:
        # Older, otherwise complete selection checkpoints did not retain the
        # optional vector state.  Re-establish that external analysis resource
        # from the retained source rather than falling back to PDF extraction
        # or crop selection.
        vector_state = start_vector_store_indexing(
            runtime, source, dependencies.analysis
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
    if stop_after_stage == STAGE_ANALYSIS_COMPLETE:
        return _checkpoint_stage_outcome(runtime, STAGE_ANALYSIS_COMPLETE)
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
    skip_post_render_projection: bool = False,
    stop_after_stage: str = "",
    projection_only: bool = False,
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
            stop_after_stage=stop_after_stage,
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
            stop_after_stage=stop_after_stage,
        )
    if stage_name == STAGE_ANALYSIS_COMPLETE:
        return _resume_from_analysis_checkpoint(
            runtime,
            dependencies,
            analytics_projection_fn,
            skip_post_render_projection=skip_post_render_projection,
            stop_after_stage=stop_after_stage,
            projection_only=projection_only,
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
    "_resume_crop_from_source_checkpoint",
    "_resume_from_render_checkpoint",
    "_pdf_text_unextractable_outcome",
    "_pdf_text_ocr_failed_outcome",
    "_doc_map_empty_outcome",
    "_cleanup_transient_vector_store",
]
