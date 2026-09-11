"""Canonical producing-prompt identity for report artifact families."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from src.contracts.prompts import PromptSet
from src.generators.prompt_preparation import PreparedPromptBundle
from src.services.prompt_service import build_llm_execution_identity
from src.utils.cache_utils import sha256_json
from src.utils.model_resolver import (
    execution_policies_from_config,
    resolve_execution_policy,
    resolve_routing_policy,
    routing_policies_from_config,
)

ARTIFACT_PROMPT_IDENTITY_SCHEMA_VERSION = "1.0"
ARTIFACT_PROMPT_VALIDATOR_VERSION = "artifacts_schema:3.0"


def artifact_prompt_identity(
    *,
    prepared: PreparedPromptBundle,
    relevant_input_hash: str,
) -> dict[str, object]:
    """Return the single retained identity for the prompt that produced output."""

    return {
        "schema_version": ARTIFACT_PROMPT_IDENTITY_SCHEMA_VERSION,
        "namespace": prepared.namespace,
        "family_schema_version": "1.0",
        "processing_version": "report_generation_checkpoint_v2",
        "prompt_content_hash": prepared.prompt_content_hash,
        "prompt_dependency_manifest": asdict(prepared.dependency_manifest),
        "execution_identity": prepared.execution_identity.execution_identity,
        "execution_identity_manifest": asdict(prepared.execution_identity),
        "model_provider": str(prepared.execution_policy.policy.provider or ""),
        "model_name": prepared.resolved_model,
        "model_policy_namespace": prepared.namespace.split("/", 1)[0],
        "routing_policy_version": prepared.execution_policy.policy_hash,
        "validator_version": ARTIFACT_PROMPT_VALIDATOR_VERSION,
        "relevant_input_hash": str(relevant_input_hash or ""),
        "configuration_policy_hash": sha256_json(
            {
                "execution_policy_hash": prepared.execution_policy.policy_hash,
                "execution_policy": asdict(prepared.execution_policy.policy),
                "routing_policy": asdict(prepared.routing_decision),
            }
        ),
    }


def artifact_family_for_producing_namespace(namespace: str) -> str:
    """Map a primary or targeted-regeneration namespace to its output family."""

    return str(namespace or "").replace("/regenerate/", "/", 1)


def current_artifact_prompt_identity(
    *,
    namespace: str,
    prompt_set: PromptSet,
    settings: Any,
    retrieval_mode: str,
    relevant_input_hash: str,
) -> dict[str, object]:
    """Build the current identity without rendering templates or calling a model."""

    default_model = str(getattr(settings, "openai_model", "") or "")
    default_temperature = float(getattr(settings, "temperature", 1.0))
    routing_decision = resolve_routing_policy(
        namespace,
        routing_policies_from_config(
            getattr(settings, "llm_routing", {}),
            model_overrides=getattr(settings, "openai_models", {}),
        ),
        default_model=default_model,
    )
    execution_policy = resolve_execution_policy(
        namespace,
        execution_policies_from_config(
            getattr(settings, "llm_execution_policies", {}),
            model_overrides=getattr(settings, "openai_models", {}),
            legacy_routing=getattr(settings, "llm_routing", {}),
            default_model=default_model,
            default_temperature=default_temperature,
            default_seed=getattr(settings, "openai_seed", None),
            default_timeout_seconds=getattr(settings, "openai_timeout_seconds", None),
        ),
        default_model=default_model,
        default_temperature=default_temperature,
        default_seed=getattr(settings, "openai_seed", None),
        default_timeout_seconds=getattr(settings, "openai_timeout_seconds", None),
    )
    policy = execution_policy.policy
    seed = (
        None
        if policy.seed_policy == "disabled"
        else policy.seed
        if policy.seed_policy == "fixed"
        else getattr(settings, "openai_seed", None)
    )
    execution_identity = build_llm_execution_identity(
        prompt_content_hash=prompt_set.prompt_content_hash,
        provider=policy.provider,
        model=policy.model,
        temperature=policy.temperature,
        seed=seed,
        max_output_tokens=policy.max_output_tokens,
        timeout_seconds=policy.timeout_seconds
        if policy.timeout_seconds is not None
        else getattr(settings, "openai_timeout_seconds", None),
        retrieval_mode=retrieval_mode,
        routing_policy={
            "policy_source": routing_decision.policy_source,
            "tier": routing_decision.tier,
            "quality_threshold": routing_decision.quality_threshold,
            "same_provider_fallback": routing_decision.same_provider_fallback,
            "max_input_tokens": routing_decision.max_input_tokens,
            "compaction_enabled": routing_decision.compaction_enabled,
            "execution_policy_hash": execution_policy.policy_hash,
            "execution_policy_source": execution_policy.policy_source,
        },
        compaction_policy={
            "enabled": routing_decision.compaction_enabled,
            "max_input_tokens": routing_decision.max_input_tokens or None,
            "strategy": "anchor_preserving_head_tail",
        },
        output_contract_schema_version="artifact_json:1.0",
        validator_version=ARTIFACT_PROMPT_VALIDATOR_VERSION,
    )
    return {
        "schema_version": ARTIFACT_PROMPT_IDENTITY_SCHEMA_VERSION,
        "namespace": namespace,
        "family_schema_version": "1.0",
        "processing_version": "report_generation_checkpoint_v2",
        "prompt_content_hash": prompt_set.prompt_content_hash,
        "prompt_dependency_manifest": asdict(prompt_set.dependency_manifest),
        "execution_identity": execution_identity.execution_identity,
        "execution_identity_manifest": asdict(execution_identity),
        "model_provider": str(policy.provider or ""),
        "model_name": policy.model,
        "model_policy_namespace": namespace.split("/", 1)[0],
        "routing_policy_version": execution_policy.policy_hash,
        "validator_version": ARTIFACT_PROMPT_VALIDATOR_VERSION,
        "relevant_input_hash": str(relevant_input_hash or ""),
        "configuration_policy_hash": sha256_json(
            {
                "execution_policy_hash": execution_policy.policy_hash,
                "execution_policy": asdict(policy),
                "routing_policy": asdict(routing_decision),
            }
        ),
    }
