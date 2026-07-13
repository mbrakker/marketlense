from __future__ import annotations

from typer.testing import CliRunner

from src.cli import cli_app


def test_lineage_backfill_dry_run_uses_explicit_local_paths_without_provider_config(
    tmp_path,
) -> None:
    checkpoint_root = tmp_path / "checkpoints"
    checkpoint_root.mkdir()
    reports_db = tmp_path / "reports.sqlite"

    result = CliRunner().invoke(
        cli_app,
        [
            "backfill-artifact-lineage",
            "--reports-db",
            str(reports_db),
            "--checkpoint-root",
            str(checkpoint_root),
            "--dry-run",
            "--limit",
            "1",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Artifact Lineage Backfill" in result.output
    assert "Checkpoints scanned" in result.output
    assert reports_db.is_file()
