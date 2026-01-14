from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from src.contracts.config import AppSettings
from src.contracts.openai import OpenAIJSONPromptRequest, OpenAIResponseRequest
from src.contracts.prompts import PromptLoadRequest, PromptRenderRequest
from src.contracts.run_context import RunContext
from src.services import openai_service, prompt_service, report_analysis_store_service
from src.utils.errors import AppError
from src.utils.model_resolver import resolve_model
from src.utils.logging import child_context, log_event, new_run_context
from src.utils.schema_validator import validate_schema

logger = logging.getLogger("market_lense.artifact_generator")

METRIC_FIELDS = ("value", "unit", "trend", "timeframe", "geography", "segment", "sample_size", "confidence")


def generate_artifacts(
    report_id: str,
    doc_map: Dict[str, Any],
    evidence_packs: Dict[str, Any],
    settings: AppSettings,
    *,
    vector_store_id: Optional[str] = None,
    source_status: Optional[Dict[str, Any]] = None,
    ctx: Optional[RunContext] = None,
    openai_client=openai_service,
    prompt_client=prompt_service,
    analysis_store=report_analysis_store_service,
) -> Dict[str, Any]:
    ctx = ctx or new_run_context(task_id=f"artifacts:{report_id}")
    logger.info(log_event(
        ctx,
        role="generator",
        event="artifact_generate_start",
        module=logger.name,
        fields={"report_id": report_id, "has_vector_store": bool(vector_store_id)},
    ))
    safe_doc_map = doc_map or {}
    safe_evidence = evidence_packs or {}
    has_density_input = isinstance(source_status, dict) and ("text_density" in source_status or "density_threshold" in source_status)
    availability = _normalize_source_status(source_status, settings, has_density=has_density_input, vector_store_id=vector_store_id)
    if has_density_input and availability["density_threshold"] and availability["text_density"] < availability["density_threshold"]:
        availability["not_available"] = True
        availability["reason"] = availability["reason"] or "text_density_below_threshold"
    evidence_present = _has_evidence_content(safe_doc_map, safe_evidence)
    availability["evidence_present"] = evidence_present
    fallback_reasons: List[str] = []
    if availability["not_available"] and availability["reason"]:
        fallback_reasons.append(availability["reason"])
    if not evidence_present:
        fallback_reasons.append("evidence_packs_empty")
    if fallback_reasons and not vector_store_id:
        availability["not_available"] = True
        availability["reason"] = ",".join(sorted(set(fallback_reasons)))
        payload = _placeholder_artifacts(availability)
        validate_schema(payload, "artifacts", ctx)
        analysis_store.store_pack(settings.output_dir, report_id, "artifacts", payload, ctx)
        logger.info(log_event(
            ctx,
            role="generator",
            event="artifact_short_circuit",
            module=logger.name,
            fields={"report_id": report_id, "reason": availability["reason"], "text_density": availability["text_density"], "evidence_present": evidence_present},
        ))
        return payload

    base_vars = {
        "doc_map_json": _dump_json(safe_doc_map),
        "evidence_json": _dump_json(safe_evidence),
    }

    toc_ctx = child_context(ctx, task_id=f"{ctx.task_id}:toc")
    toc_result = _call_json_model(
        namespace="report_vs/artifacts/toc",
        variables=base_vars,
        settings=settings,
        ctx=toc_ctx,
        openai_client=openai_client,
        prompt_client=prompt_client,
        allow_vector_store=bool(vector_store_id),
        vector_store_id=vector_store_id,
    )
    toc_topics = _normalize_topics(toc_result.get("toc_topics"))

    summary_ctx = child_context(ctx, task_id=f"{ctx.task_id}:summary")
    summary_result = _call_json_model(
        namespace="report_vs/artifacts/summary",
        variables=base_vars,
        settings=settings,
        ctx=summary_ctx,
        openai_client=openai_client,
        prompt_client=prompt_client,
        allow_vector_store=bool(vector_store_id),
        vector_store_id=vector_store_id,
    )
    summary = _normalize_summary(summary_result.get("summary"))

    insights_ctx = child_context(ctx, task_id=f"{ctx.task_id}:insights_candidates")
    insights_candidates_result = _call_json_model(
        namespace="report_vs/artifacts/insights_candidates",
        variables=base_vars,
        settings=settings,
        ctx=insights_ctx,
        openai_client=openai_client,
        prompt_client=prompt_client,
        allow_vector_store=bool(vector_store_id),
        vector_store_id=vector_store_id,
    )
    insights_candidates = _normalize_insights(insights_candidates_result.get("insights_candidates"), prefix="candidate")
    if not insights_candidates:
        logger.info(log_event(
            ctx,
            role="generator",
            event="artifact_insights_candidates_empty",
            module=logger.name,
            fields={},
        ))

    insights_final_ctx = child_context(ctx, task_id=f"{ctx.task_id}:insights_final")
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
        allow_vector_store=bool(vector_store_id),
        vector_store_id=vector_store_id,
    )
    insights_final = _pad_insights(_normalize_insights(insights_final_result.get("insights_final"), prefix="insight"), insights_candidates)

    quote_candidates = []
    quote_pack = safe_evidence.get("quote_candidates")
    if isinstance(quote_pack, dict):
        quote_candidates = quote_pack.get("quote_candidates") or []
    elif isinstance(quote_pack, list):
        quote_candidates = quote_pack
    quotes_ctx = child_context(ctx, task_id=f"{ctx.task_id}:quotes")
    quotes_vars = {
        **base_vars,
        "quote_candidates_json": _dump_json(quote_candidates),
    }
    quotes_result = _call_json_model(
        namespace="report_vs/artifacts/quotes",
        variables=quotes_vars,
        settings=settings,
        ctx=quotes_ctx,
        openai_client=openai_client,
        prompt_client=prompt_client,
        allow_vector_store=bool(vector_store_id),
        vector_store_id=vector_store_id,
    )
    quotes_final = _normalize_quotes(quotes_result.get("quotes_final"))

    expert_ctx = child_context(ctx, task_id=f"{ctx.task_id}:expert_comment")
    expert_vars = {
        "summary_json": _dump_json(summary),
        "insights_final_json": _dump_json(insights_final),
        "quotes_json": _dump_json(quotes_final),
    }
    expert_result = _call_json_model(
        namespace="report_vs/artifacts/expert_comment",
        variables=expert_vars,
        settings=settings,
        ctx=expert_ctx,
        openai_client=openai_client,
        prompt_client=prompt_client,
        allow_vector_store=bool(vector_store_id),
        vector_store_id=vector_store_id,
    )
    expert_comment = _s(expert_result.get("expert_comment"))

    linkedin_ctx = child_context(ctx, task_id=f"{ctx.task_id}:linkedin_post")
    linkedin_vars = {
        "summary_json": _dump_json(summary),
        "insights_final_json": _dump_json(insights_final),
    }
    linkedin_result = _call_json_model(
        namespace="report_vs/artifacts/linkedin_post",
        variables=linkedin_vars,
        settings=settings,
        ctx=linkedin_ctx,
        openai_client=openai_client,
        prompt_client=prompt_client,
        allow_vector_store=bool(vector_store_id),
        vector_store_id=vector_store_id,
    )
    linkedin_post = _s(linkedin_result.get("linkedin_post"))

    artifacts_payload: Dict[str, Any] = {
        "schema_version": "1.0",
        "toc_topics": toc_topics,
        "summary": summary,
        "insights_candidates": insights_candidates,
        "insights_final": insights_final,
        "quotes_final": quotes_final,
        "expert_comment": expert_comment,
        "linkedin_post": linkedin_post,
        "source_status": availability,
    }

    try:
        validate_schema(artifacts_payload, "artifacts", ctx)
    except AppError as exc:
        logger.info(log_event(
            ctx,
            role="generator",
            event="artifact_schema_validation_failed",
            module=logger.name,
            fields={"code": exc.code, "message": exc.message},
        ))
        raise

    analysis_store.store_pack(settings.output_dir, report_id, "artifacts", artifacts_payload, ctx)

    logger.info(log_event(
        ctx,
        role="generator",
        event="artifact_generate_complete",
        module=logger.name,
        fields={"report_id": report_id, "topics": len(toc_topics), "insight_candidates": len(insights_candidates), "insights_final": len(insights_final)},
    ))
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
    prompt_set = prompt_client.load_prompt_set(PromptLoadRequest(schema_version="1.0", namespace=namespace), ctx)
    system_rendered = prompt_client.render_prompt(PromptRenderRequest(schema_version="1.0", template=prompt_set.system, variables=variables), ctx)
    user_rendered = prompt_client.render_prompt(PromptRenderRequest(schema_version="1.0", template=prompt_set.user, variables=variables), ctx)
    logger.info(log_event(
        ctx,
        role="generator",
        event="artifact_prompt_rendered",
        module=logger.name,
        fields={
            "namespace": namespace,
            "prompt_system_sha256": prompt_set.system.sha256,
            "prompt_user_sha256": prompt_set.user.sha256,
        },
    ))
    resolved_model = resolve_model(namespace, getattr(settings, "openai_models", {}), settings.openai_model)
    logger.info(log_event(
        ctx,
        role="generator",
        event="model_resolved",
        module=logger.name,
        fields={
            "namespace": namespace,
            "resolved_model": resolved_model,
            "default_model": settings.openai_model,
        },
    ))
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
    logger.info(log_event(
        ctx,
        role="generator",
        event="artifact_model_complete",
        module=logger.name,
        fields={
            "namespace": namespace,
            "model": getattr(resp, "model", resolved_model),
            "has_json": bool(resp.parsed_json),
        },
    ))
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


