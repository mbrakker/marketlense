"""Typed retained claim-validation contracts for publish-readiness gates."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

CLAIM_VALIDATION_SCHEMA_VERSION = "1.0"
ClaimKind = Literal["numeric", "quotation", "descriptive", "causal", "interpretive"]
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
    text_hash: str = field(metadata={"doc": "SHA-256 of claim text."})
    kind: ClaimKind = field(metadata={"doc": "Deterministic claim taxonomy."})
    factual: bool = field(
        metadata={"doc": "Whether unsupported status blocks readiness."}
    )
    evidence_references: list[ClaimEvidenceReference] = field(default_factory=list)


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
    reasons: list[str] = field(default_factory=list)
    semantic_validator_used: bool = field(default=False)
    semantic_execution_identity: str = field(default="")


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
