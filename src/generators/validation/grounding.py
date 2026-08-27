from __future__ import annotations

import json
import re
from dataclasses import asdict
from typing import Any, List, Sequence

from src.contracts.prompt_family_materialization import (
    PROMPT_FAMILY_MATERIALIZATION_SCHEMA_VERSION,
    PromptFamilyMaterializationRequest,
    PromptFamilyReuseRequest,
)
from src.contracts.schema_validation import SchemaValidateRequest
from src.contracts.structured_output import StructuredOutputExecutionRequest
from src.contracts.validation import ValidationIssue, ValidationRequest
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
from src.utils.quantity import extract_quantities
from src.utils.text_normalization import normalize_text

from .evidence import sanitize_citation_tokens
from .models import EvidenceWindow, ValidationRuntime
from .quantities import collect_quantities_from_texts
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
        source_id=runtime.source_id,
        vector_store_content_hash=runtime.vector_store_content_hash,
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
    source_id: str = "",
    vector_store_content_hash: str = "",
    prompt_family_reuse_reader=read_reusable_prompt_family,
    prompt_family_materializer=materialize_prompt_family,
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
            event="prompt_rendered_identity",
            module=LOGGER_NAME,
            fields={
                "prompt_content_hash": prompt_bundle.prompt_content_hash,
                "execution_identity": prompt_bundle.execution_identity.execution_identity,
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
                "temperature": prompt_bundle.effective_temperature,
                "vector_store_id_present": bool(request.vector_store_id),
                "setting_enabled": bool(
                    getattr(settings, "validation_grounding_use_vector_store", False)
                ),
                "grounding_use_vector_store": grounding_use_vector_store,
                "retrieval_mode": grounding_retrieval_mode(grounding_use_vector_store),
                "seed": prompt_bundle.effective_seed,
                "execution_policy_hash": prompt_bundle.execution_policy.policy_hash,
            },
        )
    )
    vector_provenance_verified = not grounding_use_vector_store or bool(
        str(vector_store_content_hash or "").strip()
    )
    relevant_input_hash = (
        sha256_json(
            {
                "grounding_payload": grounding_payload(request, artifacts),
                "evidence_texts": list(evidence_texts),
                "vector_store_id": request.vector_store_id or "",
                "vector_store_content_hash": vector_store_content_hash,
                "retrieval_mode": grounding_retrieval_mode(grounding_use_vector_store),
            }
        )
        if source_id and vector_provenance_verified
        else ""
    )
    configuration_policy_hash = sha256_json(
        {
            "execution_policy_hash": prompt_bundle.execution_policy.policy_hash,
            "execution_policy": asdict(prompt_bundle.execution_policy.policy),
            "routing_policy": asdict(prompt_bundle.routing_decision),
        }
    )
    try:
        output_schema = provider_output_schema("grounding_validation_output")
        reused_payload = None
        if source_id and vector_provenance_verified:
            reuse = prompt_family_reuse_reader(
                PromptFamilyReuseRequest(
                    schema_version=PROMPT_FAMILY_MATERIALIZATION_SCHEMA_VERSION,
                    db_path=settings.reports_db,
                    output_dir=settings.output_dir,
                    report_id=str(request.report_id),
                    report_slug=request.report_name or str(request.report_id),
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
                    validator_version="grounding_validation_output:1.0",
                    relevant_input_hash=relevant_input_hash,
                    configuration_policy_hash=configuration_policy_hash,
                ),
                prompt_ctx,
            )
            if reuse.reusable:
                validate_schema(
                    SchemaValidateRequest(
                        schema_version="1.0",
                        payload=reuse.output_payload,
                        schema_name="grounding_validation_output",
                    ),
                    prompt_ctx,
                )
                reused_payload = dict(reuse.output_payload)
                logger.info(
                    log_event(
                        prompt_ctx,
                        role="generator",
                        event="grounding_prompt_family_reused",
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
                    artifact_family="validation_grounding",
                    schema_errors=schema_errors,
                    original_response=original_response,
                    output_schema=output_schema,
                    source_evidence={
                        "report_json": prompt_vars["report_json"],
                        "evidence_json": prompt_vars["evidence_json"],
                    },
                    settings=settings,
                    ctx=prompt_ctx,
                    prompt_client=prompt_client,
                    vector_store_id=(
                        request.vector_store_id if grounding_use_vector_store else None
                    ),
                )
            return invoke_structured_output_model(
                openai_client=openai_client,
                prompt_bundle=bundle,
                settings=settings,
                ctx=prompt_ctx,
                vector_store_id=(
                    request.vector_store_id if grounding_use_vector_store else None
                ),
                report_id=str(request.report_id),
                artifact_family="validation_grounding",
                stage=f"validation_grounding_{mode}",
                publisher_name=request.publisher_name,
                report_name=request.report_name,
                source_url=request.source_url,
                output_schema=output_schema,
                output_schema_identity="grounding_validation_output_v1",
                repair_attempt={"primary": 0, "model_repair": 1, "regeneration": 2}[
                    mode
                ],
            )

        if reused_payload is None:
            recovery = execute_structured_output(
                StructuredOutputExecutionRequest(
                    schema_version="1.0",
                    report_id=str(request.report_id),
                    artifact_family="validation_grounding",
                    schema_name="grounding_validation_output",
                    model=prompt_bundle.resolved_model,
                    terminal_failure_code="validation_grounding_invalid_json",
                ),
                prompt_ctx,
                call_model=call_model,
                normalize_payload=lambda payload: (
                    dict(payload) if isinstance(payload, dict) else payload
                ),
                validate_payload=lambda payload: validate_schema(
                    SchemaValidateRequest(
                        schema_version="1.0",
                        payload=payload,
                        schema_name="grounding_validation_output",
                    ),
                    prompt_ctx,
                ),
                is_substantive=lambda payload: (
                    isinstance(payload, dict) and "unsupported" in payload
                ),
                model_pricing=settings.model_pricing,
            )
            response_payload = recovery.payload
        else:
            response_payload = reused_payload
        unsupported: list[Any] = response_payload.get("unsupported") or []
        if (
            reused_payload is None
            and source_id
            and vector_provenance_verified
            and not recovery_attempted
        ):
            prompt_family_materializer(
                PromptFamilyMaterializationRequest(
                    schema_version=PROMPT_FAMILY_MATERIALIZATION_SCHEMA_VERSION,
                    db_path=settings.reports_db,
                    output_dir=settings.output_dir,
                    report_id=str(request.report_id),
                    report_slug=request.report_name or str(request.report_id),
                    source_id=source_id,
                    family_id=prompt_namespace,
                    family_schema_version="1.0",
                    processing_version="validation_rule_v2",
                    output_payload=response_payload,
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
                    validator_version="grounding_validation_output:1.0",
                    validation_status="pass",
                ),
                prompt_ctx,
            )
        logger.info(
            log_event(
                prompt_ctx,
                role="generator",
                event="grounding_response",
                module=LOGGER_NAME,
                fields={
                    "has_json": True,
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
                severity=(
                    "warning" if request.deterministic_grounding_passed else "error"
                ),
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
    summary_clean: dict[str, Any] = {
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
    if (
        policy == "mixed"
        and not METRIC_ATTRIBUTION_RE.search(lowered)
        and re.search(
            r"\b(should|could|may|might|consider|recommend|priority)\b", lowered
        )
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
        "numerically_inconsistent": "numerically_inconsistent",
        "numeric_inconsistency": "numerically_inconsistent",
        "contradicted": "contradicted",
        "contradiction": "contradicted",
        "invalid_comparison": "invalid_comparison",
        "invalid_comparator": "invalid_comparison",
        "missing_material_evidence": "missing_material_evidence",
        "missing_evidence": "missing_material_evidence",
        "hallucinated_evidence_id": "hallucinated_evidence_id",
        "unknown_evidence_id": "hallucinated_evidence_id",
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
    if "invalid comparison" in combined or "incompatible comparison" in combined:
        return "invalid_comparison"
    if "numeric inconsisten" in combined or "numerically inconsisten" in combined:
        return "numerically_inconsistent"
    if "missing material evidence" in combined:
        return "missing_material_evidence"
    if "evidence id" in combined and any(
        keyword in combined for keyword in ("hallucin", "unknown", "invented")
    ):
        return "hallucinated_evidence_id"
    if "contradict" in combined:
        return "contradicted"
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
