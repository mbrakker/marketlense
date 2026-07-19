"""One bounded, lease-protected composition of existing workflow controls."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Callable

from src.contracts.run_context import RunContext
from src.contracts.workflow_control import SupervisorRunRequest, SupervisorRunResult
from src.contracts.workflow_queue import WORKFLOW_QUEUE_NAMES
from src.orchestrators.workflow_worker_orchestrator import run_workflow_worker_once
from src.services import workflow_queue_service
from src.utils.logging import child_context, log_event

logger = logging.getLogger("market_lense.workflow_supervisor")


@dataclass(frozen=True)
class SupervisorDependencies:
    acquire_lease: Callable = workflow_queue_service.acquire_workflow_supervisor_lease
    release_lease: Callable = workflow_queue_service.release_workflow_supervisor_lease
    materialize_outbox: Callable = workflow_queue_service.materialize_workflow_outbox
    recover_leases: Callable = workflow_queue_service.release_expired_workflow_leases
    run_worker: Callable = run_workflow_worker_once
    reconcile: Callable = workflow_queue_service.reconcile_workflow_queue
    queue_health: Callable = workflow_queue_service.read_workflow_queue_health
    reap_deferred_work: Callable[[SupervisorRunRequest, RunContext], int] | None = None
    reap_remediation: Callable[[SupervisorRunRequest, RunContext], int] | None = None


def run_supervisor_once(
    request: SupervisorRunRequest,
    ctx: RunContext,
    *,
    dependencies: SupervisorDependencies | None = None,
) -> SupervisorRunResult:
    """Run exactly one deterministic supervisory pass; never schedule recurrence."""

    settings = request.settings
    if not settings.enabled:
        return SupervisorRunResult(
            schema_version="1.0", status="disabled", lease_acquired=False
        )
    deps = dependencies or SupervisorDependencies()
    if not deps.acquire_lease(
        request.state_db,
        owner_id=request.worker_id,
        now_utc=request.now_utc,
        lease_seconds=settings.lease_seconds,
        ctx=ctx,
    ):
        return SupervisorRunResult(
            schema_version="1.0", status="busy", lease_acquired=False
        )

    started = time.monotonic()
    materialized = recovered = completed = deferred = reconciled = 0
    deferred_reaped = remediation_reaped = 0
    errors: list[str] = []
    try:
        if settings.materialize_outbox_enabled:
            materialized = len(
                deps.materialize_outbox(
                    request.state_db,
                    f"supervisor:{request.worker_id}:{request.now_utc}",
                    ctx,
                    limit=settings.max_total_jobs,
                )
            )
        if settings.recover_expired_leases_enabled:
            recovered = len(
                deps.recover_leases(
                    request.state_db,
                    ctx,
                    now_utc=request.now_utc,
                    actor=request.worker_id,
                )
            )
        if settings.deferred_work_enabled:
            if deps.reap_deferred_work is None:
                errors.append("deferred_work_adapter_unregistered")
            else:
                deferred_reaped = deps.reap_deferred_work(request, ctx)
        if settings.remediation_enabled:
            if deps.reap_remediation is None:
                errors.append("remediation_adapter_unregistered")
            else:
                remediation_reaped = deps.reap_remediation(request, ctx)
        if settings.worker_batches_enabled:
            remaining = settings.max_total_jobs
            for queue_name in WORKFLOW_QUEUE_NAMES:
                if (
                    remaining <= 0
                    or time.monotonic() - started >= settings.max_runtime_seconds
                ):
                    if remaining > 0:
                        deferred += 1
                    break
                for ordinal in range(min(settings.max_jobs_per_queue, remaining)):
                    result = deps.run_worker(
                        state_db=request.state_db,
                        queue_name=queue_name,
                        worker_id=f"{request.worker_id}:{queue_name}",
                        ctx=child_context(
                            ctx, task_id=f"supervisor:{queue_name}:{ordinal + 1}"
                        ),
                        now_utc=request.now_utc,
                    )
                    recovered += len(result.released_lease_job_ids)
                    if result.terminal_status == "idle":
                        break
                    remaining -= 1
                    if result.terminal_status == "succeeded":
                        completed += 1
                    elif result.terminal_status in {
                        "budget_deferred",
                        "retry_wait",
                        "blocked",
                    }:
                        deferred += 1
                    else:
                        errors.append(f"worker:{queue_name}:{result.terminal_status}")
        if settings.reconcile_enabled:
            reconciliation = deps.reconcile(
                request.state_db, ctx, now_utc=request.now_utc
            )
            reconciled = sum(
                len(value)
                for value in reconciliation.values()
                if isinstance(value, list)
            )
            errors.extend(str(value) for value in reconciliation.get("anomalies", []))
        health = (
            deps.queue_health(request.state_db, ctx, now_utc=request.now_utc)
            if settings.evidence_enabled
            else []
        )
        status = "failed" if errors else "partially_deferred" if deferred else "healthy"
        result = SupervisorRunResult(
            schema_version="1.0",
            status=status,
            lease_acquired=True,
            materialized_job_count=materialized,
            recovered_lease_count=recovered,
            deferred_reaped_count=deferred_reaped,
            remediation_reaped_count=remediation_reaped,
            completed_job_count=completed,
            deferred_job_count=deferred,
            reconciled_count=reconciled,
            queue_health_count=len(health),
            error_codes=sorted(errors),
        )
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="workflow_supervisor_complete",
                module=__name__,
                fields={
                    "status": result.status,
                    "materialized_job_count": result.materialized_job_count,
                    "recovered_lease_count": result.recovered_lease_count,
                    "deferred_reaped_count": result.deferred_reaped_count,
                    "remediation_reaped_count": result.remediation_reaped_count,
                    "completed_job_count": result.completed_job_count,
                    "deferred_job_count": result.deferred_job_count,
                    "reconciled_count": result.reconciled_count,
                    "queue_health_count": result.queue_health_count,
                    "error_count": len(result.error_codes),
                },
            )
        )
        return result
    finally:
        deps.release_lease(
            request.state_db,
            owner_id=request.worker_id,
            now_utc=request.now_utc,
            ctx=ctx,
        )
