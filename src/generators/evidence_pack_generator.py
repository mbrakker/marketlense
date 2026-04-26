from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Optional, Tuple

from src.contracts.config import AppSettings
from src.contracts.openai import OpenAIResponseRequest, OpenAIResponseResult
from src.contracts.report_analysis import (
    AnalysisPackPathRequest,
    AnalysisStorePackRequest,
)
from src.contracts.run_context import RunContext
from src.contracts.schema_validation import SchemaValidateRequest
from src.generators.analysis_pack_cache import (
    CachedPackAdaptResult,
    load_cached_pack,
)
from src.generators.analysis_store_adapter import (
    resolve_pack_path as resolve_analysis_pack_path,
    store_pack as store_analysis_pack,
)
from src.generators.prompt_preparation import prepare_prompt_bundle
from src.generators.evidence_packs.doc_map_strategy import (
    normalize_payload as normalize_doc_map_payload,
)
from src.generators.evidence_packs.doc_map_strategy import (
    summarize_completeness as summarize_doc_map_completeness,
)
from src.generators.evidence_packs.doc_map_strategy import (
    summarize_payload as summarize_doc_map,
)
from src.generators.evidence_packs.base import EvidencePackStrategy
from src.generators.evidence_packs.registry import (
    DEFAULT_PACK_REGISTRY,
    PACK_STRATEGIES,
    VARIETY_PACKS,
)
from src.services import file_service
from src.services import llm_service
from src.services import prompt_service
from src.services import report_analysis_store_service
from src.services.schema_validator_service import validate_schema
from src.utils.cache_utils import sha256_json
from src.utils.coercion import coerce_int
from src.utils.errors import AppError
from src.utils.json_recovery import parse_json_from_text, strip_json_fence
from src.utils.logging import child_context, log_event, new_run_context

logger = logging.getLogger("market_lense.evidence_pack_generator")


def _pack_parallel_workers(settings: AppSettings, step_count: int) -> int:
    configured = coerce_int(
        getattr(settings, "evidence_pack_parallel_workers", 3), 3, min_value=1
    )
    return max(1, min(configured, step_count))


def _resolve_pack_steps(settings: AppSettings) -> list[EvidencePackStrategy]:
    raw_registry = getattr(settings, "evidence_pack_registry", None)
    enable_variety = bool(
        getattr(settings, "evidence_pack_enable_new_variety_packs", False)
    )
    registry: list[str] = []
    if isinstance(raw_registry, list):
        for value in raw_registry:
            token = str(value).strip()
            if token and token in PACK_STRATEGIES and token not in registry:
                registry.append(token)
    if not registry:
        registry = list(DEFAULT_PACK_REGISTRY)
    if enable_variety:
        for pack_name in VARIETY_PACKS:
            if pack_name not in registry:
                registry.append(pack_name)
    if "doc_map" not in registry:
        registry = ["doc_map", *registry]
    elif registry[0] != "doc_map":
        registry = ["doc_map"] + [item for item in registry if item != "doc_map"]
    return [PACK_STRATEGIES[pack_name] for pack_name in registry]


def _prompt_namespace_for_strategy(strategy: EvidencePackStrategy) -> str:
    return f"report_vs/{strategy.prompt_namespace_suffix}"


def _strip_json_fence(text: str) -> str:
    return strip_json_fence(text)


def _parse_json_payload_from_text(text: str) -> Optional[object]:
    parsed, _strategy = parse_json_from_text(text, accepted_types=(dict, list))
    return parsed


