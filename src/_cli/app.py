from __future__ import annotations

import logging

import typer
from rich.console import Console



cli_app = typer.Typer(
    add_completion=False,
    help="PDF -> Structured HTML digests",
    pretty_exceptions_show_locals=False,
)

console = Console()

logger = logging.getLogger("market_lense.cli")

@cli_app.callback(invoke_without_command=True)
def cli(
    ctx: typer.Context,
    folder: str = typer.Option(None, help="Override Drive folder ID"),
    limit: int = typer.Option(None, help="Max PDFs to process this run"),
):
    if ctx.invoked_subcommand is None:
        from src import cli as cli_facade

        cli_facade.ingest(folder=folder, limit=limit)

def main() -> None:
    cli_app()
