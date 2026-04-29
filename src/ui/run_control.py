from __future__ import annotations

from pathlib import Path
from typing import Any

from src.contracts.ui_run_control import (
    UiRunDeadLetterActionListRequest,
    UiRunDeadLetterActionListResponse,
    UiRunDeadLetterActionRequest,
    UiRunDeadLetterActionResponse,
    UiRunDeadLetterListRequest,
    UiRunDeadLetterListResponse,
    UiRunCancelRequest,
    UiRunCancelResponse,
    UiRunLaunchRequest,
    UiRunLaunchResponse,
    UiRunListRequest,
    UiRunListResponse,
    UiRunPollRequest,
    UiRunPollResponse,
)
from src.contracts.semantic_ids import RunId
from src.orchestrators.ui_run_control_orchestrator import (
    apply_dead_letter_action,
    cancel_ui_run,
    launch_ui_run,
    list_dead_letter_actions,
    list_dead_letter_runs,
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
) -> UiRunLaunchResponse:
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


def poll_selected_run(
    settings: Any, *, max_bytes: int = 32768
) -> UiRunPollResponse | None:
    run_id = ui_state.get_selected_run_id()
    if not run_id:
        return None
    return poll_ui_run(
        UiRunPollRequest(
            schema_version="1.0",
            registry_path=ui_state.get_ui_run_registry_path(settings),
            run_id=RunId(run_id),
            output_tail_bytes=max_bytes,
        ),
        _ctx("poll_selected_run"),
    )


def cancel_selected_run(settings: Any) -> UiRunCancelResponse | None:
    run_id = ui_state.get_selected_run_id()
    if not run_id:
        return None
    return cancel_ui_run(
        UiRunCancelRequest(
            schema_version="1.0",
            registry_path=ui_state.get_ui_run_registry_path(settings),
            run_id=RunId(run_id),
        ),
        _ctx("cancel_selected_run"),
    )


def list_recent_runs(
    settings: Any, *, statuses: list[str] | None = None, limit: int = 20
) -> UiRunListResponse:
    return list_ui_runs(
        UiRunListRequest(
            schema_version="1.0",
            registry_path=ui_state.get_ui_run_registry_path(settings),
            statuses=statuses or [],
            limit=limit,
        ),
        _ctx("list_recent_runs"),
    )


def list_dead_letters(
    settings: Any, *, triage_statuses: list[str] | None = None, limit: int = 50
) -> UiRunDeadLetterListResponse:
    return list_dead_letter_runs(
        UiRunDeadLetterListRequest(
            schema_version="1.0",
            registry_path=ui_state.get_ui_run_registry_path(settings),
            triage_statuses=triage_statuses or [],
            limit=limit,
        ),
        _ctx("list_dead_letters"),
    )


def list_selected_dead_letter_actions(
    settings: Any, *, limit: int = 20
) -> UiRunDeadLetterActionListResponse | None:
    run_id = ui_state.get_selected_run_id()
    if not run_id:
        return None
    return list_dead_letter_actions(
        UiRunDeadLetterActionListRequest(
            schema_version="1.0",
            registry_path=ui_state.get_ui_run_registry_path(settings),
            run_id=RunId(run_id),
            limit=limit,
        ),
        _ctx("list_selected_dead_letter_actions"),
    )


def mark_dead_letter_recovery_requested(
    settings: Any,
    *,
    run_id: str,
    recovery_run_id: str,
    note: str = "",
) -> UiRunDeadLetterActionResponse:
    return apply_dead_letter_action(
        UiRunDeadLetterActionRequest(
            schema_version="1.0",
            registry_path=ui_state.get_ui_run_registry_path(settings),
            run_id=RunId(run_id),
            action="retry_requested",
            actor="ui",
            note=note,
            related_run_id=recovery_run_id,
        ),
        _ctx("mark_dead_letter_recovery_requested"),
    )


def discard_dead_letter(
    settings: Any,
    *,
    run_id: str,
    note: str = "",
) -> UiRunDeadLetterActionResponse:
    return apply_dead_letter_action(
        UiRunDeadLetterActionRequest(
            schema_version="1.0",
            registry_path=ui_state.get_ui_run_registry_path(settings),
            run_id=RunId(run_id),
            action="discarded",
            actor="ui",
            note=note,
        ),
        _ctx("discard_dead_letter"),
    )
