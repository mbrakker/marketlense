# ruff: noqa: B008
from __future__ import annotations

import os
from dataclasses import asdict

import typer
import yaml
from rich import box
from rich.table import Table

from src._cli.app import cli_app, console
from src.contracts.config import ConfigLoadRequest, IngestSettingsBuildRequest
from src.contracts.deferred_work import (
    DeferredWorkListRequest,
    DeferredWorkMetricsRequest,
    DeferredWorkReaperRequest,
)
from src.contracts.files import ReadTextRequest
from src.contracts.logging import LoggingSetupRequest
from src.contracts.remediation import (
    RemediationListRequest,
    RemediationReaperRequest,
    RemediationSoakReportRequest,
)
from src.contracts.run_context import RunContext
from src.orchestrators.deferred_work_orchestrator import (
    run_bounded_deferred_work_reaper,
)
from src.orchestrators.recovery_adapter_registry import (
    build_recovery_adapter_registry,
)
from src.orchestrators.remediation_orchestrator import (
    build_remediation_opportunity_report,
    run_bounded_remediation_reaper,
)
from src.services.config_service import (
    build_ingest_settings,
    load_settings,
    load_workflow_control_settings,
)
from src.services.config_service import new_runtime_context as new_run_context
from src.services.file_service import read_text
from src.services.llm_usage_ledger_service import (
    deferred_work_metrics,
    list_deferred_work,
)
from src.services.logging_service import setup_logging
from src.services.state_service import (
    list_remediation_records,
    read_remediation_soak_report,
)
from src.utils.clock import utc_now_seconds_z


@cli_app.command("remediations")
def list_remediations(
    state_db: str | None = typer.Option(
        None, help="Optional state database path; defaults to application settings."
    ),
    status: list[str] | None = typer.Option(
        None,
        "--status",
        help="Optional remediation state filter; repeat as needed.",
    ),
    limit: int = typer.Option(50, min=1, max=500, help="Maximum records to display."),
) -> None:
    """Show concise canonical remediation state without raw diagnostics."""

    ctx = new_run_context(task_id="cli_remediations")
    setup_logging(LoggingSetupRequest(schema_version="1.0"), ctx)
    resolved_state_db = str(state_db or "").strip()
    if not resolved_state_db:
        settings = load_settings(ConfigLoadRequest(schema_version="1.0", path=""), ctx)
        resolved_state_db = settings.state_db
    records = list_remediation_records(
        RemediationListRequest(
            schema_version="1.0",
            state_db=resolved_state_db,
            statuses=list(status or []),
            limit=limit,
        ),
        ctx,
    ).records
    table = Table(title="Durable Remediation Ledger", box=box.SIMPLE_HEAVY)
    for heading in (
        "ID",
        "Workflow",
        "State",
        "Failure",
        "Action",
        "Attempts",
        "Checkpoint",
        "Next action",
    ):
        table.add_column(heading)
    for record in records:
        table.add_row(
            record.remediation_id,
            record.workflow,
            record.status,
            record.error_code,
            record.action_code,
            f"{record.attempt_count}/{record.max_attempts}",
            record.checkpoint.stage_name if record.checkpoint else "",
            record.operator_next_action,
        )
    console.print(table)


def _runbook_codes(path: str, ctx: RunContext) -> list[str]:
    payload = (
        yaml.safe_load(
            read_text(ReadTextRequest(schema_version="1.0", path=path), ctx).content
        )
        or {}
    )
    runbooks = payload.get("runbooks") if isinstance(payload, dict) else []
    if not isinstance(runbooks, list):
        return []
    return sorted(
        {
            str(item.get("failure_code") or "").strip()
            for item in runbooks
            if isinstance(item, dict) and str(item.get("failure_code") or "").strip()
        }
    )


@cli_app.command("remediation-soak")
def remediation_soak(
    state_db: str | None = typer.Option(
        None, help="Optional state database path; defaults to application settings."
    ),
    registry: str = typer.Option(
        "docs/ops/failure_remediation.yaml",
        help="Approved runbook registry used only for mapping validation.",
    ),
    now_utc: str | None = typer.Option(
        None, help="Optional ISO-8601 UTC observation time for reproducible reads."
    ),
) -> None:
    """Report remediation soak evidence without claiming leases or executing repairs."""

    ctx = new_run_context(task_id="cli_remediation_soak")
    setup_logging(LoggingSetupRequest(schema_version="1.0"), ctx)
    resolved_state_db = str(state_db or "").strip()
    if not resolved_state_db:
        settings = load_settings(ConfigLoadRequest(schema_version="1.0", path=""), ctx)
        resolved_state_db = settings.state_db
    report = read_remediation_soak_report(
        RemediationSoakReportRequest(
            schema_version="1.0",
            state_db=resolved_state_db,
            now_utc=str(now_utc or "").strip() or utc_now_seconds_z(),
            runbook_error_codes=_runbook_codes(registry, ctx),
        ),
        ctx,
    )
    table = Table(title="Read-only Remediation Soak", box=box.SIMPLE_HEAVY)
    table.add_column("Signal")
    table.add_column("Count", justify="right")
    table.add_column("IDs / codes")
    for label, values in (
        ("created records", report.created_record_ids),
        ("deduplicated records", report.deduplicated_record_ids),
        ("stale leases", report.stale_lease_ids),
        ("eligible records", report.eligible_record_ids),
        ("held records", report.held_record_ids),
        ("missing runbook mappings", report.missing_runbook_error_codes),
    ):
        table.add_row(label, str(len(values)), ", ".join(values) or "—")
    console.print(table)


