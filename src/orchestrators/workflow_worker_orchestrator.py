"""One bounded worker loop for the typed durable workflow queue."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime

from src.contracts.performance_telemetry import (
    PerformanceTelemetryMeasurement,
    PerformanceTelemetrySpan,
)
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
from src.services.performance_telemetry_service import (
    record_performance_measurement,
    record_performance_span,
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


def _is_budget_deferral_error(error: AppError) -> bool:
    """Identify recoverable resource budgets, not input-size policy failures."""

    code = error.code
    if code == "cross_report_prompt_budget_exceeded":
        return False
    return (
        code.startswith("budget_")
        or code.startswith("workflow_budget_")
        or "_budget_" in code
    )


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
    started_monotonic_ns = time.monotonic_ns()
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
        _record_worker_telemetry(
            state_db=state_db,
            job=running,
            completed_at_utc=completed.completed_at_utc,
            status="completed",
            started_monotonic_ns=started_monotonic_ns,
            ctx=work_ctx,
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
            budget_deferred=_is_budget_deferral_error(exc),
            blocked=exc.code
            in {
                "stale_approval",
                "source_identity_conflict",
                "captcha_blocked",
                "credentials_required",
                "cross_report_publish_live_disabled",
            },
        )
        _record_worker_telemetry(
            state_db=state_db,
            job=running,
            completed_at_utc=failed.updated_at_utc,
            status="failed",
            started_monotonic_ns=started_monotonic_ns,
            ctx=work_ctx,
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
        _record_worker_telemetry(
            state_db=state_db,
            job=running,
            completed_at_utc=failed.updated_at_utc,
            status="failed",
            started_monotonic_ns=started_monotonic_ns,
            ctx=work_ctx,
        )
        return WorkflowWorkerRunResult(
            queue_name=queue_name,
            worker_id=worker_id,
            released_lease_job_ids=released,
            claimed_job_id=running.job_id,
            terminal_status=failed.status,
        )


def _record_worker_telemetry(
    *,
    state_db: str,
    job,
    completed_at_utc: str,
    status: str,
    started_monotonic_ns: int,
    ctx: RunContext,
) -> None:
    """Persist one queue-attempt span after its terminal queue transition."""

    record_performance_span(
        state_db,
        PerformanceTelemetrySpan(
            schema_version="1.0",
            span_id=ctx.span_id,
            run_id=str(ctx.run_id),
            stage=job.queue_name,
            status=status,  # type: ignore[arg-type]
            measurement_profile_hash=(
                f"queue:{job.workflow_version}:{job.processing_version or 'default'}"
            ),
            queue_name=job.queue_name,
            worker_id=job.lease_owner,
            queued_at_utc=job.created_at_utc,
            started_at_utc=job.started_at_utc,
            completed_at_utc=completed_at_utc,
            attributes={"job_id": job.job_id, "workflow": job.workflow_version},
        ),
        ctx,
    )
    wait_ms = _queue_wait_ms(
        created_at_utc=job.created_at_utc,
        available_at_utc=job.available_at_utc,
        started_at_utc=job.started_at_utc,
    )
    record_performance_measurement(
        state_db,
        PerformanceTelemetryMeasurement(
            schema_version="1.0",
            span_id=ctx.span_id,
            metric="queue_wait_ms",
            status="observed" if wait_ms is not None else "unavailable",
            integer_value=wait_ms,
        ),
        ctx,
    )
    record_performance_measurement(
        state_db,
        PerformanceTelemetryMeasurement(
            schema_version="1.0",
            span_id=ctx.span_id,
            metric="wall_time_ms",
            status="observed",
            integer_value=max(
                0, round((time.monotonic_ns() - started_monotonic_ns) / 1_000_000)
            ),
        ),
        ctx,
    )


def _queue_wait_ms(
    *, created_at_utc: str, available_at_utc: str, started_at_utc: str
) -> int | None:
    try:
        start = _parse_utc(started_at_utc)
        queued = max(_parse_utc(created_at_utc), _parse_utc(available_at_utc))
    except ValueError:
        return None
    return max(0, round((start - queued).total_seconds() * 1000))


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
