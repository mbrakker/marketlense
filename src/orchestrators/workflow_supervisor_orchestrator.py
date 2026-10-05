"""One bounded, lease-protected composition of existing workflow controls."""

from __future__ import annotations

import logging
import time
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from typing import Callable

from src.contracts.run_context import RunContext
from src.contracts.workflow_control import SupervisorRunRequest, SupervisorRunResult
from src.contracts.workflow_queue import WORKFLOW_QUEUE_NAMES
from src.orchestrators.workflow_worker_orchestrator import (
    WorkflowWorkerRunResult,
    run_workflow_worker_once,
)
from src.services import workflow_queue_service
from src.utils.clock import utc_now_seconds_iso
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
            if settings.max_parallel_workers <= 1:
                (
                    worker_recovered,
                    worker_completed,
                    worker_deferred,
                    worker_errors,
                ) = _run_worker_batches_serial(
                    request=request, ctx=ctx, deps=deps, started=started
                )
            else:
                (
                    worker_recovered,
                    worker_completed,
                    worker_deferred,
                    worker_errors,
                    worker_materialized,
                ) = _run_worker_batches_parallel(
                    request=request, ctx=ctx, deps=deps, started=started
                )
                materialized += worker_materialized
            recovered += worker_recovered
            completed += worker_completed
            deferred += worker_deferred
            errors.extend(worker_errors)
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
            now_utc=utc_now_seconds_iso(),
            ctx=ctx,
        )


def _run_worker_batches_serial(
    *,
    request: SupervisorRunRequest,
    ctx: RunContext,
    deps: SupervisorDependencies,
    started: float,
) -> tuple[int, int, int, list[str]]:
    """Preserve the existing queue-order execution for the default worker cap."""
    remaining = request.settings.max_total_jobs
    recovered = completed = deferred = 0
    errors: list[str] = []
    for queue_name in WORKFLOW_QUEUE_NAMES:
        if (
            remaining <= 0
            or time.monotonic() - started >= request.settings.max_runtime_seconds
        ):
            if remaining > 0:
                deferred += 1
            break
        for ordinal in range(min(request.settings.max_jobs_per_queue, remaining)):
            result = _run_worker(
                request=request,
                ctx=ctx,
                deps=deps,
                queue_name=queue_name,
                ordinal=ordinal,
            )
            result_recovered, result_completed, result_deferred, result_errors = (
                _worker_result_counts(queue_name=queue_name, result=result)
            )
            recovered += result_recovered
            completed += result_completed
            deferred += result_deferred
            errors.extend(result_errors)
            if result.terminal_status == "idle":
                break
            remaining -= 1
    return recovered, completed, deferred, errors


