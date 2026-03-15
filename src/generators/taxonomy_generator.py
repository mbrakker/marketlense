from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from src.contracts.openai import OpenAIResponseRequest, OpenAIResponseResult
from src.contracts.report_analysis import AnalysisPackPathRequest, AnalysisStorePackRequest
from src.contracts.run_context import RunContext
from src.contracts.categories import CategoryMappingLoadRequest
from src.contracts.schema_validation import SchemaValidateRequest
from src.contracts.taxonomy import TaxonomyExtractRequest, TaxonomyExtractResponse
from src.generators.analysis_pack_cache import (
    CachedPackAdaptResult,
    load_cached_pack,
)
from src.generators.analysis_store_adapter import (
    resolve_pack_path as resolve_analysis_pack_path,
    store_pack as store_analysis_pack,
)
from src.generators.prompt_preparation import prepare_prompt_bundle
from src.services.category_mapping_service import load_mappings as load_category_mappings
from src.services import file_service, openai_service, prompt_service, report_analysis_store_service
from src.utils.errors import AppError
from src.utils.logging import log_event
from src.utils.cache_utils import sha256_json
from src.services.schema_validator_service import validate_schema

logger = logging.getLogger("market_lense.taxonomy_generator")


def extract_taxonomy(
    request: TaxonomyExtractRequest,
    ctx: RunContext,
    *,
    openai_client=openai_service,
    prompt_client=prompt_service,
    analysis_store=report_analysis_store_service,
    file_client=file_service,
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
            "md5": request.md5 or "",
            "report_slug": request.report_slug or "",
        },
    ))
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
    prompt_bundle = prepare_prompt_bundle(
        namespace=request.prompt_namespace,
        settings=request.settings,
        ctx=ctx,
        prompt_client=prompt_client,
        system_variables={},
        user_variables={
            "report_title": request.report_title,
            "allowed_tags_json": json.dumps(allowed_tags, ensure_ascii=True),
        },
        reload_if_changed=True,
    )
    logger.info(log_event(
        ctx,
        role="generator",
        event="taxonomy_prompt_selected",
        module=logger.name,
        fields={
            "namespace": request.prompt_namespace,
            "system_path": prompt_bundle.prompt_set.system.path,
            "system_sha256": prompt_bundle.prompt_set.system.sha256,
            "user_path": prompt_bundle.prompt_set.user.path,
            "user_sha256": prompt_bundle.prompt_set.user.sha256,
        },
    ))
    logger.info(log_event(
        ctx,
        role="generator",
        event="taxonomy_prompt_rendered",
        module=logger.name,
        fields={
            "system_prompt": prompt_bundle.system_prompt,
            "user_prompt": prompt_bundle.user_prompt,
        },
    ))
    logger.info(log_event(
        ctx,
        role="generator",
        event="taxonomy_model_resolved",
        module=logger.name,
        fields={
            "namespace": request.prompt_namespace,
            "resolved_model": prompt_bundle.resolved_model,
            "default_model": request.settings.openai_model,
            "temperature": request.settings.temperature,
            "seed": request.settings.openai_seed,
        },
    ))
    cache_key = ""
    cache_eligible, cache_skip_reason = _taxonomy_cache_eligibility(request)
    if cache_eligible:
        cache_meta = _taxonomy_cache_meta(
            request=request,
            allowed_tags=allowed_tags,
            prompt_system_sha256=prompt_bundle.prompt_set.system.sha256,
            prompt_user_sha256=prompt_bundle.prompt_set.user.sha256,
            resolved_model=prompt_bundle.resolved_model,
        )
        cache_key = sha256_json(cache_meta)
        cached_response, miss_reason = _load_cached_taxonomy(
            request=request,
            cache_key=cache_key,
            analysis_store=analysis_store,
            file_client=file_client,
            ctx=ctx,
        )
        if cached_response is not None:
            logger.info(log_event(
                ctx,
                role="generator",
                event="taxonomy_cache_hit",
                module=logger.name,
                fields={
                    "report_id": request.report_id,
                    "cache_key": cache_key,
                },
            ))
            return cached_response
        logger.info(log_event(
            ctx,
            role="generator",
            event="taxonomy_cache_miss",
            module=logger.name,
            fields={
                "report_id": request.report_id,
                "reason": miss_reason,
            },
        ))
    else:
        logger.info(log_event(
            ctx,
            role="generator",
            event="taxonomy_cache_skipped",
            module=logger.name,
            fields={
                "report_id": request.report_id,
                "reason": cache_skip_reason,
            },
        ))

    parsed_json: Dict[str, Any] | None = None
    not_found_reason = ""
    raw_text = ""
    try:
        resp: OpenAIResponseResult = openai_client.openai_respond_with_vector_store(
            OpenAIResponseRequest(
                schema_version="1.0",
                system_prompt=prompt_bundle.system_prompt,
                user_prompt=prompt_bundle.user_prompt,
                vector_store_id=request.vector_store_id,
                model=prompt_bundle.resolved_model,
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
                "model": getattr(resp, "model", prompt_bundle.resolved_model),
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
        validate_schema(
            SchemaValidateRequest(schema_version="1.0", payload=payload, schema_name="taxonomy"),
            ctx,
        )
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
    if cache_eligible:
        _store_taxonomy_cache(
            request=request,
            response=response,
            cache_key=cache_key,
            analysis_store=analysis_store,
            ctx=ctx,
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


def _taxonomy_cache_eligibility(request: TaxonomyExtractRequest) -> Tuple[bool, str]:
    if not request.md5:
        return False, "md5_missing"
    if not getattr(request.settings, "vector_store_keep", False):
        return False, "vector_store_keep_false"
    return True, ""


def _taxonomy_cache_meta(
    *,
    request: TaxonomyExtractRequest,
    allowed_tags: List[str],
    prompt_system_sha256: str,
    prompt_user_sha256: str,
    resolved_model: str,
) -> Dict[str, Any]:
    return {
        "schema_version": "1.0",
        "md5": request.md5 or "",
        "report_title": request.report_title,
        "allowed_tags_sha256": sha256_json({"allowed_tags": allowed_tags}),
        "prompt_system_sha256": prompt_system_sha256,
        "prompt_user_sha256": prompt_user_sha256,
        "resolved_model": resolved_model,
        "temperature": request.settings.temperature,
        "seed": request.settings.openai_seed,
    }


def _resolve_pack_path(
    *,
    analysis_store,
    output_dir: str,
    report_id: str,
    report_slug: Optional[str],
    ctx: RunContext,
) -> str:
    return resolve_analysis_pack_path(
        analysis_store=analysis_store,
        request=AnalysisPackPathRequest(
            schema_version="1.0",
            output_dir=output_dir,
            report_id=report_id,
            pack_name="taxonomy",
            report_slug=report_slug,
        ),
        ctx=ctx,
    )


def _store_pack(
    *,
    analysis_store,
    output_dir: str,
    report_id: str,
    report_slug: Optional[str],
    payload: Dict[str, Any],
    ctx: RunContext,
) -> str:
    return store_analysis_pack(
        analysis_store=analysis_store,
        request=AnalysisStorePackRequest(
            schema_version="1.0",
            output_dir=output_dir,
            report_id=report_id,
            pack_name="taxonomy",
            payload=payload,
            report_slug=report_slug,
        ),
        ctx=ctx,
    )


def _load_cached_taxonomy(
    *,
    request: TaxonomyExtractRequest,
    cache_key: str,
    analysis_store,
    file_client,
    ctx: RunContext,
) -> Tuple[Optional[TaxonomyExtractResponse], str]:
    def _log_read_failed(exc: AppError, path: str) -> None:
        logger.info(
            log_event(
                ctx,
                role="generator",
                event="taxonomy_cache_read_failed",
                module=logger.name,
                fields={
                    "report_id": request.report_id,
                    "path": path,
                    "error": exc.message,
                },
            )
        )

    def _adapt_payload(
        payload: Dict[str, Any], path: str
    ) -> CachedPackAdaptResult[TaxonomyExtractResponse]:
        taxonomy_payload = {
            "schema_version": "1.0",
            "taxonomy": payload.get("taxonomy"),
            "region": payload.get("region"),
            "time_period": payload.get("time_period"),
            "not_found_reason": payload.get("not_found_reason"),
        }
        try:
            validate_schema(
                SchemaValidateRequest(
                    schema_version="1.0",
                    payload=taxonomy_payload,
                    schema_name="taxonomy",
                ),
                ctx,
            )
        except AppError as exc:
            logger.info(
                log_event(
                    ctx,
                    role="generator",
                    event="taxonomy_cache_invalid",
                    module=logger.name,
                    fields={
                        "report_id": request.report_id,
                        "path": path,
                        "code": exc.code,
                        "message": exc.message,
                    },
                )
            )
            return CachedPackAdaptResult(
                schema_version="1.0",
                status="schema_invalid",
                value=None,
            )
        return CachedPackAdaptResult(
            schema_version="1.0",
            status="hit",
            value=TaxonomyExtractResponse(
                schema_version="1.0",
                taxonomy=_normalize_tags(taxonomy_payload.get("taxonomy")),
                region=_s(taxonomy_payload.get("region")),
                time_period=_s(taxonomy_payload.get("time_period")),
                not_found_reason=_s(taxonomy_payload.get("not_found_reason")) or None,
            ),
        )

    result = load_cached_pack(
        cache_key=cache_key,
        ctx=ctx,
        resolve_path=lambda: _resolve_pack_path(
            analysis_store=analysis_store,
            output_dir=request.settings.output_dir,
            report_id=request.report_id,
            report_slug=request.report_slug,
            ctx=ctx,
        ),
        read_text=file_client.read_text,
        on_read_failed=_log_read_failed,
        adapt_payload=_adapt_payload,
    )
    return result.value, result.status


def _store_taxonomy_cache(
    *,
    request: TaxonomyExtractRequest,
    response: TaxonomyExtractResponse,
    cache_key: str,
    analysis_store,
    ctx: RunContext,
) -> None:
    payload = {
        "schema_version": "1.0",
        "taxonomy": response.taxonomy,
        "region": response.region,
        "time_period": response.time_period,
        "not_found_reason": response.not_found_reason or "",
        "_cache": {
            "key": cache_key,
        },
    }
    output_path = _store_pack(
        analysis_store=analysis_store,
        output_dir=request.settings.output_dir,
        report_id=request.report_id,
        report_slug=request.report_slug,
        payload=payload,
        ctx=ctx,
    )
    logger.info(log_event(
        ctx,
        role="generator",
        event="taxonomy_cache_written",
        module=logger.name,
        fields={"report_id": request.report_id, "path": output_path},
    ))


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
