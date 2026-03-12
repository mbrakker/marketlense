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
from src.contracts.validation import ValidationIssue, ValidationReport, ValidationRequest
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
    dependencies: ReportGeneratorDependencies,
) -> VectorStoreIndexingState:
    vector_store_id = None
    openai_file_id = None
    vector_store_status = None
    indexed_at_utc = None
    last_error = None

    mode_ctx = child_context(runtime.ctx, task_id=f"{runtime.ctx.task_id}:vector_store")
    logger.info(
        log_event(
            mode_ctx,
            role="generator",
            event="vector_store_prepare_start",
            module=logger.name,
            fields={"file_id": runtime.file.file_id, "analysis_mode": runtime.analysis_mode},
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
                fields={"file_id": runtime.file.file_id, "vector_store_id": vector_store_id},
            )
        )
        status_resp = dependencies.vector_store_get_status(
            VectorStoreStatusRequest(
                schema_version="1.0",
                vector_store_id=vector_store_id,
            ),
            ctx=mode_ctx,
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
                fields={"file_id": runtime.file.file_id, "vector_store_id": vector_store_id},
            )
        )
        upload_resp = dependencies.vector_store_upload_file(
            VectorStoreUploadFileRequest(
                schema_version="1.0",
                vector_store_id=vector_store_id,
                file_path=runtime.local_pdf_path,
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
            fields={"vector_store_id": vector_store_id, "status": state.vector_store_status or ""},
        )
    )
    status_resp = dependencies.vector_store_wait_until_indexed(
        VectorStoreWaitRequest(
            schema_version="1.0",
            vector_store_id=vector_store_id,
            timeout_s=int(runtime.settings.openai_timeout_seconds),
            poll_interval_s=5,
        ),
        ctx=mode_ctx,
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
    indexing_state = start_vector_store_indexing(runtime, dependencies)
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
    mode_ctx = child_context(runtime.ctx, task_id=f"{runtime.ctx.task_id}:vector_store")
    vector_state = _await_vector_store_indexing(
        indexing_state,
        runtime,
        mode_ctx,
        dependencies,
    )
    record_state_progress(
        settings=runtime.settings,
        file_id=runtime.file.file_id,
        md5=runtime.md5,
        ctx=mode_ctx,
        dependencies=dependencies,
        stage="vector_store_ready",
        vector_store_id=vector_state.vector_store_id,
        vector_store_status=vector_state.vector_store_status,
        indexed_at_utc=vector_state.indexed_at_utc,
        openai_file_id=vector_state.openai_file_id,
        last_error=vector_state.last_error,
    )

    data = selection.payload
    evidence_ctx = child_context(mode_ctx, task_id=f"{mode_ctx.task_id}:evidence")
    packs: dict[str, dict] = {}
    evidence_error: Optional[Exception] = None
    evidence_kwargs: dict[str, Any] = {}
    artifact_kwargs: dict[str, Any] = {}
    if evidence_pack_openai_client is not None:
        evidence_kwargs["openai_client"] = evidence_pack_openai_client
    if artifact_openai_client is not None:
        artifact_kwargs["openai_client"] = artifact_openai_client

    if runtime.parallel_within_file:
        logger.info(
            log_event(
                mode_ctx,
                role="generator",
                event="post_vector_store_parallel_start",
                module=logger.name,
                fields={
                    "file_id": runtime.file.file_id,
                    "tasks": ["taxonomy_categories", "evidence_packs"],
                    "max_workers": min(runtime.report_worker_limit, 2),
                },
            )
        )
        with ThreadPoolExecutor(max_workers=min(runtime.report_worker_limit, 2)) as executor:
            taxonomy_future = executor.submit(
                _resolve_taxonomy_and_categories,
                runtime,
                selection,
                mode_ctx,
                vector_state.vector_store_id,
                dependencies,
            )
            evidence_future = executor.submit(
                dependencies.generate_evidence_packs,
                report_id=runtime.file.file_id,
                report_name=runtime.report_name,
                vector_store_id=vector_state.vector_store_id,
                settings=runtime.settings,
                ctx=evidence_ctx,
                md5=runtime.md5,
                **evidence_kwargs,
            )
            taxonomy_state = taxonomy_future.result()
            try:
                packs = evidence_future.result()
            except Exception as exc:
                evidence_error = exc
        logger.info(
            log_event(
                mode_ctx,
                role="generator",
                event="post_vector_store_parallel_complete",
                module=logger.name,
                fields={
                    "file_id": runtime.file.file_id,
                    "tasks": ["taxonomy_categories", "evidence_packs"],
                    "evidence_failed": evidence_error is not None,
                },
            )
        )
    else:
        taxonomy_state = _resolve_taxonomy_and_categories(
            runtime,
            selection,
            mode_ctx,
            vector_state.vector_store_id,
            dependencies,
        )

    data.taxonomy = taxonomy_state.taxonomy
    data.region = taxonomy_state.region
    data.time_period = taxonomy_state.time_period
    category_assignment = taxonomy_state.category_assignment
    data.categories = category_assignment.categories
    base_payload = normalize_report(data, runtime.ctx)
    mode_data = deepcopy(base_payload)

    try:
        if not runtime.parallel_within_file:
            packs = dependencies.generate_evidence_packs(
                report_id=runtime.file.file_id,
                report_name=runtime.report_name,
                vector_store_id=vector_state.vector_store_id,
                settings=runtime.settings,
                ctx=evidence_ctx,
                md5=runtime.md5,
                **evidence_kwargs,
            )
        elif evidence_error is not None:
            raise evidence_error
    except AppError as exc:
        if exc.code == "doc_map_empty":
            doc_map_summary = exc.context if isinstance(exc.context, dict) else None
            logger.info(
                log_event(
                    mode_ctx,
                    role="generator",
                    event="doc_map_validation_halt",
                    module=logger.name,
                    fields={
                        "file_id": runtime.file.file_id,
                        "code": exc.code,
                        "message": exc.message,
                        "has_content": doc_map_summary.get("has_content") if doc_map_summary else None,
                        "sections_count": doc_map_summary.get("sections_count") if doc_map_summary else None,
                        "title_present": doc_map_summary.get("title_present") if doc_map_summary else None,
                        "doc_id_present": doc_map_summary.get("doc_id_present") if doc_map_summary else None,
                        "summary_present": doc_map_summary.get("summary_present") if doc_map_summary else None,
                        "not_found_reason": doc_map_summary.get("not_found_reason") if doc_map_summary else "",
                    },
                )
            )
        raise

    mode_evidence_paths = pack_paths(
        runtime.settings.output_dir,
        runtime.file.file_id,
        runtime.report_name,
        list(packs.keys()),
        mode_ctx,
        dependencies,
    )
    mode_data._vector_store_id = vector_state.vector_store_id or ""
    mode_data._evidence_packs = mode_evidence_paths
    logger.info(
        log_event(
            mode_ctx,
            role="generator",
            event="evidence_packs_ready",
            module=logger.name,
            fields={
                "file_id": runtime.file.file_id,
                "vector_store_id": vector_state.vector_store_id,
                "pack_count": len(mode_evidence_paths),
            },
        )
    )
    record_state_progress(
        settings=runtime.settings,
        file_id=runtime.file.file_id,
        md5=runtime.md5,
        ctx=mode_ctx,
        dependencies=dependencies,
        stage="evidence_packs",
        vector_store_id=vector_state.vector_store_id,
        vector_store_status=vector_state.vector_store_status,
        indexed_at_utc=vector_state.indexed_at_utc,
        openai_file_id=vector_state.openai_file_id,
        last_error=vector_state.last_error,
    )

    doc_map_pack = packs.get("doc_map", {})
    if isinstance(doc_map_pack, dict):
        doc_map_title, resolved_publisher, title_source, publisher_source = resolve_doc_map_metadata(doc_map_pack)
        if doc_map_title:
            data.title = doc_map_title
        if resolved_publisher:
            data.publisher = resolved_publisher
        if doc_map_title or resolved_publisher:
            logger.info(
                log_event(
                    mode_ctx,
                    role="generator",
                    event="doc_map_resolved_metadata",
                    module=logger.name,
                    fields={
                        "file_id": runtime.file.file_id,
                        "title": data.title,
                        "publisher": data.publisher,
                        "title_source": title_source or "ingest_payload",
                        "publisher_source": publisher_source or "unset",
                    },
                )
            )

    artifacts_payload: dict | None = None
    try:
        artifacts_payload = dependencies.generate_artifacts(
            report_id=runtime.file.file_id,
            report_name=runtime.report_name,
            doc_map=packs.get("doc_map", {}),
            evidence_packs=packs,
            settings=runtime.settings,
            vector_store_id=vector_state.vector_store_id,
            source_status=source.text_status,
            categories=category_assignment.category_labels,
            ctx=child_context(mode_ctx, task_id=f"{mode_ctx.task_id}:artifacts"),
            md5=runtime.md5,
            **artifact_kwargs,
        )
        mode_evidence_paths["artifacts"] = pack_paths(
            runtime.settings.output_dir,
            runtime.file.file_id,
            runtime.report_name,
            ["artifacts"],
            mode_ctx,
            dependencies,
        )["artifacts"]
        record_state_progress(
            settings=runtime.settings,
            file_id=runtime.file.file_id,
            md5=runtime.md5,
            ctx=mode_ctx,
            dependencies=dependencies,
            stage="artifacts_ready",
            vector_store_id=vector_state.vector_store_id,
            vector_store_status=vector_state.vector_store_status,
            indexed_at_utc=vector_state.indexed_at_utc,
            openai_file_id=vector_state.openai_file_id,
            last_error=vector_state.last_error,
        )
    except Exception as exc:
        logger.info(
            log_event(
                mode_ctx,
                role="generator",
                event="artifacts_generation_failed",
                module=logger.name,
                fields={"file_id": runtime.file.file_id, "error": str(exc)},
            )
        )

    mode_data = merge_artifacts_into_payload(mode_data, artifacts_payload or {})

    validation_pack_name = "validation"
    validation_report: ValidationReport | None = None
    try:
        validation_req = ValidationRequest(
            schema_version="1.0",
            report_id=runtime.file.file_id,
            report=mode_data,
            artifacts=artifacts_payload or {},
            evidence_packs=packs,
            vector_store_id=vector_state.vector_store_id,
        )
        validation_report = dependencies.run_validation(
            validation_req,
            runtime.settings,
            child_context(mode_ctx, task_id=f"{mode_ctx.task_id}:validation"),
            pack_name=validation_pack_name,
            report_name=runtime.report_name,
            md5=runtime.md5,
        )
        if validation_report.source_path:
            mode_evidence_paths[validation_pack_name] = validation_report.source_path
        record_state_progress(
            settings=runtime.settings,
            file_id=runtime.file.file_id,
            md5=runtime.md5,
            ctx=mode_ctx,
            dependencies=dependencies,
            stage="validation_complete",
            vector_store_id=vector_state.vector_store_id,
            vector_store_status=vector_state.vector_store_status,
            indexed_at_utc=vector_state.indexed_at_utc,
            openai_file_id=vector_state.openai_file_id,
            last_error=vector_state.last_error,
        )
    except Exception as exc:
        logger.info(
            log_event(
                mode_ctx,
                role="generator",
                event="validation_failed",
                module=logger.name,
                fields={"file_id": runtime.file.file_id, "error": str(exc), "mode": runtime.analysis_mode},
            )
        )
        fallback_report = ValidationReport(
            schema_version="1.1",
            status="fail",
            issues=[
                ValidationIssue(
                    schema_version="1.0",
                    message=f"Validation error: {exc}",
                    severity="error",
                    affected_section="validation",
                )
            ],
            severity="error",
        )
        try:
            validation_path = dependencies.analysis_store_pack(
                AnalysisStorePackRequest(
                    schema_version="1.0",
                    output_dir=runtime.settings.output_dir,
                    report_id=runtime.file.file_id,
                    pack_name=validation_pack_name,
                    payload=fallback_report.to_dict(),
                    report_slug=runtime.report_name,
                ),
                mode_ctx,
            ).output_path
            fallback_report = ValidationReport(
                schema_version=fallback_report.schema_version,
                status=fallback_report.status,
                issues=fallback_report.issues,
                severity=fallback_report.severity,
                source_path=validation_path,
            )
            mode_evidence_paths[validation_pack_name] = validation_path
        except Exception as store_exc:  # pragma: no cover
            logger.info(
                log_event(
                    mode_ctx,
                    role="generator",
                    event="validation_store_failed",
                    module=logger.name,
                    fields={"file_id": runtime.file.file_id, "error": str(store_exc), "mode": runtime.analysis_mode},
                )
            )
        validation_report = fallback_report

    data_dict = mode_data.to_dict()
    if artifacts_payload:
        data_dict["artifacts"] = artifacts_payload
    if validation_report:
        data_dict["validation_report"] = validation_report.to_dict()
    data_dict["categories_display"] = category_assignment.category_labels
    data_dict["analysis_mode"] = runtime.analysis_mode
    logger.info(
        log_event(
            mode_ctx,
            role="generator",
            event="report_payload_ready",
            module=logger.name,
            fields={"payload": data_dict},
        )
    )
    snapshot_name = f"analysis_{runtime.analysis_mode}"
    snapshot_path = dependencies.analysis_store_pack(
        AnalysisStorePackRequest(
            schema_version="1.0",
            output_dir=runtime.settings.output_dir,
            report_id=runtime.file.file_id,
            pack_name=snapshot_name,
            payload=data_dict,
            report_slug=runtime.report_name,
        ),
        mode_ctx,
    ).output_path
    mode_evidence_paths[snapshot_name] = snapshot_path

    return ReportAnalysisState(
        schema_version="1.0",
        runtime=runtime,
        source=source,
        selection=selection,
        payload=data,
        normalized_payload=mode_data,
        data_dict=data_dict,
        evidence_paths=dict(mode_evidence_paths),
        evidence_packs=packs,
        artifacts_payload=artifacts_payload,
        validation_report=validation_report,
        category_labels=list(category_assignment.category_labels),
        vector_store_id=vector_state.vector_store_id,
        vector_store_status=vector_state.vector_store_status,
        indexed_at_utc=vector_state.indexed_at_utc,
        openai_file_id=vector_state.openai_file_id,
        last_error=vector_state.last_error,
    )
