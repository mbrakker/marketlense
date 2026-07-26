from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from typing import Any, Dict

from src.contracts.llm import (
    LLMExecutionPolicy,
    LLMExecutionPolicyDecision,
    LLMRoutingDecision,
    LLMRoutingPolicy,
)
from src.utils.errors import AppError

REPORT_GENERATION_NAMESPACES: tuple[str, ...] = (
    "report_vs/artifacts/summary",
    "report_vs/artifacts/cover_semantics",
    "report_vs/artifacts/cover_semantics_repair",
    "report_vs/artifacts/insights_candidates",
    "report_vs/artifacts/insights_final",
    "report_vs/artifacts/quotes",
    "report_vs/artifacts/expert_comment",
    "report_vs/artifacts/linkedin_post",
    "report_vs/doc_map",
    "report_vs/evidence_packs/scope",
    "report_vs/evidence_packs/findings",
    "report_vs/evidence_packs/limitations",
    "report_vs/evidence_packs/methods",
    "report_vs/evidence_packs/quote_candidates",
    "report_vs/validate/grounding",
    "report_vs/validate/semantic",
    "report_vs/taxonomy",
    "report_vs/taxonomy_repair",
    "report_vs/context_category_fit",
    "report_vs/context_category_fit_repair",
    "report_vs/structured_output/repair",
    "report_vs/structured_output/regenerate",
)

# This is the finite production prompt/provider inventory. It is intentionally
# separate from the policy map: policies may govern a family by approved prefix,
# while a new namespace must still be deliberately added here before it can
# reach provider preparation. Generic provider operations that do not load a
# prompt use their own explicit action namespace at the owning service boundary.
PRODUCTION_LLM_NAMESPACES: tuple[str, ...] = (
    "browser_report_download/browser_route",
    "browser_report_download/browser_route/browser_email_form",
    "browser_report_download/browser_route/browser_listing_hub",
    "browser_report_download/browser_route/browser_onsite_report",
    "browser_report_download/browser_route/browser_pdf_click",
    "browser_report_download/browser_route/browser_tracker_redirect",
    "claim_embedding/generate",
    "crop_qa_escalation/publication_strict",
    "cross_report_analysis/synthesis",
    "pdf_text/ocr_fallback",
    "publisher_inventory/discovery",
    "publisher_inventory/meaningful_candidate_screen",
    "rank_candidates",
    "rank_candidates/crop_refine",
    "report_vs/artifacts/cover_semantics",
    "report_vs/artifacts/cover_semantics_repair",
    "report_vs/artifacts/expert_comment",
    "report_vs/artifacts/insights_candidates",
    "report_vs/artifacts/insights_final",
    "report_vs/artifacts/linkedin_post",
    "report_vs/artifacts/quotes",
    "report_vs/artifacts/regenerate/expert_comment",
    "report_vs/artifacts/regenerate/insights_candidates",
    "report_vs/artifacts/regenerate/insights_final",
    "report_vs/artifacts/regenerate/linkedin_post",
    "report_vs/artifacts/regenerate/quotes",
    "report_vs/artifacts/regenerate/summary",
    "report_vs/artifacts/summary",
    "report_vs/context_category_fit",
    "report_vs/context_category_fit_repair",
    "report_vs/structured_output/repair",
    "report_vs/structured_output/regenerate",
    "report_vs/doc_map",
    "report_vs/evidence_packs/contradictions",
    "report_vs/evidence_packs/findings",
    "report_vs/evidence_packs/key_metrics",
    "report_vs/evidence_packs/limitations",
    "report_vs/evidence_packs/methods",
    "report_vs/evidence_packs/quote_candidates",
    "report_vs/evidence_packs/recommendations",
    "report_vs/evidence_packs/risk_register",
    "report_vs/evidence_packs/scope",
    "report_vs/figure_caption",
    "report_vs/taxonomy",
    "report_vs/taxonomy_repair",
    "report_vs/validate/grounding",
    "report_vs/validate/semantic",
    "signal_generation/synthesis",
    "briefing_generation/synthesis",
)


