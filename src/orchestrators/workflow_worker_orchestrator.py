"""One bounded worker loop for the typed durable workflow queue."""

from __future__ import annotations

from dataclasses import dataclass

from src.contracts.run_context import RunContext
from src.orchestrators.workflow_queue_orchestrator import (
    WorkflowQueueHandlerRegistration,
    execute_workflow_queue_handler,
)
from src.services.workflow_queue_service import (
    claim_next_workflow_job,
    complete_workflow_job,
    fail_workflow_job,
    load_workflow_job_payload,
    release_expired_workflow_leases,
    start_workflow_job,
)
from src.utils.errors import AppError
from src.utils.logging import child_context


@dataclass(frozen=True)
class WorkflowWorkerRunResult:
    queue_name: str
    worker_id: str
    released_lease_job_ids: list[str]
    claimed_job_id: str = ""
    terminal_status: str = "idle"


def run_workflow_worker_once(
    *,
    state_db: str,
    queue_name: str,
    worker_id: str,
    ctx: RunContext,
    registry: dict[tuple[str, str], WorkflowQueueHandlerRegistration] | None = None,
    now_utc: str = "",
) -> WorkflowWorkerRunResult:
    """Claim at most one job and never let a stale lease complete an outcome."""
    released = release_expired_workflow_leases(
        state_db, ctx, now_utc=now_utc, actor=worker_id
    )
    leased = claim_next_workflow_job(
        state_db, queue_name, worker_id, ctx, now_utc=now_utc
    )
    if leased is None:
        return WorkflowWorkerRunResult(
            queue_name=queue_name,
            worker_id=worker_id,
            released_lease_job_ids=released,
        )
    work_ctx = child_context(ctx, task_id=f"workflow_job:{leased.job_id}")
    running = start_workflow_job(
        state_db, leased.job_id, worker_id, work_ctx, now_utc=now_utc
    )
    try:
        payload = load_workflow_job_payload(running)
        execution = execute_workflow_queue_handler(
            running, payload, work_ctx, registry=registry
        )
        completed = complete_workflow_job(
            state_db,
            running.job_id,
            worker_id,
            execution.result,
            execution.downstream,
            work_ctx,
            now_utc=now_utc,
            provider_usage=execution.provider_usage,
            external_effects=execution.external_effects,
        )
        return WorkflowWorkerRunResult(
            queue_name=queue_name,
            worker_id=worker_id,
            released_lease_job_ids=released,
            claimed_job_id=running.job_id,
            terminal_status=completed.status,
        )
    except AppError as exc:
        failed = fail_workflow_job(
            state_db,
            running.job_id,
            worker_id,
            exc,
            work_ctx,
            now_utc=now_utc,
            budget_deferred=(
                exc.code.startswith("budget_")
                or exc.code.startswith("workflow_budget_")
                or "_budget_" in exc.code
            ),
            blocked=exc.code
            in {
                "stale_approval",
                "source_identity_conflict",
                "captcha_blocked",
                "credentials_required",
            },
        )
        return WorkflowWorkerRunResult(
            queue_name=queue_name,
            worker_id=worker_id,
            released_lease_job_ids=released,
            claimed_job_id=running.job_id,
            terminal_status=failed.status,
        )
    except Exception as exc:
        failed = fail_workflow_job(
            state_db,
            running.job_id,
            worker_id,
            AppError(
                code="workflow_queue_programming_defect",
                message="Unhandled worker handler exception",
                cause=exc,
                retryable=False,
            ),
            work_ctx,
            now_utc=now_utc,
        )
        return WorkflowWorkerRunResult(
            queue_name=queue_name,
            worker_id=worker_id,
            released_lease_job_ids=released,
            claimed_job_id=running.job_id,
            terminal_status=failed.status,
        )
