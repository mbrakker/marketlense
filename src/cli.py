from __future__ import annotations

import logging
import os
import json

import typer
from rich.console import Console
from rich.table import Table
from rich import box

from src.utils.errors import AppError
from src.contracts.acquisition_audit import AcquisitionAuditBatchRequest
from src.contracts.costs import CostReportRequest, CostReportingRequest
from src.contracts.browser_download import ReportDownloadOrchestratorRequest
from src.contracts.categories import RecategorizeRequest
from src.contracts.config import ConfigLoadRequest, IngestSettingsBuildRequest
from src.contracts.cover_images import CoverImageOrchestratorRequest
from src.contracts.drive import DriveOAuthAuthorizeRequest
from src.contracts.logging import LoggingSetupRequest
from src.contracts.publisher_inventory import PublisherInventoryDiscoveryRequest
from src.contracts.publisher_profiles import PublisherSyncRequest
from src.contracts.ui_run_control import (
    UiRunRecord,
    UiRunRecordGetRequest,
    UiRunRecordWriteRequest,
    UiRunWorkerRequest,
)
from src.orchestrators.report_download_orchestrator import run_report_download
from src.orchestrators.acquisition_audit_orchestrator import run_acquisition_audit
from src.orchestrators.cost_reporting_orchestrator import run_cost_reporting
from src.orchestrators.ingest_orchestrator import run_ingest
from src.orchestrators.candidate_extraction_orchestrator import run_candidate_extraction
from src.orchestrators.cover_image_orchestrator import run_cover_image_generation
from src.orchestrators.publisher_inventory_orchestrator import (
    run_publisher_inventory_discovery,
)
from src.orchestrators.publisher_sync_orchestrator import run_publisher_sync
from src.orchestrators.publish_orchestrator import run_publish
from src.orchestrators.recategorize_orchestrator import run_recategorize
from src.orchestrators.wp_category_update_orchestrator import run_update_wp_categories
from src.services.config_service import (
    build_ingest_settings,
    load_browser_download_settings,
    load_publisher_inventory_settings,
    load_settings,
    load_publish_settings,
)
from src.services.drive_service import authorize_oauth_user
from src.services.logging_service import setup_logging
from src.services.run_registry_service import get_ui_run_record, write_ui_run_record
from src.utils.logging import log_event, new_run_context


cli_app = typer.Typer(add_completion=False, help="PDF -> Structured HTML digests")
console = Console()
logger = logging.getLogger("market_lense.cli")


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _load_ui_run_worker_request(path: str) -> UiRunWorkerRequest:
    request_path = str(path or "").strip()
    if not request_path:
        raise AppError(
            code="ui_run_worker_request_missing",
            message="UI run worker request path is required",
            retryable=False,
        )
    try:
        payload = json.loads(open(request_path, "r", encoding="utf-8").read())
    except FileNotFoundError as exc:
        raise AppError(
            code="ui_run_worker_request_missing",
            message=f"UI run worker request not found: {request_path}",
            cause=exc,
            retryable=False,
        ) from exc
    except json.JSONDecodeError as exc:
        raise AppError(
            code="ui_run_worker_request_invalid",
            message=f"UI run worker request JSON invalid: {request_path}",
            cause=exc,
            retryable=False,
        ) from exc
    if not isinstance(payload, dict):
        raise AppError(
            code="ui_run_worker_request_invalid",
            message=f"UI run worker request root must be an object: {request_path}",
            retryable=False,
        )
    return UiRunWorkerRequest(
        schema_version=str(payload.get("schema_version", "1.0")),
        registry_path=str(payload.get("registry_path") or "").strip(),
        run_id=str(payload.get("run_id") or "").strip(),
        run_type=str(payload.get("run_type") or "").strip(),
        request_payload=dict(payload.get("request_payload") or {}),
    )


