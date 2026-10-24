from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from src.contracts.pipeline_preflight import (
    CapabilityPreflightCheck,
    CapabilityPreflightReport,
)
from src.contracts.workflow_queue import WORKFLOW_QUEUE_NAMES, WorkflowQueuePolicy
from src.orchestrators.pipeline_preflight_orchestrator import (
    build_execution_readiness,
    derive_capability_workflows,
    validate_execution_readiness,
    validate_capability_registry_coverage,
    workflow_profiles_for_runtime,
)
from src.orchestrators.workflow_queue_orchestrator import (
    default_workflow_queue_registry,
)
from src.orchestrators.workflow_queue_capabilities import (
    canonical_workflow_queue_capability_registration,
)
from src.utils.errors import AppError


def _queue(name: str, *, enabled: bool) -> WorkflowQueuePolicy:
    return WorkflowQueuePolicy(queue_name=name, enabled=enabled)


def test_manual_profile_checks_only_the_explicit_manual_workflow() -> None:
    workflows = derive_capability_workflows(
        profile_name="manual",
        supervisor_enabled=False,
        queue_policies={"wordpress_publish": _queue("wordpress_publish", enabled=True)},
    )

    assert workflows == ("report_generation",)


def test_autonomous_profile_uses_enabled_queue_configuration() -> None:
    workflows = derive_capability_workflows(
        profile_name="autonomous_mvp",
        supervisor_enabled=True,
        queue_policies={
            "report_analysis": _queue("report_analysis", enabled=True),
            "mailbox_delivery": _queue("mailbox_delivery", enabled=False),
            "wordpress_publish": _queue("wordpress_publish", enabled=True),
        },
    )

    assert workflows == ("report_analysis", "wordpress_publish")


def test_autonomous_profile_does_not_claim_workflows_when_supervisor_is_disabled() -> (
    None
):
    workflows = derive_capability_workflows(
        profile_name="autonomous_mvp",
        supervisor_enabled=False,
        queue_policies={"report_analysis": _queue("report_analysis", enabled=True)},
    )

    assert workflows == ()


def test_every_registered_queue_has_a_capability_profile_decision() -> None:
    assert all(
        canonical_workflow_queue_capability_registration(queue_name) is not None
        for queue_name in WORKFLOW_QUEUE_NAMES
    )


def test_mailbox_delivery_includes_its_browser_and_drive_prerequisite_profile() -> None:
    assert workflow_profiles_for_runtime(("mailbox_delivery",)) == ("report_download",)


def test_execution_readiness_preserves_not_checked_and_blocks_it() -> None:
    report = CapabilityPreflightReport(
        schema_version="1.0",
        profile_name="autonomous_mvp",
        status="degraded",
        workflow_names=["report_analysis", "cost_reconciliation"],
        workflow_statuses={
            "report_analysis": "degraded",
            "cost_reconciliation": "ready",
        },
        checks=[
            CapabilityPreflightCheck(
                schema_version="1.0",
                capability="llm_model",
                affected_workflows=["report_analysis"],
                status="not_checked",
                reason_code="llm_live_probe_skipped",
                retryable=False,
                remediation="Rerun with --live",
                required=True,
            ),
            CapabilityPreflightCheck(
                schema_version="1.0",
                capability="queue_operations",
                affected_workflows=["report_analysis", "cost_reconciliation"],
                status="ready",
                reason_code="queue_operational_settings_ready",
                retryable=False,
                remediation="continue",
                required=True,
            ),
        ],
        elapsed_ms=17,
        provider_calls=0,
        external_writes=0,
        blocking_count=1,
    )

    readiness = build_execution_readiness(
        report,
        generated_at_utc="2026-10-24T10:00:00Z",
        expires_at_utc="2026-10-24T10:15:00Z",
    )

    assert readiness.workflow_scope == ["cost_reconciliation", "report_analysis"]
    assert readiness.executable_workflows == ["cost_reconciliation"]
    assert readiness.blocked_workflows == {
        "report_analysis": ["llm_live_probe_skipped"]
    }
    assert readiness.deferred_workflows == {}
    assert readiness.proof.proof_id
    assert readiness.proof.verification_mode == "offline"
    with pytest.raises(AppError) as error:
        validate_execution_readiness(
            readiness,
            expected_workflow="report_analysis",
            now_utc="2026-10-24T10:01:00Z",
        )
    assert error.value.code == "capability_readiness_workflow_blocked"


