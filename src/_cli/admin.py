from __future__ import annotations

import os

import typer
from rich.table import Table
from rich import box

from src.contracts.config import ConfigLoadRequest
from src.contracts.drive import DriveOAuthAuthorizeRequest
from src.contracts.logging import LoggingSetupRequest
from src.contracts.publisher_profiles import PublisherSyncRequest
from src.orchestrators.publisher_sync_orchestrator import run_publisher_sync
from src.services.config_service import (
    load_settings,
)
from src.services.drive_service import authorize_oauth_user
from src.services.logging_service import setup_logging
from src.utils.logging import log_event, new_run_context

from src._cli.app import cli_app, console, logger
from src._cli.runtime import sync_cli_patch_points

_CLI_PATCH_POINTS = (
    "authorize_oauth_user",
    "build_ingest_settings",
    "console",
    "default_browser_doctor_verification_url",
    "default_ui_run_registry_path",
    "execute_ui_run",
    "get_ui_run_record",
    "load_browser_download_settings",
    "load_publish_settings",
    "load_publisher_inventory_settings",
    "load_settings",
    "promote_private_api_evidence_to_browser_playbook",
    "read_text",
    "replay_ui_run",
    "run_acquisition_audit",
    "run_browser_developer_diagnostics",
    "run_candidate_extraction",
    "run_cost_reporting",
    "run_cover_image_generation",
    "run_cross_report_analysis_orchestrator",
    "run_ingest",
    "run_publish",
    "run_publisher_inventory_discovery",
    "run_publisher_sync",
    "run_recategorize",
    "run_report_download",
    "run_update_wp_categories",
    "setup_logging",
    "write_ui_run_record",
    "write_ui_run_replay_manifest",
)


def _sync_cli_patch_points() -> None:
    sync_cli_patch_points(globals(), _CLI_PATCH_POINTS)



@cli_app.command("drive-oauth-login")
def drive_oauth_login(
    client_json: str = typer.Option(
        "",
        help="Path to the Google OAuth desktop client JSON",
    ),
    token_json: str = typer.Option(
        "",
        help="Path where the authorized-user token JSON should be written",
    ),
    open_browser: bool = typer.Option(
        True,
        "--open-browser/--no-browser",
        help="Open the system browser for the OAuth consent flow",
    ),
    port: int = typer.Option(
        0,
        help="Local loopback port for the OAuth callback server; 0 picks a free port",
    ),
):
    _sync_cli_patch_points()
    ctx = new_run_context(task_id="cli_drive_oauth_login")
    setup_logging(LoggingSetupRequest(schema_version="1.0"), ctx)
    resolved_client_json = (
        client_json.strip() or os.getenv("GOOGLE_OAUTH_CLIENT_JSON", "").strip()
    )
    resolved_token_json = (
        token_json.strip() or os.getenv("GOOGLE_OAUTH_TOKEN_JSON", "").strip()
    )
    if not resolved_client_json:
        console.print(
            "[red]Missing OAuth client JSON path. Pass --client-json or set GOOGLE_OAUTH_CLIENT_JSON.[/red]"
        )
        raise typer.Exit(code=1)
    if not resolved_token_json:
        console.print(
            "[red]Missing OAuth token output path. Pass --token-json or set GOOGLE_OAUTH_TOKEN_JSON.[/red]"
        )
        raise typer.Exit(code=1)
    result = authorize_oauth_user(
        DriveOAuthAuthorizeRequest(
            schema_version="1.0",
            client_secret_path=resolved_client_json,
            token_output_path=resolved_token_json,
            open_browser=open_browser,
            port=port,
        ),
        ctx,
    )
    table = Table(title="Drive OAuth Login", box=box.SIMPLE_HEAVY)
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("Token path", result.token_output_path)
    table.add_row("Scopes", ", ".join(result.scopes))
    table.add_row("Refresh token", "yes" if result.refresh_token_present else "no")
    console.print(table)


@cli_app.command("sync-publishers")
def sync_publishers(
    snapshot_path: str = typer.Option(
        None,
        help="Optional override path to the publisher snapshot JSON sourced from Notion",
    ),
):
    _sync_cli_patch_points()
    ctx = new_run_context(task_id="cli_sync_publishers")
    setup_logging(LoggingSetupRequest(schema_version="1.0"), ctx)
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="cli_sync_publishers_start",
            module=logger.name,
            fields={"snapshot_path_override": snapshot_path or ""},
        )
    )
    settings = load_settings(ConfigLoadRequest(schema_version="1.0", path=""), ctx)
    result = run_publisher_sync(
        PublisherSyncRequest(
            schema_version="1.0",
            snapshot_path=snapshot_path or settings.publisher_profiles_path,
            reports_db=settings.reports_db,
        ),
        ctx=ctx,
    )

    table = Table(title="Publishers Sync", box=box.SIMPLE_HEAVY)
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("Snapshot", result.snapshot_path)
    table.add_row("Reports DB", result.reports_db)
    table.add_row("Source page", result.source_page_url)
    table.add_row("Replaced publishers", str(result.replaced_count))
    console.print(table)