def _update_ui_run_record(
    *,
    worker_request: UiRunWorkerRequest,
    run_ctx,
    status: str,
    started_at_utc: str | None = None,
    finished_at_utc: str | None = None,
    pid: int | None = None,
    exit_code: int | None = None,
    result_summary: dict[str, object] | None = None,
    artifact_paths: list[str] | None = None,
    error_code: str = "",
    error_message: str = "",
) -> UiRunRecord:
    existing = get_ui_run_record(
        UiRunRecordGetRequest(
            schema_version="1.0",
            registry_path=worker_request.registry_path,
            run_id=worker_request.run_id,
        ),
        run_ctx,
    ).record
    if existing is None:
        raise AppError(
            code="ui_run_not_found",
            message=f"UI run record not found for worker: {worker_request.run_id}",
            retryable=False,
        )
    updated = UiRunRecord(
        schema_version="1.0",
        run_id=existing.run_id,
        run_type=existing.run_type,
        display_name=existing.display_name,
        status=status,
        request_payload=existing.request_payload,
        command=existing.command,
        created_at_utc=existing.created_at_utc,
        updated_at_utc=_utc_now(),
        started_at_utc=started_at_utc if started_at_utc is not None else existing.started_at_utc,
        finished_at_utc=finished_at_utc if finished_at_utc is not None else existing.finished_at_utc,
        output_path=existing.output_path,
        request_path=existing.request_path,
        artifact_paths=artifact_paths if artifact_paths is not None else existing.artifact_paths,
        result_summary=result_summary if result_summary is not None else existing.result_summary,
        pid=pid if pid is not None else existing.pid,
        exit_code=exit_code if exit_code is not None else existing.exit_code,
        error_code=error_code,
        error_message=error_message,
    )
    write_ui_run_record(
        UiRunRecordWriteRequest(
            schema_version="1.0",
            registry_path=worker_request.registry_path,
            record=updated,
        ),
        run_ctx,
    )
    return updated