def generate_evidence_packs(
    report_id: str,
    report_name: str,
    vector_store_id: str,
    settings: AppSettings,
    ctx: Optional[RunContext] = None,
    md5: Optional[str] = None,
    *,
    openai_client=None,
    prompt_client=prompt_service,
    analysis_store=report_analysis_store_service,
) -> Dict[str, dict]:
    ctx = ctx or new_run_context(task_id=f"evidence_pack:{report_id}")
    openai_client = openai_client or llm_service.build_openai_client_for_settings(
        settings,
        scope="evidence_pack_generator",
    )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="evidence_pack_start",
            module=logger.name,
            fields={"report_id": report_id, "vector_store_id": vector_store_id},
        )
    )
    strategies = _resolve_pack_steps(settings)
    results: Dict[str, dict] = {}
    parallel_workers = _pack_parallel_workers(settings, max(0, len(strategies) - 1))
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="evidence_pack_parallel_config",
            module=logger.name,
            fields={
                "report_id": report_id,
                "parallel_workers": parallel_workers,
                "parallel_step_count": max(0, len(strategies) - 1),
                "pack_registry": [strategy.pack_name for strategy in strategies],
            },
        )
    )

    doc_strategy = strategies[0]
    step_name = doc_strategy.pack_name
    step_ctx = child_context(ctx, task_id=f"{ctx.task_id}:{step_name}")
    results[step_name] = _generate_pack(
        report_id=report_id,
        report_name=report_name,
        vector_store_id=vector_store_id,
        settings=settings,
        ctx=step_ctx,
        md5=md5,
        openai_client=openai_client,
        prompt_client=prompt_client,
        analysis_store=analysis_store,
        strategy=doc_strategy,
    )
    completeness = _summarize_doc_map_completeness(results[step_name])
    if completeness["warn"]:
        logger.warning(
            log_event(
                step_ctx,
                role="generator",
                event="doc_map_completeness_warning",
                module=logger.name,
                fields={
                    "report_id": report_id,
                    "vector_store_id": vector_store_id,
                    "sections_count": completeness["sections_count"],
                    "sections_with_summary": completeness["sections_with_summary"],
                    "sections_missing_summary": completeness["sections_missing_summary"],
                    "summary_coverage_ratio": completeness["summary_coverage_ratio"],
                    "sections_with_key_points": completeness[
                        "sections_with_key_points"
                    ],
                    "key_points_coverage_ratio": completeness[
                        "key_points_coverage_ratio"
                    ],
                },
            )
        )
    summary = _summarize_doc_map(results[step_name])
    if not summary["has_content"]:
        reason = summary["not_found_reason"] or "no_content"
        logger.info(
            log_event(
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
            )
        )
        raise AppError(
            code="doc_map_empty",
            message=f"doc_map_empty:{reason}",
            retryable=False,
            context=summary,
        )

    parallel_strategies = strategies[1:]
    parallel_results: Dict[str, dict] = {}
    if parallel_strategies and parallel_workers > 1:
        with ThreadPoolExecutor(max_workers=parallel_workers) as executor:
            futures = {}
            for strategy in parallel_strategies:
                step_name = strategy.pack_name
                step_ctx = child_context(ctx, task_id=f"{ctx.task_id}:{step_name}")
                future = executor.submit(
                    _generate_pack,
                    report_id=report_id,
                    report_name=report_name,
                    vector_store_id=vector_store_id,
                    settings=settings,
                    ctx=step_ctx,
                    md5=md5,
                    openai_client=openai_client,
                    prompt_client=prompt_client,
                    analysis_store=analysis_store,
                    strategy=strategy,
                )
                futures[future] = step_name
            first_error: Optional[Tuple[str, Exception]] = None
            for future in as_completed(futures):
                current_step = futures[future]
                try:
                    parallel_results[current_step] = future.result()
                except Exception as exc:  # pragma: no cover - defensive fallback
                    if first_error is None:
                        first_error = (current_step, exc)
                    logger.info(
                        log_event(
                            ctx,
                            role="generator",
                            event="evidence_pack_parallel_step_failed",
                            module=logger.name,
                            fields={
                                "report_id": report_id,
                                "pack": current_step,
                                "error": str(exc),
                            },
                        )
                    )
            if first_error is not None:
                for future in futures:
                    future.cancel()
                failed_step, first_exc = first_error
                if isinstance(first_exc, AppError):
                    raise first_exc
                raise AppError(
                    code="evidence_pack_step_failed",
                    message=f"Evidence pack step failed: {failed_step}",
                    cause=first_exc,
                    retryable=True,
                    context={"report_id": report_id, "pack": failed_step},
                ) from first_exc
    else:
        for strategy in parallel_strategies:
            step_name = strategy.pack_name
            step_ctx = child_context(ctx, task_id=f"{ctx.task_id}:{step_name}")
            parallel_results[step_name] = _generate_pack(
                report_id=report_id,
                report_name=report_name,
                vector_store_id=vector_store_id,
                settings=settings,
                ctx=step_ctx,
                md5=md5,
                openai_client=openai_client,
                prompt_client=prompt_client,
                analysis_store=analysis_store,
                strategy=strategy,
            )
    for strategy in parallel_strategies:
        results[strategy.pack_name] = parallel_results[strategy.pack_name]
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="evidence_pack_complete",
            module=logger.name,
            fields={"report_id": report_id, "packs": list(results.keys())},
        )
    )
    return results


