from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

from src.contracts.config import AppSettings
from src.contracts.openai import OpenAIJSONPromptRequest, OpenAIResponseRequest
from src.contracts.prompts import PromptLoadRequest
from src.contracts.report_analysis import (
    AnalysisPackPathRequest,
    AnalysisStorePackRequest,
)
from src.contracts.run_context import RunContext
from src.contracts.schema_validation import SchemaValidateRequest
from src.generators.artifact_normalization import (
    METRIC_FIELDS,
    artifact_base_variables,
    artifact_quote_candidates,
    artifact_retrieval_mode,
    artifact_vector_store_enabled,
    normalize_artifact_evidence_ids,
    normalize_artifact_insights,
    normalize_artifact_quotes,
    normalize_artifact_source_status,
    normalize_artifact_summary,
    normalize_artifact_topics,
    normalize_expert_domain,
    pad_artifact_insights,
    strip_artifact_inline_reference_ids,
)
from src.generators.analysis_pack_cache import (
    CachedPackAdaptResult,
    load_cached_pack,
)
from src.generators.prompt_preparation import prepare_prompt_bundle
from src.generators.analysis_store_adapter import (
    resolve_pack_path as resolve_analysis_pack_path,
    store_pack as store_analysis_pack,
)
from src.services import (
    file_service,
    openai_service,
    prompt_service,
    report_analysis_store_service,
)
from src.utils.errors import AppError
from src.utils.model_resolver import resolve_model
from src.utils.logging import child_context, log_event, new_run_context
from src.utils.coercion import coerce_int
from src.services.schema_validator_service import (
    validate_evidence_references,
    validate_schema,
)
from src.utils.cache_utils import sha256_json

logger = logging.getLogger("market_lense.artifact_generator")

TOPIC_TOKEN_STOPWORDS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "by",
    "for",
    "from",
    "in",
    "into",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}
TOPIC_BRIEF_MAX_KEY_POINTS = 4


