from __future__ import annotations

from src.contracts.pipeline_preflight import (
    CapabilityPreflightReport,
    CapabilityExecutionReadiness,
)
from src.orchestrators.pipeline_preflight_orchestrator import build_execution_readiness


def ready_capability_readiness(
    workflows: tuple[str, ...],
    *,
    generated_at_utc: str = "2026-01-01T00:00:00Z",
    expires_at_utc: str = "2099-01-01T00:00:00Z",
) -> CapabilityExecutionReadiness:
    ordered = sorted(
        {str(workflow).strip() for workflow in workflows if str(workflow).strip()}
    )
    report = CapabilityPreflightReport(
        schema_version="1.0",
        profile_name="autonomous_mvp",
        status="ready",
        workflow_names=ordered,
        workflow_statuses={workflow: "ready" for workflow in ordered},
        checks=[],
        elapsed_ms=0,
        provider_calls=0,
        external_writes=0,
        blocking_count=0,
    )
    return build_execution_readiness(
        report,
        generated_at_utc=generated_at_utc,
        expires_at_utc=expires_at_utc,
    )
