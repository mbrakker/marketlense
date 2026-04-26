from __future__ import annotations

import logging
from math import ceil
import re
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import asdict
from typing import Any, Dict, List, Optional

from src.contracts.regeneration import (
    ArtifactRegenerationRequest,
    RegenerationAttemptResult,
    RegenerationIssue,
    RegenerationLoopState,
    RegenerationPlan,
    RegenerationTarget,
)
from src.contracts.report_analysis import (
    AnalysisPackPathRequest,
    AnalysisStorePackRequest,
)
from src.contracts.report_generation import (
    ReportAnalysisState,
    ReportRuntimeState,
    ReportSelectionState,
    ReportSourceState,
)
from src.contracts.validation import (
    ValidationIssue,
    ValidationReport,
    ValidationRequest,
)
from src.contracts.semantic_ids import ReportId
from src.contracts.vector_store import (
    VectorStoreStatusRequest,
    VectorStoreMetadata,
    VectorStoreUpdateMetadataRequest,
)
from src.generators.normalize_generator import normalize_report
from src.generators.figure_caption_generator import generate_figure_captions
from src.generators.report_analysis_generator import (
    VectorStoreIndexingState,
    _resolve_categories_from_report_context,
    _resolve_taxonomy,
)
from src.generators.report_generation_dependencies import ReportAnalysisDependencies
from src.generators.report_generation_shared import (
    merge_artifacts_into_payload,
    pack_paths,
    record_state_progress,
    resolve_doc_map_metadata,
    resolve_doc_map_primary_contributor,
)
from src.orchestrators.retry_orchestrator import RetryPolicy, run_with_retry
from src.utils.errors import AppError
from src.utils.logging import child_context, log_event

logger = logging.getLogger("market_lense.report_analysis_orchestrator")

RULE_ID_RE = re.compile(r"^\[([^\]]+)\]")
TARGET_ORDER = [
    "topics",
    "summary",
    "insights_bundle",
    "quotes",
    "expert_comment",
    "linkedin_post",
]
BROAD_TARGETS = [
    "summary",
    "insights_bundle",
    "quotes",
    "expert_comment",
    "linkedin_post",
]
REPORT_PAYLOAD_SENTINELS = {"not available from text"}
VECTOR_STORE_READY_STATUSES = {"completed", "ready", "indexed"}
VECTOR_STORE_FAILED_STATUSES = {"failed", "errored"}
VECTOR_STORE_POLL_INTERVAL_SECONDS = 5


def _attach_payload_analysis_metadata(
    payload,
    *,
    vector_store_id: Optional[str],
    evidence_paths: Dict[str, str],
):
    payload._vector_store_id = str(vector_store_id or "")
    payload._evidence_packs = dict(evidence_paths)
    return payload


def _serialize_context_category_fit_payload(fit_response) -> dict[str, Any]:
    return {
        "schema_version": str(fit_response.schema_version or "1.0"),
        "selected_category_ids": list(fit_response.categories or []),
        "category_fits": [
            {
                "category_id": str(fit.category_id),
                "label": str(fit.label),
                "fit_score": float(fit.fit_score),
                "decision": str(fit.decision),
                "why_fit": str(fit.why_fit),
                "why_not_fit": str(fit.why_not_fit),
                "evidence_sections": list(fit.evidence_sections or []),
            }
            for fit in fit_response.fits
        ],
    }


def _is_vector_store_ready(status: Optional[str]) -> bool:
    return str(status or "").strip().lower() in VECTOR_STORE_READY_STATUSES


