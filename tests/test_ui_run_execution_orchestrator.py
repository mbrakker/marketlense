from __future__ import annotations

from src.contracts.ui_run_control import UiRunWorkerRequest
from src.orchestrators.ui_run_execution_orchestrator import (
    execute_ui_run,
    resolve_ui_run_config_snapshot,
)
from src.utils.logging import new_run_context


def _ctx():
    return new_run_context(task_id="test_ui_run_execution_orchestrator")


def _worker(run_type: str, payload: dict[str, object]) -> UiRunWorkerRequest:
    return UiRunWorkerRequest(
        schema_version="1.0",
        registry_path="unused.sqlite",
        run_id="run-1",
        run_type=run_type,
        request_payload=payload,
    )


def test_execute_ui_run_reports_invalid_limit_as_validation_error() -> None:
    response = execute_ui_run(_worker("ingest", {"limit": "not-a-number"}), _ctx())

    assert response.status == "failed"
    assert response.error_code == "ui_run_payload_invalid_int"
    assert (
        response.error_message
        == "UI run payload field must be a positive integer: limit"
    )
    assert response.config_snapshot["payload_error"]["field"] == "limit"


def test_execute_ui_run_reports_missing_report_download_url() -> None:
    response = execute_ui_run(_worker("report_download", {}), _ctx())

    assert response.status == "failed"
    assert response.error_code == "ui_run_payload_url_missing"
    assert response.config_snapshot["payload_error"]["field"] == "url"


def test_resolve_ui_run_config_snapshot_is_deterministic_for_invalid_payload() -> None:
    snapshot = resolve_ui_run_config_snapshot(
        _worker("publisher_discovery", {}),
        _ctx(),
    )

    assert snapshot["run_type"] == "publisher_discovery"
    assert snapshot["payload_error"]["code"] == "ui_run_payload_insights_url_missing"
    assert snapshot["payload_error"]["field"] == "insights_url"
