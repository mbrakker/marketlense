from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class RetryDecisionTelemetryRow:
    schema_version: str = field(metadata={"doc": "Retry telemetry row schema version."})
    step_name: str = field(metadata={"doc": "Step that emitted retry decisions."})
    error_code: str = field(metadata={"doc": "Error code that produced decisions."})
    publisher: str = field(metadata={"doc": "Publisher when present, otherwise empty."})
    workflow: str = field(metadata={"doc": "Workflow when present, otherwise empty."})
    action: str = field(metadata={"doc": "Retry decision action."})
    reason: str = field(metadata={"doc": "Retry decision reason."})
    decision_count: int = field(metadata={"doc": "Number of decisions in this group."})
    max_attempt: int = field(metadata={"doc": "Highest one-based attempt observed."})
    cumulative_delay_seconds: float = field(
        metadata={"doc": "Total retry/defer delay seconds in this group."}
    )
    successful_after_retry_count: int = field(
        metadata={"doc": "Number of runs that completed successfully after retry."}
    )
    retry_exhaustion_count: int = field(
        metadata={"doc": "Number of retry-exhaustion abort decisions."}
    )
    deferred_count: int = field(metadata={"doc": "Number of defer decisions."})
    user_action_required_count: int = field(
        metadata={"doc": "Number of user-action-required decisions."}
    )
    estimated_wasted_calls: int = field(
        metadata={"doc": "Estimated model/browser calls spent before final abort."}
    )
    estimated_avoided_calls: int = field(
        metadata={"doc": "Estimated calls avoided by preflight/user-action decisions."}
    )
    final_outcomes: dict[str, int] = field(
        metadata={"doc": "Final status counts observed after decisions."}
    )


@dataclass(frozen=True)
class RetryDecisionTelemetryReport:
    schema_version: str = field(
        metadata={"doc": "Retry telemetry report schema version."}
    )
    decision_count: int = field(metadata={"doc": "Total retry decisions observed."})
    retry_count: int = field(metadata={"doc": "Total retry actions observed."})
    deferred_count: int = field(metadata={"doc": "Total defer actions observed."})
    user_action_required_count: int = field(
        metadata={"doc": "Total user-action-required actions observed."}
    )
    retry_exhaustion_count: int = field(
        metadata={"doc": "Total retry-exhaustion aborts observed."}
    )
    successful_after_retry_count: int = field(
        metadata={"doc": "Runs or groups that completed successfully after retry."}
    )
    successful_after_retry_rate: float = field(
        metadata={"doc": "Successful-after-retry count divided by retry count."}
    )
    retry_exhaustion_rate: float = field(
        metadata={"doc": "Retry-exhaustion count divided by total decisions."}
    )
    cumulative_retry_delay_seconds: float = field(
        metadata={"doc": "Total delay seconds across retry/defer decisions."}
    )
    estimated_wasted_calls: int = field(
        metadata={"doc": "Estimated model/browser calls wasted before exhaustion."}
    )
    estimated_avoided_calls: int = field(
        metadata={"doc": "Estimated model/browser calls avoided by early user action."}
    )
    rows: list[RetryDecisionTelemetryRow] = field(
        metadata={"doc": "Grouped retry telemetry rows in deterministic order."}
    )

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=True, indent=2, sort_keys=True)