def _run_worker_batches_parallel(
    *,
    request: SupervisorRunRequest,
    ctx: RunContext,
    deps: SupervisorDependencies,
    started: float,
) -> tuple[int, int, int, list[str], int]:
    """Fairly overlap independent queue work without exceeding the job allowance."""
    remaining = request.settings.max_total_jobs
    recovered = completed = deferred = 0
    materialized = 0
    errors: list[str] = []

    queue_start_index = 0

    def _candidate_sequence(
        *, priority_queue_names: tuple[str, ...] = ()
    ) -> list[tuple[str, int]]:
        ordered_queues = (
            WORKFLOW_QUEUE_NAMES[queue_start_index:]
            + WORKFLOW_QUEUE_NAMES[:queue_start_index]
        )
        priority_queues = tuple(
            queue_name
            for index, queue_name in enumerate(priority_queue_names)
            if queue_name in ordered_queues
            and queue_name not in priority_queue_names[:index]
        )
        if priority_queues:
            ordered_queues = priority_queues + tuple(
                queue_name
                for queue_name in ordered_queues
                if queue_name not in priority_queues
            )
        return [
            (queue_name, ordinal)
            for ordinal in range(request.settings.max_jobs_per_queue)
            for queue_name in ordered_queues
        ]

    candidates = _candidate_sequence()
    idle_queues: set[str] = set()
    pending_rechecks: list[str] = []
    pending_recheck_queues: set[str] = set()
    epoch = 0
    next_candidate = 0
    dispatch_sequence = 0
    priority_queue_names: tuple[str, ...] = ()
    runtime_exhausted = False
    lease_lost = False
    lease_heartbeat_seconds = max(
        0.1, min(30.0, max(1, request.settings.lease_seconds) / 3)
    )
    with ThreadPoolExecutor(
        max_workers=request.settings.max_parallel_workers,
        thread_name_prefix="workflow-supervisor",
    ) as executor:
        in_flight: dict[Future[WorkflowWorkerRunResult], tuple[str, int, int, int]] = {}

        def _schedule_pending_recheck() -> bool:
            nonlocal dispatch_sequence
            for pending_index, queue_name in enumerate(pending_rechecks):
                if queue_name in idle_queues:
                    pending_rechecks.pop(pending_index)
                    pending_recheck_queues.discard(queue_name)
                    return True
                active_ordinals = {
                    worker_ordinal
                    for active_queue, worker_ordinal, _active_epoch, _rank in (
                        in_flight.values()
                    )
                    if active_queue == queue_name
                }
                if len(active_ordinals) >= request.settings.max_jobs_per_queue:
                    continue
                ordinal = next(
                    slot
                    for slot in range(request.settings.max_jobs_per_queue)
                    if slot not in active_ordinals
                )
                pending_rechecks.pop(pending_index)
                pending_recheck_queues.discard(queue_name)
                future = executor.submit(
                    _run_worker,
                    request=request,
                    ctx=ctx,
                    deps=deps,
                    queue_name=queue_name,
                    ordinal=ordinal,
                )
                in_flight[future] = (
                    queue_name,
                    ordinal,
                    epoch,
                    dispatch_sequence,
                )
                dispatch_sequence += 1
                return True
            return False

        while in_flight or next_candidate < len(candidates) or pending_rechecks:
            while (
                not runtime_exhausted
                and (next_candidate < len(candidates) or pending_rechecks)
                and len(in_flight) < request.settings.max_parallel_workers
                and len(in_flight) < remaining
            ):
                if time.monotonic() - started >= request.settings.max_runtime_seconds:
                    runtime_exhausted = True
                    break
                for pending_index in range(len(pending_rechecks) - 1, -1, -1):
                    queue_name = pending_rechecks[pending_index]
                    if queue_name in idle_queues:
                        pending_rechecks.pop(pending_index)
                        pending_recheck_queues.discard(queue_name)
                if (
                    pending_rechecks
                    and next_candidate >= len(priority_queue_names)
                    and _schedule_pending_recheck()
                ):
                    continue
                if next_candidate < len(candidates):
                    queue_name, ordinal = candidates[next_candidate]
                    next_candidate += 1
                    if queue_name in idle_queues:
                        continue
                    active_ordinals = {
                        worker_ordinal
                        for active_queue, worker_ordinal, _active_epoch, _rank in (
                            in_flight.values()
                        )
                        if active_queue == queue_name
                    }
                    if ordinal in active_ordinals:
                        continue
                    if len(active_ordinals) >= request.settings.max_jobs_per_queue:
                        continue
                    future = executor.submit(
                        _run_worker,
                        request=request,
                        ctx=ctx,
                        deps=deps,
                        queue_name=queue_name,
                        ordinal=ordinal,
                    )
                    in_flight[future] = (queue_name, ordinal, epoch, dispatch_sequence)
                    dispatch_sequence += 1
                    continue
                if not _schedule_pending_recheck():
                    break
            if not in_flight:
                break
            done, _ = wait(
                in_flight,
                timeout=lease_heartbeat_seconds,
                return_when=FIRST_COMPLETED,
            )
            if not done:
                if not lease_lost and not deps.acquire_lease(
                    request.state_db,
                    owner_id=request.worker_id,
                    now_utc=utc_now_seconds_iso(),
                    lease_seconds=request.settings.lease_seconds,
                    ctx=ctx,
                ):
                    lease_lost = True
                    runtime_exhausted = True
                continue
            reopen_epoch = False
            last_success_queue = ""
            successful_queues: list[str] = []
            for future in sorted(done, key=lambda item: in_flight[item][3]):
                queue_name, _ordinal, worker_epoch, _rank = in_flight.pop(future)
                result = future.result()
                result_recovered, result_completed, result_deferred, result_errors = (
                    _worker_result_counts(queue_name=queue_name, result=result)
                )
                recovered += result_recovered
                completed += result_completed
                deferred += result_deferred
                errors.extend(result_errors)
                if result.terminal_status == "idle":
                    current_epoch_poll_active = any(
                        active_queue == queue_name and active_epoch == epoch
                        for active_queue, _ordinal, active_epoch, _rank in (
                            in_flight.values()
                        )
                    )
                    candidate_remains = any(
                        candidate_queue == queue_name
                        for candidate_queue, _ordinal in candidates[next_candidate:]
                    )
                    if (
                        not current_epoch_poll_active
                        and not candidate_remains
                        and queue_name not in pending_recheck_queues
                    ):
                        if worker_epoch == epoch:
                            idle_queues.add(queue_name)
                        elif queue_name not in idle_queues:
                            # Only re-offer the stale queue. Restarting every
                            # queue here can create an idle-poll feedback loop.
                            pending_rechecks.append(queue_name)
                            pending_recheck_queues.add(queue_name)
                else:
                    remaining -= 1
                    if result.terminal_status == "succeeded":
                        last_success_queue = queue_name
                        successful_queues.append(queue_name)
                        if (
                            request.settings.materialize_outbox_enabled
                            and remaining > 0
                        ):
                            new_job_ids = deps.materialize_outbox(
                                request.state_db,
                                f"supervisor:{request.worker_id}:{request.now_utc}:rescan:{completed}",
                                ctx,
                                limit=remaining,
                            )
                            materialized += len(new_job_ids)
                            reopen_epoch = reopen_epoch or bool(new_job_ids)
            if reopen_epoch:
                epoch += 1
                idle_queues.clear()
                if last_success_queue:
                    queue_start_index = (
                        WORKFLOW_QUEUE_NAMES.index(last_success_queue) + 1
                    ) % len(WORKFLOW_QUEUE_NAMES)
                    next_queue = WORKFLOW_QUEUE_NAMES[queue_start_index]
                    priority_queue_names = (last_success_queue, next_queue)
                else:
                    priority_queue_names = ()
                candidates = _candidate_sequence(
                    priority_queue_names=priority_queue_names
                )
                next_candidate = 0
            for queue_name in successful_queues:
                idle_queues.discard(queue_name)
                if queue_name not in pending_recheck_queues:
                    pending_rechecks.append(queue_name)
                    pending_recheck_queues.add(queue_name)
        if runtime_exhausted and remaining > 0:
            deferred += 1
        if lease_lost:
            errors.append("supervisor_lease_lost")
    return recovered, completed, deferred, errors, materialized


def _run_worker(
    *,
    request: SupervisorRunRequest,
    ctx: RunContext,
    deps: SupervisorDependencies,
    queue_name: str,
    ordinal: int,
):
    worker_id = f"{request.worker_id}:{queue_name}"
    if ordinal > 0:
        worker_id = f"{worker_id}:{ordinal + 1}"
    return deps.run_worker(
        state_db=request.state_db,
        queue_name=queue_name,
        worker_id=worker_id,
        ctx=child_context(ctx, task_id=f"supervisor:{queue_name}:{ordinal + 1}"),
        now_utc=utc_now_seconds_iso(),
    )


def _worker_result_counts(
    *, queue_name: str, result
) -> tuple[int, int, int, list[str]]:
    recovered = len(result.released_lease_job_ids)
    if result.terminal_status == "succeeded":
        return recovered, 1, 0, []
    if result.terminal_status in {"budget_deferred", "retry_wait", "blocked"}:
        return recovered, 0, 1, []
    if result.terminal_status == "idle":
        return recovered, 0, 0, []
    return recovered, 0, 0, [f"worker:{queue_name}:{result.terminal_status}"]
