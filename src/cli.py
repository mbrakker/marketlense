from __future__ import annotations

import logging

import typer
from rich.console import Console
from rich.table import Table
from rich import box

from src.utils.errors import AppError
from src.contracts.config import ConfigLoadRequest
from src.contracts.ingest import IngestSettings
from src.orchestrators.ingest_orchestrator import run_ingest
from src.orchestrators.publish_orchestrator import run_publish
from src.services.config_service import load_settings, load_publish_settings
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

    settings = IngestSettings(
        schema_version="1.0",
        google_sa_path=s.google_sa_path,
        gdrive_folder_id=s.gdrive_folder_id,
        openai_api_key=s.openai_api_key,
        openai_model=s.openai_model,
        batch_limit=s.batch_limit,
        output_dir=s.output_dir,
        cache_dir=s.cache_dir,
        state_db=s.state_db,
        ingest_lock_path=s.ingest_lock_path,
        ingest_lock_ttl_seconds=s.ingest_lock_ttl_seconds,
        temperature=s.temperature,
        openai_seed=s.openai_seed,
        pdf_text_max_pages=s.pdf_text_max_pages,
        pdf_text_max_chars=s.pdf_text_max_chars,
        rank_model=s.rank_model,
        rank_temperature=s.rank_temperature,
        rank_seed=s.rank_seed,
        openai_timeout_seconds=s.openai_timeout_seconds,
        rank_timeout_seconds=s.rank_timeout_seconds,
    )

    console.print("[cyan]Running ingest pipeline...[/cyan]")
    try:
        outcomes = run_ingest(settings, folder_id=folder, limit=limit)
    except AppError as exc:
        if exc.code == "ingest_locked":
            console.print(f"[red]{exc.message} (lock: {settings.ingest_lock_path})[/red]")
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
