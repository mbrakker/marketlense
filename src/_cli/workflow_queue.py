"""Operational CLI for the durable typed workflow queue."""

# ruff: noqa: E501

from __future__ import annotations

from dataclasses import asdict, replace
from uuid import uuid4

import typer

from src._cli.app import cli_app, console
from src.contracts.config import ConfigLoadRequest
from src.contracts.logging import LoggingSetupRequest
from src.contracts.workflow_queue import WorkflowQueueControl
from src.orchestrators.workflow_worker_orchestrator import run_workflow_worker_once
from src.services.config_service import (
    load_settings,
    load_workflow_queue_policies,
)
from src.services.logging_service import setup_logging
from src.services.workflow_queue_service import (
    cancel_workflow_job,
    get_workflow_job,
    get_workflow_queue_control,
    list_workflow_job_attempts,
    materialize_workflow_outbox,
    read_workflow_queue_health,
    reconcile_workflow_queue,
    release_expired_workflow_leases,
    requeue_workflow_job,
    seed_workflow_queue_controls,
    set_workflow_queue_control,
)
from src.utils.logging import new_run_context


def _ctx(task: str):
    ctx = new_run_context(task_id=task)
    setup_logging(LoggingSetupRequest(schema_version="1.0"), ctx)
    return ctx


def _state_db(ctx) -> str:
    settings = load_settings(ConfigLoadRequest(schema_version="1.0", path=""), ctx)
    policies = load_workflow_queue_policies(
        ConfigLoadRequest(schema_version="1.0", path=""), ctx
    )
    seed_workflow_queue_controls(
        settings.state_db,
        [
            WorkflowQueueControl(
                schema_version=policy.schema_version,
                queue_name=policy.queue_name,
                mode="active",
                enabled=policy.enabled,
                worker_concurrency_limit=policy.max_workers,
                maximum_pending=policy.maximum_pending,
                maximum_fanout=policy.maximum_fanout,
                max_attempts=policy.max_attempts,
                lease_seconds=policy.lease_seconds,
                budget_profile=policy.budget_profile,
                retry_delay_seconds=policy.retry_delay_seconds,
                emergency_stop_reason="",
                updated_at_utc="",
                updated_by="config_seed",
            )
            for policy in policies.values()
        ],
        ctx,
    )
    return settings.state_db


@cli_app.command("queue-list")
def queue_list() -> None:
    """List independently controllable logical queues and their durable control."""
    ctx = _ctx("cli_queue_list")
    state_db = _state_db(ctx)
    console.print_json(
        data=[asdict(item) for item in read_workflow_queue_health(state_db, ctx)]
    )


@cli_app.command("queue-health")
def queue_health(
    queue: str = typer.Option("", help="Optional one logical queue"),
) -> None:
    ctx = _ctx("cli_queue_health")
    state_db = _state_db(ctx)
    records = read_workflow_queue_health(state_db, ctx)
    if queue:
        records = [record for record in records if record.queue_name == queue]
    console.print_json(data=[asdict(item) for item in records])


@cli_app.command("queue-inspect-job")
def queue_inspect_job(job_id: str = typer.Argument(...)) -> None:
    ctx = _ctx("cli_queue_inspect_job")
    state_db = _state_db(ctx)
    job = get_workflow_job(state_db, job_id, ctx)
    if job is None:
        raise typer.BadParameter("Unknown workflow job ID")
    console.print_json(
        data={
            "job": asdict(job),
            "attempts": [
                asdict(item)
                for item in list_workflow_job_attempts(state_db, job_id, ctx)
            ],
        }
    )


def _set_mode(queue: str, mode: str, reason: str, task: str) -> None:
    ctx = _ctx(task)
    state_db = _state_db(ctx)
    current = get_workflow_queue_control(state_db, queue, ctx)
    control = replace(
        current,
        mode=mode,  # type: ignore[arg-type]
        enabled=mode == "active",
        emergency_stop_reason=reason if mode != "active" else "",
        updated_by=str(ctx.run_id),
    )
    console.print_json(data=asdict(set_workflow_queue_control(state_db, control, ctx)))


@cli_app.command("queue-pause")
def queue_pause(
    queue: str = typer.Argument(...),
    reason: str = typer.Option(..., help="Required operator reason"),
) -> None:
    _set_mode(queue, "paused", reason, "cli_queue_pause")


@cli_app.command("queue-resume")
def queue_resume(queue: str = typer.Argument(...)) -> None:
    _set_mode(queue, "active", "", "cli_queue_resume")


@cli_app.command("queue-drain")
def queue_drain(
    queue: str = typer.Argument(...),
    reason: str = typer.Option(..., help="Required operator reason"),
) -> None:
    _set_mode(queue, "draining", reason, "cli_queue_drain")


@cli_app.command("queue-cancel")
def queue_cancel(
    job_id: str = typer.Argument(...),
    yes: bool = typer.Option(False, "--yes", help="Confirm cancellation"),
) -> None:
    if not yes:
        raise typer.BadParameter("--yes is required to cancel a durable job")
    ctx = _ctx("cli_queue_cancel")
    state_db = _state_db(ctx)
    console.print_json(
        data=asdict(cancel_workflow_job(state_db, job_id, str(ctx.run_id), ctx))
    )


@cli_app.command("queue-requeue")
def queue_requeue(
    job_id: str = typer.Argument(...),
    yes: bool = typer.Option(False, "--yes", help="Confirm explicit requeue"),
) -> None:
    if not yes:
        raise typer.BadParameter("--yes is required to requeue a durable job")
    ctx = _ctx("cli_queue_requeue")
    state_db = _state_db(ctx)
    console.print_json(
        data=asdict(requeue_workflow_job(state_db, job_id, str(ctx.run_id), ctx))
    )


@cli_app.command("queue-release-expired-leases")
def queue_release_expired_leases() -> None:
    ctx = _ctx("cli_queue_release_expired_leases")
    state_db = _state_db(ctx)
    console.print_json(
        data={"released_job_ids": release_expired_workflow_leases(state_db, ctx)}
    )


@cli_app.command("queue-reconcile")
def queue_reconcile() -> None:
    ctx = _ctx("cli_queue_reconcile")
    state_db = _state_db(ctx)
    console.print_json(data=reconcile_workflow_queue(state_db, ctx))


@cli_app.command("queue-materialize-outbox")
def queue_materialize_outbox(
    limit: int = typer.Option(50, min=1, max=500),
) -> None:
    ctx = _ctx("cli_queue_materialize_outbox")
    state_db = _state_db(ctx)
    console.print_json(
        data={
            "materialised_job_ids": materialize_workflow_outbox(
                state_db, f"cli-outbox:{uuid4()}", ctx, limit=limit
            )
        }
    )


@cli_app.command("workflow-worker")
def workflow_worker(
    queue: str = typer.Option(..., help="Logical queue consumed by this worker"),
    limit: int = typer.Option(1, min=1, max=500, help="Bounded jobs this invocation"),
    worker_id: str = typer.Option(
        "", help="Stable worker identity; generated if omitted"
    ),
) -> None:
    """Run a bounded worker invocation; an external supervisor owns recurrence."""
    ctx = _ctx("cli_workflow_worker")
    state_db = _state_db(ctx)
    identity = worker_id or f"workflow-worker:{uuid4()}"
    outcomes = []
    for _ in range(limit):
        result = run_workflow_worker_once(
            state_db=state_db,
            queue_name=queue,
            worker_id=identity,
            ctx=ctx,
        )
        outcomes.append(asdict(result))
        if result.terminal_status == "idle":
            break
    console.print_json(data=outcomes)
