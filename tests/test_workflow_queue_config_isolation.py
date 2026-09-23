from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.contracts.workflow_queue import AnalyticsProjectionPayload
from src.orchestrators._workflow_queue_handlers.analytics import (
    _analytics_projection_handler,
)
from tests.test_workflow_queue_registry import (
    _ctx,
    _isolated_app_config,
    _workflow_job,
)


def test_analytics_projection_reads_carried_isolated_config_before_work(
    tmp_path: Path,
) -> None:
    missing_config = tmp_path / "missing-app.yaml"
    with pytest.raises(RuntimeError, match="Config file not found") as err:
        _analytics_projection_handler(
            _workflow_job(
                queue_name="analytics_projection", job_type="analytics_projection.v1"
            ),
            AnalyticsProjectionPayload(
                report_id="report-1",
                attributes={"config_path": str(missing_config)},
            ),
            _ctx(),
        )
    assert str(missing_config) in str(err.value)


def test_isolated_app_config_routes_mutable_accounting_to_tmp(tmp_path: Path) -> None:
    config_path = _isolated_app_config(tmp_path)
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    assert payload["analysis"]["cost_ledger_path"] == str(
        tmp_path / "cost-ledger.jsonl"
    )
    assert payload["cost"]["ledger_path"] == str(tmp_path / "cost-ledger.jsonl")
    assert payload["cost"]["daily_path"] == str(tmp_path / "cost-daily.json")
    assert payload["cost"]["usage_db_path"] == str(tmp_path / "llm-usage.sqlite")
