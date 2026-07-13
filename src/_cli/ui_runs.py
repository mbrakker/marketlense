from __future__ import annotations

import os

import typer
from rich import box
from rich.table import Table

from src._cli.app import cli_app, console
from src._cli.common import _utc_now
from src._cli.runtime import sync_cli_patch_points
from src.contracts.config import ConfigLoadRequest
from src.contracts.files import ReadJsonRequest
from src.contracts.logging import LoggingSetupRequest
from src.contracts.semantic_ids import RunId
from src.contracts.ui_run_control import (
    UiRunDeadLetterReapRequest,
    UiRunRecord,
    UiRunRecordGetRequest,
    UiRunRecordWriteRequest,
    UiRunWorkerRequest,
)
from src.contracts.ui_run_replay import (
    UiRunReplayCaptureRequest,
    UiRunReplayRequest,
)
from src.orchestrators.ui_run_control_orchestrator import reap_dead_letter_runs
from src.orchestrators.ui_run_execution_orchestrator import (
    PROMPT_TREE_ROOT,
    SOURCE_TREE_ROOT,
    execute_ui_run,
)
from src.orchestrators.ui_run_replay_orchestrator import replay_ui_run
from src.services.config_service import (
    load_settings,
)
from src.services.file_service import read_json
from src.services.logging_service import setup_logging
from src.services.run_registry_service import (
    default_ui_run_registry_path,
    get_ui_run_record,
    write_ui_run_record,
)
from src.services.ui_run_replay_service import write_ui_run_replay_manifest
from src.utils.errors import AppError
from src.utils.logging import new_run_context

_CLI_PATCH_POINTS = (
    "authorize_oauth_user",
    "build_ingest_settings",
    "console",
    "default_browser_doctor_verification_url",
    "default_ui_run_registry_path",
    "execute_ui_run",
    "get_ui_run_record",
    "load_browser_download_settings",
    "load_publish_settings",
    "load_publisher_inventory_settings",
    "load_settings",
    "promote_private_api_evidence_to_browser_playbook",
    "read_json",
    "read_text",
    "replay_ui_run",
    "run_acquisition_audit",
    "run_browser_developer_diagnostics",
    "run_candidate_extraction",
    "run_cost_reporting",
    "run_cover_image_generation",
    "run_cross_report_analysis_orchestrator",
    "run_ingest",
    "run_publish",
    "run_publisher_inventory_discovery",
    "run_publisher_sync",
    "run_recategorize",
    "run_report_download",
    "run_update_wp_categories",
    "setup_logging",
    "write_ui_run_record",
    "write_ui_run_replay_manifest",
)


def _sync_cli_patch_points() -> None:
    sync_cli_patch_points(globals(), _CLI_PATCH_POINTS)


def _load_ui_run_worker_request(path: str) -> UiRunWorkerRequest:
    request_path = str(path or "").strip()
    if not request_path:
        raise AppError(
            code="ui_run_worker_request_missing",
            message="UI run worker request path is required",
            retryable=False,
        )
    try:
        response = read_json(
            ReadJsonRequest(schema_version="1.0", path=request_path),
            new_run_context(task_id="cli_ui_run_worker_request"),
        )
        payload = response.payload
    except AppError as exc:
        if exc.code == "file_not_found":
            raise AppError(
                code="ui_run_worker_request_missing",
                message=f"UI run worker request not found: {request_path}",
                cause=exc,
                retryable=False,
            ) from exc
        if exc.code == "file_json_invalid":
            raise AppError(
                code="ui_run_worker_request_invalid",
                message=f"UI run worker request JSON invalid: {request_path}",
                cause=exc,
                retryable=False,
            ) from exc
        raise
    except TypeError as exc:
        raise AppError(
            code="ui_run_worker_request_invalid",
            message=f"UI run worker request root must be an object: {request_path}",
            cause=exc,
            retryable=False,
        ) from exc
    if not isinstance(payload, dict):
        raise AppError(
            code="ui_run_worker_request_invalid",
            message=f"UI run worker request root must be an object: {request_path}",
            retryable=False,
        )
    return UiRunWorkerRequest(
        schema_version=str(payload.get("schema_version", "1.0")),
        registry_path=str(payload.get("registry_path") or "").strip(),
        run_id=RunId(str(payload.get("run_id") or "").strip()),
        run_type=str(payload.get("run_type") or "").strip(),
        request_payload=dict(payload.get("request_payload") or {}),
    )


