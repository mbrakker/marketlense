from __future__ import annotations

import json
import logging
import re
import hashlib
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from src.contracts.config import AppSettings
from src.contracts.openai import OpenAIJSONPromptRequest, OpenAIResponseRequest
from src.contracts.prompts import PromptLoadRequest, PromptRenderRequest
from src.contracts.run_context import RunContext
from src.contracts.validation import ValidationIssue, ValidationReport, ValidationRequest
from src.services import openai_service, prompt_service, report_analysis_store_service
from src.utils.errors import AppError
from src.utils.logging import child_context, log_event, new_run_context
from src.utils.schema_validator import validate_schema
from src.utils.model_resolver import resolve_model

logger = logging.getLogger("market_lense.validation_generator")

_SEVERITY_ORDER = ("error", "warning", "info", "pass")


@dataclass(frozen=True)
class _SemanticSupport:
    supported: bool
    confidence: float
    reason: str


@dataclass(frozen=True)
class _SemanticCheckOutcome:
    metric_support: Dict[str, _SemanticSupport]
    quote_support: Dict[str, _SemanticSupport]
    issues: List[ValidationIssue]


def validate_report(
    request: ValidationRequest,
    settings: AppSettings,
    ctx: Optional[RunContext] = None,
    *,
    prompt_client=prompt_service,
    openai_client=openai_service,
    analysis_store=report_analysis_store_service,
    pack_name: str = "validation",
) -> ValidationReport:
    ctx = ctx or new_run_context(task_id=f"validation:{request.report_id}")
    logger.info(log_event(
        ctx,
        role="generator",
        event="validation_start",
        module=logger.name,
        fields={
            "report_id": request.report_id,
            "has_artifacts": bool(request.artifacts),
            "has_evidence_packs": bool(request.evidence_packs),
            "vector_store_id": request.vector_store_id or "",
        },
    ))
    issues: List[ValidationIssue] = []
    insights = _ensure_list(request.artifacts.get("insights_final") if isinstance(request.artifacts, dict) else [])
    quotes = _extract_quotes(request, insights)
    evidence_texts, evidence_map = _collect_evidence_texts(request.artifacts, request.evidence_packs)
    semantic_outcome = _run_semantic_validation(
        insights,
        quotes,
        evidence_texts,
        settings,
        prompt_client,
        openai_client,
        ctx,
    )

    issues.extend(semantic_outcome.issues)
    issues.extend(_validate_insight_metrics(insights, evidence_map, semantic_outcome.metric_support))
    issues.extend(_validate_quotes(quotes, evidence_texts, semantic_outcome.quote_support))
    issues.extend(_validate_new_numbers(request.artifacts, insights))
    issues.extend(_run_grounding_check(request, settings, evidence_texts, prompt_client, openai_client, ctx))

    data_gap = _has_data_gap(request.artifacts)
    if data_gap and getattr(settings, "validation_data_gap_policy", "warn") == "warn":
        issues = [
            ValidationIssue(
                schema_version=issue.schema_version,
                message=issue.message,
                severity="warning" if issue.severity == "error" else issue.severity,
                affected_section=issue.affected_section,
            )
            for issue in issues
        ]
    severity = _aggregate_severity(issues)
    status = "pass" if severity != "error" else "fail"
    report = ValidationReport(schema_version="1.1", status=status, issues=issues, severity=severity)

    try:
        validate_schema(report.to_dict(), "validation_report", ctx)
    except AppError as exc:
        logger.info(log_event(
            ctx,
            role="generator",
            event="validation_schema_failed",
            module=logger.name,
            fields={"code": exc.code, "message": exc.message},
        ))
        raise

    stored_path = analysis_store.store_pack(settings.output_dir, request.report_id, pack_name, report.to_dict(), ctx)
    report = ValidationReport(
        schema_version=report.schema_version,
        status=report.status,
        issues=report.issues,
        severity=report.severity,
        source_path=stored_path,
    )
    logger.info(log_event(
        ctx,
        role="generator",
        event="validation_complete",
        module=logger.name,
        fields={"report_id": request.report_id, "status": status, "severity": severity, "issue_count": len(issues), "path": stored_path},
    ))
    return report


