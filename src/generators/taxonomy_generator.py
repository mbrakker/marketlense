from __future__ import annotations

import json
import logging
import re
from hashlib import sha256
from typing import Any, Dict, List, Optional, Tuple

from src.contracts.categories import CategoryMappingLoadRequest, TaxonomyInferenceRule
from src.contracts.openai import OpenAIResponseRequest, OpenAIResponseResult
from src.contracts.report_analysis import (
    AnalysisPackPathRequest,
    AnalysisStorePackRequest,
)
from src.contracts.run_context import RunContext
from src.contracts.schema_validation import SchemaValidateRequest
from src.contracts.semantic_ids import ReportId
from src.contracts.taxonomy import (
    TaxonomyExtractRequest,
    TaxonomyExtractResponse,
    TaxonomyTagEvidence,
)
from src.generators.analysis_pack_cache import (
    CachedPackAdaptResult,
    load_cached_pack,
)
from src.generators.analysis_store_adapter import (
    resolve_pack_path as resolve_analysis_pack_path,
)
from src.generators.analysis_store_adapter import (
    store_pack as store_analysis_pack,
)
from src.generators.prompt_preparation import (
    model_request_identity_fields,
    prepare_prompt_bundle,
)
from src.services import (
    file_service,
    prompt_service,
    report_analysis_store_service,
)
from src.services.category_mapping_service import (
    load_mappings as load_category_mappings,
)
from src.services.schema_validator_service import validate_schema
from src.utils.cache_utils import sha256_json
from src.utils.coercion import string_value as _s
from src.utils.errors import AppError
from src.utils.json_recovery import parse_json_from_text
from src.utils.logging import log_event
from src.utils.model_client_contract import require_injected_model_client
from src.utils.structured_output import StructuredOutputFailure
from src.utils.tag_utils import normalize_slug_tag

logger = logging.getLogger("market_lense.taxonomy_generator")