def _artifact_parallel_workers(settings: AppSettings, step_count: int) -> int:
    configured = coerce_int(
        getattr(settings, "artifact_parallel_workers", 4), 4, min_value=1
    )
    return max(1, min(configured, step_count))


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
    ctx: Optional[RunContext] = None,
    openai_client=openai_service,
    prompt_client=prompt_service,
    analysis_store=report_analysis_store_service,
) -> Dict[str, Any]:
    ctx = ctx or new_run_context(task_id=f"artifacts:{report_id}")
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
        payload = _placeholder_artifacts(availability)
        if cache_meta and isinstance(payload, dict):
            payload = dict(payload)
            payload["_cache"] = {**cache_meta, "key": cache_key}
        validate_schema(
            SchemaValidateRequest(
                schema_version="1.0", payload=payload, schema_name="artifacts"
            ),
            ctx,
        )
        _store_pack(
            analysis_store=analysis_store,
            output_dir=settings.output_dir,
            report_id=report_id,
            pack_name="artifacts",
            payload=payload,
            ctx=ctx,
            report_slug=report_name,
        )
        logger.info(
            log_event(
                ctx,
                role="generator",
                event="artifact_short_circuit",
                module=logger.name,
                fields={
                    "report_id": report_id,
                    "reason": availability["reason"],
                    "text_density": availability["text_density"],
                    "evidence_present": evidence_present,
                },
            )
        )
        return payload

    base_vars = artifact_base_variables(safe_doc_map, safe_evidence)

    insights_final_ctx = child_context(ctx, task_id=f"{ctx.task_id}:insights_final")

    quote_candidates: list[Any] = []
    quote_pack = safe_evidence.get("quote_candidates")
    if isinstance(quote_pack, dict):
        quote_candidates = quote_pack.get("quote_candidates") or []
    elif isinstance(quote_pack, list):
        quote_candidates = quote_pack

    stage_one_steps = [
        ("toc", "report_vs/artifacts/toc", base_vars),
        ("summary", "report_vs/artifacts/summary", base_vars),
        ("insights_candidates", "report_vs/artifacts/insights_candidates", base_vars),
        (
            "quotes",
            "report_vs/artifacts/quotes",
            {**base_vars, "quote_candidates_json": _dump_json(quote_candidates)},
        ),
    ]
    parallel_workers = _artifact_parallel_workers(settings, len(stage_one_steps))
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="artifact_parallel_config",
            module=logger.name,
            fields={
                "parallel_workers": parallel_workers,
                "parallel_step_count": len(stage_one_steps),
            },
        )
    )
    stage_one_results: Dict[str, Dict[str, Any]] = {}
    if parallel_workers > 1 and len(stage_one_steps) > 1:
        with ThreadPoolExecutor(max_workers=parallel_workers) as executor:
            futures = {}
            for step_name, namespace, variables in stage_one_steps:
                step_ctx = child_context(ctx, task_id=f"{ctx.task_id}:{step_name}")
                future = executor.submit(
                    render_artifact_json_model,
                    namespace=namespace,
                    variables=variables,
                    settings=settings,
                    ctx=step_ctx,
                    openai_client=openai_client,
                    prompt_client=prompt_client,
                    allow_vector_store=artifact_use_vector_store,
                    vector_store_id=vector_store_id,
                )
                futures[future] = step_name
            first_error: Optional[Exception] = None
            for future in as_completed(futures):
                step_name = futures[future]
                try:
                    stage_one_results[step_name] = future.result()
                except Exception as exc:  # pragma: no cover - defensive fallback
                    if first_error is None:
                        first_error = exc
                    logger.info(
                        log_event(
                            ctx,
                            role="generator",
                            event="artifact_parallel_step_failed",
                            module=logger.name,
                            fields={"step": step_name, "error": str(exc)},
                        )
                    )
            if first_error is not None:
                for future in futures:
                    future.cancel()
                raise first_error
    else:
        for step_name, namespace, variables in stage_one_steps:
            step_ctx = child_context(ctx, task_id=f"{ctx.task_id}:{step_name}")
            stage_one_results[step_name] = render_artifact_json_model(
                namespace=namespace,
                variables=variables,
                settings=settings,
                ctx=step_ctx,
                openai_client=openai_client,
                prompt_client=prompt_client,
                allow_vector_store=artifact_use_vector_store,
                vector_store_id=vector_store_id,
            )

    toc_topics = normalize_artifact_topics(
        stage_one_results.get("toc", {}).get("toc_topics")
    )
    summary = normalize_artifact_summary(
        stage_one_results.get("summary", {}).get("summary")
    )
    insights_candidates = normalize_artifact_insights(
        stage_one_results.get("insights_candidates", {}).get("insights_candidates"),
        prefix="candidate",
    )
    if not insights_candidates:
        logger.info(
            log_event(
                ctx,
                role="generator",
                event="artifact_insights_candidates_empty",
                module=logger.name,
                fields={},
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
    )
    insights_final = pad_artifact_insights(
        normalize_artifact_insights(
            insights_final_result.get("insights_final"), prefix="insight"
        ),
        insights_candidates,
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

    expert_ctx = child_context(ctx, task_id=f"{ctx.task_id}:expert_comment")
    expert_vars = {
        "summary_json": _dump_json(summary),
        "insights_final_json": _dump_json(insights_final),
        "quotes_json": _dump_json(quotes_final),
        "expert_domain": expert_domain,
    }

    linkedin_ctx = child_context(ctx, task_id=f"{ctx.task_id}:linkedin_post")
    linkedin_vars = {
        "summary_json": _dump_json(summary),
        "insights_final_json": _dump_json(insights_final),
    }
    if parallel_workers > 1:
        with ThreadPoolExecutor(max_workers=2) as executor:
            expert_future = executor.submit(
                render_artifact_json_model,
                namespace="report_vs/artifacts/expert_comment",
                variables=expert_vars,
                settings=settings,
                ctx=expert_ctx,
                openai_client=openai_client,
                prompt_client=prompt_client,
                allow_vector_store=artifact_use_vector_store,
                vector_store_id=vector_store_id,
            )
            linkedin_future = executor.submit(
                render_artifact_json_model,
                namespace="report_vs/artifacts/linkedin_post",
                variables=linkedin_vars,
                settings=settings,
                ctx=linkedin_ctx,
                openai_client=openai_client,
                prompt_client=prompt_client,
                allow_vector_store=artifact_use_vector_store,
                vector_store_id=vector_store_id,
            )
            expert_result = expert_future.result()
            linkedin_result = linkedin_future.result()
    else:
        expert_result = render_artifact_json_model(
            namespace="report_vs/artifacts/expert_comment",
            variables=expert_vars,
            settings=settings,
            ctx=expert_ctx,
            openai_client=openai_client,
            prompt_client=prompt_client,
            allow_vector_store=artifact_use_vector_store,
            vector_store_id=vector_store_id,
        )
        linkedin_result = render_artifact_json_model(
            namespace="report_vs/artifacts/linkedin_post",
            variables=linkedin_vars,
            settings=settings,
            ctx=linkedin_ctx,
            openai_client=openai_client,
            prompt_client=prompt_client,
            allow_vector_store=artifact_use_vector_store,
            vector_store_id=vector_store_id,
        )
    expert_comment = _s(expert_result.get("expert_comment"))
    linkedin_post = strip_artifact_inline_reference_ids(
        _s(linkedin_result.get("linkedin_post"))
    )

    artifacts_payload = assemble_artifacts_payload(
        report_id=report_id,
        report_name=report_name,
        doc_map=safe_doc_map,
        evidence_packs=safe_evidence,
        toc_topics=toc_topics,
        summary=summary,
        insights_candidates=insights_candidates,
        insights_final=insights_final,
        quotes_final=quotes_final,
        expert_comment=expert_comment,
        linkedin_post=linkedin_post,
        source_status=availability,
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
                "insight_candidates": len(insights_candidates),
                "insights_final": len(insights_final),
            },
        )
    )
    return artifacts_payload

