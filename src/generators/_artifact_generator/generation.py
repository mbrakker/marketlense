from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from typing import Any, Dict, List, Optional

from src.contracts.artifact_generation import ArtifactRenderTask
from src.contracts.config import AppSettings
from src.contracts.run_context import RunContext
from src.generators._artifact_generator.family_policy import (
    apply_artifact_family_policy,
)
from src.generators._artifact_generator.rendering import render_artifact_json_model
from src.generators._artifact_generator.storage import (
    _artifact_cache_meta,
    _dump_json,
    _has_evidence_content,
    _load_cached_artifacts,
    _s,
    _validate_card_tldrs,
    _validate_cover_semantics,
    assemble_artifacts_payload,
    derive_metric_spine,
    store_artifacts_payload,
)
from src.generators._artifact_generator.toc import build_toc_artifacts
from src.generators.artifact_normalization import (
    artifact_base_variables,
    artifact_quote_candidates,
    artifact_retrieval_mode,
    artifact_vector_store_enabled,
    bind_artifact_evidence_spans,
    fallback_artifact_insights_from_findings,
    normalize_artifact_evidence_ids,
    normalize_artifact_insights,
    normalize_artifact_quotes,
    normalize_artifact_source_status,
    normalize_artifact_summary,
    normalize_expert_domain,
    pad_artifact_insights,
    strip_artifact_inline_reference_ids,
)
from src.services import prompt_service, report_analysis_store_service
from src.services.schema_validator_service import validate_evidence_references
from src.utils.cache_utils import sha256_json
from src.utils.errors import AppError
from src.utils.logging import child_context, log_event, new_run_context
from src.utils.model_client_contract import require_injected_model_client

logger = logging.getLogger("market_lense.artifact_generator")

ArtifactTaskRenderer = Callable[[ArtifactRenderTask], Dict[str, Any]]
ArtifactStepExecutor = Callable[
    [Sequence[ArtifactRenderTask], ArtifactTaskRenderer, RunContext, str],
    Dict[str, Dict[str, Any]],
]


def _execute_artifact_tasks_serial(
    tasks: Sequence[ArtifactRenderTask],
    render_task: ArtifactTaskRenderer,
    ctx: RunContext,
    batch_name: str,
) -> Dict[str, Dict[str, Any]]:
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="artifact_step_batch_serial",
            module=logger.name,
            fields={
                "batch_name": batch_name,
                "steps": [task.step_name for task in tasks],
            },
        )
    )
    return {task.step_name: render_task(task) for task in tasks}


