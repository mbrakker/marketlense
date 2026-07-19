from __future__ import annotations

from src.contracts.config import ConfigLoadRequest
from src.contracts.run_context import RunContext
from src.services import config_service
from src.utils.model_resolver import registered_report_generation_namespaces


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


def test_empty_report_generation_profile_derives_registered_namespaces(
    tmp_path,
) -> None:
    config_path = tmp_path / "app.yaml"
    config_path.write_text(
        """
schema_version: "1.0"
workflow_control:
  preflight_profiles:
    report_generation:
      workflow: report_generation
      prompt_namespaces: []
""",
        encoding="utf-8",
    )
    settings = config_service.load_workflow_control_settings(
        ConfigLoadRequest(schema_version="1.0", path=str(config_path)), _ctx()
    )

    assert settings.preflight_profiles["report_generation"].prompt_namespaces == (
        registered_report_generation_namespaces()
    )
