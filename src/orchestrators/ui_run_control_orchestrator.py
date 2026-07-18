from __future__ import annotations

import hashlib
import json
import logging
import sys
from datetime import UTC, datetime
from typing import Callable, cast
from uuid import uuid4

from src.contracts.config import ConfigLoadRequest
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
    UiRunDeadLetterActionListRequest,
    UiRunDeadLetterActionListResponse,
    UiRunDeadLetterActionRequest,
    UiRunDeadLetterActionResponse,
    UiRunDeadLetterListRequest,
    UiRunDeadLetterListResponse,
    UiRunDeadLetterReapRequest,
    UiRunDeadLetterReapResponse,
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
from src.contracts.workflow_queue import (
    BriefingOpportunityPayload,
    PublisherDiscoveryPayload,
    ReportAcquisitionPayload,
    SignalCandidatePayload,
    WorkflowJobSubmission,
)
from src.services.config_service import load_settings
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
from src.services.workflow_queue_service import (
    cancel_workflow_job,
    enqueue_workflow_job,
    get_workflow_job,
)
from src.utils.clock import utc_now_iso as _utc_now
from src.utils.errors import AppError
from src.utils.logging import log_event
from src.utils.ui_run_dead_letter import classify_ui_run_failure
from src.utils.ui_run_paths import ui_run_dir

logger = logging.getLogger("market_lense.ui_run_control_orchestrator")

FINAL_UI_RUN_STATUSES = {"succeeded", "failed", "canceled"}
_QUEUE_SUBMISSION_FLAG = "workflow_queue_submit"
_QUEUE_JOB_ID_KEY = "workflow_queue_job_id"
_QUEUE_STATE_DB_KEY = "workflow_queue_state_db"


