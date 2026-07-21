from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import asdict
from typing import Any, List, Optional

from src.contracts.regeneration import (
    RegenerationAttemptResult,
    RegenerationLoopState,
)
from src.contracts.report_analysis import (
    AnalysisStorePackRequest,
)
from src.contracts.report_generation import (
    ReportAnalysisState,
    ReportRuntimeState,
    ReportSelectionState,
    ReportSourceState,
)
from src.contracts.semantic_ids import ReportId
from src.contracts.validation import ValidationRequest
from src.contracts.vector_store import (
    VectorStoreMetadata,
    VectorStoreUpdateMetadataRequest,
)
from src.generators.figure_caption_generator import generate_figure_captions
from src.generators.normalize_generator import normalize_report
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
from src.orchestrators._report_analysis_orchestrator.artifact_batches import (
    ArtifactTaskRenderer,
    _artifact_batch_workers,
    _execute_artifact_step_batch,
)
from src.orchestrators._report_analysis_orchestrator.payload import (
    REPORT_PAYLOAD_SENTINELS,
    _attach_payload_analysis_metadata,
    _ensure_report_payload_complete,
    _serialize_context_category_fit_payload,
)
from src.orchestrators._report_analysis_orchestrator.regeneration_plan import (
    BROAD_TARGETS,
    RULE_ID_RE,
    TARGET_ORDER,
    _build_regeneration_plan,
    _build_target,
    _extract_rule_id,
    _issue_grounding,
    _lookup_insight_grounding,
    _lookup_quote_grounding,
    _lookup_topic_grounding,
    _normalize_regeneration_issue,
    _target_prompt_namespaces,
    _target_section,
    _target_steps,
)
from src.orchestrators._report_analysis_orchestrator.shared import logger
from src.orchestrators._report_analysis_orchestrator.validation import (
    _evaluate_and_store_public_editorial_quality,
    _merge_public_editorial_quality,
    _run_validation_regeneration_loop,
    _run_validation_with_fallback,
    _store_validation_snapshot,
)
from src.orchestrators._report_analysis_orchestrator.vector_store import (
    VECTOR_STORE_FAILED_STATUSES,
    VECTOR_STORE_POLL_INTERVAL_SECONDS,
    VECTOR_STORE_POLL_SCHEDULE_SECONDS,
    VECTOR_STORE_READY_STATUSES,
    _await_vector_store_indexing,
    _is_vector_store_ready,
)
from src.utils.errors import AppError
from src.utils.logging import child_context, log_event

__all__ = [
    "run_report_analysis",
    "ArtifactTaskRenderer",
    "BROAD_TARGETS",
    "REPORT_PAYLOAD_SENTINELS",
    "RULE_ID_RE",
    "TARGET_ORDER",
    "VECTOR_STORE_FAILED_STATUSES",
    "VECTOR_STORE_POLL_INTERVAL_SECONDS",
    "VECTOR_STORE_POLL_SCHEDULE_SECONDS",
    "VECTOR_STORE_READY_STATUSES",
    "_artifact_batch_workers",
    "_attach_payload_analysis_metadata",
    "_await_vector_store_indexing",
    "_build_regeneration_plan",
    "_build_target",
    "_ensure_report_payload_complete",
    "_execute_artifact_step_batch",
    "_evaluate_and_store_public_editorial_quality",
    "_extract_rule_id",
    "_is_vector_store_ready",
    "_issue_grounding",
    "_lookup_insight_grounding",
    "_lookup_quote_grounding",
    "_lookup_topic_grounding",
    "_merge_public_editorial_quality",
    "_normalize_regeneration_issue",
    "_run_validation_regeneration_loop",
    "_run_validation_with_fallback",
    "_serialize_context_category_fit_payload",
    "_store_validation_snapshot",
    "_target_prompt_namespaces",
    "_target_section",
    "_target_steps",
]


def _artifact_family_statuses(artifacts_payload: Any) -> dict[str, str]:
    """Return only durable artifact-family state, never generated artifact content."""

    if not isinstance(artifacts_payload, dict):
        return {}
    statuses: dict[str, str] = {}
    for family, artifact in sorted(
        artifacts_payload.items(), key=lambda item: str(item[0])
    ):
        if isinstance(artifact, dict):
            status = (
                artifact.get("status")
                or artifact.get("validation_status")
                or artifact.get("state")
                or "present"
            )
        else:
            status = "present"
        statuses[str(family)] = str(status)
    return statuses