def _generate_pack(
    *,
    report_id: str,
    report_name: str,
    vector_store_id: str,
    settings: AppSettings,
    ctx: RunContext,
    md5: Optional[str],
    openai_client,
    prompt_client,
    analysis_store,
    strategy: EvidencePackStrategy,
) -> dict:
    pack_name = strategy.pack_name
    prompt_namespace = _prompt_namespace_for_strategy(strategy)
    schema_name = strategy.schema_name
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="evidence_pack_step_start",
            module=logger.name,
            fields={
                "report_id": report_id,
                "pack": pack_name,
                "prompt_namespace": prompt_namespace,
            },
        )
    )
    prompt_bundle = prepare_prompt_bundle(
        namespace=prompt_namespace,
        settings=settings,
        ctx=ctx,
        prompt_client=prompt_client,
        system_variables={},
        user_variables={},
        default_model=settings.openai_model,
    )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="evidence_pack_prompt_rendered",
            module=logger.name,
            fields={
                "pack": pack_name,
                "namespace": prompt_namespace,
                "system_path": prompt_bundle.prompt_set.system.path,
                "user_path": prompt_bundle.prompt_set.user.path,
                "prompt_system_sha256": prompt_bundle.prompt_set.system.sha256,
                "prompt_user_sha256": prompt_bundle.prompt_set.user.sha256,
                "system_prompt": prompt_bundle.system_prompt,
                "user_prompt": prompt_bundle.user_prompt,
                "resolved_model": prompt_bundle.resolved_model,
                "temperature": settings.temperature,
            },
        )
    )
    cache_meta = None
    cache_key = ""
    if md5:
        cache_meta = {
            "schema_version": "1.0",
            "adapter_version": "2",
            "md5": md5,
            "pack_name": pack_name,
            "schema_name": schema_name,
            "prompt_system_sha256": prompt_bundle.prompt_set.system.sha256,
            "prompt_user_sha256": prompt_bundle.prompt_set.user.sha256,
            "model": prompt_bundle.resolved_model,
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
                normalized_cached = strategy.normalize_payload(
                    cached, report_id, report_name
                )
                cached = normalized_cached.payload
                if normalized_cached.changed:
                    _store_pack(
                        analysis_store=analysis_store,
                        output_dir=settings.output_dir,
                        report_id=report_id,
                        pack_name=pack_name,
                        payload=cached,
                        ctx=ctx,
                        report_name=report_name,
                    )
                    if pack_name == "doc_map":
                        logger.info(
                            log_event(
                                ctx,
                                role="generator",
                                event="doc_map_cache_normalized",
                                module=logger.name,
                                fields={
                                    "report_id": report_id,
                                    "wrapper_key": normalized_cached.metadata[
                                        "wrapper_key"
                                    ],
                                    "sections_with_ids": normalized_cached.metadata[
                                        "sections_with_ids"
                                    ],
                                    "added_section_ids": normalized_cached.metadata[
                                        "added_section_ids"
                                    ],
                                    "dropped_sections": normalized_cached.metadata[
                                        "dropped_sections"
                                    ],
                                    "doc_id_filled": normalized_cached.metadata[
                                        "doc_id_filled"
                                    ],
                                },
                            )
                        )
                if pack_name == "doc_map":
                    summary = _summarize_doc_map(cached)
                    if not summary["has_content"]:
                        logger.info(
                            log_event(
                                ctx,
                                role="generator",
                                event="evidence_pack_cache_rejected",
                                module=logger.name,
                                fields={
                                    "report_id": report_id,
                                    "pack": pack_name,
                                    "reason": summary["not_found_reason"]
                                    or "doc_map_no_content",
                                },
                            )
                        )
                        cached = None
                logger.info(
                    log_event(
                        ctx,
                        role="generator",
                        event="evidence_pack_cache_hit",
                        module=logger.name,
                        fields={"report_id": report_id, "pack": pack_name},
                    )
                )
                if cached is not None:
                    return cached
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="model_resolved",
            module=logger.name,
            fields={
                "namespace": prompt_namespace,
                "resolved_model": prompt_bundle.resolved_model,
                "default_model": settings.openai_model,
            },
        )
    )
    parsed_json: Optional[dict] = None
    not_found_reason = ""
    max_attempts = 1
    attempts_used = 1
    try:
        resp: OpenAIResponseResult = openai_client.openai_respond_with_vector_store(
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
        logger.info(
            log_event(
                ctx,
                role="generator",
                event="evidence_pack_raw_response",
                module=logger.name,
                fields={
                    "report_id": report_id,
                    "pack": pack_name,
                    "namespace": prompt_namespace,
                    "model": str(resp.model or prompt_bundle.resolved_model or ""),
                    "request_id": resp.request_id or "",
                    "input_tokens": resp.input_tokens,
                    "output_tokens": resp.output_tokens,
                    "tool_calls": resp.tool_calls,
                    "has_json": isinstance(resp.parsed_json, (dict, list)),
                    "raw_response": str(resp.text or ""),
                },
            )
        )
        parsed_payload: Optional[object] = (
            resp.parsed_json if isinstance(resp.parsed_json, (dict, list)) else None
        )
        if parsed_payload is None:
            parsed_payload = _parse_json_payload_from_text(resp.text or "")
            if parsed_payload is not None:
                logger.info(
                    log_event(
                        ctx,
                        role="generator",
                        event="evidence_pack_json_text_fallback",
                        module=logger.name,
                        fields={
                            "report_id": report_id,
                            "pack": pack_name,
                            "attempt": 1,
                        },
                    )
                )
        if parsed_payload is None:
            not_found_reason = "model_returned_no_json"
        else:
            try:
                if pack_name == "doc_map" and not isinstance(parsed_payload, dict):
                    raise AppError(
                        code="schema_type_mismatch",
                        message="doc_map payload must be a JSON object",
                        retryable=False,
                    )
                normalized_result = strategy.normalize_payload(
                    parsed_payload, report_id, report_name
                )
                parsed_json = normalized_result.payload
                if pack_name == "doc_map" and normalized_result.changed:
                    logger.info(
                        log_event(
                            ctx,
                            role="generator",
                            event="doc_map_normalized",
                            module=logger.name,
                            fields={
                                "report_id": report_id,
                                "wrapper_key": normalized_result.metadata[
                                    "wrapper_key"
                                ],
                                "sections_with_ids": normalized_result.metadata[
                                    "sections_with_ids"
                                ],
                                "added_section_ids": normalized_result.metadata[
                                    "added_section_ids"
                                ],
                                "dropped_sections": normalized_result.metadata[
                                    "dropped_sections"
                                ],
                                "doc_id_filled": normalized_result.metadata[
                                    "doc_id_filled"
                                ],
                            },
                        )
                    )
                if getattr(settings, "strict_schema_validation", True):
                    validate_schema(
                        SchemaValidateRequest(
                            schema_version="1.0",
                            payload=parsed_json,
                            schema_name=schema_name,
                        ),
                        ctx,
                    )
            except AppError as exc:
                if exc.retryable:
                    logger.info(
                        log_event(
                            ctx,
                            role="generator",
                            event="evidence_pack_retryable_error_propagated",
                            module=logger.name,
                            fields={
                                "report_id": report_id,
                                "pack": pack_name,
                                "code": exc.code,
                                "message": exc.message,
                                "source": "schema_validation",
                            },
                        )
                    )
                    raise
                not_found_reason = f"schema_validation_failed:{exc.code}"
                parsed_json = None
    except AppError as exc:
        if exc.retryable:
            logger.info(
                log_event(
                    ctx,
                    role="generator",
                    event="evidence_pack_retryable_error_propagated",
                    module=logger.name,
                    fields={
                        "report_id": report_id,
                        "pack": pack_name,
                        "code": exc.code,
                        "message": exc.message,
                        "source": "model_call",
                    },
                )
            )
            raise
        if exc.code in {
            "openai_response_empty",
            "openai_response_invalid_json",
            "openai_response_json_type_invalid",
        }:
            not_found_reason = "model_returned_no_json"
        else:
            not_found_reason = exc.code
        parsed_json = None
    result_payload = parsed_json or _empty_payload(pack_name, not_found_reason)
    if cache_meta and isinstance(result_payload, dict):
        result_payload = dict(result_payload)
        result_payload["_cache"] = {**cache_meta, "key": cache_key}
    _store_pack(
        analysis_store=analysis_store,
        output_dir=settings.output_dir,
        report_id=report_id,
        pack_name=pack_name,
        payload=result_payload,
        ctx=ctx,
        report_name=report_name,
    )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="evidence_pack_step_complete",
            module=logger.name,
            fields={
                "report_id": report_id,
                "pack": pack_name,
                "not_found_reason": not_found_reason,
                "attempts": attempts_used,
                "max_attempts": max_attempts,
            },
        )
    )
    return result_payload


