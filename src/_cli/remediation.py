# ruff: noqa: B008
from __future__ import annotations

import typer
from rich import box
from rich.table import Table

from src._cli.app import cli_app, console
from src.contracts.config import ConfigLoadRequest
from src.contracts.logging import LoggingSetupRequest
from src.contracts.remediation import RemediationListRequest
from src.services.config_service import load_settings
from src.services.logging_service import setup_logging
from src.services.state_service import list_remediation_records
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


__all__ = ["list_remediations"]