def _run_ui_worker_payload(
    worker_request: UiRunWorkerRequest,
    run_ctx,
) -> tuple[dict[str, object], list[str]]:
    payload = worker_request.request_payload
    run_type = worker_request.run_type
    if run_type == "ingest":
        app_settings = load_settings(ConfigLoadRequest(schema_version="1.0", path=""), run_ctx)
        settings = build_ingest_settings(
            IngestSettingsBuildRequest(schema_version="1.0", app_settings=app_settings),
            run_ctx,
        )
        outcomes = run_ingest(
            settings,
            folder_id=str(payload.get("folder_id") or "").strip() or None,
            limit=int(payload["limit"]) if payload.get("limit") is not None else None,
            ctx=run_ctx,
        )
        processed_count = len([item for item in outcomes if item.status == "processed"])
        return (
            {
                "processed_count": processed_count,
                "total_count": len(outcomes),
            },
            [item.html_path for item in outcomes if item.html_path],
        )
    if run_type == "candidate_extraction":
        app_settings = load_settings(ConfigLoadRequest(schema_version="1.0", path=""), run_ctx)
        settings = build_ingest_settings(
            IngestSettingsBuildRequest(schema_version="1.0", app_settings=app_settings),
            run_ctx,
        )
        outcomes = run_candidate_extraction(
            settings,
            folder_id=str(payload.get("folder_id") or "").strip() or None,
            limit=int(payload["limit"]) if payload.get("limit") is not None else None,
            file_id=str(payload.get("file_id") or "").strip() or None,
            pdf_path=str(payload.get("pdf_path") or "").strip() or None,
            report_id=str(payload.get("report_id") or "").strip() or None,
            ctx=run_ctx,
        )
        artifact_paths: list[str] = []
        for outcome in outcomes:
            if outcome.candidates_path:
                artifact_paths.append(outcome.candidates_path)
            artifact_paths.extend(outcome.crop_paths[:5])
        return (
            {
                "total_count": len(outcomes),
                "candidate_count": sum(item.candidate_count for item in outcomes),
                "chart_count": sum(item.chart_count for item in outcomes),
                "table_count": sum(item.table_count for item in outcomes),
            },
            artifact_paths,
        )
    if run_type == "cover_images":
        settings = load_settings(ConfigLoadRequest(schema_version="1.0", path=""), run_ctx)
        outcomes = run_cover_image_generation(
            CoverImageOrchestratorRequest(
                schema_version="1.0",
                reports_db=settings.reports_db,
                output_dir=settings.output_dir,
                style_config_path=str(payload.get("style_config_path") or "").strip(),
                limit=int(payload["limit"]) if payload.get("limit") is not None else None,
                file_id=str(payload.get("file_id") or "").strip() or None,
            ),
            ctx=run_ctx,
        )
        return (
            {
                "total_count": len(outcomes),
                "generated_count": len([item for item in outcomes if item.status == "generated"]),
            },
            [item.output_path for item in outcomes if item.output_path],
        )
    if run_type == "publish":
        settings = load_publish_settings(ConfigLoadRequest(schema_version="1.0", path=""), run_ctx)
        outcomes = run_publish(
            settings,
            limit=int(payload["limit"]) if payload.get("limit") is not None else None,
            ctx=run_ctx,
        )
        return (
            {
                "total_count": len(outcomes),
                "published_count": len([item for item in outcomes if item.status == "published"]),
            },
            [item.html_path for item in outcomes if item.html_path],
        )
    if run_type == "publisher_discovery":
        settings = load_publisher_inventory_settings(
            ConfigLoadRequest(schema_version="1.0", path=""),
            run_ctx,
        )
        result = run_publisher_inventory_discovery(
            PublisherInventoryDiscoveryRequest(
                schema_version="1.0",
                insights_url=str(payload.get("insights_url") or "").strip(),
                reports_db=settings.reports_db,
                settings=settings,
            ),
            ctx=run_ctx,
        )
        return (
            {
                "publisher_name": result.publisher_name,
                "current_report_count": result.current_report_count,
                "previous_report_count": result.previous_report_count,
                "new_report_count": len(result.new_report_urls),
                "quality_band": result.run_quality_summary.quality_band,
                "recommended_route_kind": result.run_quality_summary.recommended_route_kind,
            },
            [],
        )
    if run_type == "report_download":
        settings = load_browser_download_settings(
            ConfigLoadRequest(schema_version="1.0", path=""),
            run_ctx,
        )
        result = run_report_download(
            ReportDownloadOrchestratorRequest(
                schema_version="1.0",
                url=str(payload.get("url") or "").strip(),
                settings=settings,
                state_db=settings.state_db,
                reports_db=settings.reports_db,
                delivery_email=str(payload.get("delivery_email") or "").strip() or None,
            ),
            ctx=run_ctx,
        )
        artifact_paths = [
            path
            for path in [result.downloaded_file_path, result.onsite_capture_path]
            if path
        ]
        return (
            {
                "route_kind": result.route_kind,
                "route_family": result.route_family,
                "outcome": result.outcome,
                "final_page_url": result.final_page_url,
                "downloaded_file_name": result.downloaded_file_name or "",
            },
            artifact_paths,
        )
    if run_type == "acquisition_audit":
        app_settings = load_settings(ConfigLoadRequest(schema_version="1.0", path=""), run_ctx)
        inventory_settings = load_publisher_inventory_settings(
            ConfigLoadRequest(schema_version="1.0", path=""),
            run_ctx,
        )
        browser_settings = load_browser_download_settings(
            ConfigLoadRequest(schema_version="1.0", path=""),
            run_ctx,
        )
        result = run_acquisition_audit(
            AcquisitionAuditBatchRequest(
                schema_version="1.0",
                reports_db=app_settings.reports_db,
                publisher_inventory_settings=inventory_settings,
                browser_download_settings=browser_settings,
                output_dir=app_settings.output_dir,
                delivery_email=str(payload.get("delivery_email") or "").strip() or None,
                publisher_limit=int(payload["publisher_limit"]) if payload.get("publisher_limit") is not None else None,
                candidate_limit_per_publisher=int(payload["candidate_limit_per_publisher"]) if payload.get("candidate_limit_per_publisher") is not None else None,
            ),
            ctx=run_ctx,
        )
        return (
            {
                "publisher_count": result.publisher_count,
                "candidate_count": result.candidate_count,
                "output_path": result.output_path,
            },
            [result.output_path],
        )
    raise AppError(
        code="ui_run_type_unknown",
        message=f"Unknown UI run type: {run_type}",
        retryable=False,
        context={"run_type": run_type},
    )


