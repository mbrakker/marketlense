from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from hashlib import sha256
from typing import Dict, Optional, Tuple

from src.contracts.analysis_family import AnalysisFamilyStatus
from src.contracts.config import AppSettings
from src.contracts.report_analysis import (
    AnalysisPackPathRequest,
    AnalysisStorePackRequest,
)
from src.contracts.run_context import RunContext
from src.contracts.schema_validation import SchemaValidateRequest
from src.contracts.semantic_ids import ReportId
from src.contracts.structured_output import StructuredOutputExecutionRequest
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
from src.generators.evidence_packs.base import EvidencePackStrategy
from src.generators.evidence_packs.doc_map_strategy import (
    normalize_payload as normalize_doc_map_payload,
)
from src.generators.evidence_packs.doc_map_strategy import (
    summarize_completeness as summarize_doc_map_completeness,
)
from src.generators.evidence_packs.doc_map_strategy import (
    summarize_payload as summarize_doc_map,
)
from src.generators.evidence_packs.registry import (
    DEFAULT_PACK_REGISTRY,
    PACK_STRATEGIES,
    VARIETY_PACKS,
)
from src.generators.prompt_preparation import prepare_prompt_bundle
from src.generators.structured_output_execution import (
    invoke_structured_output_model,
    recovery_prompt_bundle,
)
from src.services import file_service, prompt_service, report_analysis_store_service
from src.services.schema_validator_service import (
    provider_output_schema,
    validate_schema,
)
from src.services.structured_output_service import execute_structured_output
from src.utils.analysis_family import serialize_family_status
from src.utils.cache_utils import sha256_json
from src.utils.coercion import coerce_int
from src.utils.errors import AppError
from src.utils.json_recovery import parse_json_from_text, strip_json_fence
from src.utils.logging import child_context, log_event, new_run_context
from src.utils.model_client_contract import require_injected_model_client

logger = logging.getLogger("market_lense.evidence_pack_generator")

_OPTIONAL_EVIDENCE_PACKS = {
    "scope",
    "methods",
    "findings",
    "limitations",
    "quote_candidates",
    "key_metrics",
    "risk_register",
    "recommendations",
    "contradictions",
}


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


def _attach_pack_family_status(pack_name: str, payload: dict) -> dict:
    enriched = dict(payload)
    enriched["family_status"] = serialize_family_status(
        _build_pack_family_status(pack_name, enriched)
    )
    return enriched


def _build_pack_family_status(
    pack_name: str,
    payload: dict,
) -> AnalysisFamilyStatus:
    confidence_score = _pack_confidence_score(pack_name, payload)
    not_found_reason = str(payload.get("not_found_reason") or "").strip()
    if not_found_reason:
        status = "abstained"
        reason = not_found_reason
    elif confidence_score <= 0.0:
        status = "abstained"
        reason = "insufficient_pack_content"
    else:
        status = "generated"
        reason = ""
    policy_action = _pack_policy_action(pack_name, status)
    return AnalysisFamilyStatus(
        schema_version="1.0",
        family=pack_name,
        source="evidence_pack",
        status=status,
        confidence_score=confidence_score,
        policy_action=policy_action,
        reason=reason,
    )


def _pack_policy_action(pack_name: str, status: str) -> str:
    if status != "abstained":
        return "keep"
    if pack_name == "doc_map":
        return "regenerate"
    if pack_name in _OPTIONAL_EVIDENCE_PACKS:
        return "abstain"
    return "regenerate"


def _pack_confidence_score(pack_name: str, payload: dict) -> float:
    if str(payload.get("not_found_reason") or "").strip():
        return 0.0
    if pack_name == "doc_map":
        return _doc_map_confidence_score(payload)
    if pack_name in {"scope", "methods"}:
        return _scalar_or_list_pack_confidence(payload, root_key=pack_name)
    if pack_name in {
        "findings",
        "limitations",
        "quote_candidates",
        "key_metrics",
        "risk_register",
        "recommendations",
        "contradictions",
    }:
        return _scalar_or_list_pack_confidence(payload, root_key=pack_name)
    return 0.0


def _doc_map_confidence_score(payload: dict) -> float:
    raw_sections = payload.get("sections")
    sections = raw_sections if isinstance(raw_sections, list) else []
    title_present = bool(str(payload.get("title") or "").strip())
    doc_id_present = bool(str(payload.get("doc_id") or "").strip())
    sections_with_summary = 0
    for entry in sections:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("summary") or "").strip():
            sections_with_summary += 1
    score = 0.0
    if title_present:
        score += 0.2
    if doc_id_present:
        score += 0.15
    if sections:
        score += 0.35
        score += 0.3 * (sections_with_summary / max(1, len(sections)))
    return max(0.0, min(1.0, round(score, 3)))


