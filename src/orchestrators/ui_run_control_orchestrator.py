from __future__ import annotations

import logging
import sys
from uuid import uuid4

from src.contracts.run_context import RunContext
from src.contracts.semantic_ids import RunId
from src.contracts.ui_run_control import (
    UiRunDeadLetterActionListRequest,
    UiRunDeadLetterActionListResponse,
    UiRunDeadLetterActionRequest,
    UiRunDeadLetterActionResponse,
    UiRunDeadLetterListRequest,
    UiRunDeadLetterListResponse,
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
    UiRunWorkerRequestWriteRequest,
)
from src.services.process_service import (
    launch_process,
    poll_process,
    read_process_output,
    terminate_process,
)
from src.services.run_registry_service import (
    get_ui_run_record,
    list_ui_run_dead_letter_actions,
    list_ui_run_dead_letters,
    list_ui_run_records,
    record_ui_run_dead_letter_action,
    write_ui_run_record,
)
from src.services.ui_run_replay_service import write_ui_run_worker_request
from src.utils.clock import utc_now_iso as _utc_now
from src.utils.errors import AppError
from src.utils.logging import log_event
from src.utils.ui_run_dead_letter import classify_ui_run_failure
from src.utils.ui_run_paths import ui_run_dir

logger = logging.getLogger("market_lense.ui_run_control_orchestrator")

FINAL_UI_RUN_STATUSES = {"succeeded", "failed", "canceled"}


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
        error_retryable=record.error_retryable,
        error_severity=record.error_severity,
    )


def launch_ui_run(request: UiRunLaunchRequest, ctx: RunContext) -> UiRunLaunchResponse:
    created_at = _utc_now()
    run_id = RunId(str(uuid4()))
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
    worker_write = write_ui_run_worker_request(
        UiRunWorkerRequestWriteRequest(
            schema_version="1.0",
            registry_path=request.registry_path,
            worker_request=worker_request,
        ),
        ctx,
    )
    request_path = worker_write.request_path
    output_path = str(ui_run_dir(request.registry_path, run_id) / "output.log")
    command = [
        sys.executable,
        "-m",
        "src.cli",
        "ui-run-worker",
        "--request-json",
        request_path,
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
        output_path=output_path,
        request_path=request_path,
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
            error_retryable=exc.retryable if isinstance(exc, AppError) else False,
            error_severity=exc.severity if isinstance(exc, AppError) else "error",
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
        status="running",
        request_payload=record.request_payload,
        command=record.command,
        created_at_utc=record.created_at_utc,
        updated_at_utc=_utc_now(),
        started_at_utc=process.started_at_utc,
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
        if process.running and record.status == "queued":
            record = UiRunRecord(
                schema_version="1.0",
                run_id=record.run_id,
                run_type=record.run_type,
                display_name=record.display_name,
                status="running",
                request_payload=record.request_payload,
                command=record.command,
                created_at_utc=record.created_at_utc,
                updated_at_utc=_utc_now(),
                started_at_utc=record.started_at_utc or _utc_now(),
                output_path=record.output_path,
                request_path=record.request_path,
                artifact_paths=record.artifact_paths,
                result_summary=record.result_summary,
                pid=record.pid,
                exit_code=record.exit_code,
                error_code=record.error_code,
                error_message=record.error_message,
            )
            write_ui_run_record(
                UiRunRecordWriteRequest(
                    schema_version="1.0",
                    registry_path=request.registry_path,
                    record=record,
                ),
                ctx,
            )
        elif not process.running and record.status not in FINAL_UI_RUN_STATUSES:
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
                error_retryable=False,
                error_severity="error",
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
    failure_classification = None
    if record.status == "failed":
        failure_classification = classify_ui_run_failure(
            record=record,
            output_tail=output_chunk.text if output_chunk is not None else "",
        )
    return UiRunPollResponse(
        schema_version="1.0",
        record=record,
        output_chunk=output_chunk,
        failure_classification=failure_classification,
    )


def cancel_ui_run(request: UiRunCancelRequest, ctx: RunContext) -> UiRunCancelResponse:
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
            error_retryable=stored.error_retryable,
            error_severity=stored.error_severity,
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


def list_dead_letter_runs(
    request: UiRunDeadLetterListRequest, ctx: RunContext
) -> UiRunDeadLetterListResponse:
    return list_ui_run_dead_letters(request, ctx)


def list_dead_letter_actions(
    request: UiRunDeadLetterActionListRequest, ctx: RunContext
) -> UiRunDeadLetterActionListResponse:
    return list_ui_run_dead_letter_actions(request, ctx)


def apply_dead_letter_action(
    request: UiRunDeadLetterActionRequest, ctx: RunContext
) -> UiRunDeadLetterActionResponse:
    return record_ui_run_dead_letter_action(request, ctx)