@cli_app.command("ingest")
def ingest(
    folder: str = typer.Option(None, help="Override Drive folder ID"),
    limit: int = typer.Option(None, help="Max PDFs to process this run"),
):
    ctx = new_run_context(task_id="cli_ingest")
    setup_logging(LoggingSetupRequest(schema_version="1.0"), ctx)
    console.print("[cyan]Loading settings...[/cyan]")
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="cli_load_settings_start",
            module=logger.name,
            fields={},
        )
    )
    s = load_settings(ConfigLoadRequest(schema_version="1.0", path=""), ctx)
    settings = build_ingest_settings(
        IngestSettingsBuildRequest(schema_version="1.0", app_settings=s),
        ctx,
    )

    console.print("[cyan]Running ingest pipeline...[/cyan]")
    try:
        outcomes = run_ingest(settings, folder_id=folder, limit=limit, ctx=ctx)
    except AppError as exc:
        if exc.code == "ingest_locked":
            console.print(
                f"[red]{exc.message} (lock: {settings.ingest_lock_path})[/red]"
            )
            raise typer.Exit(code=1)
        if exc.code == "db_locked":
            console.print(f"[red]{exc.message}[/red]")
            raise typer.Exit(code=1)
        raise

    table = Table(title="Processed Reports", box=box.SIMPLE_HEAVY)
    table.add_column("File")
    table.add_column("ID")
    table.add_column("MD5")
    table.add_column("HTML")
    processed = 0
    for outcome in outcomes:
        if outcome.status == "processed":
            processed += 1
        md5_short = (outcome.md5 or "")[:10] + ":" if outcome.md5 else ""
        table.add_row(outcome.name, outcome.file_id, md5_short, outcome.html_path or "")

    console.print(table)
    console.print(f"[green]Done: {processed} file(s).[/green]")


@cli_app.command("extract-candidates")
def extract_candidates(
    folder: str = typer.Option(None, help="Override Drive folder ID"),
    limit: int = typer.Option(None, help="Max PDFs to process this run"),
    file_id: str = typer.Option(None, help="Optional Drive file ID to process"),
    pdf: str = typer.Option(None, help="Local PDF path to process instead of Drive"),
    report_id: str = typer.Option(
        None, help="Optional report ID override for local PDFs"
    ),
):
    ctx = new_run_context(task_id="cli_extract_candidates")
    setup_logging(LoggingSetupRequest(schema_version="1.0"), ctx)
    console.print("[cyan]Loading settings...[/cyan]")
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="cli_candidate_extract_start",
            module=logger.name,
            fields={
                "folder": folder or "",
                "limit": limit,
                "file_id": file_id or "",
                "pdf": pdf or "",
            },
        )
    )
    s = load_settings(ConfigLoadRequest(schema_version="1.0", path=""), ctx)
    settings = build_ingest_settings(
        IngestSettingsBuildRequest(schema_version="1.0", app_settings=s),
        ctx,
    )

    console.print("[cyan]Running candidate extraction...[/cyan]")
    outcomes = run_candidate_extraction(
        settings,
        folder_id=folder,
        limit=limit,
        file_id=file_id,
        pdf_path=pdf,
        report_id=report_id,
        ctx=ctx,
    )

    table = Table(title="Candidate Extraction", box=box.SIMPLE_HEAVY)
    table.add_column("Report")
    table.add_column("ID")
    table.add_column("Candidates", justify="right")
    table.add_column("Charts", justify="right")
    table.add_column("Tables", justify="right")
    table.add_column("JSON")
    for outcome in outcomes:
        table.add_row(
            outcome.report_name,
            outcome.report_id,
            str(outcome.candidate_count),
            str(outcome.chart_count),
            str(outcome.table_count),
            outcome.candidates_path or "",
        )
    console.print(table)
    console.print(f"[green]Done: {len(outcomes)} run(s).[/green]")