def assemble_artifacts_payload(
    *,
    report_id: str,
    report_name: Optional[str],
    doc_map: Dict[str, Any],
    evidence_packs: Dict[str, Any],
    toc_topics: List[str],
    summary: Dict[str, Any],
    insights_candidates: List[Dict[str, Any]],
    insights_final: List[Dict[str, Any]],
    quotes_final: List[Dict[str, Any]],
    expert_comment: str,
    linkedin_post: str,
    source_status: Dict[str, Any],
    ctx: RunContext,
    cache_meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    del report_id, report_name
    topic_briefs = _expand_topics_with_briefs(
        toc_topics=toc_topics,
        doc_map=doc_map,
        summary=summary,
        insights_final=insights_final,
    )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="artifact_topic_briefs_built",
            module=logger.name,
            fields={
                "topic_count": len(toc_topics),
                "brief_count": len(topic_briefs),
                "briefs_with_summary": len(
                    [item for item in topic_briefs if _s(item.get("summary")).strip()]
                ),
                "briefs_with_key_points": len(
                    [
                        item
                        for item in topic_briefs
                        if isinstance(item.get("key_points"), list)
                        and len(item.get("key_points") or []) > 0
                    ]
                ),
            },
        )
    )
    evidence_id_stats = normalize_artifact_evidence_ids(
        summary=summary,
        insights_candidates=insights_candidates,
        insights_final=insights_final,
        quotes_final=quotes_final,
        doc_map=doc_map,
        evidence_packs=evidence_packs,
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
    artifacts_payload: Dict[str, Any] = {
        "schema_version": "1.0",
        "toc_topics": toc_topics,
        "toc_topics_expanded": topic_briefs,
        "summary": summary,
        "insights_candidates": insights_candidates,
        "insights_final": insights_final,
        "quotes_final": quotes_final,
        "expert_comment": expert_comment,
        "linkedin_post": linkedin_post,
        "source_status": source_status,
    }
    if cache_meta:
        artifacts_payload["_cache"] = dict(cache_meta)
    try:
        validate_schema(
            SchemaValidateRequest(
                schema_version="1.0",
                payload=artifacts_payload,
                schema_name="artifacts",
            ),
            ctx,
        )
        validate_evidence_references(artifacts_payload, evidence_packs, ctx)
    except AppError as exc:
        logger.info(
            log_event(
                ctx,
                role="generator",
                event="artifact_schema_validation_failed",
                module=logger.name,
                fields={"code": exc.code, "message": exc.message},
            )
        )
        raise
    return artifacts_payload


def store_artifacts_payload(
    *,
    analysis_store,
    output_dir: str,
    report_id: str,
    report_name: Optional[str],
    payload: Dict[str, Any],
    ctx: RunContext,
    pack_name: str = "artifacts",
) -> str:
    output_path = _store_pack(
        analysis_store=analysis_store,
        output_dir=output_dir,
        report_id=report_id,
        pack_name=pack_name,
        payload=payload,
        ctx=ctx,
        report_slug=report_name,
    )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="artifact_payload_stored",
            module=logger.name,
            fields={
                "report_id": report_id,
                "pack_name": pack_name,
                "path": output_path,
            },
        )
    )
    return output_path


