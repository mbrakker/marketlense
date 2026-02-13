from __future__ import annotations

import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from src.contracts.config import AppSettings
from src.contracts.files import ReadTextRequest
from src.contracts.openai import OpenAIResponseRequest, OpenAIResponseResult
from src.contracts.prompts import PromptLoadRequest
from src.contracts.report_analysis import AnalysisPackPathRequest, AnalysisStorePackRequest
from src.contracts.run_context import RunContext
from src.contracts.schema_validation import SchemaValidateRequest
from src.services import file_service
from src.services import openai_service
from src.services import prompt_service
from src.services import report_analysis_store_service
from src.utils.logging import child_context, log_event, new_run_context
from src.services.schema_validator_service import validate_schema
from src.utils.errors import AppError
from src.utils.model_resolver import resolve_model
from src.utils.cache_utils import sha256_json
from src.utils.slugify import slugify

logger = logging.getLogger("market_lense.evidence_pack_generator")


@dataclass
class _GlobalEvidencePackLimiter:
    max_in_flight: int
    min_interval_s: float
    semaphore: threading.BoundedSemaphore
    gate_lock: threading.Lock
    next_allowed_monotonic: float


_GLOBAL_LIMITER_LOCK = threading.Lock()
_GLOBAL_LIMITER: Optional[_GlobalEvidencePackLimiter] = None


def _safe_int(value: object, default: int, *, min_value: int = 0) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    if parsed < min_value:
        return min_value
    return parsed


def _get_global_limiter(settings: AppSettings) -> _GlobalEvidencePackLimiter:
    global _GLOBAL_LIMITER
    max_in_flight = _safe_int(getattr(settings, "evidence_pack_global_max_in_flight", 2), 2, min_value=1)
    min_interval_ms = _safe_int(getattr(settings, "evidence_pack_global_min_interval_ms", 250), 250, min_value=0)
    min_interval_s = float(min_interval_ms) / 1000.0
    with _GLOBAL_LIMITER_LOCK:
        if (
            _GLOBAL_LIMITER is None
            or _GLOBAL_LIMITER.max_in_flight != max_in_flight
            or abs(_GLOBAL_LIMITER.min_interval_s - min_interval_s) > 1e-9
        ):
            _GLOBAL_LIMITER = _GlobalEvidencePackLimiter(
                max_in_flight=max_in_flight,
                min_interval_s=min_interval_s,
                semaphore=threading.BoundedSemaphore(max_in_flight),
                gate_lock=threading.Lock(),
                next_allowed_monotonic=0.0,
            )
        return _GLOBAL_LIMITER


@contextmanager
def _acquire_rate_limit(settings: AppSettings, ctx: RunContext, pack_name: str):
    limiter = _get_global_limiter(settings)
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
                event="evidence_pack_rate_limiter_wait",
                module=logger.name,
                fields={
                    "pack": pack_name,
                    "in_flight_wait_ms": in_flight_wait_ms,
                    "rate_wait_ms": rate_wait_ms,
                    "global_max_in_flight": limiter.max_in_flight,
                    "global_min_interval_ms": int(round(limiter.min_interval_s * 1000)),
                },
            ))
        yield
    finally:
        limiter.semaphore.release()