def _ui_payload_hash(*parts: object) -> str:
    """Return a stable non-sensitive identity for a typed UI queue request."""

    encoded = json.dumps(
        parts,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _ui_string_list(payload: dict[str, object], field_name: str) -> list[str]:
    raw = payload.get(field_name, [])
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        raise AppError(
            code="ui_run_payload_list_invalid",
            message="Queue-backed UI list fields must contain strings",
            retryable=False,
            context={"field": field_name},
        )
    return [item.strip() for item in raw if item.strip()]


def _ui_positive_int(payload: dict[str, object], field_name: str, default: int) -> int:
    raw = payload.get(field_name, default)
    if isinstance(raw, bool) or not isinstance(raw, (int, str)):
        raise AppError(
            code="ui_run_payload_number_invalid",
            message="Queue-backed UI numeric fields must be positive integers",
            retryable=False,
            context={"field": field_name},
        )
    try:
        value = int(raw or default)
    except (TypeError, ValueError) as exc:
        raise AppError(
            code="ui_run_payload_number_invalid",
            message="Queue-backed UI numeric fields must be positive integers",
            cause=exc,
            retryable=False,
            context={"field": field_name},
        ) from exc
    if value < 1:
        raise AppError(
            code="ui_run_payload_number_invalid",
            message="Queue-backed UI numeric fields must be positive integers",
            retryable=False,
            context={"field": field_name},
        )
    return value


def _ui_boolean(payload: dict[str, object], field_name: str, default: bool) -> bool:
    raw = payload.get(field_name, default)
    if not isinstance(raw, bool):
        raise AppError(
            code="ui_run_payload_boolean_invalid",
            message="Queue-backed UI boolean fields must be booleans",
            retryable=False,
            context={"field": field_name},
        )
    return raw


def _ui_queue_submission(
    *,
    run_id: RunId,
    run_type: str,
    payload: dict[str, object],
) -> WorkflowJobSubmission | None:
    """Map supported UI requests onto the fixed typed workflow graph."""

    normalized_type = str(run_type or "").strip().lower()
    if normalized_type == "publisher_discovery":
        insights_url = str(payload.get("insights_url") or "").strip()
        if not insights_url:
            raise AppError(
                code="ui_run_payload_insights_url_missing",
                message="Publisher discovery requires an insights URL",
                retryable=False,
            )
        publisher_id = "ui-publisher:" + insights_url
        return WorkflowJobSubmission(
            schema_version="1.0",
            queue_name="publisher_discovery",
            job_type="publisher_discovery.v1",
            payload=PublisherDiscoveryPayload(
                publisher_id=publisher_id,
                insights_url=insights_url,
                discovery_policy_version="ui-v1",
                input_reference=insights_url,
                input_content_hash=_ui_payload_hash("publisher", insights_url, "ui-v1"),
                processing_version="ui-v1",
            ),
            idempotency_key=f"{publisher_id}:ui-v1",
            deduplication_scope="ui-publisher-discovery",
            root_workflow_id=str(run_id),
            correlation_id=str(run_id),
            publisher_id=publisher_id,
            budget_profile="publisher_inventory",
        )
    if normalized_type == "report_download":
        source_url = str(payload.get("url") or "").strip()
        if not source_url:
            raise AppError(
                code="ui_run_payload_url_missing",
                message="Report download requires a source URL",
                retryable=False,
            )
        source_identity_id = "ui-source:" + source_url
        return WorkflowJobSubmission(
            schema_version="1.0",
            queue_name="report_acquisition",
            job_type="report_acquisition.v1",
            payload=ReportAcquisitionPayload(
                source_identity_id=source_identity_id,
                source_url=source_url,
                acquisition_policy_version="ui-v1",
                input_reference=source_url,
                input_content_hash=_ui_payload_hash("source", source_url, "ui-v1"),
                processing_version="ui-v1",
                attributes={
                    "delivery_email": str(payload.get("delivery_email") or ""),
                    "publisher_insights_url": str(
                        payload.get("publisher_insights_url") or ""
                    ),
                    "publisher_google_folder": str(
                        payload.get("publisher_google_folder") or ""
                    ),
                },
            ),
            idempotency_key=f"{source_identity_id}:ui-v1",
            deduplication_scope="ui-report-acquisition",
            root_workflow_id=str(run_id),
            correlation_id=str(run_id),
            source_identity_id=source_identity_id,
            budget_profile="browser_acquisition",
        )
    if normalized_type in {"signal_candidate_extraction", "signal_post"}:
        topic = str(payload.get("topic") or "").strip()
        if not topic:
            raise AppError(
                code="ui_run_payload_topic_missing",
                message="Signal queue submission requires a topic",
                retryable=False,
            )
        request_hash = _ui_payload_hash(
            "signal",
            normalized_type,
            topic,
            _ui_string_list(payload, "category_filters"),
            _ui_string_list(payload, "tag_filters"),
            _ui_string_list(payload, "publisher_filters"),
            payload.get("date_range_start") or "",
            payload.get("date_range_end") or "",
            _ui_positive_int(payload, "max_source_reports", 3),
            _ui_positive_int(payload, "max_evidence_items", 6),
            _ui_positive_int(payload, "max_signals", 8),
        )
        generate_signals = normalized_type == "signal_post"
        return WorkflowJobSubmission(
            schema_version="1.0",
            queue_name="signal_candidate",
            job_type="signal_candidate.v1",
            payload=SignalCandidatePayload(
                projection_reference=f"ui-run:{run_id}",
                signal_selection_policy_version="ui-signal-v1",
                input_reference=f"ui-run:{run_id}",
                input_content_hash=request_hash,
                processing_version="ui-signal-v1",
                attributes={
                    "category_filters": _ui_string_list(payload, "category_filters"),
                    "date_range_end": str(payload.get("date_range_end") or ""),
                    "date_range_start": str(payload.get("date_range_start") or ""),
                    "generate_signals": generate_signals,
                    "max_evidence_items": _ui_positive_int(
                        payload, "max_evidence_items", 6
                    ),
                    "max_signals": _ui_positive_int(payload, "max_signals", 8),
                    "max_source_reports": _ui_positive_int(
                        payload, "max_source_reports", 3
                    ),
                    "minimum_evidence_items": _ui_positive_int(
                        payload, "minimum_evidence_items", 2
                    ),
                    "minimum_source_reports": _ui_positive_int(
                        payload, "minimum_source_reports", 2
                    ),
                    "publisher_filters": _ui_string_list(payload, "publisher_filters"),
                    "tag_filters": _ui_string_list(payload, "tag_filters"),
                    "topic": topic,
                },
            ),
            idempotency_key=request_hash,
            deduplication_scope=f"ui-{normalized_type}",
            root_workflow_id=str(run_id),
            correlation_id=str(run_id),
            entity_type="signal",
            entity_id=topic,
            budget_profile="signal_candidate",
        )
    if normalized_type == "cross_report_analysis":
        auto_theme = _ui_boolean(payload, "auto_theme", True)
        topic = str(payload.get("topic") or "").strip()
        if not topic and not auto_theme:
            raise AppError(
                code="ui_run_payload_topic_missing",
                message=(
                    "Briefing queue submission requires a topic when auto-theme is off"
                ),
                retryable=False,
            )
        request_hash = _ui_payload_hash(
            "briefing",
            topic or "automatic-theme",
            auto_theme,
            _ui_string_list(payload, "category_filters"),
            _ui_string_list(payload, "tag_filters"),
            _ui_string_list(payload, "publisher_filters"),
            payload.get("date_range_start") or "",
            payload.get("date_range_end") or "",
            _ui_positive_int(payload, "max_source_reports", 6),
            _ui_positive_int(payload, "max_evidence_items", 48),
            _ui_positive_int(payload, "max_prompt_chars", 60_000),
        )
        return WorkflowJobSubmission(
            schema_version="1.0",
            queue_name="briefing_opportunity",
            job_type="briefing_opportunity.v1",
            payload=BriefingOpportunityPayload(
                projection_event_id=f"ui-run:{run_id}",
                topic=topic or "automatic-theme",
                rolling_window=f"ui:{request_hash[:24]}",
                briefing_policy_version="ui-briefing-v1",
                input_reference=f"ui-run:{run_id}",
                input_content_hash=request_hash,
                processing_version="ui-briefing-v1",
                prompt_policy_version="ui-briefing-v1",
                attributes={
                    "auto_theme": auto_theme,
                    "category_filters": _ui_string_list(payload, "category_filters"),
                    "date_range_end": str(payload.get("date_range_end") or ""),
                    "date_range_start": str(payload.get("date_range_start") or ""),
                    "diagnostic": _ui_boolean(payload, "diagnostic", False),
                    "max_evidence_items": _ui_positive_int(
                        payload, "max_evidence_items", 48
                    ),
                    "max_prompt_chars": _ui_positive_int(
                        payload, "max_prompt_chars", 60_000
                    ),
                    "max_source_reports": _ui_positive_int(
                        payload, "max_source_reports", 6
                    ),
                    "max_signals": 8,
                    "minimum_distinct_reports": 2,
                    "minimum_publisher_diversity": 2,
                    "override_publishability": _ui_boolean(
                        payload, "override_publishability", False
                    ),
                    "publisher_filters": _ui_string_list(payload, "publisher_filters"),
                    "publisher_ids": [],
                    "resolve_projected_sources": True,
                    "tag_filters": _ui_string_list(payload, "tag_filters"),
                },
            ),
            idempotency_key=request_hash,
            deduplication_scope="ui-briefing-request",
            root_workflow_id=str(run_id),
            correlation_id=str(run_id),
            entity_type="briefing",
            entity_id=topic or "automatic-theme",
            budget_profile="briefing_opportunity",
        )
    return None


def _queue_record_from_job(record: UiRunRecord, job) -> UiRunRecord:
    """Render durable queue state through the established UI-run compatibility view."""

    status_map = {
        "pending": "queued",
        "leased": "running",
        "running": "running",
        "retry_wait": "queued",
        "budget_deferred": "queued",
        "blocked": "failed",
        "dead_letter": "failed",
        "cancelled": "canceled",
        "succeeded": "succeeded",
    }
    ui_status = status_map.get(job.status, "failed")
    terminal = ui_status in FINAL_UI_RUN_STATUSES
    return UiRunRecord(
        schema_version="1.0",
        run_id=record.run_id,
        run_type=record.run_type,
        display_name=record.display_name,
        status=ui_status,
        request_payload=record.request_payload,
        command=[],
        created_at_utc=record.created_at_utc,
        updated_at_utc=_utc_now(),
        started_at_utc=job.started_at_utc or record.started_at_utc,
        finished_at_utc=job.completed_at_utc if terminal else "",
        artifact_paths=[
            value for value in (job.input_reference, job.output_reference) if value
        ],
        result_summary={
            "workflow_job_id": job.job_id,
            "queue_name": job.queue_name,
            "queue_status": job.status,
            "attempt_count": job.attempt_count,
            "output_verified": bool(job.output_reference),
        },
        error_code=job.error_code,
        error_message=job.error_message_summary,
        error_retryable=job.error_retryable,
        error_severity="error" if job.error_code else "",
    )


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
    if bool(request.request_payload.get(_QUEUE_SUBMISSION_FLAG, False)):
        submission = _ui_queue_submission(
            run_id=run_id,
            run_type=request.run_type,
            payload=request.request_payload,
        )
        if submission is not None:
            app = load_settings(ConfigLoadRequest(schema_version="1.0", path=""), ctx)
            job, _ = enqueue_workflow_job(app.state_db, submission, ctx)
            queue_payload = dict(request.request_payload)
            queue_payload[_QUEUE_JOB_ID_KEY] = job.job_id
            queue_payload[_QUEUE_STATE_DB_KEY] = app.state_db
            record = UiRunRecord(
                schema_version="1.0",
                run_id=run_id,
                run_type=request.run_type,
                display_name=request.display_name,
                status="queued",
                request_payload=queue_payload,
                command=[],
                created_at_utc=created_at,
                updated_at_utc=created_at,
                result_summary={
                    "workflow_job_id": job.job_id,
                    "queue_name": job.queue_name,
                    "queue_status": job.status,
                },
            )
            write_ui_run_record(
                UiRunRecordWriteRequest(
                    schema_version="1.0",
                    registry_path=request.registry_path,
                    record=record,
                ),
                ctx,
            )
            logger.info(
                log_event(
                    ctx,
                    role="orchestrator",
                    event="ui_run_queue_submission_complete",
                    module=logger.name,
                    fields={
                        "run_id": run_id,
                        "run_type": request.run_type,
                        "workflow_job_id": job.job_id,
                        "queue_name": job.queue_name,
                    },
                )
            )
            return UiRunLaunchResponse(schema_version="1.0", record=record)
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
    workflow_job_id = str(record.request_payload.get(_QUEUE_JOB_ID_KEY) or "").strip()
    workflow_state_db = str(
        record.request_payload.get(_QUEUE_STATE_DB_KEY) or ""
    ).strip()
    if workflow_job_id and workflow_state_db:
        job = get_workflow_job(workflow_state_db, workflow_job_id, ctx)
        if job is None:
            raise AppError(
                code="ui_run_workflow_job_missing",
                message="UI run references a missing durable workflow job",
                retryable=False,
                context={"run_id": record.run_id, "workflow_job_id": workflow_job_id},
            )
        record = _queue_record_from_job(record, job)
        write_ui_run_record(
            UiRunRecordWriteRequest(
                schema_version="1.0",
                registry_path=request.registry_path,
                record=record,
            ),
            ctx,
        )
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
    workflow_job_id = str(stored.request_payload.get(_QUEUE_JOB_ID_KEY) or "").strip()
    workflow_state_db = str(
        stored.request_payload.get(_QUEUE_STATE_DB_KEY) or ""
    ).strip()
    if workflow_job_id and workflow_state_db:
        job = cancel_workflow_job(
            workflow_state_db,
            workflow_job_id,
            str(ctx.run_id),
            ctx,
        )
        record = _queue_record_from_job(stored, job)
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
            canceled=job.status == "cancelled",
        )
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


