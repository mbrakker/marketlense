from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, Dict, Optional

from src.contracts.config import AppSettings
from src.contracts.ingest import IngestSettings
from src.contracts.run_context import RunContext
from src.contracts.structured_output import StructuredOutputExecutionRequest
from src.generators.prompt_preparation import (
    PreparedPromptBundle,
    prepare_prompt_bundle,
)
from src.generators.structured_output_execution import (
    invoke_structured_output_model,
    recovery_prompt_bundle,
)
from src.services.schema_validator_service import (
    provider_output_schema,
    validate_output_schema,
)
from src.services.structured_output_service import execute_structured_output
from src.utils.costing import (
    estimate_cost_usd,
    estimate_text_tokens,
    resolve_model_pricing,
)
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.artifact_generator")

_ARTIFACT_RESPONSE_ROOTS = {
    "report_vs/artifacts/summary": "summary",
    "report_vs/artifacts/insights_candidates": "insights_candidates",
    "report_vs/artifacts/insights_final": "insights_final",
    "report_vs/artifacts/quotes": "quotes_final",
    "report_vs/artifacts/expert_comment": "expert_comment",
    "report_vs/artifacts/linkedin_post": "linkedin_post",
    "report_vs/artifacts/cover_semantics": "cover_semantics",
    "report_vs/artifacts/regenerate/summary": "summary",
    "report_vs/artifacts/regenerate/insights_candidates": "insights_candidates",
    "report_vs/artifacts/regenerate/insights_final": "insights_final",
    "report_vs/artifacts/regenerate/quotes": "quotes_final",
    "report_vs/artifacts/regenerate/expert_comment": "expert_comment",
    "report_vs/artifacts/regenerate/linkedin_post": "linkedin_post",
}
_ARTIFACT_ABSTAINABLE_ROOTS = {
    "insights_candidates",
    "insights_final",
    "quotes_final",
    "expert_comment",
    "linkedin_post",
}


