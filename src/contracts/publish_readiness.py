"""Versioned contracts for the canonical report publish-readiness decision."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

PUBLISH_READINESS_SCHEMA_VERSION = "1.0"
PUBLISH_READINESS_VALIDATOR_VERSION = "publish-readiness:v1"
PUBLISH_READINESS_REFRESH_PLAN_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class PublishReadinessRuleResult:
    """One bounded, deterministic rule result retained with the decision."""

    rule_id: str = field(
        metadata={"doc": "Stable canonical readiness rule identifier."}
    )
    status: str = field(metadata={"doc": "pass or fail."})
    surfaces: List[str] = field(
        default_factory=list,
        metadata={"doc": "Bounded public or artifact surfaces inspected by the rule."},
    )
    detail: str = field(
        default="", metadata={"doc": "Bounded non-public diagnostic summary."}
    )
    schema_version: str = field(
        default=PUBLISH_READINESS_SCHEMA_VERSION,
        metadata={"doc": "Rule result schema version."},
    )


@dataclass(frozen=True)
class PublishReadinessArtifact:
    """Hash-bound readiness decision consumed directly by publication."""

    report_id: str = field(metadata={"doc": "Canonical report identifier."})
    status: str = field(metadata={"doc": "pass or fail across all readiness rules."})
    artifact_hashes: Dict[str, str] = field(
        default_factory=dict,
        metadata={"doc": "Hashes of persisted analysis and presentation artifacts."},
    )
    rule_results: List[PublishReadinessRuleResult] = field(
        default_factory=list,
        metadata={"doc": "Ordered canonical readiness results."},
    )
    final_html_hash: str = field(
        default="", metadata={"doc": "SHA-256 of the exact rendered HTML document."}
    )
    publication_projection_hash: str = field(
        default="",
        metadata={"doc": "SHA-256 of the normalized final WordPress body projection."},
    )
    configuration_hash: str = field(
        default="", metadata={"doc": "Resolved producer configuration hash."}
    )
    policy_hash: str = field(
        default="", metadata={"doc": "Resolved producer policy hash."}
    )
    producer_revision: str = field(
        default="", metadata={"doc": "Producer source revision or workspace sentinel."}
    )
    created_at_utc: str = field(
        default="", metadata={"doc": "UTC creation time of the decision."}
    )
    expires_at_utc: str = field(
        default="", metadata={"doc": "UTC expiry time; blank only for legacy parsing."}
    )
    staleness_conditions: List[str] = field(
        default_factory=list,
        metadata={"doc": "Conditions that invalidate the retained decision."},
    )
    provenance: Dict[str, str] = field(
        default_factory=dict,
        metadata={
            "doc": "Classified source and public-link provenance retained for audit."
        },
    )
    artifact_hash: str = field(
        default="",
        metadata={"doc": "SHA-256 signature over this artifact excluding itself."},
    )
    validator_version: str = field(
        default=PUBLISH_READINESS_VALIDATOR_VERSION,
        metadata={"doc": "Canonical validator compatibility version."},
    )
    schema_version: str = field(
        default=PUBLISH_READINESS_SCHEMA_VERSION,
        metadata={"doc": "Publish-readiness artifact schema version."},
    )


@dataclass(frozen=True)
class PublishReadinessRefreshPlan:
    """Typed deterministic recovery decision derived from publish readiness."""

    report_id: str = field(metadata={"doc": "Canonical report identifier."})
    previous_readiness_state: str = field(
        metadata={
            "doc": (
                "ready, expiring, stale, failed, incompatible, or missing_unverifiable."
            )
        }
    )
    reason: str = field(metadata={"doc": "Stable reason for the refresh decision."})
    invalidated_artifact_or_check: str = field(
        metadata={"doc": "Bounded readiness check or artifact invalidated."}
    )
    selected_resume_stage: str | None = field(
        metadata={"doc": "Earliest checkpoint proposed before lineage proof."}
    )
    execution_intent: str = field(
        default="",
        metadata={"doc": "Existing canonical minimum-execution intent to enforce."},
    )
    reused_stages: list[str] = field(
        default_factory=list,
        metadata={"doc": "Workflow stages retained by this readiness decision."},
    )
    reused_artifacts: list[str] = field(
        default_factory=list,
        metadata={"doc": "Artifact families retained before graph-level proof."},
    )
    regenerated_stages: list[str] = field(
        default_factory=list,
        metadata={"doc": "Stages requested before graph-level proof."},
    )
    forced_invalidations: dict[str, str] = field(
        default_factory=dict,
        metadata={
            "doc": "Typed family invalidations consumed by the canonical planner."
        },
    )
    configuration_hash: str = field(
        default="", metadata={"doc": "Current resolved configuration identity."}
    )
    policy_hash: str = field(
        default="", metadata={"doc": "Current resolved policy identity."}
    )
    producer_revision: str = field(
        default="", metadata={"doc": "Current producer revision identity."}
    )
    readiness_artifact_hash: str = field(
        default="", metadata={"doc": "Retained readiness artifact signature."}
    )
    avoided_external_calls: list[str] = field(
        default_factory=list,
        metadata={"doc": "External call categories avoided by the proposed plan."},
    )
    avoided_provider_calls: int | None = field(
        default=None,
        metadata={"doc": "Known avoided provider calls, or null when unpriced."},
    )
    avoided_tokens: int | None = field(
        default=None,
        metadata={"doc": "Known avoided provider tokens, or null when unknown."},
    )
    avoided_cost_usd: float | None = field(
        default=None,
        metadata={"doc": "Known avoided estimated cost, or null when unpriced."},
    )
    avoided_duration_ms: int | None = field(
        default=None,
        metadata={"doc": "Known avoided duration, or null when unmeasured."},
    )
    execution_result: str = field(
        default="planned",
        metadata={"doc": "planned, not_required, blocked, succeeded, or failed."},
    )
    execution_plan_hash: str = field(
        default="", metadata={"doc": "Canonical minimum-execution plan identity."}
    )
    refresh_plan_hash: str = field(
        default="", metadata={"doc": "Deterministic signature of this refresh plan."}
    )
    schema_version: str = field(
        default=PUBLISH_READINESS_REFRESH_PLAN_SCHEMA_VERSION,
        metadata={"doc": "Refresh-plan schema version."},
    )
