from __future__ import annotations

import json
import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from src.contracts.config import AppSettings
from src.contracts.files import ReadTextRequest
from src.contracts.openai import OpenAIJSONPromptRequest, OpenAIResponseRequest
from src.contracts.prompts import PromptLoadRequest, PromptRenderRequest
from src.contracts.report_analysis import AnalysisPackPathRequest, AnalysisStorePackRequest
from src.contracts.run_context import RunContext
from src.contracts.schema_validation import SchemaValidateRequest
from src.services import file_service, openai_service, prompt_service, report_analysis_store_service
from src.utils.errors import AppError
from src.utils.model_resolver import resolve_model
from src.utils.logging import child_context, log_event, new_run_context
from src.services.schema_validator_service import validate_schema
from src.utils.cache_utils import sha256_json

logger = logging.getLogger("market_lense.artifact_generator")

METRIC_FIELDS = ("value", "unit", "trend", "timeframe", "geography", "segment", "sample_size", "confidence")
INLINE_REFERENCE_TOKEN_RE = r"[A-Z]{1,4}-\d{1,4}"
INLINE_REFERENCE_GROUP_RE = re.compile(
    rf"[\(\[]\s*{INLINE_REFERENCE_TOKEN_RE}(?:\s*[/,;|]\s*{INLINE_REFERENCE_TOKEN_RE})*\s*[\)\]]"
)


@dataclass
class _GlobalArtifactLimiter:
    max_in_flight: int
    min_interval_s: float
    semaphore: threading.BoundedSemaphore
    gate_lock: threading.Lock
    next_allowed_monotonic: float


_GLOBAL_ARTIFACT_LIMITER_LOCK = threading.Lock()
_GLOBAL_ARTIFACT_LIMITER: Optional[_GlobalArtifactLimiter] = None


def _safe_int(value: object, default: int, *, min_value: int = 0) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    if parsed < min_value:
        return min_value
    return parsed


def _artifact_parallel_workers(settings: AppSettings, step_count: int) -> int:
    configured = _safe_int(getattr(settings, "artifact_parallel_workers", 4), 4, min_value=1)
    return max(1, min(configured, step_count))


def _get_artifact_global_limiter(settings: AppSettings) -> _GlobalArtifactLimiter:
    global _GLOBAL_ARTIFACT_LIMITER
    max_in_flight = _safe_int(getattr(settings, "artifact_global_max_in_flight", 2), 2, min_value=1)
    min_interval_ms = _safe_int(getattr(settings, "artifact_global_min_interval_ms", 250), 250, min_value=0)
    min_interval_s = float(min_interval_ms) / 1000.0
    with _GLOBAL_ARTIFACT_LIMITER_LOCK:
        if (
            _GLOBAL_ARTIFACT_LIMITER is None
            or _GLOBAL_ARTIFACT_LIMITER.max_in_flight != max_in_flight
            or abs(_GLOBAL_ARTIFACT_LIMITER.min_interval_s - min_interval_s) > 1e-9
        ):
            _GLOBAL_ARTIFACT_LIMITER = _GlobalArtifactLimiter(
                max_in_flight=max_in_flight,
                min_interval_s=min_interval_s,
                semaphore=threading.BoundedSemaphore(max_in_flight),
                gate_lock=threading.Lock(),
                next_allowed_monotonic=0.0,
            )
        return _GLOBAL_ARTIFACT_LIMITER