def test_incomplete_or_stale_readiness_proof_fails_closed() -> None:
    report = CapabilityPreflightReport(
        schema_version="1.0",
        profile_name="autonomous_mvp",
        status="ready",
        workflow_names=["cost_reconciliation"],
        workflow_statuses={"cost_reconciliation": "ready"},
        checks=[],
        elapsed_ms=0,
        provider_calls=0,
        external_writes=0,
        blocking_count=0,
    )
    readiness = build_execution_readiness(
        report,
        generated_at_utc="2026-10-24T10:00:00Z",
        expires_at_utc="2026-10-24T10:15:00Z",
    )
    incomplete = replace(
        readiness,
        proof=replace(readiness.proof, provider_identity=""),
    )
    with pytest.raises(AppError) as incomplete_error:
        validate_execution_readiness(
            incomplete,
            expected_workflow="cost_reconciliation",
            now_utc="2026-10-24T10:01:00Z",
        )
    assert incomplete_error.value.code == "capability_readiness_incomplete"
    with pytest.raises(AppError) as stale_error:
        validate_execution_readiness(
            readiness,
            expected_workflow="cost_reconciliation",
            expected_configuration_fingerprint="0" * 64,
            now_utc="2026-10-24T10:01:00Z",
        )
    assert stale_error.value.code == "capability_readiness_configuration_mismatch"


def test_execution_readiness_rejects_mismatched_scope() -> None:
    report = CapabilityPreflightReport(
        schema_version="1.0",
        profile_name="autonomous_mvp",
        status="ready",
        workflow_names=["cost_reconciliation"],
        workflow_statuses={"cost_reconciliation": "ready"},
        checks=[],
        elapsed_ms=0,
        provider_calls=0,
        external_writes=0,
        blocking_count=0,
    )

    readiness = build_execution_readiness(
        report,
        generated_at_utc="2026-10-24T10:00:00Z",
        expires_at_utc="2026-10-24T10:15:00Z",
    )

    assert readiness.is_workflow_executable("cost_reconciliation") is True
    assert readiness.is_workflow_executable("wordpress_publish") is False


def test_registered_queue_capabilities_are_derived_from_handler_effects() -> None:
    registry = default_workflow_queue_registry()
    control = SimpleNamespace(preflight_profiles={})
    policies = {
        queue_name: WorkflowQueuePolicy(
            queue_name=queue_name,
            enabled=True,
            max_workers=1,
            max_attempts=1,
            lease_seconds=60,
            maximum_pending=1,
            maximum_fanout=1,
            budget_profile="test",
        )
        for queue_name in WORKFLOW_QUEUE_NAMES
    }

    resolved = validate_capability_registry_coverage(policies, control)

    assert set(resolved) == set(WORKFLOW_QUEUE_NAMES)
    assert set(registry) == {
        (queue_name, f"{queue_name}.v1") for queue_name in WORKFLOW_QUEUE_NAMES
    }
    for (queue_name, _job_type), registration in registry.items():
        assert (
            tuple(sorted(registration.expected_external_effects))
            == resolved[queue_name].expected_external_effects
        )
        assert (
            registration.required_capabilities
            == resolved[queue_name].required_capabilities
        )
    assert "llm_model" in resolved["report_analysis"].required_capabilities
    assert "vector_store" in resolved["report_analysis"].required_capabilities
    assert {
        "browser",
        "google_drive",
    }.issubset(resolved["publisher_discovery"].required_capabilities)
    assert "llm_model" in resolved["signal_generation"].required_capabilities
    assert "vector_store" in resolved["vector_retention"].required_capabilities
    assert "llm_model" not in resolved["cost_reconciliation"].required_capabilities


def test_unknown_enabled_queue_fails_capability_coverage_closed() -> None:
    policies = {
        "unknown_queue": WorkflowQueuePolicy(
            queue_name="unknown_queue",
            enabled=True,
            max_workers=1,
            max_attempts=1,
            lease_seconds=60,
            maximum_pending=1,
            maximum_fanout=1,
            budget_profile="test",
        )
    }

    with pytest.raises(AppError) as error:
        validate_capability_registry_coverage(
            policies, SimpleNamespace(preflight_profiles={})
        )

    assert error.value.code == "workflow_queue_capability_mapping_missing"
