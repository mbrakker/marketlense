from __future__ import annotations

from types import SimpleNamespace

from src.contracts.semantic_ids import RunId
from src.contracts.ui_run_control import UiRunLaunchResponse, UiRunRecord
from src.ui import run_control


def test_ui_background_launch_embeds_workflow_control_resolution(
    external_boundary_mocks_only,
) -> None:
    captured = {}

    external_boundary_mocks_only.setattr(
        run_control.ui_state,
        "get_ui_run_registry_path",
        lambda settings: "state/ui_runs.sqlite",
    )
    external_boundary_mocks_only.setattr(
        run_control.ui_state,
        "set_selected_run_id",
        lambda run_id: captured.setdefault("selected_run_id", run_id),
    )

    def _fake_launch(request, ctx):
        captured["request"] = request
        return UiRunLaunchResponse(
            schema_version="1.0",
            record=UiRunRecord(
                schema_version="1.0",
                run_id=RunId("run-ui"),
                run_type=request.run_type,
                display_name=request.display_name,
                status="queued",
                request_payload=request.request_payload,
                command=["python", "-m", "src.cli"],
                created_at_utc="2026-07-04T00:00:00Z",
                updated_at_utc="2026-07-04T00:00:00Z",
            ),
        )

    external_boundary_mocks_only.setattr(run_control, "launch_ui_run", _fake_launch)

    response = run_control.launch_background_run(
        SimpleNamespace(),
        run_type="report_download",
        display_name="Download report",
        request_payload={"url": "https://example.com/report"},
    )

    payload = captured["request"].request_payload
    assert response.record.run_id == "run-ui"
    assert payload["workflow_control"]["workflow"] == "report_download"
    assert payload["workflow_control"]["preflight_profile"] == "report_download"
    assert payload["workflow_control"]["status"] == "resolved"
    authority = payload["workflow_control"]["execution_authority"]
    assert authority["workflow"] == "report_download"
    assert len(authority["plan_checksum"]) == 64


def test_ui_run_replay_type_resolves_workflow_control_payload() -> None:
    payload = run_control._resolve_ui_workflow_control_payload(
        "ui_run_replay",
        {"run_id": "run-1", "registry_path": "state/ui_runs.sqlite"},
    )

    assert payload["status"] == "resolved"
    assert payload["workflow"] == "ui_replay"
    assert payload["preflight_profile"] == "ui_replay"


def test_strategy_output_ui_types_resolve_the_cross_report_authority() -> None:
    for run_type in (
        "cross_report_analysis",
        "signal_candidate_extraction",
        "signal_post",
    ):
        payload = run_control._resolve_ui_workflow_control_payload(
            run_type,
            {"topic": "Consumer behavior"},
        )

        assert payload["status"] == "resolved"
        assert payload["workflow"] == "cross_report_analysis"
        assert payload["execution_authority"]["workflow"] == "cross_report_analysis"