@cli_app.command("remediation-opportunities")
def remediation_opportunities(
    state_db: str | None = typer.Option(
        None, help="Optional state database path; defaults to application settings."
    ),
    registry: str = typer.Option(
        "docs/ops/failure_remediation.yaml",
        help="Approved runbook registry used only for read-only grouping.",
    ),
    now_utc: str | None = typer.Option(
        None, help="Optional ISO-8601 UTC observation time for reproducible reads."
    ),
    limit: int = typer.Option(500, min=1, max=500, help="Maximum retained rows read."),
) -> None:
    """Prioritise repeated remediation work without leasing or executing it."""

    ctx = new_run_context(task_id="cli_remediation_opportunities")
    setup_logging(LoggingSetupRequest(schema_version="1.0"), ctx)
    resolved_state_db = str(state_db or "").strip()
    if not resolved_state_db:
        settings = load_settings(ConfigLoadRequest(schema_version="1.0", path=""), ctx)
        resolved_state_db = settings.state_db
    observation_time = str(now_utc or "").strip() or utc_now_seconds_z()
    records = list_remediation_records(
        RemediationListRequest(
            schema_version="1.0", state_db=resolved_state_db, limit=limit
        ),
        ctx,
    ).records
    report = build_remediation_opportunity_report(
        records,
        observed_at_utc=observation_time,
        runbook_error_codes=set(_runbook_codes(registry, ctx)),
    )
    console.print_json(data=asdict(report))


@cli_app.command("remediation-reap")
def reap_remediations(
    worker_id: str = typer.Option(
        "", help="Stable worker identity; defaults to the current process."
    ),
    now_utc: str | None = typer.Option(
        None, help="Optional ISO-8601 UTC time for reproducible invocation."
    ),
) -> None:
    """Run one bounded, feature-gated, typed checkpoint-recovery pass."""

    ctx = new_run_context(task_id="cli_remediation_reap")
    setup_logging(LoggingSetupRequest(schema_version="1.0"), ctx)
    app_settings = load_settings(ConfigLoadRequest(schema_version="1.0", path=""), ctx)
    ingest_settings = build_ingest_settings(
        IngestSettingsBuildRequest(schema_version="1.0", app_settings=app_settings), ctx
    )
    control = load_workflow_control_settings(
        ConfigLoadRequest(schema_version="1.0", path=""), ctx
    )
    registry = build_recovery_adapter_registry(
        ingest_settings=ingest_settings,
        workflow_control_settings=control,
    )
    reaper = control.remediation_reaper
    response = run_bounded_remediation_reaper(
        RemediationReaperRequest(
            schema_version="1.0",
            state_db=ingest_settings.state_db,
            worker_id=str(worker_id or f"cli-remediation:{os.getpid()}"),
            now_utc=str(now_utc or "").strip() or utc_now_seconds_z(),
            execution_enabled=reaper.execution_enabled,
            limit=reaper.max_records_per_run,
            lease_seconds=reaper.lease_seconds,
        ),
        ctx,
        dependencies=registry.remediation_dependencies,
    )
    completed_ids = set(response.resolved_ids)
    recovered = list_remediation_records(
        RemediationListRequest(
            schema_version="1.0",
            state_db=ingest_settings.state_db,
            limit=max(1, reaper.max_records_per_run),
        ),
        ctx,
    ).records
    avoided_stages = sorted(
        {
            stage
            for record in recovered
            if record.remediation_id in completed_ids
            for stage in record.diagnostics.get("avoided_stages", [])
            if isinstance(stage, str)
        }
    )
    avoided_calls = sorted(
        {
            call
            for record in recovered
            if record.remediation_id in completed_ids
            for call in record.diagnostics.get("avoided_provider_calls", [])
            if isinstance(call, str)
        }
    )
    console.print(
        "Remediation reaper: "
        f"inspected={response.inspected_count}, "
        f"resolved={len(response.resolved_ids)}, "
        f"deferred={len(response.deferred_ids)}, "
        f"terminal_or_held={len(response.held_ids)}, "
        f"avoided_stages={','.join(avoided_stages) or 'none'}, "
        f"avoided_provider_calls={','.join(avoided_calls) or 'none'}, "
        "avoided_tokens=unpriced, avoided_cost_usd=unpriced"
    )