def _normalize_namespace(namespace: str) -> str:
    if not isinstance(namespace, str):
        return ""
    normalized = namespace.replace(".", "/").strip()
    return normalized.strip("/")


def registered_report_generation_namespaces() -> tuple[str, ...]:
    """Return the finite prompt namespaces used by report-generation workflows."""

    return REPORT_GENERATION_NAMESPACES


def registered_production_llm_namespaces() -> tuple[str, ...]:
    """Return the deterministic inventory of production prompt namespaces."""

    return PRODUCTION_LLM_NAMESPACES


def preflight_execution_policy_coverage(
    policies: dict[str, LLMExecutionPolicy],
    *,
    default_model: str,
    default_temperature: float,
    default_seed: int | None,
    default_timeout_seconds: float | None,
) -> tuple[LLMExecutionPolicyDecision, ...]:
    """Resolve every registered production namespace before provider I/O.

    The result is deterministic and deliberately has no compatibility fallback:
    a missing or unknown namespace raises before a live workflow can issue a
    provider request.
    """

    return tuple(
        resolve_execution_policy(
            namespace,
            policies,
            default_model=default_model,
            default_temperature=default_temperature,
            default_seed=default_seed,
            default_timeout_seconds=default_timeout_seconds,
            require_registered_namespace=True,
        )
        for namespace in PRODUCTION_LLM_NAMESPACES
    )


def execution_policy_matrix(
    decisions: tuple[LLMExecutionPolicyDecision, ...],
) -> list[dict[str, Any]]:
    """Return the canonical, non-secret resolution matrix for retention."""

    return [
        {
            "namespace": decision.namespace,
            "policy_source": decision.policy_source,
            "provider": decision.policy.provider,
            "model": decision.policy.model,
            "policy": asdict(decision.policy),
            "policy_hash": decision.policy_hash,
        }
        for decision in decisions
    ]


