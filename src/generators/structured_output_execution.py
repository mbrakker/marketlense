"""Shared generator-side prompt and provider adapter for structured recovery."""

from __future__ import annotations

import json
import time
from typing import Any

from src.contracts.config import AppSettings
from src.contracts.ingest import IngestSettings
from src.contracts.llm import LLMContextCompactionPolicy
from src.contracts.openai import OpenAIJSONPromptRequest, OpenAIResponseRequest
from src.contracts.run_context import RunContext
from src.generators.prompt_preparation import (
    model_request_identity_fields,
    prepare_prompt_bundle,
)


def recovery_prompt_bundle(
    *,
    mode: str,
    artifact_family: str,
    schema_errors: str,
    original_response: str,
    output_schema: dict[str, Any],
    source_evidence: dict[str, Any],
    settings: AppSettings | IngestSettings,
    ctx: RunContext,
    prompt_client: Any,
    vector_store_id: str | None,
):
    namespace = (
        "report_vs/structured_output/repair"
        if mode == "model_repair"
        else "report_vs/structured_output/regenerate"
    )
    variables = {
        "artifact_family": artifact_family,
        "schema_errors": schema_errors,
        "original_response": original_response,
        "source_evidence_json": json.dumps(source_evidence, ensure_ascii=False),
        "output_schema_json": json.dumps(output_schema, ensure_ascii=True),
    }
    return prepare_prompt_bundle(
        namespace=namespace,
        settings=settings,
        ctx=ctx,
        prompt_client=prompt_client,
        system_variables=variables,
        user_variables=variables,
        retrieval_mode="vector_store" if vector_store_id else "chat_json",
        temperature=settings.temperature,
        seed=settings.openai_seed,
        timeout_seconds=settings.openai_timeout_seconds,
        output_contract_schema_version="structured_output:1.0",
        validator_version="structured_output_recovery:1.0",
    )


def invoke_structured_output_model(
    *,
    openai_client: Any,
    prompt_bundle: Any,
    settings: AppSettings | IngestSettings,
    ctx: RunContext,
    vector_store_id: str | None,
    report_id: str,
    artifact_family: str,
    stage: str,
    publisher_name: str,
    report_name: str,
    source_url: str,
    output_schema: dict[str, Any],
    output_schema_identity: str,
    repair_attempt: int,
    response_observer=None,
) -> Any:
    common = {
        "schema_version": "1.0",
        "system_prompt": prompt_bundle.system_prompt,
        "user_prompt": prompt_bundle.user_prompt,
        "model": prompt_bundle.resolved_model,
        "temperature": prompt_bundle.effective_temperature,
        "api_key": settings.openai_api_key,
        "seed": prompt_bundle.effective_seed,
        "max_output_tokens": prompt_bundle.effective_max_output_tokens,
        "timeout_seconds": prompt_bundle.effective_timeout_seconds,
        "cost_ledger_path": settings.cost_ledger_path,
        "cost_daily_path": settings.cost_daily_path,
        "usage_db_path": str(
            getattr(settings, "usage_db_path", "./state/llm_usage.sqlite")
        ),
        "model_pricing": settings.model_pricing,
        "publisher_name": publisher_name,
        "report_name": report_name,
        "source_url": source_url,
        "report_id": report_id,
        "workflow": "report_analysis",
        "stage": stage,
        "artifact_family": artifact_family,
        "prompt_namespace": prompt_bundle.prompt_set.dependency_manifest.namespace,
        "repair_attempt": repair_attempt,
        "structured_output_schema": output_schema,
        "structured_output_schema_identity": output_schema_identity,
        **model_request_identity_fields(prompt_bundle),
        "same_provider_fallback": (
            prompt_bundle.execution_policy.policy.fallback_policy
            == "same_provider_only"
        ),
        "context_compaction_policy": LLMContextCompactionPolicy(
            schema_version="1.0",
            enabled=prompt_bundle.routing_decision.compaction_enabled,
            max_input_tokens=prompt_bundle.routing_decision.max_input_tokens or None,
        ),
    }
    started = time.perf_counter()
    if vector_store_id:
        response = openai_client.openai_respond_with_vector_store(
            OpenAIResponseRequest(vector_store_id=vector_store_id, **common), ctx
        )
    else:
        response = openai_client.openai_chat_json(
            OpenAIJSONPromptRequest(**common), ctx
        )
    if response_observer is not None:
        response_observer(
            response,
            (time.perf_counter() - started) * 1000,
            "primary" if repair_attempt == 0 else "recovery",
        )
    return response
