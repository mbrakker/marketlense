from __future__ import annotations

import logging

import typer
from rich.console import Console
from rich.table import Table
from rich import box

from src.contracts.ingest import IngestSettings
from src.orchestrators.ingest_orchestrator import run_ingest
from src.services.config_service import load_settings
from src.services.logging_service import setup_logging


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
    logger.info("Loading settings")
    s = load_settings()

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
        temperature=s.temperature,
    )

    console.print("[cyan]Running ingest pipeline...[/cyan]")
    outcomes = run_ingest(settings, folder_id=folder, limit=limit)

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
