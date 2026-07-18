from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Callable

from src.contracts.deferred_work import (
    DeferredWorkClaimRequest,
    DeferredWorkItem,
    DeferredWorkLeaseReleaseRequest,
    DeferredWorkReaperRequest,
    DeferredWorkReaperResponse,
    DeferredWorkResumePlan,
    DeferredWorkStatus,
    DeferredWorkTransitionRequest,
)
from src.contracts.run_budget import BudgetDecision
from src.contracts.run_context import RunContext
from src.orchestrators.remediation_orchestrator import record_workflow_failure
from src.services.llm_usage_ledger_service import (
    claim_next_deferred_work,
    recheck_deferred_work_budget,
    release_expired_deferred_work_leases,
    transition_deferred_work,
)
from src.utils.errors import AppError
from src.utils.logging import child_context, log_event

logger = logging.getLogger("market_lense.deferred_work_orchestrator")

DeferredWorkPlanBuilder = Callable[
    [DeferredWorkItem, RunContext], DeferredWorkResumePlan
]
DeferredWorkResumer = Callable[
    [DeferredWorkItem, DeferredWorkResumePlan, RunContext], str
]
DeferredWorkBudgetCheck = Callable[[DeferredWorkItem, RunContext], BudgetDecision | str]


@dataclass(frozen=True)
class DeferredWorkReaperDependencies:
    """Workflow-owned hooks used by the single bounded deferred-work reaper."""

    plan_builders: dict[str, DeferredWorkPlanBuilder]
    resumers: dict[str, DeferredWorkResumer]
    budget_check: DeferredWorkBudgetCheck = recheck_deferred_work_budget


def _after(now_utc: str, seconds: int) -> str:
    normalized = now_utc[:-1] + "+00:00" if now_utc.endswith("Z") else now_utc
    try:
        from datetime import datetime

        now = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise AppError(
            code="deferred_work_time_invalid",
            message="Deferred-work reaper requires an ISO-8601 UTC time",
            cause=exc,
            retryable=False,
        ) from exc
    if now.tzinfo is None:
        raise AppError(
            code="deferred_work_time_invalid",
            message="Deferred-work reaper time must include a UTC offset",
            retryable=False,
        )
    return (now + timedelta(seconds=max(1, seconds))).isoformat()


def _expired(item: DeferredWorkItem, now_utc: str) -> bool:
    return bool(item.deadline_at_utc) and item.deadline_at_utc <= now_utc


def _transition(
    request: DeferredWorkReaperRequest,
    item: DeferredWorkItem,
    *,
    status: DeferredWorkStatus,
    reason: str,
    ctx: RunContext,
    earliest_run_at_utc: str = "",
    terminal_status: str = "",
    remediation_id: str = "",
    plan: DeferredWorkResumePlan | None = None,
    increment_defer_count: bool = False,
) -> DeferredWorkItem:
    return transition_deferred_work(
        DeferredWorkTransitionRequest(
            schema_version="1.0",
            usage_db_path=request.usage_db_path,
            work_key=item.work_key,
            worker_id=request.worker_id,
            status=status,
            reason=reason,
            now_utc=request.now_utc,
            earliest_run_at_utc=earliest_run_at_utc,
            terminal_status=terminal_status,
            remediation_id=remediation_id,
            plan_hash=plan.plan_hash if plan else "",
            reusable_artifacts=plan.reusable_artifacts if plan else None,
            increment_defer_count=increment_defer_count,
        ),
        ctx,
    ).record


def _handoff_to_remediation(
    request: DeferredWorkReaperRequest,
    item: DeferredWorkItem,
    *,
    terminal_status: str,
    error: Exception,
    ctx: RunContext,
) -> DeferredWorkItem:
    remediation = record_workflow_failure(
        state_db=request.state_db,
        workflow=item.workflow,
        stage=item.stage or "budget_deferred_work",
        operation=item.operation,
        error=error,
        ctx=ctx,
        workflow_run_id=item.run_id,
        input_checksum=item.plan_hash or item.source_id or item.work_key,
        report_id=item.report_id,
        source_id=item.source_id,
        publisher_id=item.publisher_id,
    )
    return _transition(
        request,
        item,
        status="remediation",
        reason="remediation_handoff",
        terminal_status=terminal_status,
        remediation_id=remediation.remediation_id if remediation else "",
        ctx=ctx,
    )


