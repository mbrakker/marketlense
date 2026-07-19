from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from src.contracts.config import AppSettings
from src.contracts.ingest import IngestSettings
from src.contracts.llm import LLMContextCompactionPolicy
from src.contracts.openai import OpenAIJSONPromptRequest, OpenAIResponseRequest
from src.contracts.run_context import RunContext
from src.generators.prompt_preparation import (
    model_request_identity_fields,
    prepare_prompt_bundle,
)
from src.utils.costing import (
    estimate_cost_usd,
    estimate_text_tokens,
    resolve_model_pricing,
)
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.artifact_generator")


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
) -> Dict[str, Any]:
    prompt_bundle = prepare_prompt_bundle(
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
                "temperature": settings.temperature,
                "seed": settings.openai_seed,
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
    if allow_vector_store and vector_store_id:
        resp = openai_client.openai_respond_with_vector_store(
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
                usage_db_path=str(getattr(settings, "usage_db_path", "./state/llm_usage.sqlite")),
                model_pricing=settings.model_pricing,
                publisher_name=publisher_name,
                report_name=report_name,
                source_url=source_url,
                prompt_namespace=namespace,
                **model_request_identity_fields(prompt_bundle),
                same_provider_fallback=prompt_bundle.routing_decision.same_provider_fallback,
                context_compaction_policy=LLMContextCompactionPolicy(
                    schema_version="1.0",
                    enabled=prompt_bundle.routing_decision.compaction_enabled,
                    max_input_tokens=prompt_bundle.routing_decision.max_input_tokens
                    or None,
                ),
            ),
            ctx,
        )
    else:
        resp = openai_client.openai_chat_json(
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
                usage_db_path=str(getattr(settings, "usage_db_path", "./state/llm_usage.sqlite")),
                model_pricing=settings.model_pricing,
                publisher_name=publisher_name,
                report_name=report_name,
                source_url=source_url,
                prompt_namespace=namespace,
                **model_request_identity_fields(prompt_bundle),
                same_provider_fallback=prompt_bundle.routing_decision.same_provider_fallback,
                context_compaction_policy=LLMContextCompactionPolicy(
                    schema_version="1.0",
                    enabled=prompt_bundle.routing_decision.compaction_enabled,
                    max_input_tokens=prompt_bundle.routing_decision.max_input_tokens
                    or None,
                ),
            ),
            ctx,
        )
    parsed = resp.parsed_json if isinstance(resp.parsed_json, dict) else {}
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="artifact_model_response",
            module=logger.name,
            fields={
                "namespace": namespace,
                "model": getattr(resp, "model", prompt_bundle.resolved_model),
                "has_json": bool(resp.parsed_json),
                "request_id": getattr(resp, "request_id", "") or "",
                "response_chars": len(getattr(resp, "text", "") or ""),
            },
        )
    )
    return parsed
