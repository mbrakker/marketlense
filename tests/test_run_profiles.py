from __future__ import annotations

import pytest

from src._cli.pipeline import _resolve_cli_workflow_control
from src.contracts.config import ConfigLoadRequest
from src.contracts.workflow_control import RunIntent
from src.orchestrators import workflow_control_orchestrator as workflow
from src.services import config_service
from src.ui.run_control import _resolve_ui_workflow_control_payload
from src.utils.errors import AppError
from src.utils.logging import new_run_context


def _ctx():
    return new_run_context(task_id="run_profile_test")


def _settings():
    return config_service.load_workflow_control_settings(
        ConfigLoadRequest(schema_version="1.0", path="src/config/app.yaml"), _ctx()
    )


def _intent(*, profile: str = "", overrides: dict | None = None) -> RunIntent:
    return RunIntent(
        schema_version="1.0",
        intent="ingest new reports",
        subject="",
        publisher="",
        report_id="",
        requested_side_effects=[],
        dry_run=True,
        allow_automation=False,
        metadata={"source": "test"},
        run_profile=profile,
        profile_overrides=overrides or {},
    )


def test_project_run_profiles_cover_required_operating_outcomes() -> None:
    settings = _settings()

    assert set(settings.run_profiles) == {
        "safe_default",
        "fast_cached",
        "repair_failed",
        "publish_ready",
        "browser_acquisition",
        "cost_saver",
        "high_quality",
    }
    assert all(
        profile.human_publication_approval_required
        for profile in settings.run_profiles.values()
    )


def test_recommendation_does_not_apply_profile_and_hash_is_deterministic() -> None:
    settings = _settings()
    first = workflow.resolve_run_profile(_intent(), settings, ctx=_ctx())
    second = workflow.resolve_run_profile(_intent(), settings, ctx=_ctx())

    assert first.profile_name == "safe_default"
    assert first.recommended_profile == "safe_default"
    assert first.explicitly_selected is False
    assert first.profile_hash == second.profile_hash


def test_explicit_profile_override_wins_over_profile_value() -> None:
    settings = _settings()
    resolved = workflow.resolve_run_profile(
        _intent(profile="cost_saver", overrides={"maximum_provider_calls": 2}),
        settings,
        ctx=_ctx(),
    )

    assert resolved.profile_name == "cost_saver"
    assert resolved.effective_selections["maximum_provider_calls"] == 2
    assert "explicit_override_preserved:maximum_provider_calls" in resolved.warnings


def test_unknown_incompatible_and_unbounded_repair_profiles_fail_before_execution(
) -> None:
    settings = _settings()
    with pytest.raises(AppError, match="not configured"):
        workflow.resolve_run_profile(_intent(profile="unknown"), settings, ctx=_ctx())
    with pytest.raises(AppError, match="incompatible"):
        workflow.resolve_run_profile(
            _intent(profile="publish_ready"), settings, ctx=_ctx()
        )
    with pytest.raises(AppError, match="bounded report"):
        workflow.resolve_run_profile(
            _intent(profile="repair_failed"), settings, ctx=_ctx()
        )


def test_cli_and_ui_use_the_same_resolved_profile() -> None:
    cli = _resolve_cli_workflow_control(
        intent="acquire missing pdf",
        ctx=_ctx(),
        run_profile="browser_acquisition",
    )
    ui = _resolve_ui_workflow_control_payload(
        "report_download", {"profile": "browser_acquisition"}
    )

    assert cli["run_profile"] == ui["execution_plan"]["run_profile"]
    assert cli["run_profile_hash"] == ui["execution_plan"]["run_profile_hash"]
