"""Operational CLI for the durable typed workflow queue."""

# ruff: noqa: E501

from __future__ import annotations

import hashlib
from dataclasses import asdict, replace
from uuid import uuid4

import typer

from src._cli.app import cli_app, console
from src.contracts.config import ConfigLoadRequest, IngestSettingsBuildRequest
from src.contracts.deferred_work import DeferredWorkQueueMigrationRequest
from src.contracts.files import FileStatRequest
from src.contracts.logging import LoggingSetupRequest
from src.contracts.workflow_control import SupervisorRunRequest
from src.contracts.workflow_queue import (
    PublisherDiscoveryPayload,
    ReportAcquisitionPayload,
    SourceIngestPayload,
    WordPressPublishPayload,
    WorkflowJobSubmission,
    WorkflowQueueControl,
)
from src.orchestrators.deferred_work_queue_adapter import (
    migrate_deferred_work_to_workflow_queue,
)
from src.orchestrators.recovery_adapter_registry import (
    build_recovery_adapter_registry,
    reap_deferred_work_from_supervisor,
)
from src.orchestrators.workflow_supervisor_orchestrator import (
    SupervisorDependencies,
    run_supervisor_once,
)
from src.orchestrators.workflow_worker_orchestrator import run_workflow_worker_once
from src.services.config_service import (
    build_ingest_settings,
    load_settings,
    load_workflow_control_settings,
    load_workflow_queue_policies,
)
from src.services.file_service import file_stat
from src.services.logging_service import setup_logging
from src.services.workflow_queue_service import (
    approve_publication_package,
    cancel_workflow_job,
    enqueue_workflow_job,
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
from src.utils.clock import utc_now_seconds_iso
from src.services.config_service import new_runtime_context as new_run_context


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


def _stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@cli_app.command("queue-submit-discovery")
def queue_submit_discovery(
    publisher_id: str = typer.Option(...),
    insights_url: str = typer.Option(...),
    policy_version: str = typer.Option("v1"),
) -> None:
    """Submit one durable publisher-discovery request and return its job ID."""
    ctx = _ctx("cli_queue_submit_discovery")
    state_db = _state_db(ctx)
    source_hash = _stable_hash(f"{publisher_id}:{insights_url}:{policy_version}")
    job, created = enqueue_workflow_job(
        state_db,
        WorkflowJobSubmission(
            schema_version="1.0",
            queue_name="publisher_discovery",
            job_type="publisher_discovery.v1",
            payload=PublisherDiscoveryPayload(
                publisher_id=publisher_id,
                insights_url=insights_url,
                discovery_policy_version=policy_version,
                input_reference=insights_url,
                input_content_hash=source_hash,
                processing_version=policy_version,
            ),
            idempotency_key=source_hash,
            deduplication_scope="publisher-discovery",
            root_workflow_id=f"discovery:{source_hash[:20]}",
            publisher_id=publisher_id,
            budget_profile="publisher_inventory",
        ),
        ctx,
    )
    console.print_json(data={"job_id": job.job_id, "created": created})


@cli_app.command("queue-submit-acquisition")
def queue_submit_acquisition(
    source_url: str = typer.Option(...),
    publisher_id: str = typer.Option(""),
    title: str = typer.Option(""),
    publisher_name: str = typer.Option(""),
    delivery_email: str = typer.Option(""),
    policy_version: str = typer.Option("v1"),
) -> None:
    """Submit one durable report-acquisition request; it never waits for I/O."""
    ctx = _ctx("cli_queue_submit_acquisition")
    state_db = _state_db(ctx)
    source_identity_id = _stable_hash(source_url)
    job, created = enqueue_workflow_job(
        state_db,
        WorkflowJobSubmission(
            schema_version="1.0",
            queue_name="report_acquisition",
            job_type="report_acquisition.v1",
            payload=ReportAcquisitionPayload(
                source_identity_id=source_identity_id,
                source_url=source_url,
                publisher_id=publisher_id,
                acquisition_policy_version=policy_version,
                report_title=title,
                publisher_name=publisher_name,
                delivery_email_reference=delivery_email,
                input_reference=source_url,
                input_content_hash=source_identity_id,
                processing_version=policy_version,
            ),
            idempotency_key=f"{source_identity_id}:{policy_version}",
            deduplication_scope="report-acquisition-source",
            root_workflow_id=f"acquisition:{source_identity_id[:20]}",
            publisher_id=publisher_id,
            source_identity_id=source_identity_id,
            budget_profile="browser_acquisition",
        ),
        ctx,
    )
    console.print_json(data={"job_id": job.job_id, "created": created})


@cli_app.command("queue-submit-source-ingest")
def queue_submit_source_ingest(
    artifact_path: str = typer.Option(...),
    report_id: str = typer.Option(...),
    source_identity_id: str = typer.Option(""),
    processing_version: str = typer.Option("v1"),
) -> None:
    """Submit a verified local source artifact for durable report-stage processing."""
    ctx = _ctx("cli_queue_submit_source_ingest")
    state_db = _state_db(ctx)
    stat = file_stat(
        FileStatRequest(schema_version="1.0", path=artifact_path, compute_md5=True), ctx
    )
    if not stat.exists or not stat.is_file or not stat.md5:
        raise typer.BadParameter("artifact-path must be a readable retained file")
    identity = source_identity_id or _stable_hash(f"{artifact_path}:{stat.md5}")
    job, created = enqueue_workflow_job(
        state_db,
        WorkflowJobSubmission(
            schema_version="1.0",
            queue_name="source_ingest",
            job_type="source_ingest.v1",
            payload=SourceIngestPayload(
                source_identity_id=identity,
                source_artifact_reference=artifact_path,
                source_content_hash=stat.md5,
                report_id=report_id,
                parser_ocr_compatibility_version=processing_version,
                input_reference=artifact_path,
                input_content_hash=stat.md5,
                processing_version=processing_version,
            ),
            idempotency_key=f"{stat.md5}:source_ingest:{processing_version}",
            deduplication_scope="source-ingest-content",
            root_workflow_id=f"ingest:{report_id}",
            source_identity_id=identity,
            report_id=report_id,
            budget_profile="report_ingest",
        ),
        ctx,
    )
    console.print_json(data={"job_id": job.job_id, "created": created})


@cli_app.command("queue-migrate-deferred-work")
def queue_migrate_deferred_work(
    limit: int = typer.Option(100, min=1, max=500),
    yes: bool = typer.Option(False, "--yes", help="Confirm legacy-work handoff"),
) -> None:
    """Submit supported legacy budget deferrals to the canonical queue.

    The source ledger is deliberately not deleted or rewritten.  Each retained
    work key produces at most one effective queue job, and rows lacking a safe
    mapping are returned for operator action.
    """
    if not yes:
        raise typer.BadParameter("--yes is required to hand off legacy deferred work")
    ctx = _ctx("cli_queue_migrate_deferred_work")
    state_db = _state_db(ctx)
    settings = load_settings(ConfigLoadRequest(schema_version="1.0", path=""), ctx)
    response = migrate_deferred_work_to_workflow_queue(
        DeferredWorkQueueMigrationRequest(
            schema_version="1.0",
            usage_db_path=settings.usage_db_path,
            state_db=state_db,
            limit=limit,
        ),
        ctx,
    )
    console.print_json(data=asdict(response))


@cli_app.command("queue-approve-publication")
def queue_approve_publication(
    package_checksum: str = typer.Option(...),
    package_reference: str = typer.Option(...),
    entity_type: str = typer.Option(...),
    target_site: str = typer.Option("default"),
    note: str = typer.Option(""),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Execute the approved WordPress queue job without any WordPress write.",
    ),
    yes: bool = typer.Option(False, "--yes", help="Confirm human approval"),
) -> None:
    """Record human approval and enqueue—never execute—WordPress publication."""
    if not yes:
        raise typer.BadParameter("--yes is required to record publication approval")
    ctx = _ctx("cli_queue_approve_publication")
    state_db = _state_db(ctx)
    submission = WorkflowJobSubmission(
        schema_version="1.0",
        queue_name="wordpress_publish",
        job_type="wordpress_publish.v1",
        payload=WordPressPublishPayload(
            entity_type=entity_type,
            entity_package_reference=package_reference,
            package_checksum=package_checksum,
            target_site=target_site,
            input_reference=package_reference,
            input_content_hash=package_checksum,
            dry_run=dry_run,
        ),
        idempotency_key=f"{target_site}:{entity_type}:{package_checksum}",
        deduplication_scope="wordpress-publish-package",
        root_workflow_id=f"publication:{package_checksum[:20]}",
        entity_type=entity_type,
        entity_id=package_checksum,
        budget_profile="publishing",
    )
    approval = approve_publication_package(
        state_db,
        package_checksum=package_checksum,
        actor_id=str(ctx.run_id),
        note=note,
        publish_submission=submission,
        ctx=ctx,
    )
    console.print_json(data=asdict(approval))


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


