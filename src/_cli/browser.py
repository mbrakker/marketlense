from __future__ import annotations

import json
from dataclasses import asdict

import typer
from rich.table import Table
from rich import box

from src.contracts.browser_download import ReportDownloadOrchestratorRequest
from src.contracts.browser_download import BrowserDeveloperDiagnosticsRequest
from src.contracts.browser_download import BrowserDownloadSessionReusePolicy
from src.contracts.mailbox_acquisition import MailReportAcquisitionRequest
from src.contracts.config import ConfigLoadRequest
from src.contracts.logging import LoggingSetupRequest
from src.orchestrators.mail_report_acquisition_orchestrator import (
    run_mail_report_acquisition,
)
from src.orchestrators.report_download_orchestrator import run_report_download
from src.services.config_service import (
    load_browser_download_settings,
    load_mailbox_acquisition_settings,
)
from src.services.browser_report_download_service import (
    default_browser_doctor_verification_url,
    run_browser_developer_diagnostics,
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
    "load_mailbox_acquisition_settings",
    "load_publish_settings",
    "load_publisher_inventory_settings",
    "load_settings",
    "promote_private_api_evidence_to_browser_playbook",
    "read_text",
    "replay_ui_run",
    "run_acquisition_audit",
    "run_browser_developer_diagnostics",
    "run_mail_report_acquisition",
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


@cli_app.command("download-report")
def download_report(
    url: str = typer.Argument(..., help="Absolute report landing-page URL"),
    delivery_email: str = typer.Option(
        None,
        help="Optional email address used when the report is gated behind an email form",
    ),
    publisher_insights_url: str = typer.Option(
        None,
        help="Optional publisher insights URL used to resolve the publisher Drive folder",
    ),
    publisher_google_folder: str = typer.Option(
        None,
        help="Optional publisher Drive folder URL or folder ID for acquired artifacts",
    ),
    report_title: str = typer.Option(
        "",
        help="Optional report title used to match deferred mailbox delivery",
    ),
    publisher_name: str = typer.Option(
        "",
        help="Optional publisher name used to match deferred mailbox delivery",
    ),
):
    _sync_cli_patch_points()
    ctx = new_run_context(task_id="cli_download_report")
    setup_logging(LoggingSetupRequest(schema_version="1.0"), ctx)
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="cli_download_report_start",
            module=logger.name,
            fields={
                "url": url,
                "has_delivery_email": bool(delivery_email),
                "has_publisher_insights_url": bool(publisher_insights_url),
                "has_publisher_google_folder": bool(publisher_google_folder),
            },
        )
    )
    settings = load_browser_download_settings(
        ConfigLoadRequest(schema_version="1.0", path=""),
        ctx,
    )
    mailbox_settings = load_mailbox_acquisition_settings(
        ConfigLoadRequest(schema_version="1.0", path=""),
        ctx,
    )
    result = run_report_download(
        ReportDownloadOrchestratorRequest(
            schema_version="1.0",
            url=url,
            settings=settings,
            state_db=settings.state_db,
            reports_db=settings.reports_db,
            delivery_email=delivery_email,
            publisher_insights_url=publisher_insights_url,
            publisher_google_folder=publisher_google_folder,
            report_title=report_title,
            publisher_name=publisher_name,
            mailbox_settings=mailbox_settings,
        ),
        ctx=ctx,
    )

    table = Table(title="Report Download", box=box.SIMPLE_HEAVY)
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("URL", result.source_url)
    table.add_row("Normalized URL", result.normalized_url)
    table.add_row("Route", result.route_kind)
    table.add_row("Outcome", result.outcome)
    table.add_row("Used memory route", "yes" if result.used_memory_route else "no")
    table.add_row("Final page", result.final_page_url)
    table.add_row(
        "Encountered form fields",
        ", ".join(result.encountered_form_fields),
    )
    table.add_row(
        "Identity fields added",
        ", ".join(result.identity_fields_added),
    )
    table.add_row("File", result.downloaded_file_path or "")
    table.add_row(
        "Drive uploads",
        ", ".join(
            f"{item.status}:{item.drive_file.file_id}" for item in result.drive_uploads
        ),
    )
    table.add_row("Summary", result.route_summary)
    console.print(table)


@cli_app.command("poll-mail-report")
def poll_mail_report(
    source_url: str = typer.Argument(
        ...,
        help="Original report landing-page URL that requested email delivery",
    ),
    report_title: str = typer.Option(
        "",
        help="Report title used to identify the delivered email",
    ),
    publisher_name: str = typer.Option(
        "",
        help="Publisher name used to identify the delivered email",
    ),
    delivery_email: str = typer.Option(
        None,
        help="Delivery email submitted to the publisher form",
    ),
    requested_after_utc: str = typer.Option(
        None,
        help="Optional UTC request watermark; older matching emails are ignored",
    ),
):
    _sync_cli_patch_points()
    ctx = new_run_context(task_id="cli_poll_mail_report")
    setup_logging(LoggingSetupRequest(schema_version="1.0"), ctx)
    browser_settings = load_browser_download_settings(
        ConfigLoadRequest(schema_version="1.0", path=""),
        ctx,
    )
    mailbox_settings = load_mailbox_acquisition_settings(
        ConfigLoadRequest(schema_version="1.0", path=""),
        ctx,
    )
    result = run_mail_report_acquisition(
        MailReportAcquisitionRequest(
            schema_version="1.0",
            source_url=source_url,
            report_title=report_title,
            publisher_name=publisher_name,
            delivery_email=delivery_email,
            reports_db=browser_settings.reports_db,
            mailbox_settings=mailbox_settings,
            browser_download_settings=browser_settings,
            requested_after_utc=requested_after_utc,
        ),
        ctx=ctx,
    )
    table = Table(title="Mail Report Acquisition", box=box.SIMPLE_HEAVY)
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("Source URL", result.source_url)
    table.add_row("Outcome", result.outcome)
    table.add_row("Mailbox polls", str(result.mailbox_poll_count))
    table.add_row("Selected report URL", result.selected_report_url or "")
    table.add_row("Selected message", result.selected_message_id or "")
    table.add_row("File", result.downloaded_file_path or "")
    console.print(table)


