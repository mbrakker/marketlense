from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.contracts.categories import (
    CategoryAssignment,
)
from src.contracts.context_category_fit import (
    ContextCategoryFitResponse,
    ContextCategoryFitRequest,
    ReportCategoryContext,
    ReportContextBuildRequest,
)
from src.contracts.report_generation import (
    ReportAnalysisState,
    ReportRuntimeState,
    ReportSelectionState,
    ReportSourceState,
)
from src.contracts.report_store import ReportMetadataGetResponse
from src.contracts.state import StateGetRequest
from src.contracts.taxonomy import TaxonomyExtractRequest
from src.contracts.vector_store import (
    VectorStoreAttachFileRequest,
    VectorStoreCreateRequest,
    VectorStoreMetadata,
    VectorStoreStatusRequest,
    VectorStoreUploadFileRequest,
)
from src.generators.report_generation_dependencies import ReportAnalysisDependencies
from src.generators.report_generation_shared import (
    logger,
    record_state_progress,
)
from src.utils.errors import AppError
from src.utils.logging import child_context, log_event


@dataclass(frozen=True)
class VectorStoreIndexingState:
    vector_store_id: Optional[str]
    openai_file_id: Optional[str]
    vector_store_status: Optional[str]
    indexed_at_utc: Optional[str]
    last_error: Optional[str]


@dataclass(frozen=True)
class _TaxonomyState:
    taxonomy: list[str]
    region: str
    time_period: str


@dataclass(frozen=True)
class _ContextCategoryState:
    category_assignment: CategoryAssignment
    report_context: ReportCategoryContext
    fit_response: ContextCategoryFitResponse


def _is_vector_store_ready(status: Optional[str]) -> bool:
    return str(status or "").strip().lower() in {"completed", "ready", "indexed"}


def start_vector_store_indexing(
    runtime: ReportRuntimeState,
    source: ReportSourceState | None,
    dependencies: ReportAnalysisDependencies,
) -> VectorStoreIndexingState:
    vector_store_id = None
    openai_file_id = None
    vector_store_status = None
    indexed_at_utc = None
    last_error = None
    analysis_pdf_path = (
        source.analysis_pdf_path
        if source is not None and source.analysis_pdf_path
        else runtime.local_pdf_path
    )

    mode_ctx = child_context(runtime.ctx, task_id=f"{runtime.ctx.task_id}:vector_store")
    logger.info(
        log_event(
            mode_ctx,
            role="generator",
            event="vector_store_prepare_start",
            module=logger.name,
            fields={
                "file_id": runtime.file.file_id,
                "analysis_mode": runtime.analysis_mode,
            },
        )
    )
    existing = None
    try:
        existing = dependencies.state_get(
            StateGetRequest(
                schema_version="1.0",
                state_db=runtime.settings.state_db,
                file_id=runtime.file.file_id,
            ),
            mode_ctx,
        )
    except Exception:
        existing = None
    if existing and runtime.settings.vector_store_keep and existing.vector_store_id:
        vector_store_id = existing.vector_store_id
        openai_file_id = existing.openai_file_id
        logger.info(
            log_event(
                mode_ctx,
                role="generator",
                event="vector_store_reuse",
                module=logger.name,
                fields={
                    "file_id": runtime.file.file_id,
                    "vector_store_id": vector_store_id,
                },
            )
        )
        status_resp = dependencies.vector_store_get_status(
            VectorStoreStatusRequest(
                schema_version="1.0",
                vector_store_id=vector_store_id,
            ),
            mode_ctx,
        )
        vector_store_status = status_resp.status
        indexed_at_utc = status_resp.indexed_at_utc
        last_error = status_resp.last_error
    if not vector_store_id:
        vs_resp = dependencies.vector_store_create(
            VectorStoreCreateRequest(
                schema_version="1.0",
                name=runtime.file.file_id,
                metadata=VectorStoreMetadata(
                    schema_version="1.0",
                    report_id=runtime.file.file_id,
                    report_name=runtime.file_name or runtime.file.file_id,
                    taxonomy=[],
                    categories=[],
                    region="",
                    time_period="",
                ),
            ),
            mode_ctx,
        )
        vector_store_id = vs_resp.vector_store_id
        logger.info(
            log_event(
                mode_ctx,
                role="generator",
                event="vector_store_created",
                module=logger.name,
                fields={
                    "file_id": runtime.file.file_id,
                    "vector_store_id": vector_store_id,
                },
            )
        )
        upload_resp = dependencies.vector_store_upload_file(
            VectorStoreUploadFileRequest(
                schema_version="1.0",
                vector_store_id=vector_store_id,
                file_path=analysis_pdf_path,
            ),
            mode_ctx,
        )
        openai_file_id = upload_resp.openai_file_id
        dependencies.vector_store_attach_file(
            VectorStoreAttachFileRequest(
                schema_version="1.0",
                vector_store_id=vector_store_id,
                openai_file_id=upload_resp.openai_file_id,
            ),
            mode_ctx,
        )
        vector_store_status = "indexing"

    logger.info(
        log_event(
            mode_ctx,
            role="generator",
            event="vector_store_indexing_started"
            if not _is_vector_store_ready(vector_store_status)
            else "vector_store_already_indexed",
            module=logger.name,
            fields={
                "file_id": runtime.file.file_id,
                "vector_store_id": vector_store_id,
                "status": vector_store_status or "",
                "indexed_at_utc": indexed_at_utc or "",
            },
        )
    )
    if not _is_vector_store_ready(vector_store_status):
        record_state_progress(
            settings=runtime.settings,
            file_id=runtime.file.file_id,
            md5=runtime.md5,
            ctx=mode_ctx,
            dependencies=dependencies,
            stage="vector_store_indexing",
            vector_store_id=vector_store_id,
            vector_store_status=vector_store_status or "indexing",
            indexed_at_utc=indexed_at_utc,
            openai_file_id=openai_file_id,
            last_error=last_error,
        )
    return VectorStoreIndexingState(
        vector_store_id=vector_store_id,
        openai_file_id=openai_file_id,
        vector_store_status=vector_store_status,
        indexed_at_utc=indexed_at_utc,
        last_error=last_error,
    )


