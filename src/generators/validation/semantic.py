from __future__ import annotations

import hashlib
import json
from typing import Dict, List, Sequence

from src.contracts.config import AppSettings
from src.contracts.openai import OpenAIJSONPromptRequest
from src.contracts.run_context import RunContext
from src.contracts.validation import ValidationIssue
from src.generators.prompt_preparation import prepare_prompt_bundle
from src.utils.errors import AppError
from src.utils.logging import child_context, log_event

from .evidence import quote_label
from .models import SemanticCheckOutcome, SemanticSupport, ValidationRuntime
from .shared import LOGGER_NAME, issue, logger, s, to_float

RULE_ID = "semantic"


def run_semantic_rule(runtime: ValidationRuntime) -> List[ValidationIssue]:
    outcome = run_semantic_validation(
        insights=runtime.prepared.insights,
        quotes=runtime.prepared.quotes,
        evidence_texts=runtime.prepared.evidence_texts,
        settings=runtime.settings,
        prompt_client=runtime.prompt_client,
        openai_client=runtime.openai_client,
        ctx=runtime.ctx,
    )
    runtime.semantic_outcome = outcome
    return outcome.issues


def run_semantic_validation(
    insights: Sequence[dict],
    quotes: Sequence[dict],
    evidence_texts: Sequence[str],
    settings: AppSettings,
    prompt_client,
    openai_client,
    ctx: RunContext,
) -> SemanticCheckOutcome:
    if not evidence_texts or (not insights and not quotes):
        return SemanticCheckOutcome(metric_support={}, quote_support={}, issues=[])
    semantic_ctx = child_context(ctx, task_id=f"{ctx.task_id}:semantic")
    logger.info(
        log_event(
            semantic_ctx,
            role="generator",
            event="semantic_validation_start",
            module=LOGGER_NAME,
            fields={
                "insight_count": len(insights),
                "quote_count": len(quotes),
                "evidence_count": len(evidence_texts),
            },
        )
    )
    prompt_namespace = "report_vs/validate/semantic"
    payload = semantic_payload(insights, quotes)
    prompt_vars = {
        "metrics_json": json.dumps(payload["metrics"], ensure_ascii=False),
        "quotes_json": json.dumps(payload["quotes"], ensure_ascii=False),
        "evidence_json": json.dumps(list(evidence_texts), ensure_ascii=False),
    }
    prompt_bundle = prepare_prompt_bundle(
        namespace=prompt_namespace,
        settings=settings,
        ctx=semantic_ctx,
        prompt_client=prompt_client,
        system_variables=prompt_vars,
        user_variables=prompt_vars,
    )
    logger.info(
        log_event(
            semantic_ctx,
            role="generator",
            event="prompt_selected",
            module=LOGGER_NAME,
            fields={
                "namespace": prompt_namespace,
                "system_path": prompt_bundle.prompt_set.system.path,
                "system_sha256": prompt_bundle.prompt_set.system.sha256,
                "user_path": prompt_bundle.prompt_set.user.path,
                "user_sha256": prompt_bundle.prompt_set.user.sha256,
            },
        )
    )
    logger.info(
        log_event(
            semantic_ctx,
            role="generator",
            event="prompt_rendered",
            module=LOGGER_NAME,
            fields={
                "system_prompt": prompt_bundle.system_prompt,
                "user_prompt": prompt_bundle.user_prompt,
            },
        )
    )
    evidence_hash = hashlib.sha256(
        "||".join(evidence_texts).encode("utf-8")
    ).hexdigest()
    metrics_hash = hashlib.sha256(
        json.dumps(payload["metrics"], sort_keys=True, ensure_ascii=False).encode(
            "utf-8"
        )
    ).hexdigest()
    quotes_hash = hashlib.sha256(
        json.dumps(payload["quotes"], sort_keys=True, ensure_ascii=False).encode(
            "utf-8"
        )
    ).hexdigest()
    logger.info(
        log_event(
            semantic_ctx,
            role="generator",
            event="model_resolved",
            module=LOGGER_NAME,
            fields={
                "namespace": prompt_namespace,
                "resolved_model": prompt_bundle.resolved_model,
                "default_model": settings.openai_model,
                "evidence_sha256": evidence_hash,
                "metrics_sha256": metrics_hash,
                "quotes_sha256": quotes_hash,
            },
        )
    )
    logger.info(
        log_event(
            semantic_ctx,
            role="generator",
            event="semantic_request_config",
            module=LOGGER_NAME,
            fields={
                "model": prompt_bundle.resolved_model,
                "temperature": settings.temperature,
                "seed": settings.openai_seed,
            },
        )
    )
    try:
        response = openai_client.openai_chat_json(
            OpenAIJSONPromptRequest(
                schema_version="1.0",
                system_prompt=prompt_bundle.system_prompt,
                user_prompt=prompt_bundle.user_prompt,
                model=prompt_bundle.resolved_model,
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
        parsed = response.parsed_json if isinstance(response.parsed_json, dict) else None
        logger.info(
            log_event(
                semantic_ctx,
                role="generator",
                event="semantic_response",
                module=LOGGER_NAME,
                fields={
                    "has_json": isinstance(parsed, dict),
                    "input_tokens": response.input_tokens,
                    "output_tokens": response.output_tokens,
                },
            )
        )
        if parsed is None:
            raise AppError(
                code="semantic_response_invalid",
                message="Semantic validation did not return JSON payload",
                retryable=False,
                context={"model": resolved_model},
            )
        outcome = parse_semantic_response(parsed)
        logger.info(
            log_event(
                semantic_ctx,
                role="generator",
                event="semantic_validation_complete",
                module=LOGGER_NAME,
                fields={
                    "metric_entries": len(outcome.metric_support),
                    "quote_entries": len(outcome.quote_support),
                    "issue_count": len(outcome.issues),
                },
            )
        )
        return outcome
    except AppError as exc:
        logger.info(
            log_event(
                semantic_ctx,
                role="generator",
                event="semantic_validation_failed",
                module=LOGGER_NAME,
                fields={"code": exc.code, "message": exc.message},
            )
        )
        return SemanticCheckOutcome(
            metric_support={},
            quote_support={},
            issues=[
                issue(
                    rule_id=RULE_ID,
                    message=f"Semantic validation failed: {exc.message}",
                    severity="warning",
                    section="semantic",
                )
            ],
        )


def semantic_payload(insights: Sequence[dict], quotes: Sequence[dict]) -> dict:
    metrics: List[dict] = []
    for idx, insight in enumerate(insights):
        if not isinstance(insight, dict):
            continue
        metric = insight.get("metric") if isinstance(insight.get("metric"), dict) else {}
        metrics.append(
            {
                "id": s(insight.get("id") or f"insight_{idx + 1}"),
                "value": s(metric.get("value")),
                "unit": s(metric.get("unit")),
                "timeframe": s(metric.get("timeframe")),
                "insight_text": s(insight.get("text")),
                "evidence_id": s(insight.get("evidence_id")),
            }
        )
    quote_entries: List[dict] = []
    for idx, quote in enumerate(quotes):
        if not isinstance(quote, dict):
            continue
        quote_entries.append(
            {
                "id": quote_label(quote, idx),
                "text": s(quote.get("text")),
                "speaker": s(quote.get("speaker")),
                "evidence_id": s(quote.get("evidence_id")),
            }
        )
    return {"metrics": metrics, "quotes": quote_entries}


def parse_semantic_response(payload: dict) -> SemanticCheckOutcome:
    metric_support: Dict[str, SemanticSupport] = {}
    quote_support: Dict[str, SemanticSupport] = {}
    issues: List[ValidationIssue] = []
    metrics = payload.get("metrics") if isinstance(payload, dict) else []
    if isinstance(metrics, list):
        for entry in metrics:
            if not isinstance(entry, dict):
                continue
            label = s(entry.get("id") or entry.get("label") or entry.get("insight_id"))
            if not label:
                continue
            state = entry.get("supported")
            if isinstance(state, str):
                normalized = state.strip().lower()
                supported = normalized in {"true", "yes", "supported", "pass"}
            else:
                supported = bool(state) if state is not None else False
            confidence = to_float(entry.get("confidence")) or 0.0
            reason = s(entry.get("reason"))
            metric_support[label] = SemanticSupport(
                supported=supported, confidence=confidence, reason=reason
            )
            if not supported:
                severity = "error" if confidence >= 0.6 else "warning"
                reason_suffix = f" ({reason})" if reason else ""
                issues.append(
                    issue(
                        rule_id=RULE_ID,
                        message=f"Semantic check: metric for {label} not supported{reason_suffix}",
                        severity=severity,
                        section=f"insights:{label}",
                    )
                )
    quotes = payload.get("quotes") if isinstance(payload, dict) else []
    if isinstance(quotes, list):
        for entry in quotes:
            if not isinstance(entry, dict):
                continue
            label = s(entry.get("id") or entry.get("label") or entry.get("quote_id"))
            if not label:
                continue
            state = entry.get("supported")
            if isinstance(state, str):
                normalized = state.strip().lower()
                supported = normalized in {"true", "yes", "supported", "pass"}
            else:
                supported = bool(state) if state is not None else False
            confidence = to_float(entry.get("confidence")) or 0.0
            reason = s(entry.get("reason"))
            quote_support[label] = SemanticSupport(
                supported=supported, confidence=confidence, reason=reason
            )
            if not supported:
                severity = "error" if confidence >= 0.6 else "warning"
                reason_suffix = f" ({reason})" if reason else ""
                issues.append(
                    issue(
                        rule_id=RULE_ID,
                        message=f"Semantic check: quote {label} not supported{reason_suffix}",
                        severity=severity,
                        section=f"quotes:{label}",
                    )
                )
    return SemanticCheckOutcome(
        metric_support=metric_support,
        quote_support=quote_support,
        issues=issues,
    )
