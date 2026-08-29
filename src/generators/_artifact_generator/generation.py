from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import asdict
from typing import Any, Dict, List, Optional, TypedDict

from src.contracts.artifact_generation import ArtifactRenderTask
from src.contracts.config import AppSettings
from src.contracts.prompt_family_materialization import (
    PROMPT_FAMILY_MATERIALIZATION_SCHEMA_VERSION,
    PromptFamilyReuseRequest,
)
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
    normalize_artifact_editorial_plan,
    normalize_artifact_evidence_ids,
    normalize_artifact_insights,
    normalize_artifact_quotes,
    normalize_artifact_source_status,
    normalize_artifact_summary,
    normalize_expert_domain,
    select_artifact_insights,
    strip_artifact_inline_reference_ids,
)
from src.generators.prompt_preparation import prepare_prompt_bundle
from src.services import prompt_service, report_analysis_store_service
from src.services.prompt_family_materialization_service import (
    read_reusable_prompt_family,
)
from src.services.schema_validator_service import validate_evidence_references
from src.utils.cache_utils import sha256_json
from src.utils.costing import estimate_cost_usd, estimate_text_tokens
from src.utils.errors import AppError
from src.utils.logging import child_context, log_event, new_run_context
from src.utils.model_client_contract import require_injected_model_client

logger = logging.getLogger("market_lense.artifact_generator")

ArtifactTaskRenderer = Callable[[ArtifactRenderTask], Dict[str, Any]]
ArtifactStepExecutor = Callable[
    [Sequence[ArtifactRenderTask], ArtifactTaskRenderer, RunContext, str],
    Dict[str, Dict[str, Any]],
]


class PromptFamilyUsageTelemetry(TypedDict):
    """Bounded model-usage accounting for one artifact prompt family."""

    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    actual_model_calls: int
    execution_time_ms: int
    expected_input_tokens: int


class PromptFamilyReuseTelemetry(TypedDict):
    """Bounded reuse decision and usage telemetry persisted with artifacts."""

    requested_families: list[str]
    reused_families: list[str]
    regenerated_families: list[str]
    regeneration_reasons: dict[str, str]
    model_calls_avoided: int
    actual_model_calls: int
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    execution_time_ms: int
    family_usage: dict[str, PromptFamilyUsageTelemetry]


