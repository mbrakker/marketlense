"""Versioned source-bound hypotheses for visual assessment."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ProvisionalFinding:
    finding: dict[str, Any] = field(
        metadata={"doc": "Unverified discovery hypothesis."}
    )
    source_references: list[dict[str, Any]] = field(
        metadata={"doc": "Physical-page source identities and text hashes."}
    )
    schema_version: str = field(
        default="1.0", metadata={"doc": "Finding handoff schema version."}
    )


@dataclass(frozen=True)
class ProvisionalEvidence:
    schema_version: str = field(metadata={"doc": "Handoff schema version."})
    source_identity: str = field(
        metadata={"doc": "Identity including source PDF hash."}
    )
    findings: list[ProvisionalFinding] = field(
        metadata={"doc": "Unverified findings, not factual authority."}
    )
