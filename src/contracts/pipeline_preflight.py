from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from src.contracts.browser_download import BrowserDownloadSettings
from src.contracts.config import AppSettings
from src.contracts.ingest import IngestSettings
from src.contracts.mailbox_acquisition import MailboxAcquisitionSettings
from src.contracts.publish import PublishSettings
from src.contracts.publisher_inventory import PublisherInventorySettings
from src.contracts.workflow_control import WorkflowControlSettings
from src.contracts.workflow_queue import WorkflowQueuePolicy

PreflightCheckStatus = Literal["pass", "warning", "blocker", "auto_fixed"]
CapabilityStatus = Literal[
    "ready", "degraded", "blocked", "not_required", "not_checked"
]
CapabilityProfileName = Literal["manual", "autonomous_mvp"]


@dataclass(frozen=True)
class CapabilityPreflightCheck:
    schema_version: str = field(
        metadata={"doc": "Capability preflight check schema version."}
    )
    capability: str = field(
        metadata={"doc": "Stable name of the infrastructure capability checked."}
    )
    affected_workflows: list[str] = field(
        metadata={"doc": "Enabled workflows that depend on this capability."}
    )
    status: CapabilityStatus = field(
        metadata={
            "doc": "Capability status: ready, degraded, blocked, not_required, or not_checked."
        }
    )
    reason_code: str = field(
        metadata={"doc": "Stable machine-readable reason without secret values."}
    )
    retryable: bool = field(
        metadata={"doc": "Whether recovery may safely retry this capability check."}
    )
    remediation: str = field(
        metadata={"doc": "Safe, actionable operator remediation guidance."}
    )
    required: bool = field(
        metadata={"doc": "Whether an enabled workflow requires this capability."}
    )


@dataclass(frozen=True)
class CapabilityPreflightRequest:
    schema_version: str = field(
        metadata={"doc": "Capability preflight request schema version."}
    )
    profile_name: CapabilityProfileName = field(
        metadata={"doc": "Resolved operational configuration profile."}
    )
    settings: AppSettings = field(
        metadata={
            "doc": "Resolved application settings; secret values are never serialized."
        }
    )
    workflow_control: WorkflowControlSettings = field(
        metadata={"doc": "Resolved supervisor and workflow preflight configuration."}
    )
    queue_policies: dict[str, WorkflowQueuePolicy] = field(
        metadata={"doc": "Resolved queue enablement and budget policies."}
    )
    publish_settings: PublishSettings | None = field(
        default=None,
        metadata={"doc": "Resolved publication settings when publication is enabled."},
    )
    mailbox_settings: MailboxAcquisitionSettings | None = field(
        default=None,
        metadata={"doc": "Resolved mailbox settings when mailbox work is enabled."},
    )
    browser_settings: BrowserDownloadSettings | None = field(
        default=None,
        metadata={"doc": "Resolved browser settings when browser work is enabled."},
    )
    publisher_inventory_settings: PublisherInventorySettings | None = field(
        default=None,
        metadata={
            "doc": "Resolved publisher inventory settings when publisher discovery is enabled."
        },
    )
    publisher_inventory_config_error: str | None = field(
        default=None,
        metadata={
            "doc": "Safe stable config error code scoped to publisher discovery, if its optional settings could not load."
        },
    )
    live_checks: bool = field(
        default=False,
        metadata={
            "doc": "Whether bounded read-only external capability probes may run."
        },
    )


@dataclass(frozen=True)
class CapabilityPreflightReport:
    schema_version: str = field(
        metadata={"doc": "Capability preflight report schema version."}
    )
    profile_name: CapabilityProfileName = field(
        metadata={"doc": "Profile evaluated by this report."}
    )
    status: CapabilityStatus = field(
        metadata={"doc": "Overall readiness outcome derived from required checks."}
    )
    workflow_names: list[str] = field(
        metadata={"doc": "Ordered enabled workflows included in this proof."}
    )
    workflow_statuses: dict[str, CapabilityStatus] = field(
        metadata={
            "doc": "Readiness per enabled workflow so an unavailable integration does not obscure independent workflow status."
        }
    )
    checks: list[CapabilityPreflightCheck] = field(
        metadata={"doc": "Deterministic ordered capability checks."}
    )
    elapsed_ms: int = field(
        metadata={"doc": "Wall-clock duration of this preflight in milliseconds."}
    )
    provider_calls: int = field(
        metadata={"doc": "Number of bounded external provider requests made."}
    )
    external_writes: int = field(
        metadata={
            "doc": "Number of external data writes performed; capability checks use zero."
        }
    )
    blocking_count: int = field(
        metadata={"doc": "Required capabilities not ready for execution."}
    )


