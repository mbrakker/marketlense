from __future__ import annotations

import os
from unittest.mock import patch

from src.contracts.config import ConfigLoadRequest
from src.services.config_service import (
    load_workflow_control_settings,
    load_workflow_queue_policies,
    new_runtime_context,
)


def test_config_request_selects_autonomous_profile_overlay(tmp_path) -> None:
    base = tmp_path / "app.yaml"
    base.write_text(
        'schema_version: "1.0"\nworkflow_queues:\n  report_acquisition:\n    enabled: false\n',
        encoding="utf-8",
    )
    (tmp_path / "app.autonomous_mvp.yaml").write_text(
        'schema_version: "1.0"\nworkflow_queues:\n  report_acquisition:\n    enabled: true\n',
        encoding="utf-8",
    )

    policies = load_workflow_queue_policies(
        ConfigLoadRequest(
            schema_version="1.0",
            path=str(base),
            profile_name="autonomous_mvp",
        ),
        new_runtime_context(task_id="test_capability_profile_config"),
    )

    assert policies["report_acquisition"].enabled is True


def test_explicit_manual_profile_ignores_process_autonomous_profile(tmp_path) -> None:
    base = tmp_path / "app.yaml"
    base.write_text(
        'schema_version: "1.0"\nworkflow_queues:\n  report_acquisition:\n    enabled: false\n',
        encoding="utf-8",
    )
    (tmp_path / "app.autonomous_mvp.yaml").write_text(
        'schema_version: "1.0"\nworkflow_queues:\n  report_acquisition:\n    enabled: true\n',
        encoding="utf-8",
    )
    with patch.dict(
        os.environ, {"MARKET_LENSE_CONFIG_PROFILE": "autonomous_mvp"}, clear=False
    ):
        policies = load_workflow_queue_policies(
            ConfigLoadRequest(schema_version="1.0", path=str(base), profile_name=""),
            new_runtime_context(task_id="test_capability_manual_profile_config"),
        )

    assert policies["report_acquisition"].enabled is False


def test_workflow_budget_reference_set_includes_canonical_queue_defaults() -> None:
    control = load_workflow_control_settings(
        ConfigLoadRequest(
            schema_version="1.0",
            path="src/config/app.yaml",
            profile_name="",
        ),
        new_runtime_context(task_id="test_capability_default_budget_profiles"),
    )

    assert "maintenance" in control.available_budget_profile_refs
