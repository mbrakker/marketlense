from __future__ import annotations

import json
import logging
from typing import Callable, Dict, Optional

from src.contracts.config import AppSettings
from src.contracts.files import ReadTextRequest
from src.contracts.openai import OpenAIResponseRequest, OpenAIResponseResult
from src.contracts.prompts import PromptLoadRequest
from src.contracts.run_context import RunContext
from src.services import file_service
from src.services import openai_service
from src.services import prompt_service
from src.services import report_analysis_store_service
from src.utils.logging import child_context, log_event, new_run_context
from src.services.schema_validator_service import validate_schema
from src.utils.errors import AppError
from src.utils.model_resolver import resolve_model
from src.utils.cache_utils import sha256_json

logger = logging.getLogger("market_lense.evidence_pack_generator")


def generate_evidence_packs(
    report_id: str,
    report_name: str,
    vector_store_id: str,
    settings: AppSettings,
    ctx: Optional[RunContext] = None,
    md5: Optional[str] = None,
    *,
    openai_client=openai_service,
    prompt_client=prompt_service,
    analysis_store=report_analysis_store_service,
) -> Dict[str, dict]:
    ctx = ctx or new_run_context(task_id=f"evidence_pack:{report_id}")
    logger.info(log_event(
        ctx,
        role="generator",
        event="evidence_pack_start",
        module=logger.name,
        fields={"report_id": report_id, "vector_store_id": vector_store_id},
    ))
    steps = [
        ("doc_map", "doc_map", "doc_map"),
        ("scope", "evidence_packs/scope", "evidence_pack"),
        ("methods", "evidence_packs/methods", "evidence_pack"),
        ("findings", "evidence_packs/findings", "evidence_pack"),
        ("limitations", "evidence_packs/limitations", "evidence_pack"),
        ("quote_candidates", "evidence_packs/quote_candidates", "evidence_pack"),
    ]
    results: Dict[str, dict] = {}
    for step_name, prompt_ns, schema in steps:
        step_ctx = child_context(ctx, task_id=f"{ctx.task_id}:{step_name}")
        results[step_name] = _generate_pack(
            report_id=report_id,
            report_name=report_name,
            vector_store_id=vector_store_id,
            prompt_namespace=f"report_vs/{prompt_ns}",
            schema_name="doc_map" if schema == "doc_map" else "evidence_pack",
            settings=settings,
            ctx=step_ctx,
            md5=md5,
            openai_client=openai_client,
            prompt_client=prompt_client,
            analysis_store=analysis_store,
            pack_name=step_name,
        )
        if step_name == "doc_map":
            summary = _summarize_doc_map(results[step_name])
            if not summary["has_content"]:
                reason = summary["not_found_reason"] or "no_content"
                logger.info(log_event(
                    step_ctx,
                    role="generator",
                    event="doc_map_validation_failed",
                    module=logger.name,
                    fields={
                        "report_id": report_id,
                        "vector_store_id": vector_store_id,
                        "sections_count": summary["sections_count"],
                        "title_present": summary["title_present"],
                        "doc_id_present": summary["doc_id_present"],
                        "summary_present": summary["summary_present"],
                        "not_found_reason": summary["not_found_reason"],
                    },
                ))
                raise AppError(
                    code="doc_map_empty",
                    message=f"doc_map_empty:{reason}",
                    retryable=False,
                    context=summary,
                )
    logger.info(log_event(
        ctx,
        role="generator",
        event="evidence_pack_complete",
        module=logger.name,
        fields={"report_id": report_id, "packs": list(results.keys())},
    ))
    return results


