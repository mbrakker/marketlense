from __future__ import annotations

from typer.testing import CliRunner

from src.cli import cli_app


def test_plan_command_emits_a_side_effect_free_publish_plan() -> None:
    result = CliRunner().invoke(
        cli_app,
        ["plan", "publish ready reports", "--subject", "report-1"],
    )

    assert result.exit_code == 0, result.output
    assert '"workflow": "publishing"' in result.output
    assert '"executable": true' in result.output
    assert '"wordpress"' in result.output
