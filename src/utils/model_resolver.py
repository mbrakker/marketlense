from __future__ import annotations

from typing import Dict

from src.contracts.llm import LLMRoutingDecision, LLMRoutingPolicy


def _normalize_namespace(namespace: str) -> str:
    if not isinstance(namespace, str):
        return ""
    normalized = namespace.replace(".", "/").strip()
    return normalized.strip("/")


def resolve_model(namespace: str, overrides: Dict[str, str], default_model: str) -> str:
    """
    Resolve the model for a prompt namespace using longest-prefix match.

    Examples:
    - namespace: "report_vs/validate/grounding"
    - overrides keys allowed: "report_vs/validate/grounding", "report_vs/validate", "report_vs"
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