@cli_app.command("publish-wp")
def publish_wp(
    limit: int = typer.Option(None, help="Max HTML reports to publish this run"),
):
    ctx = new_run_context(task_id="cli_publish")
    setup_logging(LoggingSetupRequest(schema_version="1.0"), ctx)
    console.print("[cyan]Loading settings...[/cyan]")
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="cli_load_publish_settings_start",
            module=logger.name,
            fields={},
        )
    )
    settings = load_publish_settings(
        ConfigLoadRequest(schema_version="1.0", path=""), ctx
    )

    console.print("[cyan]Publishing reports to WordPress...[/cyan]")
    outcomes = run_publish(settings, limit=limit, ctx=ctx)

    table = Table(title="Published Reports", box=box.SIMPLE_HEAVY)
    table.add_column("HTML")
    table.add_column("File ID")
    table.add_column("Status")
    table.add_column("Post URL")
    published = 0
    for outcome in outcomes:
        if outcome.status == "published":
            published += 1
        table.add_row(
            outcome.html_path,
            outcome.file_id or "",
            outcome.status,
            outcome.post_url or "",
        )

    console.print(table)
    console.print(f"[green]Done: {published} post(s) published.[/green]")


@cli_app.command("recategorize")
def recategorize():
    ctx = new_run_context(task_id="cli_recategorize")
    setup_logging(LoggingSetupRequest(schema_version="1.0"), ctx)
    console.print("[cyan]Loading settings...[/cyan]")
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="cli_load_settings_start",
            module=logger.name,
            fields={},
        )
    )
    s = load_settings(ConfigLoadRequest(schema_version="1.0", path=""), ctx)
    console.print("[cyan]Recomputing categories...[/cyan]")
    outcomes = run_recategorize(
        RecategorizeRequest(
            schema_version="1.0",
            db_path=s.reports_db,
            category_mapping_path=s.category_mapping_path,
            settings=s,
        )
    )
    table = Table(title="Recategorization", box=box.SIMPLE_HEAVY)
    table.add_column("Title")
    table.add_column("File ID")
    table.add_column("Categories")
    table.add_column("Unmapped")
    table.add_column("Status")
    updated = 0
    for outcome in outcomes:
        if outcome.status == "updated":
            updated += 1
        cats = ", ".join(outcome.categories)
        unmapped = ", ".join(outcome.unmapped_tags)
        table.add_row(
            outcome.title,
            outcome.file_id,
            cats,
            unmapped,
            outcome.status
            if not outcome.error
            else f"{outcome.status}:{outcome.error}",
        )
    console.print(table)
    console.print(f"[green]Done: {updated} record(s) updated.[/green]")


@cli_app.command("generate-covers")
def generate_covers(
    style_config: str = typer.Option("", help="Override path to cover style YAML"),
    limit: int = typer.Option(None, help="Max reports to process this run"),
    file_id: str = typer.Option(None, help="Optional report file ID to process"),
):
    ctx = new_run_context(task_id="cli_generate_covers")
    setup_logging(LoggingSetupRequest(schema_version="1.0"), ctx)
    console.print("[cyan]Loading settings...[/cyan]")
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="cli_cover_generate_start",
            module=logger.name,
            fields={
                "style_config": style_config or "",
                "limit": limit,
                "file_id": file_id or "",
            },
        )
    )
    settings = load_settings(ConfigLoadRequest(schema_version="1.0", path=""), ctx)

    console.print("[cyan]Generating cover images...[/cyan]")
    outcomes = run_cover_image_generation(
        CoverImageOrchestratorRequest(
            schema_version="1.0",
            reports_db=settings.reports_db,
            output_dir=settings.output_dir,
            style_config_path=style_config,
            limit=limit,
            file_id=file_id,
        ),
        ctx=ctx,
    )

    table = Table(title="Cover Images", box=box.SIMPLE_HEAVY)
    table.add_column("Report")
    table.add_column("File ID")
    table.add_column("Status")
    table.add_column("Output")
    for outcome in outcomes:
        table.add_row(
            outcome.title,
            outcome.file_id,
            outcome.status,
            outcome.output_path or outcome.error or "",
        )
    console.print(table)
    console.print(f"[green]Done: {len(outcomes)} report(s).[/green]")


