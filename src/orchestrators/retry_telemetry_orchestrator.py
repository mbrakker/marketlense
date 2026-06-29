from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Iterable

from src.contracts.retry_telemetry import (
    RetryDecisionTelemetryReport,
    RetryDecisionTelemetryRow,
)

_SUCCESS_STATUSES = {
    "processed",
    "success",
    "succeeded",
    "published",
    "completed",
    "ok",
}


@dataclass
class _DecisionEvent:
    run_id: str
    step_name: str
    error_code: str
    publisher: str
    workflow: str
    action: str
    reason: str
    attempt: int
    delay_seconds: float


def build_retry_decision_telemetry(
    payloads: Iterable[dict[str, Any]],
) -> RetryDecisionTelemetryReport:
    events = list(payloads)
    decisions: list[_DecisionEvent] = []
    for event in events:
        decision = _coerce_decision_event(event)
        if decision is not None:
            decisions.append(decision)
    final_outcomes = _final_outcomes(events)

    grouped: dict[tuple[str, str, str, str, str, str], list[_DecisionEvent]] = (
        defaultdict(list)
    )
    for decision in decisions:
        grouped[
            (
                decision.step_name,
                decision.error_code,
                decision.publisher,
                decision.workflow,
                decision.action,
                decision.reason,
            )
        ].append(decision)

    rows: list[RetryDecisionTelemetryRow] = []
    for key in sorted(grouped):
        step, error_code, publisher, workflow, action, reason = key
        group = grouped[key]
        outcomes = _matching_outcomes(final_outcomes, group)
        successful = _successful_after_retry(group, outcomes)
        retry_exhaustions = sum(
            1
            for item in group
            if item.action == "abort" and item.reason == "retry_attempts_exhausted"
        )
        user_actions = sum(1 for item in group if item.action == "user_action_required")
        deferred = sum(1 for item in group if item.action == "defer")
        wasted_calls = retry_exhaustions
        rows.append(
            RetryDecisionTelemetryRow(
                schema_version="1.0",
                step_name=step,
                error_code=error_code,
                publisher=publisher,
                workflow=workflow,
                action=action,
                reason=reason,
                decision_count=len(group),
                max_attempt=max(item.attempt for item in group),
                cumulative_delay_seconds=round(
                    sum(item.delay_seconds for item in group), 6
                ),
                successful_after_retry_count=successful,
                retry_exhaustion_count=retry_exhaustions,
                deferred_count=deferred,
                user_action_required_count=user_actions,
                estimated_wasted_calls=wasted_calls,
                estimated_avoided_calls=user_actions,
                final_outcomes=outcomes,
            )
        )

    rows = sorted(
        rows, key=lambda row: (_action_rank(row.action), row.step_name, row.error_code)
    )
    decision_count = len(decisions)
    retry_count = sum(1 for item in decisions if item.action == "retry")
    deferred_count = sum(1 for item in decisions if item.action == "defer")
    user_action_count = sum(
        1 for item in decisions if item.action == "user_action_required"
    )
    retry_exhaustion_count = sum(
        1
        for item in decisions
        if item.action == "abort" and item.reason == "retry_attempts_exhausted"
    )
    successful_after_retry_count = sum(row.successful_after_retry_count for row in rows)
    return RetryDecisionTelemetryReport(
        schema_version="1.0",
        decision_count=decision_count,
        retry_count=retry_count,
        deferred_count=deferred_count,
        user_action_required_count=user_action_count,
        retry_exhaustion_count=retry_exhaustion_count,
        successful_after_retry_count=successful_after_retry_count,
        successful_after_retry_rate=(
            round(successful_after_retry_count / retry_count, 6) if retry_count else 0.0
        ),
        retry_exhaustion_rate=(
            round(retry_exhaustion_count / decision_count, 6) if decision_count else 0.0
        ),
        cumulative_retry_delay_seconds=round(
            sum(item.delay_seconds for item in decisions), 6
        ),
        estimated_wasted_calls=sum(row.estimated_wasted_calls for row in rows),
        estimated_avoided_calls=sum(row.estimated_avoided_calls for row in rows),
        rows=rows,
    )


def _coerce_decision_event(event: dict[str, Any]) -> _DecisionEvent | None:
    raw_fields = event.get("fields")
    fields: dict[str, Any] = raw_fields if isinstance(raw_fields, dict) else {}
    action = str(fields.get("decision") or "").strip()
    reason = str(fields.get("reason") or "").strip()
    if not action or not reason:
        return None
    step_name = str(fields.get("step") or fields.get("step_name") or "").strip()
    if not step_name:
        return None
    return _DecisionEvent(
        run_id=str(event.get("run_id") or "").strip(),
        step_name=step_name,
        error_code=str(fields.get("error_code") or fields.get("code") or "").strip(),
        publisher=str(fields.get("publisher") or "").strip(),
        workflow=str(fields.get("workflow") or "").strip(),
        action=action,
        reason=reason,
        attempt=_int(fields.get("decision_attempt") or fields.get("attempt") or 0),
        delay_seconds=_float(fields.get("delay_seconds") or 0.0),
    )


def _final_outcomes(
    events: list[dict[str, Any]],
) -> dict[tuple[str, str, str, str], dict[str, int]]:
    outcomes: dict[tuple[str, str, str, str], dict[str, int]] = defaultdict(
        lambda: defaultdict(int)
    )
    for event in events:
        raw_fields = event.get("fields")
        fields: dict[str, Any] = raw_fields if isinstance(raw_fields, dict) else {}
        step_name = str(fields.get("step") or fields.get("step_name") or "").strip()
        if not step_name:
            continue
        status = str(fields.get("status") or fields.get("final_outcome") or "").strip()
        if not status:
            continue
        key = (
            str(event.get("run_id") or "").strip(),
            step_name,
            str(fields.get("publisher") or "").strip(),
            str(fields.get("workflow") or "").strip(),
        )
        outcomes[key][status] += 1
    return {key: dict(value) for key, value in outcomes.items()}


def _matching_outcomes(
    final_outcomes: dict[tuple[str, str, str, str], dict[str, int]],
    group: list[_DecisionEvent],
) -> dict[str, int]:
    merged: dict[str, int] = defaultdict(int)
    for decision in group:
        key = (
            decision.run_id,
            decision.step_name,
            decision.publisher,
            decision.workflow,
        )
        for status, count in final_outcomes.get(key, {}).items():
            merged[status] += count
    return dict(sorted(merged.items()))


def _successful_after_retry(
    group: list[_DecisionEvent],
    outcomes: dict[str, int],
) -> int:
    if not any(item.action == "retry" for item in group):
        return 0
    return sum(
        count for status, count in outcomes.items() if status in _SUCCESS_STATUSES
    )


def _action_rank(action: str) -> int:
    order = {"defer": 0, "retry": 1, "user_action_required": 2, "abort": 3}
    return order.get(action, 99)


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