def _empty_payload(pack_name: str, reason: str) -> dict:
    return PACK_STRATEGIES[pack_name].empty_payload(reason)


def _normalize_evidence_pack_payload(payload: object, pack_name: str) -> dict:
    if pack_name == "doc_map":
        raise AppError(
            code="invalid_pack_strategy",
            message="doc_map uses _normalize_doc_map_payload",
            retryable=False,
        )
    return PACK_STRATEGIES[pack_name].normalize_payload(payload, "", "").payload


def _normalize_doc_map_payload(
    payload: dict, report_id: str, report_name: str = ""
) -> Tuple[dict, dict]:
    normalized = normalize_doc_map_payload(payload, report_id, report_name)
    return normalized.payload, normalized.metadata


def _summarize_doc_map(payload: dict) -> dict:
    return summarize_doc_map(payload)


def _summarize_doc_map_completeness(payload: dict) -> dict:
    return summarize_doc_map_completeness(payload)


def _resolve_pack_path(
    output_dir: str,
    report_id: str,
    pack_name: str,
    report_name: str,
    analysis_store,
    ctx: RunContext,
) -> str:
    return resolve_analysis_pack_path(
        analysis_store=analysis_store,
        request=AnalysisPackPathRequest(
            schema_version="1.0",
            output_dir=output_dir,
            report_id=report_id,
            pack_name=pack_name,
            report_slug=report_name,
        ),
        ctx=ctx,
    )


