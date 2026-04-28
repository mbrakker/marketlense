from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AnalysisFamilyStatus:
    schema_version: str = field(
        metadata={"doc": "Analysis family-status schema version."}
    )
    family: str = field(
        metadata={"doc": "Stable evidence-pack or artifact family name."}
    )
    source: str = field(
        metadata={"doc": "Family source namespace: evidence_pack or artifact."}
    )
    status: str = field(metadata={"doc": "Generation status: generated or abstained."})
    confidence_score: float = field(
        metadata={"doc": "Deterministic confidence score in the range 0.0-1.0."}
    )
    policy_action: str = field(
        metadata={"doc": "Policy outcome: keep, regenerate, or abstain."}
    )
    reason: str = field(
        default="",
        metadata={"doc": "Short machine-readable explanation for the current status."},
    )