@cli_app.command("browser-doctor")
def browser_doctor(
    profile_dir: str = typer.Option(
        "out/browser_doctor/profile",
        help="Browser-use profile directory for the diagnostic run.",
    ),
    downloads_dir: str = typer.Option(
        "out/browser_doctor/downloads",
        help="Browser-use downloads directory for the diagnostic run.",
    ),
    verification_url: str = typer.Option(
        "",
        help="URL opened to verify browser-use tab/CDP state.",
    ),
    cdp_url: str = typer.Option(
        "",
        help="Optional existing Chrome remote-debugging URL to connect to.",
    ),
    headed: bool = typer.Option(
        False,
        "--headed",
        help="Run the diagnostic browser headed for manual inspection.",
    ),
    keep_browser_open: bool = typer.Option(
        False,
        "--keep-browser-open",
        help="Leave the diagnostic browser open after checks complete.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Print the diagnostic result as JSON.",
    ),
    timeout_seconds: float = typer.Option(
        20.0,
        "--timeout-seconds",
        help="Per-operation browser diagnostic timeout.",
    ),
    reuse_session_key: str = typer.Option(
        "",
        "--reuse-session-key",
        help="Optional developer-canary browser session key for bounded profile reuse.",
    ),
    reuse_publisher_scope: str = typer.Option(
        "",
        "--reuse-publisher-scope",
        help="Publisher/domain scope allowed to reuse the browser session key.",
    ),
    reuse_ttl_seconds: float = typer.Option(
        0.0,
        "--reuse-ttl-seconds",
        help="TTL in seconds for developer-canary browser session profile reuse.",
    ),
    reuse_base_dir: str = typer.Option(
        "",
        "--reuse-base-dir",
        help="Optional base directory for reusable browser session profiles.",
    ),
):
    _sync_cli_patch_points()
    ctx = new_run_context(task_id="cli_browser_doctor")
    setup_logging(LoggingSetupRequest(schema_version="1.0"), ctx)
    selected_verification_url = (
        str(verification_url or "").strip() or default_browser_doctor_verification_url()
    )
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="cli_browser_doctor_start",
            module=logger.name,
            fields={
                "profile_dir": profile_dir,
                "downloads_dir": downloads_dir,
                "verification_url": selected_verification_url,
                "has_cdp_url": bool(str(cdp_url or "").strip()),
                "headed": headed,
                "keep_browser_open": keep_browser_open,
            },
        )
    )
    result = run_browser_developer_diagnostics(
        BrowserDeveloperDiagnosticsRequest(
            schema_version="1.0",
            profile_path=profile_dir,
            downloads_path=downloads_dir,
            headed=bool(headed),
            verification_url=selected_verification_url,
            cdp_url=str(cdp_url or "").strip(),
            activate_verification_tab=True,
            cleanup_stale_once=True,
            keep_browser_open=bool(keep_browser_open),
            timeout_seconds=float(timeout_seconds),
            session_reuse_policy=BrowserDownloadSessionReusePolicy(
                schema_version="1.0",
                enabled=bool(str(reuse_session_key or "").strip()),
                mode="developer_canary",
                session_key=str(reuse_session_key or "").strip(),
                publisher_scope=str(reuse_publisher_scope or "").strip(),
                ttl_seconds=float(reuse_ttl_seconds),
                base_dir=str(reuse_base_dir or "").strip(),
                cleanup_expired=True,
                allow_cross_publisher=False,
            ),
        ),
        ctx,
    )
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="cli_browser_doctor_complete",
            module=logger.name,
            fields={
                "status": result.status,
                "browser_use_connected": result.browser_use_connected,
                "cdp_available": result.cdp_available,
                "real_tab_available": result.real_tab_available,
                "cleanup_attempted": result.cleanup_attempted,
                "cleanup_status": result.cleanup_status,
                "verification_tab_activated": result.verification_tab_activated,
            },
        )
    )
    if json_output:
        console.print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    else:
        table = Table(title="Browser Doctor", box=box.SIMPLE_HEAVY)
        table.add_column("Check")
        table.add_column("Status")
        table.add_column("Message")
        table.add_column("Detail")
        for check in result.checks:
            table.add_row(check.name, check.status, check.message, check.detail)
        console.print(table)
        console.print(f"[cyan]Profile:[/cyan] {result.profile_path}")
        console.print(f"[cyan]Downloads:[/cyan] {result.downloads_path}")
        console.print(f"[cyan]Active tab:[/cyan] {result.active_tab_url}")
        console.print(f"[cyan]CDP URL:[/cyan] {result.cdp_url or '(not exposed)'}")
    if result.status == "failed":
        raise typer.Exit(code=1)
    console.print(f"[green]Done: browser doctor {result.status}.[/green]")