def _store_pack(
    *,
    analysis_store,
    output_dir: str,
    report_id: str,
    pack_name: str,
    payload: dict,
    ctx: RunContext,
    report_name: str,
) -> str:
    return store_analysis_pack(
        analysis_store=analysis_store,
        request=AnalysisStorePackRequest(
            schema_version="1.0",
            output_dir=output_dir,
            report_id=report_id,
            pack_name=pack_name,
            payload=payload,
            report_slug=report_name,
        ),
        ctx=ctx,
    )


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
    def _log_read_failed(exc: AppError, path: str) -> None:
        del path
        logger.info(
            log_event(
                ctx,
                role="generator",
                event="evidence_pack_cache_read_failed",
                module=logger.name,
                fields={
                    "report_id": report_id,
                    "pack": pack_name,
                    "error": exc.message,
                },
            )
        )

    def _adapt_payload(
        payload: Dict[str, object], path: str
    ) -> CachedPackAdaptResult[dict]:
        strategy = PACK_STRATEGIES[pack_name]
        normalized_payload = dict(
            strategy.normalize_payload(payload, report_id, report_name).payload
        )
        try:
            validate_schema(
                SchemaValidateRequest(
                    schema_version="1.0",
                    payload=normalized_payload,
                    schema_name=strategy.schema_name,
                ),
                ctx,
            )
        except AppError as exc:
            logger.info(
                log_event(
                    ctx,
                    role="generator",
                    event="evidence_pack_cache_invalid",
                    module=logger.name,
                    fields={
                        "report_id": report_id,
                        "pack": pack_name,
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
        not_found_reason = str(normalized_payload.get("not_found_reason") or "").strip()
        if not_found_reason:
            logger.info(
                log_event(
                    ctx,
                    role="generator",
                    event="evidence_pack_cache_rejected",
                    module=logger.name,
                    fields={
                        "report_id": report_id,
                        "pack": pack_name,
                        "reason": not_found_reason,
                    },
                )
            )
            return CachedPackAdaptResult(
                schema_version="1.0",
                status="cache_rejected",
                value=None,
            )
        return CachedPackAdaptResult(
            schema_version="1.0",
            status="hit",
            value=normalized_payload,
        )

    result = load_cached_pack(
        cache_key=cache_key,
        ctx=ctx,
        resolve_path=lambda: _resolve_pack_path(
            output_dir, report_id, pack_name, report_name, analysis_store, ctx
        ),
        read_text=file_service.read_text,
        on_read_failed=_log_read_failed,
        adapt_payload=_adapt_payload,
    )
    if result.status == "key_mismatch":
        logger.info(
            log_event(
                ctx,
                role="generator",
                event="evidence_pack_cache_miss",
                module=logger.name,
                fields={"report_id": report_id, "pack": pack_name},
            )
        )
    return result.value if result.status == "hit" else None
