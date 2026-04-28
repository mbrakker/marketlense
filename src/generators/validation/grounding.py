from __future__ import annotations

import json
import re
from typing import Any, List, Sequence

from src.contracts.openai import OpenAIJSONPromptRequest, OpenAIResponseRequest
from src.contracts.validation import ValidationIssue, ValidationRequest
from src.generators.prompt_preparation import prepare_prompt_bundle
from src.utils.errors import AppError
from src.utils.logging import child_context, log_event
from src.utils.quantity import extract_quantities
from src.utils.text_normalization import normalize_text

from .evidence import sanitize_citation_tokens
from .models import EvidenceWindow, ValidationRuntime
from .quantities import (
    all_quantities_supported,
    collect_quantities_from_texts,
    quantity_has_metric_cues_from_text,
)
from .shared import (
    GROUNDING_HARD_FAILURES,
    LOGGER_NAME,
    METRIC_ATTRIBUTION_RE,
    RETRIEVAL_FAILURE_HINTS,
    ensure_dict,
    grounding_retrieval_mode,
    issue,
    logger,
    s,
    section_policy,
    section_root,
)

RULE_ID = "grounding"


def run_grounding_rule(runtime: ValidationRuntime) -> List[ValidationIssue]:
    return run_grounding_check(
        request=runtime.request,
        settings=runtime.settings,
        grounding_use_vector_store=runtime.prepared.grounding_use_vector_store,
        evidence_texts=runtime.prepared.evidence_texts,
        evidence_windows=runtime.prepared.evidence_windows,
        prompt_client=runtime.prompt_client,
        openai_client=runtime.openai_client,
        ctx=runtime.ctx,
    )


