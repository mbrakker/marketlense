# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._support_cases import *  # noqa: F401,F403


def test_project_supervisor_configuration_defaults_to_three_workers() -> None:
    settings = config_service.load_workflow_control_settings(
        ConfigLoadRequest(schema_version="1.0", path="src/config/app.yaml"), _ctx()
    )

    assert settings.supervisor.max_parallel_workers == 3
    assert settings.supervisor.max_jobs_per_queue == 3
    assert settings.supervisor.max_runtime_seconds == 1200
    assert settings.supervisor.lease_seconds == 180


def test_project_supervisor_configuration_allows_five_worker_override(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "app.yaml"
    config_path.write_text(
        """
schema_version: "1.0"
workflow_control:
  supervisor:
    max_parallel_workers: 5
    max_jobs_per_queue: 5
""",
        encoding="utf-8",
    )

    settings = config_service.load_workflow_control_settings(
        ConfigLoadRequest(schema_version="1.0", path=str(config_path)), _ctx()
    )

    assert settings.supervisor.max_parallel_workers == 5
    assert settings.supervisor.max_jobs_per_queue == 5
