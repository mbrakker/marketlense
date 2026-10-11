from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from src._cli import pipeline as pipeline_cli
from src.contracts.config import AppSettings, ConfigLoadRequest
from src.contracts.run_context import RunContext
from src.contracts.workflow_queue import WORKFLOW_QUEUE_NAMES, WorkflowQueuePolicy
from src.services import config_service
from src import cli as cli_facade
from src.cli import cli_app


def test_publish_config_failure_keeps_other_enabled_workflow_reported(
    tmp_path: Path,
    external_boundary_mocks_only,
) -> None:
    repository_root = Path(__file__).resolve().parents[1]
    assets = {
        "categories": tmp_path / "categories.yaml",
        "cover_style": tmp_path / "cover-style.yaml",
        "publishers": tmp_path / "publishers.json",
    }
    assets["categories"].write_text("categories: []\n", encoding="utf-8")
    assets["cover_style"].write_text("style: test\n", encoding="utf-8")
    assets["publishers"].write_text("{}\n", encoding="utf-8")
    settings = AppSettings(
        schema_version="1.0",
        google_sa_path=str(tmp_path / "service-account.json"),
        gdrive_folder_id="folder-test",
        openai_api_key="sk-test",
        openai_model="model-test",
        batch_limit=1,
        output_dir=str(tmp_path / "out"),
        cache_dir=str(tmp_path / "cache"),
        state_db=str(tmp_path / "state.sqlite"),
        reports_db=str(tmp_path / "reports.sqlite"),
        publisher_profiles_path=str(assets["publishers"]),
        category_mapping_path=str(assets["categories"]),
        cover_style_path=str(assets["cover_style"]),
        ingest_lock_path=str(tmp_path / "ingest.lock"),
        temperature=0.0,
    )
    ctx = RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")
    control = config_service.load_workflow_control_settings(
        ConfigLoadRequest(
            schema_version="1.0",
            path=str(repository_root / "src" / "config" / "app.yaml"),
            profile_name="autonomous_mvp",
        ),
        ctx,
    )
    queue_policies = {
        name: WorkflowQueuePolicy(
            queue_name=name,
            enabled=name in {"cost_reconciliation", "wordpress_publish"},
            max_workers=1,
            max_attempts=1,
            lease_seconds=60,
            maximum_pending=10,
            maximum_fanout=1,
            budget_profile="publishing",
        )
        for name in WORKFLOW_QUEUE_NAMES
    }
    external_boundary_mocks_only.chdir(tmp_path)

    def fail_publish_settings(_request, _ctx):
        raise RuntimeError("Missing required config/env values: WP_APP_PASSWORD")

    external_boundary_mocks_only.setattr(
        cli_facade, "load_settings", lambda *_: settings
    )
    external_boundary_mocks_only.setattr(
        pipeline_cli,
        "load_workflow_control_settings",
        lambda *_: control,
    )
    external_boundary_mocks_only.setattr(
        pipeline_cli,
        "load_workflow_queue_policies",
        lambda *_: queue_policies,
    )
    external_boundary_mocks_only.setattr(
        cli_facade, "load_publish_settings", fail_publish_settings
    )

    result = CliRunner().invoke(
        cli_app, ["capability-preflight", "--profile", "autonomous_mvp"]
    )

    assert result.exit_code == 1, result.output
    output_start = result.output.rfind('{\n  "repository_commit_sha"')
    assert output_start >= 0, result.output
    report = json.loads(result.output[output_start:])
    assert report["workflow_names"] == ["cost_reconciliation", "wordpress_publish"]
    assert report["workflow_statuses"]["cost_reconciliation"] == "blocked"
    assert report["workflow_statuses"]["wordpress_publish"] == "blocked"
    assert report["status"] == "blocked"
    wordpress = next(
        check for check in report["checks"] if check["capability"] == "wordpress"
    )
    assert wordpress["reason_code"] == "publish_configuration_invalid"
    assert "WP_APP_PASSWORD" not in result.output
