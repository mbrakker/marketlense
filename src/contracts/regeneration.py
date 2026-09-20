from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.contracts.ingest import IngestSettings
from src.contracts.run_context import RunContext
from src.contracts.semantic_ids import ReportId, SemanticIdContract


@dataclass(frozen=True)
class FailureFingerprint:
    """Stable, content-free identity for one repairable validation failure."""

    rule_id: str = field(metadata={"doc": "Stable validator rule identifier."})
    affected_section: str = field(
        metadata={"doc": "Normalized artifact section or field containing the failure."}
    )
    entity_id: str = field(
        default="",
        metadata={"doc": "Stable affected public-item identifier when known."},
    )
    evidence_ids: List[str] = field(
        default_factory=list,
        metadata={
            "doc": "Sorted retained evidence identities involved in the failure."
        },
    )
    schema_version: str = field(
        default="1.0", metadata={"doc": "Failure fingerprint schema version."}
    )

    @property
    def key(self) -> str:
        payload = {
            "rule_id": self.rule_id.strip().lower(),
            "affected_section": self.affected_section.strip().lower(),
            "entity_id": self.entity_id.strip(),
            "evidence_ids": sorted(
                {value.strip() for value in self.evidence_ids if value.strip()}
            ),
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()


@dataclass(frozen=True)
class RepairDelta:
    """Non-canonical memory retained from one candidate attempt."""

    resolved: List[FailureFingerprint] = field(default_factory=list)
    persisting: List[FailureFingerprint] = field(default_factory=list)
    introduced: List[FailureFingerprint] = field(default_factory=list)
    schema_version: str = field(
        default="1.0", metadata={"doc": "Repair-delta schema version."}
    )


def repair_strategy_fingerprint(
    failure_fingerprints: List[str], strategy: str, evidence_ids: List[str]
) -> str:
    """Return a stable identity for a failed strategy/evidence combination."""

    payload = {
        "failure_fingerprints": sorted(set(failure_fingerprints)),
        "strategy": strategy.strip().lower(),
        "evidence_ids": sorted(
            {value.strip() for value in evidence_ids if value.strip()}
        ),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class RegenerationIssue:
    rule_id: str = field(
        metadata={"doc": "Validation rule identifier associated with the issue."}
    )
    affected_section: str = field(
        metadata={"doc": "Original validation affected_section string."}
    )
    message: str = field(metadata={"doc": "Human-readable validation failure message."})
    severity: str = field(
        metadata={"doc": "Validation severity level: error|warning|info."}
    )
    repair_target: str = field(
        default="",
        metadata={"doc": "Normalized regeneration target key for the issue."},
    )
    entity_id: str = field(
        default="",
        metadata={"doc": "Stable entity identifier associated with the issue."},
    )
    evidence_ids: List[str] = field(
        default_factory=list,
        metadata={"doc": "Evidence identifiers relevant to the failed section."},
    )
    excluded_evidence_ids: List[str] = field(
        default_factory=list,
        metadata={
            "doc": "Evidence identifiers quarantined from this repair after a fidelity failure."
        },
    )
    pages: List[int] = field(
        default_factory=list,
        metadata={
            "doc": "Relevant one-based page numbers associated with the failure."
        },
    )
    failure_fingerprint: str = field(
        default="", metadata={"doc": "Stable fingerprint key for retry memory."}
    )
    schema_version: str = field(
        default="1.0", metadata={"doc": "Regeneration issue schema version."}
    )


@dataclass(frozen=True)
class RegenerationTarget:
    target_section: str = field(metadata={"doc": "Normalized regeneration target key."})
    regenerate_steps: List[str] = field(
        default_factory=list,
        metadata={"doc": "Ordered artifact steps that must be regenerated."},
    )
    prompt_namespaces: List[str] = field(
        default_factory=list,
        metadata={"doc": "Prompt namespaces used to regenerate this target."},
    )
    issues: List[RegenerationIssue] = field(
        default_factory=list,
        metadata={"doc": "Issues grouped under this regeneration target."},
    )
    repair_action: str = field(
        default="REGENERATE_ITEM",
        metadata={"doc": "Cheapest approved repair action for this target."},
    )
    repair_strategy: str = field(
        default="current_evidence",
        metadata={"doc": "Materially distinct repair strategy."},
    )
    allowed_paths: List[str] = field(
        default_factory=list,
        metadata={"doc": "Artifact roots allowed to change for this candidate."},
    )
    selected_evidence_ids: List[str] = field(default_factory=list)
    quarantined_evidence_ids: List[str] = field(default_factory=list)
    schema_version: str = field(
        default="1.0", metadata={"doc": "Regeneration target schema version."}
    )


@dataclass(frozen=True)
class RegenerationPlan:
    mode: str = field(metadata={"doc": "Plan mode: targeted|broad|skip."})
    targets: List[RegenerationTarget] = field(
        default_factory=list,
        metadata={"doc": "Ordered regeneration targets for the current attempt."},
    )
    unmappable_issues: List[RegenerationIssue] = field(
        default_factory=list,
        metadata={"doc": "Issues that could not be mapped to a concrete target."},
    )
    broad_retry_allowed: bool = field(
        default=False,
        metadata={"doc": "Whether a single broad retry remains available."},
    )
    schema_version: str = field(
        default="1.0", metadata={"doc": "Regeneration plan schema version."}
    )


@dataclass(frozen=True)
class LineageRegenerationPlan:
    schema_version: str = field(
        metadata={"doc": "Lineage regeneration plan schema version."}
    )
    change_kind: str = field(
        metadata={"doc": "Source, prompt, template, crop, or validator change."}
    )
    resume_from_stage: str = field(
        metadata={"doc": "Earliest checkpoint stage safe to reuse."}
    )
    full_regeneration_required: bool = field(
        metadata={"doc": "Whether source provenance requires a fresh pipeline run."}
    )
    reused_stages: List[str] = field(
        metadata={"doc": "Ordered valid stages retained without recomputation."}
    )
    regenerated_stages: List[str] = field(
        metadata={"doc": "Ordered stages that must be recomputed."}
    )
    avoided_work: List[str] = field(
        metadata={"doc": "Expensive work families safely avoided by the plan."}
    )


@dataclass(frozen=True)
class LineageRegenerationQualityReport:
    """Auditable quality and cost visibility for a selective regeneration plan."""

    schema_version: str = field(
        metadata={"doc": "Lineage regeneration quality-report schema version."}
    )
    change_kind: str = field(
        metadata={"doc": "Normalized change family used for invalidation."}
    )
    fan_out: int = field(
        metadata={"doc": "Total checkpoint stages considered by the plan."}
    )
    reused_stage_count: int = field(
        metadata={"doc": "Number of proven-compatible stages retained."}
    )
    regenerated_stage_count: int = field(
        metadata={"doc": "Number of stages scheduled for recomputation."}
    )
    avoided_work: List[str] = field(
        metadata={"doc": "Expensive work families safely avoided."}
    )
    estimated_avoided_cost_usd: float | None = field(
        metadata={
            "doc": "Known avoided cost, or null when no defensible price is available."
        }
    )
    cost_status: str = field(
        metadata={"doc": "known or unpriced; unpriced never represents free work."}
    )


@dataclass(frozen=True)
class RegenerationAttemptResult:
    attempt_index: int = field(
        metadata={"doc": "One-based regeneration attempt index."}
    )
    plan_mode: str = field(
        metadata={"doc": "Plan mode applied for this attempt: targeted|broad."}
    )
    validation_before_status: str = field(
        metadata={"doc": "Validation status before the regeneration attempt."}
    )
    validation_after_status: str = field(
        metadata={"doc": "Validation status after the regeneration attempt."}
    )
    regenerated_sections: List[str] = field(
        default_factory=list,
        metadata={"doc": "Artifact sections regenerated during this attempt."},
    )
    artifacts_path: str = field(
        default="",
        metadata={"doc": "Canonical artifacts.json path after this attempt."},
    )
    artifacts_snapshot_path: str = field(
        default="",
        metadata={"doc": "Per-attempt artifacts snapshot path."},
    )
    validation_path: str = field(
        default="",
        metadata={"doc": "Canonical validation.json path after this attempt."},
    )
    validation_snapshot_path: str = field(
        default="",
        metadata={"doc": "Per-attempt validation snapshot path."},
    )
    candidate_artifacts_path: str = field(
        default="",
        metadata={
            "doc": (
                "Immutable per-attempt candidate artifact path evaluated before "
                "promotion."
            )
        },
    )
    candidate_audit_path: str = field(
        default="",
        metadata={
            "doc": "Retained grounding and lineage audit for the candidate artifact."
        },
    )
    promotion_outcome: str = field(
        default="not_attempted",
        metadata={
            "doc": "Candidate disposition: promoted, rolled_back, or not_attempted."
        },
    )
    failure_fingerprints: List[str] = field(default_factory=list)
    repair_delta: RepairDelta = field(default_factory=RepairDelta)
    strategy_fingerprint: str = field(default="")
    latency_ms: int | None = field(default=None)
    schema_version: str = field(
        default="1.0", metadata={"doc": "Regeneration attempt result schema version."}
    )


@dataclass(frozen=True)
class RegenerationLoopState:
    attempt_count: int = field(
        metadata={"doc": "Number of regeneration attempts executed."}
    )
    max_attempts: int = field(
        metadata={"doc": "Configured maximum regeneration attempts."}
    )
    final_status: str = field(metadata={"doc": "Loop end status: pass|fail|skipped."})
    max_reached: bool = field(
        metadata={"doc": "Whether the loop exited because max attempts were reached."}
    )
    schema_version: str = field(
        default="1.0", metadata={"doc": "Regeneration loop state schema version."}
    )


@dataclass(frozen=True)
class ArtifactRegenerationRequest(SemanticIdContract):
    report_id: ReportId = field(metadata={"doc": "Report identifier."})
    report_name: str = field(
        metadata={"doc": "Normalized report slug used for persisted outputs."}
    )
    attempt_index: int = field(
        metadata={"doc": "One-based regeneration attempt index."}
    )
    plan: RegenerationPlan = field(
        metadata={"doc": "Concrete regeneration plan for this pass."}
    )
    current_artifacts: Dict[str, Any] = field(
        metadata={"doc": "Current canonical artifacts payload before regeneration."}
    )
    doc_map: Dict[str, Any] = field(
        metadata={"doc": "Resolved doc_map evidence pack payload."}
    )
    evidence_packs: Dict[str, Any] = field(
        metadata={"doc": "Resolved evidence-pack payloads keyed by pack name."}
    )
    settings: IngestSettings = field(
        metadata={"doc": "Resolved ingest settings for this report run."}
    )
    ctx: RunContext = field(
        metadata={"doc": "Structured logging/run context for the regeneration pass."}
    )
    source_status: Dict[str, Any] = field(
        default_factory=dict,
        metadata={"doc": "Source availability payload reused in artifacts output."},
    )
    categories: List[str] = field(
        default_factory=list,
        metadata={"doc": "Human-readable category labels for prompt grounding."},
    )
    vector_store_id: Optional[str] = field(
        default=None,
        metadata={"doc": "Vector store identifier, if artifact retrieval uses it."},
    )
    md5: Optional[str] = field(
        default=None,
        metadata={"doc": "Source PDF md5 used for cache metadata and logging."},
    )
    publisher_name: str = field(
        default="",
        metadata={"doc": "Publisher context recorded with downstream LLM usage."},
    )
    source_url: str = field(
        default="",
        metadata={
            "doc": "Source/report URL context recorded with downstream LLM usage."
        },
    )
    repair_memory: List[RepairDelta] = field(
        default_factory=list,
        metadata={"doc": "Rejected candidate deltas that must inform this repair."},
    )
    schema_version: str = field(
        default="1.0", metadata={"doc": "Artifact regeneration request schema version."}
    )


@dataclass(frozen=True)
class ArtifactRegenerationResponse:
    updated_artifacts: Dict[str, Any] = field(
        metadata={"doc": "Updated canonical artifacts payload after regeneration."}
    )
    regenerated_sections: List[str] = field(
        default_factory=list,
        metadata={"doc": "Ordered artifact sections regenerated in this pass."},
    )
    prompt_namespaces: List[str] = field(
        default_factory=list,
        metadata={"doc": "Prompt namespaces invoked during regeneration."},
    )
    artifacts_path: str = field(
        default="",
        metadata={"doc": "Canonical artifacts output path after regeneration."},
    )
    artifacts_snapshot_path: str = field(
        default="",
        metadata={"doc": "Per-attempt artifacts snapshot path."},
    )
    candidate_artifacts_path: str = field(
        default="",
        metadata={
            "doc": (
                "Candidate artifact path; it is not the current artifact until "
                "promotion."
            )
        },
    )
    repair_action: str = field(default="")
    repair_strategy: str = field(default="")
    schema_version: str = field(
        default="1.0",
        metadata={"doc": "Artifact regeneration response schema version."},
    )


@dataclass(frozen=True)
class RegenerationEvidenceLineage:
    """Evidence continuity retained for one material candidate entity."""

    entity_kind: str = field(
        metadata={"doc": "Artifact family: summary_claim, insight, or quote."}
    )
    entity_id: str = field(
        metadata={"doc": "Stable original claim or insight identity within its family."}
    )
    original_evidence_ids: List[str] = field(
        default_factory=list,
        metadata={"doc": "Evidence IDs carried by the current artifact."},
    )
    candidate_evidence_ids: List[str] = field(
        default_factory=list,
        metadata={"doc": "Evidence IDs carried by the candidate artifact."},
    )
    original_source_pages: List[int] = field(
        default_factory=list,
        metadata={"doc": "Source pages carried by the current artifact."},
    )
    candidate_source_pages: List[int] = field(
        default_factory=list,
        metadata={"doc": "Source pages carried by the candidate artifact."},
    )
    validation_issues: List[str] = field(
        default_factory=list,
        metadata={"doc": "Bounded validation issue codes associated with the entity."},
    )
    schema_version: str = field(
        default="1.0",
        metadata={"doc": "Regeneration evidence-lineage schema version."},
    )


@dataclass(frozen=True)
class RegenerationCandidateAudit:
    """Durable audit record for a candidate before its atomic promotion."""

    attempt_index: int = field(metadata={"doc": "One-based regeneration attempt."})
    before_sha256: str = field(
        metadata={"doc": "Canonical JSON hash of the current artifact before repair."}
    )
    after_sha256: str = field(
        metadata={"doc": "Canonical JSON hash of the candidate artifact."}
    )
    transformation_scope: List[str] = field(
        default_factory=list,
        metadata={"doc": "Regenerated artifact families in this candidate."},
    )
    unchanged_family_sha256: Dict[str, str] = field(
        default_factory=dict,
        metadata={
            "doc": (
                "Canonical hashes of claim-bearing artifact families proven "
                "byte-equivalent before and after this candidate repair."
            )
        },
    )
    current_artifacts_path: str = field(
        default="",
        metadata={
            "doc": "Current artifact path retained until atomic promotion succeeds."
        },
    )
    candidate_artifacts_path: str = field(
        default="", metadata={"doc": "Persisted candidate artifact path."}
    )
    validation_status: str = field(
        default="candidate",
        metadata={"doc": "Candidate validation status before promotion."},
    )
    promotion_outcome: str = field(
        default="candidate",
        metadata={"doc": "candidate, promoted, or rolled_back."},
    )
    validation_issues: List[str] = field(
        default_factory=list,
        metadata={"doc": "Bounded validation issue codes found for the candidate."},
    )
    evidence_lineage: List[RegenerationEvidenceLineage] = field(
        default_factory=list,
        metadata={"doc": "Original-to-candidate material evidence continuity."},
    )
    failure_fingerprints: List[str] = field(default_factory=list)
    repair_action: str = field(default="")
    repair_strategy: str = field(default="")
    allowed_paths: List[str] = field(default_factory=list)
    selected_evidence_ids: List[str] = field(default_factory=list)
    quarantined_evidence_ids: List[str] = field(default_factory=list)
    repair_delta: RepairDelta = field(default_factory=RepairDelta)
    report_id: str = field(default="")
    validation_run_id: str = field(default="")
    cohort_id: str = field(default="")
    workflow_run_id: str = field(default="")
    configuration_hash: str = field(default="")
    policy_hash: str = field(default="")
    producer_build_identity: str = field(default="")
    strategy_fingerprint: str = field(default="")
    latency_ms: int | None = field(default=None)
    schema_version: str = field(
        default="1.0",
        metadata={"doc": "Regeneration candidate-audit schema version."},
    )