@cli_app.command("supervise-workflows")
def supervise_workflows(
    once: bool = typer.Option(False, "--once", help="Required: run one bounded pass"),
    worker_id: str = typer.Option("", help="Stable supervisor identity"),
) -> None:
    """Compose existing durable controls once; the host owns recurrence."""

    if not once:
        raise typer.BadParameter("--once is required; this command never loops")
    ctx = _ctx("cli_supervise_workflows")
    state_db = _state_db(ctx)
    settings = load_settings(ConfigLoadRequest(schema_version="1.0", path=""), ctx)
    control = load_workflow_control_settings(
        ConfigLoadRequest(schema_version="1.0", path=""), ctx
    )
    ingest_settings = build_ingest_settings(
        IngestSettingsBuildRequest(schema_version="1.0", app_settings=settings), ctx
    )
    registry = build_recovery_adapter_registry(
        ingest_settings=ingest_settings,
        workflow_control_settings=control,
    )
    result = run_supervisor_once(
        SupervisorRunRequest(
            schema_version="1.0",
            state_db=state_db,
            usage_db_path=settings.usage_db_path,
            worker_id=worker_id or f"workflow-supervisor:{ctx.run_id}",
            now_utc=utc_now_seconds_iso(),
            settings=control.supervisor,
        ),
        ctx,
        dependencies=SupervisorDependencies(
            reap_deferred_work=lambda request, work_ctx: (
                reap_deferred_work_from_supervisor(
                    request,
                    work_ctx,
                    registry=registry,
                    settings=control,
                )
            )
        ),
    )
    console.print_json(data=asdict(result))
    exit_codes = {
        "healthy": 0,
        "partially_deferred": 3,
        "failed": 1,
        "busy": 4,
        "disabled": 2,
    }
    raise typer.Exit(code=exit_codes[result.status])
