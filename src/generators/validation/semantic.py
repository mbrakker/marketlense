from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from typing import Any, Dict, List, Sequence

from src.contracts.config import AppSettings
from src.contracts.prompt_family_materialization import (
    PROMPT_FAMILY_MATERIALIZATION_SCHEMA_VERSION,
    PromptFamilyMaterializationRequest,
    PromptFamilyReuseRequest,
)
from src.contracts.run_context import RunContext
from src.contracts.schema_validation import SchemaValidateRequest
from src.contracts.structured_output import StructuredOutputExecutionRequest
from src.contracts.validation import ValidationIssue
from src.generators.prompt_preparation import prepare_prompt_bundle
from src.generators.structured_output_execution import (
    invoke_structured_output_model,
    recovery_prompt_bundle,
)
from src.services.prompt_family_materialization_service import (
    materialize_prompt_family,
    read_reusable_prompt_family,
)
from src.services.schema_validator_service import (
    provider_output_schema,
    validate_schema,
)
from src.services.structured_output_service import execute_structured_output
from src.utils.cache_utils import sha256_json
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
        publisher_name=runtime.request.publisher_name,
        report_name=runtime.request.report_name,
        source_url=runtime.request.source_url,
        report_id=str(runtime.request.report_id),
        source_id=runtime.source_id,
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
    publisher_name: str = "",
    report_name: str = "",
    source_url: str = "",
    report_id: str = "",
    source_id: str = "",
    prompt_family_reuse_reader=read_reusable_prompt_family,
    prompt_family_materializer=materialize_prompt_family,
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
    resolved_report_id = str(report_id or report_name)
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
            event="prompt_rendered_identity",
            module=LOGGER_NAME,
            fields={
                "prompt_content_hash": prompt_bundle.prompt_content_hash,
                "execution_identity": prompt_bundle.execution_identity.execution_identity,
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
                "temperature": prompt_bundle.effective_temperature,
                "seed": prompt_bundle.effective_seed,
                "execution_policy_hash": prompt_bundle.execution_policy.policy_hash,
            },
        )
    )
    relevant_input_hash = sha256_json(
        {
            "metrics": payload["metrics"],
            "quotes": payload["quotes"],
            "evidence": list(evidence_texts),
        }
    )
    configuration_policy_hash = sha256_json(
        {
            "execution_policy_hash": prompt_bundle.execution_policy.policy_hash,
            "execution_policy": asdict(prompt_bundle.execution_policy.policy),
            "routing_policy": asdict(prompt_bundle.routing_decision),
        }
    )
    try:
        output_schema = provider_output_schema("semantic_validation_output")
        reused_payload = None
        if source_id:
            reuse = prompt_family_reuse_reader(
                PromptFamilyReuseRequest(
                    schema_version=PROMPT_FAMILY_MATERIALIZATION_SCHEMA_VERSION,
                    db_path=settings.reports_db,
                    output_dir=settings.output_dir,
                    report_id=resolved_report_id,
                    report_slug=report_name or resolved_report_id,
                    source_id=source_id,
                    family_id=prompt_namespace,
                    family_schema_version="1.0",
                    processing_version="validation_rule_v2",
                    prompt_content_hash=prompt_bundle.prompt_content_hash,
                    execution_identity=prompt_bundle.execution_identity.execution_identity,
                    model_provider=str(prompt_bundle.execution_policy.policy.provider),
                    model_name=prompt_bundle.resolved_model,
                    model_policy_namespace="report_vs",
                    routing_policy_version=prompt_bundle.execution_policy.policy_hash,
                    validator_version="semantic_validation_output:1.0",
                    relevant_input_hash=relevant_input_hash,
                    configuration_policy_hash=configuration_policy_hash,
                ),
                semantic_ctx,
            )
            if reuse.reusable:
                validate_schema(
                    SchemaValidateRequest(
                        schema_version="1.0",
                        payload=reuse.output_payload,
                        schema_name="semantic_validation_output",
                    ),
                    semantic_ctx,
                )
                reused_payload = dict(reuse.output_payload)
                logger.info(
                    log_event(
                        semantic_ctx,
                        role="generator",
                        event="semantic_prompt_family_reused",
                        module=LOGGER_NAME,
                        fields={"family_id": prompt_namespace, "reason": reuse.reason},
                    )
                )
        recovery_attempted = False

        def call_model(mode: str, original_response: str, schema_errors: str):
            nonlocal recovery_attempted
            if mode != "primary":
                recovery_attempted = True
            bundle = prompt_bundle
            if mode != "primary":
                bundle = recovery_prompt_bundle(
                    mode=mode,
                    artifact_family="validation_semantic",
                    schema_errors=schema_errors,
                    original_response=original_response,
                    output_schema=output_schema,
                    source_evidence=prompt_vars,
                    settings=settings,
                    ctx=semantic_ctx,
                    prompt_client=prompt_client,
                    vector_store_id=None,
                )
            return invoke_structured_output_model(
                openai_client=openai_client,
                prompt_bundle=bundle,
                settings=settings,
                ctx=semantic_ctx,
                vector_store_id=None,
                report_id=resolved_report_id,
                artifact_family="validation_semantic",
                stage=f"validation_semantic_{mode}",
                publisher_name=publisher_name,
                report_name=report_name,
                source_url=source_url,
                output_schema=output_schema,
                output_schema_identity="semantic_validation_output_v1",
                repair_attempt={"primary": 0, "model_repair": 1, "regeneration": 2}[
                    mode
                ],
            )

        if reused_payload is None:
            recovery = execute_structured_output(
                StructuredOutputExecutionRequest(
                    schema_version="1.0",
                    report_id=resolved_report_id,
                    artifact_family="validation_semantic",
                    schema_name="semantic_validation_output",
                    model=prompt_bundle.resolved_model,
                    workflow="report_analysis",
                    prompt_family=prompt_bundle.routing_decision.namespace,
                    terminal_failure_code="validation_semantic_invalid_json",
                ),
                semantic_ctx,
                call_model=call_model,
                normalize_payload=lambda payload: (
                    dict(payload) if isinstance(payload, dict) else payload
                ),
                validate_payload=lambda payload: validate_schema(
                    SchemaValidateRequest(
                        schema_version="1.0",
                        payload=payload,
                        schema_name="semantic_validation_output",
                    ),
                    semantic_ctx,
                ),
                is_substantive=lambda payload: (
                    isinstance(payload, dict)
                    and "metrics" in payload
                    and "quotes" in payload
                ),
                model_pricing=settings.model_pricing,
            )
            parsed = recovery.payload
        else:
            parsed = reused_payload
        if reused_payload is None and source_id and not recovery_attempted:
            prompt_family_materializer(
                PromptFamilyMaterializationRequest(
                    schema_version=PROMPT_FAMILY_MATERIALIZATION_SCHEMA_VERSION,
                    db_path=settings.reports_db,
                    output_dir=settings.output_dir,
                    report_id=resolved_report_id,
                    report_slug=report_name or resolved_report_id,
                    source_id=source_id,
                    family_id=prompt_namespace,
                    family_schema_version="1.0",
                    processing_version="validation_rule_v2",
                    output_payload=parsed,
                    system_prompt_hash=prompt_bundle.prompt_set.system.sha256,
                    user_prompt_hash=prompt_bundle.prompt_set.user.sha256,
                    prompt_content_hash=prompt_bundle.prompt_content_hash,
                    prompt_dependency_manifest=asdict(
                        prompt_bundle.dependency_manifest
                    ),
                    execution_identity=prompt_bundle.execution_identity.execution_identity,
                    execution_identity_manifest=asdict(
                        prompt_bundle.execution_identity
                    ),
                    prompt_policy_version=prompt_bundle.prompt_content_hash,
                    model_name=prompt_bundle.resolved_model,
                    model_provider=str(prompt_bundle.execution_policy.policy.provider),
                    model_policy_namespace="report_vs",
                    routing_policy_version=prompt_bundle.execution_policy.policy_hash,
                    relevant_input_hash=relevant_input_hash,
                    configuration_policy_hash=configuration_policy_hash,
                    validator_version="semantic_validation_output:1.0",
                    validation_status="pass",
                ),
                semantic_ctx,
            )
        logger.info(
            log_event(
                semantic_ctx,
                role="generator",
                event="semantic_response",
                module=LOGGER_NAME,
                fields={
                    "has_json": isinstance(parsed, dict),
                    "attempt_count": recovery.attempts,
                    "final_disposition": recovery.disposition,
                },
            )
        )
        if parsed is None:
            raise AppError(
                code="semantic_response_invalid",
                message="Semantic validation did not return JSON payload",
                retryable=False,
                context={"model": prompt_bundle.resolved_model},
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
        if exc.retryable:
            logger.info(
                log_event(
                    semantic_ctx,
                    role="generator",
                    event="semantic_retryable_error_propagated",
                    module=LOGGER_NAME,
                    fields={"code": exc.code, "message": exc.message},
                )
            )
            raise
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
        raw_metric = insight.get("metric")
        metric: dict[str, Any] = raw_metric if isinstance(raw_metric, dict) else {}
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
