from __future__ import annotations

from click.testing import CliRunner
from typer.main import get_command

from src._cli import pipeline as _pipeline  # noqa: F401
from src._cli.app import cli_app


def test_ingest_help_exposes_distinct_selection_controls() -> None:
    result = CliRunner().invoke(get_command(cli_app), ["ingest", "--help"])

    assert result.exit_code == 0, result.output
    assert "--cohort-size" in result.output
    assert "--attempt-limit" in result.output
    assert "--success-target" in result.output
    assert "--cohort-manifest" in result.output
    assert "Deprecated alias for --attempt-limit" in result.output


def test_ingest_rejects_ambiguous_legacy_and_attempt_limit() -> None:
    result = CliRunner().invoke(
        get_command(cli_app),
        ["ingest", "--attempt-limit", "1", "--limit", "1"],
    )

    assert result.exit_code != 0
    assert "Use either --attempt-limit or the deprecated --limit" in result.output
