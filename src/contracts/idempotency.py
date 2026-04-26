from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class OrchestratorIdempotencyGetRequest:
    schema_version: str = field(
        metadata={"doc": "Orchestrator idempotency get request schema version."}
    )
    db_path: str = field(
        metadata={"doc": "SQLite database path used to persist idempotency outcomes."}
    )
    scope: str = field(
        metadata={"doc": "Stable orchestrator step scope, for example publish_html."}
    )
    idempotency_key: str = field(
        metadata={"doc": "Stable logical key for the side-effecting step."}
    )
    input_checksum: str = field(
        metadata={"doc": "Deterministic checksum of the step input payload."}
    )


@dataclass(frozen=True)
class OrchestratorIdempotencyRecordRequest:
    schema_version: str = field(
        metadata={"doc": "Orchestrator idempotency record request schema version."}
    )
    db_path: str = field(
        metadata={"doc": "SQLite database path used to persist idempotency outcomes."}
    )
    scope: str = field(
        metadata={"doc": "Stable orchestrator step scope, for example publish_html."}
    )
    idempotency_key: str = field(
        metadata={"doc": "Stable logical key for the side-effecting step."}
    )
    input_checksum: str = field(
        metadata={"doc": "Deterministic checksum of the step input payload."}
    )
    outcome_payload: Dict[str, Any] = field(
        metadata={"doc": "Serialized step outcome returned when the side effect completed."}
    )
    artifact_references: Dict[str, Any] = field(
        default_factory=dict,
        metadata={"doc": "Artifact identifiers or paths created by the completed step."},
    )


@dataclass(frozen=True)
class OrchestratorIdempotencyRecord:
    schema_version: str = field(
        metadata={"doc": "Persisted orchestrator idempotency record schema version."}
    )
    scope: str = field(metadata={"doc": "Stable orchestrator step scope."})
    idempotency_key: str = field(
        metadata={"doc": "Stable logical key for the side-effecting step."}
    )
    input_checksum: str = field(
        metadata={"doc": "Deterministic checksum of the step input payload."}
    )
    outcome_payload: Dict[str, Any] = field(
        metadata={"doc": "Serialized step outcome returned when the side effect completed."}
    )
    recorded_at_utc: str = field(
        metadata={"doc": "UTC timestamp when this idempotency record was last written."}
    )
    artifact_references: Dict[str, Any] = field(
        default_factory=dict,
        metadata={"doc": "Artifact identifiers or paths created by the completed step."},
    )


@dataclass(frozen=True)
class OrchestratorIdempotencyLookupResponse:
    schema_version: str = field(
        metadata={"doc": "Orchestrator idempotency lookup response schema version."}
    )
    found: bool = field(
        metadata={"doc": "Whether a completed idempotency outcome was already stored."}
    )
    record: Optional[OrchestratorIdempotencyRecord] = field(
        default=None,
        metadata={"doc": "Stored idempotency record when one exists."},
    )
