from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from src.contracts.remediation import (
    RemediationActionCode,
    RemediationArtifactReference,
    RemediationBudgetSummary,
    RemediationCheckpointReference,
    RemediationClaimRequest,
    RemediationExpiredLeaseReleaseRequest,
    RemediationIdempotencyKey,
    RemediationReaperRequest,
    RemediationReaperResponse,
    RemediationRecord,
    RemediationTransitionRequest,
    RemediationUpsertRequest,
)
from src.contracts.retry_decision import RetryDecision
from src.contracts.run_context import RunContext
from src.services import state_service
from src.utils.clock import utc_now_seconds_z
from src.utils.errors import AppError
from src.utils.logging import child_context, log_event

logger = logging.getLogger("market_lense.remediation_orchestrator")

_SIDE_EFFECTING_ACTIONS = {
    "retry_transient_service_call",
    "rerun_targeted_artifact_family",
    "retry_idempotent_publication",
    "revalidate_replaced_source",
}


def _utc_after(now_utc: str, seconds: int) -> str:
    if seconds <= 0:
        return now_utc
    value = now_utc[:-1] + "+00:00" if now_utc.endswith("Z") else now_utc
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        parsed = datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return (
        (parsed.astimezone(timezone.utc) + timedelta(seconds=seconds))
        .isoformat()
        .replace("+00:00", "Z")
    )


def _failure_code(error: Exception) -> str:
    return error.code if isinstance(error, AppError) else error.__class__.__name__


def _failure_diagnostics(error: Exception) -> dict[str, object]:
    if not isinstance(error, AppError):
        return {"error_type": error.__class__.__name__}
    return {
        "severity": error.severity,
        "retryable": error.retryable,
        "context_keys": sorted(str(key) for key in error.context),
    }


def _action_for_failure(
    *,
    workflow: str,
    error: Exception,
    decision: RetryDecision | None,
    checkpoint: RemediationCheckpointReference | None,
) -> tuple[RemediationActionCode, str, str]:
    code = _failure_code(error).lower()
    if not isinstance(error, AppError):
        return (
            "mark_terminal_blocker",
            "terminal",
            "Inspect the unexpected failure before retrying.",
        )
    if decision is not None and decision.action == "user_action_required":
        return "escalate_credentials", "operator_action_required", decision.next_action
    if any(
        token in code for token in ("credential", "api_key", "oauth", "token_missing")
    ):
        return (
            "escalate_credentials",
            "operator_action_required",
            "Provide or refresh credentials.",
        )
    if decision is not None and decision.action == "defer":
        return "defer_for_budget", "deferred", decision.next_action
    if code == "mail_report_not_arrived_yet":
        return (
            "poll_mailbox_delivery",
            "pending",
            "Wait for and poll the requested mailbox delivery.",
        )
    if "source" in code and any(
        token in code for token in ("stale", "replaced", "changed")
    ):
        return (
            "revalidate_replaced_source",
            "pending",
            "Verify the replacement source before retrying.",
        )
    if "artifact" in code and any(
        token in code for token in ("invalid", "missing", "validation")
    ):
        return (
            "rerun_targeted_artifact_family",
            "pending",
            "Rerun only the invalid artifact family.",
        )
    if (
        workflow in {"publish", "publishing"}
        and decision is not None
        and decision.action == "retry"
    ):
        return (
            "retry_idempotent_publication",
            "pending",
            "Retry publication only after idempotency verification.",
        )
    if checkpoint is not None and checkpoint.validation_status == "validated":
        return (
            "resume_valid_checkpoint",
            "pending",
            "Resume from the validated checkpoint.",
        )
    if error.retryable and (decision is None or decision.action == "retry"):
        return (
            "retry_transient_service_call",
            "pending",
            decision.next_action
            if decision is not None
            else "retry_after_operator_review",
        )
    return (
        "mark_terminal_blocker",
        "terminal",
        "Resolve the blocker before another workflow attempt.",
    )