def _update_ui_run_record(
    *,
    worker_request: UiRunWorkerRequest,
    run_ctx,
    status: str,
    started_at_utc: str | None = None,
    finished_at_utc: str | None = None,
    pid: int | None = None,
    exit_code: int | None = None,
    result_summary: dict[str, object] | None = None,
    artifact_paths: list[str] | None = None,
    error_code: str = "",
    error_message: str = "",
    error_retryable: bool | None = None,
    error_severity: str = "",
) -> UiRunRecord:
    _sync_cli_patch_points()
    existing = get_ui_run_record(
        UiRunRecordGetRequest(
            schema_version="1.0",
            registry_path=worker_request.registry_path,
            run_id=worker_request.run_id,
        ),
        run_ctx,
    ).record
    if existing is None:
        raise AppError(
            code="ui_run_not_found",
            message=f"UI run record not found for worker: {worker_request.run_id}",
            retryable=False,
        )
    updated = UiRunRecord(
        schema_version="1.0",
        run_id=existing.run_id,
        run_type=existing.run_type,
        display_name=existing.display_name,
        status=status,
        request_payload=existing.request_payload,
        command=existing.command,
        created_at_utc=existing.created_at_utc,
        updated_at_utc=_utc_now(),
        started_at_utc=started_at_utc
        if started_at_utc is not None
        else existing.started_at_utc,
        finished_at_utc=finished_at_utc
        if finished_at_utc is not None
        else existing.finished_at_utc,
        output_path=existing.output_path,
        request_path=existing.request_path,
        artifact_paths=artifact_paths
        if artifact_paths is not None
        else existing.artifact_paths,
        result_summary=result_summary
        if result_summary is not None
        else existing.result_summary,
        pid=pid if pid is not None else existing.pid,
        exit_code=exit_code if exit_code is not None else existing.exit_code,
        error_code=error_code,
        error_message=error_message,
        error_retryable=error_retryable,
        error_severity=error_severity,
    )
    write_ui_run_record(
        UiRunRecordWriteRequest(
            schema_version="1.0",
            registry_path=worker_request.registry_path,
            record=updated,
        ),
        run_ctx,
    )
    return updated


@cli_app.command("replay-run")
def replay_run(
    run_id: str = typer.Option(..., help="Original UI run identifier to replay"),
    registry_path: str | None = typer.Option(
        None,
        help="Optional UI-run registry path. Defaults to the configured state DB sibling.",
    ),
):
    _sync_cli_patch_points()
    ctx = new_run_context(task_id=f"cli_replay_run:{run_id}")
    setup_logging(LoggingSetupRequest(schema_version="1.0"), ctx)
    resolved_registry_path = str(registry_path or "").strip()
    if not resolved_registry_path:
        settings = load_settings(ConfigLoadRequest(schema_version="1.0", path=""), ctx)
        resolved_registry_path = default_ui_run_registry_path(settings.state_db)
    result = replay_ui_run(
        UiRunReplayRequest(
            schema_version="1.0",
            registry_path=resolved_registry_path,
            run_id=RunId(run_id),
        ),
        ctx,
    )
    table = Table(title="UI Run Replay", box=box.SIMPLE_HEAVY)
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("Run ID", str(result.original_record.run_id))
    table.add_row("Run type", result.original_record.run_type)
    table.add_row("Replay status", result.report.replay_status)
    table.add_row("Matched", str(result.report.matched))
    table.add_row("Manifest", result.manifest_path)
    table.add_row("Report", result.report_path)
    table.add_row("Delta count", str(len(result.report.deltas)))
    console.print(table)
    if not result.report.matched:
        raise typer.Exit(code=1)


@cli_app.command("reap-ui-dead-letters")
def reap_ui_dead_letters(
    registry_path: str | None = typer.Option(
        None,
        help="Optional UI-run registry path. Defaults to the configured state DB sibling.",
    ),
    cooldown_seconds: int = typer.Option(
        300, min=0, help="Minimum failed-run age before an automated retry."
    ),
    limit: int = typer.Option(10, min=1, help="Maximum replacement workers to launch."),
    max_recovery_attempts: int = typer.Option(
        3,
        min=1,
        help="Maximum automated replacement launches for one recovery chain.",
    ),
):
    _sync_cli_patch_points()
    ctx = new_run_context(task_id="cli_reap_ui_dead_letters")
    setup_logging(LoggingSetupRequest(schema_version="1.0"), ctx)
    resolved_registry_path = str(registry_path or "").strip()
    if not resolved_registry_path:
        settings = load_settings(ConfigLoadRequest(schema_version="1.0", path=""), ctx)
        resolved_registry_path = default_ui_run_registry_path(settings.state_db)
    result = reap_dead_letter_runs(
        UiRunDeadLetterReapRequest(
            schema_version="1.0",
            registry_path=resolved_registry_path,
            workspace_root=os.getcwd(),
            cooldown_seconds=cooldown_seconds,
            limit=limit,
            max_recovery_attempts=max_recovery_attempts,
        ),
        ctx,
    )
    table = Table(title="UI Dead-letter Reaper", box=box.SIMPLE_HEAVY)
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("Inspected", str(result.inspected_count))
    table.add_row("Recovered", str(len(result.recovered_run_ids)))
    table.add_row("Held", str(len(result.held_run_ids)))
    console.print(table)