def _validate_insight_metrics(
    insights: Sequence[dict],
    evidence_map: Dict[str, str],
    semantic_support: Optional[Dict[str, _SemanticSupport]] = None,
) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    for idx, insight in enumerate(insights):
        if not isinstance(insight, dict):
            continue
        metric = insight.get("metric") if isinstance(insight.get("metric"), dict) else {}
        evidence_id = _s(insight.get("evidence_id"))
        evidence_text = _s(insight.get("evidence")) or evidence_map.get(evidence_id, "")
        label = _s(insight.get("id") or f"insight_{idx + 1}")
        if metric and not evidence_text.strip():
            issues.append(_issue(
                message=f"Missing evidence snippet for metric on {label}",
                severity="error",
                section=f"insights:{label}",
            ))
            continue
        value = _s(metric.get("value")).strip()
        unit = _s(metric.get("unit")).strip()
        timeframe = _s(metric.get("timeframe")).strip()
        semantic_entry = (semantic_support or {}).get(label)
        value_supported_exact = _metric_value_supported(value, evidence_text)
        value_supported_semantic = semantic_entry.supported if semantic_entry else False
        if value and not (value_supported_exact or value_supported_semantic):
            reason = f" ({semantic_entry.reason})" if semantic_entry and semantic_entry.reason else ""
            severity = "error" if not semantic_entry or semantic_entry.confidence >= 0.6 else "warning"
            issues.append(_issue(
                message=f"Metric value '{value}' not found in evidence for {label}{reason}",
                severity=severity,
                section=f"insights:{label}",
            ))
        if value and not value_supported_exact and value_supported_semantic:
            issues.append(_issue(
                message=f"Metric value '{value}' not verbatim but semantically supported (confidence={_format_confidence(semantic_entry.confidence)}) for {label}",
                severity="info",
                section=f"insights:{label}",
            ))
        if unit and not _contains_token(unit, evidence_text):
            if semantic_entry and semantic_entry.supported:
                issues.append(_issue(
                    message=f"Metric unit '{unit}' not verbatim but semantically supported (confidence={_format_confidence(semantic_entry.confidence)}) for {label}",
                    severity="info",
                    section=f"insights:{label}",
                ))
            else:
                issues.append(_issue(
                    message=f"Metric unit '{unit}' not present in evidence for {label}",
                    severity="warning",
                    section=f"insights:{label}",
                ))
        if timeframe and not _contains_token(timeframe, evidence_text):
            if semantic_entry and semantic_entry.supported:
                issues.append(_issue(
                    message=f"Metric timeframe '{timeframe}' not verbatim but semantically supported (confidence={_format_confidence(semantic_entry.confidence)}) for {label}",
                    severity="info",
                    section=f"insights:{label}",
                ))
            else:
                issues.append(_issue(
                    message=f"Metric timeframe '{timeframe}' not present in evidence for {label}",
                    severity="warning",
                    section=f"insights:{label}",
                ))
    return issues


def _validate_quotes(
    quotes: Sequence[dict],
    evidence_texts: Sequence[str],
    semantic_support: Optional[Dict[str, _SemanticSupport]] = None,
) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    if not quotes:
        return issues
    for idx, quote in enumerate(quotes):
        if not isinstance(quote, dict):
            continue
        text = _s(quote.get("text"))
        if not text:
            continue
        label = _quote_label(quote, idx)
        semantic_entry = (semantic_support or {}).get(label)
        verbatim_match = any(text in evidence for evidence in evidence_texts)
        if verbatim_match:
            continue
        if semantic_entry and semantic_entry.supported:
            issues.append(_issue(
                message=f"Quote paraphrased but semantically supported (confidence={_format_confidence(semantic_entry.confidence)}): {text[:120]}",
                severity="info",
                section=f"quotes:{label}",
            ))
        else:
            reason = f" ({semantic_entry.reason})" if semantic_entry and semantic_entry.reason else ""
            severity = "error" if not semantic_entry or semantic_entry.confidence >= 0.6 else "warning"
            issues.append(_issue(
                message=f"Quote not verbatim in evidence{reason}: {text[:120]}",
                severity=severity,
                section=f"quotes:{label}",
            ))
    return issues