def _await_vector_store_indexing(
    state: VectorStoreIndexingState,
    runtime: ReportRuntimeState,
    mode_ctx,
    dependencies: ReportAnalysisDependencies,
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
                role="orchestrator",
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
                role="orchestrator",
                event="vector_store_ready",
                module=logger.name,
                fields={
                    "vector_store_id": vector_store_id,
                    "status": state.vector_store_status or "",
                    "indexed_at_utc": state.indexed_at_utc or "",
                },
            )
        )
        return state

    timeout_seconds = max(1, int(runtime.settings.openai_timeout_seconds))
    poll_interval_seconds = VECTOR_STORE_POLL_INTERVAL_SECONDS
    max_attempts = max(1, int(ceil(timeout_seconds / poll_interval_seconds)))
    last_status = state.vector_store_status or ""
    last_error = state.last_error
    last_indexed_at = state.indexed_at_utc

    logger.info(
        log_event(
            mode_ctx,
            role="orchestrator",
            event="vector_store_wait_start",
            module=logger.name,
            fields={
                "vector_store_id": vector_store_id,
                "status": last_status,
                "timeout_s": timeout_seconds,
                "poll_interval_s": poll_interval_seconds,
                "max_attempts": max_attempts,
            },
        )
    )

    def _poll_status():
        nonlocal last_status, last_error, last_indexed_at
        status_resp = dependencies.vector_store_get_status(
            VectorStoreStatusRequest(
                schema_version="1.0",
                vector_store_id=vector_store_id,
            ),
            mode_ctx,
        )
        last_status = status_resp.status
        last_error = status_resp.last_error
        last_indexed_at = status_resp.indexed_at_utc
        normalized_status = str(status_resp.status or "").strip().lower()
        if normalized_status in VECTOR_STORE_READY_STATUSES:
            return status_resp
        if normalized_status in VECTOR_STORE_FAILED_STATUSES:
            raise AppError(
                code="vector_store_index_failed",
                message=(
                    "Vector store indexing failed: "
                    f"{status_resp.last_error or status_resp.status}"
                ),
                retryable=False,
                context={
                    "vector_store_id": vector_store_id,
                    "last_status": status_resp.status,
                    "last_error": status_resp.last_error,
                },
            )
        raise AppError(
            code="vector_store_index_pending",
            message="Vector store indexing is still in progress",
            retryable=True,
            context={
                "vector_store_id": vector_store_id,
                "last_status": status_resp.status,
                "last_error": status_resp.last_error,
                "indexed_at_utc": status_resp.indexed_at_utc,
            },
        )

    try:
        status_resp = run_with_retry(
            step_name="vector_store_index_status",
            operation=_poll_status,
            ctx=mode_ctx,
            logger=logger,
            module_name=logger.name,
            policy=RetryPolicy(
                retries=max_attempts - 1,
                base_delay_seconds=float(poll_interval_seconds),
                backoff_step_seconds=0.0,
                jitter_seconds=0.0,
            ),
            retry_event="vector_store_wait_retry",
            retry_fields_builder=lambda exc, attempt: {
                "step": "vector_store_index_status",
                "attempt": attempt + 1,
                "vector_store_id": vector_store_id,
                "status": (
                    exc.context.get("last_status", "")
                    if isinstance(exc, AppError) and isinstance(exc.context, dict)
                    else last_status
                ),
                "timeout_s": timeout_seconds,
                "poll_interval_s": poll_interval_seconds,
            },
            failure_event="vector_store_wait_failed",
            failure_fields_builder=lambda exc, attempt, retryable: {
                "step": "vector_store_index_status",
                "attempt": attempt + 1,
                "retryable": retryable,
                "vector_store_id": vector_store_id,
                "status": (
                    exc.context.get("last_status", "")
                    if isinstance(exc, AppError) and isinstance(exc.context, dict)
                    else last_status
                ),
                "code": exc.code if isinstance(exc, AppError) else "",
                "error": exc.message if isinstance(exc, AppError) else str(exc),
            },
            is_retryable=lambda exc: isinstance(exc, AppError) and exc.retryable,
        )
    except AppError as exc:
        if exc.code == "vector_store_index_pending":
            logger.info(
                log_event(
                    mode_ctx,
                    role="orchestrator",
                    event="vector_store_wait_timeout",
                    module=logger.name,
                    fields={
                        "vector_store_id": vector_store_id,
                        "last_status": last_status,
                        "timeout_s": timeout_seconds,
                        "poll_interval_s": poll_interval_seconds,
                        "max_attempts": max_attempts,
                    },
                )
            )
            raise AppError(
                code="vector_store_index_timeout",
                message="Timed out waiting for vector store indexing",
                retryable=True,
                context={
                    "vector_store_id": vector_store_id,
                    "last_status": last_status or None,
                    "last_error": last_error,
                    "timeout_s": timeout_seconds,
                    "poll_interval_s": poll_interval_seconds,
                    "max_attempts": max_attempts,
                },
            ) from exc
        raise

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
            role="orchestrator",
            event="vector_store_ready",
            module=logger.name,
            fields={
                "vector_store_id": ready_state.vector_store_id,
                "status": ready_state.vector_store_status or "",
                "indexed_at_utc": ready_state.indexed_at_utc or "",
            },
        )
    )
    return ready_state


def _ensure_report_payload_complete(
    payload,
    *,
    ctx,
    file_id: str,
    stage: str,
) -> None:
    missing_fields: List[str] = []

    def _missing_text(value: Any) -> bool:
        text = str(value or "").strip()
        return not text or text.lower() in REPORT_PAYLOAD_SENTINELS

    if _missing_text(payload.title):
        missing_fields.append("title")
    if _missing_text(payload.tldr):
        missing_fields.append("tldr")
    if _missing_text(payload.commentary):
        missing_fields.append("commentary")
    insights = list(payload.insights or [])
    if len(insights) < 5:
        missing_fields.append("insights")
    for index in range(5):
        insight = insights[index] if index < len(insights) else ""
        if _missing_text(insight):
            missing_fields.append(f"insights[{index}]")
    if _missing_text(payload.quote.text):
        missing_fields.append("quote.text")
    if bool(getattr(payload, "_figure_section_enabled", True)):
        if _missing_text(payload.figure.title):
            missing_fields.append("figure.title")
        if _missing_text(payload.figure.evidence):
            missing_fields.append("figure.evidence")

    if not missing_fields:
        return

    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="report_payload_incomplete",
            module=logger.name,
            fields={
                "file_id": file_id,
                "stage": stage,
                "missing_fields": missing_fields,
            },
        )
    )
    raise AppError(
        code="report_payload_incomplete",
        message="Report payload is missing required semantic fields",
        retryable=False,
        context={
            "file_id": file_id,
            "stage": stage,
            "missing_fields": missing_fields,
        },
    )