def ensure_vector_store(
    runtime: ReportRuntimeState,
    dependencies: ReportAnalysisDependencies,
) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str], Optional[str]]:
    logger.info(
        log_event(
            runtime.ctx,
            role="generator",
            event="invalid_generator_entrypoint",
            module=logger.name,
            fields={
                "file_id": runtime.file.file_id,
                "expected_entrypoint": "src.orchestrators.report_analysis_orchestrator.run_report_analysis",
            },
        )
    )
    raise AppError(
        code="invalid_generator_entrypoint",
        message=(
            "Vector-store wait sequencing belongs to "
            "src.orchestrators.report_analysis_orchestrator.run_report_analysis."
        ),
        retryable=False,
        context={"file_id": runtime.file.file_id},
    )


def _resolve_taxonomy(
    runtime: ReportRuntimeState,
    mode_ctx,
    vector_store_id: Optional[str],
    dependencies: ReportAnalysisDependencies,
) -> _TaxonomyState:
    taxonomy_ctx = child_context(mode_ctx, task_id=f"{mode_ctx.task_id}:taxonomy")
    taxonomy_resp = dependencies.extract_taxonomy(
        TaxonomyExtractRequest(
            schema_version="1.0",
            report_id=runtime.file.file_id,
            report_title=runtime.report_title,
            vector_store_id=vector_store_id or "",
            settings=runtime.settings,
            md5=runtime.md5,
            report_slug=runtime.report_name,
        ),
        taxonomy_ctx,
    )
    return _TaxonomyState(
        taxonomy=taxonomy_resp.taxonomy,
        region=taxonomy_resp.region,
        time_period=taxonomy_resp.time_period,
    )


def _resolve_categories_from_report_context(
    runtime: ReportRuntimeState,
    *,
    title: str,
    publisher: str,
    taxonomy_state: _TaxonomyState,
    evidence_pack_paths: dict[str, str],
    mode_ctx,
    dependencies: ReportAnalysisDependencies,
) -> _ContextCategoryState:
    category_ctx = child_context(mode_ctx, task_id=f"{mode_ctx.task_id}:categories")
    report_metadata = ReportMetadataGetResponse(
        schema_version="1.1",
        file_id=runtime.file.file_id,
        title=title,
        created_at=0,
        updated_at=0,
        file_name=runtime.file_name,
        publisher=publisher or None,
        taxonomy=list(taxonomy_state.taxonomy),
        categories=[],
        region=taxonomy_state.region or None,
        time_period=taxonomy_state.time_period or None,
        source_url=None,
        html_path=None,
        md5=runtime.md5,
        page_count=None,
        contents_page_number=0,
        pdf_metadata={},
        analysis_mode=runtime.analysis_mode,
        vector_store_id=None,
        evidence_pack_paths=dict(evidence_pack_paths),
    )
    report_context = dependencies.build_report_category_context(
        ReportContextBuildRequest(
            schema_version="1.0",
            report=report_metadata,
        ),
        category_ctx,
    )
    fit_response = dependencies.fit_report_categories_from_context(
        ContextCategoryFitRequest(
            schema_version="1.0",
            context=report_context,
            settings=runtime.settings,
            category_mapping_path=runtime.settings.category_mapping_path,
        ),
        category_ctx,
    )
    return _ContextCategoryState(
        category_assignment=CategoryAssignment(
            schema_version="1.1",
            categories=list(fit_response.categories),
            category_labels=list(fit_response.category_labels),
            unmapped_tags=[],
            score_details=[],
        ),
        report_context=report_context,
        fit_response=fit_response,
    )


def complete_report_analysis(
    runtime: ReportRuntimeState,
    source: ReportSourceState,
    selection: ReportSelectionState,
    indexing_state: VectorStoreIndexingState,
    dependencies: ReportAnalysisDependencies,
    *,
    evidence_pack_openai_client=None,
    artifact_openai_client=None,
) -> ReportAnalysisState:
    logger.info(
        log_event(
            runtime.ctx,
            role="generator",
            event="invalid_generator_entrypoint",
            module=logger.name,
            fields={
                "file_id": runtime.file.file_id,
                "expected_entrypoint": "src.orchestrators.report_analysis_orchestrator.run_report_analysis",
            },
        )
    )
    raise AppError(
        code="invalid_generator_entrypoint",
        message=(
            "Report analysis sequencing belongs to "
            "src.orchestrators.report_analysis_orchestrator.run_report_analysis."
        ),
        retryable=False,
        context={"file_id": runtime.file.file_id},
    )
