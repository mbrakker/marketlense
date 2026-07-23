from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

AdmissionOutcome = Literal[
    "admitted",
    "duplicate",
    "unsupported_document",
    "corrupt_source",
    "insufficient_content",
    "missing_source_identity",
    "policy_blocked",
    "budget_blocked",
    "quarantined",
]


@dataclass(frozen=True)
class AdmissionPreflightDecision:
    """One reproducible no-model source-admission decision."""

    schema_version: str = field(
        metadata={"doc": "Admission-decision contract schema version."}
    )
    preflight_version: str = field(
        metadata={"doc": "Version of the deterministic admission rules."}
    )
    outcome: AdmissionOutcome = field(
        metadata={"doc": "Typed admission outcome used to gate evidence generation."}
    )
    file_id: str = field(metadata={"doc": "Acquired source artifact identifier."})
    source_identity_id: str = field(
        metadata={"doc": "Verified immutable source-content identity."}
    )
    report_title: str = field(
        metadata={"doc": "Report title or stable file-ID fallback used for admission."}
    )
    publisher_id: str = field(
        metadata={"doc": "Publisher identity or explicit unattributed source sentinel."}
    )
    source_url: str = field(
        metadata={
            "doc": "Canonical internal source reference; never a public URL claim."
        }
    )
    source_url_classification: str = field(
        metadata={
            "doc": "Classification of source_url provenance and publication safety."
        }
    )
    media_type: str = field(
        metadata={"doc": "Normalized declared or inferred media type."}
    )
    source_artifact_path: str = field(
        metadata={"doc": "Canonical local artifact path inspected before model work."}
    )
    source_artifact_exists: bool = field(
        metadata={"doc": "Whether the retained local source artifact existed."}
    )
    structure_readable: bool = field(
        metadata={"doc": "Whether deterministic PDF structure validation passed."}
    )
    page_count: int = field(metadata={"doc": "Observed PDF page count when readable."})
    size_bytes: int = field(
        metadata={"doc": "Observed source size in bytes when available."}
    )
    sample_char_count: int = field(
        metadata={"doc": "Bounded deterministic extracted-text sample character count."}
    )
    sample_text_density: float = field(
        metadata={"doc": "Bounded deterministic text-density sample."}
    )
    duplicate_identity_match: str = field(
        metadata={
            "doc": "Exact content identity already admitted in this selection, if any."
        }
    )
    near_duplicate_title_match: str = field(
        metadata={
            "doc": (
                "Conservative normalized-title candidate; never alone blocks admission."
            )
        }
    )
    required_artifact_families: tuple[str, ...] = field(
        metadata={
            "doc": "Artifact families whose minimum evidence potential was checked."
        }
    )
    evidence_potential: str = field(
        metadata={
            "doc": "Sufficient, insufficient, or policy-blocked evidence potential."
        }
    )
    runtime_preflight_hash: str = field(
        metadata={
            "doc": "Non-sensitive canonical runtime/model-policy preflight identity."
        }
    )
    runtime_dependencies_ready: bool = field(
        metadata={
            "doc": "Whether required runtime dependencies passed the run preflight."
        }
    )
    model_policy_covered: bool = field(
        metadata={"doc": "Whether required model routes were covered before admission."}
    )
    estimated_provider_calls: int = field(
        metadata={"doc": "Deterministic minimum required-provider-call forecast."}
    )
    estimated_provider_tokens: int = field(
        metadata={"doc": "Deterministic minimum required-provider-token forecast."}
    )
    estimated_cost_usd: float = field(
        metadata={"doc": "Deterministic estimated cost in USD for required families."}
    )
    budget_decision: str = field(
        metadata={"doc": "Canonical budget forecast decision or not_configured."}
    )
    configuration_hash: str = field(
        metadata={"doc": "Resolved non-secret configuration identity."}
    )
    policy_hash: str = field(metadata={"doc": "Resolved admission policy identity."})
    decision_hash: str = field(
        metadata={
            "doc": "Stable SHA-256 over retained admission inputs and decision fields."
        }
    )


@dataclass(frozen=True)
class AdmissionPreflightResult:
    """The source and its typed admission decision."""

    schema_version: str = field(
        metadata={"doc": "Admission-preflight result schema version."}
    )
    admitted: bool = field(
        metadata={
            "doc": "Whether evidence generation and editorial model work may start."
        }
    )
    decision: AdmissionPreflightDecision = field(
        metadata={"doc": "Persistable deterministic admission evidence."}
    )
