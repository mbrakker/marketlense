from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

RetryDecisionAction = Literal["retry", "defer", "abort", "user_action_required"]


@dataclass(frozen=True)
class RetryDecision:
    schema_version: str = field(
        metadata={"doc": "Retry decision contract schema version."}
    )
    step_name: str = field(
        metadata={"doc": "Owning orchestrator step for this retry decision."}
    )
    action: RetryDecisionAction = field(
        metadata={
            "doc": "Control decision: retry, defer, abort, or user_action_required."
        }
    )
    attempt: int = field(
        metadata={"doc": "One-based attempt number that produced this decision."}
    )
    max_attempts: int = field(
        metadata={"doc": "Maximum attempts allowed by the active retry policy."}
    )
    delay_seconds: float = field(
        metadata={"doc": "Delay before the next action, zero when not applicable."}
    )
    reason: str = field(
        metadata={"doc": "Stable machine-readable reason for the decision."}
    )
    next_action: str = field(
        metadata={"doc": "Operator or orchestrator action implied by the decision."}
    )
    error_code: str = field(
        metadata={"doc": "Typed error code that produced the decision."}
    )
    error_retryable: bool = field(
        metadata={"doc": "Retryability flag from the error taxonomy."}
    )
    error_severity: str = field(metadata={"doc": "Severity from the error taxonomy."})
