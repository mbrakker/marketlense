from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from src.contracts.semantic_ids import RunId
from src.contracts.ui_run_control import (
    UiRunCancelRequest,
    UiRunCancelResponse,
    UiRunDeadLetterActionListRequest,
    UiRunDeadLetterActionListResponse,
    UiRunDeadLetterActionRequest,
    UiRunDeadLetterActionResponse,
    UiRunDeadLetterListRequest,
    UiRunDeadLetterListResponse,
    UiRunLaunchRequest,
    UiRunLaunchResponse,
    UiRunListRequest,
    UiRunListResponse,
    UiRunPollRequest,
    UiRunPollResponse,
)
from src.contracts.workflow_control import (
    PipelineExecutionAuthorizationRequest,
    RunIntent,
)
from src.orchestrators import workflow_control_orchestrator as workflow_control
from src.orchestrators.ui_run_control_orchestrator import (
    apply_dead_letter_action,
    cancel_ui_run,
    launch_ui_run,
    list_dead_letter_actions,
    list_dead_letter_runs,
    list_ui_runs,
    poll_ui_run,
)
from src.ui import state as ui_state
from src.ui.common import _ctx


def launch_background_run(
    settings: Any,
    *,
    run_type: str,
    display_name: str,
    request_payload: dict[str, Any],
) -> UiRunLaunchResponse:
    registry_path = ui_state.get_ui_run_registry_path(settings)
    workflow_payload = _resolve_ui_workflow_control_payload(run_type, request_payload)
    enriched_payload = dict(request_payload)
    enriched_payload["workflow_control"] = workflow_payload
    if run_type in {
        "publisher_discovery",
        "report_download",
        "signal_candidate_extraction",
        "signal_post",
        "cross_report_analysis",
    }:
        enriched_payload["workflow_queue_submit"] = True
    response = launch_ui_run(
        UiRunLaunchRequest(
            schema_version="1.0",
            registry_path=registry_path,
            workspace_root=str(Path(__file__).resolve().parents[2]),
            run_type=run_type,
            display_name=display_name,
            request_payload=enriched_payload,
        ),
        _ctx(f"launch_{run_type}"),
    )
    ui_state.set_selected_run_id(response.record.run_id)
    return response


def _resolve_ui_workflow_control_payload(
    run_type: str,
    request_payload: dict[str, Any],
) -> dict[str, Any]:
    intent = _ui_run_type_to_intent(run_type)
    ctx = _ctx(f"workflow_control_{run_type}")
    settings = workflow_control.default_workflow_control_settings()
    resolved = workflow_control.resolve_run_intent(
        RunIntent(
            schema_version="1.0",
            intent=intent,
            subject=str(
                request_payload.get("url")
                or request_payload.get("file_id")
                or request_payload.get("topic")
                or ""
            ),
            publisher=str(
                request_payload.get("publisher")
                or request_payload.get("publisher_name")
                or ""
            ),
            report_id=str(request_payload.get("report_id") or ""),
            requested_side_effects=[],
            dry_run=False,
            allow_automation=True,
            metadata={"source": "ui", "run_type": run_type},
        ),
        settings,
        ctx=ctx,
    )
    plan = workflow_control.build_pipeline_execution_plan(
        RunIntent(
            schema_version="1.0",
            intent=intent,
            subject=str(
                request_payload.get("url")
                or request_payload.get("file_id")
                or request_payload.get("topic")
                or ""
            ),
            publisher=str(
                request_payload.get("publisher")
                or request_payload.get("publisher_name")
                or ""
            ),
            report_id=str(request_payload.get("report_id") or ""),
            requested_side_effects=[],
            dry_run=True,
            allow_automation=False,
            metadata={"source": "ui", "run_type": run_type},
        ),
        settings,
        ctx=ctx,
    )
    authorization = workflow_control.authorize_pipeline_execution(
        PipelineExecutionAuthorizationRequest(
            schema_version="1.0",
            plan=plan,
            expected_workflow=resolved.workflow,
            requested_side_effects=[],
        ),
        ctx=ctx,
    )
    retry_policy_id = ""
    if resolved.workflow:
        step_name = (
            "wordpress_publish"
            if resolved.workflow == "publishing"
            else "report_pipeline"
            if resolved.workflow == "report_generation"
            else "execute"
        )
        retry_policy_id = workflow_control.resolve_retry_policy(
            settings,
            workflow_name=resolved.workflow,
            step_name=step_name,
            ctx=ctx,
        ).policy_id
    return {
        "status": resolved.status,
        "intent": resolved.intent_key,
        "workflow": resolved.workflow,
        "preflight_profile": resolved.preflight_profile,
        "budget_profile": resolved.budget_profile,
        "retry_policy_id": retry_policy_id,
        "resume_stage": resolved.resume_stage,
        "side_effect_plan": list(resolved.side_effect_plan),
        "alternatives": list(resolved.alternatives),
        "blockers": list(resolved.blockers),
        "execution_plan": {
            "schema_version": plan.schema_version,
            "intent_key": plan.intent_key,
            "workflow": plan.workflow,
            "profile": plan.profile,
            "ordered_steps": list(plan.ordered_steps),
            "skipped_steps": list(plan.skipped_steps),
            "blocked_steps": list(plan.blocked_steps),
            "required_credentials": list(plan.required_credentials),
            "checkpoints": list(plan.checkpoints),
            "expected_artifacts": list(plan.expected_artifacts),
            "planned_side_effects": list(plan.planned_side_effects),
            "idempotency_key": plan.idempotency_key,
            "executable": plan.executable,
            "blockers": list(plan.blockers),
        },
        "execution_authority": asdict(authorization),
    }


def _ui_run_type_to_intent(run_type: str) -> str:
    normalized = str(run_type or "").strip().lower().replace("-", "_")
    mapping = {
        "ingest": "ingest new reports",
        "report_generation": "ingest new reports",
        "report_download": "acquire missing pdf",
        "publisher_discovery": "refresh publisher inventory",
        "publisher_inventory": "refresh publisher inventory",
        "cross_report_analysis": "generate cross-report analysis",
        "signal_candidate_extraction": "extract signal candidates",
        "signal_post": "generate signal post",
        "publish": "publish ready reports",
        "publish_wp": "publish ready reports",
        "ui_replay": "replay ui run",
        "ui_run_replay": "replay ui run",
        "browser_acquisition": "audit acquisition",
    }
    return mapping.get(normalized, normalized)


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