def extract_taxonomy(
    request: TaxonomyExtractRequest,
    ctx: RunContext,
    *,
    openai_client=None,
    prompt_client=prompt_service,
    analysis_store=report_analysis_store_service,
    file_client=file_service,
) -> TaxonomyExtractResponse:
    openai_client = require_injected_model_client(openai_client, scope="taxonomy")
    taxonomy_temperature = _resolve_taxonomy_temperature(request)
    logger.info(
        log_event(
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
        )
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
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="taxonomy_allowed_tags_loaded",
            module=logger.name,
            fields={
                "count": len(allowed_tags),
                "path": request.settings.category_mapping_path,
            },
        )
    )
    prompt_bundle = prepare_prompt_bundle(
        namespace=request.prompt_namespace,
        settings=request.settings,
        ctx=ctx,
        prompt_client=prompt_client,
        system_variables={},
        user_variables={
            "report_title": request.report_title,
            "allowed_tags_json": json.dumps(allowed_tags, ensure_ascii=True),
            "repair_error": request.repair_error,
            "repair_attempt": request.repair_attempt,
            "repair_response": request.repair_response,
        },
        reload_if_changed=True,
        default_model=request.settings.openai_model,
        temperature=taxonomy_temperature,
        seed=request.settings.openai_seed,
        timeout_seconds=request.settings.openai_timeout_seconds,
    )
    logger.info(
        log_event(
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
        )
    )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="taxonomy_prompt_rendered",
            module=logger.name,
            fields={
                "prompt_content_hash": prompt_bundle.prompt_content_hash,
                "execution_identity": prompt_bundle.execution_identity.execution_identity,
                "system_prompt_chars": len(prompt_bundle.system_prompt),
                "user_prompt_chars": len(prompt_bundle.user_prompt),
            },
        )
    )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="taxonomy_model_resolved",
            module=logger.name,
            fields={
                "namespace": request.prompt_namespace,
                "resolved_model": prompt_bundle.resolved_model,
                "default_model": request.settings.openai_model,
                "temperature": prompt_bundle.effective_temperature,
                "seed": prompt_bundle.effective_seed,
            },
        )
    )
    cache_key = ""
    cache_eligible, cache_skip_reason = _taxonomy_cache_eligibility(request)
    if cache_eligible:
        cache_meta = _taxonomy_cache_meta(
            request=request,
            allowed_tags=allowed_tags,
            prompt_system_sha256=prompt_bundle.prompt_set.system.sha256,
            prompt_user_sha256=prompt_bundle.prompt_set.user.sha256,
            resolved_model=prompt_bundle.resolved_model,
            execution_identity=prompt_bundle.execution_identity.execution_identity,
            execution_policy_hash=prompt_bundle.execution_policy.policy_hash,
        )
        cache_key = sha256_json(cache_meta)
        cached_response, miss_reason = _load_cached_taxonomy(
            request=request,
            cache_key=cache_key,
            inference_rules=mappings_resp.mappings.inference_rules,
            analysis_store=analysis_store,
            file_client=file_client,
            ctx=ctx,
        )
        if cached_response is not None:
            logger.info(
                log_event(
                    ctx,
                    role="generator",
                    event="taxonomy_cache_hit",
                    module=logger.name,
                    fields={
                        "report_id": request.report_id,
                        "cache_key": cache_key,
                    },
                )
            )
            return cached_response
        logger.info(
            log_event(
                ctx,
                role="generator",
                event="taxonomy_cache_miss",
                module=logger.name,
                fields={
                    "report_id": request.report_id,
                    "reason": miss_reason,
                },
            )
        )
    else:
        logger.info(
            log_event(
                ctx,
                role="generator",
                event="taxonomy_cache_skipped",
                module=logger.name,
                fields={
                    "report_id": request.report_id,
                    "reason": cache_skip_reason,
                },
            )
        )

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
                temperature=prompt_bundle.effective_temperature,
                api_key=request.settings.openai_api_key,
                seed=prompt_bundle.effective_seed,
                max_output_tokens=prompt_bundle.effective_max_output_tokens,
                timeout_seconds=prompt_bundle.effective_timeout_seconds,
                cost_ledger_path=request.settings.cost_ledger_path,
                cost_daily_path=request.settings.cost_daily_path,
                usage_db_path=str(
                    getattr(
                        request.settings, "usage_db_path", "./state/llm_usage.sqlite"
                    )
                ),
                model_pricing=request.settings.model_pricing,
                publisher_name=request.publisher_name,
                report_name=request.report_title,
                report_id=str(request.report_id),
                source_url=request.source_url,
                workflow=request.workflow,
                stage=request.stage,
                artifact_family=request.artifact_family,
                publisher_id=request.publisher_id or request.publisher_name,
                prompt_namespace=request.prompt_namespace,
                policy_hash=prompt_bundle.execution_policy.policy_hash,
                validation_run_id=str(getattr(ctx, "validation_run_id", "") or ""),
                configuration_hash=str(getattr(ctx, "configuration_hash", "") or ""),
                producer_build_identity=str(
                    getattr(ctx, "producer_commit_sha", "") or ""
                ),
                repair_attempt=request.repair_attempt,
                **model_request_identity_fields(prompt_bundle),
            ),
            ctx,
        )
        raw_text = resp.text or ""
        logger.info(
            log_event(
                ctx,
                role="generator",
                event="taxonomy_model_response",
                module=logger.name,
                fields={
                    "model": getattr(resp, "model", prompt_bundle.resolved_model),
                    "response_chars": len(raw_text),
                    "response_hash": sha256(raw_text.encode("utf-8")).hexdigest(),
                    "has_json": bool(resp.parsed_json),
                },
            )
        )
        parsed_json = resp.parsed_json if isinstance(resp.parsed_json, dict) else None
        if parsed_json is None:
            recovered, _strategy = parse_json_from_text(
                raw_text, accepted_types=(dict,)
            )
            parsed_json = recovered if isinstance(recovered, dict) else None
        if parsed_json is None:
            raise StructuredOutputFailure(
                code="taxonomy_invalid_json",
                message="Taxonomy extraction returned no JSON object",
                artifact_family="taxonomy",
                response_text=raw_text,
                repair_attempt=request.repair_attempt,
            )
    except AppError as exc:
        if isinstance(exc, StructuredOutputFailure):
            raise
        if exc.retryable:
            logger.info(
                log_event(
                    ctx,
                    role="generator",
                    event="taxonomy_retryable_error_propagated",
                    module=logger.name,
                    fields={"code": exc.code, "message": exc.message},
                )
            )
            raise
        if exc.code in {
            "openai_response_empty",
            "openai_response_invalid_json",
            "openai_response_json_type_invalid",
        }:
            raise StructuredOutputFailure(
                code="taxonomy_invalid_json",
                message="Taxonomy extraction returned an invalid structured response",
                artifact_family="taxonomy",
                response_text=raw_text,
                schema_errors=exc.code,
                repair_attempt=request.repair_attempt,
            ) from exc
        raise

    payload = parsed_json
    if payload is None:  # Defensive: the provider branch above always classifies this.
        raise StructuredOutputFailure(
            code="taxonomy_invalid_json",
            message="Taxonomy extraction returned no usable structured response",
            artifact_family="taxonomy",
            response_text=raw_text,
            repair_attempt=request.repair_attempt,
        )
    try:
        validate_schema(
            SchemaValidateRequest(
                schema_version="1.0", payload=payload, schema_name="taxonomy"
            ),
            ctx,
        )
        logger.info(
            log_event(
                ctx,
                role="generator",
                event="taxonomy_schema_valid",
                module=logger.name,
                fields={"reason": not_found_reason or ""},
            )
        )
    except AppError as exc:
        if exc.retryable:
            logger.info(
                log_event(
                    ctx,
                    role="generator",
                    event="taxonomy_retryable_error_propagated",
                    module=logger.name,
                    fields={"code": exc.code, "message": exc.message},
                )
            )
            raise
        raise StructuredOutputFailure(
            code="taxonomy_schema_invalid",
            message="Taxonomy extraction did not satisfy its output schema",
            artifact_family="taxonomy",
            response_text=raw_text,
            schema_errors=exc.code,
            repair_attempt=request.repair_attempt,
        ) from exc

    primary_tags = _normalize_tags(payload.get("primary_tags"))
    secondary_tags = _normalize_tags(payload.get("secondary_tags"))
    initial_taxonomy = _merge_taxonomy_lists(
        payload.get("taxonomy"),
        primary_tags,
        secondary_tags,
        _extract_evidence_tags(payload.get("tag_evidence")),
    )
    tag_evidence = _normalize_tag_evidence(
        payload.get("tag_evidence"),
        primary_tags=primary_tags,
        secondary_tags=secondary_tags,
        known_tags=initial_taxonomy,
    )
    primary_tags, secondary_tags, tag_evidence = _apply_inference_rules(
        primary_tags=primary_tags,
        secondary_tags=secondary_tags,
        tag_evidence=tag_evidence,
        inference_rules=mappings_resp.mappings.inference_rules,
    )
    taxonomy = _finalize_taxonomy_list(
        raw_taxonomy=payload.get("taxonomy"),
        primary_tags=primary_tags,
        secondary_tags=secondary_tags,
        tag_evidence=tag_evidence,
    )
    region = _s(payload.get("region"))
    time_period = _s(payload.get("time_period"))
    response = TaxonomyExtractResponse(
        schema_version="1.0",
        taxonomy=taxonomy,
        primary_tags=primary_tags,
        secondary_tags=secondary_tags,
        tag_evidence=tag_evidence,
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
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="taxonomy_extract_complete",
            module=logger.name,
            fields={
                "taxonomy_count": len(taxonomy),
                "primary_tag_count": len(primary_tags),
                "secondary_tag_count": len(secondary_tags),
                "tag_evidence_count": len(tag_evidence),
                "region": region,
                "time_period": time_period,
                "not_found_reason": not_found_reason or "",
            },
        )
    )
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
    execution_identity: str,
    execution_policy_hash: str,
) -> Dict[str, Any]:
    return {
        "schema_version": "1.0",
        "md5": request.md5 or "",
        "report_title": request.report_title,
        "allowed_tags_sha256": sha256_json({"allowed_tags": allowed_tags}),
        "prompt_system_sha256": prompt_system_sha256,
        "prompt_user_sha256": prompt_user_sha256,
        "resolved_model": resolved_model,
        "execution_identity": execution_identity,
        "execution_policy_hash": execution_policy_hash,
    }