def record_workflow_failure(
    *,
    state_db: str,
    workflow: str,
    stage: str,
    operation: str,
    error: Exception,
    ctx: RunContext,
    retry_decision: RetryDecision | None = None,
    workflow_run_id: str = "",
    input_checksum: str = "",
    report_id: str = "",
    source_id: str = "",
    publisher_id: str = "",
    checkpoint: RemediationCheckpointReference | None = None,
    reusable_artifacts: list[RemediationArtifactReference] | None = None,
    committed_side_effects: list[str] | None = None,
    idempotency_keys: list[RemediationIdempotencyKey] | None = None,
    budget: RemediationBudgetSummary | None = None,
) -> RemediationRecord | None:
    """Persist terminal workflow failure evidence without changing retry policy."""

    if not state_db.strip():
        return None
    now = utc_now_seconds_z()
    action, status, operator_action = _action_for_failure(
        workflow=workflow,
        error=error,
        decision=retry_decision,
        checkpoint=checkpoint,
    )
    code = _failure_code(error)
    fingerprint = {
        "workflow": workflow,
        "run_id": workflow_run_id or str(ctx.run_id),
        "stage": stage,
        "operation": operation,
        "input_checksum": input_checksum,
        "error_code": code,
        "report_id": report_id,
        "source_id": source_id,
        "publisher_id": publisher_id,
    }
    digest = hashlib.sha256(
        json.dumps(
            fingerprint, ensure_ascii=True, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    delay = max(0, int(retry_decision.delay_seconds)) if retry_decision else 0
    record = RemediationRecord(
        schema_version="1.0",
        remediation_id=f"rem_{digest[:32]}",
        dedupe_key=f"remediation:{digest}",
        workflow=workflow,
        run_id=workflow_run_id or str(ctx.run_id),
        task_id=str(ctx.task_id),
        span_id=ctx.span_id,
        report_id=report_id,
        source_id=source_id,
        publisher_id=publisher_id,
        input_checksum=input_checksum,
        failed_stage=stage,
        operation=operation,
        error_code=code,
        error_classification=(
            "typed_app_error" if isinstance(error, AppError) else "unknown"
        ),
        retry_decision=retry_decision,
        status=status,
        checkpoint=checkpoint,
        reusable_artifacts=list(reusable_artifacts or []),
        committed_side_effects=list(committed_side_effects or []),
        idempotency_keys=list(idempotency_keys or []),
        budget=budget or RemediationBudgetSummary(schema_version="1.0"),
        max_attempts=(retry_decision.max_attempts if retry_decision else 1),
        cooldown_seconds=delay,
        next_eligible_at_utc=_utc_after(now, delay),
        action_code=action,
        operator_next_action=operator_action,
        created_at_utc=now,
        updated_at_utc=now,
        diagnostics=_failure_diagnostics(error),
    )
    response = state_service.upsert_remediation_record(
        RemediationUpsertRequest(
            schema_version="1.0", state_db=state_db, record=record
        ),
        child_context(ctx, task_id="remediation:record_failure"),
    )
    return response.record


RemediationExecutor = Callable[[RemediationRecord, RunContext], str]
RemediationBudgetCheck = Callable[[RemediationRecord, RunContext], str]
RemediationCheckpointValidator = Callable[[RemediationRecord, RunContext], bool]
RemediationIdempotencyCheck = Callable[[RemediationRecord, RunContext], str]


@dataclass(frozen=True)
class RemediationReaperDependencies:
    """Explicit closed-action hooks; absent hooks fail closed to an operator."""

    resume_valid_checkpoint: RemediationExecutor | None = None
    retry_transient_service_call: RemediationExecutor | None = None
    rerun_targeted_artifact_family: RemediationExecutor | None = None
    revalidate_replaced_source: RemediationExecutor | None = None
    poll_mailbox_delivery: RemediationExecutor | None = None
    retry_idempotent_publication: RemediationExecutor | None = None
    budget_check: RemediationBudgetCheck | None = None
    checkpoint_validator: RemediationCheckpointValidator | None = None
    idempotency_check: RemediationIdempotencyCheck | None = None


def _executor_for(
    dependencies: RemediationReaperDependencies,
    action: RemediationActionCode,
) -> RemediationExecutor | None:
    if action == "resume_valid_checkpoint":
        return dependencies.resume_valid_checkpoint
    if action == "retry_transient_service_call":
        return dependencies.retry_transient_service_call
    if action == "rerun_targeted_artifact_family":
        return dependencies.rerun_targeted_artifact_family
    if action == "revalidate_replaced_source":
        return dependencies.revalidate_replaced_source
    if action == "poll_mailbox_delivery":
        return dependencies.poll_mailbox_delivery
    if action == "retry_idempotent_publication":
        return dependencies.retry_idempotent_publication
    return None


def _transition(
    *,
    state_db: str,
    record: RemediationRecord,
    status: str,
    reason: str,
    actor: str,
    ctx: RunContext,
    next_eligible_at_utc: str = "",
    increment_attempt: bool = False,
) -> RemediationRecord:
    return state_service.transition_remediation(
        RemediationTransitionRequest(
            schema_version="1.0",
            state_db=state_db,
            remediation_id=record.remediation_id,
            status=status,
            reason=reason,
            actor=actor,
            next_eligible_at_utc=next_eligible_at_utc,
            increment_attempt=increment_attempt,
        ),
        ctx,
    ).record


def _log_reaper_event(
    ctx: RunContext, event: str, record: RemediationRecord, reason: str
) -> None:
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event=event,
            module=logger.name,
            fields={
                "remediation_id": record.remediation_id,
                "workflow": record.workflow,
                "action_code": record.action_code,
                "status": record.status,
                "transition_reason": reason,
                "attempt_count": record.attempt_count,
                "max_attempts": record.max_attempts,
            },
        )
    )