@cli_app.command("ui-run-worker", hidden=True)
def ui_run_worker(
    request_json: str = typer.Option(
        ...,
        "--request-json",
        help="Internal worker request JSON path.",
    ),
):
    _sync_cli_patch_points()
    worker_request = _load_ui_run_worker_request(request_json)
    ctx = new_run_context(task_id=f"ui_run_worker:{worker_request.run_type}")
    setup_logging(LoggingSetupRequest(schema_version="1.0"), ctx)
    started_at = _utc_now()
    _update_ui_run_record(
        worker_request=worker_request,
        run_ctx=ctx,
        status="running",
        started_at_utc=started_at,
        pid=os.getpid(),
    )
    print(
        f"[ui-run-worker] started run_id={worker_request.run_id} type={worker_request.run_type}",
        flush=True,
    )
    try:
        execution = execute_ui_run(worker_request, ctx)
        finished_at = _utc_now()
        write_ui_run_replay_manifest(
            UiRunReplayCaptureRequest(
                schema_version="1.0",
                registry_path=worker_request.registry_path,
                run_id=worker_request.run_id,
                run_type=worker_request.run_type,
                status=execution.status,
                recorded_at_utc=finished_at,
                request_payload=worker_request.request_payload,
                config_snapshot=execution.config_snapshot,
                config_fingerprint=execution.config_fingerprint,
                source_tree_root=str(SOURCE_TREE_ROOT),
                prompt_tree_root=str(PROMPT_TREE_ROOT),
                artifact_paths=execution.artifact_paths,
                result_summary=execution.result_summary,
                error_code=execution.error_code,
                error_message=execution.error_message,
            ),
            ctx,
        )
        if execution.status != "succeeded":
            _update_ui_run_record(
                worker_request=worker_request,
                run_ctx=ctx,
                status="failed",
                finished_at_utc=finished_at,
                pid=os.getpid(),
                exit_code=1,
                error_code=execution.error_code or "ui_run_worker_failed",
                error_message=execution.error_message or "UI run execution failed.",
                error_retryable=execution.error_retryable,
                error_severity=execution.error_severity,
            )
            print(
                f"[ui-run-worker] failed run_id={worker_request.run_id} code={execution.error_code} message={execution.error_message}",
                flush=True,
            )
            raise typer.Exit(code=1)
        _update_ui_run_record(
            worker_request=worker_request,
            run_ctx=ctx,
            status="succeeded",
            finished_at_utc=finished_at,
            pid=os.getpid(),
            exit_code=0,
            result_summary=execution.result_summary,
            artifact_paths=execution.artifact_paths,
        )
        print(
            f"[ui-run-worker] completed run_id={worker_request.run_id}",
            flush=True,
        )
    except AppError as exc:
        _update_ui_run_record(
            worker_request=worker_request,
            run_ctx=ctx,
            status="failed",
            finished_at_utc=_utc_now(),
            pid=os.getpid(),
            exit_code=1,
            error_code=exc.code,
            error_message=exc.message,
            error_retryable=exc.retryable,
            error_severity=exc.severity,
        )
        print(
            f"[ui-run-worker] failed run_id={worker_request.run_id} code={exc.code} message={exc.message}",
            flush=True,
        )
        raise typer.Exit(code=1)
    except typer.Exit:
        raise
    except Exception as exc:
        _update_ui_run_record(
            worker_request=worker_request,
            run_ctx=ctx,
            status="failed",
            finished_at_utc=_utc_now(),
            pid=os.getpid(),
            exit_code=1,
            error_code="ui_run_worker_failed",
            error_message=str(exc),
            error_retryable=False,
            error_severity="error",
        )
        print(
            f"[ui-run-worker] failed run_id={worker_request.run_id} error={exc}",
            flush=True,
        )
        raise typer.Exit(code=1)