@contextmanager
def _acquire_artifact_rate_limit(settings: AppSettings, ctx: RunContext, namespace: str):
    limiter = _get_artifact_global_limiter(settings)
    wait_start = time.monotonic()
    limiter.semaphore.acquire()
    acquired_at = time.monotonic()
    in_flight_wait_ms = int((acquired_at - wait_start) * 1000)
    rate_wait_ms = 0
    try:
        if limiter.min_interval_s > 0:
            with limiter.gate_lock:
                now = time.monotonic()
                scheduled = max(now, limiter.next_allowed_monotonic)
                limiter.next_allowed_monotonic = scheduled + limiter.min_interval_s
            sleep_for = max(0.0, scheduled - time.monotonic())
            if sleep_for > 0:
                time.sleep(sleep_for)
            rate_wait_ms = int((time.monotonic() - acquired_at) * 1000)
        if in_flight_wait_ms > 0 or rate_wait_ms > 0:
            logger.info(log_event(
                ctx,
                role="generator",
                event="artifact_rate_limiter_wait",
                module=logger.name,
                fields={
                    "namespace": namespace,
                    "in_flight_wait_ms": in_flight_wait_ms,
                    "rate_wait_ms": rate_wait_ms,
                    "global_max_in_flight": limiter.max_in_flight,
                    "global_min_interval_ms": int(round(limiter.min_interval_s * 1000)),
                },
            ))
        yield
    finally:
        limiter.semaphore.release()


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
    cache_key = ""
    cache_meta = None
    if md5:
        cache_meta = _artifact_cache_meta(
            md5=md5,
            doc_map=safe_doc_map,
            evidence_packs=safe_evidence,
            availability=availability,
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
            logger.info(log_event(
                ctx,
                role="generator",
                event="artifact_cache_hit",
                module=logger.name,
                fields={"report_id": report_id},
            ))
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
            SchemaValidateRequest(schema_version="1.0", payload=payload, schema_name="artifacts"),
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

    insights_final_ctx = child_context(ctx, task_id=f"{ctx.task_id}:insights_final")

    quote_candidates = []
    quote_pack = safe_evidence.get("quote_candidates")
    if isinstance(quote_pack, dict):
        quote_candidates = quote_pack.get("quote_candidates") or []
    elif isinstance(quote_pack, list):
        quote_candidates = quote_pack

    stage_one_steps = [
        ("toc", "report_vs/artifacts/toc", base_vars),
        ("summary", "report_vs/artifacts/summary", base_vars),
        ("insights_candidates", "report_vs/artifacts/insights_candidates", base_vars),
        ("quotes", "report_vs/artifacts/quotes", {**base_vars, "quote_candidates_json": _dump_json(quote_candidates)}),
    ]
    parallel_workers = _artifact_parallel_workers(settings, len(stage_one_steps))
    limiter = _get_artifact_global_limiter(settings)
    logger.info(log_event(
        ctx,
        role="generator",
        event="artifact_parallel_config",
        module=logger.name,
        fields={
            "parallel_workers": parallel_workers,
            "global_max_in_flight": limiter.max_in_flight,
            "global_min_interval_ms": int(round(limiter.min_interval_s * 1000)),
            "parallel_step_count": len(stage_one_steps),
        },
    ))
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
                    allow_vector_store=bool(vector_store_id),
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
                    logger.info(log_event(
                        ctx,
                        role="generator",
                        event="artifact_parallel_step_failed",
                        module=logger.name,
                        fields={"step": step_name, "error": str(exc)},
                    ))
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
                allow_vector_store=bool(vector_store_id),
                vector_store_id=vector_store_id,
            )

    toc_topics = _normalize_topics(stage_one_results.get("toc", {}).get("toc_topics"))
    summary = _normalize_summary(stage_one_results.get("summary", {}).get("summary"))
    insights_candidates = _normalize_insights(stage_one_results.get("insights_candidates", {}).get("insights_candidates"), prefix="candidate")
    if not insights_candidates:
        logger.info(log_event(
            ctx,
            role="generator",
            event="artifact_insights_candidates_empty",
            module=logger.name,
            fields={},
        ))
    quotes_final = _normalize_quotes(stage_one_results.get("quotes", {}).get("quotes_final"))

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

    expert_ctx = child_context(ctx, task_id=f"{ctx.task_id}:expert_comment")
    expert_vars = {
        "summary_json": _dump_json(summary),
        "insights_final_json": _dump_json(insights_final),
        "quotes_json": _dump_json(quotes_final),
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
                allow_vector_store=bool(vector_store_id),
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
                allow_vector_store=bool(vector_store_id),
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
            allow_vector_store=bool(vector_store_id),
            vector_store_id=vector_store_id,
        )
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
    expert_comment = _s(expert_result.get("expert_comment"))
    linkedin_post = _strip_inline_reference_ids(_s(linkedin_result.get("linkedin_post")))

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
    if cache_meta:
        artifacts_payload["_cache"] = {**cache_meta, "key": cache_key}

    try:
        validate_schema(
            SchemaValidateRequest(schema_version="1.0", payload=artifacts_payload, schema_name="artifacts"),
            ctx,
        )
    except AppError as exc:
        logger.info(log_event(
            ctx,
            role="generator",
            event="artifact_schema_validation_failed",
            module=logger.name,
            fields={"code": exc.code, "message": exc.message},
        ))
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
    with _acquire_artifact_rate_limit(settings, ctx, namespace):
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
        "executive_summary": _strip_inline_reference_ids(_s(data.get("executive_summary"))),
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


def _artifact_cache_meta(
    *,
    md5: str,
    doc_map: Dict[str, Any],
    evidence_packs: Dict[str, Any],
    availability: Dict[str, Any],
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
        prompt_set = prompt_client.load_prompt_set(PromptLoadRequest(schema_version="1.0", namespace=namespace), ctx)
        prompt_meta[namespace] = {
            "prompt_system_sha256": prompt_set.system.sha256,
            "prompt_user_sha256": prompt_set.user.sha256,
            "model": resolve_model(namespace, getattr(settings, "openai_models", {}), settings.openai_model),
        }
    inputs_hash = sha256_json({
        "doc_map": doc_map,
        "evidence_packs": evidence_packs,
        "availability": availability,
    })
    return {
        "schema_version": "1.0",
        "md5": md5,
        "inputs_sha256": inputs_hash,
        "prompts": prompt_meta,
        "temperature": settings.temperature,
        "seed": settings.openai_seed,
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
        resp = file_service.read_text(ReadTextRequest(schema_version="1.0", path=path), ctx)
    except AppError as exc:
        if exc.code == "file_not_found":
            return None
        logger.info(log_event(
            ctx,
            role="generator",
            event="artifact_cache_read_failed",
            module=logger.name,
            fields={"report_id": report_id, "error": exc.message},
        ))
        return None
    try:
        payload = json.loads(resp.content)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    cached = payload.get("_cache") if isinstance(payload.get("_cache"), dict) else {}
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
            return str(analysis_store.pack_path(output_dir, report_id, pack_name, report_slug=report_slug))
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
            return str(analysis_store.store_pack(
                output_dir,
                report_id,
                pack_name,
                payload,
                ctx,
                report_slug=report_slug,
            ))
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
