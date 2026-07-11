from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.contracts.ingest import IngestSettings
from src.contracts.run_context import RunContext
from src.contracts.semantic_ids import ReportId, SemanticIdContract


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
    pages: List[int] = field(
        default_factory=list,
        metadata={
            "doc": "Relevant one-based page numbers associated with the failure."
        },
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
        metadata={"doc": "Source/report URL context recorded with downstream LLM usage."},
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
    schema_version: str = field(
        default="1.0",
        metadata={"doc": "Artifact regeneration response schema version."},
    )
