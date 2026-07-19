from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional

from src.contracts.llm import LLMRoutingDecision
from src.contracts.prompts import (
    LLMExecutionIdentity,
    PromptDependencyManifest,
    PromptLoadRequest,
    PromptRenderRequest,
    PromptSet,
)
from src.contracts.run_context import RunContext
from src.services.prompt_service import build_llm_execution_identity
from src.utils.errors import AppError
from src.utils.model_resolver import (
    resolve_routing_policy,
    routing_policies_from_config,
)


@dataclass(frozen=True)
class PreparedPromptBundle:
    schema_version: str = field(
        metadata={"doc": "Prepared prompt bundle schema version."}
    )
    namespace: str = field(metadata={"doc": "Prompt namespace used for loading."})
    prompt_set: PromptSet = field(
        metadata={"doc": "Loaded prompt set used to render the request."}
    )
    system_prompt: str = field(metadata={"doc": "Rendered system prompt text."})
    user_prompt: str = field(metadata={"doc": "Rendered user prompt text."})
    resolved_model: str = field(metadata={"doc": "Resolved model identifier."})
    routing_decision: LLMRoutingDecision = field(
        metadata={"doc": "Deterministic quality/cost routing decision."}
    )
    dependency_manifest: PromptDependencyManifest = field(
        metadata={"doc": "Complete prompt dependency manifest used for rendering."}
    )
    prompt_content_hash: str = field(
        metadata={"doc": "Stable identity of all prompt content dependencies."}
    )
    execution_identity: LLMExecutionIdentity = field(
        metadata={"doc": "Resolved content and execution compatibility identity."}
    )


def model_request_identity_fields(bundle: PreparedPromptBundle) -> dict[str, Any]:
    """Return content-free provenance fields accepted by model request contracts."""

    return {
        "prompt_hash": bundle.prompt_content_hash,
        "prompt_content_hash": bundle.prompt_content_hash,
        "prompt_dependency_manifest": asdict(bundle.dependency_manifest),
        "execution_identity": bundle.execution_identity.execution_identity,
        "execution_identity_manifest": asdict(bundle.execution_identity),
    }


def prepare_prompt_bundle(
    *,
    namespace: str,
    settings: Any,
    ctx: RunContext,
    prompt_client: Any,
    system_variables: Optional[Dict[str, Any]] = None,
    user_variables: Optional[Dict[str, Any]] = None,
    reload_if_changed: bool = False,
    force_reload: bool = False,
    default_model: Optional[str] = None,
    provider: str = "openai",
    retrieval_mode: str = "chat_json",
    temperature: float | None = None,
    seed: int | None = None,
    max_output_tokens: int | None = None,
    timeout_seconds: float | None = None,
    output_contract_schema_version: str = "",
    validator_version: str = "",
) -> PreparedPromptBundle:
    prompt_set = prompt_client.load_prompt_set(
        PromptLoadRequest(
            schema_version="1.0",
            namespace=namespace,
            reload_if_changed=reload_if_changed,
            force_reload=force_reload,
        ),
        ctx,
    )
    rendered_system = prompt_client.render_prompt(
        PromptRenderRequest(
            schema_version="1.0",
            template=prompt_set.system,
            variables=dict(system_variables or {}),
        ),
        ctx,
    )
    rendered_user = prompt_client.render_prompt(
        PromptRenderRequest(
            schema_version="1.0",
            template=prompt_set.user,
            variables=dict(user_variables or {}),
        ),
        ctx,
    )
    fallback_model = str(default_model or getattr(settings, "openai_model", "") or "")
    routing_decision = resolve_routing_policy(
        namespace,
        routing_policies_from_config(
            getattr(settings, "llm_routing", {}),
            model_overrides=getattr(settings, "openai_models", {}),
        ),
        default_model=fallback_model,
    )
    manifest = prompt_set.dependency_manifest
    if manifest is None or not prompt_set.prompt_content_hash:
        raise AppError(
            code="prompt_dependency_manifest_missing",
            message="Canonical prompt loading did not provide dependency provenance",
            retryable=False,
            context={"namespace": namespace},
        )
    resolved_temperature = (
        float(temperature)
        if temperature is not None
        else (
            float(settings.temperature)
            if getattr(settings, "temperature", None) is not None
            else None
        )
    )
    resolved_seed = seed if seed is not None else getattr(settings, "openai_seed", None)
    resolved_timeout = (
        float(timeout_seconds)
        if timeout_seconds is not None
        else (
            float(settings.openai_timeout_seconds)
            if getattr(settings, "openai_timeout_seconds", None) is not None
            else None
        )
    )
    execution_identity = build_llm_execution_identity(
        prompt_content_hash=prompt_set.prompt_content_hash,
        provider=provider,
        model=routing_decision.model,
        temperature=resolved_temperature,
        seed=resolved_seed,
        max_output_tokens=max_output_tokens,
        timeout_seconds=resolved_timeout,
        provider_retry_count=0,
        retrieval_mode=retrieval_mode,
        routing_policy={
            "policy_source": routing_decision.policy_source,
            "tier": routing_decision.tier,
            "quality_threshold": routing_decision.quality_threshold,
            "same_provider_fallback": routing_decision.same_provider_fallback,
            "max_input_tokens": routing_decision.max_input_tokens,
            "compaction_enabled": routing_decision.compaction_enabled,
        },
        compaction_policy={
            "enabled": routing_decision.compaction_enabled,
            "max_input_tokens": routing_decision.max_input_tokens or None,
            "strategy": "anchor_preserving_head_tail",
        },
        output_contract_schema_version=output_contract_schema_version,
        validator_version=validator_version,
    )
    return PreparedPromptBundle(
        schema_version="1.0",
        namespace=namespace,
        prompt_set=prompt_set,
        system_prompt=rendered_system.text,
        user_prompt=rendered_user.text,
        resolved_model=routing_decision.model,
        routing_decision=routing_decision,
        dependency_manifest=manifest,
        prompt_content_hash=prompt_set.prompt_content_hash,
        execution_identity=execution_identity,
    )
