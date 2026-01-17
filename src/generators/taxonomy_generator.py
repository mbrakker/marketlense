from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from src.contracts.openai import OpenAIResponseRequest, OpenAIResponseResult
from src.contracts.prompts import PromptLoadRequest, PromptRenderRequest
from src.contracts.run_context import RunContext
from src.contracts.categories import CategoryMappingLoadRequest
from src.contracts.taxonomy import TaxonomyExtractRequest, TaxonomyExtractResponse
from src.services.category_mapping_service import load_mappings as load_category_mappings
from src.services import openai_service, prompt_service
from src.utils.errors import AppError
from src.utils.logging import log_event
from src.utils.model_resolver import resolve_model
from src.utils.schema_validator import validate_schema

logger = logging.getLogger("market_lense.taxonomy_generator")


def extract_taxonomy(
    request: TaxonomyExtractRequest,
    ctx: RunContext,
    *,
    openai_client=openai_service,
    prompt_client=prompt_service,
) -> TaxonomyExtractResponse:
    logger.info(log_event(
        ctx,
        role="generator",
        event="taxonomy_extract_start",
        module=logger.name,
        fields={
            "report_id": request.report_id,
            "vector_store_id": request.vector_store_id,
            "prompt_namespace": request.prompt_namespace,
            "report_title": request.report_title,
        },
    ))
    prompt_set = prompt_client.load_prompt_set(
        PromptLoadRequest(schema_version="1.0", namespace=request.prompt_namespace, reload_if_changed=True),
        ctx,
    )
    mappings_resp = load_category_mappings(
        CategoryMappingLoadRequest(
            schema_version="1.0",
            path=request.settings.category_mapping_path,
            reload_if_changed=True,
        ),
        ctx,
    )
    allowed_tags = _collect_allowed_tags(mappings_resp)
    logger.info(log_event(
        ctx,
        role="generator",
        event="taxonomy_allowed_tags_loaded",
        module=logger.name,
        fields={
            "count": len(allowed_tags),
            "path": request.settings.category_mapping_path,
        },
    ))
    logger.info(log_event(
        ctx,
        role="generator",
        event="taxonomy_prompt_selected",
        module=logger.name,
        fields={
            "namespace": request.prompt_namespace,
            "system_path": prompt_set.system.path,
            "system_sha256": prompt_set.system.sha256,
            "user_path": prompt_set.user.path,
            "user_sha256": prompt_set.user.sha256,
        },
    ))
    system_render = prompt_client.render_prompt(
        PromptRenderRequest(
            schema_version="1.0",
            template=prompt_set.system,
            variables={},
        ),
        ctx,
    )
    user_render = prompt_client.render_prompt(
        PromptRenderRequest(
            schema_version="1.0",
            template=prompt_set.user,
            variables={
                "report_title": request.report_title,
                "allowed_tags_json": json.dumps(allowed_tags, ensure_ascii=True),
            },
        ),
        ctx,
    )
    logger.info(log_event(
        ctx,
        role="generator",
        event="taxonomy_prompt_rendered",
        module=logger.name,
        fields={
            "system_prompt": system_render.text,
            "user_prompt": user_render.text,
        },
    ))
    resolved_model = resolve_model(
        request.prompt_namespace,
        getattr(request.settings, "openai_models", {}),
        request.settings.openai_model,
    )
    logger.info(log_event(
        ctx,
        role="generator",
        event="taxonomy_model_resolved",
        module=logger.name,
        fields={
            "namespace": request.prompt_namespace,
            "resolved_model": resolved_model,
            "default_model": request.settings.openai_model,
            "temperature": request.settings.temperature,
            "seed": request.settings.openai_seed,
        },
    ))

    parsed_json: Dict[str, Any] | None = None
    not_found_reason = ""
    raw_text = ""
    try:
        resp: OpenAIResponseResult = openai_client.openai_respond_with_vector_store(
            OpenAIResponseRequest(
                schema_version="1.0",
                system_prompt=system_render.text,
                user_prompt=user_render.text,
                vector_store_id=request.vector_store_id,
                model=resolved_model,
                temperature=request.settings.temperature,
                api_key=request.settings.openai_api_key,
                seed=request.settings.openai_seed,
                timeout_seconds=request.settings.openai_timeout_seconds,
                cost_ledger_path=request.settings.cost_ledger_path,
                cost_daily_path=request.settings.cost_daily_path,
                model_pricing=request.settings.model_pricing,
            ),
            ctx,
        )
        raw_text = resp.text or ""
        logger.info(log_event(
            ctx,
            role="generator",
            event="taxonomy_model_response",
            module=logger.name,
            fields={
                "model": getattr(resp, "model", resolved_model),
                "raw_response": raw_text,
                "has_json": bool(resp.parsed_json),
            },
        ))
        parsed_json = resp.parsed_json if isinstance(resp.parsed_json, dict) else None
        if parsed_json is None:
            not_found_reason = "model_returned_no_json"
    except AppError as exc:
        not_found_reason = exc.code
        logger.info(log_event(
            ctx,
            role="generator",
            event="taxonomy_model_failed",
            module=logger.name,
            fields={"code": exc.code, "message": exc.message},
        ))

    payload = parsed_json or _empty_payload(not_found_reason)
    try:
        validate_schema(payload, "taxonomy", ctx)
        logger.info(log_event(
            ctx,
            role="generator",
            event="taxonomy_schema_valid",
            module=logger.name,
            fields={"reason": not_found_reason or ""},
        ))
    except AppError as exc:
        not_found_reason = not_found_reason or f"schema_validation_failed:{exc.code}"
        payload = _empty_payload(not_found_reason)
        logger.info(log_event(
            ctx,
            role="generator",
            event="taxonomy_schema_invalid",
            module=logger.name,
            fields={"code": exc.code, "message": exc.message},
        ))

    taxonomy = _normalize_tags(payload.get("taxonomy"))
    region = _s(payload.get("region"))
    time_period = _s(payload.get("time_period"))
    response = TaxonomyExtractResponse(
        schema_version="1.0",
        taxonomy=taxonomy,
        region=region,
        time_period=time_period,
        not_found_reason=not_found_reason or None,
    )
    logger.info(log_event(
        ctx,
        role="generator",
        event="taxonomy_extract_complete",
        module=logger.name,
        fields={
            "taxonomy_count": len(taxonomy),
            "region": region,
            "time_period": time_period,
            "not_found_reason": not_found_reason or "",
        },
    ))
    return response


def _normalize_tags(items: Any) -> List[str]:
    if not isinstance(items, list):
        return []
    cleaned: List[str] = []
    seen = set()
    for item in items:
        text = _s(item).strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(text)
    return cleaned


def _collect_allowed_tags(mappings_resp) -> List[str]:
    allowed: List[str] = []
    seen = set()
    for cat in mappings_resp.mappings.categories:
        for tag in cat.tags:
            tag_s = str(tag or "").strip()
            if not tag_s:
                continue
            key = tag_s.lower()
            if key in seen:
                continue
            seen.add(key)
            allowed.append(tag_s)
    return allowed


def _empty_payload(reason: str) -> Dict[str, Any]:
    return {
        "schema_version": "1.0",
        "taxonomy": [],
        "region": "",
        "time_period": "",
        "not_found_reason": reason,
    }


def _s(value: Any) -> str:
    if value is None:
        return ""
    return value if isinstance(value, str) else str(value)