def run_report_analysis(
    runtime: ReportRuntimeState,
    source: ReportSourceState,
    selection: ReportSelectionState,
    indexing_state: VectorStoreIndexingState,
    dependencies: ReportAnalysisDependencies,
    *,
    taxonomy_openai_client=None,
    category_fit_openai_client=None,
    evidence_pack_openai_client=None,
    artifact_openai_client=None,
    validation_openai_client=None,
    regeneration_openai_client=None,
    figure_caption_openai_client=None,
) -> ReportAnalysisState:
    if runtime.execution_plan_hash:
        logger.info(
            log_event(
                runtime.ctx,
                role="orchestrator",
                event="minimal_execution_plan_consumed",
                module=logger.name,
                fields={
                    "plan_hash": runtime.execution_plan_hash,
                    "intent": runtime.execution_plan_intent,
                    "required_stages": runtime.planned_stages,
                    "consumer_stage": "analysis_complete",
                    "file_id": runtime.file.file_id,
                },
            )
        )
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
                openai_client=taxonomy_openai_client,
            )
            evidence_future = executor.submit(
                dependencies.generate_evidence_packs,
                report_id=runtime.file.file_id,
                report_name=runtime.report_name,
                vector_store_id=vector_state.vector_store_id,
                settings=runtime.settings,
                ctx=evidence_ctx,
                md5=runtime.md5,
                publisher_name=runtime.publisher_name,
                source_url=runtime.source_url,
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
            openai_client=taxonomy_openai_client,
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
                publisher_name=runtime.publisher_name,
                source_url=runtime.source_url,
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
        openai_client=category_fit_openai_client,
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
        artifact_ctx = child_context(mode_ctx, task_id=f"{mode_ctx.task_id}:artifacts")
        artifact_kwargs["artifact_step_executor"] = (
            lambda tasks, render_task, batch_ctx, batch_name: (
                _execute_artifact_step_batch(
                    runtime.settings,
                    tasks,
                    render_task,
                    batch_ctx,
                    batch_name,
                )
            )
        )
        artifacts_payload = dependencies.generate_artifacts(
            report_id=runtime.file.file_id,
            report_name=runtime.report_name,
            doc_map=packs.get("doc_map", {}),
            evidence_packs=packs,
            settings=runtime.settings,
            vector_store_id=vector_state.vector_store_id,
            source_status=source.text_status,
            categories=category_assignment.category_labels,
            ctx=artifact_ctx,
            md5=runtime.md5,
            publisher_name=runtime.publisher_name,
            source_url=runtime.source_url,
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
    except AppError as exc:
        logger.info(
            log_event(
                mode_ctx,
                role="orchestrator",
                event="artifacts_generation_failed",
                module=logger.name,
                fields={"file_id": runtime.file.file_id, "error": str(exc)},
            )
        )
        raise
    except Exception as exc:
        logger.exception(
            log_event(
                mode_ctx,
                role="orchestrator",
                event="artifacts_generation_failed",
                module=logger.name,
                fields={"file_id": runtime.file.file_id, "error": str(exc)},
            )
        )
        raise AppError(
            code="artifacts_generation_failed",
            message="Artifact generation failed before report validation",
            cause=exc,
            retryable=False,
            context={"file_id": runtime.file.file_id},
        ) from exc

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
        llm_client=figure_caption_openai_client,
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
        artifacts=artifacts_payload or {},
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
            publisher_name=runtime.publisher_name,
            report_name=runtime.source_report_name or runtime.report_title,
            source_url=runtime.source_url,
        ),
        pack_name="validation",
        openai_client=validation_openai_client,
    )
    editorial_validation, editorial_before_path = (
        _evaluate_and_store_public_editorial_quality(
            runtime=runtime,
            dependencies=dependencies,
            artifacts=artifacts_payload or {},
            pack_name="public_editorial_quality_before",
            ctx=mode_ctx,
        )
    )
    validation_report = _merge_public_editorial_quality(
        validation_report, editorial_validation
    )
    _store_validation_snapshot(
        runtime=runtime,
        dependencies=dependencies,
        report=validation_report,
        pack_name="validation",
        ctx=mode_ctx,
    )
    if editorial_before_path:
        mode_evidence_paths["public_editorial_quality_before"] = editorial_before_path
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
            validation_openai_client=validation_openai_client,
            regeneration_openai_client=regeneration_openai_client,
        )
        mode_evidence_paths.update(regeneration_paths)
        if validation_report.source_path:
            mode_evidence_paths["validation"] = validation_report.source_path
        if regeneration_attempts:
            mode_evidence_paths["artifacts"] = regeneration_attempts[-1].artifacts_path

    _, editorial_after_path = _evaluate_and_store_public_editorial_quality(
        runtime=runtime,
        dependencies=dependencies,
        artifacts=artifacts_payload or {},
        pack_name="public_editorial_quality_after",
        ctx=mode_ctx,
    )
    if editorial_after_path:
        mode_evidence_paths["public_editorial_quality_after"] = editorial_after_path

    normalized_payload = _attach_payload_analysis_metadata(
        merge_artifacts_into_payload(deepcopy(base_payload), artifacts_payload or {}),
        vector_store_id=vector_state.vector_store_id,
        evidence_paths=mode_evidence_paths,
    )
    data_dict = normalized_payload.to_dict()
    if artifacts_payload:
        data_dict["artifacts"] = artifacts_payload
    data_dict["evidence_packs"] = packs
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
    logger.info(
        log_event(
            mode_ctx,
            role="orchestrator",
            event="report_payload_ready",
            module=logger.name,
            fields={
                "file_id": runtime.file.file_id,
                "output_schema_version": normalized_payload.schema_version,
                "artifact_family_statuses": _artifact_family_statuses(
                    artifacts_payload
                ),
                "evidence_pack_names": sorted(str(name) for name in packs),
                "evidence_pack_count": len(packs),
                "validation_status": validation_report.status
                if validation_report
                else "not_run",
                "validation_issue_count": len(validation_report.issues)
                if validation_report
                else 0,
                "category_count": len(category_assignment.categories),
                "retained_snapshot_path": str(snapshot_path),
            },
        )
    )

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