def render_artifact_json_model(
    *,
    namespace: str,
    variables: Dict[str, Any],
    settings: AppSettings,
    ctx: RunContext,
    openai_client,
    prompt_client,
    allow_vector_store: bool,
    vector_store_id: Optional[str],
) -> Dict[str, Any]:
    prompt_bundle = prepare_prompt_bundle(
        namespace=namespace,
        settings=settings,
        ctx=ctx,
        prompt_client=prompt_client,
        system_variables=variables,
        user_variables=variables,
    )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="artifact_prompt_rendered",
            module=logger.name,
            fields={
                "namespace": namespace,
                "system_path": prompt_bundle.prompt_set.system.path,
                "user_path": prompt_bundle.prompt_set.user.path,
                "prompt_system_sha256": prompt_bundle.prompt_set.system.sha256,
                "prompt_user_sha256": prompt_bundle.prompt_set.user.sha256,
                "system_prompt": prompt_bundle.system_prompt,
                "user_prompt": prompt_bundle.user_prompt,
            },
        )
    )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="model_resolved",
            module=logger.name,
            fields={
                "namespace": namespace,
                "resolved_model": prompt_bundle.resolved_model,
                "default_model": settings.openai_model,
            },
        )
    )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="artifact_model_request",
            module=logger.name,
            fields={
                "namespace": namespace,
                "model": prompt_bundle.resolved_model,
                "temperature": settings.temperature,
                "seed": settings.openai_seed,
                "retrieval_mode": (
                    "vector_store"
                    if allow_vector_store and vector_store_id
                    else "chat_json"
                ),
                "vector_store_id": vector_store_id or "",
            },
        )
    )
    if allow_vector_store and vector_store_id:
        resp = openai_client.openai_respond_with_vector_store(
            OpenAIResponseRequest(
                schema_version="1.0",
                system_prompt=prompt_bundle.system_prompt,
                user_prompt=prompt_bundle.user_prompt,
                vector_store_id=vector_store_id,
                model=prompt_bundle.resolved_model,
                temperature=settings.temperature,
                api_key=settings.openai_api_key,
                seed=settings.openai_seed,
                timeout_seconds=settings.openai_timeout_seconds,
                cost_ledger_path=settings.cost_ledger_path,
                cost_daily_path=settings.cost_daily_path,
                model_pricing=settings.model_pricing,
            ),
            ctx,
        )
    else:
        resp = openai_client.openai_chat_json(
            OpenAIJSONPromptRequest(
                schema_version="1.0",
                system_prompt=prompt_bundle.system_prompt,
                user_prompt=prompt_bundle.user_prompt,
                model=prompt_bundle.resolved_model,
                temperature=settings.temperature,
                api_key=settings.openai_api_key,
                seed=settings.openai_seed,
                timeout_seconds=settings.openai_timeout_seconds,
                cost_ledger_path=settings.cost_ledger_path,
                cost_daily_path=settings.cost_daily_path,
                model_pricing=settings.model_pricing,
            ),
            ctx,
        )
    parsed = resp.parsed_json if isinstance(resp.parsed_json, dict) else {}
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="artifact_model_complete",
            module=logger.name,
            fields={
                "namespace": namespace,
                "model": getattr(resp, "model", prompt_bundle.resolved_model),
                "has_json": bool(resp.parsed_json),
                "request_id": getattr(resp, "request_id", "") or "",
                "raw_response": getattr(resp, "text", "") or "",
            },
        )
    )
    return parsed


