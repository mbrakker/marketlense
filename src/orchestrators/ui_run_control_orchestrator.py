from __future__ import annotations

import json
import logging
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from src.contracts.run_context import RunContext
from src.contracts.semantic_ids import RunId
from src.contracts.ui_run_control import (
    ProcessLaunchRequest,
    ProcessOutputChunk,
    ProcessOutputReadRequest,
    ProcessPollRequest,
    ProcessTerminateRequest,
    UiRunCancelRequest,
    UiRunCancelResponse,
    UiRunLaunchRequest,
    UiRunLaunchResponse,
    UiRunListRequest,
    UiRunListResponse,
    UiRunPollRequest,
    UiRunPollResponse,
    UiRunRecord,
    UiRunRecordGetRequest,
    UiRunRecordListRequest,
    UiRunRecordWriteRequest,
    UiRunSummary,
    UiRunWorkerRequest,
)
from src.services.process_service import (
    launch_process,
    poll_process,
    read_process_output,
    terminate_process,
)
from src.services.run_registry_service import (
    get_ui_run_record,
    list_ui_run_records,
    write_ui_run_record,
)
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.ui_run_control_orchestrator")

FINAL_UI_RUN_STATUSES = {"succeeded", "failed", "canceled"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_state_dir(registry_path: str) -> Path:
    registry = Path(registry_path).expanduser().resolve()
    return registry.parent / "ui_runs"


def _summary(record: UiRunRecord) -> UiRunSummary:
    return UiRunSummary(
        schema_version="1.0",
        run_id=record.run_id,
        run_type=record.run_type,
        display_name=record.display_name,
        status=record.status,
        created_at_utc=record.created_at_utc,
        started_at_utc=record.started_at_utc,
        finished_at_utc=record.finished_at_utc,
        output_path=record.output_path,
        pid=record.pid,
        exit_code=record.exit_code,
        error_code=record.error_code,
    )


def _write_worker_request(request_path: Path, worker_request: UiRunWorkerRequest) -> None:
    request_path.parent.mkdir(parents=True, exist_ok=True)
    request_path.write_text(
        json.dumps(asdict(worker_request), ensure_ascii=True, indent=2),
        encoding="utf-8",
    )


def launch_ui_run(
    request: UiRunLaunchRequest, ctx: RunContext
) -> UiRunLaunchResponse:
    created_at = _utc_now()
    run_id = RunId(str(uuid4()))
    run_dir = _run_state_dir(request.registry_path) / run_id
    request_path = run_dir / "request.json"
    output_path = run_dir / "output.log"
    worker_request = UiRunWorkerRequest(
        schema_version="1.0",
        registry_path=request.registry_path,
        run_id=run_id,
        run_type=request.run_type,
        request_payload=request.request_payload,
    )
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="ui_run_launch_start",
            module=logger.name,
            fields={
                "registry_path": request.registry_path,
                "run_id": run_id,
                "run_type": request.run_type,
                "display_name": request.display_name,
            },
        )
    )
    _write_worker_request(request_path, worker_request)
    command = [
        sys.executable,
        "-m",
        "src.cli",
        "ui-run-worker",
        "--request-json",
        str(request_path),
    ]
    record = UiRunRecord(
        schema_version="1.0",
        run_id=run_id,
        run_type=request.run_type,
        display_name=request.display_name,
        status="queued",
        request_payload=request.request_payload,
        command=command,
        created_at_utc=created_at,
        updated_at_utc=created_at,
        output_path=str(output_path),
        request_path=str(request_path),
    )
    write_ui_run_record(
        UiRunRecordWriteRequest(
            schema_version="1.0",
            registry_path=request.registry_path,
            record=record,
        ),
        ctx,
    )
    try:
        process = launch_process(
            ProcessLaunchRequest(
                schema_version="1.0",
                command=command,
                cwd=request.workspace_root,
                output_path=str(output_path),
            ),
            ctx,
        )
    except Exception as exc:
        failed_record = UiRunRecord(
            schema_version="1.0",
            run_id=record.run_id,
            run_type=record.run_type,
            display_name=record.display_name,
            status="failed",
            request_payload=record.request_payload,
            command=record.command,
            created_at_utc=record.created_at_utc,
            updated_at_utc=_utc_now(),
            finished_at_utc=_utc_now(),
            output_path=record.output_path,
            request_path=record.request_path,
            error_code="ui_run_launch_failed",
            error_message=str(exc),
        )
        write_ui_run_record(
            UiRunRecordWriteRequest(
                schema_version="1.0",
                registry_path=request.registry_path,
                record=failed_record,
            ),
            ctx,
        )
        raise
    launched_record = UiRunRecord(
        schema_version="1.0",
        run_id=record.run_id,
        run_type=record.run_type,
        display_name=record.display_name,
        status=record.status,
        request_payload=record.request_payload,
        command=record.command,
        created_at_utc=record.created_at_utc,
        updated_at_utc=_utc_now(),
        output_path=record.output_path,
        request_path=record.request_path,
        pid=process.pid,
    )
    write_ui_run_record(
        UiRunRecordWriteRequest(
            schema_version="1.0",
            registry_path=request.registry_path,
            record=launched_record,
        ),
        ctx,
    )
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="ui_run_launch_complete",
            module=logger.name,
            fields={
                "registry_path": request.registry_path,
                "run_id": launched_record.run_id,
                "run_type": launched_record.run_type,
                "pid": launched_record.pid,
                "output_path": launched_record.output_path,
            },
        )
    )
    return UiRunLaunchResponse(schema_version="1.0", record=launched_record)


