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
from src.utils.errors import AppError
from src.utils.logging import log_event

from .checkpoints import (
    _analysis_checkpoint_payload,
    _analysis_checkpoint_refs,
    _build_runtime_state,
    _render_checkpoint_refs,
    _selection_checkpoint_payload,
    _source_checkpoint_payload,
    _write_stage_checkpoint,
)

from .resume import (
    _analysis_with_report_value_score,
    _cleanup_transient_vector_store,
    _doc_map_empty_outcome,
    _pdf_text_ocr_failed_outcome,
    _pdf_text_unextractable_outcome,
    _resume_from_analysis_checkpoint,
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
    deps = (
        _with_signal_candidate_orchestrator(dependencies)
        if dependencies is not None
        else _default_report_generation_dependencies()
    )
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
        report_value_score = _score_ingested_report_source(runtime, analysis, deps)
        analysis = _analysis_with_report_value_score(analysis, report_value_score)
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