def _scalar_or_list_pack_confidence(payload: dict, *, root_key: str) -> float:
    value = payload.get(root_key)
    if isinstance(value, list):
        if not value:
            return 0.0
        substantive = 0
        for item in value:
            if isinstance(item, str) and item.strip():
                substantive += 1
                continue
            if isinstance(item, dict) and any(
                str(v or "").strip() for v in item.values()
            ):
                substantive += 1
        ratio = substantive / max(1, len(value))
        return max(0.0, min(1.0, round(0.4 + (0.5 * ratio), 3)))
    if isinstance(value, dict):
        substantive = any(str(v or "").strip() for v in value.values())
        return 0.9 if substantive else 0.0
    if isinstance(value, str):
        return 0.9 if value.strip() else 0.0
    return 0.0


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
    publisher_name: str = "",
    source_url: str = "",
    *,
    openai_client=None,
    prompt_client=prompt_service,
    analysis_store=report_analysis_store_service,
) -> Dict[str, dict]:
    ctx = ctx or new_run_context(task_id=f"evidence_pack:{report_id}")
    openai_client = require_injected_model_client(
        openai_client,
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
        publisher_name=publisher_name,
        source_url=source_url,
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
                    "sections_missing_summary": completeness[
                        "sections_missing_summary"
                    ],
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
                    publisher_name=publisher_name,
                    source_url=source_url,
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
                publisher_name=publisher_name,
                source_url=source_url,
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
    publisher_name: str,
    source_url: str,
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
                "resolved_model": prompt_bundle.resolved_model,
                "temperature": prompt_bundle.effective_temperature,
                "execution_policy_hash": prompt_bundle.execution_policy.policy_hash,
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
                    return _attach_pack_family_status(pack_name, cached)
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
    not_found_reason = ""
    output_schema = provider_output_schema(schema_name)

    def call_model(mode: str, original_response: str, schema_errors: str):
        bundle = prompt_bundle
        if mode != "primary":
            bundle = recovery_prompt_bundle(
                mode=mode,
                artifact_family=pack_name,
                schema_errors=schema_errors,
                original_response=original_response,
                output_schema=output_schema,
                source_evidence={
                    "report_name": report_name,
                    "vector_store_id": vector_store_id,
                    "pack_name": pack_name,
                },
                settings=settings,
                ctx=ctx,
                prompt_client=prompt_client,
                vector_store_id=vector_store_id,
            )
        resp = invoke_structured_output_model(
            openai_client=openai_client,
            prompt_bundle=bundle,
            settings=settings,
            ctx=ctx,
            vector_store_id=vector_store_id,
            report_id=report_id,
            artifact_family=pack_name,
            stage=f"evidence_pack_{mode}",
            publisher_name=publisher_name,
            report_name=report_name,
            source_url=source_url,
            output_schema=output_schema,
            output_schema_identity=f"{pack_name}_v1",
            repair_attempt={"primary": 0, "model_repair": 1, "regeneration": 2}[mode],
        )
        logger.info(
            log_event(
                ctx,
                role="generator",
                event="evidence_pack_response_received",
                module=logger.name,
                fields={
                    "report_id": report_id,
                    "pack": pack_name,
                    "namespace": bundle.dependency_manifest.namespace,
                    "model": str(resp.model or bundle.resolved_model or ""),
                    "request_id": resp.request_id or "",
                    "input_tokens": resp.input_tokens,
                    "output_tokens": resp.output_tokens,
                    "tool_calls": resp.tool_calls,
                    "has_json": isinstance(resp.parsed_json, (dict, list)),
                    "response_chars": len(str(resp.text or "")),
                    "response_sha256": sha256(
                        str(resp.text or "").encode("utf-8")
                    ).hexdigest(),
                },
            )
        )
        return resp

    def normalize_payload(payload: object) -> dict:
        if pack_name == "doc_map" and not isinstance(payload, dict):
            raise AppError(
                code="schema_type_mismatch",
                message="doc_map payload must be a JSON object",
                retryable=False,
            )
        return strategy.normalize_payload(payload, report_id, report_name).payload

    recovery = execute_structured_output(
        StructuredOutputExecutionRequest(
            schema_version="1.0",
            report_id=report_id,
            artifact_family=pack_name,
            schema_name=schema_name,
            model=prompt_bundle.resolved_model,
            allow_abstention=pack_name in _OPTIONAL_EVIDENCE_PACKS,
            terminal_failure_code=("doc_map_invalid_json" if pack_name == "doc_map" else "evidence_pack_invalid_json"),
        ),
        ctx,
        call_model=call_model,
        normalize_payload=normalize_payload,
        validate_payload=lambda payload: validate_schema(
            SchemaValidateRequest(
                schema_version="1.0", payload=payload, schema_name=schema_name
            ),
            ctx,
        ),
        is_substantive=lambda payload: _pack_confidence_score(pack_name, payload) > 0.0,
        model_pricing=settings.model_pricing,
        is_formal_abstention=lambda payload: bool(
            isinstance(payload, dict)
            and str(payload.get("not_found_reason") or "").strip()
        ),
    )
    result_payload = recovery.payload
    not_found_reason = str(result_payload.get("not_found_reason") or "")
    attempts_used = recovery.attempts
    max_attempts = 3
    result_payload = _attach_pack_family_status(pack_name, result_payload)
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
            report_id=ReportId(report_id),
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
            report_id=ReportId(report_id),
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
        normalized_payload = _attach_pack_family_status(pack_name, normalized_payload)
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
