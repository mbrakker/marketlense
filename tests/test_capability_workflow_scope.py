from __future__ import annotations

from src.contracts.workflow_queue import WORKFLOW_QUEUE_NAMES, WorkflowQueuePolicy
from src.orchestrators.pipeline_preflight_orchestrator import (
    _QUEUE_PREFLIGHT_PROFILES,
    derive_capability_workflows,
    workflow_profiles_for_runtime,
)


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
    assert set(_QUEUE_PREFLIGHT_PROFILES) == set(WORKFLOW_QUEUE_NAMES)


def test_mailbox_delivery_includes_its_browser_and_drive_prerequisite_profile() -> None:
    assert workflow_profiles_for_runtime(("mailbox_delivery",)) == ("report_download",)
