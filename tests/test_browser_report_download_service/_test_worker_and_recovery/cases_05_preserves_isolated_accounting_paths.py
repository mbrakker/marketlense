from __future__ import annotations

from dataclasses import asdict, replace

from src.contracts.run_budget import RunBudgetLimits

from ._shared import _settings, browser_worker_runtime


def test_browser_worker_settings_preserve_configured_accounting_paths(tmp_path) -> None:
    settings = replace(
        _settings(tmp_path),
        cost_ledger_path=str(tmp_path / "isolated" / "ledger.jsonl"),
        cost_daily_path=str(tmp_path / "isolated" / "daily.json"),
        usage_db_path=str(tmp_path / "isolated" / "usage.sqlite"),
        drive_upload_enabled=True,
        drive_upload_parent_folder_id="drive-folder",
        drive_upload_auth_mode="oauth",
        drive_upload_oauth_client_path=str(tmp_path / "client.json"),
        drive_upload_oauth_token_path=str(tmp_path / "token.json"),
        route_memory_ttl_seconds=123,
        run_budget_enabled=True,
        run_budget_max_browser_launches=20,
        run_budget_max_drive_writes=24,
        run_budget_enabled_effect_kinds=("browser_launch", "drive_write"),
        run_budget_limits_run=RunBudgetLimits(
            schema_version="1.0",
            max_browser_launches=20,
            max_drive_writes=24,
        ),
    )

    restored = browser_worker_runtime._build_settings(asdict(settings))

    assert restored.cost_ledger_path == settings.cost_ledger_path
    assert restored.cost_daily_path == settings.cost_daily_path
    assert restored.usage_db_path == settings.usage_db_path
    assert restored.drive_upload_enabled is True
    assert restored.drive_upload_parent_folder_id == "drive-folder"
    assert restored.drive_upload_auth_mode == "oauth"
    assert restored.drive_upload_oauth_client_path == str(tmp_path / "client.json")
    assert restored.drive_upload_oauth_token_path == str(tmp_path / "token.json")
    assert restored.route_memory_ttl_seconds == 123
    assert restored.run_budget_enabled is True
    assert restored.run_budget_max_browser_launches == 20
    assert restored.run_budget_max_drive_writes == 24
    assert restored.run_budget_enabled_effect_kinds == ("browser_launch", "drive_write")
    assert restored.run_budget_limits_run == settings.run_budget_limits_run