def _normalize_summary(value: Any) -> Dict[str, Any]:
    data = value if isinstance(value, dict) else {}
    claim_map = data.get("claim_evidence_map") if isinstance(data.get("claim_evidence_map"), list) else []
    return {
        "tldr": _s(data.get("tldr")),
        "executive_summary": _s(data.get("executive_summary")),
        "claim_evidence_map": _normalize_claims(claim_map),
    }


def _normalize_claims(items: Any) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    if not isinstance(items, list):
        return normalized
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        pages_raw = item.get("pages") if isinstance(item.get("pages"), list) else []
        pages = [int(p) for p in pages_raw if isinstance(p, int)]
        evidence_id = _s(item.get("evidence_id") or f"claim_{idx + 1}")
        normalized.append({
            "claim": _s(item.get("claim")),
            "evidence_id": evidence_id or f"claim_{idx + 1}",
            "evidence": _s(item.get("evidence")),
            "pages": pages,
        })
    return normalized


def _normalize_insights(items: Any, *, prefix: str) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    if not isinstance(items, list):
        return normalized
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        metric_raw = item.get("metric") if isinstance(item.get("metric"), dict) else {}
        metric = {key: _s(metric_raw.get(key, "")) for key in METRIC_FIELDS}
        pages_raw = item.get("pages") if isinstance(item.get("pages"), list) else []
        pages = [int(p) for p in pages_raw if isinstance(p, int)]
        evidence_id = _s(item.get("evidence_id") or item.get("id") or f"{prefix}_{idx + 1}")
        score_val = item.get("score")
        insight: Dict[str, Any] = {
            "id": _s(item.get("id") or f"{prefix}_{idx + 1}"),
            "text": _s(item.get("text")),
            "evidence_id": evidence_id or f"{prefix}_{idx + 1}",
            "evidence": _s(item.get("evidence")),
            "metric": metric,
            "pages": pages,
        }
        if isinstance(score_val, (int, float)):
            insight["score"] = float(score_val)
        normalized.append(insight)
    return normalized


