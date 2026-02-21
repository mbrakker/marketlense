from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, Optional, Tuple

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


def _safe_int(value: object, default: int, *, min_value: int = 0) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    if parsed < min_value:
        return min_value
    return parsed


def _pack_parallel_workers(settings: AppSettings, step_count: int) -> int:
    configured = _safe_int(getattr(settings, "evidence_pack_parallel_workers", 3), 3, min_value=1)
    return max(1, min(configured, step_count))


def _strip_json_fence(text: str) -> str:
    stripped = (text or "").strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if len(lines) < 2 or lines[-1].strip() != "```":
        return stripped
    first_line = lines[0].strip().lower()
    if first_line not in {"```", "```json", "```jsonc", "```javascript", "```js"}:
        return stripped
    return "\n".join(lines[1:-1]).strip()


def _extract_json_value(text: str) -> str:
    source = (text or "").strip()
    start = -1
    for idx, ch in enumerate(source):
        if ch in {"{", "["}:
            start = idx
            break
    if start < 0:
        return ""
    stack: list[str] = []
    in_string = False
    escaped = False
    for idx in range(start, len(source)):
        ch = source[idx]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == "\"":
                in_string = False
            continue
        if ch == "\"":
            in_string = True
            continue
        if ch == "{":
            stack.append("}")
            continue
        if ch == "[":
            stack.append("]")
            continue
        if ch in {"}", "]"}:
            if not stack or ch != stack[-1]:
                return ""
            stack.pop()
            if not stack:
                return source[start:idx + 1]
    return ""


