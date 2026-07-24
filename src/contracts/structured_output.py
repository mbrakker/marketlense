"""Versioned contracts for bounded model structured-output recovery."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class StructuredOutputExecutionRequest:
    schema_version: str = field(
        metadata={"doc": "Structured-output execution contract version."}
    )
    report_id: str = field(metadata={"doc": "Stable report identity."})
    artifact_family: str = field(
        metadata={"doc": "Stable model-produced report artifact family."}
    )
    schema_name: str = field(metadata={"doc": "Canonical JSON schema identity."})
    schema_root_key: str = field(
        default="", metadata={"doc": "Optional root property for a response fragment."}
    )
    provider: str = field(
        default="openai", metadata={"doc": "Provider used for attempt audit records."}
    )
    model: str = field(
        default="",
        metadata={"doc": "Resolved provider model for attempt audit records."},
    )
    allow_abstention: bool = field(
        default=False,
        metadata={"doc": "Whether a formal downstream abstention is permitted."},
    )
    terminal_failure_code: str = field(
        default="structured_output_recovery_exhausted",
        metadata={"doc": "Typed permanent failure code when recovery is exhausted."},
    )


@dataclass(frozen=True)
class StructuredOutputExecutionResult:
    schema_version: str = field(
        metadata={"doc": "Structured-output result contract version."}
    )
    payload: Any = field(metadata={"doc": "Schema-valid normalized output payload."})
    disposition: str = field(
        metadata={
            "doc": (
                "generated, deterministic_repair, model_repair, regeneration, "
                "or abstained."
            )
        }
    )
    attempts: int = field(
        metadata={"doc": "Provider attempts consumed, bounded at three."}
    )
    error_class: str = field(
        default="", metadata={"doc": "Last failed recovery classification, if any."}
    )
    model: str = field(
        default="", metadata={"doc": "Model that produced the accepted output."}
    )
    request_id: str = field(
        default="",
        metadata={"doc": "Provider request identifier for the accepted output."},
    )