def run_report_analysis(
    runtime: ReportRuntimeState,
    source: ReportSourceState,
    selection: ReportSelectionState,
    indexing_state: VectorStoreIndexingState,
    dependencies: ReportAnalysisDependencies,
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
                role="orchestrator",
                event="post_vector_store_parallel_start",
                module=logger.name,
                fields={
                    "file_id": runtime.file.file_id,
                    "tasks": ["taxonomy_categories", "evidence_packs"],
                    "max_workers": min(runtime.report_worker_limit, 2),
                },
            )
        )
        with ThreadPoolExecutor(
            max_workers=min(runtime.report_worker_limit, 2)
        ) as executor:
            taxonomy_future = executor.submit(
                _resolve_taxonomy,
                runtime,
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
                role="orchestrator",
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
        taxonomy_state = _resolve_taxonomy(
            runtime,
            mode_ctx,
            vector_state.vector_store_id,
            dependencies,
        )

    data.taxonomy = taxonomy_state.taxonomy
    data.region = taxonomy_state.region
    data.time_period = taxonomy_state.time_period

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
                    role="orchestrator",
                    event="doc_map_validation_halt",
                    module=logger.name,
                    fields={
                        "file_id": runtime.file.file_id,
                        "code": exc.code,
                        "message": exc.message,
                        "has_content": doc_map_summary.get("has_content")
                        if doc_map_summary
                        else None,
                        "sections_count": doc_map_summary.get("sections_count")
                        if doc_map_summary
                        else None,
                        "title_present": doc_map_summary.get("title_present")
                        if doc_map_summary
                        else None,
                        "doc_id_present": doc_map_summary.get("doc_id_present")
                        if doc_map_summary
                        else None,
                        "summary_present": doc_map_summary.get("summary_present")
                        if doc_map_summary
                        else None,
                        "not_found_reason": doc_map_summary.get("not_found_reason")
                        if doc_map_summary
                        else "",
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
    logger.info(
        log_event(
            mode_ctx,
            role="orchestrator",
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

    context_category_state = _resolve_categories_from_report_context(
        runtime,
        title=data.title,
        publisher=data.publisher,
        taxonomy_state=taxonomy_state,
        evidence_pack_paths=mode_evidence_paths,
        mode_ctx=mode_ctx,
        dependencies=dependencies,
    )
    category_assignment = context_category_state.category_assignment
    data.categories = category_assignment.categories
    for pack_name, payload in (
        ("report_context", asdict(context_category_state.report_context)),
        (
            "context_category_fit",
            _serialize_context_category_fit_payload(
                context_category_state.fit_response
            ),
        ),
    ):
        packs[pack_name] = payload
        stored_pack = dependencies.analysis_store_pack(
            AnalysisStorePackRequest(
                schema_version="1.0",
                output_dir=runtime.settings.output_dir,
                report_id=ReportId(runtime.file.file_id),
                pack_name=pack_name,
                payload=payload,
                report_slug=runtime.report_name,
            ),
            child_context(mode_ctx, task_id=f"{mode_ctx.task_id}:{pack_name}"),
        )
        mode_evidence_paths[pack_name] = stored_pack.output_path
    if vector_state.vector_store_id:
        dependencies.vector_store_update_metadata(
            VectorStoreUpdateMetadataRequest(
                schema_version="1.0",
                vector_store_id=vector_state.vector_store_id,
                metadata=VectorStoreMetadata(
                    schema_version="1.0",
                    report_id=ReportId(runtime.file.file_id),
                    report_name=runtime.report_title,
                    taxonomy=taxonomy_state.taxonomy,
                    categories=category_assignment.categories,
                    region=taxonomy_state.region,
                    time_period=taxonomy_state.time_period,
                ),
            ),
            child_context(mode_ctx, task_id=f"{mode_ctx.task_id}:metadata"),
        )
    logger.info(
        log_event(
            mode_ctx,
            role="orchestrator",
            event="context_first_categories_resolved",
            module=logger.name,
            fields={
                "file_id": runtime.file.file_id,
                "categories": category_assignment.categories,
                "category_labels": category_assignment.category_labels,
            },
        )
    )

    doc_map_pack = packs.get("doc_map", {})
    if isinstance(doc_map_pack, dict):
        doc_map_title, resolved_publisher, title_source, publisher_source = (
            resolve_doc_map_metadata(doc_map_pack)
        )
        if doc_map_title:
            data.title = doc_map_title
        if resolved_publisher:
            data.publisher = resolved_publisher
        if doc_map_title or resolved_publisher:
            logger.info(
                log_event(
                    mode_ctx,
                    role="orchestrator",
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

    base_payload = normalize_report(data, runtime.ctx)
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
                role="orchestrator",
                event="artifacts_generation_failed",
                module=logger.name,
                fields={"file_id": runtime.file.file_id, "error": str(exc)},
            )
        )

    normalized_payload = _attach_payload_analysis_metadata(
        merge_artifacts_into_payload(deepcopy(base_payload), artifacts_payload or {}),
        vector_store_id=vector_state.vector_store_id,
        evidence_paths=mode_evidence_paths,
    )
    caption_result = generate_figure_captions(
        runtime=runtime,
        selection=selection,
        payload=normalized_payload,
        doc_map=packs.get("doc_map", {})
        if isinstance(packs.get("doc_map"), dict)
        else {},
        findings_pack=packs.get("findings", {})
        if isinstance(packs.get("findings"), dict)
        else {},
        artifacts_payload=artifacts_payload or {},
        dependencies=dependencies.figure_caption,
    )
    if caption_result.pack_path:
        mode_evidence_paths["figure_captions"] = caption_result.pack_path
        base_payload = normalize_report(caption_result.payload, runtime.ctx)
        normalized_payload = _attach_payload_analysis_metadata(
            merge_artifacts_into_payload(
                deepcopy(base_payload), artifacts_payload or {}
            ),
            vector_store_id=vector_state.vector_store_id,
            evidence_paths=mode_evidence_paths,
        )
    _ensure_report_payload_complete(
        normalized_payload,
        ctx=mode_ctx,
        file_id=runtime.file.file_id,
        stage="pre_validation",
    )
    validation_report = _run_validation_with_fallback(
        runtime=runtime,
        mode_ctx=mode_ctx,
        dependencies=dependencies,
        validation_req=ValidationRequest(
            schema_version="1.0",
            report_id=ReportId(runtime.file.file_id),
            report=normalized_payload,
            artifacts=artifacts_payload or {},
            evidence_packs=packs,
            vector_store_id=vector_state.vector_store_id,
        ),
        pack_name="validation",
    )
    if validation_report.source_path:
        mode_evidence_paths["validation"] = validation_report.source_path
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

    regeneration_attempts: List[RegenerationAttemptResult] = []
    regeneration_loop_state = RegenerationLoopState(
        attempt_count=0,
        max_attempts=int(runtime.settings.validation_regeneration_max_attempts),
        final_status="pass" if validation_report.status == "pass" else "fail",
        max_reached=False,
    )
    if validation_report.status != "pass" and isinstance(artifacts_payload, dict):
        (
            artifacts_payload,
            validation_report,
            regeneration_attempts,
            regeneration_loop_state,
            regeneration_paths,
        ) = _run_validation_regeneration_loop(
            runtime=runtime,
            mode_ctx=mode_ctx,
            base_payload=base_payload,
            current_artifacts=artifacts_payload,
            current_validation_report=validation_report,
            evidence_packs=packs,
            source_status=source.text_status,
            category_labels=category_assignment.category_labels,
            vector_store_id=vector_state.vector_store_id,
            dependencies=dependencies,
        )
        mode_evidence_paths.update(regeneration_paths)
        if validation_report.source_path:
            mode_evidence_paths["validation"] = validation_report.source_path
        if regeneration_attempts:
            mode_evidence_paths["artifacts"] = regeneration_attempts[-1].artifacts_path

    normalized_payload = _attach_payload_analysis_metadata(
        merge_artifacts_into_payload(deepcopy(base_payload), artifacts_payload or {}),
        vector_store_id=vector_state.vector_store_id,
        evidence_paths=mode_evidence_paths,
    )
    data_dict = normalized_payload.to_dict()
    if artifacts_payload:
        data_dict["artifacts"] = artifacts_payload
    if validation_report:
        data_dict["validation_report"] = validation_report.to_dict()
    data_dict["report_identity_author"] = resolve_doc_map_primary_contributor(
        packs.get("doc_map", {}) if isinstance(packs.get("doc_map"), dict) else {}
    )
    data_dict["categories_display"] = category_assignment.category_labels
    data_dict["analysis_mode"] = runtime.analysis_mode
    data_dict["regeneration_loop_state"] = asdict(regeneration_loop_state)
    data_dict["regeneration_attempts"] = [
        asdict(item) for item in regeneration_attempts
    ]
    logger.info(
        log_event(
            mode_ctx,
            role="orchestrator",
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
            report_id=ReportId(runtime.file.file_id),
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
        normalized_payload=normalized_payload,
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
        regeneration_loop_state=regeneration_loop_state,
        regeneration_attempts=list(regeneration_attempts),
    )


def _run_validation_regeneration_loop(
    *,
    runtime: ReportRuntimeState,
    mode_ctx,
    base_payload,
    current_artifacts: Dict[str, Any],
    current_validation_report: ValidationReport,
    evidence_packs: Dict[str, Any],
    source_status: Dict[str, Any],
    category_labels: List[str],
    vector_store_id: Optional[str],
    dependencies: ReportAnalysisDependencies,
) -> tuple[
    Dict[str, Any],
    ValidationReport,
    List[RegenerationAttemptResult],
    RegenerationLoopState,
    Dict[str, str],
]:
    max_attempts = max(1, int(runtime.settings.validation_regeneration_max_attempts))
    attempts: List[RegenerationAttemptResult] = []
    evidence_paths: Dict[str, str] = {}
    broad_retry_used = False
    logger.info(
        log_event(
            mode_ctx,
            role="orchestrator",
            event="validation_regen_loop_start",
            module=logger.name,
            fields={
                "file_id": runtime.file.file_id,
                "max_attempts": max_attempts,
                "initial_status": current_validation_report.status,
            },
        )
    )
    final_status = current_validation_report.status
    for attempt_index in range(1, max_attempts + 1):
        if current_validation_report.status == "pass":
            final_status = "pass"
            break
        plan = _build_regeneration_plan(
            issues=current_validation_report.issues,
            artifacts=current_artifacts,
            broad_retry_available=not broad_retry_used,
        )
        logger.info(
            log_event(
                mode_ctx,
                role="orchestrator",
                event="validation_regen_plan_built",
                module=logger.name,
                fields={
                    "file_id": runtime.file.file_id,
                    "attempt_index": attempt_index,
                    "mode": plan.mode,
                    "targets": [target.target_section for target in plan.targets],
                    "unmappable_issue_count": len(plan.unmappable_issues),
                },
            )
        )
        if plan.mode == "skip":
            logger.info(
                log_event(
                    mode_ctx,
                    role="orchestrator",
                    event="validation_regen_skip_no_targets",
                    module=logger.name,
                    fields={
                        "file_id": runtime.file.file_id,
                        "attempt_index": attempt_index,
                        "issue_count": len(current_validation_report.issues),
                    },
                )
            )
            final_status = "skipped"
            break
        if plan.mode == "broad":
            broad_retry_used = True
            logger.info(
                log_event(
                    mode_ctx,
                    role="orchestrator",
                    event="validation_regen_unmappable_broad_retry",
                    module=logger.name,
                    fields={
                        "file_id": runtime.file.file_id,
                        "attempt_index": attempt_index,
                        "issue_count": len(plan.unmappable_issues),
                    },
                )
            )
        attempt_ctx = child_context(
            mode_ctx, task_id=f"{mode_ctx.task_id}:regen:{attempt_index}"
        )
        logger.info(
            log_event(
                attempt_ctx,
                role="orchestrator",
                event="validation_regen_attempt_start",
                module=logger.name,
                fields={
                    "file_id": runtime.file.file_id,
                    "attempt_index": attempt_index,
                    "mode": plan.mode,
                    "targets": [target.target_section for target in plan.targets],
                    "validation_before_status": current_validation_report.status,
                },
            )
        )
        validation_before_status = current_validation_report.status
        regeneration_response = dependencies.regenerate_artifacts(
            ArtifactRegenerationRequest(
                report_id=ReportId(runtime.file.file_id),
                report_name=runtime.report_name,
                attempt_index=attempt_index,
                plan=plan,
                current_artifacts=current_artifacts,
                doc_map=evidence_packs.get("doc_map", {}),
                evidence_packs=evidence_packs,
                settings=runtime.settings,
                ctx=attempt_ctx,
                source_status=source_status,
                categories=category_labels,
                vector_store_id=vector_store_id,
                md5=runtime.md5,
            )
        )
        current_artifacts = regeneration_response.updated_artifacts
        evidence_paths["artifacts"] = regeneration_response.artifacts_path
        evidence_paths[f"artifacts_regen_attempt_{attempt_index}"] = (
            regeneration_response.artifacts_snapshot_path
        )
        regenerated_payload = merge_artifacts_into_payload(
            deepcopy(base_payload), current_artifacts
        )
        _ensure_report_payload_complete(
            regenerated_payload,
            ctx=attempt_ctx,
            file_id=runtime.file.file_id,
            stage=f"regeneration_attempt_{attempt_index}",
        )
        current_validation_report = _run_validation_with_fallback(
            runtime=runtime,
            mode_ctx=attempt_ctx,
            dependencies=dependencies,
            validation_req=ValidationRequest(
                schema_version="1.0",
                report_id=ReportId(runtime.file.file_id),
                report=regenerated_payload,
                artifacts=current_artifacts,
                evidence_packs=evidence_packs,
                vector_store_id=vector_store_id,
            ),
            pack_name="validation",
        )
        validation_snapshot_path = _store_validation_snapshot(
            runtime=runtime,
            dependencies=dependencies,
            report=current_validation_report,
            pack_name=f"validation_regen_attempt_{attempt_index}",
            ctx=attempt_ctx,
        )
        if current_validation_report.source_path:
            evidence_paths["validation"] = current_validation_report.source_path
        evidence_paths[f"validation_regen_attempt_{attempt_index}"] = (
            validation_snapshot_path
        )
        attempt_result = RegenerationAttemptResult(
            attempt_index=attempt_index,
            plan_mode=plan.mode,
            regenerated_sections=regeneration_response.regenerated_sections,
            validation_before_status=validation_before_status,
            validation_after_status=current_validation_report.status,
            artifacts_path=regeneration_response.artifacts_path,
            artifacts_snapshot_path=regeneration_response.artifacts_snapshot_path,
            validation_path=current_validation_report.source_path,
            validation_snapshot_path=validation_snapshot_path,
        )
        attempts.append(attempt_result)
        logger.info(
            log_event(
                attempt_ctx,
                role="orchestrator",
                event="validation_regen_attempt_complete",
                module=logger.name,
                fields={
                    "file_id": runtime.file.file_id,
                    "attempt_index": attempt_index,
                    "mode": plan.mode,
                    "regenerated_sections": regeneration_response.regenerated_sections,
                    "validation_after_status": current_validation_report.status,
                },
            )
        )
        if current_validation_report.status == "pass":
            logger.info(
                log_event(
                    attempt_ctx,
                    role="orchestrator",
                    event="validation_regen_pass",
                    module=logger.name,
                    fields={
                        "file_id": runtime.file.file_id,
                        "attempt_index": attempt_index,
                    },
                )
            )
            final_status = "pass"
            break
        final_status = current_validation_report.status

    max_reached = (
        current_validation_report.status != "pass" and len(attempts) >= max_attempts
    )
    if max_reached:
        logger.info(
            log_event(
                mode_ctx,
                role="orchestrator",
                event="validation_regen_max_attempts_reached",
                module=logger.name,
                fields={
                    "file_id": runtime.file.file_id,
                    "attempt_count": len(attempts),
                    "max_attempts": max_attempts,
                    "remaining_status": current_validation_report.status,
                    "unresolved_sections": [
                        issue.affected_section
                        for issue in current_validation_report.issues
                    ],
                },
            )
        )
        final_status = "fail"
    loop_state = RegenerationLoopState(
        attempt_count=len(attempts),
        max_attempts=max_attempts,
        final_status=final_status,
        max_reached=max_reached,
    )
    return (
        current_artifacts,
        current_validation_report,
        attempts,
        loop_state,
        evidence_paths,
    )


def _run_validation_with_fallback(
    *,
    runtime: ReportRuntimeState,
    mode_ctx,
    dependencies: ReportAnalysisDependencies,
    validation_req: ValidationRequest,
    pack_name: str,
) -> ValidationReport:
    try:
        return dependencies.run_validation(
            validation_req,
            runtime.settings,
            child_context(mode_ctx, task_id=f"{mode_ctx.task_id}:{pack_name}"),
            pack_name=pack_name,
            report_name=runtime.report_name,
            md5=runtime.md5,
        )
    except Exception as exc:
        logger.info(
            log_event(
                mode_ctx,
                role="orchestrator",
                event="validation_failed",
                module=logger.name,
                fields={
                    "file_id": runtime.file.file_id,
                    "error": str(exc),
                    "mode": runtime.analysis_mode,
                    "pack_name": pack_name,
                },
            )
        )
        fallback_path = dependencies.analysis_pack_path(
            AnalysisPackPathRequest(
                schema_version="1.0",
                output_dir=runtime.settings.output_dir,
                report_id=ReportId(runtime.file.file_id),
                pack_name=pack_name,
                report_slug=runtime.report_name,
            ),
            mode_ctx,
        ).output_path
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
            source_path=fallback_path,
        )
        try:
            dependencies.analysis_store_pack(
                AnalysisStorePackRequest(
                    schema_version="1.0",
                    output_dir=runtime.settings.output_dir,
                    report_id=ReportId(runtime.file.file_id),
                    pack_name=pack_name,
                    payload=fallback_report.to_dict(),
                    report_slug=runtime.report_name,
                ),
                mode_ctx,
            )
        except Exception as store_exc:  # pragma: no cover
            logger.info(
                log_event(
                    mode_ctx,
                    role="orchestrator",
                    event="validation_store_failed",
                    module=logger.name,
                    fields={
                        "file_id": runtime.file.file_id,
                        "error": str(store_exc),
                        "mode": runtime.analysis_mode,
                    },
                )
            )
        return fallback_report


def _store_validation_snapshot(
    *,
    runtime: ReportRuntimeState,
    dependencies: ReportAnalysisDependencies,
    report: ValidationReport,
    pack_name: str,
    ctx,
) -> str:
    output_path = dependencies.analysis_pack_path(
        AnalysisPackPathRequest(
            schema_version="1.0",
            output_dir=runtime.settings.output_dir,
            report_id=ReportId(runtime.file.file_id),
            pack_name=pack_name,
            report_slug=runtime.report_name,
        ),
        ctx,
    ).output_path
    payload = report.to_dict()
    payload["source_path"] = output_path
    dependencies.analysis_store_pack(
        AnalysisStorePackRequest(
            schema_version="1.0",
            output_dir=runtime.settings.output_dir,
            report_id=ReportId(runtime.file.file_id),
            pack_name=pack_name,
            payload=payload,
            report_slug=runtime.report_name,
        ),
        ctx,
    )
    return output_path


def _build_regeneration_plan(
    *,
    issues: List[ValidationIssue],
    artifacts: Dict[str, Any],
    broad_retry_available: bool,
) -> RegenerationPlan:
    grouped: Dict[str, List[RegenerationIssue]] = {}
    unmappable: List[RegenerationIssue] = []
    for issue in issues:
        normalized = _normalize_regeneration_issue(issue, artifacts)
        target_key = normalized.repair_target or _target_section(
            normalized.affected_section
        )
        if target_key:
            grouped.setdefault(target_key, []).append(normalized)
        else:
            unmappable.append(normalized)
    if grouped:
        targets = [
            _build_target(target_key, grouped[target_key])
            for target_key in TARGET_ORDER
            if target_key in grouped
        ]
        return RegenerationPlan(
            mode="targeted",
            targets=targets,
            unmappable_issues=unmappable,
            broad_retry_allowed=broad_retry_available,
        )
    if unmappable and broad_retry_available:
        return RegenerationPlan(
            mode="broad",
            targets=[
                _build_target(target_key, list(unmappable))
                for target_key in BROAD_TARGETS
            ],
            unmappable_issues=unmappable,
            broad_retry_allowed=False,
        )
    return RegenerationPlan(
        mode="skip",
        targets=[],
        unmappable_issues=unmappable,
        broad_retry_allowed=False,
    )


def _build_target(
    target_key: str,
    issues: List[RegenerationIssue],
) -> RegenerationTarget:
    return RegenerationTarget(
        target_section=target_key,
        regenerate_steps=_target_steps(target_key),
        prompt_namespaces=_target_prompt_namespaces(target_key),
        issues=issues,
    )


def _normalize_regeneration_issue(
    issue: ValidationIssue,
    artifacts: Dict[str, Any],
) -> RegenerationIssue:
    evidence_ids, pages = _issue_grounding(issue.affected_section, artifacts)
    return RegenerationIssue(
        rule_id=issue.rule_id or _extract_rule_id(issue.message),
        affected_section=issue.affected_section,
        message=issue.message,
        severity=issue.severity,
        repair_target=issue.repair_target,
        entity_id=issue.entity_id,
        evidence_ids=evidence_ids,
        pages=pages,
    )


def _extract_rule_id(message: str) -> str:
    match = RULE_ID_RE.match(str(message or "").strip())
    if match:
        return str(match.group(1)).strip().lower()
    return "unknown"


def _target_section(affected_section: str) -> str:
    section = str(affected_section or "").strip().lower()
    if not section:
        return ""
    if (
        section.startswith("topics")
        or section.startswith("toc_entries")
        or section.startswith("toc_topics")
        or section.startswith("toc_topics_expanded")
    ):
        return "topics"
    if section in {"tldr", "executive_summary", "claim_evidence_map"}:
        return "summary"
    if section.startswith("summary"):
        return "summary"
    if section.startswith("insights"):
        return "insights_bundle"
    if section.startswith("key_data_insights"):
        return "insights_bundle"
    if section.startswith("claims_list"):
        return "insights_bundle"
    if section.startswith("quotes"):
        return "quotes"
    if section.startswith("expert_comment"):
        return "expert_comment"
    if section.startswith("linkedin_post"):
        return "linkedin_post"
    return ""


def _target_steps(target_key: str) -> List[str]:
    if target_key == "topics":
        return ["toc_entries", "toc_topics", "toc_topics_expanded"]
    if target_key == "summary":
        return ["summary"]
    if target_key == "insights_bundle":
        return ["insights_candidates", "insights_final"]
    if target_key == "quotes":
        return ["quotes"]
    if target_key == "expert_comment":
        return ["expert_comment"]
    if target_key == "linkedin_post":
        return ["linkedin_post"]
    return []


def _target_prompt_namespaces(target_key: str) -> List[str]:
    if target_key == "topics":
        return []
    if target_key == "summary":
        return ["report_vs/artifacts/regenerate/summary"]
    if target_key == "insights_bundle":
        return [
            "report_vs/artifacts/regenerate/insights_candidates",
            "report_vs/artifacts/regenerate/insights_final",
        ]
    if target_key == "quotes":
        return ["report_vs/artifacts/regenerate/quotes"]
    if target_key == "expert_comment":
        return ["report_vs/artifacts/regenerate/expert_comment"]
    if target_key == "linkedin_post":
        return ["report_vs/artifacts/regenerate/linkedin_post"]
    return []


def _issue_grounding(
    affected_section: str,
    artifacts: Dict[str, Any],
) -> tuple[List[str], List[int]]:
    section = str(affected_section or "").strip()
    if not section:
        return [], []
    lower_section = section.lower()
    if (
        lower_section.startswith("topics")
        or lower_section.startswith("toc_entries")
        or lower_section.startswith("toc_topics")
        or lower_section.startswith("toc_topics_expanded")
    ):
        topic_index = section.split(":", 1)[1].strip() if ":" in section else ""
        return _lookup_topic_grounding(topic_index, artifacts)
    if lower_section in {
        "tldr",
        "executive_summary",
        "claim_evidence_map",
    } or lower_section.startswith("summary"):
        evidence_ids: List[str] = []
        pages: List[int] = []
        summary_value = artifacts.get("summary")
        summary = summary_value if isinstance(summary_value, dict) else {}
        for claim in summary.get("claim_evidence_map") or []:
            if not isinstance(claim, dict):
                continue
            evidence_id = str(claim.get("evidence_id") or "").strip()
            if evidence_id and evidence_id not in evidence_ids:
                evidence_ids.append(evidence_id)
            for page in claim.get("pages") or []:
                if isinstance(page, int) and page not in pages:
                    pages.append(page)
        return evidence_ids, pages
    if lower_section.startswith("insights"):
        insight_id = section.split(":", 1)[1].strip() if ":" in section else ""
        return _lookup_insight_grounding(insight_id, artifacts)
    if lower_section.startswith("quotes"):
        quote_id = section.split(":", 1)[1].strip() if ":" in section else ""
        return _lookup_quote_grounding(quote_id, artifacts)
    return [], []


def _lookup_topic_grounding(
    topic_index: str,
    artifacts: Dict[str, Any],
) -> tuple[List[str], List[int]]:
    evidence_ids: List[str] = []
    pages: List[int] = []
    toc_entries = artifacts.get("toc_entries") or []
    if isinstance(toc_entries, list) and toc_entries:
        for entry in toc_entries:
            if not isinstance(entry, dict):
                continue
            section_id = str(entry.get("section_id") or "").strip()
            if topic_index and not topic_index.isdigit() and section_id != topic_index:
                continue
            if section_id and section_id not in evidence_ids:
                evidence_ids.append(section_id)
            for page in entry.get("pages") or []:
                if isinstance(page, int) and page not in pages:
                    pages.append(page)
            if topic_index and not topic_index.isdigit():
                return evidence_ids, pages
    topic_briefs = artifacts.get("toc_topics_expanded") or []
    resolved_index = int(topic_index) - 1 if topic_index.isdigit() else -1
    for idx, entry in enumerate(topic_briefs):
        if not isinstance(entry, dict):
            continue
        if resolved_index >= 0 and idx != resolved_index:
            continue
        section_id = str(entry.get("section_id") or "").strip()
        if section_id and section_id not in evidence_ids:
            evidence_ids.append(section_id)
        for page in entry.get("pages") or []:
            if isinstance(page, int) and page not in pages:
                pages.append(page)
        if resolved_index >= 0:
            break
    return evidence_ids, pages


def _lookup_insight_grounding(
    insight_id: str,
    artifacts: Dict[str, Any],
) -> tuple[List[str], List[int]]:
    evidence_ids: List[str] = []
    pages: List[int] = []
    for key in ("insights_final", "insights_candidates"):
        for entry in artifacts.get(key) or []:
            if not isinstance(entry, dict):
                continue
            entry_id = str(entry.get("id") or "").strip()
            if insight_id and entry_id != insight_id:
                continue
            evidence_id = str(entry.get("evidence_id") or "").strip()
            if evidence_id and evidence_id not in evidence_ids:
                evidence_ids.append(evidence_id)
            for page in entry.get("pages") or []:
                if isinstance(page, int) and page not in pages:
                    pages.append(page)
            if insight_id:
                break
    return evidence_ids, pages


def _lookup_quote_grounding(
    quote_id: str,
    artifacts: Dict[str, Any],
) -> tuple[List[str], List[int]]:
    evidence_ids: List[str] = []
    pages: List[int] = []
    quotes = artifacts.get("quotes_final") or []
    for idx, entry in enumerate(quotes):
        if not isinstance(entry, dict):
            continue
        candidate_ids = {
            str(entry.get("id") or "").strip(),
            str(entry.get("evidence_id") or "").strip(),
            str(idx + 1),
        }
        if quote_id and quote_id not in candidate_ids:
            continue
        evidence_id = str(entry.get("evidence_id") or "").strip()
        if evidence_id and evidence_id not in evidence_ids:
            evidence_ids.append(evidence_id)
        page = entry.get("page")
        if isinstance(page, int) and page not in pages:
            pages.append(page)
        if quote_id:
            break
    return evidence_ids, pages