def render_artifact_json_model(
    *,
    namespace: str,
    variables: Dict[str, Any],
    settings: AppSettings | IngestSettings,
    ctx: RunContext,
    openai_client,
    prompt_client,
    allow_vector_store: bool,
    vector_store_id: Optional[str],
    publisher_name: str = "",
    report_name: str = "",
    source_url: str = "",
    payload_validator: Callable[[Dict[str, Any]], Any] | None = None,
    repair_namespace: str = "",
    repair_attempt: int = 0,
    report_id: str = "",
    prepared_prompt_bundle: PreparedPromptBundle | None = None,
    response_observer: Callable[[Any, float, str], None] | None = None,
) -> Dict[str, Any]:
    """Render one artifact through the shared bounded JSON recovery service."""
    prompt_bundle = prepared_prompt_bundle or prepare_prompt_bundle(
        namespace=namespace,
        settings=settings,
        ctx=ctx,
        prompt_client=prompt_client,
        system_variables=variables,
        user_variables=variables,
        retrieval_mode=(
            "vector_store" if allow_vector_store and vector_store_id else "chat_json"
        ),
        temperature=settings.temperature,
        seed=settings.openai_seed,
        timeout_seconds=settings.openai_timeout_seconds,
        output_contract_schema_version="artifact_json:1.0",
        validator_version="artifacts_schema:3.0",
    )
    expected_input_tokens = estimate_text_tokens(
        f"{prompt_bundle.system_prompt}\n{prompt_bundle.user_prompt}"
    )
    pricing_resolution = resolve_model_pricing(
        prompt_bundle.resolved_model, settings.model_pricing
    )
    expected_cost_usd = estimate_cost_usd(
        prompt_bundle.resolved_model,
        expected_input_tokens,
        0,
        0,
        settings.model_pricing,
    )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="artifact_prompt_rendered",
            module=logger.name,
            fields={
                "namespace": namespace,
                "system_path": prompt_bundle.prompt_set.system.path,
                "user_path": prompt_bundle.prompt_set.user.path,
                "prompt_system_sha256": prompt_bundle.prompt_set.system.sha256,
                "prompt_user_sha256": prompt_bundle.prompt_set.user.sha256,
                "prompt_content_hash": prompt_bundle.prompt_content_hash,
                "execution_identity": prompt_bundle.execution_identity.execution_identity,
                "partial_count": len(
                    prompt_bundle.dependency_manifest.included_partials
                ),
                "schema_snippet_count": len(
                    prompt_bundle.dependency_manifest.schema_snippets
                ),
            },
        )
    )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="model_resolved",
            module=logger.name,
            fields={
                "namespace": namespace,
                "resolved_model": prompt_bundle.resolved_model,
                "default_model": settings.openai_model,
            },
        )
    )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="artifact_model_request",
            module=logger.name,
            fields={
                "namespace": namespace,
                "model": prompt_bundle.resolved_model,
                "routing_tier": prompt_bundle.routing_decision.tier,
                "routing_policy_source": prompt_bundle.routing_decision.policy_source,
                "routing_quality_threshold": prompt_bundle.routing_decision.quality_threshold,
                "same_provider_fallback": prompt_bundle.routing_decision.same_provider_fallback,
                "compaction_enabled": prompt_bundle.routing_decision.compaction_enabled,
                "compaction_max_input_tokens": prompt_bundle.routing_decision.max_input_tokens,
                "expected_input_tokens": expected_input_tokens,
                "expected_cost_usd": expected_cost_usd,
                "pricing_status": pricing_resolution.status,
                "temperature": prompt_bundle.effective_temperature,
                "seed": prompt_bundle.effective_seed,
                "execution_policy_hash": prompt_bundle.execution_policy.policy_hash,
                "execution_policy_source": prompt_bundle.execution_policy.policy_source,
                "retrieval_mode": (
                    "vector_store"
                    if allow_vector_store and vector_store_id
                    else "chat_json"
                ),
                "vector_store_id": vector_store_id or "",
                "prompt_content_hash": prompt_bundle.prompt_content_hash,
                "execution_identity": prompt_bundle.execution_identity.execution_identity,
            },
        )
    )
    root_key = _ARTIFACT_RESPONSE_ROOTS.get(namespace)
    if not root_key:
        raise AppError(
            code="artifact_structured_output_namespace_unknown",
            message="Artifact prompt namespace has no structured response contract",
            retryable=False,
            context={"namespace": namespace},
        )
    output_schema = provider_output_schema("artifacts", root_key)
    resolved_report_id = str(report_id or getattr(ctx, "report_id", "") or report_name)

    def call_model(mode: str, original_response: str, schema_errors: str):
        bundle = prompt_bundle
        if mode != "primary":
            bundle = recovery_prompt_bundle(
                mode=mode,
                artifact_family=root_key,
                schema_errors=schema_errors,
                original_response=original_response,
                output_schema=output_schema,
                source_evidence=variables,
                settings=settings,
                ctx=ctx,
                prompt_client=prompt_client,
                vector_store_id=(vector_store_id if allow_vector_store else None),
            )
        response = invoke_structured_output_model(
            openai_client=openai_client,
            prompt_bundle=bundle,
            settings=settings,
            ctx=ctx,
            vector_store_id=(vector_store_id if allow_vector_store else None),
            report_id=resolved_report_id,
            artifact_family=root_key,
            stage=f"artifact_{root_key}_{mode}",
            publisher_name=publisher_name,
            report_name=report_name,
            source_url=source_url,
            output_schema=output_schema,
            output_schema_identity=f"artifact_{root_key}_v1",
            repair_attempt=(
                repair_attempt
                if mode == "primary" and repair_attempt
                else {"primary": 0, "model_repair": 1, "regeneration": 2}[mode]
            ),
            response_observer=response_observer,
        )
        logger.info(
            log_event(
                ctx,
                role="generator",
                event="artifact_model_response",
                module=logger.name,
                fields={
                    "namespace": bundle.dependency_manifest.namespace,
                    "model": getattr(response, "model", bundle.resolved_model),
                    "has_json": bool(response.parsed_json),
                    "request_id": getattr(response, "request_id", "") or "",
                    "response_chars": len(getattr(response, "text", "") or ""),
                },
            )
        )
        return response

    def validate_payload(payload: Dict[str, Any]) -> None:
        validate_output_schema(
            payload=payload,
            schema_name="artifacts",
            root_key=root_key,
            ctx=ctx,
        )
        if payload_validator is not None:
            payload_validator(payload)

    recovery = execute_structured_output(
        StructuredOutputExecutionRequest(
            schema_version="1.0",
            report_id=resolved_report_id,
            artifact_family=root_key,
            schema_name="artifacts",
            schema_root_key=root_key,
            model=prompt_bundle.resolved_model,
            workflow="report_analysis",
            prompt_family=prompt_bundle.routing_decision.namespace,
            allow_abstention=root_key in _ARTIFACT_ABSTAINABLE_ROOTS,
            terminal_failure_code="artifact_structured_output_invalid",
        ),
        ctx,
        call_model=call_model,
        normalize_payload=lambda payload: _normalize_artifact_response(
            payload, root_key
        ),
        validate_payload=validate_payload,
        is_substantive=lambda payload: _artifact_response_substantive(
            payload, root_key
        ),
        model_pricing=settings.model_pricing,
        is_formal_abstention=lambda payload: (
            root_key in _ARTIFACT_ABSTAINABLE_ROOTS
            and not _artifact_response_substantive(payload, root_key)
        ),
    )
    return dict(recovery.payload)


