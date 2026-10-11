from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from src.contracts.workflow_control import ModelCallReplayBundle

ModelCallReplayComparisonClassification = Literal[
    "equivalent",
    "compatible_but_changed",
    "incomplete",
    "malformed",
    "materially_regressed",
    "incompatible",
]


@dataclass(frozen=True)
class ModelCallReplayBundleComparisonRequest:
    """Read-only request to compare two retained model-call replay bundles."""

    schema_version: str = field(metadata={"doc": "Comparison request schema version."})
    artifact_family: str = field(
        metadata={"doc": "Expected stable output artifact family."}
    )
    baseline_bundle: ModelCallReplayBundle | None = field(
        metadata={"doc": "Baseline bundle, or None when parsing failed."}
    )
    candidate_bundle: ModelCallReplayBundle | None = field(
        metadata={"doc": "Candidate bundle, or None when parsing failed."}
    )
    baseline_bundle_sha256: str = field(
        metadata={"doc": "SHA-256 of the exact retained baseline bundle bytes."}
    )
    candidate_bundle_sha256: str = field(
        metadata={"doc": "SHA-256 of the exact retained candidate bundle bytes."}
    )
    input_diagnostic_codes: tuple[str, ...] = field(
        default=(),
        metadata={"doc": "Bounded parse diagnostics from the read-only file adapter."},
    )


@dataclass(frozen=True)
class ModelCallReplayBundleComparisonResponse:
    """Bounded comparison result containing identity field names, never values."""

    schema_version: str = field(metadata={"doc": "Comparison response schema version."})
    artifact_family: str = field(
        metadata={"doc": "Requested artifact family used for this comparison."}
    )
    baseline_bundle_sha256: str = field(
        metadata={"doc": "SHA-256 reference to the retained baseline bundle."}
    )
    candidate_bundle_sha256: str = field(
        metadata={"doc": "SHA-256 reference to the retained candidate bundle."}
    )
    classification: ModelCallReplayComparisonClassification = field(
        metadata={"doc": "Deterministic comparison outcome."}
    )
    cohort_compatibility: Literal["compatible", "incompatible", "unknown"] = field(
        metadata={"doc": "Whether regression evidence is comparable."}
    )
    compared_fields: tuple[str, ...] = field(
        default=(), metadata={"doc": "Safe identity field names compared."}
    )
    changed_fields: tuple[str, ...] = field(
        default=(), metadata={"doc": "Safe identity field names that changed."}
    )
    missing_fields: tuple[str, ...] = field(
        default=(), metadata={"doc": "Required identity field names not retained."}
    )
    diagnostic_codes: tuple[str, ...] = field(
        default=(), metadata={"doc": "Bounded stable diagnostic codes."}
    )
    regression_evidence: tuple[str, ...] = field(
        default=(),
        metadata={"doc": "Comparable evidence codes supporting a regression."},
    )