def _generate_pack(
    *,
    report_id: str,
    report_name: str,
    vector_store_id: str,
    prompt_namespace: str,
    schema_name: str,
    settings: AppSettings,
    ctx: RunContext,
    md5: Optional[str],
    openai_client,
    prompt_client,
    analysis_store,
    pack_name: str,
) -> dict:
    logger.info(log_event(
        ctx,
        role="generator",
        event="evidence_pack_step_start",
        module=logger.name,
        fields={"report_id": report_id, "pack": pack_name, "prompt_namespace": prompt_namespace},
    ))
    prompt_set = prompt_client.load_prompt_set(PromptLoadRequest(schema_version="1.0", namespace=prompt_namespace), ctx)
    system_prompt = prompt_set.system.text
    user_prompt = prompt_set.user.text
    resolved_model = resolve_model(prompt_namespace, getattr(settings, "openai_models", {}), settings.openai_model)
    cache_meta = None
    cache_key = ""
    if md5:
        cache_meta = {
            "schema_version": "1.0",
            "md5": md5,
            "pack_name": pack_name,
            "schema_name": schema_name,
            "prompt_system_sha256": prompt_set.system.sha256,
            "prompt_user_sha256": prompt_set.user.sha256,
            "model": resolved_model,
            "temperature": settings.temperature,
            "seed": settings.openai_seed,
        }
        cache_key = sha256_json(cache_meta)
        if settings.vector_store_keep:
            cached = _load_cached_pack(
                output_dir=settings.output_dir,
                report_id=report_id,
                pack_name=pack_name,
                report_name=report_name,
                cache_key=cache_key,
                ctx=ctx,
                analysis_store=analysis_store,
            )
            if cached is not None:
                logger.info(log_event(
                    ctx,
                    role="generator",
                    event="evidence_pack_cache_hit",
                    module=logger.name,
                    fields={"report_id": report_id, "pack": pack_name},
                ))
                return cached
    logger.info(log_event(
        ctx,
        role="generator",
        event="model_resolved",
        module=logger.name,
        fields={
            "namespace": prompt_namespace,
            "resolved_model": resolved_model,
            "default_model": settings.openai_model,
        },
    ))
    parsed_json = None
    not_found_reason = ""
    try:
        resp: OpenAIResponseResult = openai_client.openai_respond_with_vector_store(
            OpenAIResponseRequest(
                schema_version="1.0",
                system_prompt=system_prompt,
                user_prompt=user_prompt,
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
        parsed_json = resp.parsed_json
        if parsed_json is None:
            not_found_reason = "model_returned_no_json"
        else:
            try:
                validate_schema(parsed_json, schema_name, ctx)
            except AppError as exc:
                not_found_reason = f"schema_validation_failed:{exc.code}"
    except AppError as exc:
        not_found_reason = exc.code
        parsed_json = None
    result_payload = parsed_json or _empty_payload(schema_name, not_found_reason)
    if cache_meta and isinstance(result_payload, dict):
        result_payload = dict(result_payload)
        result_payload["_cache"] = {
            **cache_meta,
            "key": cache_key,
        }
    analysis_store.store_pack(
        settings.output_dir,
        report_id,
        pack_name,
        result_payload,
        ctx,
        report_slug=report_name,
        mirror_legacy=settings.mirror_legacy_packs,
    )
    logger.info(log_event(
        ctx,
        role="generator",
        event="evidence_pack_step_complete",
        module=logger.name,
        fields={"report_id": report_id, "pack": pack_name, "not_found_reason": not_found_reason},
    ))
    return result_payload


def _empty_payload(schema_name: str, reason: str) -> dict:
    if schema_name == "doc_map":
        return {"doc_id": "", "title": "", "sections": [], "not_found_reason": reason}
    return {"scope": "", "methods": [], "findings": [], "limitations": [], "quote_candidates": [], "not_found_reason": reason}


def _summarize_doc_map(payload: dict) -> dict:
    if not isinstance(payload, dict):
        return {
            "has_content": False,
            "sections_count": 0,
            "title_present": False,
            "doc_id_present": False,
            "summary_present": False,
            "not_found_reason": "invalid_payload",
        }
    title = str(payload.get("title") or "").strip()
    doc_id = str(payload.get("doc_id") or "").strip()
    summary_text = str(payload.get("summary") or "").strip()
    sections = payload.get("sections")
    sections_count = len(sections) if isinstance(sections, list) else 0
    not_found_reason = str(payload.get("not_found_reason") or "").strip()
    return {
        "has_content": bool(title or doc_id or summary_text or sections_count),
        "sections_count": sections_count,
        "title_present": bool(title),
        "doc_id_present": bool(doc_id),
        "summary_present": bool(summary_text),
        "not_found_reason": not_found_reason,
    }


def _resolve_pack_path(output_dir: str, report_id: str, pack_name: str, report_name: str, analysis_store) -> str:
    if hasattr(analysis_store, "pack_path"):
        return str(analysis_store.pack_path(output_dir, report_id, pack_name, report_slug=report_name))
    return str(report_analysis_store_service.pack_path(output_dir, report_id, pack_name, report_slug=report_name))


def _load_cached_pack(
    *,
    output_dir: str,
    report_id: str,
    pack_name: str,
    report_name: str,
    cache_key: str,
    ctx: RunContext,
    analysis_store,
) -> Optional[dict]:
    if not cache_key:
        return None
    path = _resolve_pack_path(output_dir, report_id, pack_name, report_name, analysis_store)
    try:
        resp = file_service.read_text(ReadTextRequest(schema_version="1.0", path=path), ctx)
    except AppError as exc:
        if exc.code == "file_not_found":
            return None
        logger.info(log_event(
            ctx,
            role="generator",
            event="evidence_pack_cache_read_failed",
            module=logger.name,
            fields={"report_id": report_id, "pack": pack_name, "error": exc.message},
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
        logger.info(log_event(
            ctx,
            role="generator",
            event="evidence_pack_cache_miss",
            module=logger.name,
            fields={"report_id": report_id, "pack": pack_name},
        ))
        return None
    return payload