def _artifact_response_substantive(payload: object, root_key: str) -> bool:
    if not isinstance(payload, dict):
        return False
    value = payload.get(root_key)
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return bool(value)
    if isinstance(value, dict):
        return any(
            bool(item.strip()) if isinstance(item, str) else bool(item)
            for item in value.values()
        )
    return False


def _normalize_artifact_response(payload: object, root_key: str) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return payload  # type: ignore[return-value]
    normalized = dict(payload)
    if root_key not in normalized:
        if root_key == "quotes_final" and isinstance(normalized.get("quotes"), list):
            normalized[root_key] = normalized.pop("quotes")
        elif root_key == "summary" and any(
            key in normalized
            for key in ("tldr", "tldr_card", "card_tldr_compact", "executive_summary")
        ):
            normalized = {root_key: normalized}
        elif root_key in {"expert_comment", "linkedin_post"}:
            normalized[root_key] = ""
        else:
            normalized[root_key] = []
    value = normalized.get(root_key)
    if root_key == "summary" and isinstance(value, dict):
        value = dict(value)
        if not value.get("card_tldr_compact") and value.get("tldr_card"):
            value["card_tldr_compact"] = value.get("tldr_card")
        value.setdefault("tldr", "")
        value.setdefault("card_tldr_compact", "")
        value.setdefault("executive_summary", "")
        claims = value.get("claim_evidence_map")
        if isinstance(claims, list):
            value["claim_evidence_map"] = [
                {
                    **item,
                    "claim": str(item.get("claim") or ""),
                    "evidence_id": str(item.get("evidence_id") or ""),
                    "evidence": str(item.get("evidence") or ""),
                }
                for item in claims
                if isinstance(item, dict)
            ]
        else:
            value["claim_evidence_map"] = []
        normalized[root_key] = value
    elif root_key in {"insights_candidates", "insights_final"} and isinstance(
        value, list
    ):
        normalized[root_key] = [
            {
                **item,
                "id": str(item.get("id") or ""),
                "text": str(item.get("text") or ""),
                "evidence_id": str(item.get("evidence_id") or ""),
            }
            for item in value
            if isinstance(item, dict)
        ]
    elif root_key == "quotes_final" and isinstance(value, list):
        normalized[root_key] = [
            {
                **item,
                "text": str(item.get("text") or ""),
                "evidence_id": str(item.get("evidence_id") or ""),
            }
            for item in value
            if isinstance(item, dict)
        ]
    return normalized