def _log(ctx: RunContext, event: str, item: DeferredWorkItem, reason: str) -> None:
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event=event,
            module=logger.name,
            fields={
                "work_key": item.work_key,
                "workflow": item.workflow,
                "stage": item.stage,
                "status": item.status,
                "reason": reason,
                "attempt_count": item.attempt_count,
                "max_attempts": item.max_attempts,
                "defer_count": item.defer_count,
                "affected_limit": item.affected_limit,
                "lease_owner": item.lease_owner,
            },
        )
    )


def run_bounded_deferred_work_reaper(
    request: DeferredWorkReaperRequest,
    ctx: RunContext,
    *,
    dependencies: DeferredWorkReaperDependencies,
) -> DeferredWorkReaperResponse:
    """Lease and resume at most ``limit`` deferred records once.

    Invocation cadence belongs to an existing external supervisor or worker. This
    function intentionally performs no polling, sleeping, or scheduler setup.
    """

    if not request.execution_enabled:
        return DeferredWorkReaperResponse(schema_version="1.0", inspected_count=0)
    released = release_expired_deferred_work_leases(
        DeferredWorkLeaseReleaseRequest(
            schema_version="1.0",
            usage_db_path=request.usage_db_path,
            now_utc=request.now_utc,
        ),
        child_context(ctx, task_id="deferred_work:release_expired_leases"),
    ).released_work_keys
    completed: list[str] = []
    deferred: list[str] = []
    remediation: list[str] = []
    inspected = 0
    for _ in range(max(1, min(100, request.limit))):
        claim = claim_next_deferred_work(
            DeferredWorkClaimRequest(
                schema_version="1.0",
                usage_db_path=request.usage_db_path,
                worker_id=request.worker_id,
                now_utc=request.now_utc,
                lease_seconds=request.lease_seconds,
            ),
            child_context(ctx, task_id="deferred_work:claim"),
        )
        item = claim.record
        if item is None:
            break
        inspected += 1
        work_ctx = child_context(ctx, task_id=f"deferred_work:{item.work_key[:16]}")
        if _expired(item, request.now_utc):
            held = _handoff_to_remediation(
                request,
                item,
                terminal_status="deadline_expired",
                error=AppError(
                    code="deferred_work_deadline_expired",
                    message="Budget-deferred work reached its automatic-resume deadline",
                    retryable=False,
                ),
                ctx=work_ctx,
            )
            _log(work_ctx, "deferred_work_deadline_expired", held, "deadline_expired")
            remediation.append(item.work_key)
            continue
        if item.attempt_count > item.max_attempts:
            held = _handoff_to_remediation(
                request,
                item,
                terminal_status="attempt_budget_exhausted",
                error=AppError(
                    code="deferred_work_attempt_budget_exhausted",
                    message="Budget-deferred work exhausted its bounded automatic attempts",
                    retryable=False,
                ),
                ctx=work_ctx,
            )
            _log(
                work_ctx,
                "deferred_work_attempts_exhausted",
                held,
                "attempt_budget_exhausted",
            )
            remediation.append(item.work_key)
            continue
        try:
            budget_result = dependencies.budget_check(item, work_ctx)
            decision = (
                budget_result.decision
                if isinstance(budget_result, BudgetDecision)
                else str(budget_result or "stop")
            )
        except Exception as exc:
            held = _handoff_to_remediation(
                request,
                item,
                terminal_status="budget_recheck_failed",
                error=exc,
                ctx=work_ctx,
            )
            _log(
                work_ctx,
                "deferred_work_budget_recheck_failed",
                held,
                "budget_recheck_failed",
            )
            remediation.append(item.work_key)
            continue
        if decision == "defer":
            waiting = _transition(
                request,
                item,
                status="pending",
                reason="budget_still_deferred",
                earliest_run_at_utc=_after(
                    request.now_utc, request.retry_delay_seconds
                ),
                increment_defer_count=True,
                ctx=work_ctx,
            )
            _log(
                work_ctx,
                "deferred_work_still_deferred",
                waiting,
                "budget_still_deferred",
            )
            deferred.append(item.work_key)
            continue
        if decision in {"pause", "stop"}:
            held = _handoff_to_remediation(
                request,
                item,
                terminal_status=f"budget_{decision}",
                error=AppError(
                    code=f"deferred_work_budget_{decision}",
                    message="Budget authority prevented automatic deferred-work resumption",
                    retryable=False,
                ),
                ctx=work_ctx,
            )
            _log(work_ctx, "deferred_work_budget_terminal", held, f"budget_{decision}")
            remediation.append(item.work_key)
            continue
        if decision not in {"allow", "warn", "authorized_override"}:
            held = _handoff_to_remediation(
                request,
                item,
                terminal_status="budget_recheck_invalid",
                error=AppError(
                    code="deferred_work_budget_recheck_invalid",
                    message="Budget authority returned an unsupported resume decision",
                    retryable=False,
                ),
                ctx=work_ctx,
            )
            _log(
                work_ctx,
                "deferred_work_budget_terminal",
                held,
                "budget_recheck_invalid",
            )
            remediation.append(item.work_key)
            continue
        plan_builder = dependencies.plan_builders.get(item.workflow)
        resumer = dependencies.resumers.get(item.workflow)
        if plan_builder is None or resumer is None:
            held = _handoff_to_remediation(
                request,
                item,
                terminal_status="workflow_resume_handler_missing",
                error=AppError(
                    code="deferred_work_resume_handler_missing",
                    message="No approved deferred-work resume handler exists for this workflow",
                    retryable=False,
                ),
                ctx=work_ctx,
            )
            _log(
                work_ctx,
                "deferred_work_handler_missing",
                held,
                "workflow_resume_handler_missing",
            )
            remediation.append(item.work_key)
            continue
        try:
            plan = plan_builder(item, work_ctx)
            if not plan.plan_hash or not plan.resume_stage:
                raise AppError(
                    code="deferred_work_plan_invalid",
                    message="Deferred-work plan must contain a hash and safe resume stage",
                    retryable=False,
                )
            if plan.plan_hash != item.plan_hash:
                item = _transition(
                    request,
                    item,
                    status="leased",
                    reason="plan_rebuilt",
                    plan=plan,
                    ctx=work_ctx,
                )
                _log(work_ctx, "deferred_work_plan_rebuilt", item, "plan_rebuilt")
            outcome = str(resumer(item, plan, work_ctx) or "").strip().lower()
        except Exception as exc:
            if isinstance(exc, AppError) and (
                exc.context.get("retry_decision") == "defer"
                or exc.code.endswith("_budget_defer")
            ):
                waiting = _transition(
                    request,
                    item,
                    status="pending",
                    reason="resume_budget_deferred",
                    earliest_run_at_utc=_after(
                        request.now_utc, request.retry_delay_seconds
                    ),
                    increment_defer_count=True,
                    ctx=work_ctx,
                )
                _log(
                    work_ctx,
                    "deferred_work_resume_deferred",
                    waiting,
                    "resume_budget_deferred",
                )
                deferred.append(item.work_key)
            else:
                held = _handoff_to_remediation(
                    request,
                    item,
                    terminal_status="plan_or_resume_failed",
                    error=exc,
                    ctx=work_ctx,
                )
                _log(
                    work_ctx,
                    "deferred_work_resume_failed",
                    held,
                    "plan_or_resume_failed",
                )
                remediation.append(item.work_key)
            continue
        if outcome == "completed":
            done = _transition(
                request,
                item,
                status="completed",
                reason="resume_completed",
                ctx=work_ctx,
            )
            _log(work_ctx, "deferred_work_completed", done, "resume_completed")
            completed.append(item.work_key)
        elif outcome == "deferred":
            waiting = _transition(
                request,
                item,
                status="pending",
                reason="resume_deferred",
                earliest_run_at_utc=_after(
                    request.now_utc, request.retry_delay_seconds
                ),
                increment_defer_count=True,
                ctx=work_ctx,
            )
            _log(work_ctx, "deferred_work_resume_deferred", waiting, "resume_deferred")
            deferred.append(item.work_key)
        else:
            held = _handoff_to_remediation(
                request,
                item,
                terminal_status="resume_requires_remediation",
                error=AppError(
                    code="deferred_work_resume_requires_remediation",
                    message="Deferred-work resume did not complete safely",
                    retryable=False,
                ),
                ctx=work_ctx,
            )
            _log(
                work_ctx,
                "deferred_work_resume_failed",
                held,
                "resume_requires_remediation",
            )
            remediation.append(item.work_key)
    return DeferredWorkReaperResponse(
        schema_version="1.0",
        inspected_count=inspected,
        completed_work_keys=completed,
        deferred_work_keys=deferred,
        remediation_work_keys=remediation,
        released_lease_work_keys=released,
    )


__all__ = [
    "DeferredWorkReaperDependencies",
    "DeferredWorkPlanBuilder",
    "DeferredWorkResumer",
    "run_bounded_deferred_work_reaper",
]