@dataclass(frozen=True)
class PipelinePreflightCheck:
    schema_version: str = field(
        metadata={"doc": "Pipeline preflight check schema version."}
    )
    check_name: str = field(metadata={"doc": "Stable preflight check name."})
    status: PreflightCheckStatus = field(
        metadata={"doc": "Check outcome: pass, warning, blocker, or auto_fixed."}
    )
    code: str = field(metadata={"doc": "Stable machine-readable outcome code."})
    message: str = field(metadata={"doc": "Sanitized operator-facing outcome message."})
    next_action: str = field(
        metadata={"doc": "Exact next action needed before execution continues."}
    )
    auto_fix_applied: bool = field(
        metadata={"doc": "True when the preflight remediated the issue."}
    )
    metadata: dict[str, Any] = field(
        metadata={"doc": "Sanitized structured evidence for the check."}
    )


@dataclass(frozen=True)
class PipelinePreflightReport:
    schema_version: str = field(
        metadata={"doc": "Pipeline preflight report schema version."}
    )
    workflow: str = field(metadata={"doc": "Workflow being preflighted."})
    planned_side_effects: list[str] = field(
        metadata={"doc": "Expensive or external side-effect families planned."}
    )
    passed: bool = field(metadata={"doc": "True when no blocking checks failed."})
    expensive_side_effects_allowed: bool = field(
        metadata={"doc": "True when planned expensive work may start."}
    )
    blocker_count: int = field(metadata={"doc": "Number of blocking failures."})
    warning_count: int = field(metadata={"doc": "Number of non-blocking warnings."})
    auto_fixed_count: int = field(metadata={"doc": "Number of remediations applied."})
    checks: list[PipelinePreflightCheck] = field(
        metadata={"doc": "All preflight checks in deterministic order."}
    )
    blockers: list[PipelinePreflightCheck] = field(
        metadata={"doc": "Blocking checks that prevent expensive work."}
    )
    warnings: list[PipelinePreflightCheck] = field(
        metadata={"doc": "Warning checks that do not prevent expensive work."}
    )
    auto_fixable_issues: list[PipelinePreflightCheck] = field(
        metadata={"doc": "Checks remediated automatically during preflight."}
    )
    next_actions: list[str] = field(
        metadata={"doc": "Deduplicated operator or orchestrator next actions."}
    )


@dataclass(frozen=True)
class PipelinePreflightRequest:
    schema_version: str = field(
        metadata={"doc": "Pipeline preflight request schema version."}
    )
    workflow: str = field(metadata={"doc": "Workflow being preflighted."})
    planned_side_effects: list[str] = field(
        metadata={"doc": "Planned expensive or external side-effect families."}
    )
    settings: IngestSettings = field(
        metadata={"doc": "Resolved ingest/report settings to inspect."}
    )
    prompt_namespaces: list[str] = field(
        metadata={"doc": "Prompt namespaces required by the planned workflow."}
    )
    require_llm: bool = field(
        metadata={"doc": "Whether model credentials and model settings are required."}
    )
    require_drive: bool = field(
        metadata={"doc": "Whether Drive source or archive readiness is required."}
    )
    require_publish: bool = field(
        metadata={"doc": "Whether WordPress publish readiness is required."}
    )
    require_browser: bool = field(
        metadata={"doc": "Whether browser acquisition dependencies are required."}
    )
    require_live_endpoints: bool = field(
        metadata={"doc": "Whether bounded live endpoint probes should run."}
    )
    publish_settings: PublishSettings | None = field(
        default=None,
        metadata={
            "doc": "Resolved publish settings when publish readiness is planned."
        },
    )
