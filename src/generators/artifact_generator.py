from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

from src.contracts.config import AppSettings
from src.contracts.files import ReadTextRequest
from src.contracts.openai import OpenAIJSONPromptRequest, OpenAIResponseRequest
from src.contracts.prompts import PromptLoadRequest, PromptRenderRequest
from src.contracts.report_analysis import (
    AnalysisPackPathRequest,
    AnalysisStorePackRequest,
)
from src.contracts.run_context import RunContext
from src.contracts.schema_validation import SchemaValidateRequest
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

METRIC_FIELDS = (
    "value",
    "unit",
    "trend",
    "timeframe",
    "geography",
    "segment",
    "sample_size",
    "confidence",
)
INLINE_REFERENCE_TOKEN_RE = r"[A-Z]{1,4}-\d{1,4}"
INLINE_REFERENCE_GROUP_RE = re.compile(
    rf"[\(\[]\s*{INLINE_REFERENCE_TOKEN_RE}(?:\s*[/,;|]\s*{INLINE_REFERENCE_TOKEN_RE})*\s*[\)\]]"
)
EVIDENCE_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]*")
QUOTE_ALIAS_RE = re.compile(r"^quote[-_]?(\d+)$", re.IGNORECASE)
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
    availability = _normalize_source_status(
        source_status,
        settings,
        has_density=has_density_input,
        vector_store_id=vector_store_id,
    )
    artifact_use_vector_store = _resolve_artifact_vector_store_mode(
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
    expert_domain = _normalize_expert_domain(categories)
    cache_key = ""
    cache_meta = None
    if md5:
        cache_meta = _artifact_cache_meta(
            md5=md5,
            doc_map=safe_doc_map,
            evidence_packs=safe_evidence,
            availability=availability,
            expert_domain=expert_domain,
            retrieval_mode=_artifact_retrieval_mode(artifact_use_vector_store),
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

    base_vars = {
        "doc_map_json": _dump_json(safe_doc_map),
        "evidence_json": _dump_json(safe_evidence),
    }

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
                    _call_json_model,
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
            stage_one_results[step_name] = _call_json_model(
                namespace=namespace,
                variables=variables,
                settings=settings,
                ctx=step_ctx,
                openai_client=openai_client,
                prompt_client=prompt_client,
                allow_vector_store=artifact_use_vector_store,
                vector_store_id=vector_store_id,
            )

    toc_topics = _normalize_topics(stage_one_results.get("toc", {}).get("toc_topics"))
    summary = _normalize_summary(stage_one_results.get("summary", {}).get("summary"))
    insights_candidates = _normalize_insights(
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
    quotes_final = _normalize_quotes(
        stage_one_results.get("quotes", {}).get("quotes_final")
    )

    insights_final_vars = {
        **base_vars,
        "insights_candidates_json": _dump_json(insights_candidates),
    }
    insights_final_result = _call_json_model(
        namespace="report_vs/artifacts/insights_final",
        variables=insights_final_vars,
        settings=settings,
        ctx=insights_final_ctx,
        openai_client=openai_client,
        prompt_client=prompt_client,
        allow_vector_store=artifact_use_vector_store,
        vector_store_id=vector_store_id,
    )
    insights_final = _pad_insights(
        _normalize_insights(
            insights_final_result.get("insights_final"), prefix="insight"
        ),
        insights_candidates,
    )
    topic_briefs = _expand_topics_with_briefs(
        toc_topics=toc_topics,
        doc_map=safe_doc_map,
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
                    [
                        item
                        for item in topic_briefs
                        if _s(item.get("summary")).strip()
                    ]
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
    evidence_id_stats = _normalize_artifact_evidence_ids(
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
                _call_json_model,
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
                _call_json_model,
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
        expert_result = _call_json_model(
            namespace="report_vs/artifacts/expert_comment",
            variables=expert_vars,
            settings=settings,
            ctx=expert_ctx,
            openai_client=openai_client,
            prompt_client=prompt_client,
            allow_vector_store=artifact_use_vector_store,
            vector_store_id=vector_store_id,
        )
        linkedin_result = _call_json_model(
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
    linkedin_post = _strip_inline_reference_ids(
        _s(linkedin_result.get("linkedin_post"))
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
        "source_status": availability,
    }
    if cache_meta:
        artifacts_payload["_cache"] = {**cache_meta, "key": cache_key}

    try:
        validate_schema(
            SchemaValidateRequest(
                schema_version="1.0", payload=artifacts_payload, schema_name="artifacts"
            ),
            ctx,
        )
        validate_evidence_references(artifacts_payload, safe_evidence, ctx)
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

    _store_pack(
        analysis_store=analysis_store,
        output_dir=settings.output_dir,
        report_id=report_id,
        pack_name="artifacts",
        payload=artifacts_payload,
        ctx=ctx,
        report_slug=report_name,
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


def _call_json_model(
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
    prompt_set = prompt_client.load_prompt_set(
        PromptLoadRequest(schema_version="1.0", namespace=namespace), ctx
    )
    system_rendered = prompt_client.render_prompt(
        PromptRenderRequest(
            schema_version="1.0", template=prompt_set.system, variables=variables
        ),
        ctx,
    )
    user_rendered = prompt_client.render_prompt(
        PromptRenderRequest(
            schema_version="1.0", template=prompt_set.user, variables=variables
        ),
        ctx,
    )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="artifact_prompt_rendered",
            module=logger.name,
            fields={
                "namespace": namespace,
                "prompt_system_sha256": prompt_set.system.sha256,
                "prompt_user_sha256": prompt_set.user.sha256,
            },
        )
    )
    resolved_model = resolve_model(
        namespace, getattr(settings, "openai_models", {}), settings.openai_model
    )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="model_resolved",
            module=logger.name,
            fields={
                "namespace": namespace,
                "resolved_model": resolved_model,
                "default_model": settings.openai_model,
            },
        )
    )
    if allow_vector_store and vector_store_id:
        resp = openai_client.openai_respond_with_vector_store(
            OpenAIResponseRequest(
                schema_version="1.0",
                system_prompt=system_rendered.text,
                user_prompt=user_rendered.text,
                vector_store_id=vector_store_id,
                model=resolved_model,
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
                system_prompt=system_rendered.text,
                user_prompt=user_rendered.text,
                model=resolved_model,
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
                "model": getattr(resp, "model", resolved_model),
                "has_json": bool(resp.parsed_json),
            },
        )
    )
    return parsed


def _normalize_topics(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    topics: List[str] = []
    for item in value:
        text = _s(item).strip()
        if text:
            topics.append(text)
    return topics


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


def _normalize_summary(value: Any) -> Dict[str, Any]:
    data = value if isinstance(value, dict) else {}
    claim_map = (
        data.get("claim_evidence_map")
        if isinstance(data.get("claim_evidence_map"), list)
        else []
    )
    return {
        "tldr": _s(data.get("tldr")),
        "executive_summary": _strip_inline_reference_ids(
            _s(data.get("executive_summary"))
        ),
        "claim_evidence_map": _normalize_claims(claim_map),
    }


def _strip_inline_reference_ids(text: str) -> str:
    if not text:
        return ""
    cleaned = INLINE_REFERENCE_GROUP_RE.sub("", text)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+([,.;:!?])", r"\1", cleaned)
    cleaned = re.sub(r"([(\[])\s+", r"\1", cleaned)
    cleaned = re.sub(r"\s+([)\]])", r"\1", cleaned)
    return cleaned.strip()


def _collect_known_evidence_ids(
    *, doc_map: Dict[str, Any], evidence_packs: Dict[str, Any]
) -> tuple[set[str], Dict[str, str]]:
    known_ids: set[str] = set()
    alias_to_id: Dict[str, str] = {}

    def _register(value: Any) -> str:
        evidence_id = _s(value).strip()
        if not evidence_id:
            return ""
        known_ids.add(evidence_id)
        alias_to_id.setdefault(evidence_id.lower(), evidence_id)
        return evidence_id

    findings_pack = evidence_packs.get("findings")
    if isinstance(findings_pack, dict):
        for finding in findings_pack.get("findings") or []:
            if isinstance(finding, dict):
                _register(finding.get("id"))

    quote_pack = evidence_packs.get("quote_candidates")
    quote_candidates: list[Any]
    if isinstance(quote_pack, dict):
        quote_candidates = quote_pack.get("quote_candidates") or []
    elif isinstance(quote_pack, list):
        quote_candidates = quote_pack
    else:
        quote_candidates = []
    for idx, quote in enumerate(quote_candidates, start=1):
        if not isinstance(quote, dict):
            continue
        quote_id = _register(quote.get("id"))
        if quote_id:
            alias_to_id.setdefault(f"quote_{idx}", quote_id)
            alias_to_id.setdefault(f"quote-{idx}", quote_id)
            alias_to_id.setdefault(f"quote{idx}", quote_id)

    if isinstance(doc_map, dict):
        for section in doc_map.get("sections") or []:
            if isinstance(section, dict):
                _register(section.get("id"))

    for evidence_id in list(known_ids):
        match = re.match(r"^q(\d+)$", evidence_id, flags=re.IGNORECASE)
        if not match:
            continue
        quote_num = match.group(1)
        alias_to_id.setdefault(f"quote_{quote_num}", evidence_id)
        alias_to_id.setdefault(f"quote-{quote_num}", evidence_id)
        alias_to_id.setdefault(f"quote{quote_num}", evidence_id)

    return known_ids, alias_to_id


def _extract_evidence_id_candidates(raw_evidence_id: Any) -> List[str]:
    raw = _s(raw_evidence_id).strip()
    if not raw:
        return []

    candidates: List[str] = [raw]
    split_candidates = re.split(r"[,;|/]", raw)
    if len(split_candidates) > 1:
        candidates.extend(split_candidates)
    if raw.startswith("[") and raw.endswith("]"):
        candidates.extend(EVIDENCE_TOKEN_RE.findall(raw))
    if " " in raw:
        candidates.extend(EVIDENCE_TOKEN_RE.findall(raw))

    normalized: List[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        token = _s(candidate).strip()
        token = token.strip("\"'`")
        token = token.strip("[](){}")
        token = token.strip()
        if not token or token in seen:
            continue
        seen.add(token)
        normalized.append(token)
    return normalized


def _canonicalize_evidence_id(
    evidence_id: Any,
    *,
    known_ids: set[str],
    alias_to_id: Dict[str, str],
) -> str:
    raw = _s(evidence_id).strip()
    if not raw:
        return ""
    for candidate in _extract_evidence_id_candidates(raw):
        if not candidate:
            continue
        canonical = alias_to_id.get(candidate.lower())
        if canonical:
            return canonical
        quote_alias = QUOTE_ALIAS_RE.match(candidate)
        if quote_alias:
            alias_candidate = f"quote_{quote_alias.group(1)}"
            canonical = alias_to_id.get(alias_candidate)
            if canonical:
                return canonical
        if candidate in known_ids:
            return candidate
    return ""


def _normalize_artifact_evidence_ids(
    *,
    summary: Dict[str, Any],
    insights_candidates: List[Dict[str, Any]],
    insights_final: List[Dict[str, Any]],
    quotes_final: List[Dict[str, Any]],
    doc_map: Dict[str, Any],
    evidence_packs: Dict[str, Any],
) -> Dict[str, int]:
    known_ids, alias_to_id = _collect_known_evidence_ids(
        doc_map=doc_map, evidence_packs=evidence_packs
    )
    normalized_count = 0
    cleared_count = 0
    checked_count = 0

    def _normalize_item(item: Any) -> None:
        nonlocal normalized_count, cleared_count, checked_count
        if not isinstance(item, dict):
            return
        original = _s(item.get("evidence_id")).strip()
        checked_count += 1
        normalized = _canonicalize_evidence_id(
            original, known_ids=known_ids, alias_to_id=alias_to_id
        )
        if normalized != original:
            normalized_count += 1
            if not normalized:
                cleared_count += 1
        item["evidence_id"] = normalized

    claim_map = summary.get("claim_evidence_map")
    if isinstance(claim_map, list):
        for claim in claim_map:
            _normalize_item(claim)
    for item in insights_candidates:
        _normalize_item(item)
    for item in insights_final:
        _normalize_item(item)
    for item in quotes_final:
        _normalize_item(item)

    return {
        "known_reference_count": len(known_ids),
        "checked_count": checked_count,
        "normalized_count": normalized_count,
        "cleared_count": cleared_count,
    }


def _normalize_claims(items: Any) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    if not isinstance(items, list):
        return normalized
    for item in items:
        if not isinstance(item, dict):
            continue
        pages_raw_obj = item.get("pages")
        pages_raw = pages_raw_obj if isinstance(pages_raw_obj, list) else []
        pages = [int(p) for p in pages_raw if isinstance(p, int)]
        evidence_id = _s(item.get("evidence_id"))
        normalized.append(
            {
                "claim": _s(item.get("claim")),
                "evidence_id": evidence_id,
                "evidence": _s(item.get("evidence")),
                "pages": pages,
            }
        )
    return normalized


def _normalize_insights(items: Any, *, prefix: str) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    if not isinstance(items, list):
        return normalized
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        metric_raw = _to_dict(item.get("metric"))
        metric = {key: _s(metric_raw.get(key, "")) for key in METRIC_FIELDS}
        pages_raw_obj = item.get("pages")
        pages_raw = pages_raw_obj if isinstance(pages_raw_obj, list) else []
        pages = [int(p) for p in pages_raw if isinstance(p, int)]
        evidence_id = _s(item.get("evidence_id"))
        score_val = item.get("score")
        insight: Dict[str, Any] = {
            "id": _s(item.get("id") or f"{prefix}_{idx + 1}"),
            "text": _s(item.get("text")),
            "evidence_id": evidence_id,
            "evidence": _s(item.get("evidence")),
            "metric": metric,
            "pages": pages,
        }
        if isinstance(score_val, (int, float)):
            insight["score"] = float(score_val)
        normalized.append(insight)
    return normalized


def _pad_insights(
    insights_final: List[Dict[str, Any]], insights_candidates: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    padded = list(insights_final)[:5]
    idx = 0
    while len(padded) < 5 and insights_candidates:
        source = insights_candidates[idx % len(insights_candidates)]
        metric_raw = _to_dict(source.get("metric"))
        source_pages_raw = source.get("pages")
        source_pages = source_pages_raw if isinstance(source_pages_raw, list) else []
        source_score = source.get("score")
        padded.append(
            {
                "id": _s(source.get("id") or f"insight_{len(padded) + 1}"),
                "text": _s(source.get("text")),
                "evidence_id": _s(source.get("evidence_id")),
                "evidence": _s(source.get("evidence")),
                "metric": {key: _s(metric_raw.get(key, "")) for key in METRIC_FIELDS},
                "pages": [int(p) for p in source_pages if isinstance(p, int)],
                **(
                    {"score": float(source_score)}
                    if isinstance(source_score, (int, float))
                    else {}
                ),
            }
        )
        idx += 1
    while len(padded) < 5:
        padded.append(_empty_insight(len(padded) + 1))
    return padded


def _empty_insight(idx: int) -> Dict[str, Any]:
    return {
        "id": f"insight_{idx}",
        "text": "",
        "evidence_id": "",
        "evidence": "",
        "metric": {key: "" for key in METRIC_FIELDS},
        "pages": [],
    }


def _normalize_quotes(items: Any) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    if not isinstance(items, list):
        return normalized
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        page_val = item.get("page")
        page = page_val if isinstance(page_val, int) else 0
        evidence_id = _s(item.get("evidence_id"))
        normalized.append(
            {
                "text": _s(item.get("text")),
                "speaker": _s(item.get("speaker") or "Unknown"),
                "citation": _s(item.get("citation")),
                "page": page,
                "evidence_id": evidence_id,
            }
        )
    return normalized


def _normalize_source_status(
    source_status: Optional[Dict[str, Any]],
    settings: AppSettings,
    *,
    has_density: bool,
    vector_store_id: Optional[str] = None,
) -> Dict[str, Any]:
    status = source_status.copy() if isinstance(source_status, dict) else {}
    status.setdefault("schema_version", "1.0")
    status.setdefault("text_density", 0.0)
    status.setdefault(
        "density_threshold",
        float(getattr(settings, "pdf_text_min_density", 0.0)) if has_density else 0.0,
    )
    status.setdefault("pages_sampled", 0)
    status.setdefault("char_count", 0)
    status.setdefault("not_available", False)
    status.setdefault("reason", "")
    status.setdefault("evidence_present", True)
    if vector_store_id:
        status["density_threshold"] = 0.0
        status["not_available"] = False
        status["reason"] = ""
    return status


def _resolve_artifact_vector_store_mode(
    *, settings: AppSettings, vector_store_id: Optional[str]
) -> bool:
    return bool(vector_store_id) and bool(
        getattr(settings, "artifacts_use_vector_store", False)
    )


def _artifact_retrieval_mode(use_vector_store: bool) -> str:
    return "vector_store" if use_vector_store else "chat_json"


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


def _normalize_expert_domain(categories: Optional[List[str]]) -> str:
    if not isinstance(categories, (list, tuple)):
        return "industry"
    normalized: List[str] = []
    seen: set[str] = set()
    for raw in categories:
        value = _s(raw).strip()
        if not value:
            continue
        value_key = value.casefold()
        if value_key in seen:
            continue
        seen.add(value_key)
        normalized.append(value)
        if len(normalized) == 3:
            break
    if not normalized:
        return "industry"
    return ", ".join(normalized)


def _load_cached_artifacts(
    *,
    output_dir: str,
    report_id: str,
    report_name: Optional[str],
    cache_key: str,
    ctx: RunContext,
    analysis_store,
) -> Optional[Dict[str, Any]]:
    if not cache_key:
        return None
    path = _resolve_pack_path(
        analysis_store=analysis_store,
        output_dir=output_dir,
        report_id=report_id,
        pack_name="artifacts",
        ctx=ctx,
        report_slug=report_name,
    )
    try:
        resp = file_service.read_text(
            ReadTextRequest(schema_version="1.0", path=path), ctx
        )
    except AppError as exc:
        if exc.code == "file_not_found":
            return None
        logger.info(
            log_event(
                ctx,
                role="generator",
                event="artifact_cache_read_failed",
                module=logger.name,
                fields={"report_id": report_id, "error": exc.message},
            )
        )
        return None
    try:
        payload = json.loads(resp.content)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    cached = _to_dict(payload.get("_cache"))
    if cached.get("key") != cache_key:
        return None
    return payload


def _resolve_pack_path(
    *,
    analysis_store,
    output_dir: str,
    report_id: str,
    pack_name: str,
    ctx: RunContext,
    report_slug: Optional[str],
) -> str:
    if hasattr(analysis_store, "pack_path"):
        try:
            response = analysis_store.pack_path(
                AnalysisPackPathRequest(
                    schema_version="1.0",
                    output_dir=output_dir,
                    report_id=report_id,
                    pack_name=pack_name,
                    report_slug=report_slug,
                ),
                ctx,
            )
            if isinstance(response, str):
                return response
            output_path = getattr(response, "output_path", None)
            if isinstance(output_path, str):
                return output_path
        except TypeError:
            return str(
                analysis_store.pack_path(
                    output_dir, report_id, pack_name, report_slug=report_slug
                )
            )
    return report_analysis_store_service.pack_path(
        AnalysisPackPathRequest(
            schema_version="1.0",
            output_dir=output_dir,
            report_id=report_id,
            pack_name=pack_name,
            report_slug=report_slug,
        ),
        ctx,
    ).output_path


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
    if hasattr(analysis_store, "store_pack"):
        try:
            response = analysis_store.store_pack(
                AnalysisStorePackRequest(
                    schema_version="1.0",
                    output_dir=output_dir,
                    report_id=report_id,
                    pack_name=pack_name,
                    payload=payload,
                    report_slug=report_slug,
                ),
                ctx,
            )
            if isinstance(response, str):
                return response
            output_path = getattr(response, "output_path", None)
            if isinstance(output_path, str):
                return output_path
        except TypeError:
            return str(
                analysis_store.store_pack(
                    output_dir,
                    report_id,
                    pack_name,
                    payload,
                    ctx,
                    report_slug=report_slug,
                )
            )
    return report_analysis_store_service.store_pack(
        AnalysisStorePackRequest(
            schema_version="1.0",
            output_dir=output_dir,
            report_id=report_id,
            pack_name=pack_name,
            payload=payload,
            report_slug=report_slug,
        ),
        ctx,
    ).output_path


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


def _to_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}