def _normalize_topic_lookup_text(value: Any) -> str:
    text = _s(value).strip().lower()
    if not text:
        return ""
    collapsed = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", collapsed).strip()


def _topic_tokens(value: Any) -> List[str]:
    normalized = _normalize_topic_lookup_text(value)
    if not normalized:
        return []
    return [
        token
        for token in normalized.split(" ")
        if token and token not in TOPIC_TOKEN_STOPWORDS
    ]


def _coerce_topic_key_points(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    points: List[str] = []
    for item in value:
        if isinstance(item, dict):
            text = _s(
                item.get("text")
                or item.get("point")
                or item.get("summary")
                or item.get("value")
            ).strip()
        else:
            text = _s(item).strip()
        if text and text not in points:
            points.append(text)
    return points


def _coerce_topic_pages(value: Any) -> List[int]:
    if not isinstance(value, list):
        return []
    pages: List[int] = []
    for page in value:
        if isinstance(page, int):
            pages.append(page)
    return pages


def _doc_map_sections_for_topics(doc_map: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not isinstance(doc_map, dict):
        return []
    candidate = doc_map
    for key in ("doc_map", "docmap", "docMap"):
        wrapped = doc_map.get(key)
        if isinstance(wrapped, dict):
            candidate = wrapped
            break
    sections_raw = candidate.get("sections")
    if not isinstance(sections_raw, list):
        return []
    sections: List[Dict[str, Any]] = []
    for idx, raw_section in enumerate(sections_raw):
        if not isinstance(raw_section, dict):
            continue
        title = _s(
            raw_section.get("title")
            or raw_section.get("heading")
            or raw_section.get("name")
        ).strip()
        section_id = _s(raw_section.get("id")).strip()
        summary = _s(raw_section.get("summary")).strip()
        key_points = _coerce_topic_key_points(raw_section.get("key_points"))
        pages = _coerce_topic_pages(raw_section.get("pages"))
        sections.append(
            {
                "section_id": section_id,
                "title": title,
                "summary": summary,
                "key_points": key_points,
                "pages": pages,
                "title_norm": _normalize_topic_lookup_text(title),
                "id_norm": _normalize_topic_lookup_text(section_id),
                "title_tokens": _topic_tokens(title),
                "index": idx,
            }
        )
    return sections


def _topic_match_score(
    *,
    topic_norm: str,
    topic_tokens: List[str],
    section: Dict[str, Any],
    prefer_index: int,
) -> int:
    score = 0
    title_norm = _s(section.get("title_norm")).strip()
    id_norm = _s(section.get("id_norm")).strip()
    if topic_norm and (topic_norm == title_norm or topic_norm == id_norm):
        score += 100
    elif topic_norm and (
        (topic_norm in title_norm and title_norm)
        or (title_norm in topic_norm and topic_norm)
        or (topic_norm in id_norm and id_norm)
    ):
        score += 75

    title_tokens = set(section.get("title_tokens") or [])
    topic_tokens_set = set(topic_tokens)
    if topic_tokens_set and title_tokens:
        overlap = len(topic_tokens_set & title_tokens)
        coverage = overlap / max(1, len(topic_tokens_set))
        score += int(round(coverage * 45))
    if prefer_index == int(section.get("index", -1)):
        score += 12
    if _s(section.get("summary")).strip():
        score += 3
    return score


def _select_topic_section(
    *,
    topic: str,
    topic_index: int,
    sections: List[Dict[str, Any]],
    used_indexes: set[int],
) -> Optional[Dict[str, Any]]:
    if not sections:
        return None
    topic_norm = _normalize_topic_lookup_text(topic)
    tokens = _topic_tokens(topic)
    preferred_indexes = [
        idx for idx in range(len(sections)) if idx not in used_indexes
    ] or list(range(len(sections)))
    best_idx = -1
    best_score = -1
    for idx in preferred_indexes:
        section = sections[idx]
        score = _topic_match_score(
            topic_norm=topic_norm,
            topic_tokens=tokens,
            section=section,
            prefer_index=topic_index,
        )
        if score > best_score:
            best_score = score
            best_idx = idx
    if best_idx < 0:
        return None
    if best_score >= 35:
        used_indexes.add(best_idx)
        return sections[best_idx]
    if topic_index < len(sections) and topic_index not in used_indexes:
        used_indexes.add(topic_index)
        return sections[topic_index]
    return None


def _text_matches_topic(text: str, topic: str) -> bool:
    text_norm = _normalize_topic_lookup_text(text)
    topic_norm = _normalize_topic_lookup_text(topic)
    if not text_norm or not topic_norm:
        return False
    if topic_norm in text_norm:
        return True
    topic_tokens = set(_topic_tokens(topic))
    text_tokens = set(_topic_tokens(text))
    if not topic_tokens or not text_tokens:
        return False
    overlap = len(topic_tokens & text_tokens)
    required = max(1, min(2, len(topic_tokens)))
    return overlap >= required


def _dedupe_non_empty_text(values: List[str], *, limit: int) -> List[str]:
    deduped: List[str] = []
    seen: set[str] = set()
    for value in values:
        text = _s(value).strip()
        if not text:
            continue
        key = _normalize_topic_lookup_text(text)
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(text)
        if len(deduped) >= limit:
            break
    return deduped


def _topic_brief_from_claims(topic: str, summary: Dict[str, Any]) -> tuple[str, List[str]]:
    claim_map = summary.get("claim_evidence_map")
    if not isinstance(claim_map, list):
        return "", []
    matching_claims: List[str] = []
    claim_points: List[str] = []
    for claim in claim_map:
        if not isinstance(claim, dict):
            continue
        claim_text = _s(claim.get("claim")).strip()
        evidence_text = _s(claim.get("evidence")).strip()
        if not _text_matches_topic(f"{claim_text} {evidence_text}", topic):
            continue
        if claim_text:
            matching_claims.append(claim_text)
        if evidence_text:
            claim_points.append(evidence_text)
    summary_text = matching_claims[0] if matching_claims else ""
    points = _dedupe_non_empty_text(claim_points, limit=TOPIC_BRIEF_MAX_KEY_POINTS)
    return summary_text, points


def _topic_points_from_insights(topic: str, insights_final: List[Dict[str, Any]]) -> List[str]:
    if not isinstance(insights_final, list):
        return []
    matched: List[str] = []
    for insight in insights_final:
        if not isinstance(insight, dict):
            continue
        insight_text = _s(insight.get("text")).strip()
        if insight_text and _text_matches_topic(insight_text, topic):
            matched.append(insight_text)
    return _dedupe_non_empty_text(matched, limit=TOPIC_BRIEF_MAX_KEY_POINTS)


def _expand_topics_with_briefs(
    *,
    toc_topics: List[str],
    doc_map: Dict[str, Any],
    summary: Dict[str, Any],
    insights_final: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    if not toc_topics:
        return []
    sections = _doc_map_sections_for_topics(doc_map)
    used_indexes: set[int] = set()
    expanded: List[Dict[str, Any]] = []
    for index, raw_topic in enumerate(toc_topics):
        topic = _s(raw_topic).strip()
        if not topic:
            continue
        section = _select_topic_section(
            topic=topic,
            topic_index=index,
            sections=sections,
            used_indexes=used_indexes,
        )
        section_summary = _s(section.get("summary")).strip() if section else ""
        section_points = (
            section.get("key_points")
            if section and isinstance(section.get("key_points"), list)
            else []
        )
        key_points = _dedupe_non_empty_text(
            [_s(point) for point in section_points], limit=TOPIC_BRIEF_MAX_KEY_POINTS
        )
        summary_text = section_summary

        claim_summary, claim_points = _topic_brief_from_claims(topic, summary)
        if not summary_text:
            summary_text = claim_summary
        key_points = _dedupe_non_empty_text(
            key_points + claim_points, limit=TOPIC_BRIEF_MAX_KEY_POINTS
        )

        insight_points = _topic_points_from_insights(topic, insights_final)
        if not summary_text and insight_points:
            summary_text = insight_points[0]
        key_points = _dedupe_non_empty_text(
            key_points + insight_points, limit=TOPIC_BRIEF_MAX_KEY_POINTS
        )

        if not summary_text and key_points:
            summary_text = key_points[0]

        expanded.append(
            {
                "topic": topic,
                "summary": summary_text,
                "key_points": key_points,
                "section_id": _s(section.get("section_id")).strip() if section else "",
                "section_title": _s(section.get("title")).strip() if section else "",
                "pages": section.get("pages") if section else [],
            }
        )
    return expanded


def _has_evidence_content(
    doc_map: Dict[str, Any], evidence_packs: Dict[str, Any]
) -> bool:
    if isinstance(doc_map, dict):
        sections = doc_map.get("sections")
        if isinstance(sections, list) and len(sections) > 0:
            return True
    if not isinstance(evidence_packs, dict):
        return False
    for pack in evidence_packs.values():
        if not isinstance(pack, dict):
            continue
        if (
            pack.get("findings")
            or pack.get("quote_candidates")
            or pack.get("methods")
            or pack.get("scope")
            or pack.get("limitations")
            or pack.get("key_metrics")
            or pack.get("risk_register")
            or pack.get("recommendations")
            or pack.get("contradictions")
        ):
            return True
    return False


def _artifact_cache_meta(
    *,
    md5: str,
    doc_map: Dict[str, Any],
    evidence_packs: Dict[str, Any],
    availability: Dict[str, Any],
    expert_domain: str,
    retrieval_mode: str,
    settings: AppSettings,
    prompt_client,
    ctx: RunContext,
) -> Dict[str, Any]:
    prompt_meta: Dict[str, Any] = {}
    namespaces = [
        "report_vs/artifacts/toc",
        "report_vs/artifacts/summary",
        "report_vs/artifacts/insights_candidates",
        "report_vs/artifacts/insights_final",
        "report_vs/artifacts/quotes",
        "report_vs/artifacts/expert_comment",
        "report_vs/artifacts/linkedin_post",
    ]
    for namespace in namespaces:
        prompt_set = prompt_client.load_prompt_set(
            PromptLoadRequest(schema_version="1.0", namespace=namespace), ctx
        )
        prompt_meta[namespace] = {
            "prompt_system_sha256": prompt_set.system.sha256,
            "prompt_user_sha256": prompt_set.user.sha256,
            "model": resolve_model(
                namespace, getattr(settings, "openai_models", {}), settings.openai_model
            ),
        }
    inputs_hash = sha256_json(
        {
            "doc_map": doc_map,
            "evidence_packs": evidence_packs,
            "availability": availability,
            "expert_domain": expert_domain,
        }
    )
    return {
        "schema_version": "1.0",
        "md5": md5,
        "inputs_sha256": inputs_hash,
        "prompts": prompt_meta,
        "temperature": settings.temperature,
        "seed": settings.openai_seed,
        "retrieval_mode": retrieval_mode,
    }

def _load_cached_artifacts(
    *,
    output_dir: str,
    report_id: str,
    report_name: Optional[str],
    cache_key: str,
    ctx: RunContext,
    analysis_store,
) -> Optional[Dict[str, Any]]:
    def _log_read_failed(exc: AppError, path: str) -> None:
        del path
        logger.info(
            log_event(
                ctx,
                role="generator",
                event="artifact_cache_read_failed",
                module=logger.name,
                fields={"report_id": report_id, "error": exc.message},
            )
        )

    result = load_cached_pack(
        cache_key=cache_key,
        ctx=ctx,
        resolve_path=lambda: _resolve_pack_path(
            analysis_store=analysis_store,
            output_dir=output_dir,
            report_id=report_id,
            pack_name="artifacts",
            ctx=ctx,
            report_slug=report_name,
        ),
        read_text=file_service.read_text,
        on_read_failed=_log_read_failed,
        adapt_payload=lambda payload, path: CachedPackAdaptResult(
            schema_version="1.0",
            status="hit",
            value=payload,
        ),
    )
    return result.value if result.status == "hit" else None


def _resolve_pack_path(
    *,
    analysis_store,
    output_dir: str,
    report_id: str,
    pack_name: str,
    ctx: RunContext,
    report_slug: Optional[str],
) -> str:
    return resolve_analysis_pack_path(
        analysis_store=analysis_store,
        request=AnalysisPackPathRequest(
            schema_version="1.0",
            output_dir=output_dir,
            report_id=report_id,
            pack_name=pack_name,
            report_slug=report_slug,
        ),
        ctx=ctx,
    )


def _store_pack(
    *,
    analysis_store,
    output_dir: str,
    report_id: str,
    pack_name: str,
    payload: Dict[str, Any],
    ctx: RunContext,
    report_slug: Optional[str],
) -> str:
    return store_analysis_pack(
        analysis_store=analysis_store,
        request=AnalysisStorePackRequest(
            schema_version="1.0",
            output_dir=output_dir,
            report_id=report_id,
            pack_name=pack_name,
            payload=payload,
            report_slug=report_slug,
        ),
        ctx=ctx,
    )


def _placeholder_artifacts(status: Dict[str, Any]) -> Dict[str, Any]:
    reason = status.get("reason") or "not_available_from_text"
    placeholder_text = "Not available from text"
    return {
        "schema_version": "1.0",
        "toc_topics": [placeholder_text],
        "toc_topics_expanded": [],
        "summary": {
            "tldr": placeholder_text,
            "executive_summary": placeholder_text,
            "claim_evidence_map": [
                {
                    "claim": placeholder_text,
                    "evidence_id": "not_available",
                    "evidence": placeholder_text,
                    "pages": [],
                }
            ],
        },
        "insights_candidates": [
            {
                "id": "candidate_1",
                "text": placeholder_text,
                "evidence_id": "not_available",
                "evidence": placeholder_text,
                "metric": {key: "" for key in METRIC_FIELDS},
                "pages": [],
                "score": 0.0,
            }
        ],
        "insights_final": [
            {
                "id": "insight_1",
                "text": placeholder_text,
                "evidence_id": "not_available",
                "evidence": placeholder_text,
                "metric": {key: "" for key in METRIC_FIELDS},
                "pages": [],
            }
        ],
        "quotes_final": [
            {
                "text": placeholder_text,
                "speaker": "Unknown",
                "citation": reason.replace("_", " "),
                "page": 0,
                "evidence_id": "not_available",
            }
        ],
        "expert_comment": placeholder_text,
        "linkedin_post": placeholder_text,
        "source_status": {
            **status,
            "not_available": True,
            "reason": reason,
            "evidence_present": bool(status.get("evidence_present", False)),
        },
    }


def _dump_json(data: Any) -> str:
    try:
        return json.dumps(data, ensure_ascii=False)
    except Exception:
        return ""


def _s(value: Any) -> str:
    if value is None:
        return ""
    return value if isinstance(value, str) else str(value)

