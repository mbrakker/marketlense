from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict

from src.contracts.run_context import RunContext


@dataclass(frozen=True)
class ArtifactRenderTask:
    schema_version: str = field(
        metadata={"doc": "Artifact render task contract schema version."}
    )
    step_name: str = field(
        metadata={"doc": "Stable artifact step identifier used for results and logs."}
    )
    namespace: str = field(
        metadata={"doc": "Prompt namespace used to render this artifact step."}
    )
    variables: Dict[str, Any] = field(
        metadata={"doc": "Prompt variables for the artifact step."}
    )
    ctx: RunContext = field(
        metadata={"doc": "Run context scoped to the artifact step execution."}
    )


@dataclass(frozen=True)
class EditorialCoverageChallengeRequest:
    """Source-bound inputs for independently reviewing an alleged coverage gap."""

    schema_version: str = field(metadata={"doc": "Challenge request version."})
    original_assessment: Dict[str, Any] = field(
        metadata={"doc": "Unmodified, source-bound independent coverage assessment."}
    )
    editorial_plan: Dict[str, Any] = field(metadata={"doc": "Current editorial plan."})
    final_insights: list[Dict[str, Any]] = field(
        metadata={"doc": "Exact final insight roster being reviewed."}
    )
    candidate_insights: list[Dict[str, Any]] = field(
        metadata={"doc": "Admitted candidates supplying canonical bindings."}
    )
    verified_facts: list[Dict[str, Any]] = field(
        metadata={"doc": "Canonical verified facts underlying the review."}
    )
    original_essential_obligations: list[Dict[str, Any]] = field(
        metadata={"doc": "Original essential obligations retained across replanning."}
    )
    require_original_obligation_assessment: bool = field(
        metadata={"doc": "Whether original obligation verdicts are mandatory."}
    )
    ctx: RunContext = field(metadata={"doc": "Source- and run-bound context."})


@dataclass(frozen=True)
class EditorialCoverageChallengeResponse:
    """Model-owned verdicts, checked against the source-bound request."""

    schema_version: str = field(metadata={"doc": "Challenge response version."})
    verdicts: list[Dict[str, Any]] = field(
        metadata={"doc": "Independent semantic verdict for each original gap."}
    )
    request_id: str = field(default="", metadata={"doc": "Provider request identity."})
    prompt_identity: Dict[str, Any] = field(
        default_factory=dict,
        metadata={"doc": "Non-sensitive producing prompt and model identity."},
    )