def generate_artifacts(
    report_id: str,
    doc_map: Dict[str, Any],
    evidence_packs: Dict[str, Any],
    settings: AppSettings,
    *,
    report_name: Optional[str] = None,
    md5: Optional[str] = None,
    vector_store_id: Optional[str] = None,
    source_status: Optional[Dict[str, Any]] = None,
    categories: Optional[List[str]] = None,
    category_ids: Optional[List[str]] = None,
    ctx: Optional[RunContext] = None,
    publisher_name: str = "",
    source_url: str = "",
    openai_client=None,
    prompt_client=prompt_service,
    analysis_store=report_analysis_store_service,
    artifact_step_executor: Optional[ArtifactStepExecutor] = None,
) -> Dict[str, Any]:
    ctx = ctx or new_run_context(task_id=f"artifacts:{report_id}")
    openai_client = require_injected_model_client(
        openai_client,
        scope="artifact_generator",
    )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="artifact_generate_start",
            module=logger.name,
            fields={"report_id": report_id, "has_vector_store": bool(vector_store_id)},
        )
    )
    safe_doc_map = doc_map or {}
    safe_evidence = evidence_packs or {}
    reference_evidence_packs = {**safe_evidence, "doc_map": safe_doc_map}

    def validate_required_evidence_references(
        payload: Dict[str, Any], task_ctx: RunContext
    ) -> None:
        validate_evidence_references(payload, reference_evidence_packs, task_ctx)

    has_density_input = isinstance(source_status, dict) and (
        "text_density" in source_status or "density_threshold" in source_status
    )
    availability = normalize_artifact_source_status(
        source_status,
        settings,
        has_density=has_density_input,
        vector_store_id=vector_store_id,
    )
    artifact_use_vector_store = artifact_vector_store_enabled(
        settings=settings, vector_store_id=vector_store_id
    )
    step_executor = artifact_step_executor or _execute_artifact_tasks_serial

    def render_task(task: ArtifactRenderTask) -> Dict[str, Any]:
        payload_validator = None
        if task.step_name in {"insights_candidates", "quotes"}:

            def payload_validator(payload: Dict[str, Any]) -> None:
                validate_required_evidence_references(payload, task.ctx)

        elif task.step_name == "summary":

            def payload_validator(payload: Dict[str, Any]) -> None:
                _validate_card_tldrs(
                    normalize_artifact_summary(payload.get("summary")),
                    summary_abstained=False,
                    ctx=task.ctx,
                )

        return render_artifact_json_model(
            namespace=task.namespace,
            variables=task.variables,
            settings=settings,
            ctx=task.ctx,
            openai_client=openai_client,
            prompt_client=prompt_client,
            allow_vector_store=artifact_use_vector_store,
            vector_store_id=vector_store_id,
            publisher_name=publisher_name,
            report_name=report_name or "",
            source_url=source_url,
            report_id=report_id,
            payload_validator=payload_validator,
        )

    logger.info(
        log_event(
            ctx,
            role="generator",
            event="artifact_vector_store_mode",
            module=logger.name,
            fields={
                "enabled": artifact_use_vector_store,
                "vector_store_id_present": bool(vector_store_id),
                "setting_enabled": bool(
                    getattr(settings, "artifacts_use_vector_store", False)
                ),
            },
        )
    )
    if (
        has_density_input
        and availability["density_threshold"]
        and availability["text_density"] < availability["density_threshold"]
    ):
        availability["not_available"] = True
        availability["reason"] = (
            availability["reason"] or "text_density_below_threshold"
        )
    evidence_present = _has_evidence_content(safe_doc_map, safe_evidence)
    availability["evidence_present"] = evidence_present
    expert_domain = normalize_expert_domain(categories)
    cache_key = ""
    cache_meta = None
    if md5:
        cache_meta = _artifact_cache_meta(
            md5=md5,
            doc_map=safe_doc_map,
            evidence_packs=safe_evidence,
            availability=availability,
            expert_domain=expert_domain,
            category_ids=category_ids or [],
            retrieval_mode=artifact_retrieval_mode(artifact_use_vector_store),
            settings=settings,
            prompt_client=prompt_client,
            ctx=ctx,
        )
        cache_key = sha256_json(cache_meta)
        cached = _load_cached_artifacts(
            output_dir=settings.output_dir,
            report_id=report_id,
            report_name=report_name,
            cache_key=cache_key,
            expected_cache_meta=cache_meta,
            ctx=ctx,
            analysis_store=analysis_store,
        )
        if cached is not None:
            logger.info(
                log_event(
                    ctx,
                    role="generator",
                    event="artifact_cache_hit",
                    module=logger.name,
                    fields={"report_id": report_id},
                )
            )
            return cached
    fallback_reasons: List[str] = []
    if availability["not_available"] and availability["reason"]:
        fallback_reasons.append(availability["reason"])
    if not evidence_present:
        fallback_reasons.append("evidence_packs_empty")
    if fallback_reasons and not vector_store_id:
        availability["not_available"] = True
        availability["reason"] = ",".join(sorted(set(fallback_reasons)))
        logger.info(
            log_event(
                ctx,
                role="generator",
                event="artifact_inputs_unavailable",
                module=logger.name,
                fields={
                    "report_id": report_id,
                    "reason": availability["reason"],
                    "text_density": availability["text_density"],
                    "density_threshold": availability["density_threshold"],
                    "evidence_present": evidence_present,
                },
            )
        )
        raise AppError(
            code="artifact_inputs_unavailable",
            message=(
                "Artifact generation requires extractable text or evidence-backed "
                "inputs"
            ),
            retryable=False,
            context={
                "report_id": report_id,
                "reason": availability["reason"],
                "text_density": availability["text_density"],
                "density_threshold": availability["density_threshold"],
                "evidence_present": evidence_present,
                "vector_store_id_present": bool(vector_store_id),
            },
        )

    base_vars = artifact_base_variables(safe_doc_map, safe_evidence)

    insights_final_ctx = child_context(ctx, task_id=f"{ctx.task_id}:insights_final")

    quote_candidates = artifact_quote_candidates(safe_evidence)

    toc_bundle = build_toc_artifacts(doc_map=safe_doc_map)
    toc_topics = [entry["display_title"] for entry in toc_bundle["toc_entries"]]

    stage_one_tasks = [
        ArtifactRenderTask(
            schema_version="1.0",
            step_name="summary",
            namespace="report_vs/artifacts/summary",
            variables=base_vars,
            ctx=child_context(ctx, task_id=f"{ctx.task_id}:summary"),
        ),
        ArtifactRenderTask(
            schema_version="1.0",
            step_name="insights_candidates",
            namespace="report_vs/artifacts/insights_candidates",
            variables=base_vars,
            ctx=child_context(ctx, task_id=f"{ctx.task_id}:insights_candidates"),
        ),
        ArtifactRenderTask(
            schema_version="1.0",
            step_name="quotes",
            namespace="report_vs/artifacts/quotes",
            variables={
                **base_vars,
                "quote_candidates_json": _dump_json(quote_candidates),
            },
            ctx=child_context(ctx, task_id=f"{ctx.task_id}:quotes"),
        ),
    ]
    stage_one_results = step_executor(
        stage_one_tasks,
        render_task,
        ctx,
        "stage_one",
    )

    summary = normalize_artifact_summary(
        stage_one_results.get("summary", {}).get("summary")
    )
    insights_candidates = normalize_artifact_insights(
        stage_one_results.get("insights_candidates", {}).get("insights_candidates"),
        prefix="candidate",
    )
    insights_candidates = pad_artifact_insights([], insights_candidates)
    insights_candidates = [
        candidate
        for candidate in insights_candidates
        if _s(candidate.get("text")).strip()
    ]
    initial_candidate_count = len(
        insights_candidates
    )
    if initial_candidate_count < 5:
        fallback_candidates = fallback_artifact_insights_from_findings(
            safe_evidence.get("findings")
        )
        existing_evidence_ids = {
            _s(candidate.get("evidence_id")).strip()
            for candidate in insights_candidates
            if _s(candidate.get("evidence_id")).strip()
        }
        fallback_candidates = [
            candidate
            for candidate in fallback_candidates
            if _s(candidate.get("evidence_id")).strip() not in existing_evidence_ids
        ]
        insights_candidates = pad_artifact_insights(
            insights_candidates,
            fallback_candidates,
        )
        completed_candidate_count = len(
            [
                candidate
                for candidate in insights_candidates
                if _s(candidate.get("text"))
            ]
        )
        logger.info(
            log_event(
                ctx,
                role="generator",
                event=(
                    "artifact_insights_candidates_completed_from_findings"
                    if completed_candidate_count > initial_candidate_count
                    else "artifact_insights_candidates_incomplete"
                ),
                module=logger.name,
                fields={
                    "initial_candidate_count": initial_candidate_count,
                    "candidate_count": completed_candidate_count,
                },
            )
        )
    quotes_final = normalize_artifact_quotes(
        stage_one_results.get("quotes", {}).get("quotes_final")
    )

    insights_final_vars = {
        **base_vars,
        "insights_candidates_json": _dump_json(insights_candidates),
    }
    insights_final_result = render_artifact_json_model(
        namespace="report_vs/artifacts/insights_final",
        variables=insights_final_vars,
        settings=settings,
        ctx=insights_final_ctx,
        openai_client=openai_client,
        prompt_client=prompt_client,
        allow_vector_store=artifact_use_vector_store,
        vector_store_id=vector_store_id,
        publisher_name=publisher_name,
        report_name=report_name or "",
        source_url=source_url,
        report_id=report_id,
        payload_validator=lambda payload: validate_required_evidence_references(
            payload, insights_final_ctx
        ),
    )
    insights_final = pad_artifact_insights(
        normalize_artifact_insights(
            insights_final_result.get("insights_final"), prefix="insight"
        ),
        insights_candidates,
    )
    cover_semantics_variables = {
        **base_vars,
        "summary_json": _dump_json(summary),
        "insights_final_json": _dump_json(insights_final),
        "categories_json": _dump_json(categories or []),
        "region": _s(
            safe_doc_map.get("region") or safe_doc_map.get("geography")
        ).strip(),
        "covered_period": _s(
            safe_doc_map.get("covered_period")
            or safe_doc_map.get("time_period")
            or safe_doc_map.get("period")
        ).strip(),
    }
    cover_semantics_ctx = child_context(ctx, task_id=f"{ctx.task_id}:cover_semantics")
    cover_semantics_result = render_artifact_json_model(
        namespace="report_vs/artifacts/cover_semantics",
        variables=cover_semantics_variables,
        settings=settings,
        ctx=cover_semantics_ctx,
        openai_client=openai_client,
        prompt_client=prompt_client,
        allow_vector_store=artifact_use_vector_store,
        vector_store_id=vector_store_id,
        publisher_name=publisher_name,
        report_name=report_name or "",
        source_url=source_url,
        report_id=report_id,
        payload_validator=lambda payload: _validate_cover_semantics(
            payload.get("cover_semantics"), ctx=cover_semantics_ctx
        ),
        repair_namespace="report_vs/artifacts/cover_semantics_repair",
    )
    cover_semantics = _validate_cover_semantics(
        cover_semantics_result.get("cover_semantics"),
        ctx=ctx,
    )
    evidence_id_stats = normalize_artifact_evidence_ids(
        summary=summary,
        insights_candidates=insights_candidates,
        insights_final=insights_final,
        quotes_final=quotes_final,
        doc_map=safe_doc_map,
        evidence_packs=safe_evidence,
    )
    if evidence_id_stats.get("normalized_count", 0) > 0:
        logger.info(
            log_event(
                ctx,
                role="generator",
                event="artifact_evidence_ids_normalized",
                module=logger.name,
                fields=evidence_id_stats,
            )
        )
    evidence_span_stats = bind_artifact_evidence_spans(
        summary=summary,
        insights_candidates=insights_candidates,
        insights_final=insights_final,
        quotes_final=quotes_final,
        doc_map=safe_doc_map,
        evidence_packs=safe_evidence,
    )
    if (
        evidence_span_stats.get("bound_count", 0) > 0
        or evidence_span_stats.get("unbound_count", 0) > 0
    ):
        logger.info(
            log_event(
                ctx,
                role="generator",
                event="artifact_evidence_spans_bound",
                module=logger.name,
                fields=evidence_span_stats,
            )
        )
    metric_spine = derive_metric_spine(safe_evidence)
    metric_spine_json = _dump_json(metric_spine)

    expert_ctx = child_context(ctx, task_id=f"{ctx.task_id}:expert_comment")
    expert_vars = {
        "summary_json": _dump_json(summary),
        "insights_final_json": _dump_json(insights_final),
        "quotes_json": _dump_json(quotes_final),
        "metric_spine_json": metric_spine_json,
        "expert_domain": expert_domain,
    }

    linkedin_ctx = child_context(ctx, task_id=f"{ctx.task_id}:linkedin_post")
    linkedin_vars = {
        "summary_json": _dump_json(summary),
        "insights_final_json": _dump_json(insights_final),
        "metric_spine_json": metric_spine_json,
    }
    distribution_results = step_executor(
        [
            ArtifactRenderTask(
                schema_version="1.0",
                step_name="expert_comment",
                namespace="report_vs/artifacts/expert_comment",
                variables=expert_vars,
                ctx=expert_ctx,
            ),
            ArtifactRenderTask(
                schema_version="1.0",
                step_name="linkedin_post",
                namespace="report_vs/artifacts/linkedin_post",
                variables=linkedin_vars,
                ctx=linkedin_ctx,
            ),
        ],
        render_task,
        ctx,
        "distribution",
    )
    expert_result = distribution_results.get("expert_comment", {})
    linkedin_result = distribution_results.get("linkedin_post", {})
    expert_comment = _s(expert_result.get("expert_comment"))
    linkedin_post = strip_artifact_inline_reference_ids(
        _s(linkedin_result.get("linkedin_post"))
    )
    (
        summary,
        insights_candidates,
        insights_final,
        quotes_final,
        expert_comment,
        linkedin_post,
        family_status,
    ) = apply_artifact_family_policy(
        summary=summary,
        insights_candidates=insights_candidates,
        insights_final=insights_final,
        quotes_final=quotes_final,
        expert_comment=expert_comment,
        linkedin_post=linkedin_post,
    )

    artifacts_payload = assemble_artifacts_payload(
        report_id=report_id,
        report_name=report_name,
        doc_map=safe_doc_map,
        evidence_packs=safe_evidence,
        toc_bundle=toc_bundle,
        summary=summary,
        cover_semantics=cover_semantics,
        insights_candidates=insights_candidates,
        insights_final=insights_final,
        quotes_final=quotes_final,
        expert_comment=expert_comment,
        linkedin_post=linkedin_post,
        source_status=availability,
        family_status=family_status,
        category_ids=category_ids,
        ctx=ctx,
        cache_meta={**cache_meta, "key": cache_key} if cache_meta else None,
    )
    store_artifacts_payload(
        analysis_store=analysis_store,
        output_dir=settings.output_dir,
        report_id=report_id,
        report_name=report_name,
        payload=artifacts_payload,
        ctx=ctx,
    )

    logger.info(
        log_event(
            ctx,
            role="generator",
            event="artifact_generate_complete",
            module=logger.name,
            fields={
                "report_id": report_id,
                "topics": len(toc_topics),
                "toc_entries": len(toc_bundle["toc_entries"]),
                "insight_candidates": len(insights_candidates),
                "insights_final": len(insights_final),
            },
        )
    )
    return artifacts_payload