def run_grounding_check(
    request: ValidationRequest,
    settings,
    grounding_use_vector_store: bool,
    evidence_texts: Sequence[str],
    evidence_windows: Sequence[EvidenceWindow],
    prompt_client,
    openai_client,
    ctx,
) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    prompt_ctx = child_context(ctx, task_id=f"{ctx.task_id}:grounding")
    prompt_namespace = "report_vs/validate/grounding"
    artifacts = request.artifacts if isinstance(request.artifacts, dict) else {}
    prompt_vars = {
        "report_json": json.dumps(
            grounding_payload(request, artifacts), ensure_ascii=False
        ),
        "evidence_json": json.dumps(list(evidence_texts), ensure_ascii=False),
    }
    prompt_bundle = prepare_prompt_bundle(
        namespace=prompt_namespace,
        settings=settings,
        ctx=prompt_ctx,
        prompt_client=prompt_client,
        system_variables=prompt_vars,
        user_variables=prompt_vars,
    )
    logger.info(
        log_event(
            prompt_ctx,
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
            prompt_ctx,
            role="generator",
            event="prompt_rendered",
            module=LOGGER_NAME,
            fields={
                "system_prompt": prompt_bundle.system_prompt,
                "user_prompt": prompt_bundle.user_prompt,
            },
        )
    )
    logger.info(
        log_event(
            prompt_ctx,
            role="generator",
            event="model_resolved",
            module=LOGGER_NAME,
            fields={
                "namespace": prompt_namespace,
                "resolved_model": prompt_bundle.resolved_model,
                "default_model": settings.openai_model,
            },
        )
    )
    logger.info(
        log_event(
            prompt_ctx,
            role="generator",
            event="grounding_request_config",
            module=LOGGER_NAME,
            fields={
                "model": prompt_bundle.resolved_model,
                "temperature": settings.temperature,
                "vector_store_id_present": bool(request.vector_store_id),
                "setting_enabled": bool(
                    getattr(settings, "validation_grounding_use_vector_store", False)
                ),
                "grounding_use_vector_store": grounding_use_vector_store,
                "retrieval_mode": grounding_retrieval_mode(grounding_use_vector_store),
                "seed": settings.openai_seed,
            },
        )
    )
    try:
        if grounding_use_vector_store:
            response = openai_client.openai_respond_with_vector_store(
                OpenAIResponseRequest(
                    schema_version="1.0",
                    system_prompt=prompt_bundle.system_prompt,
                    user_prompt=prompt_bundle.user_prompt,
                    vector_store_id=request.vector_store_id or "",
                    model=prompt_bundle.resolved_model,
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
                prompt_ctx,
            )
        unsupported: list[Any] = []
        if isinstance(response.parsed_json, dict):
            unsupported = response.parsed_json.get("unsupported") or []
        logger.info(
            log_event(
                prompt_ctx,
                role="generator",
                event="grounding_response",
                module=LOGGER_NAME,
                fields={
                    "has_json": isinstance(response.parsed_json, dict),
                    "unsupported_count": len(unsupported)
                    if isinstance(unsupported, list)
                    else 0,
                },
            )
        )
        if isinstance(unsupported, list):
            evidence_quantities = collect_quantities_from_texts(evidence_texts)
            for window in evidence_windows:
                evidence_quantities.extend(window.quantities)
            for entry in unsupported:
                if not isinstance(entry, dict):
                    continue
                text = s(entry.get("text"))
                section = s(entry.get("section") or "grounding")
                reason = s(entry.get("reason") or "Unsupported sentence")
                section_key = section_root(section)
                current_policy = section_policy(section_key)
                classification = normalize_claim_classification(
                    s(entry.get("classification"))
                )
                if not classification:
                    classification = infer_claim_classification(section_key, text)
                violation_type = normalize_violation_type(
                    s(entry.get("violation_type") or entry.get("failure_type"))
                )
                if not violation_type:
                    violation_type = infer_violation_type(
                        section_key=section_key,
                        classification=classification,
                        text=text,
                        reason=reason,
                    )
                if is_retrieval_failure(reason):
                    violation_type = "evidence_retrieval_failure"

                if violation_type == "unsupported_number":
                    candidate_quantities = extract_quantities(text)
                    if candidate_quantities and all_quantities_supported(
                        candidate_quantities, evidence_quantities, numeric_only=True
                    ):
                        issues.append(
                            issue(
                                rule_id=RULE_ID,
                                message=(
                                    f"[{classification}|normalized_quantity_supported] {reason}: "
                                    f"{text[:200]}"
                                ),
                                severity="info",
                                section=section,
                            )
                        )
                        continue
                severity = grounding_issue_severity(
                    section_policy_value=current_policy,
                    classification=classification,
                    violation_type=violation_type,
                    text=text,
                )
                if severity == "pass":
                    continue
                if text:
                    issues.append(
                        issue(
                            rule_id=RULE_ID,
                            message=f"[{classification}|{violation_type}] {reason}: {text[:200]}",
                            severity=severity,
                            section=section,
                        )
                    )
    except AppError as exc:
        if exc.retryable:
            logger.info(
                log_event(
                    prompt_ctx,
                    role="generator",
                    event="grounding_retryable_error_propagated",
                    module=LOGGER_NAME,
                    fields={"code": exc.code, "message": exc.message},
                )
            )
            raise
        logger.info(
            log_event(
                prompt_ctx,
                role="generator",
                event="grounding_failed",
                module=LOGGER_NAME,
                fields={"code": exc.code, "message": exc.message},
            )
        )
        issues.append(
            issue(
                rule_id=RULE_ID,
                message=f"Grounding check failed: {exc.message}",
                severity="warning",
                section="grounding",
            )
        )
    return issues


def grounding_payload(request: ValidationRequest, artifacts: dict) -> dict:
    summary = artifacts.get("summary") if isinstance(artifacts, dict) else {}
    insights_raw = (
        artifacts.get("insights_final") if isinstance(artifacts, dict) else []
    )
    insights: List[dict] = []
    for insight in insights_raw if isinstance(insights_raw, list) else []:
        if not isinstance(insight, dict):
            continue
        metric = ensure_dict(insight.get("metric"))
        insights.append(
            {
                "id": s(insight.get("id")),
                "text": s(insight.get("text")),
                "evidence_id": s(insight.get("evidence_id")),
                "evidence": s(insight.get("evidence")),
                "metric": {
                    "value": s(metric.get("value")),
                    "unit": s(metric.get("unit")),
                    "timeframe": s(metric.get("timeframe")),
                    "trend": s(metric.get("trend")),
                    "sample_size": s(metric.get("sample_size")),
                    "geography": s(metric.get("geography")),
                    "segment": s(metric.get("segment")),
                },
            }
        )
    summary_clean = {
        "tldr": s(summary.get("tldr")) if isinstance(summary, dict) else "",
        "executive_summary": sanitize_citation_tokens(
            s(summary.get("executive_summary"))
        )
        if isinstance(summary, dict)
        else "",
        "claim_evidence_map": summary.get("claim_evidence_map")
        if isinstance(summary, dict)
        else [],
    }
    return {
        "tldr": request.report.tldr,
        "title": request.report.title,
        "insights_final": insights,
        "quotes_final": artifacts.get("quotes_final")
        if isinstance(artifacts, dict)
        else [],
        "summary": summary_clean,
        "expert_comment": sanitize_citation_tokens(
            s(artifacts.get("expert_comment") if isinstance(artifacts, dict) else "")
        ),
        "linkedin_post": sanitize_citation_tokens(
            s(artifacts.get("linkedin_post") if isinstance(artifacts, dict) else "")
        ),
    }


def normalize_claim_classification(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in {"factual", "fact", "factual_claim", "claim"}:
        return "factual_claim"
    if normalized in {"analyst_interpretation", "interpretation", "analysis"}:
        return "analyst_interpretation"
    if normalized in {"prescriptive_recommendation", "recommendation", "prescriptive"}:
        return "prescriptive_recommendation"
    return ""


def infer_claim_classification(section_key: str, text: str) -> str:
    lowered = normalize_text(text)
    policy = section_policy(section_key)
    if policy == "soft":
        if re.search(
            r"\b(should|must|need to|recommend|recommended|prioriti[sz]e|consider|action|next step|implement)\b",
            lowered,
        ):
            return "prescriptive_recommendation"
        return "analyst_interpretation"
    if policy == "mixed" and not METRIC_ATTRIBUTION_RE.search(lowered):
        if re.search(
            r"\b(should|could|may|might|consider|recommend|priority)\b", lowered
        ):
            return "analyst_interpretation"
    return "factual_claim"


def normalize_violation_type(value: str) -> str:
    normalized = value.strip().lower()
    mapping = {
        "hallucinated_entity_or_event": "hallucinated_entity_or_event",
        "hallucination": "hallucinated_entity_or_event",
        "unsupported_number": "unsupported_number",
        "new_number": "unsupported_number",
        "misattributed_quote": "misattributed_quote",
        "quote_misattribution": "misattributed_quote",
        "report_directive_misattribution": "report_directive_misattribution",
        "report_said_x": "report_directive_misattribution",
        "unsupported_factual_claim": "unsupported_factual_claim",
        "factual_claim": "unsupported_factual_claim",
        "evidence_retrieval_failure": "evidence_retrieval_failure",
        "non_fatal_interpretation": "non_fatal_interpretation",
    }
    return mapping.get(normalized, "")


def infer_violation_type(
    *,
    section_key: str,
    classification: str,
    text: str,
    reason: str,
) -> str:
    text_l = normalize_text(text)
    reason_l = normalize_text(reason)
    combined = f"{text_l} {reason_l}"
    if (
        is_report_directive_misattribution(text_l)
        or "report instruct" in combined
        or "report recommends" in combined
    ):
        return "report_directive_misattribution"
    if section_key.startswith("quotes") or "quote" in combined:
        return "misattributed_quote"
    if extract_quantities(text) and any(
        keyword in combined
        for keyword in ("number", "metric", "value", "figure", "percent", "unsupported")
    ):
        return "unsupported_number"
    if any(
        keyword in combined
        for keyword in (
            "hallucin",
            "invented",
            "made up",
            "contradict",
            "not in evidence",
            "unsupported fact",
            "entity",
            "event",
        )
    ):
        return "hallucinated_entity_or_event"
    if classification == "factual_claim":
        return "unsupported_factual_claim"
    return "non_fatal_interpretation"


def is_report_directive_misattribution(text: str) -> bool:
    return bool(
        re.search(
            r"\breport\s+(says|said|states|stated|instructs|instructed|requires|required|recommends|recommended)\b",
            normalize_text(text),
        )
    )


def is_retrieval_failure(reason: str) -> bool:
    reason_norm = normalize_text(reason)
    if not reason_norm:
        return False
    return any(hint in reason_norm for hint in RETRIEVAL_FAILURE_HINTS)


def grounding_issue_severity(
    *,
    section_policy_value: str,
    classification: str,
    violation_type: str,
    text: str,
) -> str:
    if violation_type in GROUNDING_HARD_FAILURES:
        return "error"
    if violation_type == "evidence_retrieval_failure":
        return "warning"
    if violation_type == "unsupported_number":
        if section_policy_value == "strict":
            return "error"
        if section_policy_value == "mixed":
            if METRIC_ATTRIBUTION_RE.search(text) or quantity_has_metric_cues_from_text(
                text
            ):
                return "error"
            return "warning"
        if quantity_has_metric_cues_from_text(text):
            return "error"
        return "warning"
    if section_policy_value == "soft" and classification in {
        "analyst_interpretation",
        "prescriptive_recommendation",
    }:
        return "info"
    if section_policy_value == "mixed" and classification in {
        "analyst_interpretation",
        "prescriptive_recommendation",
    }:
        return "info"
    if violation_type == "non_fatal_interpretation":
        return "info"
    return "warning"