def _pad_insights(insights_final: List[Dict[str, Any]], insights_candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    padded = list(insights_final)[:5]
    idx = 0
    while len(padded) < 5 and insights_candidates:
        source = insights_candidates[idx % len(insights_candidates)]
        metric_raw = source.get("metric") if isinstance(source.get("metric"), dict) else {}
        padded.append({
            "id": _s(source.get("id") or f"insight_{len(padded) + 1}"),
            "text": _s(source.get("text")),
            "evidence_id": _s(source.get("evidence_id") or source.get("id") or f"insight_{len(padded) + 1}"),
            "evidence": _s(source.get("evidence")),
            "metric": {key: _s(metric_raw.get(key, "")) for key in METRIC_FIELDS},
            "pages": [int(p) for p in source.get("pages") or [] if isinstance(p, int)],
            **({"score": float(source.get("score"))} if isinstance(source.get("score"), (int, float)) else {}),
        })
        idx += 1
    while len(padded) < 5:
        padded.append(_empty_insight(len(padded) + 1))
    return padded


def _empty_insight(idx: int) -> Dict[str, Any]:
    return {
        "id": f"insight_{idx}",
        "text": "",
        "evidence_id": f"insight_{idx}",
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
        evidence_id = _s(item.get("evidence_id") or f"quote_{idx + 1}")
        normalized.append({
            "text": _s(item.get("text")),
            "speaker": _s(item.get("speaker") or "Unknown"),
            "citation": _s(item.get("citation")),
            "page": page,
            "evidence_id": evidence_id or f"quote_{idx + 1}",
        })
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
    status.setdefault("density_threshold", float(getattr(settings, "pdf_text_min_density", 0.0)) if has_density else 0.0)
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


def _has_evidence_content(doc_map: Dict[str, Any], evidence_packs: Dict[str, Any]) -> bool:
    if isinstance(doc_map, dict):
        sections = doc_map.get("sections")
        if isinstance(sections, list) and len(sections) > 0:
            return True
    if not isinstance(evidence_packs, dict):
        return False
    for pack in evidence_packs.values():
        if not isinstance(pack, dict):
            continue
        if pack.get("findings") or pack.get("quote_candidates") or pack.get("methods") or pack.get("scope") or pack.get("limitations"):
            return True
    return False


def _placeholder_artifacts(status: Dict[str, Any]) -> Dict[str, Any]:
    reason = status.get("reason") or "not_available_from_text"
    placeholder_text = "Not available from text"
    return {
        "schema_version": "1.0",
        "toc_topics": [placeholder_text],
        "summary": {
            "tldr": placeholder_text,
            "executive_summary": placeholder_text,
            "claim_evidence_map": [{
                "claim": placeholder_text,
                "evidence_id": "not_available",
                "evidence": placeholder_text,
                "pages": [],
            }],
        },
        "insights_candidates": [{
            "id": "candidate_1",
            "text": placeholder_text,
            "evidence_id": "not_available",
            "evidence": placeholder_text,
            "metric": {key: "" for key in METRIC_FIELDS},
            "pages": [],
            "score": 0.0,
        }],
        "insights_final": [{
            "id": "insight_1",
            "text": placeholder_text,
            "evidence_id": "not_available",
            "evidence": placeholder_text,
            "metric": {key: "" for key in METRIC_FIELDS},
            "pages": [],
        }],
        "quotes_final": [{
            "text": placeholder_text,
            "speaker": "Unknown",
            "citation": reason.replace("_", " "),
            "page": 0,
            "evidence_id": "not_available",
        }],
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
