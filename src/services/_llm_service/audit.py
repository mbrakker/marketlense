from __future__ import annotations

import hashlib
from typing import Any

from src.contracts.workflow_control import ModelCallAuditRecord, ModelCallReplayBundle


def build_model_call_audit_record(
    *,
    operation: str,
    scope: str,
    request: Any,
    response: Any,
) -> ModelCallAuditRecord:
    system_prompt = str(getattr(request, "system_prompt", "") or "")
    user_prompt = str(getattr(request, "user_prompt", "") or "")
    rendered_hash = hashlib.sha256(
        f"{system_prompt}\n{user_prompt}".encode("utf-8")
    ).hexdigest()
    prompt_hash = str(
        getattr(request, "prompt_hash", "")
        or getattr(request, "prompt_sha256", "")
        or getattr(request, "prompt_user_sha256", "")
        or rendered_hash
    )
    seed = getattr(request, "seed", None)
    try:
        normalized_seed = int(seed) if seed is not None else None
    except (TypeError, ValueError):
        normalized_seed = None
    return ModelCallAuditRecord(
        schema_version="1.0",
        operation=str(operation),
        scope=str(scope),
        provider_decision="openai_primary",
        prompt_namespace=str(getattr(request, "prompt_namespace", "") or ""),
        prompt_hash=prompt_hash,
        rendered_prompt_redaction_hash=rendered_hash,
        model=str(
            getattr(response, "model", "") or getattr(request, "model", "") or ""
        ),
        temperature=getattr(request, "temperature", None),
        seed=normalized_seed,
        seed_supported=normalized_seed is not None,
        schema_name=str(getattr(request, "schema_name", "") or ""),
        output_schema_version=str(getattr(request, "schema_version", "") or ""),
        response_id=str(
            getattr(response, "request_id", "")
            or getattr(response, "response_id", "")
            or ""
        ),
        input_tokens=getattr(response, "input_tokens", None),
        output_tokens=getattr(response, "output_tokens", None),
        total_tokens=getattr(response, "total_tokens", None),
        estimated_cost_usd=float(getattr(response, "estimated_cost_usd", 0.0) or 0.0),
        cache_key=str(getattr(request, "response_cache_key", "") or ""),
        cache_decision=(
            "enabled"
            if bool(getattr(request, "response_cache_enabled", False))
            else "disabled"
        ),
        validation_result=str(getattr(request, "validation_result", "") or ""),
    )


def build_model_call_replay_bundle(
    audit_record: ModelCallAuditRecord,
) -> ModelCallReplayBundle:
    return ModelCallReplayBundle(
        schema_version="1.0",
        audit_record=audit_record,
        replay_inputs={
            "operation": audit_record.operation,
            "scope": audit_record.scope,
            "provider_decision": audit_record.provider_decision,
            "prompt_namespace": audit_record.prompt_namespace,
            "prompt_hash": audit_record.prompt_hash,
            "rendered_prompt_redaction_hash": audit_record.rendered_prompt_redaction_hash,
            "model": audit_record.model,
            "temperature": audit_record.temperature,
            "seed": audit_record.seed,
            "schema_name": audit_record.schema_name,
            "schema_version": audit_record.output_schema_version,
            "cache_key": audit_record.cache_key,
        },
        live_provider_call_allowed=False,
    )


def audit_record_fields(record: ModelCallAuditRecord) -> dict[str, object]:
    return {
        "operation": record.operation,
        "scope": record.scope,
        "provider_decision": record.provider_decision,
        "prompt_namespace": record.prompt_namespace,
        "prompt_hash": record.prompt_hash,
        "rendered_prompt_redaction_hash": record.rendered_prompt_redaction_hash,
        "model": record.model,
        "temperature": record.temperature,
        "seed": record.seed,
        "seed_supported": record.seed_supported,
        "schema_name": record.schema_name,
        "schema_version": record.output_schema_version,
        "response_id": record.response_id,
        "input_tokens": record.input_tokens,
        "output_tokens": record.output_tokens,
        "total_tokens": record.total_tokens,
        "estimated_cost_usd": record.estimated_cost_usd,
        "cache_key": record.cache_key,
        "cache_decision": record.cache_decision,
        "validation_result": record.validation_result,
    }