@cli_app.command("update-wp-categories")
def update_wp_categories():
    ctx = new_run_context(task_id="cli_update_wp_categories")
    setup_logging(LoggingSetupRequest(schema_version="1.0"), ctx)
    console.print("[cyan]Loading publish settings...[/cyan]")
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="cli_load_publish_settings_start",
            module=logger.name,
            fields={},
        )
    )
    settings = load_publish_settings(
        ConfigLoadRequest(schema_version="1.0", path=""), ctx
    )
    console.print("[cyan]Updating WordPress categories...[/cyan]")
    outcomes = run_update_wp_categories(settings)
    table = Table(title="WP Category Updates", box=box.SIMPLE_HEAVY)
    table.add_column("File ID")
    table.add_column("Post ID")
    table.add_column("Categories")
    table.add_column("Status")
    updated = 0
    for outcome in outcomes:
        if outcome.status == "updated":
            updated += 1
        cats = ", ".join(outcome.categories)
        table.add_row(
            outcome.file_id,
            str(outcome.post_id or ""),
            cats,
            outcome.status
            if not outcome.error
            else f"{outcome.status}:{outcome.error}",
        )
    console.print(table)
    console.print(f"[green]Done: {updated} post(s) updated.[/green]")


@cli_app.command("cost-report")
def cost_report(
    date: str = typer.Option(None, help="UTC date (YYYY-MM-DD) to summarize"),
    run_id: str = typer.Option(None, help="Run identifier to summarize"),
    top: int = typer.Option(5, help="Number of top-cost steps to show"),
):
    if (date and run_id) or (not date and not run_id):
        raise typer.BadParameter("Provide exactly one of --date or --run-id.")
    if top <= 0:
        raise typer.BadParameter("--top must be greater than zero.")

    console.print("[cyan]Loading settings...[/cyan]")
    ctx = new_run_context(task_id="cli_cost_report")
    setup_logging(LoggingSetupRequest(schema_version="1.0"), ctx)
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="cli_cost_report_start",
            module=logger.name,
            fields={"date": date, "run_id": run_id, "top": top},
        )
    )
    settings = load_settings(ConfigLoadRequest(schema_version="1.0", path=""), ctx)

    try:
        reporting = run_cost_reporting(
            CostReportingRequest(
                schema_version="1.0",
                report_request=CostReportRequest(
                    schema_version="1.0",
                    ledger_path=settings.cost_ledger_path,
                    date_utc=date,
                    run_id=run_id,
                    top_n=top,
                ),
            ),
            ctx,
        )
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)
    report = reporting.report
    if report is None:
        console.print("[red]Cost report was not generated.[/red]")
        raise typer.Exit(code=1)

    console.print(
        f"[cyan]Cost report for {report.filter_type}={report.filter_value}[/cyan]"
    )
    totals = report.totals
    totals_table = Table(title="Totals", box=box.SIMPLE_HEAVY)
    totals_table.add_column("Metric")
    totals_table.add_column("Value", justify="right")
    totals_table.add_row("total_input_tokens", str(totals.total_input_tokens))
    totals_table.add_row("total_output_tokens", str(totals.total_output_tokens))
    totals_table.add_row("total_tool_calls", str(totals.total_tool_calls))
    totals_table.add_row("estimated_cost_usd", f"{totals.estimated_cost_usd:.6f}")
    console.print(totals_table)

    if report.top_steps:
        steps_table = Table(title="Top steps by cost", box=box.SIMPLE_HEAVY)
        steps_table.add_column("Step")
        steps_table.add_column("Cost (USD)", justify="right")
        steps_table.add_column("Input", justify="right")
        steps_table.add_column("Output", justify="right")
        steps_table.add_column("Tool calls", justify="right")
        for step in report.top_steps:
            steps_table.add_row(
                step.step_name,
                f"{step.estimated_cost_usd:.6f}",
                str(step.total_input_tokens),
                str(step.total_output_tokens),
                str(step.total_tool_calls),
            )
        console.print(steps_table)
    else:
        console.print("[yellow]No matching ledger entries found.[/yellow]")

    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="cli_cost_report_complete",
            module=logger.name,
            fields={
                "filter_type": report.filter_type,
                "filter_value": report.filter_value,
                "matched_entries": report.matched_entries,
                "top_steps": len(report.top_steps),
            },
        )
    )


