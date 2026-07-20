from __future__ import annotations

from typer.testing import CliRunner

from src.cli import cli_app


def test_policy_effectiveness_reads_an_explicit_local_ledger(tmp_path) -> None:
    usage_db = tmp_path / "usage.sqlite"

    result = CliRunner().invoke(
        cli_app,
        ["policy-effectiveness", "--usage-db", str(usage_db)],
    )

    assert result.exit_code == 0, result.output
    assert "Legacy unattributed calls: 0" in result.output
    assert "execution-identity cohorts: 0" in result.output
