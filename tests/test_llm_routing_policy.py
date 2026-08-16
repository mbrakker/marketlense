from __future__ import annotations

import pytest

from src.contracts.llm import LLMRoutingPolicy
from src.utils.errors import AppError
from src.utils.model_resolver import (
    execution_policies_from_config,
    registered_production_llm_namespaces,
    registered_report_generation_namespaces,
    resolve_execution_policy,
    resolve_routing_policy,
    routing_policies_from_config,
)


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


def test_specific_model_override_inherits_nearest_policy_quality_controls() -> None:
    policies = routing_policies_from_config(
        {
            "report_vs/artifacts": {
                "tier": "routine",
                "max_input_tokens": 48_000,
                "compaction_enabled": True,
                "quality_threshold": 0.8,
                "same_provider_fallback": True,
            }
        },
        model_overrides={"report_vs/artifacts/summary": "gpt-5-mini"},
    )

    decision = resolve_routing_policy(
        "report_vs/artifacts/summary", policies, default_model="gpt-5"
    )

    assert decision.model == "gpt-5-mini"
    assert decision.tier == "routine"
    assert decision.compaction_enabled is True
    assert decision.quality_threshold == 0.8


def test_execution_policy_uses_longest_prefix_and_changes_identity() -> None:
    policies = execution_policies_from_config(
        {
            "report_vs": {
                "model": "gpt-5-mini",
                "temperature": 0.4,
                "timeout_seconds": 60,
            },
            "report_vs/validate": {
                "model": "gpt-5-mini",
                "temperature": 0.0,
                "timeout_seconds": 60,
                "structured_output_schema_identity": "validation.v1",
            },
        },
        model_overrides={},
        legacy_routing={},
        default_model="gpt-5-mini",
        default_temperature=1.0,
        default_seed=None,
        default_timeout_seconds=600,
    )

    validation = resolve_execution_policy(
        "report_vs/validate/grounding",
        policies,
        default_model="gpt-5-mini",
        default_temperature=1.0,
        default_seed=None,
        default_timeout_seconds=600,
    )
    artifact = resolve_execution_policy(
        "report_vs/artifacts/summary",
        policies,
        default_model="gpt-5-mini",
        default_temperature=1.0,
        default_seed=None,
        default_timeout_seconds=600,
    )

    assert validation.policy_source == "report_vs/validate"
    assert validation.policy.temperature == 0.0
    assert validation.policy_hash != artifact.policy_hash


def test_legacy_exact_model_override_retains_inherited_execution_controls() -> None:
    policies = execution_policies_from_config(
        {
            "report_vs": {
                "model": "gpt-5-mini",
                "temperature": 1.0,
                "max_output_tokens": 4096,
                "timeout_seconds": 600,
            }
        },
        model_overrides={"report_vs/artifacts/summary": "gpt-5-mini"},
        legacy_routing={},
        default_model="gpt-5-mini",
        default_temperature=1.0,
        default_seed=None,
        default_timeout_seconds=600,
    )

    decision = resolve_execution_policy(
        "report_vs/artifacts/summary",
        policies,
        default_model="gpt-5-mini",
        default_temperature=1.0,
        default_seed=None,
        default_timeout_seconds=600,
    )

    assert decision.policy_source == "report_vs/artifacts/summary"
    assert decision.policy.max_output_tokens == 4096
    assert decision.policy.timeout_seconds == 600


def test_execution_policy_rejects_normalized_duplicate_and_provider_retries() -> None:
    common = {
        "model_overrides": {},
        "legacy_routing": {},
        "default_model": "gpt-5-mini",
        "default_temperature": 1.0,
        "default_seed": None,
        "default_timeout_seconds": 600,
    }
    with pytest.raises(AppError) as duplicate:
        execution_policies_from_config(
            {
                "report.vs": {"model": "gpt-5-mini"},
                "report/vs": {"model": "gpt-5-mini"},
            },
            **common,
        )
    assert duplicate.value.code == "llm_execution_policy_ambiguous"

    with pytest.raises(AppError) as retries:
        execution_policies_from_config(
            {"report_vs": {"model": "gpt-5-mini", "provider_retry_count": 1}},
            **common,
        )
    assert retries.value.code == "llm_execution_policy_provider_retries_forbidden"


def test_registered_report_namespaces_are_preflight_inventory() -> None:
    namespaces = registered_report_generation_namespaces()
    assert "report_vs/artifacts/summary" in namespaces
    assert "report_vs/validate/semantic" in namespaces


def test_form_value_derivation_is_a_registered_production_namespace() -> None:
    assert (
        "browser_report_download/form_value_derivation"
        in registered_production_llm_namespaces()
    )


def test_registered_production_namespace_uses_approved_longest_prefix() -> None:
    policies = execution_policies_from_config(
        {
            "browser_report_download/browser_route": {
                "model": "gpt-5-mini",
                "temperature": 0.0,
                "timeout_seconds": 180,
            }
        },
        model_overrides={},
        legacy_routing={},
        default_model="gpt-5-mini",
        default_temperature=1.0,
        default_seed=None,
        default_timeout_seconds=600,
    )

    decision = resolve_execution_policy(
        "browser_report_download/browser_route/browser_pdf_click",
        policies,
        default_model="gpt-5-mini",
        default_temperature=1.0,
        default_seed=None,
        default_timeout_seconds=600,
        require_registered_namespace=True,
    )

    assert decision.policy_source == "browser_report_download/browser_route"
    assert decision.compatibility_mode is False


def test_unknown_production_namespace_is_rejected_without_compatibility_policy() -> (
    None
):
    with pytest.raises(AppError) as err:
        resolve_execution_policy(
            "unregistered/production_call",
            {},
            default_model="gpt-5-mini",
            default_temperature=1.0,
            default_seed=None,
            default_timeout_seconds=600,
            require_registered_namespace=True,
        )

    assert err.value.code == "llm_execution_policy_unknown_namespace"
    assert "pdf_text/ocr_fallback" in registered_production_llm_namespaces()


def test_policy_preflight_rejects_missing_registered_namespace_before_io() -> None:
    from src.utils.model_resolver import preflight_execution_policy_coverage

    policies = execution_policies_from_config(
        {
            "report_vs": {
                "model": "gpt-5-mini",
                "temperature": 0.0,
                "timeout_seconds": 60,
            }
        },
        model_overrides={},
        legacy_routing={},
        default_model="gpt-5-mini",
        default_temperature=1.0,
        default_seed=None,
        default_timeout_seconds=600,
    )

    with pytest.raises(AppError) as error:
        preflight_execution_policy_coverage(
            policies,
            default_model="gpt-5-mini",
            default_temperature=1.0,
            default_seed=None,
            default_timeout_seconds=600,
        )

    assert error.value.code == "llm_execution_policy_unknown_namespace"