def _resolve_taxonomy_temperature(request: TaxonomyExtractRequest) -> float:
    configured = getattr(
        request.settings, "taxonomy_temperature", request.settings.temperature
    )
    try:
        return float(configured)
    except (TypeError, ValueError):
        return float(request.settings.temperature)


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
            report_id=ReportId(report_id),
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
            report_id=ReportId(report_id),
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
    inference_rules: List[TaxonomyInferenceRule],
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
            "primary_tags": payload.get("primary_tags"),
            "secondary_tags": payload.get("secondary_tags"),
            "tag_evidence": payload.get("tag_evidence"),
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
        primary_tags = _normalize_tags(taxonomy_payload.get("primary_tags"))
        secondary_tags = _normalize_tags(taxonomy_payload.get("secondary_tags"))
        initial_taxonomy = _merge_taxonomy_lists(
            taxonomy_payload.get("taxonomy"),
            primary_tags,
            secondary_tags,
            _extract_evidence_tags(taxonomy_payload.get("tag_evidence")),
        )
        tag_evidence = _normalize_tag_evidence(
            taxonomy_payload.get("tag_evidence"),
            primary_tags=primary_tags,
            secondary_tags=secondary_tags,
            known_tags=initial_taxonomy,
        )
        primary_tags, secondary_tags, tag_evidence = _apply_inference_rules(
            primary_tags=primary_tags,
            secondary_tags=secondary_tags,
            tag_evidence=tag_evidence,
            inference_rules=inference_rules,
        )
        taxonomy = _finalize_taxonomy_list(
            raw_taxonomy=taxonomy_payload.get("taxonomy"),
            primary_tags=primary_tags,
            secondary_tags=secondary_tags,
            tag_evidence=tag_evidence,
        )
        return CachedPackAdaptResult(
            schema_version="1.0",
            status="hit",
            value=TaxonomyExtractResponse(
                schema_version="1.0",
                taxonomy=taxonomy,
                primary_tags=primary_tags,
                secondary_tags=secondary_tags,
                tag_evidence=tag_evidence,
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
        "primary_tags": response.primary_tags,
        "secondary_tags": response.secondary_tags,
        "tag_evidence": [
            {
                "tag": item.tag,
                "tier": item.tier,
                "section_label": item.section_label,
                "evidence": item.evidence,
            }
            for item in response.tag_evidence
        ],
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
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="taxonomy_cache_written",
            module=logger.name,
            fields={"report_id": request.report_id, "path": output_path},
        )
    )