def _stable_policy_hash(policy: LLMExecutionPolicy) -> str:
    payload = asdict(policy)
    return hashlib.sha256(
        json.dumps(
            payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def _policy_from_mapping(
    namespace_prefix: str,
    raw: dict[str, Any],
    *,
    default_model: str,
    default_temperature: float,
    default_timeout_seconds: float | None,
    legacy_routing: dict[str, dict[str, object]],
) -> LLMExecutionPolicy:
    routing = _nearest_mapping(namespace_prefix, legacy_routing)
    model = str(raw.get("model") or default_model).strip()
    provider = str(raw.get("provider") or "openai").strip().lower()
    if not model or provider != "openai":
        raise AppError(
            code="llm_execution_policy_incomplete",
            message="LLM execution policies require an OpenAI provider and model",
            retryable=False,
            context={"namespace": namespace_prefix},
        )
    retries = int(raw.get("provider_retry_count", 0) or 0)
    if retries != 0:
        raise AppError(
            code="llm_execution_policy_provider_retries_forbidden",
            message="Provider retries are owned by orchestrators and must remain zero",
            retryable=False,
            context={"namespace": namespace_prefix},
        )
    fallback = str(
        raw.get("fallback_policy")
        or (
            "same_provider_only"
            if routing.get("same_provider_fallback", True)
            else "disabled"
        )
    ).strip()
    if fallback not in {"same_provider_only", "disabled"}:
        raise AppError(
            code="llm_execution_policy_fallback_invalid",
            message=(
                "LLM execution policy fallback must be same_provider_only or disabled"
            ),
            retryable=False,
            context={"namespace": namespace_prefix},
        )
    seed_policy = str(raw.get("seed_policy") or "inherit").strip()
    if seed_policy not in {"inherit", "fixed", "disabled"}:
        raise AppError(
            code="llm_execution_policy_seed_invalid",
            message="LLM execution policy seed_policy is invalid",
            retryable=False,
            context={"namespace": namespace_prefix},
        )
    fixed_seed = raw.get("seed") if seed_policy == "fixed" else None
    if seed_policy == "fixed" and not isinstance(fixed_seed, int):
        raise AppError(
            code="llm_execution_policy_seed_missing",
            message="A fixed seed_policy requires an integer seed",
            retryable=False,
            context={"namespace": namespace_prefix},
        )
    temperature = float(raw.get("temperature", default_temperature))
    if temperature < 0 or temperature > 2:
        raise AppError(
            code="llm_execution_policy_temperature_invalid",
            message="LLM execution policy temperature must be between 0 and 2",
            retryable=False,
            context={"namespace": namespace_prefix},
        )
    max_output_tokens = raw.get("max_output_tokens")
    if max_output_tokens is not None and int(max_output_tokens) < 1:
        raise AppError(
            code="llm_execution_policy_output_limit_invalid",
            message="max_output_tokens must be positive when configured",
            retryable=False,
            context={"namespace": namespace_prefix},
        )
    timeout = raw.get("timeout_seconds", default_timeout_seconds)
    if timeout is not None and float(timeout) <= 0:
        raise AppError(
            code="llm_execution_policy_timeout_invalid",
            message="timeout_seconds must be positive when configured",
            retryable=False,
            context={"namespace": namespace_prefix},
        )
    retrieval_mode = str(raw.get("retrieval_mode") or "inherit").strip()
    if retrieval_mode not in {"inherit", "chat_json", "file_search"}:
        raise AppError(
            code="llm_execution_policy_retrieval_invalid",
            message="LLM execution policy retrieval_mode is invalid",
            retryable=False,
            context={"namespace": namespace_prefix},
        )
    return LLMExecutionPolicy(
        schema_version=str(raw.get("schema_version") or "1.0"),
        namespace_prefix=namespace_prefix,
        provider=provider,
        model=model,
        temperature=temperature,
        seed_policy=seed_policy,  # type: ignore[arg-type]
        seed=int(fixed_seed) if fixed_seed is not None else None,
        max_output_tokens=(
            int(max_output_tokens) if max_output_tokens is not None else None
        ),
        reasoning_effort=str(raw.get("reasoning_effort") or "").strip(),
        structured_output_mode=str(
            raw.get("structured_output_mode") or "json_object"
        ).strip(),
        structured_output_schema_identity=str(
            raw.get("structured_output_schema_identity") or ""
        ).strip(),
        output_validator_identity=str(
            raw.get("output_validator_identity") or ""
        ).strip(),
        retrieval_mode=retrieval_mode,
        timeout_seconds=float(timeout) if timeout is not None else None,
        provider_retry_count=retries,
        max_input_tokens=max(
            0, int(raw.get("max_input_tokens", routing.get("max_input_tokens", 0)) or 0)
        ),
        compaction_enabled=bool(
            raw.get("compaction_enabled", routing.get("compaction_enabled", False))
        ),
        fallback_policy=fallback,  # type: ignore[arg-type]
        pricing_key=str(raw.get("pricing_key") or model).strip(),
    )


def _nearest_mapping(
    namespace: str, mappings: dict[str, dict[str, object]]
) -> dict[str, object]:
    parts = namespace.split("/") if namespace else []
    for index in range(len(parts), 0, -1):
        found = mappings.get("/".join(parts[:index]))
        if found is not None:
            return found
    return {}


def execution_policies_from_config(
    raw_policies: object,
    *,
    model_overrides: Dict[str, str],
    legacy_routing: Dict[str, Dict[str, object]],
    default_model: str,
    default_temperature: float,
    default_seed: int | None,
    default_timeout_seconds: float | None,
) -> dict[str, LLMExecutionPolicy]:
    """Validate and adapt YAML policy mappings without accepting ambiguous keys."""

    raw_mapping = raw_policies if isinstance(raw_policies, dict) else {}
    normalized: dict[str, dict[str, Any]] = {}
    for raw_key, raw_value in raw_mapping.items():
        key = _normalize_namespace(str(raw_key))
        if not key or not isinstance(raw_value, dict):
            raise AppError(
                code="llm_execution_policy_invalid",
                message="Execution policy entries require a namespace and mapping value",
                retryable=False,
                context={"namespace": str(raw_key)},
            )
        if key in normalized:
            raise AppError(
                code="llm_execution_policy_ambiguous",
                message="Multiple execution policies normalize to the same prefix",
                retryable=False,
                context={"namespace": key},
            )
        normalized[key] = dict(raw_value)

    normalized_legacy = {
        _normalize_namespace(str(key)): dict(value)
        for key, value in legacy_routing.items()
        if _normalize_namespace(str(key)) and isinstance(value, dict)
    }
    merged: dict[str, dict[str, Any]] = dict(normalized)
    for raw_key, raw_model in model_overrides.items():
        key = _normalize_namespace(str(raw_key))
        model = str(raw_model or "").strip()
        if key and model and key not in merged:
            # Legacy per-namespace model selection remains supported, but it
            # must not discard the governed provider-call limits inherited
            # from the nearest canonical execution policy.  A bare exact
            # override would otherwise shadow (for example) report_vs's
            # output cap and timeout controls.
            merged[key] = {
                **_nearest_mapping(key, normalized),
                "model": model,
            }
    return {
        key: _policy_from_mapping(
            key,
            value,
            default_model=default_model,
            default_temperature=default_temperature,
            default_timeout_seconds=default_timeout_seconds,
            legacy_routing=normalized_legacy,
        )
        for key, value in merged.items()
    }


def resolve_execution_policy(
    namespace: str,
    policies: dict[str, LLMExecutionPolicy],
    *,
    default_model: str,
    default_temperature: float,
    default_seed: int | None,
    default_timeout_seconds: float | None,
    require_registered_namespace: bool = False,
) -> LLMExecutionPolicyDecision:
    """Resolve an execution policy by exact then longest-specific prefix."""

    base = _normalize_namespace(namespace)
    if require_registered_namespace and base not in PRODUCTION_LLM_NAMESPACES:
        raise AppError(
            code="llm_execution_policy_unknown_namespace",
            message="No registered production namespace matches this policy request",
            retryable=False,
            context={"namespace": base},
        )
    for index in range(len(base.split("/")), 0, -1):
        source = "/".join(base.split("/")[:index])
        policy = policies.get(source)
        if policy is not None:
            return LLMExecutionPolicyDecision(
                schema_version="1.0",
                namespace=base,
                policy_source=source,
                policy=policy,
                policy_hash=_stable_policy_hash(policy),
            )
    if require_registered_namespace:
        raise AppError(
            code="llm_execution_policy_unknown_namespace",
            message="Registered production namespace lacks an execution policy",
            retryable=False,
            context={"namespace": base},
        )
    compatibility_policy = LLMExecutionPolicy(
        schema_version="1.0",
        namespace_prefix="compatibility_default",
        provider="openai",
        model=default_model,
        temperature=default_temperature,
        seed_policy="fixed" if default_seed is not None else "inherit",
        seed=default_seed,
        timeout_seconds=default_timeout_seconds,
        pricing_key=default_model,
    )
    return LLMExecutionPolicyDecision(
        schema_version="1.0",
        namespace=base,
        policy_source="compatibility_default",
        policy=compatibility_policy,
        policy_hash=_stable_policy_hash(compatibility_policy),
        compatibility_mode=True,
    )


def resolve_model(namespace: str, overrides: Dict[str, str], default_model: str) -> str:
    """
    Resolve the model for a prompt namespace using longest-prefix match.

    Examples:
    - namespace: "report_vs/validate/grounding"
    - overrides keys allowed: a matching namespace or any ancestor prefix
    """
    base = _normalize_namespace(namespace)
    if not base:
        return default_model
    mapping: Dict[str, str] = {}
    if isinstance(overrides, dict):
        for raw_key, raw_value in overrides.items():
            key = _normalize_namespace(str(raw_key))
            val = str(raw_value).strip()
            if key and val:
                mapping[key] = val
    parts = base.split("/")
    for idx in range(len(parts), 0, -1):
        candidate = "/".join(parts[:idx])
        if candidate in mapping:
            return mapping[candidate]
    return default_model


def resolve_routing_policy(
    namespace: str,
    policies: Dict[str, LLMRoutingPolicy],
    *,
    default_model: str,
) -> LLMRoutingDecision:
    """Resolve a provider-local policy by deterministic longest namespace prefix."""
    base = _normalize_namespace(namespace)
    normalized: dict[str, LLMRoutingPolicy] = {}
    if isinstance(policies, dict):
        for raw_key, policy in policies.items():
            key = _normalize_namespace(str(raw_key))
            if key and isinstance(policy, LLMRoutingPolicy):
                normalized[key] = policy
    for index in range(len(base.split("/")), 0, -1):
        source = "/".join(base.split("/")[:index])
        matched_policy = normalized.get(source)
        if matched_policy is not None:
            return LLMRoutingDecision(
                schema_version="1.0",
                namespace=base,
                model=matched_policy.model,
                tier=matched_policy.tier,
                max_input_tokens=matched_policy.max_input_tokens,
                compaction_enabled=matched_policy.compaction_enabled,
                quality_threshold=matched_policy.quality_threshold,
                same_provider_fallback=matched_policy.same_provider_fallback,
                policy_source=source,
            )
    return LLMRoutingDecision(
        schema_version="1.0",
        namespace=base,
        model=default_model,
        tier="default",
        max_input_tokens=0,
        compaction_enabled=False,
        quality_threshold=0.0,
        same_provider_fallback=True,
        policy_source="default",
    )


def routing_policies_from_config(
    raw_policies: object,
    *,
    model_overrides: Dict[str, str],
) -> Dict[str, LLMRoutingPolicy]:
    """Adapt validated config mappings into explicit policy contracts."""
    policies: dict[str, LLMRoutingPolicy] = {}
    raw_mapping = raw_policies if isinstance(raw_policies, dict) else {}
    normalized_config = {
        _normalize_namespace(str(raw_key)): raw_value
        for raw_key, raw_value in raw_mapping.items()
        if _normalize_namespace(str(raw_key)) and isinstance(raw_value, dict)
    }

    def config_for(namespace: str) -> dict:
        parts = namespace.split("/")
        for index in range(len(parts), 0, -1):
            value = normalized_config.get("/".join(parts[:index]))
            if value is not None:
                return value
        return {}

    for raw_key, raw_model in model_overrides.items():
        namespace = _normalize_namespace(str(raw_key))
        model = str(raw_model or "").strip()
        if namespace and model:
            config = config_for(namespace)
            policies[namespace] = LLMRoutingPolicy(
                schema_version="1.0",
                model=model,
                tier=str(config.get("tier") or "default").strip() or "default",
                max_input_tokens=max(0, int(config.get("max_input_tokens") or 0)),
                compaction_enabled=bool(config.get("compaction_enabled", False)),
                quality_threshold=float(config.get("quality_threshold") or 0.0),
                same_provider_fallback=bool(config.get("same_provider_fallback", True)),
            )
    for raw_key, raw_value in raw_mapping.items():
        if not isinstance(raw_value, dict):
            continue
        namespace = _normalize_namespace(str(raw_key))
        model = str(
            raw_value.get("model") or model_overrides.get(namespace) or ""
        ).strip()
        if not namespace or not model:
            continue
        policies[namespace] = LLMRoutingPolicy(
            schema_version="1.0",
            model=model,
            tier=str(raw_value.get("tier") or "default").strip() or "default",
            max_input_tokens=max(0, int(raw_value.get("max_input_tokens") or 0)),
            compaction_enabled=bool(raw_value.get("compaction_enabled", False)),
            quality_threshold=float(raw_value.get("quality_threshold") or 0.0),
            same_provider_fallback=bool(raw_value.get("same_provider_fallback", True)),
        )
    return policies
