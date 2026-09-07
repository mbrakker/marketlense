"""Versioned contracts for deterministic public editorial release quality."""

from __future__ import annotations

from dataclasses import dataclass, field

PUBLIC_EDITORIAL_QUALITY_SCHEMA_VERSION = "1.0"
PUBLIC_EDITORIAL_VALIDATOR_VERSION = "public-editorial-quality:v5"


@dataclass(frozen=True)
class PublicEditorialQualityIssue:
    """One deterministic public-copy finding with repair provenance."""

    report_id: str = field(metadata={"doc": "Owning report identifier."})
    rule_id: str = field(metadata={"doc": "Stable deterministic rule identifier."})
    severity: str = field(metadata={"doc": "error or warning."})
    affected_artifact: str = field(
        metadata={"doc": "Artifact family that contains the public field."}
    )
    affected_field: str = field(metadata={"doc": "Stable field path."})
    evidence_ids: list[str] = field(
        default_factory=list,
        metadata={"doc": "Retained evidence identifiers relevant to the field."},
    )
    explanation: str = field(
        default="", metadata={"doc": "Deterministic, non-public finding explanation."}
    )
    repair_eligible: bool = field(
        default=False,
        metadata={"doc": "Whether scoped regeneration has sufficient grounding."},
    )
    repair_status: str = field(
        default="not_eligible",
        metadata={"doc": "not_requested, abstained, or not_eligible."},
    )
    repair_target: str = field(
        default="", metadata={"doc": "Existing targeted-regeneration family, if any."}
    )
    public_item_id: str = field(
        default="",
        metadata={
            "doc": "Stable atomic public-item identifier for diagnosis and repair routing."
        },
    )
    hard_fail_class: str = field(
        default="",
        metadata={
            "doc": "Unwaivable source-fidelity failure class, or empty for quality-only findings."
        },
    )
    validator_version: str = field(
        default=PUBLIC_EDITORIAL_VALIDATOR_VERSION,
        metadata={"doc": "Validator compatibility version."},
    )
    schema_version: str = field(
        default=PUBLIC_EDITORIAL_QUALITY_SCHEMA_VERSION,
        metadata={"doc": "Public-editorial issue schema version."},
    )


@dataclass(frozen=True)
class PublicEditorialQualityMeasurement:
    """A non-blocking, deterministic editorial quality measurement."""

    rule_id: str = field(metadata={"doc": "Stable advisory measurement identifier."})
    value: float = field(metadata={"doc": "Measured value."})
    unit: str = field(metadata={"doc": "Measurement unit."})
    explanation: str = field(metadata={"doc": "Deterministic interpretation."})
    schema_version: str = field(
        default=PUBLIC_EDITORIAL_QUALITY_SCHEMA_VERSION,
        metadata={"doc": "Measurement schema version."},
    )


@dataclass(frozen=True)
class PublicEditorialQualityItem:
    """One identifiable public surface retained for atomic fidelity assessment."""

    item_id: str = field(metadata={"doc": "Stable atomic public-item identifier."})
    artifact: str = field(metadata={"doc": "Owning artifact family."})
    field_path: str = field(metadata={"doc": "Stable public field path."})
    evidence_ids: list[str] = field(
        default_factory=list,
        metadata={"doc": "Linked retained evidence identifiers."},
    )
    repair_target: str = field(
        default="", metadata={"doc": "Smallest supported repair target."}
    )
    schema_version: str = field(
        default=PUBLIC_EDITORIAL_QUALITY_SCHEMA_VERSION,
        metadata={"doc": "Public item schema version."},
    )


@dataclass(frozen=True)
class PublicEditorialQualityReport:
    """Persisted release-gate result; never rendered to the public site."""

    report_id: str = field(metadata={"doc": "Owning report identifier."})
    status: str = field(metadata={"doc": "pass or fail across enabled blockers."})
    issues: list[PublicEditorialQualityIssue] = field(
        default_factory=list,
        metadata={"doc": "Deterministic blocker and warning findings."},
    )
    measurements: list[PublicEditorialQualityMeasurement] = field(
        default_factory=list,
        metadata={"doc": "Non-blocking editorial measurements."},
    )
    disabled_rule_waivers: dict[str, str] = field(
        default_factory=dict,
        metadata={"doc": "Explicit release waivers for disabled rules."},
    )
    items: list[PublicEditorialQualityItem] = field(
        default_factory=list,
        metadata={"doc": "Enumerated material public surfaces assessed for fidelity."},
    )
    publishable: bool = field(
        default=False,
        metadata={
            "doc": "False whenever an unresolved hard source-fidelity failure exists."
        },
    )
    hard_fail_count: int = field(
        default=0,
        metadata={"doc": "Count of unresolved unwaivable source-fidelity failures."},
    )
    validator_version: str = field(
        default=PUBLIC_EDITORIAL_VALIDATOR_VERSION,
        metadata={"doc": "Validator compatibility version."},
    )
    schema_version: str = field(
        default=PUBLIC_EDITORIAL_QUALITY_SCHEMA_VERSION,
        metadata={"doc": "Public-editorial report schema version."},
    )