@cli_app.command("deferred-work")
def list_deferred_work_items(
    usage_db: str | None = typer.Option(
        None, help="Optional usage-ledger path; defaults to application settings."
    ),
    limit: int = typer.Option(50, min=1, max=500, help="Maximum items to display."),
) -> None:
    """Show durable budget-deferred work and bounded queue health metrics."""

    ctx = new_run_context(task_id="cli_deferred_work")
    setup_logging(LoggingSetupRequest(schema_version="1.0"), ctx)
    settings = load_settings(ConfigLoadRequest(schema_version="1.0", path=""), ctx)
    usage_db_path = str(usage_db or settings.usage_db_path).strip()
    now_utc = utc_now_seconds_z()
    metrics = deferred_work_metrics(
        DeferredWorkMetricsRequest(
            schema_version="1.0", usage_db_path=usage_db_path, now_utc=now_utc
        ),
        ctx,
    )
    records = list_deferred_work(
        DeferredWorkListRequest(
            schema_version="1.0", usage_db_path=usage_db_path, limit=limit
        ),
        ctx,
    ).records
    console.print(
        "Deferred work: "
        f"depth={metrics.queue_depth}, due={metrics.due_count}, "
        f"leased={metrics.lease_count}, terminal={metrics.terminal_count}, "
        f"completion_rate={metrics.completion_rate:.0%}"
    )
    table = Table(title="Durable Budget-Deferred Work", box=box.SIMPLE_HEAVY)
    for heading in (
        "Workflow",
        "Stage",
        "State",
        "Limit",
        "Attempts",
        "Earliest UTC",
        "Terminal",
    ):
        table.add_column(heading)
    for item in records:
        table.add_row(
            item.workflow,
            item.stage,
            item.status,
            item.affected_limit,
            f"{item.attempt_count}/{item.max_attempts}",
            item.earliest_run_at_utc,
            item.terminal_status,
        )
    console.print(table)


@cli_app.command("deferred-work-reap")
def reap_deferred_work(
    worker_id: str = typer.Option(
        "", help="Stable worker identity; defaults to the current process."
    ),
    now_utc: str | None = typer.Option(
        None, help="Optional ISO-8601 UTC time for reproducible invocation."
    ),
) -> None:
    """Run one feature-gated bounded deferred-work recovery pass; never poll."""

    ctx = new_run_context(task_id="cli_deferred_work_reap")
    setup_logging(LoggingSetupRequest(schema_version="1.0"), ctx)
    app_settings = load_settings(ConfigLoadRequest(schema_version="1.0", path=""), ctx)
    ingest_settings = build_ingest_settings(
        IngestSettingsBuildRequest(schema_version="1.0", app_settings=app_settings), ctx
    )
    control = load_workflow_control_settings(
        ConfigLoadRequest(schema_version="1.0", path=""), ctx
    )
    reaper = control.deferred_work_reaper
    registry = build_recovery_adapter_registry(
        ingest_settings=ingest_settings,
        workflow_control_settings=control,
    )
    response = run_bounded_deferred_work_reaper(
        DeferredWorkReaperRequest(
            schema_version="1.0",
            usage_db_path=ingest_settings.usage_db_path,
            state_db=ingest_settings.state_db,
            worker_id=str(worker_id or f"cli-deferred-work:{os.getpid()}"),
            now_utc=str(now_utc or "").strip() or utc_now_seconds_z(),
            execution_enabled=reaper.execution_enabled,
            limit=reaper.max_records_per_run,
            lease_seconds=reaper.lease_seconds,
            retry_delay_seconds=reaper.retry_delay_seconds,
        ),
        ctx,
        dependencies=registry.deferred_work_dependencies,
    )
    console.print(
        "Deferred-work reaper: "
        f"inspected={response.inspected_count}, "
        f"completed={len(response.completed_work_keys)}, "
        f"deferred={len(response.deferred_work_keys)}, "
        f"remediation={len(response.remediation_work_keys)}, "
        f"released_leases={len(response.released_lease_work_keys)}"
    )


__all__ = [
    "list_deferred_work_items",
    "list_remediations",
    "remediation_opportunities",
    "reap_remediations",
    "reap_deferred_work",
    "remediation_soak",
]
