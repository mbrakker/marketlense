from __future__ import annotations

from src.contracts.llm import LLMRoutingPolicy
from src.utils.model_resolver import resolve_routing_policy, routing_policies_from_config


def test_routing_policy_uses_longest_namespace_prefix() -> None:
    policy = LLMRoutingPolicy(
        schema_version="1.0",
        model="gpt-5-mini",
        tier="routine",
        max_input_tokens=12_000,
        compaction_enabled=True,
        quality_threshold=0.8,
        same_provider_fallback=True,
    )

    decision = resolve_routing_policy(
        "report_vs/artifacts/summary",
        {"report_vs": policy, "report_vs/artifacts": policy},
        default_model="gpt-5",
    )

    assert decision.policy_source == "report_vs/artifacts"
    assert decision.model == "gpt-5-mini"
    assert decision.same_provider_fallback is True


def test_routing_policy_defaults_without_cross_provider_fallback() -> None:
    decision = resolve_routing_policy(
        "unknown",
        {},
        default_model="gpt-5",
    )

    assert decision.policy_source == "default"
    assert decision.model == "gpt-5"
    assert decision.same_provider_fallback is True


def test_yaml_policy_owns_the_selected_model_without_a_legacy_override() -> None:
    policies = routing_policies_from_config(
        {
            "report_vs/evidence_packs": {
                "model": "gpt-5-mini",
                "tier": "evidence_sensitive",
                "max_input_tokens": 64_000,
                "compaction_enabled": True,
                "quality_threshold": 0.9,
                "same_provider_fallback": True,
            }
        },
        model_overrides={},
    )

    decision = resolve_routing_policy(
        "report_vs/evidence_packs/findings",
        policies,
        default_model="gpt-5",
    )

    assert decision.model == "gpt-5-mini"
    assert decision.tier == "evidence_sensitive"
    assert decision.max_input_tokens == 64_000