def _parse_json_payload_from_text(text: str) -> Optional[object]:
    normalized = (text or "").strip()
    if not normalized:
        return None
    candidates = [normalized]
    stripped_fence = _strip_json_fence(normalized)
    if stripped_fence and stripped_fence != normalized:
        candidates.append(stripped_fence)
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, (dict, list)):
            return parsed
        extracted = _extract_json_value(candidate)
        if not extracted:
            continue
        try:
            parsed_extracted = json.loads(extracted)
        except json.JSONDecodeError:
            parsed_extracted = None
        if isinstance(parsed_extracted, (dict, list)):
            return parsed_extracted
    return None


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
    parallel_workers = _pack_parallel_workers(settings, max(0, len(steps) - 1))
    logger.info(log_event(
        ctx,
        role="generator",
        event="evidence_pack_parallel_config",
        module=logger.name,
        fields={
            "report_id": report_id,
            "parallel_workers": parallel_workers,
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
            "adapter_version": "2",
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
                    summary = _summarize_doc_map(cached)
                    if not summary["has_content"]:
                        logger.info(log_event(
                            ctx,
                            role="generator",
                            event="evidence_pack_cache_rejected",
                            module=logger.name,
                            fields={
                                "report_id": report_id,
                                "pack": pack_name,
                                "reason": summary["not_found_reason"] or "doc_map_no_content",
                            },
                        ))
                        cached = None
                elif isinstance(cached, dict):
                    normalized_cached = _normalize_evidence_pack_payload(cached, pack_name)
                    if normalized_cached != cached:
                        _store_pack(
                            analysis_store=analysis_store,
                            output_dir=settings.output_dir,
                            report_id=report_id,
                            pack_name=pack_name,
                            payload=normalized_cached,
                            ctx=ctx,
                            report_name=report_name,
                        )
                        cached = normalized_cached
                logger.info(log_event(
                    ctx,
                    role="generator",
                    event="evidence_pack_cache_hit",
                    module=logger.name,
                    fields={"report_id": report_id, "pack": pack_name},
                ))
                if cached is not None:
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
    parsed_json: Optional[dict] = None
    not_found_reason = ""
    max_attempts = 1
    attempts_used = 1
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
        parsed_payload: Optional[object] = resp.parsed_json if isinstance(resp.parsed_json, (dict, list)) else None
        if parsed_payload is None:
            parsed_payload = _parse_json_payload_from_text(resp.text or "")
            if parsed_payload is not None:
                logger.info(log_event(
                    ctx,
                    role="generator",
                    event="evidence_pack_json_text_fallback",
                    module=logger.name,
                    fields={
                        "report_id": report_id,
                        "pack": pack_name,
                        "attempt": 1,
                    },
                ))
        if parsed_payload is None:
            not_found_reason = "model_returned_no_json"
        else:
            try:
                if schema_name == "doc_map":
                    if not isinstance(parsed_payload, dict):
                        raise AppError(
                            code="schema_type_mismatch",
                            message="doc_map payload must be a JSON object",
                            retryable=False,
                        )
                    parsed_json, normalization = _normalize_doc_map_payload(parsed_payload, report_id)
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
                else:
                    parsed_json = _normalize_evidence_pack_payload(parsed_payload, pack_name)
                validate_schema(
                    SchemaValidateRequest(schema_version="1.0", payload=parsed_json, schema_name=schema_name),
                    ctx,
                )
            except AppError as exc:
                not_found_reason = f"schema_validation_failed:{exc.code}"
                parsed_json = None
    except AppError as exc:
        not_found_reason = exc.code
        if schema_name == "doc_map" and exc.retryable:
            not_found_reason = f"retryable_error:{exc.code}"
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
    )
    logger.info(log_event(
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
    ))
    return result_payload


def _empty_payload(schema_name: str, reason: str) -> dict:
    if schema_name == "doc_map":
        return {"doc_id": "", "title": "", "sections": [], "not_found_reason": reason}
    return {"scope": "", "methods": [], "findings": [], "limitations": [], "quote_candidates": [], "not_found_reason": reason}


def _text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _first_non_empty_text(*values: object) -> str:
    for value in values:
        candidate = _text(value)
        if candidate:
            return candidate
    return ""


def _coerce_pages(value: object) -> list[int]:
    items = value if isinstance(value, list) else [value]
    pages: list[int] = []
    seen: set[int] = set()
    for item in items:
        if isinstance(item, bool):
            continue
        if isinstance(item, (int, float)):
            page_num = int(item)
            if page_num > 0 and page_num not in seen:
                seen.add(page_num)
                pages.append(page_num)
            continue
        tokenized = _text(item).replace(";", ",").replace("|", ",")
        for token in tokenized.split(","):
            token_text = token.strip()
            if not token_text or not token_text.isdigit():
                continue
            page_num = int(token_text)
            if page_num > 0 and page_num not in seen:
                seen.add(page_num)
                pages.append(page_num)
    return pages


def _coerce_pack_items(value: object) -> list[object]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def _to_dict(value: object) -> dict:
    if isinstance(value, dict):
        return value
    return {}


def _extract_evidence_text(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        for item in value:
            if isinstance(item, str) and item.strip():
                return item.strip()
            if isinstance(item, dict):
                candidate = _first_non_empty_text(
                    item.get("snippet"),
                    item.get("text"),
                    item.get("quote"),
                    item.get("evidence"),
                    item.get("description"),
                )
                if candidate:
                    return candidate
        return ""
    if isinstance(value, dict):
        return _first_non_empty_text(
            value.get("snippet"),
            value.get("text"),
            value.get("quote"),
            value.get("evidence"),
            value.get("description"),
        )
    return ""


def _coerce_confidence(value: object) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return _text(value)


def _normalize_findings(raw_findings: object) -> list[dict]:
    normalized: list[dict] = []
    for idx, entry in enumerate(_coerce_pack_items(raw_findings)):
        if isinstance(entry, str):
            text_value = entry.strip()
            if not text_value:
                continue
            normalized.append({
                "id": f"finding_{idx + 1}",
                "text": text_value,
                "evidence": "",
                "confidence": "",
                "pages": [],
            })
            continue
        if not isinstance(entry, dict):
            continue
        item = _to_dict(entry)
        text_value = _first_non_empty_text(
            item.get("text"),
            item.get("summary"),
            item.get("finding"),
            item.get("claim"),
            item.get("title"),
        )
        evidence_value = _first_non_empty_text(
            _extract_evidence_text(item.get("evidence")),
            _extract_evidence_text(item.get("supporting_evidence")),
            item.get("rationale"),
        )
        pages = _coerce_pages(item.get("pages"))
        if not pages:
            pages = _coerce_pages(item.get("page"))
        if not (text_value or evidence_value or pages):
            continue
        normalized.append({
            "id": _first_non_empty_text(item.get("id"), f"finding_{idx + 1}"),
            "text": text_value,
            "evidence": evidence_value,
            "confidence": _coerce_confidence(item.get("confidence")),
            "pages": pages,
        })
    return normalized


def _normalize_limitations(raw_limitations: object) -> list[str]:
    limitations: list[str] = []
    for entry in _coerce_pack_items(raw_limitations):
        if isinstance(entry, str):
            text_value = entry.strip()
            if text_value:
                limitations.append(text_value)
            continue
        if not isinstance(entry, dict):
            continue
        item = _to_dict(entry)
        description = _first_non_empty_text(
            item.get("description"),
            item.get("text"),
            item.get("summary"),
            item.get("limitation"),
            item.get("title"),
            item.get("type"),
        )
        mitigation = _text(item.get("mitigation"))
        if description and mitigation:
            limitations.append(f"{description} Mitigation: {mitigation}")
            continue
        if description:
            limitations.append(description)
            continue
        if mitigation:
            limitations.append(f"Mitigation: {mitigation}")
    return limitations


def _normalize_quote_candidates(raw_quotes: object) -> list[dict]:
    quotes: list[dict] = []
    for entry in _coerce_pack_items(raw_quotes):
        if isinstance(entry, str):
            text_value = entry.strip()
            if text_value:
                quotes.append({"text": text_value, "source": "", "page": None})
            continue
        if not isinstance(entry, dict):
            continue
        item = _to_dict(entry)
        text_value = _first_non_empty_text(
            item.get("text"),
            item.get("quote"),
            item.get("snippet"),
            item.get("excerpt"),
            item.get("content"),
        )
        if not text_value:
            continue
        source_value = _first_non_empty_text(
            item.get("source"),
            item.get("citation"),
            item.get("speaker"),
            item.get("author"),
            item.get("evidence_id"),
        )
        pages = _coerce_pages(item.get("page"))
        if not pages:
            pages = _coerce_pages(item.get("pages"))
        page_value: Optional[int] = pages[0] if pages else None
        quotes.append({
            "text": text_value,
            "source": source_value,
            "page": page_value,
        })
    return quotes


def _normalize_methods(raw_methods: object) -> list[object]:
    methods: list[object] = []
    for entry in _coerce_pack_items(raw_methods):
        if isinstance(entry, dict):
            methods.append(entry)
            continue
        text_value = _text(entry)
        if text_value:
            methods.append(text_value)
    return methods


def _normalize_evidence_pack_payload(payload: object, pack_name: str) -> dict:
    cache_meta = None
    source = payload
    if isinstance(payload, dict):
        cache_meta = payload.get("_cache") if isinstance(payload.get("_cache"), dict) else None
        wrapped = payload.get(pack_name)
        if wrapped is None:
            wrapped = payload.get("evidence_pack")
        if wrapped is None:
            wrapped = payload.get("evidencePack")
        if wrapped is not None:
            source = wrapped

    root = _to_dict(source)
    normalized = _empty_payload("evidence_pack", "")

    if pack_name == "scope":
        scope_value = root.get("scope") if isinstance(source, dict) else source
        if scope_value is None:
            scope_value = ""
        if isinstance(scope_value, (str, dict)):
            normalized["scope"] = scope_value
        else:
            normalized["scope"] = _text(scope_value)
    elif pack_name == "methods":
        raw_methods = root.get("methods") if isinstance(source, dict) else source
        if raw_methods is None:
            raw_methods = root.get("methodology")
        if raw_methods is None:
            raw_methods = root.get("approach")
        normalized["methods"] = _normalize_methods(raw_methods)
    elif pack_name == "findings":
        raw_findings = root.get("findings") if isinstance(source, dict) else source
        if raw_findings is None:
            raw_findings = root.get("insights")
        if raw_findings is None:
            raw_findings = root.get("claims")
        normalized["findings"] = _normalize_findings(raw_findings)
    elif pack_name == "limitations":
        raw_limitations = root.get("limitations") if isinstance(source, dict) else source
        if raw_limitations is None:
            raw_limitations = root.get("risks")
        if raw_limitations is None:
            raw_limitations = root.get("challenges")
        normalized["limitations"] = _normalize_limitations(raw_limitations)
    elif pack_name == "quote_candidates":
        raw_quotes = root.get("quote_candidates") if isinstance(source, dict) else source
        if raw_quotes is None:
            raw_quotes = root.get("quotes")
        if raw_quotes is None:
            raw_quotes = root.get("quoteCandidates")
        normalized["quote_candidates"] = _normalize_quote_candidates(raw_quotes)

    if cache_meta:
        normalized["_cache"] = cache_meta
    return normalized


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
    has_substantive_content = bool(title or summary_text or sections_count)
    return {
        # `doc_id` is auto-filled during normalization and must not be treated
        # as evidence that the doc_map is substantively populated.
        "has_content": has_substantive_content,
        "sections_count": sections_count,
        "title_present": bool(title),
        "doc_id_present": bool(doc_id),
        "summary_present": bool(summary_text),
        "not_found_reason": not_found_reason,
    }


def _normalize_doc_map_payload(payload: dict, report_id: str) -> Tuple[dict, dict]:
    wrapper_key = ""
    candidate = payload
    for key in ("docmap", "doc_map", "docMap"):
        wrapped = payload.get(key)
        if isinstance(wrapped, dict):
            wrapper_key = key
            candidate = wrapped
            break
    normalized = dict(candidate) if isinstance(candidate, dict) else {}
    changed = bool(wrapper_key)
    cache_meta = payload.get("_cache") if isinstance(payload.get("_cache"), dict) else None
    if cache_meta:
        normalized["_cache"] = cache_meta
    doc_meta = normalized.get("document") if isinstance(normalized.get("document"), dict) else {}

    normalized_title = _text(normalized.get("title"))
    resolved_title = _first_non_empty_text(
        normalized_title,
        normalized.get("report_title"),
        doc_meta.get("title"),
        doc_meta.get("name"),
    )
    if resolved_title and resolved_title != normalized_title:
        normalized["title"] = resolved_title
        changed = True

    normalized_publisher = _text(normalized.get("publisher"))
    resolved_publisher = _first_non_empty_text(
        normalized_publisher,
        normalized.get("organization"),
        normalized.get("organisation"),
        doc_meta.get("publisher"),
        doc_meta.get("organization"),
        doc_meta.get("organisation"),
    )
    if resolved_publisher and resolved_publisher != normalized_publisher:
        normalized["publisher"] = resolved_publisher
        changed = True

    normalized_summary = _text(normalized.get("summary"))
    resolved_summary = _first_non_empty_text(
        normalized_summary,
        normalized.get("description"),
        doc_meta.get("summary"),
        doc_meta.get("description"),
    )
    if resolved_summary and resolved_summary != normalized_summary:
        normalized["summary"] = resolved_summary
        changed = True

    doc_id = _text(normalized.get("doc_id"))
    doc_id_filled = False
    if not doc_id:
        normalized["doc_id"] = report_id
        doc_id_filled = True
        changed = True
    elif normalized.get("doc_id") != doc_id:
        normalized["doc_id"] = doc_id
        changed = True

    sections = normalized.get("sections")
    if not isinstance(sections, list):
        structure = normalized.get("structure")
        if isinstance(structure, list):
            normalized["sections"] = structure
            sections = normalized["sections"]
            changed = True

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
            sec_title = _first_non_empty_text(
                sec.get("title"),
                sec.get("heading"),
                sec.get("name"),
                sec.get("section"),
                sec.get("label"),
            )
            if not sec_title:
                sec_title = f"Section {idx + 1}"
            if _text(sec.get("title")) != sec_title:
                sec["title"] = sec_title
                changed = True

            sec_id = str(sec.get("id") or "").strip()
            if not sec_id:
                slug = slugify(sec_title) if sec_title else ""
                sec_id = slug or f"section_{idx + 1}"
                sec["id"] = sec_id
                added_section_ids += 1
                changed = True

            sec_summary = _text(sec.get("summary"))
            resolved_sec_summary = _first_non_empty_text(sec_summary, sec.get("description"), sec.get("text"), sec.get("finding"))
            if resolved_sec_summary and resolved_sec_summary != sec_summary:
                sec["summary"] = resolved_sec_summary
                changed = True

            existing_pages = _coerce_pages(sec.get("pages"))
            resolved_pages = existing_pages or _coerce_pages(sec.get("page"))
            if resolved_pages and resolved_pages != existing_pages:
                sec["pages"] = resolved_pages
                changed = True

            refs = sec.get("references")
            if not isinstance(refs, list):
                refs = []
            normalized_refs = [_text(ref) for ref in refs if _text(ref)]
            if not normalized_refs:
                source_ref = _text(sec.get("source"))
                if source_ref:
                    normalized_refs = [source_ref]
            if normalized_refs and normalized_refs != refs:
                sec["references"] = normalized_refs
                changed = True

            sections_with_ids += 1 if sec.get("id") else 0
            updated_sections.append(sec)
        normalized["sections"] = updated_sections
        if dropped_sections > 0:
            changed = True

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
            ))
    return report_analysis_store_service.store_pack(
        AnalysisStorePackRequest(
            schema_version="1.0",
            output_dir=output_dir,
            report_id=report_id,
            pack_name=pack_name,
            payload=payload,
            report_slug=report_name,
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
    not_found_reason = _text(payload.get("not_found_reason"))
    if not_found_reason:
        logger.info(log_event(
            ctx,
            role="generator",
            event="evidence_pack_cache_rejected",
            module=logger.name,
            fields={"report_id": report_id, "pack": pack_name, "reason": not_found_reason},
        ))
        return None
    return payload
