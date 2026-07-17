# ruff: noqa: B008
from __future__ import annotations

import typer
import yaml
from rich import box
from rich.table import Table

from src._cli.app import cli_app, console
from src.contracts.config import ConfigLoadRequest
from src.contracts.files import ReadTextRequest
from src.contracts.logging import LoggingSetupRequest
from src.contracts.remediation import (
    RemediationListRequest,
    RemediationSoakReportRequest,
)
from src.contracts.run_context import RunContext
from src.services.config_service import load_settings
from src.services.file_service import read_text
from src.services.logging_service import setup_logging
from src.services.state_service import (
    list_remediation_records,
    read_remediation_soak_report,
)
from src.utils.clock import utc_now_seconds_z
from src.utils.logging import new_run_context


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


__all__ = ["list_remediations", "remediation_soak"]