def _validate_new_numbers(artifacts: dict, insights: Sequence[dict]) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    allowed_numbers = _collect_allowed_numbers(insights)
    expert_comment = _s(artifacts.get("expert_comment") if isinstance(artifacts, dict) else "")
    linkedin_post = _s(artifacts.get("linkedin_post") if isinstance(artifacts, dict) else "")
    for text, section in ((expert_comment, "expert_comment"), (linkedin_post, "linkedin_post")):
        if not text:
            continue
        for number in _extract_numbers(text):
            if not _number_allowed(number, allowed_numbers):
                issues.append(_issue(
                    message=f"Number {number} not present in insights",
                    severity="warning",
                    section=section,
                ))
    return issues


def _run_semantic_validation(
    insights: Sequence[dict],
    quotes: Sequence[dict],
    evidence_texts: Sequence[str],
    settings: AppSettings,
    prompt_client,
    openai_client,
    ctx: RunContext,
) -> _SemanticCheckOutcome:
    if not evidence_texts or (not insights and not quotes):
        return _SemanticCheckOutcome(metric_support={}, quote_support={}, issues=[])
    semantic_ctx = child_context(ctx, task_id=f"{ctx.task_id}:semantic")
    logger.info(log_event(
        semantic_ctx,
        role="generator",
        event="semantic_validation_start",
        module=logger.name,
        fields={
            "insight_count": len(insights),
            "quote_count": len(quotes),
            "evidence_count": len(evidence_texts),
        },
    ))
    prompt_namespace = "report_vs/validate/semantic"
    prompt_set = prompt_client.load_prompt_set(PromptLoadRequest(schema_version="1.0", namespace=prompt_namespace), semantic_ctx)
    logger.info(log_event(
        semantic_ctx,
        role="generator",
        event="prompt_selected",
        module=logger.name,
        fields={
            "namespace": prompt_namespace,
            "system_path": prompt_set.system.path,
            "system_sha256": prompt_set.system.sha256,
            "user_path": prompt_set.user.path,
            "user_sha256": prompt_set.user.sha256,
        },
    ))
    payload = _semantic_payload(insights, quotes)
    prompt_vars = {
        "metrics_json": json.dumps(payload["metrics"], ensure_ascii=False),
        "quotes_json": json.dumps(payload["quotes"], ensure_ascii=False),
        "evidence_json": json.dumps(list(evidence_texts), ensure_ascii=False),
    }
    system_render = prompt_client.render_prompt(PromptRenderRequest(schema_version="1.0", template=prompt_set.system, variables=prompt_vars), semantic_ctx)
    user_render = prompt_client.render_prompt(PromptRenderRequest(schema_version="1.0", template=prompt_set.user, variables=prompt_vars), semantic_ctx)
    logger.info(log_event(
        semantic_ctx,
        role="generator",
        event="prompt_rendered",
        module=logger.name,
        fields={
            "system_prompt": system_render.text,
            "user_prompt": user_render.text,
        },
    ))
    resolved_model = resolve_model(prompt_namespace, getattr(settings, "openai_models", {}), settings.openai_model)
    evidence_hash = hashlib.sha256("||".join(evidence_texts).encode("utf-8")).hexdigest()
    metrics_hash = hashlib.sha256(json.dumps(payload["metrics"], sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    quotes_hash = hashlib.sha256(json.dumps(payload["quotes"], sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    logger.info(log_event(
        semantic_ctx,
        role="generator",
        event="model_resolved",
        module=logger.name,
        fields={
            "namespace": prompt_namespace,
            "resolved_model": resolved_model,
            "default_model": settings.openai_model,
            "evidence_sha256": evidence_hash,
            "metrics_sha256": metrics_hash,
            "quotes_sha256": quotes_hash,
        },
    ))
    logger.info(log_event(
        semantic_ctx,
        role="generator",
        event="semantic_request_config",
        module=logger.name,
        fields={
            "model": resolved_model,
            "temperature": settings.temperature,
            "seed": settings.openai_seed,
        },
    ))
    try:
        resp = openai_client.openai_chat_json(
            OpenAIJSONPromptRequest(
                schema_version="1.0",
                system_prompt=system_render.text,
                user_prompt=user_render.text,
                model=resolved_model,
                temperature=settings.temperature,
                api_key=settings.openai_api_key,
                seed=settings.openai_seed,
                timeout_seconds=settings.openai_timeout_seconds,
                cost_ledger_path=settings.cost_ledger_path,
                cost_daily_path=settings.cost_daily_path,
                model_pricing=settings.model_pricing,
            ),
            semantic_ctx,
        )
        parsed = resp.parsed_json if isinstance(resp.parsed_json, dict) else None
        logger.info(log_event(
            semantic_ctx,
            role="generator",
            event="semantic_response",
            module=logger.name,
            fields={
                "has_json": isinstance(parsed, dict),
                "input_tokens": resp.input_tokens,
                "output_tokens": resp.output_tokens,
            },
        ))
        if parsed is None:
            raise AppError(
                code="semantic_response_invalid",
                message="Semantic validation did not return JSON payload",
                retryable=False,
                context={"model": resolved_model},
            )
        outcome = _parse_semantic_response(parsed)
        logger.info(log_event(
            semantic_ctx,
            role="generator",
            event="semantic_validation_complete",
            module=logger.name,
            fields={
                "metric_entries": len(outcome.metric_support),
                "quote_entries": len(outcome.quote_support),
                "issue_count": len(outcome.issues),
            },
        ))
        return outcome
    except AppError as exc:
        logger.info(log_event(
            semantic_ctx,
            role="generator",
            event="semantic_validation_failed",
            module=logger.name,
            fields={"code": exc.code, "message": exc.message},
        ))
        return _SemanticCheckOutcome(
            metric_support={},
            quote_support={},
            issues=[_issue(
                message=f"Semantic validation failed: {exc.message}",
                severity="warning",
                section="semantic",
            )],
        )


def _run_grounding_check(
    request: ValidationRequest,
    settings: AppSettings,
    evidence_texts: Sequence[str],
    prompt_client,
    openai_client,
    ctx: RunContext,
) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    prompt_ctx = child_context(ctx, task_id=f"{ctx.task_id}:grounding")
    prompt_namespace = "report_vs/validate/grounding"
    prompt_set = prompt_client.load_prompt_set(PromptLoadRequest(schema_version="1.0", namespace=prompt_namespace), prompt_ctx)
    logger.info(log_event(
        prompt_ctx,
        role="generator",
        event="prompt_selected",
        module=logger.name,
        fields={
            "namespace": prompt_namespace,
            "system_path": prompt_set.system.path,
            "system_sha256": prompt_set.system.sha256,
            "user_path": prompt_set.user.path,
            "user_sha256": prompt_set.user.sha256,
        },
    ))
    artifacts = request.artifacts if isinstance(request.artifacts, dict) else {}
    prompt_vars = {
        "report_json": json.dumps(_grounding_payload(request, artifacts), ensure_ascii=False),
        "evidence_json": json.dumps(list(evidence_texts), ensure_ascii=False),
    }
    system_render = prompt_client.render_prompt(PromptRenderRequest(schema_version="1.0", template=prompt_set.system, variables=prompt_vars), prompt_ctx)
    user_render = prompt_client.render_prompt(PromptRenderRequest(schema_version="1.0", template=prompt_set.user, variables=prompt_vars), prompt_ctx)
    logger.info(log_event(
        prompt_ctx,
        role="generator",
        event="prompt_rendered",
        module=logger.name,
        fields={
            "system_prompt": system_render.text,
            "user_prompt": user_render.text,
        },
    ))

    resolved_model = resolve_model(prompt_namespace, getattr(settings, "openai_models", {}), settings.openai_model)
    logger.info(log_event(
        prompt_ctx,
        role="generator",
        event="model_resolved",
        module=logger.name,
        fields={
            "namespace": prompt_namespace,
            "resolved_model": resolved_model,
            "default_model": settings.openai_model,
        },
    ))
    use_vector_store = bool(request.vector_store_id)
    logger.info(log_event(
        prompt_ctx,
        role="generator",
        event="grounding_request_config",
        module=logger.name,
        fields={
            "model": resolved_model,
            "temperature": settings.temperature,
            "vector_store": use_vector_store,
            "seed": settings.openai_seed,
        },
    ))
    try:
        if use_vector_store:
            resp = openai_client.openai_respond_with_vector_store(
            OpenAIResponseRequest(
                schema_version="1.0",
                system_prompt=system_render.text,
                user_prompt=user_render.text,
                vector_store_id=request.vector_store_id or "",
                model=resolved_model,
                temperature=settings.temperature,
                api_key=settings.openai_api_key,
                seed=settings.openai_seed,
                timeout_seconds=settings.openai_timeout_seconds,
                cost_ledger_path=settings.cost_ledger_path,
                    cost_daily_path=settings.cost_daily_path,
                    model_pricing=settings.model_pricing,
                ),
                prompt_ctx,
            )
        else:
            resp = openai_client.openai_chat_json(
            OpenAIJSONPromptRequest(
                schema_version="1.0",
                system_prompt=system_render.text,
                user_prompt=user_render.text,
                model=resolved_model,
                temperature=settings.temperature,
                api_key=settings.openai_api_key,
                seed=settings.openai_seed,
                timeout_seconds=settings.openai_timeout_seconds,
                    cost_ledger_path=settings.cost_ledger_path,
                    cost_daily_path=settings.cost_daily_path,
                    model_pricing=settings.model_pricing,
                ),
                prompt_ctx,
            )
        unsupported = []
        if isinstance(resp.parsed_json, dict):
            unsupported = resp.parsed_json.get("unsupported") or []
        logger.info(log_event(
            prompt_ctx,
            role="generator",
            event="grounding_response",
            module=logger.name,
            fields={
                "has_json": isinstance(resp.parsed_json, dict),
                "unsupported_count": len(unsupported) if isinstance(unsupported, list) else 0,
            },
        ))
        if isinstance(unsupported, list):
            for entry in unsupported:
                if not isinstance(entry, dict):
                    continue
                text = _s(entry.get("text"))
                section = _s(entry.get("section") or "grounding")
                reason = _s(entry.get("reason") or "Unsupported sentence")
                if text:
                    issues.append(_issue(
                        message=f"{reason}: {text[:200]}",
                        severity="error",
                        section=section,
                    ))
    except AppError as exc:
        logger.info(log_event(
            prompt_ctx,
            role="generator",
            event="grounding_failed",
            module=logger.name,
            fields={"code": exc.code, "message": exc.message},
        ))
        issues.append(_issue(
            message=f"Grounding check failed: {exc.message}",
            severity="warning",
            section="grounding",
        ))
    return issues


def _grounding_payload(request: ValidationRequest, artifacts: dict) -> dict:
    summary = artifacts.get("summary") if isinstance(artifacts, dict) else {}
    return {
        "tldr": request.report.tldr,
        "title": request.report.title,
        "insights_final": artifacts.get("insights_final") if isinstance(artifacts, dict) else [],
        "quotes_final": artifacts.get("quotes_final") if isinstance(artifacts, dict) else [],
        "summary": summary or {},
        "expert_comment": artifacts.get("expert_comment") if isinstance(artifacts, dict) else "",
        "linkedin_post": artifacts.get("linkedin_post") if isinstance(artifacts, dict) else "",
    }


def _semantic_payload(insights: Sequence[dict], quotes: Sequence[dict]) -> dict:
    metrics: List[dict] = []
    for idx, insight in enumerate(insights):
        if not isinstance(insight, dict):
            continue
        metric = insight.get("metric") if isinstance(insight.get("metric"), dict) else {}
        metrics.append({
            "id": _s(insight.get("id") or f"insight_{idx + 1}"),
            "value": _s(metric.get("value")),
            "unit": _s(metric.get("unit")),
            "timeframe": _s(metric.get("timeframe")),
            "insight_text": _s(insight.get("text")),
            "evidence_id": _s(insight.get("evidence_id")),
        })
    quote_entries: List[dict] = []
    for idx, quote in enumerate(quotes):
        if not isinstance(quote, dict):
            continue
        quote_entries.append({
            "id": _quote_label(quote, idx),
            "text": _s(quote.get("text")),
            "speaker": _s(quote.get("speaker")),
            "evidence_id": _s(quote.get("evidence_id")),
        })
    return {"metrics": metrics, "quotes": quote_entries}


def _parse_semantic_response(payload: dict) -> _SemanticCheckOutcome:
    metric_support: Dict[str, _SemanticSupport] = {}
    quote_support: Dict[str, _SemanticSupport] = {}
    issues: List[ValidationIssue] = []
    metrics = payload.get("metrics") if isinstance(payload, dict) else []
    if isinstance(metrics, list):
        for entry in metrics:
            if not isinstance(entry, dict):
                continue
            label = _s(entry.get("id") or entry.get("label") or entry.get("insight_id"))
            if not label:
                continue
            state = entry.get("supported")
            if isinstance(state, str):
                normalized = state.strip().lower()
                supported = normalized in {"true", "yes", "supported", "pass"}
            else:
                supported = bool(state) if state is not None else False
            confidence = _to_float(entry.get("confidence"))
            confidence = confidence if confidence is not None else 0.0
            reason = _s(entry.get("reason"))
            metric_support[label] = _SemanticSupport(supported=supported, confidence=confidence, reason=reason)
            if not supported:
                severity = "error" if confidence >= 0.6 else "warning"
                reason_suffix = f" ({reason})" if reason else ""
                issues.append(_issue(
                    message=f"Semantic check: metric for {label} not supported{reason_suffix}",
                    severity=severity,
                    section=f"insights:{label}",
                ))
    quotes = payload.get("quotes") if isinstance(payload, dict) else []
    if isinstance(quotes, list):
        for entry in quotes:
            if not isinstance(entry, dict):
                continue
            label = _s(entry.get("id") or entry.get("label") or entry.get("quote_id"))
            if not label:
                continue
            state = entry.get("supported")
            if isinstance(state, str):
                normalized = state.strip().lower()
                supported = normalized in {"true", "yes", "supported", "pass"}
            else:
                supported = bool(state) if state is not None else False
            confidence = _to_float(entry.get("confidence"))
            confidence = confidence if confidence is not None else 0.0
            reason = _s(entry.get("reason"))
            quote_support[label] = _SemanticSupport(supported=supported, confidence=confidence, reason=reason)
            if not supported:
                severity = "error" if confidence >= 0.6 else "warning"
                reason_suffix = f" ({reason})" if reason else ""
                issues.append(_issue(
                    message=f"Semantic check: quote {label} not supported{reason_suffix}",
                    severity=severity,
                    section=f"quotes:{label}",
                ))
    return _SemanticCheckOutcome(metric_support=metric_support, quote_support=quote_support, issues=issues)


def _aggregate_severity(issues: Sequence[ValidationIssue]) -> str:
    if any(issue.severity == "error" for issue in issues):
        return "error"
    if any(issue.severity == "warning" for issue in issues):
        return "warning"
    return "pass"


def _collect_allowed_numbers(insights: Sequence[dict]) -> List[float]:
    numbers: List[float] = []
    for insight in insights:
        if not isinstance(insight, dict):
            continue
        metric = insight.get("metric") if isinstance(insight.get("metric"), dict) else {}
        val = _to_float(metric.get("value"))
        if val is not None:
            numbers.append(val)
        numbers.extend(_extract_numbers(_s(insight.get("text"))))
    return numbers


def _number_allowed(value: float, allowed: Iterable[float]) -> bool:
    for allowed_value in allowed:
        if abs(allowed_value - value) <= max(0.01 * abs(allowed_value or 1.0), 0.1):
            return True
    return False


def _collect_evidence_texts(artifacts: dict, evidence_packs: dict) -> Tuple[List[str], Dict[str, str]]:
    texts: List[str] = []
    evidence_by_id: Dict[str, str] = {}

    def _add(text: str) -> None:
        if not text or not text.strip():
            return
        if text not in texts:
            texts.append(text)

    if isinstance(artifacts, dict):
        summary = artifacts.get("summary") if isinstance(artifacts.get("summary"), dict) else {}
        for claim in summary.get("claim_evidence_map") or []:
            if isinstance(claim, dict):
                ev = _s(claim.get("evidence"))
                _add(ev)
        for insight in artifacts.get("insights_final") or []:
            if isinstance(insight, dict):
                evidence_text = _s(insight.get("evidence"))
                evidence_id = _s(insight.get("evidence_id"))
                if evidence_text:
                    _add(evidence_text)
                    if evidence_id:
                        evidence_by_id[evidence_id] = evidence_text
        for quote in artifacts.get("quotes_final") or []:
            if isinstance(quote, dict):
                citation = _s(quote.get("citation"))
                _add(citation)

    if isinstance(evidence_packs, dict):
        for pack in evidence_packs.values():
            if isinstance(pack, dict):
                for entry in pack.get("findings") or []:
                    if isinstance(entry, dict):
                        ev = _s(entry.get("evidence"))
                        ev_id = _s(entry.get("id"))
                        if ev:
                            _add(ev)
                            if ev_id:
                                evidence_by_id[ev_id] = ev
                for quote in pack.get("quote_candidates") or []:
                    if isinstance(quote, dict):
                        _add(_s(quote.get("text")))
    return texts, evidence_by_id


def _extract_quotes(request: ValidationRequest, insights: Sequence[dict]) -> List[dict]:
    artifacts = request.artifacts if isinstance(request.artifacts, dict) else {}
    quotes = artifacts.get("quotes_final") or []
    if quotes:
        return quotes
    quote = request.report.quote
    return [{"text": quote.text, "speaker": quote.author, "evidence_id": _s(insights[0].get("evidence_id")) if insights else ""}]


def _quote_label(quote: dict, idx: int) -> str:
    explicit = _s(quote.get("id") or quote.get("evidence_id"))
    if explicit:
        return explicit
    return str(idx + 1)


def _metric_value_supported(value: str, evidence_text: str) -> bool:
    if not value:
        return True
    evidence_normalized = evidence_text.lower()
    value_clean = value.replace(",", "").strip()
    if value_clean and value_clean.lower() in evidence_normalized:
        return True
    numeric = _to_float(value_clean)
    if numeric is None:
        return False
    for number in _extract_numbers(evidence_text):
        if abs(number - numeric) <= max(0.01 * abs(numeric or 1.0), 0.1):
            return True
    return False


def _contains_token(token: str, text: str) -> bool:
    return token.lower() in text.lower()


def _extract_numbers(text: str) -> List[float]:
    values: List[float] = []
    for raw in re.findall(r"-?\d+(?:\.\d+)?", text):
        parsed = _to_float(raw)
        if parsed is not None:
            values.append(parsed)
    return values


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        cleaned = str(value).strip()
        if cleaned.endswith("%"):
            cleaned = cleaned[:-1]
        cleaned = cleaned.replace(",", "")
        return float(cleaned)
    except (TypeError, ValueError):
        return None


def _s(value: Any) -> str:
    if value is None:
        return ""
    return value if isinstance(value, str) else str(value)


def _ensure_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _issue(message: str, severity: str, section: str) -> ValidationIssue:
    return ValidationIssue(
        schema_version="1.0",
        message=message,
        severity=severity if severity in {"error", "warning", "info"} else "warning",
        affected_section=section,
    )


def _format_confidence(value: float) -> str:
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "0.00"


def _has_data_gap(artifacts: dict) -> bool:
    if not isinstance(artifacts, dict):
        return False
    status = artifacts.get("source_status")
    if isinstance(status, dict):
        return bool(status.get("not_available"))
    return False
