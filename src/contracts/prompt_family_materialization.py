"""Typed boundaries for independently reusable prompt-family outputs.

The report store remains the canonical lineage ledger.  These contracts add the
family-specific provenance needed to decide whether a retained model result can
be reused without treating the former composite ``artifacts`` file as proof for
an individual prompt family.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

PROMPT_FAMILY_MATERIALIZATION_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class PromptFamilyMaterializationRequest:
    """Request to atomically retain one bounded prompt-family result."""

    schema_version: str = field(
        metadata={"doc": "Prompt-family materialization request schema version."}
    )
    db_path: str = field(metadata={"doc": "Canonical reports SQLite path."})
    output_dir: str = field(metadata={"doc": "Controlled report output root."})
    report_id: str = field(metadata={"doc": "Owning report identifier."})
    report_slug: str = field(metadata={"doc": "Safe report output-path slug."})
    source_id: str = field(metadata={"doc": "Immutable source content identifier."})
    family_id: str = field(
        metadata={"doc": "Stable prompt or deterministic family ID."}
    )
    family_schema_version: str = field(
        metadata={"doc": "Output schema version for this family."}
    )
    processing_version: str = field(
        metadata={"doc": "Producer processing-version compatibility key."}
    )
    output_payload: Any = field(
        metadata={"doc": "JSON-serializable family output retained outside logs."}
    )
    system_prompt_hash: str = field(
        default="",
        metadata={"doc": "Rendered system-prompt SHA-256 when model-backed."},
    )
    user_prompt_hash: str = field(
        default="", metadata={"doc": "Rendered user-prompt SHA-256 when model-backed."}
    )
    prompt_policy_version: str = field(
        default="", metadata={"doc": "Prompt-policy compatibility fingerprint."}
    )
    model_name: str = field(
        default="", metadata={"doc": "Resolved provider model when model-backed."}
    )
    routing_policy_version: str = field(
        default="", metadata={"doc": "Model-routing compatibility fingerprint."}
    )
    validator_version: str = field(
        default="",
        metadata={
            "doc": "Validator compatibility fingerprint when this family is a validation result."
        },
    )
    direct_dependency_artifact_ids: list[str] = field(
        default_factory=list,
        metadata={"doc": "Direct retained lineage dependencies only."},
    )
    direct_dependency_hashes: dict[str, str] = field(
        default_factory=dict,
        metadata={"doc": "Verified SHA-256 digest keyed by dependency artifact ID."},
    )
    evidence_set_hash: str = field(
        default="", metadata={"doc": "Canonical evidence-set SHA-256 when applicable."}
    )
    validation_status: str = field(
        default="not_applicable",
        metadata={"doc": "Family validation result required for planner reuse."},
    )


@dataclass(frozen=True)
class PromptFamilyMaterialization:
    """Immutable, independently auditable retained family materialization."""

    schema_version: str = field(
        metadata={"doc": "Prompt-family materialization response schema version."}
    )
    family_id: str = field(
        metadata={"doc": "Stable prompt or deterministic family ID."}
    )
    family_schema_version: str = field(
        metadata={"doc": "Family output schema version."}
    )
    processing_version: str = field(metadata={"doc": "Producer processing version."})
    system_prompt_hash: str = field(
        metadata={"doc": "System-prompt hash when applicable."}
    )
    user_prompt_hash: str = field(metadata={"doc": "User-prompt hash when applicable."})
    prompt_policy_version: str = field(metadata={"doc": "Prompt-policy fingerprint."})
    model_name: str = field(metadata={"doc": "Resolved model when applicable."})
    routing_policy_version: str = field(metadata={"doc": "Routing-policy fingerprint."})
    validator_version: str = field(
        metadata={"doc": "Validator compatibility fingerprint when applicable."}
    )
    direct_dependency_artifact_ids: list[str] = field(
        metadata={"doc": "Direct retained lineage dependencies."}
    )
    direct_dependency_hashes: dict[str, str] = field(
        metadata={"doc": "Verified digest by dependency artifact ID."}
    )
    evidence_set_hash: str = field(metadata={"doc": "Evidence-set SHA-256."})
    output_reference: str = field(
        metadata={"doc": "Canonical retained JSON output path."}
    )
    output_hash: str = field(metadata={"doc": "Verified retained output SHA-256."})
    validation_status: str = field(metadata={"doc": "Family validation outcome."})
    created_at_utc: str = field(metadata={"doc": "UTC creation timestamp."})
    superseded_materialization_reference: str = field(
        metadata={"doc": "Prior family lineage ID superseded by this record, if any."}
    )
    artifact_id: str = field(metadata={"doc": "Canonical generic lineage artifact ID."})


@dataclass(frozen=True)
class PromptFamilyMaterializationResponse:
    schema_version: str = field(
        metadata={"doc": "Prompt-family materialization response schema version."}
    )
    materialization: PromptFamilyMaterialization = field(
        metadata={"doc": "Persisted independently reusable family materialization."}
    )
    created: bool = field(
        metadata={"doc": "Whether the lineage record was newly created."}
    )
