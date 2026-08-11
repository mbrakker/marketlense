from __future__ import annotations

import re

from click import unstyle
from click.testing import CliRunner
from typer.main import get_command

from src._cli import pipeline as _pipeline  # noqa: F401
from src._cli.app import cli_app


def _normalized_cli_output(output: str) -> str:
    """Make Rich-wrapped Click output stable across runner terminals."""
    text = re.sub(r"\s+", " ", unstyle(output))
    return re.sub(r"(?<=-)\s+(?=[A-Za-z])", "", text)


def test_ingest_help_exposes_distinct_selection_controls() -> None:
    result = CliRunner().invoke(get_command(cli_app), ["ingest", "--help"], color=False)

    assert result.exit_code == 0, result.output
    output = _normalized_cli_output(result.output)
    assert "--cohort-size" in output
    assert "--attempt-limit" in output
    assert "--success-target" in output
    assert "--cohort-manifest" in output
    assert "Deprecated alias for --attempt-limit" in output


def test_ingest_rejects_ambiguous_legacy_and_attempt_limit() -> None:
    result = CliRunner().invoke(
        get_command(cli_app),
        ["ingest", "--attempt-limit", "1", "--limit", "1"],
        color=False,
    )

    assert result.exit_code != 0
    assert (
        "Use either --attempt-limit or the deprecated --limit"
        in _normalized_cli_output(result.output)
    )
