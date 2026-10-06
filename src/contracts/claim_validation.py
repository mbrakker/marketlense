"""Typed contracts for deterministic and semantic retained-claim validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from src.contracts.protected_facts import ProtectedFactComparison

CLAIM_VALIDATION_SCHEMA_VERSION = "1.4"
CLAIM_VALIDATION_VALIDATOR_VERSION = "retained_claim_validation:v2"
CLAIM_GROUNDING_VALIDATOR_VERSION = "grounding_validation_output:1.5"
ClaimKind = Literal["numeric", "quotation", "descriptive", "causal", "interpretive"]
ClaimSemanticOutcome = Literal["entailed", "contradicted", "not_established"]
ClaimValidationStatus = Literal[
    "supported", "unsupported", "unresolved", "not_applicable"
]


@dataclass(frozen=True)
class ClaimEvidenceReference:
    schema_version: str = field(metadata={"doc": "Claim evidence-reference schema."})
    evidence_id: str = field(metadata={"doc": "Internal retained evidence identifier."})
    source_pack: str = field(
        default="", metadata={"doc": "Owning retained evidence pack."}
    )
    page: int | None = field(
        default=None, metadata={"doc": "Source page when retained."}
    )
    text_hash: str = field(
        default="", metadata={"doc": "Hash of bounded retained evidence text."}
    )


@dataclass(frozen=True)
class ClaimCandidate:
    schema_version: str = field(metadata={"doc": "Claim candidate schema."})
    claim_id: str = field(metadata={"doc": "Stable local validation identifier."})
    source_family: str = field(
        metadata={"doc": "Artifact family where claim was found."}
    )
    text: str = field(metadata={"doc": "Exact retained claim text."})
    text_hash: str = field(metadata={"doc": "SHA-256 of claim text."})
    kind: ClaimKind = field(metadata={"doc": "Deterministic claim taxonomy."})
    factual: bool = field(
        metadata={"doc": "Whether unsupported status blocks readiness."}
    )
    evidence_references: list[ClaimEvidenceReference] = field(default_factory=list)
    affected_section: str = field(
        default="",
        metadata={"doc": "Stable artifact field containing this retained claim."},
    )
    entity_id: str = field(
        default="",
        metadata={"doc": "Stable public item identity when the claim belongs to one."},
    )
    provenance_hash: str = field(
        default="",
        metadata={
            "doc": "Hash of retained source-span and evidence-provenance metadata."
        },
    )


@dataclass(frozen=True)
class ClaimSemanticInput:
    schema_version: str = field(metadata={"doc": "Semantic batch input schema."})
    candidate: ClaimCandidate = field(metadata={"doc": "Unresolved factual claim."})
    evidence_texts: list[str] = field(
        metadata={"doc": "Exact texts for the claim's linked evidence IDs."}
    )
    evidence_hash: str = field(
        metadata={"doc": "Hash of ordered linked evidence IDs and text hashes."}
    )
    source_identity: str = field(
        default="", metadata={"doc": "Current source identity when available."}
    )


@dataclass(frozen=True)
class ClaimSemanticValidationIdentity:
    schema_version: str = field(metadata={"doc": "Semantic result identity schema."})
    claim_id: str = field(metadata={"doc": "Stable retained claim identifier."})
    claim_text_hash: str = field(metadata={"doc": "Exact retained claim hash."})
    evidence_ids: list[str] = field(
        metadata={"doc": "Exact retained evidence IDs used for this claim."}
    )
    evidence_hash: str = field(
        metadata={"doc": "Hash of linked evidence IDs and retained text hashes."}
    )
    source_identity: str = field(
        metadata={"doc": "Immutable source identity when available, otherwise empty."}
    )
    prompt_family: str = field(metadata={"doc": "Existing grounding prompt family."})
    prompt_content_hash: str = field(
        metadata={"doc": "Rendered prompt content identity."}
    )
    execution_identity: str = field(metadata={"doc": "Prompt execution identity."})
    validator_version: str = field(
        metadata={"doc": "Grounding output validator version."}
    )
    model_provider: str = field(metadata={"doc": "Resolved model provider."})
    model_name: str = field(metadata={"doc": "Resolved model identity."})
    configuration_policy_identity: str = field(
        metadata={"doc": "Relevant model routing/configuration policy hash."}
    )
    relevant_input_hash: str = field(
        metadata={"doc": "Full report-level grounding input hash."}
    )
    retrieval_identity: str = field(
        default="",
        metadata={
            "doc": "Identity of retrieval mode and any verified vector-store content."
        },
    )


@dataclass(frozen=True)
class ClaimSemanticGroundingResult:
    schema_version: str = field(metadata={"doc": "Semantic result schema."})
    outcome: ClaimSemanticOutcome = field(
        metadata={"doc": "Semantic entailment result."}
    )
    reason: str = field(metadata={"doc": "Semantic grounding reason."})
    identity: ClaimSemanticValidationIdentity = field(
        metadata={"doc": "Identity binding the outcome to current claim inputs."}
    )
    protected_facts: ProtectedFactComparison | None = field(
        default=None,
        metadata={"doc": "Semantic protected-dimension comparison for diagnostics."},
    )
    disagreement: str = field(
        default="",
        metadata={"doc": "Explicit inconsistency within semantic output, if any."},
    )


@dataclass(frozen=True)
class ClaimValidationCheck:
    schema_version: str = field(
        metadata={"doc": "Deterministic validation check schema."}
    )
    name: str = field(metadata={"doc": "Stable check name."})
    status: str = field(metadata={"doc": "passed, failed, or not_applicable."})
    reason: str = field(default="", metadata={"doc": "Bounded stable reason code."})


@dataclass(frozen=True)
class ClaimValidationResult:
    schema_version: str = field(metadata={"doc": "Claim validation result schema."})
    candidate: ClaimCandidate = field(metadata={"doc": "Validated claim candidate."})
    checks: list[ClaimValidationCheck] = field(default_factory=list)
    status: ClaimValidationStatus = field(default="unresolved")
    deterministic_status: ClaimValidationStatus = field(default="unresolved")
    reasons: list[str] = field(default_factory=list)
    protected_facts: ProtectedFactComparison | None = field(default=None)
    semantic_outcome: ClaimSemanticOutcome | None = field(default=None)
    semantic_reason: str = field(default="")
    semantic_protected_facts: ProtectedFactComparison | None = field(default=None)
    semantic_identity: ClaimSemanticValidationIdentity | None = field(default=None)
    semantic_disagreement: str = field(default="")
    semantic_validator_used: bool = field(default=False)
    semantic_execution_identity: str = field(default="")


@dataclass(frozen=True)
class ClaimValidationExecutionIdentity:
    """Validation-stage identities checked before final artifact materialization."""

    schema_version: str = field(
        metadata={"doc": "Claim validation execution identity schema."}
    )
    report_id: str = field(metadata={"doc": "Report whose claims were validated."})
    source_id: str = field(metadata={"doc": "Source identity validated."})
    source_md5: str = field(metadata={"doc": "Source MD5 validated, if available."})
    claim_validation_validator_version: str = field(
        metadata={"doc": "Deterministic retained-claim validator identity."}
    )
    grounding_validator_version: str = field(
        metadata={"doc": "Semantic grounding validator identity."}
    )
    configuration_hash: str = field(
        metadata={"doc": "Resolved configuration identity used during validation."}
    )
    policy_hash: str = field(
        metadata={"doc": "Resolved policy identity used during validation."}
    )


@dataclass(frozen=True)
class ClaimValidationLineage:
    """Current final artifact and execution identities for a retained package."""

    schema_version: str = field(metadata={"doc": "Claim lineage schema version."})
    report_id: str = field(
        metadata={"doc": "Canonical report owning the final package."}
    )
    final_artifact_hash: str = field(
        metadata={"doc": "SHA-256 of the exact final retained artifact set."}
    )
    publication_projection_hash: str = field(
        metadata={"doc": "Hash of the final public publication projection."}
    )
    evidence_pack_hash: str = field(
        metadata={"doc": "Hash of the exact evidence packs used for grounding."}
    )
    claim_validation_validator_version: str = field(
        metadata={"doc": "Deterministic retained-claim validator identity."}
    )
    grounding_validator_version: str = field(
        metadata={"doc": "Semantic grounding output validator identity."}
    )
    source_id: str = field(
        default="", metadata={"doc": "Current immutable source identity, if known."}
    )
    source_md5: str = field(
        default="", metadata={"doc": "Current source MD5, if available."}
    )
    semantic_execution_identities: list[str] = field(
        default_factory=list,
        metadata={"doc": "Exact report-level grounding executions used."},
    )
    semantic_prompt_content_hashes: list[str] = field(
        default_factory=list,
        metadata={"doc": "Rendered grounding prompt hashes used by semantic checks."},
    )
    semantic_model_identities: list[str] = field(
        default_factory=list,
        metadata={"doc": "Resolved provider/model identities used by semantic checks."},
    )
    configuration_hash: str = field(
        default="", metadata={"doc": "Current resolved configuration identity."}
    )
    policy_hash: str = field(
        default="", metadata={"doc": "Current resolved policy identity."}
    )


@dataclass(frozen=True)
class ClaimValidationPackage:
    schema_version: str = field(metadata={"doc": "Claim validation package schema."})
    artifact_hash: str = field(
        metadata={"doc": "Hash of validated retained artifact input."}
    )
    package_hash: str = field(metadata={"doc": "Canonical package identity."})
    results: list[ClaimValidationResult] = field(default_factory=list)
    readiness_status: str = field(default="not_publishable")
    unsupported_factual_count: int = field(default=0)
    unresolved_factual_count: int = field(default=0)
    deterministic_pass_count: int = field(default=0)
    semantic_validation_count: int = field(default=0)
    semantic_execution_identities: list[str] = field(default_factory=list)
    validation_identity: ClaimValidationExecutionIdentity | None = field(
        default=None,
        metadata={"doc": "Source and policy identity of validation-stage results."},
    )
    lineage: ClaimValidationLineage | None = field(
        default=None,
        metadata={"doc": "Final retained artifact and grounding execution lineage."},
    )
