from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

CapabilityStatus = Literal[
    "ready", "degraded", "blocked", "not_required", "not_checked"
]
CapabilityProfileName = Literal["manual", "autonomous_mvp"]


@dataclass(frozen=True)
class CapabilityWorkflowDecision:
    """Execution authorization for one workflow in a capability proof."""

    schema_version: str = field(
        metadata={"doc": "Execution-readiness decision schema version."}
    )
    workflow: str = field(metadata={"doc": "Canonical workflow being decided."})
    status: CapabilityStatus = field(
        metadata={"doc": "Diagnostic status retained without collapsing not_checked."}
    )
    executable: bool = field(
        metadata={"doc": "Whether this workflow may claim or dispatch work."}
    )
    reason_codes: list[str] = field(
        metadata={"doc": "Stable reasons that explain the decision."}
    )
    remediations: list[str] = field(
        metadata={"doc": "Safe operator remediations in deterministic order."}
    )
    required_capabilities: list[str] = field(
        default_factory=list,
        metadata={"doc": "Capabilities required by this workflow scope."},
    )


@dataclass(frozen=True)
class CapabilityReadinessProof:
    """Redacted identity and validity material for an execution decision."""

    schema_version: str = field(
        metadata={"doc": "Persisted capability-proof schema version."}
    )
    proof_id: str = field(metadata={"doc": "Hash of semantic proof identity."})
    profile_name: CapabilityProfileName = field(
        metadata={"doc": "Selected operational profile."}
    )
    workflow_scope: list[str] = field(
        metadata={"doc": "Exact ordered workflow scope evaluated."}
    )
    configuration_fingerprint: str = field(
        metadata={"doc": "Redacted effective configuration identity."}
    )
    execution_policy_fingerprint: str = field(
        metadata={"doc": "Execution-policy and queue-policy identity."}
    )
    build_identity: str = field(
        metadata={"doc": "Repository/build identity used by the proof."}
    )
    dependency_identity: str = field(
        metadata={"doc": "Supported runtime/dependency identity."}
    )
    asset_identity: str = field(
        metadata={"doc": "Required asset/tool/schema identity."}
    )
    sqlite_identity: str = field(
        metadata={"doc": "Required SQLite schema/integrity identity."}
    )
    provider_identity: str = field(
        metadata={"doc": "Normalized provider capability-result identity."}
    )
    tool_identity: str = field(
        metadata={"doc": "Required executable/runtime tool identity."}
    )
    generated_at_utc: str = field(metadata={"doc": "UTC proof generation time."})
    expires_at_utc: str = field(metadata={"doc": "UTC proof expiry time."})
    verification_mode: str = field(
        metadata={"doc": "offline or live bounded verification mode."}
    )
    reason_codes: list[str] = field(
        metadata={"doc": "Bounded stable proof reason codes."}
    )
    remediation: list[str] = field(metadata={"doc": "Bounded safe remediation values."})
    artifact_reference: str = field(
        default="",
        metadata={"doc": "Retained redacted proof artifact reference."},
    )
    valid: bool = field(
        default=True,
        metadata={"doc": "Whether the proof is currently internally valid."},
    )


@dataclass(frozen=True)
class CapabilityExecutionReadiness:
    """Typed decision consumed at workflow dispatch and claim boundaries."""

    schema_version: str = field(
        metadata={"doc": "Execution-readiness decision schema version."}
    )
    profile_name: CapabilityProfileName = field(
        metadata={"doc": "Profile whose exact scope was checked."}
    )
    workflow_scope: list[str] = field(
        metadata={"doc": "Exact ordered runnable-profile workflow scope."}
    )
    executable_workflows: list[str] = field(
        metadata={"doc": "Workflows authorized to claim or dispatch work."}
    )
    blocked_workflows: dict[str, list[str]] = field(
        metadata={"doc": "Blocked workflows and stable reason codes."}
    )
    deferred_workflows: dict[str, list[str]] = field(
        metadata={"doc": "Deferred workflows and stable reason codes."}
    )
    decisions: list[CapabilityWorkflowDecision] = field(
        metadata={"doc": "Per-workflow decisions in deterministic order."}
    )
    proof: CapabilityReadinessProof = field(
        metadata={"doc": "Identity and validity proof consumed by execution."}
    )

    def is_workflow_executable(self, workflow: str) -> bool:
        return str(workflow).strip() in set(self.executable_workflows)
