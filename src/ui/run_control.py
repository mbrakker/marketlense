from __future__ import annotations

from pathlib import Path
from typing import Any

from src.contracts.ui_run_control import (
    UiRunCancelRequest,
    UiRunLaunchRequest,
    UiRunListRequest,
    UiRunPollRequest,
)
from src.orchestrators.ui_run_control_orchestrator import (
    cancel_ui_run,
    launch_ui_run,
    list_ui_runs,
    poll_ui_run,
)
from src.ui.common import _ctx
from src.ui import state as ui_state


def launch_background_run(
    settings: Any,
    *,
    run_type: str,
    display_name: str,
    request_payload: dict[str, Any],
):
    registry_path = ui_state.get_ui_run_registry_path(settings)
    response = launch_ui_run(
        UiRunLaunchRequest(
            schema_version="1.0",
            registry_path=registry_path,
            workspace_root=str(Path(__file__).resolve().parents[2]),
            run_type=run_type,
            display_name=display_name,
            request_payload=request_payload,
        ),
        _ctx(f"launch_{run_type}"),
    )
    ui_state.set_selected_run_id(response.record.run_id)
    return response


def poll_selected_run(settings: Any, *, max_bytes: int = 32768):
    run_id = ui_state.get_selected_run_id()
    if not run_id:
        return None
    return poll_ui_run(
        UiRunPollRequest(
            schema_version="1.0",
            registry_path=ui_state.get_ui_run_registry_path(settings),
            run_id=run_id,
            output_tail_bytes=max_bytes,
        ),
        _ctx("poll_selected_run"),
    )


def cancel_selected_run(settings: Any):
    run_id = ui_state.get_selected_run_id()
    if not run_id:
        return None
    return cancel_ui_run(
        UiRunCancelRequest(
            schema_version="1.0",
            registry_path=ui_state.get_ui_run_registry_path(settings),
            run_id=run_id,
        ),
        _ctx("cancel_selected_run"),
    )


def list_recent_runs(settings: Any, *, statuses: list[str] | None = None, limit: int = 20):
    return list_ui_runs(
        UiRunListRequest(
            schema_version="1.0",
            registry_path=ui_state.get_ui_run_registry_path(settings),
            statuses=statuses or [],
            limit=limit,
        ),
        _ctx("list_recent_runs"),
    )
