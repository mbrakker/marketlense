from __future__ import annotations

from pathlib import Path

import yaml

from tests.test_workflow_queue_registry import _isolated_app_config


def test_isolated_app_config_routes_mutable_accounting_to_tmp(tmp_path: Path) -> None:
    config_path = _isolated_app_config(tmp_path)
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    assert payload["analysis"]["cost_ledger_path"] == str(
        tmp_path / "cost-ledger.jsonl"
    )
    assert payload["cost"]["ledger_path"] == str(tmp_path / "cost-ledger.jsonl")
    assert payload["cost"]["daily_path"] == str(tmp_path / "cost-daily.json")
    assert payload["cost"]["usage_db_path"] == str(tmp_path / "llm-usage.sqlite")
