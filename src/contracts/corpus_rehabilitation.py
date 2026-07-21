"""Read-only classification and plan evidence for retained-corpus rehabilitation."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CorpusRehabilitationPlanRequest:
    schema_version: str = field(metadata={"doc": "Plan request schema version."})
    db_path: str = field(metadata={"doc": "Canonical reports SQLite database."})
    limit: int = field(default=100, metadata={"doc": "Maximum retained reports read."})


@dataclass(frozen=True)
class CorpusRehabilitationCandidate:
    schema_version: str = field(metadata={"doc": "Candidate schema version."})
    report_id: str = field(metadata={"doc": "Canonical retained report identifier."})
    classification: str = field(
        metadata={"doc": "Typed rehabilitation classification."}
    )
    disposition: str = field(
        metadata={"doc": "repair, recompute, content_review, or abstain."}
    )
    reason: str = field(metadata={"doc": "Bounded deterministic decision reason."})
    reusable_artifact_count: int = field(
        metadata={"doc": "Validated retained artifacts eligible for reuse."}
    )
    estimated_provider_calls: int | None = field(
        metadata={
            "doc": "Known planned provider calls; absent when evidence is insufficient."
        }
    )
    estimated_cost_usd: float | None = field(
        metadata={"doc": "Known cost estimate; absent rather than silently zero."}
    )
    estimate_status: str = field(
        metadata={"doc": "known or unavailable estimate provenance."}
    )
    source_checksum: str = field(
        default="", metadata={"doc": "Retained source checksum when provable."}
    )
    retained_reference: str = field(
        default="", metadata={"doc": "Retained artifact reference when safe to queue."}
    )
    reusable_artifact_ids: list[str] = field(
        default_factory=list,
        metadata={
            "doc": "Validated immutable artifact identifiers eligible for reuse."
        },
    )


@dataclass(frozen=True)
class CorpusRehabilitationPlanResponse:
    schema_version: str = field(metadata={"doc": "Plan response schema version."})
    candidates: list[CorpusRehabilitationCandidate] = field(default_factory=list)
    classification_counts: dict[str, int] = field(default_factory=dict)
    provider_calls: int = field(
        default=0, metadata={"doc": "Always zero: plan reads retained evidence only."}
    )


@dataclass(frozen=True)
class CorpusRehabilitationCampaignCreateRequest:
    """Explicitly persist a bounded campaign from the current read-only plan."""

    schema_version: str = field(metadata={"doc": "Campaign request schema version."})
    db_path: str = field(metadata={"doc": "Canonical reports SQLite database."})
    report_ids: list[str] = field(default_factory=list)
    batch_size: int = field(default=10)
    created_by: str = field(default="operator")


@dataclass(frozen=True)
class CorpusRehabilitationCampaignItem:
    schema_version: str = field(
        default="1.0", metadata={"doc": "Campaign item schema version."}
    )
    campaign_id: str = field(default="")
    report_id: str = field(default="")
    classification: str = field(default="")
    disposition: str = field(default="")
    source_checksum: str = field(default="")
    retained_reference: str = field(default="")
    reusable_artifact_ids: list[str] = field(default_factory=list)
    status: str = field(default="operator_held")
    reason: str = field(default="")
    queue_job_id: str = field(default="")


@dataclass(frozen=True)
class CorpusRehabilitationCampaign:
    schema_version: str = field(
        default="1.0", metadata={"doc": "Campaign schema version."}
    )
    campaign_id: str = field(default="")
    plan_hash: str = field(default="")
    approval_hash: str = field(default="")
    status: str = field(default="planned")
    batch_size: int = field(default=0)
    planned_provider_calls: int = field(default=0)
    actual_provider_calls: int = field(default=0)
    planned_cost_usd: float | None = field(default=None)
    actual_cost_usd: float | None = field(default=None)
    created_at_utc: str = field(default="")
    approved_at_utc: str = field(default="")
    submitted_at_utc: str = field(default="")


@dataclass(frozen=True)
class CorpusRehabilitationCampaignResponse:
    schema_version: str = field(
        default="1.0", metadata={"doc": "Campaign response schema version."}
    )
    campaign: CorpusRehabilitationCampaign = field(
        default_factory=CorpusRehabilitationCampaign
    )
    items: list[CorpusRehabilitationCampaignItem] = field(default_factory=list)
    created: bool = field(default=False)


@dataclass(frozen=True)
class CorpusRehabilitationCampaignApprovalRequest:
    schema_version: str = field(metadata={"doc": "Approval request schema version."})
    db_path: str = field(metadata={"doc": "Canonical reports SQLite database."})
    campaign_id: str = field(metadata={"doc": "Persisted campaign identifier."})
    approved_by: str = field(metadata={"doc": "Bounded operator identifier."})
    reason: str = field(metadata={"doc": "Bounded approval reason."})


@dataclass(frozen=True)
class CorpusRehabilitationCampaignReadRequest:
    schema_version: str = field(metadata={"doc": "Read request schema version."})
    db_path: str = field(metadata={"doc": "Canonical reports SQLite database."})
    campaign_id: str = field(metadata={"doc": "Persisted campaign identifier."})


@dataclass(frozen=True)
class CorpusRehabilitationCampaignItemUpdateRequest:
    schema_version: str = field(metadata={"doc": "Item update request schema version."})
    db_path: str = field(metadata={"doc": "Canonical reports SQLite database."})
    campaign_id: str = field(metadata={"doc": "Persisted campaign identifier."})
    report_id: str = field(metadata={"doc": "Campaign report identifier."})
    status: str = field(metadata={"doc": "queued, completed, or operator_held."})
    queue_job_id: str = field(default="")
    actual_provider_calls: int = field(default=0)
    actual_cost_usd: float | None = field(default=None)