def run_bounded_remediation_reaper(
    request: RemediationReaperRequest,
    ctx: RunContext,
    *,
    dependencies: RemediationReaperDependencies | None = None,
) -> RemediationReaperResponse:
    """Run at most ``limit`` closed, policy-approved remediation actions once."""

    if not request.execution_enabled:
        return RemediationReaperResponse(schema_version="1.0", inspected_count=0)
    deps = dependencies or RemediationReaperDependencies()
    released = state_service.release_expired_remediation_leases(
        RemediationExpiredLeaseReleaseRequest(
            schema_version="1.0", state_db=request.state_db, now_utc=request.now_utc
        ),
        child_context(ctx, task_id="remediation:release_expired_leases"),
    ).released_ids
    resolved: list[str] = []
    deferred: list[str] = []
    held: list[str] = []
    inspected = 0
    for _ in range(max(1, min(100, request.limit))):
        claim = state_service.claim_next_remediation(
            RemediationClaimRequest(
                schema_version="1.0",
                state_db=request.state_db,
                worker_id=request.worker_id,
                now_utc=request.now_utc,
                lease_seconds=request.lease_seconds,
            ),
            child_context(ctx, task_id="remediation:claim"),
        )
        record = claim.record
        if record is None:
            break
        inspected += 1
        work_ctx = child_context(ctx, task_id=f"remediation:{record.remediation_id}")
        if record.attempt_count >= record.max_attempts:
            record = _transition(
                state_db=request.state_db,
                record=record,
                status="terminal",
                reason="attempt_budget_exhausted",
                actor=request.worker_id,
                ctx=work_ctx,
            )
            _log_reaper_event(
                work_ctx, "remediation_exhausted", record, "attempt_budget_exhausted"
            )
            held.append(record.remediation_id)
            continue
        budget_decision = (
            deps.budget_check(record, work_ctx)
            if deps.budget_check is not None
            else record.budget.decision
        )
        if budget_decision in {"defer", "pause", "stop"}:
            record = _transition(
                state_db=request.state_db,
                record=record,
                status="deferred",
                reason="budget_prevented_retry",
                actor=request.worker_id,
                ctx=work_ctx,
                next_eligible_at_utc=_utc_after(
                    request.now_utc, max(1, record.cooldown_seconds)
                ),
            )
            _log_reaper_event(
                work_ctx,
                "remediation_budget_prevented_retry",
                record,
                "budget_prevented_retry",
            )
            deferred.append(record.remediation_id)
            continue
        if record.action_code == "resume_valid_checkpoint":
            valid = bool(
                deps.checkpoint_validator
                and deps.checkpoint_validator(record, work_ctx)
            )
            if not valid:
                record = _transition(
                    state_db=request.state_db,
                    record=record,
                    status="operator_action_required",
                    reason="checkpoint_rejected",
                    actor=request.worker_id,
                    ctx=work_ctx,
                )
                _log_reaper_event(
                    work_ctx,
                    "remediation_checkpoint_rejected",
                    record,
                    "checkpoint_rejected",
                )
                held.append(record.remediation_id)
                continue
        if record.action_code in _SIDE_EFFECTING_ACTIONS:
            proof = (
                deps.idempotency_check(record, work_ctx)
                if deps.idempotency_check
                else "unknown"
            )
            if proof == "already_completed":
                record = _transition(
                    state_db=request.state_db,
                    record=record,
                    status="resolved",
                    reason="idempotency_proved_completed",
                    actor=request.worker_id,
                    ctx=work_ctx,
                )
                _log_reaper_event(
                    work_ctx,
                    "remediation_succeeded",
                    record,
                    "idempotency_proved_completed",
                )
                resolved.append(record.remediation_id)
                continue
            if proof != "safe_to_execute":
                record = _transition(
                    state_db=request.state_db,
                    record=record,
                    status="operator_action_required",
                    reason="idempotency_proof_missing",
                    actor=request.worker_id,
                    ctx=work_ctx,
                )
                _log_reaper_event(
                    work_ctx,
                    "remediation_operator_action_required",
                    record,
                    "idempotency_proof_missing",
                )
                held.append(record.remediation_id)
                continue
        executor = _executor_for(deps, record.action_code)
        if executor is None:
            terminal_status = (
                "terminal"
                if record.action_code == "mark_terminal_blocker"
                else "operator_action_required"
            )
            record = _transition(
                state_db=request.state_db,
                record=record,
                status=terminal_status,
                reason="action_not_enabled",
                actor=request.worker_id,
                ctx=work_ctx,
            )
            _log_reaper_event(
                work_ctx,
                "remediation_terminal_blocker"
                if terminal_status == "terminal"
                else "remediation_operator_action_required",
                record,
                "action_not_enabled",
            )
            held.append(record.remediation_id)
            continue
        record = _transition(
            state_db=request.state_db,
            record=record,
            status="retrying",
            reason="remediation_started",
            actor=request.worker_id,
            ctx=work_ctx,
            increment_attempt=True,
        )
        _log_reaper_event(
            work_ctx, "remediation_started", record, "remediation_started"
        )
        outcome = executor(record, work_ctx)
        if outcome == "succeeded":
            record = _transition(
                state_db=request.state_db,
                record=record,
                status="resolved",
                reason="remediation_succeeded",
                actor=request.worker_id,
                ctx=work_ctx,
            )
            _log_reaper_event(
                work_ctx, "remediation_succeeded", record, "remediation_succeeded"
            )
            resolved.append(record.remediation_id)
        elif outcome == "deferred":
            record = _transition(
                state_db=request.state_db,
                record=record,
                status="deferred",
                reason="executor_deferred",
                actor=request.worker_id,
                ctx=work_ctx,
                next_eligible_at_utc=_utc_after(
                    request.now_utc, max(1, record.cooldown_seconds)
                ),
            )
            _log_reaper_event(
                work_ctx, "remediation_deferred", record, "executor_deferred"
            )
            deferred.append(record.remediation_id)
        else:
            status = "terminal" if outcome == "terminal" else "operator_action_required"
            record = _transition(
                state_db=request.state_db,
                record=record,
                status=status,
                reason=f"executor_{outcome or 'held'}",
                actor=request.worker_id,
                ctx=work_ctx,
            )
            _log_reaper_event(
                work_ctx,
                "remediation_terminal_blocker"
                if status == "terminal"
                else "remediation_operator_action_required",
                record,
                f"executor_{outcome or 'held'}",
            )
            held.append(record.remediation_id)
    return RemediationReaperResponse(
        schema_version="1.0",
        inspected_count=inspected,
        resolved_ids=resolved,
        deferred_ids=deferred,
        held_ids=held,
        released_lease_ids=released,
    )


__all__ = [
    "RemediationReaperDependencies",
    "record_workflow_failure",
    "run_bounded_remediation_reaper",
]
