from __future__ import annotations

import logging

import typer
from rich.console import Console
from rich.table import Table
from rich import box

from src.utils.errors import AppError
from src.contracts.costs import CostReportRequest
from src.contracts.categories import RecategorizeRequest
from src.contracts.config import ConfigLoadRequest
from src.orchestrators.ingest_orchestrator import run_ingest
from src.orchestrators.candidate_extraction_orchestrator import run_candidate_extraction
from src.orchestrators.publish_orchestrator import run_publish
from src.orchestrators.recategorize_orchestrator import run_recategorize
from src.orchestrators.wp_category_update_orchestrator import run_update_wp_categories
from src.services.config_service import load_settings, load_publish_settings, to_ingest_settings
from src.services.cost_ledger_service import generate_cost_report
from src.services.logging_service import setup_logging
from src.utils.logging import log_event, new_run_context


cli_app = typer.Typer(add_completion=False, help="PDF -> Structured HTML digests")
console = Console()
logger = logging.getLogger("market_lense.cli")


@cli_app.command("ingest")
def ingest(
    folder: str = typer.Option(None, help="Override Drive folder ID"),
    limit: int = typer.Option(None, help="Max PDFs to process this run"),
):
    setup_logging()
    console.print("[cyan]Loading settings...[/cyan]")
    ctx = new_run_context(task_id="cli_ingest")
    logger.info(log_event(
        ctx,
        role="orchestrator",
        event="cli_load_settings_start",
        module=logger.name,
        fields={},
    ))
    s = load_settings(ConfigLoadRequest(schema_version="1.0", path=""), ctx)
    settings = to_ingest_settings(s)

    console.print("[cyan]Running ingest pipeline...[/cyan]")
    try:
        outcomes = run_ingest(settings, folder_id=folder, limit=limit, ctx=ctx)
    except AppError as exc:
        if exc.code == "ingest_locked":
            console.print(f"[red]{exc.message} (lock: {settings.ingest_lock_path})[/red]")
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
    report_id: str = typer.Option(None, help="Optional report ID override for local PDFs"),
):
    setup_logging()
    console.print("[cyan]Loading settings...[/cyan]")
    ctx = new_run_context(task_id="cli_extract_candidates")
    logger.info(log_event(
        ctx,
        role="orchestrator",
        event="cli_candidate_extract_start",
        module=logger.name,
        fields={"folder": folder or "", "limit": limit, "file_id": file_id or "", "pdf": pdf or ""},
    ))
    s = load_settings(ConfigLoadRequest(schema_version="1.0", path=""), ctx)
    settings = to_ingest_settings(s)

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
    setup_logging()
    console.print("[cyan]Loading settings...[/cyan]")
    ctx = new_run_context(task_id="cli_publish")
    logger.info(log_event(
        ctx,
        role="orchestrator",
        event="cli_load_publish_settings_start",
        module=logger.name,
        fields={},
    ))
    settings = load_publish_settings(ConfigLoadRequest(schema_version="1.0", path=""), ctx)

    console.print("[cyan]Publishing reports to WordPress...[/cyan]")
    outcomes = run_publish(settings, limit=limit)

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
    setup_logging()
    console.print("[cyan]Loading settings...[/cyan]")
    ctx = new_run_context(task_id="cli_recategorize")
    logger.info(log_event(
        ctx,
        role="orchestrator",
        event="cli_load_settings_start",
        module=logger.name,
        fields={},
    ))
    s = load_settings(ConfigLoadRequest(schema_version="1.0", path=""), ctx)
    console.print("[cyan]Recomputing categories...[/cyan]")
    outcomes = run_recategorize(RecategorizeRequest(
        schema_version="1.0",
        db_path=s.reports_db,
        category_mapping_path=s.category_mapping_path,
    ))
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
        table.add_row(outcome.title, outcome.file_id, cats, unmapped, outcome.status if not outcome.error else f"{outcome.status}:{outcome.error}")
    console.print(table)
    console.print(f"[green]Done: {updated} record(s) updated.[/green]")


@cli_app.command("update-wp-categories")
def update_wp_categories():
    setup_logging()
    console.print("[cyan]Loading publish settings...[/cyan]")
    ctx = new_run_context(task_id="cli_update_wp_categories")
    logger.info(log_event(
        ctx,
        role="orchestrator",
        event="cli_load_publish_settings_start",
        module=logger.name,
        fields={},
    ))
    settings = load_publish_settings(ConfigLoadRequest(schema_version="1.0", path=""), ctx)
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
            outcome.status if not outcome.error else f"{outcome.status}:{outcome.error}",
        )
    console.print(table)
    console.print(f"[green]Done: {updated} post(s) updated.[/green]")


@cli_app.command("cost-report")
def cost_report(
    date: str = typer.Option(None, help="UTC date (YYYY-MM-DD) to summarize"),
    run_id: str = typer.Option(None, help="Run identifier to summarize"),
    top: int = typer.Option(5, help="Number of top-cost steps to show"),
):
    setup_logging()
    if (date and run_id) or (not date and not run_id):
        raise typer.BadParameter("Provide exactly one of --date or --run-id.")
    if top <= 0:
        raise typer.BadParameter("--top must be greater than zero.")

    console.print("[cyan]Loading settings...[/cyan]")
    ctx = new_run_context(task_id="cli_cost_report")
    logger.info(log_event(
        ctx,
        role="orchestrator",
        event="cli_cost_report_start",
        module=logger.name,
        fields={"date": date, "run_id": run_id, "top": top},
    ))
    settings = load_settings(ConfigLoadRequest(schema_version="1.0", path=""), ctx)

    try:
        report = generate_cost_report(
            CostReportRequest(
                schema_version="1.0",
                ledger_path=settings.cost_ledger_path,
                date_utc=date,
                run_id=run_id,
                top_n=top,
            ),
            ctx,
        )
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)

    console.print(f"[cyan]Cost report for {report.filter_type}={report.filter_value}[/cyan]")
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

    logger.info(log_event(
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
    ))


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
