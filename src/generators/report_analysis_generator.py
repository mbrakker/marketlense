from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Optional

from src.contracts.categories import (
    CategoryAssignment,
    CategoryMappingLoadRequest,
    UncategorizedTagsUpdateRequest,
)
from src.contracts.report_analysis import AnalysisStorePackRequest
from src.contracts.report_generation import (
    ReportAnalysisState,
    ReportRuntimeState,
    ReportSelectionState,
    ReportSourceState,
)
from src.contracts.state import StateGetRequest
from src.contracts.taxonomy import TaxonomyExtractRequest
from src.contracts.validation import (
    ValidationIssue,
    ValidationReport,
    ValidationRequest,
)
from src.contracts.vector_store import (
    VectorStoreAttachFileRequest,
    VectorStoreCreateRequest,
    VectorStoreMetadata,
    VectorStoreStatusRequest,
    VectorStoreUpdateMetadataRequest,
    VectorStoreUploadFileRequest,
    VectorStoreWaitRequest,
)
from src.generators.normalize_generator import normalize_report
from src.generators.report_generation_dependencies import ReportGeneratorDependencies
from src.generators.report_generation_shared import (
    logger,
    merge_artifacts_into_payload,
    pack_paths,
    record_state_progress,
    resolve_doc_map_metadata,
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
class _TaxonomyCategoryState:
    taxonomy: list[str]
    region: str
    time_period: str
    category_assignment: CategoryAssignment


def _is_vector_store_ready(status: Optional[str]) -> bool:
    return str(status or "").strip().lower() in {"completed", "ready", "indexed"}


def start_vector_store_indexing(
    runtime: ReportRuntimeState,
    source: ReportSourceState | None,
    dependencies: ReportGeneratorDependencies,
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


def _await_vector_store_indexing(
    state: VectorStoreIndexingState,
    runtime: ReportRuntimeState,
    mode_ctx,
    dependencies: ReportGeneratorDependencies,
) -> VectorStoreIndexingState:
    vector_store_id = state.vector_store_id
    if not vector_store_id:
        raise AppError(
            code="vector_store_missing",
            message="vector_store_id is required before awaiting indexing",
            retryable=False,
        )
    if _is_vector_store_ready(state.vector_store_status):
        logger.info(
            log_event(
                mode_ctx,
                role="generator",
                event="vector_store_wait_skipped",
                module=logger.name,
                fields={
                    "vector_store_id": vector_store_id,
                    "status": state.vector_store_status or "",
                    "indexed_at_utc": state.indexed_at_utc or "",
                },
            )
        )
        logger.info(
            log_event(
                mode_ctx,
                role="generator",
                event="vector_store_ready",
                module=logger.name,
                fields={
                    "vector_store_id": vector_store_id,
                    "status": state.vector_store_status,
                    "indexed_at_utc": state.indexed_at_utc or "",
                },
            )
        )
        return state
    logger.info(
        log_event(
            mode_ctx,
            role="generator",
            event="vector_store_wait_start",
            module=logger.name,
            fields={
                "vector_store_id": vector_store_id,
                "status": state.vector_store_status or "",
            },
        )
    )
    status_resp = dependencies.vector_store_wait_until_indexed(
        VectorStoreWaitRequest(
            schema_version="1.0",
            vector_store_id=vector_store_id,
            timeout_s=int(runtime.settings.openai_timeout_seconds),
            poll_interval_s=5,
        ),
        mode_ctx,
    )
    ready_state = VectorStoreIndexingState(
        vector_store_id=vector_store_id,
        openai_file_id=state.openai_file_id,
        vector_store_status=status_resp.status,
        indexed_at_utc=status_resp.indexed_at_utc,
        last_error=status_resp.last_error,
    )
    logger.info(
        log_event(
            mode_ctx,
            role="generator",
            event="vector_store_ready",
            module=logger.name,
            fields={
                "vector_store_id": ready_state.vector_store_id,
                "status": ready_state.vector_store_status,
                "indexed_at_utc": ready_state.indexed_at_utc or "",
            },
        )
    )
    return ready_state


def ensure_vector_store(
    runtime: ReportRuntimeState,
    dependencies: ReportGeneratorDependencies,
) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str], Optional[str]]:
    indexing_state = start_vector_store_indexing(runtime, None, dependencies)
    ready_state = _await_vector_store_indexing(
        indexing_state,
        runtime,
        child_context(runtime.ctx, task_id=f"{runtime.ctx.task_id}:vector_store"),
        dependencies,
    )
    return (
        ready_state.vector_store_id,
        ready_state.openai_file_id,
        ready_state.vector_store_status,
        ready_state.indexed_at_utc,
        ready_state.last_error,
    )


def _resolve_taxonomy_and_categories(
    runtime: ReportRuntimeState,
    selection: ReportSelectionState,
    mode_ctx,
    vector_store_id: Optional[str],
    dependencies: ReportGeneratorDependencies,
) -> _TaxonomyCategoryState:
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
    mappings_resp = dependencies.load_category_mappings(
        CategoryMappingLoadRequest(
            schema_version="1.0",
            path=runtime.settings.category_mapping_path,
            reload_if_changed=True,
        ),
        taxonomy_ctx,
    )
    category_assignment = dependencies.categorize_taxonomy(
        taxonomy_resp.taxonomy,
        mappings_resp,
        taxonomy_ctx,
    )
    if category_assignment.unmapped_tags or mappings_resp.mappings.uncategorized:
        dependencies.update_uncategorized_tags(
            UncategorizedTagsUpdateRequest(
                schema_version="1.0",
                path=runtime.settings.category_mapping_path,
                report_title=runtime.report_title,
                tags=category_assignment.unmapped_tags,
            ),
            taxonomy_ctx,
        )
    if vector_store_id:
        dependencies.vector_store_update_metadata(
            VectorStoreUpdateMetadataRequest(
                schema_version="1.0",
                vector_store_id=vector_store_id,
                metadata=VectorStoreMetadata(
                    schema_version="1.0",
                    report_id=runtime.file.file_id,
                    report_name=runtime.report_title,
                    taxonomy=taxonomy_resp.taxonomy,
                    categories=category_assignment.categories,
                    region=taxonomy_resp.region,
                    time_period=taxonomy_resp.time_period,
                ),
            ),
            child_context(mode_ctx, task_id=f"{mode_ctx.task_id}:metadata"),
        )
    return _TaxonomyCategoryState(
        taxonomy=taxonomy_resp.taxonomy,
        region=taxonomy_resp.region,
        time_period=taxonomy_resp.time_period,
        category_assignment=category_assignment,
    )


def complete_report_analysis(
    runtime: ReportRuntimeState,
    source: ReportSourceState,
    selection: ReportSelectionState,
    indexing_state: VectorStoreIndexingState,
    dependencies: ReportGeneratorDependencies,
    *,
    evidence_pack_openai_client=None,
    artifact_openai_client=None,
) -> ReportAnalysisState:
    logger.info(
        log_event(
            runtime.ctx,
            role="generator",
            event="report_analysis_delegate",
            module=logger.name,
            fields={
                "file_id": runtime.file.file_id,
                "delegated_to": "src.orchestrators.report_analysis_orchestrator.run_report_analysis",
            },
        )
    )
    from src.orchestrators.report_analysis_orchestrator import run_report_analysis

    return run_report_analysis(
        runtime,
        source,
        selection,
        indexing_state,
        dependencies,
        evidence_pack_openai_client=evidence_pack_openai_client,
        artifact_openai_client=artifact_openai_client,
    )
    analysis_pdf_path = (
        source.analysis_pdf_path if source is not None else runtime.local_pdf_path
    )
