from __future__ import annotations

from typer.testing import CliRunner

import src.cli  # noqa: F401 - imports command modules that register the public CLI.
from src._cli.app import cli_app
from src.contracts.remediation import RemediationRecord, RemediationUpsertRequest
from src.services.state_service import upsert_remediation_record
from src.utils.logging import new_run_context


def test_remediations_command_projects_concise_operator_fields(tmp_path) -> None:
    state_db = str(tmp_path / "state.sqlite")
    ctx = new_run_context(task_id="test_remediation_cli")
    upsert_remediation_record(
        RemediationUpsertRequest(
            schema_version="1.0",
            state_db=state_db,
            record=RemediationRecord(
                schema_version="1.0",
                remediation_id="rem-cli",
                dedupe_key="dedupe:cli",
                workflow="report_download",
                run_id="run-cli",
                task_id="task-cli",
                span_id="span-cli",
                error_code="browser_download_timeout",
                action_code="retry_transient_service_call",
                operator_next_action="retry after route validation",
            ),
        ),
        ctx,
    )

    result = CliRunner().invoke(cli_app, ["remediations", "--state-db", state_db])

    assert result.exit_code == 0, result.output
    assert "rem-cli" in result.output
    assert "Failure" in result.output
    assert "Action" in result.output


def test_remediation_soak_command_is_read_only_and_projects_required_signals(
    tmp_path,
) -> None:
    state_db = str(tmp_path / "state.sqlite")
    ctx = new_run_context(task_id="test_remediation_soak_cli")
    upsert_remediation_record(
        RemediationUpsertRequest(
            schema_version="1.0",
            state_db=state_db,
            record=RemediationRecord(
                schema_version="1.0",
                remediation_id="rem-soak",
                dedupe_key="dedupe:soak",
                workflow="report_download",
                run_id="run-soak",
                task_id="task-soak",
                span_id="span-soak",
                error_code="browser_download_timeout",
                action_code="retry_transient_service_call",
            ),
        ),
        ctx,
    )

    result = CliRunner().invoke(
        cli_app,
        [
            "remediation-soak",
            "--state-db",
            state_db,
            "--now-utc",
            "2026-07-15T12:00:00Z",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Read-only Remediation Soak" in result.output
    assert "created records" in result.output
    assert "eligible records" in result.output
    assert "missing runbook mappings" in result.output