@cli_app.command("download-report")
def download_report(
    url: str = typer.Argument(..., help="Absolute report landing-page URL"),
    delivery_email: str = typer.Option(
        None,
        help="Optional email address used when the report is gated behind an email form",
    ),
):
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
            },
        )
    )
    settings = load_browser_download_settings(
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
    table.add_row("Summary", result.route_summary)
    console.print(table)


@cli_app.command("discover-publisher-inventory")
def discover_publisher_inventory(
    insights_url: str = typer.Argument(..., help="Publisher insights URL to crawl"),
):
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
    ctx = new_run_context(task_id="cli_drive_oauth_login")
    setup_logging(LoggingSetupRequest(schema_version="1.0"), ctx)
    resolved_client_json = client_json.strip() or os.getenv("GOOGLE_OAUTH_CLIENT_JSON", "").strip()
    resolved_token_json = token_json.strip() or os.getenv("GOOGLE_OAUTH_TOKEN_JSON", "").strip()
    if not resolved_client_json:
        console.print("[red]Missing OAuth client JSON path. Pass --client-json or set GOOGLE_OAUTH_CLIENT_JSON.[/red]")
        raise typer.Exit(code=1)
    if not resolved_token_json:
        console.print("[red]Missing OAuth token output path. Pass --token-json or set GOOGLE_OAUTH_TOKEN_JSON.[/red]")
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


@cli_app.command("sync-publishers")
def sync_publishers(
    snapshot_path: str = typer.Option(
        None,
        help="Optional override path to the publisher snapshot JSON sourced from Notion",
    ),
):
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


@cli_app.command("ui-run-worker", hidden=True)
def ui_run_worker(
    request_json: str = typer.Option(
        ...,
        "--request-json",
        help="Internal worker request JSON path.",
    ),
):
    worker_request = _load_ui_run_worker_request(request_json)
    ctx = new_run_context(task_id=f"ui_run_worker:{worker_request.run_type}")
    setup_logging(LoggingSetupRequest(schema_version="1.0"), ctx)
    started_at = _utc_now()
    _update_ui_run_record(
        worker_request=worker_request,
        run_ctx=ctx,
        status="running",
        started_at_utc=started_at,
        pid=os.getpid(),
    )
    print(
        f"[ui-run-worker] started run_id={worker_request.run_id} type={worker_request.run_type}",
        flush=True,
    )
    try:
        result_summary, artifact_paths = _run_ui_worker_payload(worker_request, ctx)
        _update_ui_run_record(
            worker_request=worker_request,
            run_ctx=ctx,
            status="succeeded",
            finished_at_utc=_utc_now(),
            pid=os.getpid(),
            exit_code=0,
            result_summary=result_summary,
            artifact_paths=artifact_paths,
        )
        print(
            f"[ui-run-worker] completed run_id={worker_request.run_id}",
            flush=True,
        )
    except AppError as exc:
        _update_ui_run_record(
            worker_request=worker_request,
            run_ctx=ctx,
            status="failed",
            finished_at_utc=_utc_now(),
            pid=os.getpid(),
            exit_code=1,
            error_code=exc.code,
            error_message=exc.message,
        )
        print(
            f"[ui-run-worker] failed run_id={worker_request.run_id} code={exc.code} message={exc.message}",
            flush=True,
        )
        raise typer.Exit(code=1)
    except Exception as exc:
        _update_ui_run_record(
            worker_request=worker_request,
            run_ctx=ctx,
            status="failed",
            finished_at_utc=_utc_now(),
            pid=os.getpid(),
            exit_code=1,
            error_code="ui_run_worker_failed",
            error_message=str(exc),
        )
        print(
            f"[ui-run-worker] failed run_id={worker_request.run_id} error={exc}",
            flush=True,
        )
        raise typer.Exit(code=1)


@cli_app.callback(invoke_without_command=True)
def cli(
    ctx: typer.Context,
    folder: str = typer.Option(None, help="Override Drive folder ID"),
    limit: int = typer.Option(None, help="Max PDFs to process this run"),
):
    if ctx.invoked_subcommand is None:
        ingest(folder=folder, limit=limit)


def main() -> None:
    cli_app()


if __name__ == "__main__":
    main()