def reap_dead_letter_runs(
    request: UiRunDeadLetterReapRequest,
    ctx: RunContext,
    *,
    launch_run: Callable[
        [UiRunLaunchRequest, RunContext], UiRunLaunchResponse
    ] = launch_ui_run,
) -> UiRunDeadLetterReapResponse:
    """Launch one idempotent replacement only for cooled-down retryable dead letters."""
    records = list_dead_letter_runs(
        UiRunDeadLetterListRequest(
            schema_version="1.0",
            registry_path=request.registry_path,
            triage_statuses=["open"],
            limit=max(1, request.limit),
        ),
        ctx,
    ).records
    now = datetime.now(UTC)
    recovered: list[RunId] = []
    held: list[RunId] = []
    for dead_letter in records:
        if not dead_letter.error_taxonomy.retryable or not _dead_letter_is_cooled_down(
            dead_letter.failed_at_utc,
            now=now,
            cooldown_seconds=request.cooldown_seconds,
        ):
            if not dead_letter.error_taxonomy.retryable:
                _escalate_dead_letter(
                    request=request,
                    dead_letter=dead_letter,
                    note="automatic_escalation:non_retryable_failure",
                    ctx=ctx,
                )
            held.append(dead_letter.run_id)
            continue
        stored = get_ui_run_record(
            UiRunRecordGetRequest(
                schema_version="1.0",
                registry_path=request.registry_path,
                run_id=dead_letter.run_id,
            ),
            ctx,
        ).record
        if stored is None or stored.status != "failed":
            held.append(dead_letter.run_id)
            continue
        classification = classify_ui_run_failure(record=stored)
        if not classification.retryable or classification.action not in {
            "retry_now",
            "retry_later",
            "resume_from_checkpoint",
        }:
            _escalate_dead_letter(
                request=request,
                dead_letter=dead_letter,
                note=f"automatic_escalation:{classification.action}",
                ctx=ctx,
            )
            held.append(dead_letter.run_id)
            continue
        payload = dict(stored.request_payload)
        recovery_attempt = _recovery_attempt(payload)
        if recovery_attempt >= max(0, request.max_recovery_attempts):
            _escalate_dead_letter(
                request=request,
                dead_letter=dead_letter,
                note="automatic_escalation:recovery_attempt_budget_exhausted",
                ctx=ctx,
            )
            held.append(dead_letter.run_id)
            continue
        payload["_workflow_control_recovery_attempt"] = recovery_attempt + 1
        if classification.resume_stage:
            payload["resume_from_stage"] = classification.resume_stage
        replacement = launch_run(
            UiRunLaunchRequest(
                schema_version="1.0",
                registry_path=request.registry_path,
                workspace_root=request.workspace_root,
                run_type=stored.run_type,
                display_name=f"Recovery: {stored.display_name}",
                request_payload=payload,
            ),
            ctx,
        )
        apply_dead_letter_action(
            UiRunDeadLetterActionRequest(
                schema_version="1.0",
                registry_path=request.registry_path,
                run_id=dead_letter.run_id,
                action="retry_requested",
                actor=request.actor,
                note=f"automatic_recovery:{classification.action}",
                related_run_id=str(replacement.record.run_id),
            ),
            ctx,
        )
        recovered.append(dead_letter.run_id)
    response = UiRunDeadLetterReapResponse(
        schema_version="1.0",
        inspected_count=len(records),
        recovered_run_ids=recovered,
        held_run_ids=held,
    )
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="ui_run_dead_letter_reap_complete",
            module=logger.name,
            fields={
                "inspected_count": response.inspected_count,
                "recovered_count": len(response.recovered_run_ids),
                "held_count": len(response.held_run_ids),
            },
        )
    )
    return response


def _escalate_dead_letter(
    *,
    request: UiRunDeadLetterReapRequest,
    dead_letter,
    note: str,
    ctx: RunContext,
) -> None:
    if dead_letter.triage_status != "open":
        return
    apply_dead_letter_action(
        UiRunDeadLetterActionRequest(
            schema_version="1.0",
            registry_path=request.registry_path,
            run_id=dead_letter.run_id,
            action="escalated",
            actor=request.actor,
            note=note,
        ),
        ctx,
    )


def _dead_letter_is_cooled_down(
    failed_at_utc: str, *, now: datetime, cooldown_seconds: int
) -> bool:
    try:
        failed_at = datetime.fromisoformat(failed_at_utc.replace("Z", "+00:00"))
    except ValueError:
        return False
    return (now - failed_at).total_seconds() >= max(0, cooldown_seconds)


def _recovery_attempt(payload: dict[str, object]) -> int:
    value = payload.get("_workflow_control_recovery_attempt", 0)
    try:
        return max(0, int(cast(str | bytes | int | float, value)))
    except (TypeError, ValueError):
        return 0
