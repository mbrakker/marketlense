from __future__ import annotations


import typer
from rich.table import Table
from rich import box

from src.utils.errors import AppError
from src.contracts.acquisition_audit import AcquisitionAuditBatchRequest
from src.contracts.config import ConfigLoadRequest
from src.contracts.logging import LoggingSetupRequest
from src.contracts.publisher_inventory import PublisherInventoryDiscoveryRequest
from src.orchestrators.acquisition_audit_orchestrator import run_acquisition_audit
from src.orchestrators.publisher_inventory_orchestrator import (
    run_publisher_inventory_discovery,
)
from src.services.config_service import (
    load_browser_download_settings,
    load_publisher_inventory_settings,
    load_settings,
)
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


@cli_app.command("discover-publisher-inventory")
def discover_publisher_inventory(
    insights_url: str = typer.Argument(..., help="Publisher insights URL to crawl"),
):
    _sync_cli_patch_points()
    ctx = new_run_context(task_id="cli_discover_publisher_inventory")
    setup_logging(LoggingSetupRequest(schema_version="1.0"), ctx)
    settings = load_publisher_inventory_settings(
        ConfigLoadRequest(schema_version="1.0", path=""),
        ctx,
    )
    try:
        result = run_publisher_inventory_discovery(
            PublisherInventoryDiscoveryRequest(
                schema_version="1.0",
                insights_url=insights_url,
                reports_db=settings.reports_db,
                settings=settings,
                state_db=load_settings(
                    ConfigLoadRequest(schema_version="1.0", path=""), ctx
                ).state_db,
            ),
            ctx=ctx,
        )
    except AppError as exc:
        if exc.code == "publisher_inventory_browser_pagination_limit":
            table = Table(title="Publisher Inventory Discovery", box=box.SIMPLE_HEAVY)
            table.add_column("Field")
            table.add_column("Value")
            table.add_row("Insights URL", insights_url)
            table.add_row("Outcome", "bounded")
            table.add_row("Status code", exc.code)
            table.add_row("Message", exc.message)
            console.print(table)
            return
        raise
    table = Table(title="Publisher Inventory Discovery", box=box.SIMPLE_HEAVY)
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("Publisher", result.publisher_name)
    table.add_row("Insights URL", result.insights_url)
    table.add_row("Normalized URL", result.normalized_insights_url)
    table.add_row("Current reports", str(result.current_report_count))
    table.add_row("Previous reports", str(result.previous_report_count))
    table.add_row("Used memory route", "yes" if result.used_memory_route else "no")
    table.add_row("Snapshot changed", "yes" if result.snapshot_changed else "no")
    table.add_row("Run quality", result.run_quality_summary.quality_band)
    table.add_row("Run outcome", result.run_quality_summary.outcome)
    table.add_row(
        "Next route",
        result.run_quality_summary.recommended_route_kind,
    )
    console.print(table)

    diff_table = Table(title="New Report URLs", box=box.SIMPLE_HEAVY)
    diff_table.add_column("Page")
    diff_table.add_column("Title")
    diff_table.add_column("URL")
    for item in result.new_report_urls:
        diff_table.add_row(
            str(item.discovered_on_page_number),
            item.title,
            item.canonical_url,
        )
    console.print(diff_table)


@cli_app.command("audit-acquisition-paths")
def audit_acquisition_paths(
    publisher_limit: int = typer.Option(
        None,
        help="Optional maximum number of current publishers to audit",
    ),
    candidate_limit_per_publisher: int = typer.Option(
        None,
        help="Optional maximum number of current candidates to audit per publisher",
    ),
    delivery_email: str = typer.Option(
        None,
        help="Optional delivery email used when a report is gated behind email delivery",
    ),
):
    _sync_cli_patch_points()
    ctx = new_run_context(task_id="cli_audit_acquisition_paths")
    setup_logging(LoggingSetupRequest(schema_version="1.0"), ctx)
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="cli_audit_acquisition_paths_start",
            module=logger.name,
            fields={
                "publisher_limit": publisher_limit,
                "candidate_limit_per_publisher": candidate_limit_per_publisher,
                "has_delivery_email": bool(delivery_email),
            },
        )
    )
    app_settings = load_settings(ConfigLoadRequest(schema_version="1.0", path=""), ctx)
    publisher_inventory_settings = load_publisher_inventory_settings(
        ConfigLoadRequest(schema_version="1.0", path=""),
        ctx,
    )
    browser_download_settings = load_browser_download_settings(
        ConfigLoadRequest(schema_version="1.0", path=""),
        ctx,
    )
    result = run_acquisition_audit(
        AcquisitionAuditBatchRequest(
            schema_version="1.0",
            reports_db=app_settings.reports_db,
            publisher_inventory_settings=publisher_inventory_settings,
            browser_download_settings=browser_download_settings,
            output_dir=app_settings.output_dir,
            delivery_email=delivery_email,
            publisher_limit=publisher_limit,
            candidate_limit_per_publisher=candidate_limit_per_publisher,
        ),
        ctx=ctx,
    )

    summary_table = Table(title="Acquisition Audit", box=box.SIMPLE_HEAVY)
    summary_table.add_column("Field")
    summary_table.add_column("Value")
    summary_table.add_row("Generated at", result.generated_at_utc)
    summary_table.add_row("Artifact", result.output_path)
    summary_table.add_row("Publishers", str(result.publisher_count))
    summary_table.add_row("Candidates", str(result.candidate_count))
    console.print(summary_table)

    publisher_table = Table(title="Publisher Recommendations", box=box.SIMPLE_HEAVY)
    publisher_table.add_column("Publisher")
    publisher_table.add_column("Candidates", justify="right")
    publisher_table.add_column("Discovery")
    publisher_table.add_column("Recommendation")
    for publisher in result.publishers:
        publisher_table.add_row(
            publisher.publisher_name,
            str(publisher.current_candidate_count),
            publisher.recommended_discovery_route_kind,
            publisher.recommended_publisher_flow,
        )
    console.print(publisher_table)