def poll_ui_run(request: UiRunPollRequest, ctx: RunContext) -> UiRunPollResponse:
    stored = get_ui_run_record(
        UiRunRecordGetRequest(
            schema_version="1.0",
            registry_path=request.registry_path,
            run_id=request.run_id,
        ),
        ctx,
    ).record
    if stored is None:
        raise AppError(
            code="ui_run_not_found",
            message=f"UI run not found: {request.run_id}",
            retryable=False,
            context={"run_id": request.run_id},
        )
    record = stored
    if record.status not in FINAL_UI_RUN_STATUSES and record.pid is not None:
        process = poll_process(
            ProcessPollRequest(schema_version="1.0", pid=record.pid),
            ctx,
        )
        if not process.running and record.status not in FINAL_UI_RUN_STATUSES:
            record = UiRunRecord(
                schema_version="1.0",
                run_id=record.run_id,
                run_type=record.run_type,
                display_name=record.display_name,
                status="failed",
                request_payload=record.request_payload,
                command=record.command,
                created_at_utc=record.created_at_utc,
                updated_at_utc=_utc_now(),
                started_at_utc=record.started_at_utc,
                finished_at_utc=_utc_now(),
                output_path=record.output_path,
                request_path=record.request_path,
                artifact_paths=record.artifact_paths,
                result_summary=record.result_summary,
                pid=record.pid,
                exit_code=record.exit_code if record.exit_code is not None else 1,
                error_code=record.error_code or "ui_run_worker_exited_unexpectedly",
                error_message=record.error_message
                or "Background worker exited without recording a terminal status.",
            )
            write_ui_run_record(
                UiRunRecordWriteRequest(
                    schema_version="1.0",
                    registry_path=request.registry_path,
                    record=record,
                ),
                ctx,
            )
    output_chunk: ProcessOutputChunk | None = None
    if record.output_path:
        output_chunk = read_process_output(
            ProcessOutputReadRequest(
                schema_version="1.0",
                path=record.output_path,
                max_bytes=request.output_tail_bytes,
            ),
            ctx,
        ).chunk
    return UiRunPollResponse(
        schema_version="1.0",
        record=record,
        output_chunk=output_chunk,
    )


def cancel_ui_run(
    request: UiRunCancelRequest, ctx: RunContext
) -> UiRunCancelResponse:
    stored = get_ui_run_record(
        UiRunRecordGetRequest(
            schema_version="1.0",
            registry_path=request.registry_path,
            run_id=request.run_id,
        ),
        ctx,
    ).record
    if stored is None:
        raise AppError(
            code="ui_run_not_found",
            message=f"UI run not found: {request.run_id}",
            retryable=False,
            context={"run_id": request.run_id},
        )
    canceled = False
    if stored.status not in FINAL_UI_RUN_STATUSES and stored.pid is not None:
        terminate_process(
            ProcessTerminateRequest(schema_version="1.0", pid=stored.pid),
            ctx,
        )
        canceled = True
    record = stored
    if stored.status not in FINAL_UI_RUN_STATUSES:
        record = UiRunRecord(
            schema_version="1.0",
            run_id=stored.run_id,
            run_type=stored.run_type,
            display_name=stored.display_name,
            status="canceled",
            request_payload=stored.request_payload,
            command=stored.command,
            created_at_utc=stored.created_at_utc,
            updated_at_utc=_utc_now(),
            started_at_utc=stored.started_at_utc,
            finished_at_utc=_utc_now(),
            output_path=stored.output_path,
            request_path=stored.request_path,
            artifact_paths=stored.artifact_paths,
            result_summary=stored.result_summary,
            pid=stored.pid,
            exit_code=stored.exit_code,
            error_code=stored.error_code,
            error_message=stored.error_message,
        )
        write_ui_run_record(
            UiRunRecordWriteRequest(
                schema_version="1.0",
                registry_path=request.registry_path,
                record=record,
            ),
            ctx,
        )
    return UiRunCancelResponse(
        schema_version="1.0",
        record=record,
        canceled=canceled,
    )


def list_ui_runs(request: UiRunListRequest, ctx: RunContext) -> UiRunListResponse:
    records = list_ui_run_records(
        UiRunRecordListRequest(
            schema_version="1.0",
            registry_path=request.registry_path,
            statuses=request.statuses,
            limit=request.limit,
        ),
        ctx,
    ).records
    return UiRunListResponse(
        schema_version="1.0",
        records=[_summary(record) for record in records],
    )