def _pack_parallel_workers(settings: AppSettings, step_count: int) -> int:
    configured = _safe_int(getattr(settings, "evidence_pack_parallel_workers", 3), 3, min_value=1)
    return max(1, min(configured, step_count))


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
    limiter = _get_global_limiter(settings)
    parallel_workers = _pack_parallel_workers(settings, max(0, len(steps) - 1))
    logger.info(log_event(
        ctx,
        role="generator",
        event="evidence_pack_parallel_config",
        module=logger.name,
        fields={
            "report_id": report_id,
            "parallel_workers": parallel_workers,
            "global_max_in_flight": limiter.max_in_flight,
            "global_min_interval_ms": int(round(limiter.min_interval_s * 1000)),
            "parallel_step_count": max(0, len(steps) - 1),
        },
    ))

    # `doc_map` is a hard gate; other packs depend on it being non-empty.
    doc_step = steps[0]
    step_name, prompt_ns, schema = doc_step
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

    parallel_steps = steps[1:]
    parallel_results: Dict[str, dict] = {}
    if parallel_steps and parallel_workers > 1:
        with ThreadPoolExecutor(max_workers=parallel_workers) as executor:
            futures = {}
            for step_name, prompt_ns, schema in parallel_steps:
                step_ctx = child_context(ctx, task_id=f"{ctx.task_id}:{step_name}")
                future = executor.submit(
                    _generate_pack,
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
                futures[future] = step_name
            first_error: Optional[Tuple[str, Exception]] = None
            for future in as_completed(futures):
                current_step = futures[future]
                try:
                    parallel_results[current_step] = future.result()
                except Exception as exc:  # pragma: no cover - defensive fallback
                    if first_error is None:
                        first_error = (current_step, exc)
                    logger.info(log_event(
                        ctx,
                        role="generator",
                        event="evidence_pack_parallel_step_failed",
                        module=logger.name,
                        fields={"report_id": report_id, "pack": current_step, "error": str(exc)},
                    ))
            if first_error is not None:
                for future in futures:
                    future.cancel()
                failed_step, exc = first_error
                if isinstance(exc, AppError):
                    raise exc
                raise AppError(
                    code="evidence_pack_step_failed",
                    message=f"Evidence pack step failed: {failed_step}",
                    cause=exc,
                    retryable=True,
                    context={"report_id": report_id, "pack": failed_step},
                ) from exc
    else:
        for step_name, prompt_ns, schema in parallel_steps:
            step_ctx = child_context(ctx, task_id=f"{ctx.task_id}:{step_name}")
            parallel_results[step_name] = _generate_pack(
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
    for step_name, _, _ in parallel_steps:
        results[step_name] = parallel_results[step_name]
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
                if schema_name == "doc_map":
                    cached, normalization = _normalize_doc_map_payload(cached, report_id)
                    if normalization["changed"]:
                        _store_pack(
                            analysis_store=analysis_store,
                            output_dir=settings.output_dir,
                            report_id=report_id,
                            pack_name=pack_name,
                            payload=cached,
                            ctx=ctx,
                            report_name=report_name,
                            mirror_legacy=settings.mirror_legacy_packs,
                        )
                        logger.info(log_event(
                            ctx,
                            role="generator",
                            event="doc_map_cache_normalized",
                            module=logger.name,
                            fields={
                                "report_id": report_id,
                                "wrapper_key": normalization["wrapper_key"],
                                "sections_with_ids": normalization["sections_with_ids"],
                                "added_section_ids": normalization["added_section_ids"],
                                "dropped_sections": normalization["dropped_sections"],
                                "doc_id_filled": normalization["doc_id_filled"],
                            },
                        ))
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
        with _acquire_rate_limit(settings, ctx, pack_name):
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
                if schema_name == "doc_map" and isinstance(parsed_json, dict):
                    parsed_json, normalization = _normalize_doc_map_payload(parsed_json, report_id)
                    if normalization["changed"]:
                        logger.info(log_event(
                            ctx,
                            role="generator",
                            event="doc_map_normalized",
                            module=logger.name,
                            fields={
                                "report_id": report_id,
                                "wrapper_key": normalization["wrapper_key"],
                                "sections_with_ids": normalization["sections_with_ids"],
                                "added_section_ids": normalization["added_section_ids"],
                                "dropped_sections": normalization["dropped_sections"],
                                "doc_id_filled": normalization["doc_id_filled"],
                            },
                        ))
                validate_schema(
                    SchemaValidateRequest(schema_version="1.0", payload=parsed_json, schema_name=schema_name),
                    ctx,
                )
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
    _store_pack(
        analysis_store=analysis_store,
        output_dir=settings.output_dir,
        report_id=report_id,
        pack_name=pack_name,
        payload=result_payload,
        ctx=ctx,
        report_name=report_name,
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


def _normalize_doc_map_payload(payload: dict, report_id: str) -> Tuple[dict, dict]:
    wrapper_key = ""
    candidate = payload
    if isinstance(payload.get("docmap"), dict):
        wrapper_key = "docmap"
        candidate = payload["docmap"]
    elif isinstance(payload.get("doc_map"), dict):
        wrapper_key = "doc_map"
        candidate = payload["doc_map"]
    normalized = dict(candidate) if isinstance(candidate, dict) else {}
    cache_meta = payload.get("_cache") if isinstance(payload.get("_cache"), dict) else None
    if cache_meta:
        normalized["_cache"] = cache_meta
    doc_id = str(normalized.get("doc_id") or "").strip()
    doc_id_filled = False
    if not doc_id:
        normalized["doc_id"] = report_id
        doc_id_filled = True
    sections = normalized.get("sections")
    sections_with_ids = 0
    added_section_ids = 0
    dropped_sections = 0
    if isinstance(sections, list):
        updated_sections = []
        for idx, section in enumerate(sections):
            if not isinstance(section, dict):
                dropped_sections += 1
                continue
            sec = dict(section)
            sec_id = str(sec.get("id") or "").strip()
            if not sec_id:
                title = str(sec.get("title") or "").strip()
                slug = slugify(title) if title else ""
                sec_id = slug or f"section_{idx + 1}"
                sec["id"] = sec_id
                added_section_ids += 1
            sections_with_ids += 1 if sec.get("id") else 0
            updated_sections.append(sec)
        normalized["sections"] = updated_sections
    changed = wrapper_key != "" or doc_id_filled or added_section_ids > 0 or dropped_sections > 0
    return normalized, {
        "changed": changed,
        "wrapper_key": wrapper_key,
        "sections_with_ids": sections_with_ids,
        "added_section_ids": added_section_ids,
        "dropped_sections": dropped_sections,
        "doc_id_filled": doc_id_filled,
    }


def _resolve_pack_path(
    output_dir: str,
    report_id: str,
    pack_name: str,
    report_name: str,
    analysis_store,
    ctx: RunContext,
) -> str:
    if hasattr(analysis_store, "pack_path"):
        try:
            response = analysis_store.pack_path(
                AnalysisPackPathRequest(
                    schema_version="1.0",
                    output_dir=output_dir,
                    report_id=report_id,
                    pack_name=pack_name,
                    report_slug=report_name,
                ),
                ctx,
            )
            if isinstance(response, str):
                return response
            output_path = getattr(response, "output_path", None)
            if isinstance(output_path, str):
                return output_path
        except TypeError:
            return str(analysis_store.pack_path(output_dir, report_id, pack_name, report_slug=report_name))
    return report_analysis_store_service.pack_path(
        AnalysisPackPathRequest(
            schema_version="1.0",
            output_dir=output_dir,
            report_id=report_id,
            pack_name=pack_name,
            report_slug=report_name,
        ),
        ctx,
    ).output_path


def _store_pack(
    *,
    analysis_store,
    output_dir: str,
    report_id: str,
    pack_name: str,
    payload: dict,
    ctx: RunContext,
    report_name: str,
    mirror_legacy: bool,
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
                    report_slug=report_name,
                    mirror_legacy=mirror_legacy,
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
                report_slug=report_name,
                mirror_legacy=mirror_legacy,
            ))
    return report_analysis_store_service.store_pack(
        AnalysisStorePackRequest(
            schema_version="1.0",
            output_dir=output_dir,
            report_id=report_id,
            pack_name=pack_name,
            payload=payload,
            report_slug=report_name,
            mirror_legacy=mirror_legacy,
        ),
        ctx,
    ).output_path


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
    path = _resolve_pack_path(output_dir, report_id, pack_name, report_name, analysis_store, ctx)
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