_ARTIFACT_FAMILY_ROOTS = {
    "report_vs/artifacts/editorial_plan": "editorial_plan",
    "report_vs/artifacts/summary": "summary",
    "report_vs/artifacts/insights_candidates": "insights_candidates",
    "report_vs/artifacts/quotes": "quotes_final",
    "report_vs/artifacts/insights_final": "insights_final",
    "report_vs/artifacts/cover_semantics": "cover_semantics",
    "report_vs/artifacts/expert_comment": "expert_comment",
    "report_vs/artifacts/linkedin_post": "linkedin_post",
}


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
    vector_store_content_hash: Optional[str] = None,
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
    prompt_family_reuse_reader=read_reusable_prompt_family,
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

    def validate_editorial_plan(
        payload: Dict[str, Any], task_ctx: RunContext
    ) -> None:
        normalize_artifact_editorial_plan(payload.get("editorial_plan"))
        validate_required_evidence_references(payload, task_ctx)

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

    family_reuse: dict[str, dict[str, object]] = {}
    family_outputs: dict[str, object] = {}
    family_reuse_telemetry: PromptFamilyReuseTelemetry = {
        "requested_families": [],
        "reused_families": [],
        "regenerated_families": [],
        "regeneration_reasons": {},
        "model_calls_avoided": 0,
        "actual_model_calls": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "estimated_cost_usd": 0.0,
        "execution_time_ms": 0,
        "family_usage": {},
    }

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

        return resolve_or_render_family(
            namespace=task.namespace,
            variables=task.variables,
            ctx=task.ctx,
            payload_validator=payload_validator,
        )

    def resolve_or_render_family(
        *,
        namespace: str,
        variables: Dict[str, Any],
        ctx: RunContext,
        payload_validator=None,
        repair_namespace: str = "",
    ) -> Dict[str, Any]:
        """Resolve one exact retained family before entering model recovery."""
        root_key = _ARTIFACT_FAMILY_ROOTS[namespace]
        prepared = prepare_prompt_bundle(
            namespace=namespace,
            settings=settings,
            ctx=ctx,
            prompt_client=prompt_client,
            system_variables=variables,
            user_variables=variables,
            retrieval_mode=(
                "vector_store"
                if artifact_use_vector_store and vector_store_id
                else "chat_json"
            ),
            temperature=settings.temperature,
            seed=settings.openai_seed,
            timeout_seconds=settings.openai_timeout_seconds,
            output_contract_schema_version="artifact_json:1.0",
            validator_version="artifacts_schema:3.0",
        )
        vector_provenance_verified = not artifact_use_vector_store or bool(
            str(vector_store_content_hash or "").strip()
        )
        relevant_input_hash = (
            sha256_json(
                {
                    "family_id": namespace,
                    "variables": variables,
                    "vector_store_id": (
                        vector_store_id if artifact_use_vector_store else ""
                    ),
                    "vector_store_content_hash": (
                        vector_store_content_hash if artifact_use_vector_store else ""
                    ),
                }
            )
            if vector_provenance_verified
            else ""
        )
        configuration_policy_hash = sha256_json(
            {
                "execution_policy_hash": prepared.execution_policy.policy_hash,
                "execution_policy": asdict(prepared.execution_policy.policy),
                "routing_policy": asdict(prepared.routing_decision),
            }
        )
        model_provider = str(prepared.execution_policy.policy.provider or "")
        model_policy_namespace = namespace.split("/", 1)[0]
        identity: dict[str, object] = {
            "family_schema_version": "1.0",
            "processing_version": "report_generation_checkpoint_v2",
            "prompt_content_hash": prepared.prompt_content_hash,
            "prompt_dependency_manifest": asdict(prepared.dependency_manifest),
            "execution_identity": prepared.execution_identity.execution_identity,
            "execution_identity_manifest": asdict(prepared.execution_identity),
            "model_provider": model_provider,
            "model_name": prepared.resolved_model,
            "model_policy_namespace": model_policy_namespace,
            "routing_policy_version": prepared.execution_policy.policy_hash,
            "validator_version": "artifacts_schema:3.0",
            "relevant_input_hash": relevant_input_hash,
            "configuration_policy_hash": configuration_policy_hash,
        }
        family_reuse[namespace] = identity
        requested = family_reuse_telemetry["requested_families"]
        assert isinstance(requested, list)
        requested.append(namespace)
        if md5 and vector_provenance_verified:
            reuse = prompt_family_reuse_reader(
                PromptFamilyReuseRequest(
                    schema_version=PROMPT_FAMILY_MATERIALIZATION_SCHEMA_VERSION,
                    db_path=settings.reports_db,
                    output_dir=settings.output_dir,
                    report_id=report_id,
                    report_slug=report_name or report_id,
                    source_id=md5,
                    family_id=namespace,
                    family_schema_version="1.0",
                    processing_version="report_generation_checkpoint_v2",
                    prompt_content_hash=prepared.prompt_content_hash,
                    execution_identity=prepared.execution_identity.execution_identity,
                    model_provider=model_provider,
                    model_name=prepared.resolved_model,
                    model_policy_namespace=model_policy_namespace,
                    routing_policy_version=prepared.execution_policy.policy_hash,
                    validator_version="artifacts_schema:3.0",
                    relevant_input_hash=relevant_input_hash,
                    configuration_policy_hash=configuration_policy_hash,
                ),
                ctx,
            )
        else:
            reuse = None
        if reuse is not None and reuse.reusable:
            reused = family_reuse_telemetry["reused_families"]
            assert isinstance(reused, list)
            reused.append(namespace)
            family_reuse_telemetry["model_calls_avoided"] = (
                int(family_reuse_telemetry["model_calls_avoided"]) + 1
            )
            family_reuse[namespace]["decision"] = "reused"
            family_reuse[namespace]["artifact_id"] = reuse.artifact_id
            family_reuse[namespace]["output_hash"] = reuse.output_hash
            family_outputs[namespace] = reuse.output_payload
            logger.info(
                log_event(
                    ctx,
                    role="generator",
                    event="artifact_prompt_family_reused",
                    module=logger.name,
                    fields={"family_id": namespace, "artifact_id": reuse.artifact_id},
                )
            )
            return {root_key: reuse.output_payload}
        reason = (
            reuse.reason
            if reuse is not None
            else (
                "vector_store_provenance_missing"
                if not vector_provenance_verified
                else "source_identity_missing"
            )
        )
        regenerated = family_reuse_telemetry["regenerated_families"]
        reasons = family_reuse_telemetry["regeneration_reasons"]
        assert isinstance(regenerated, list) and isinstance(reasons, dict)
        regenerated.append(namespace)
        reasons[namespace] = reason
        input_tokens = estimate_text_tokens(
            f"{prepared.system_prompt}\n{prepared.user_prompt}"
        )
        family_reuse[namespace]["decision"] = "regenerated"
        family_reuse[namespace]["regeneration_reason"] = reason

        def observe_response(response, elapsed_ms: float, mode: str) -> None:
            if mode != "primary":
                family_reuse[namespace]["recovery_attempted"] = True
            actual_input = int(getattr(response, "input_tokens", 0) or 0)
            actual_output = int(getattr(response, "output_tokens", 0) or 0)
            tool_calls = int(getattr(response, "tool_calls", 0) or 0)
            cost = estimate_cost_usd(
                str(getattr(response, "model", "") or prepared.resolved_model),
                actual_input,
                actual_output,
                tool_calls,
                settings.model_pricing,
            )
            usage = family_reuse_telemetry["family_usage"]
            assert isinstance(usage, dict)
            family_usage = usage.setdefault(
                namespace,
                {
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "estimated_cost_usd": 0.0,
                    "actual_model_calls": 0,
                    "execution_time_ms": 0,
                    "expected_input_tokens": input_tokens,
                },
            )
            assert isinstance(family_usage, dict)
            family_usage["input_tokens"] += actual_input
            family_usage["output_tokens"] += actual_output
            family_usage["estimated_cost_usd"] = round(
                float(family_usage["estimated_cost_usd"]) + cost, 8
            )
            family_usage["actual_model_calls"] += 1
            family_usage["execution_time_ms"] += max(0, round(elapsed_ms))
            family_reuse_telemetry["actual_model_calls"] = (
                int(family_reuse_telemetry["actual_model_calls"]) + 1
            )
            family_reuse_telemetry["input_tokens"] = (
                int(family_reuse_telemetry["input_tokens"]) + actual_input
            )
            family_reuse_telemetry["output_tokens"] = (
                int(family_reuse_telemetry["output_tokens"]) + actual_output
            )
            family_reuse_telemetry["estimated_cost_usd"] = round(
                float(family_reuse_telemetry["estimated_cost_usd"]) + cost, 8
            )
            family_reuse_telemetry["execution_time_ms"] = int(
                family_reuse_telemetry["execution_time_ms"]
            ) + max(0, round(elapsed_ms))

        rendered = render_artifact_json_model(
            namespace=namespace,
            variables=variables,
            settings=settings,
            ctx=ctx,
            openai_client=openai_client,
            prompt_client=prompt_client,
            allow_vector_store=artifact_use_vector_store,
            vector_store_id=vector_store_id,
            publisher_name=publisher_name,
            report_name=report_name or "",
            source_url=source_url,
            report_id=report_id,
            payload_validator=payload_validator,
            repair_namespace=repair_namespace,
            prepared_prompt_bundle=prepared,
            response_observer=observe_response,
        )
        family_outputs[namespace] = rendered.get(root_key)
        return rendered

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
    editorial_plan_ctx = child_context(ctx, task_id=f"{ctx.task_id}:editorial_plan")
    editorial_plan_result = resolve_or_render_family(
        namespace="report_vs/artifacts/editorial_plan",
        variables=base_vars,
        ctx=editorial_plan_ctx,
        payload_validator=lambda payload: validate_editorial_plan(
            payload, editorial_plan_ctx
        ),
    )
    editorial_plan = normalize_artifact_editorial_plan(
        editorial_plan_result.get("editorial_plan")
    )
    editorial_plan_json = _dump_json(editorial_plan)

    insights_final_ctx = child_context(ctx, task_id=f"{ctx.task_id}:insights_final")

    quote_candidates = artifact_quote_candidates(safe_evidence)

    toc_bundle = build_toc_artifacts(doc_map=safe_doc_map)
    toc_topics = [entry["display_title"] for entry in toc_bundle["toc_entries"]]

    stage_one_tasks = [
        ArtifactRenderTask(
            schema_version="1.0",
            step_name="summary",
            namespace="report_vs/artifacts/summary",
            variables={**base_vars, "editorial_plan_json": editorial_plan_json},
            ctx=child_context(ctx, task_id=f"{ctx.task_id}:summary"),
        ),
        ArtifactRenderTask(
            schema_version="1.0",
            step_name="insights_candidates",
            namespace="report_vs/artifacts/insights_candidates",
            variables={**base_vars, "editorial_plan_json": editorial_plan_json},
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
    insights_candidates = [
        candidate
        for candidate in insights_candidates
        if _s(candidate.get("text")).strip()
    ]
    initial_candidate_count = len(insights_candidates)
    final_insight_target_count = len(editorial_plan["themes"])
    fallback_candidates = fallback_artifact_insights_from_findings(
        safe_evidence.get("findings"),
        limit=sum(len(theme["evidence_ids"]) for theme in editorial_plan["themes"]),
    )
    insights_candidates = select_artifact_insights(
        final_insights=insights_candidates,
        candidate_insights=fallback_candidates,
        editorial_plan=editorial_plan,
    )
    completed_candidate_count = len(
        [
            candidate for candidate in insights_candidates if _s(candidate.get("text"))
        ]
    )
    if completed_candidate_count > initial_candidate_count:
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
        "editorial_plan_json": editorial_plan_json,
        "insights_candidates_json": _dump_json(insights_candidates),
        "final_insight_target_count": final_insight_target_count,
    }
    insights_final_result = resolve_or_render_family(
        namespace="report_vs/artifacts/insights_final",
        variables=insights_final_vars,
        ctx=insights_final_ctx,
        payload_validator=lambda payload: validate_required_evidence_references(
            payload, insights_final_ctx
        ),
    )
    insights_final = select_artifact_insights(
        final_insights=normalize_artifact_insights(
            insights_final_result.get("insights_final"), prefix="insight"
        ),
        candidate_insights=insights_candidates,
        editorial_plan=editorial_plan,
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
    cover_semantics_result = resolve_or_render_family(
        namespace="report_vs/artifacts/cover_semantics",
        variables=cover_semantics_variables,
        ctx=cover_semantics_ctx,
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
        "editorial_plan_json": editorial_plan_json,
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
        editorial_plan=editorial_plan,
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
        cache_meta={
            **(cache_meta or {}),
            "key": cache_key,
            "family_reuse": family_reuse,
            "family_outputs": family_outputs,
            "family_reuse_telemetry": {
                **family_reuse_telemetry,
                "requested_families": sorted(
                    family_reuse_telemetry["requested_families"]
                ),
                "reused_families": sorted(family_reuse_telemetry["reused_families"]),
                "regenerated_families": sorted(
                    family_reuse_telemetry["regenerated_families"]
                ),
                "regeneration_reasons": dict(
                    sorted(family_reuse_telemetry["regeneration_reasons"].items())
                ),
            },
        },
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
                "prompt_family_reuse": {
                    "requested": len(family_reuse_telemetry["requested_families"]),
                    "reused": len(family_reuse_telemetry["reused_families"]),
                    "regenerated": len(family_reuse_telemetry["regenerated_families"]),
                    "model_calls_avoided": family_reuse_telemetry[
                        "model_calls_avoided"
                    ],
                    "actual_model_calls": family_reuse_telemetry["actual_model_calls"],
                    "input_tokens": family_reuse_telemetry["input_tokens"],
                    "output_tokens": family_reuse_telemetry["output_tokens"],
                    "estimated_cost_usd": family_reuse_telemetry["estimated_cost_usd"],
                    "execution_time_ms": family_reuse_telemetry["execution_time_ms"],
                },
            },
        )
    )
    return artifacts_payload