def _normalize_tags(items: Any) -> List[str]:
    if not isinstance(items, list):
        return []
    cleaned: List[str] = []
    seen = set()
    for item in items:
        text = normalize_slug_tag(item)
        if not text:
            continue
        if text in seen:
            continue
        seen.add(text)
        cleaned.append(text)
    return cleaned


def _merge_taxonomy_lists(*groups: Any) -> List[str]:
    merged: List[str] = []
    seen = set()
    for group in groups:
        if not isinstance(group, list):
            continue
        for item in group:
            text = normalize_slug_tag(item)
            if not text:
                continue
            if text in seen:
                continue
            seen.add(text)
            merged.append(text)
    return merged


def _extract_evidence_tags(items: Any) -> List[str]:
    if not isinstance(items, list):
        return []
    return _normalize_tags(
        [
            _s(item.get("tag")).strip()
            for item in items
            if isinstance(item, dict) and _s(item.get("tag")).strip()
        ]
    )


def _normalize_tag_evidence(
    items: Any,
    *,
    primary_tags: List[str],
    secondary_tags: List[str],
    known_tags: List[str],
) -> List[TaxonomyTagEvidence]:
    if not isinstance(items, list):
        return []
    secondary_norms = {
        normalize_slug_tag(tag) for tag in secondary_tags if normalize_slug_tag(tag)
    }
    known_norms = {
        normalize_slug_tag(tag) for tag in known_tags if normalize_slug_tag(tag)
    }
    evidence_items: List[TaxonomyTagEvidence] = []
    seen = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        tag = normalize_slug_tag(item.get("tag"))
        if not tag:
            continue
        if known_norms and tag not in known_norms:
            continue
        section_label = _s(
            item.get("section_label")
            or item.get("section")
            or item.get("section_title")
        ).strip()
        evidence = _s(item.get("evidence")).strip()
        tier = _s(item.get("tier")).strip().lower()
        if tier not in {"primary", "secondary"}:
            tier = "secondary" if tag in secondary_norms else "primary"
        dedupe_key = (tag, tier, section_label.lower())
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        evidence_items.append(
            TaxonomyTagEvidence(
                tag=tag,
                tier=tier,
                section_label=section_label,
                evidence=evidence,
            )
        )
    return evidence_items


def _apply_inference_rules(
    *,
    primary_tags: List[str],
    secondary_tags: List[str],
    tag_evidence: List[TaxonomyTagEvidence],
    inference_rules: List[TaxonomyInferenceRule],
) -> tuple[List[str], List[str], List[TaxonomyTagEvidence]]:
    updated_primary = list(primary_tags)
    updated_secondary = list(secondary_tags)
    updated_evidence = list(tag_evidence)
    for rule in inference_rules:
        trigger_evidence = _find_trigger_evidence_for_rule(rule, updated_evidence)
        if trigger_evidence is None:
            continue
        updated_primary, updated_secondary, updated_evidence = _apply_inference_rule(
            rule=rule,
            trigger_evidence=trigger_evidence,
            primary_tags=updated_primary,
            secondary_tags=updated_secondary,
            tag_evidence=updated_evidence,
        )

    return (
        _normalize_tags(updated_primary),
        _normalize_tags(updated_secondary),
        _dedupe_tag_evidence(updated_evidence),
    )


