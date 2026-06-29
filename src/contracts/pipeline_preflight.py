from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from src.contracts.ingest import IngestSettings
from src.contracts.publish import PublishSettings

PreflightCheckStatus = Literal["pass", "warning", "blocker", "auto_fixed"]


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