def _finalize_taxonomy_list(
    *,
    raw_taxonomy: Any,
    primary_tags: List[str],
    secondary_tags: List[str],
    tag_evidence: List[TaxonomyTagEvidence],
) -> List[str]:
    structured_taxonomy = _merge_taxonomy_lists(
        primary_tags,
        secondary_tags,
        [item.tag for item in tag_evidence],
    )
    if structured_taxonomy:
        return structured_taxonomy
    return _merge_taxonomy_lists(raw_taxonomy)


def _find_trigger_evidence_for_rule(
    rule: TaxonomyInferenceRule,
    tag_evidence: List[TaxonomyTagEvidence],
) -> TaxonomyTagEvidence | None:
    trigger_tags = {
        normalize_slug_tag(tag) for tag in rule.trigger_tags if normalize_slug_tag(tag)
    }
    context_keywords_any = [
        keyword for keyword in rule.context_keywords_any if keyword.strip()
    ]
    for item in tag_evidence:
        if normalize_slug_tag(item.tag) not in trigger_tags:
            continue
        if not context_keywords_any:
            return item
        haystack = f"{item.section_label} {item.evidence}"
        if any(
            _keyword_matches_evidence(keyword, haystack)
            for keyword in context_keywords_any
        ):
            return item
    return None


def _keyword_matches_evidence(keyword: str, haystack: str) -> bool:
    normalized_keyword = _normalize_match_text(keyword)
    normalized_haystack = _normalize_match_text(haystack)
    if not normalized_keyword or not normalized_haystack:
        return False
    return f" {normalized_keyword} " in f" {normalized_haystack} "


def _normalize_match_text(value: str) -> str:
    normalized = str(value or "")
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = normalize_slug_tag(normalized).replace("_", " ")
    normalized = re.sub(r"[^0-9a-z]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _apply_inference_rule(
    *,
    rule: TaxonomyInferenceRule,
    trigger_evidence: TaxonomyTagEvidence,
    primary_tags: List[str],
    secondary_tags: List[str],
    tag_evidence: List[TaxonomyTagEvidence],
) -> tuple[List[str], List[str], List[TaxonomyTagEvidence]]:
    remove_norms = {
        normalize_slug_tag(tag) for tag in rule.remove_tags if normalize_slug_tag(tag)
    }
    inferred_tag = normalize_slug_tag(rule.inferred_tag)
    inferred_norm = inferred_tag

    updated_primary = [
        tag for tag in primary_tags if normalize_slug_tag(tag) not in remove_norms
    ]
    updated_secondary = [
        tag for tag in secondary_tags if normalize_slug_tag(tag) not in remove_norms
    ]
    updated_evidence = [
        item
        for item in tag_evidence
        if normalize_slug_tag(item.tag) not in remove_norms
    ]

    updated_primary = [
        tag for tag in updated_primary if normalize_slug_tag(tag) != inferred_norm
    ]
    updated_secondary = [
        tag for tag in updated_secondary if normalize_slug_tag(tag) != inferred_norm
    ]

    if rule.inferred_tier == "primary":
        updated_primary.append(inferred_tag)
    else:
        updated_secondary.append(inferred_tag)

    updated_evidence.append(
        TaxonomyTagEvidence(
            tag=inferred_tag,
            tier=rule.inferred_tier,
            section_label=trigger_evidence.section_label,
            evidence=trigger_evidence.evidence,
        )
    )
    return updated_primary, updated_secondary, updated_evidence


def _dedupe_tag_evidence(
    items: List[TaxonomyTagEvidence],
) -> List[TaxonomyTagEvidence]:
    deduped: List[TaxonomyTagEvidence] = []
    seen = set()
    for item in items:
        key = (
            normalize_slug_tag(item.tag),
            item.tier.strip().lower(),
            item.section_label.strip().lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _collect_allowed_tags(mappings_resp) -> List[str]:
    allowed: List[str] = []
    seen = set()
    for cat in mappings_resp.mappings.categories:
        for tag in (
            list(cat.core_tags)
            + list(cat.supporting_tags)
            + list(cat.secondary_supporting_tags)
            + list(cat.descriptor_tags)
            + list(cat.tags)
            + list(cat.generic_tags)
        ):
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
        "primary_tags": [],
        "secondary_tags": [],
        "tag_evidence": [],
        "region": "",
        "time_period": "",
        "not_found_reason": reason,
    }
