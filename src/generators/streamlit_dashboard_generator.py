from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional, Sequence

from src.contracts.files import FileStatRequest, ListDirectoryRequest, ReadTextRequest
from src.contracts.lock import LockGetRequest
from src.contracts.report_store import ReportMetadataListRequest
from src.contracts.run_context import RunContext
from src.contracts.state import StateProcessedListRequest, StatePublishedListRequest
from src.contracts.streamlit_dashboard import (
    DirectoryCountRow,
    DirectoryCountsRequest,
    DirectoryCountsResponse,
    JsonPayloadReadRequest,
    JsonPayloadReadResponse,
    LedgerEntriesLoadRequest,
    LedgerEntriesLoadResponse,
    LockSnapshot,
    LockSnapshotLoadRequest,
    LogEventLoadRequest,
    LogEventLoadResponse,
    LogFileDiscoveryRequest,
    LogFileDiscoveryResponse,
    LogFileRecord,
    ReportRowsLoadRequest,
    ReportRowsLoadResponse,
    StateRowsLoadRequest,
    StateRowsLoadResponse,
    StorageHealthRequest,
    StorageHealthResponse,
    StorageHealthRow,
    ValidationArtifactSummaryRequest,
    ValidationArtifactSummaryResponse,
    ValidationArtifactSummaryRow,
)
from src.services import file_service, lock_service, report_store_service, state_service
from src.utils.errors import AppError
from src.utils.gui_utils import (
    extract_log_date_from_filename,
    parse_structured_log_line,
    row_dicts,
    safe_json_loads,
    status_chip_level,
)
from src.utils.logging import child_context, log_event, new_run_context

logger = logging.getLogger("market_lense.streamlit_dashboard_generator")


def discover_log_files(
    request: LogFileDiscoveryRequest,
    ctx: Optional[RunContext] = None,
) -> LogFileDiscoveryResponse:
    ctx = ctx or new_run_context(task_id="streamlit:discover_log_files")
    limit = _normalized_limit(request.limit, default=100, maximum=1000)
    logger.info(log_event(
        ctx,
        role="generator",
        event="streamlit_discover_logs_start",
        module=logger.name,
        fields={
            "log_dir": request.log_dir,
            "file_prefix": request.file_prefix,
            "limit": limit,
        },
    ))
    try:
        response = file_service.list_directory(
            ListDirectoryRequest(
                schema_version="1.0",
                root_dir=request.log_dir.strip(),
                glob_pattern=f"{request.file_prefix.strip()}_*.log",
                recursive=False,
                include_files=True,
                include_dirs=False,
                limit=limit,
            ),
            child_context(ctx, task_id="streamlit:list_logs"),
        )
    except AppError as exc:
        logger.info(log_event(
            ctx,
            role="generator",
            event="streamlit_discover_logs_error",
            module=logger.name,
            fields={"code": exc.code, "message": exc.message},
        ))
        return LogFileDiscoveryResponse(schema_version="1.0", records=[])

    rows = row_dicts(response.entries, include_object_attrs=True)
    rows.sort(key=lambda row: float(row.get("mtime_utc") or 0.0), reverse=True)
    records = [
        LogFileRecord(
            schema_version="1.0",
            path=str(row.get("path") or ""),
            name=str(row.get("name") or ""),
            mtime_utc=(
                float(raw_mtime)
                if (raw_mtime := row.get("mtime_utc")) is not None
                else None
            ),
            size_bytes=(
                int(raw_size)
                if (raw_size := row.get("size_bytes")) is not None
                else None
            ),
        )
        for row in rows
        if str(row.get("path") or "").strip()
    ]
    logger.info(log_event(
        ctx,
        role="generator",
        event="streamlit_discover_logs_complete",
        module=logger.name,
        fields={"count": len(records)},
    ))
    return LogFileDiscoveryResponse(schema_version="1.0", records=records)


def load_log_events(
    request: LogEventLoadRequest,
    ctx: Optional[RunContext] = None,
) -> LogEventLoadResponse:
    ctx = ctx or new_run_context(task_id="streamlit:load_log_events")
    max_lines = _normalized_limit(request.max_lines_per_file, default=5000, maximum=20000)
    log_paths = [str(path).strip() for path in request.log_paths if str(path).strip()]
    logger.info(log_event(
        ctx,
        role="generator",
        event="streamlit_load_log_events_start",
        module=logger.name,
        fields={"path_count": len(log_paths), "max_lines_per_file": max_lines},
    ))
    events: list[dict[str, Any]] = []
    for path in log_paths:
        try:
            text = file_service.read_text(
                ReadTextRequest(schema_version="1.0", path=path),
                child_context(ctx, task_id="streamlit:read_log"),
            ).content
        except AppError as exc:
            logger.info(log_event(
                ctx,
                role="generator",
                event="streamlit_load_log_events_read_error",
                module=logger.name,
                fields={"path": path, "code": exc.code, "message": exc.message},
            ))
            continue
        log_date = extract_log_date_from_filename(path)
        for line in text.splitlines()[-max_lines:]:
            event = parse_structured_log_line(line, log_date=log_date)
            if not event:
                continue
            event["log_path"] = path
            events.append(event)
    events.sort(key=lambda row: str(row.get("timestamp_utc") or row.get("timestamp_hms") or ""))
    logger.info(log_event(
        ctx,
        role="generator",
        event="streamlit_load_log_events_complete",
        module=logger.name,
        fields={"event_count": len(events)},
    ))
    return LogEventLoadResponse(schema_version="1.0", events=events)


def read_json_payload(
    request: JsonPayloadReadRequest,
    ctx: Optional[RunContext] = None,
) -> JsonPayloadReadResponse:
    ctx = ctx or new_run_context(task_id="streamlit:read_json")
    path = request.path.strip()
    logger.info(log_event(
        ctx,
        role="generator",
        event="streamlit_read_json_start",
        module=logger.name,
        fields={"path": path},
    ))
    try:
        payload_text = file_service.read_text(
            ReadTextRequest(schema_version="1.0", path=path),
            child_context(ctx, task_id="streamlit:read_json_file"),
        ).content
    except AppError as exc:
        logger.info(log_event(
            ctx,
            role="generator",
            event="streamlit_read_json_error",
            module=logger.name,
            fields={"path": path, "code": exc.code, "message": exc.message},
        ))
        return JsonPayloadReadResponse(schema_version="1.0", path=path, payload=None)
    payload = safe_json_loads(payload_text)
    logger.info(log_event(
        ctx,
        role="generator",
        event="streamlit_read_json_complete",
        module=logger.name,
        fields={"path": path, "payload_type": type(payload).__name__ if payload is not None else "none"},
    ))
    return JsonPayloadReadResponse(schema_version="1.0", path=path, payload=payload)


def collect_storage_health(
    request: StorageHealthRequest,
    ctx: Optional[RunContext] = None,
) -> StorageHealthResponse:
    ctx = ctx or new_run_context(task_id="streamlit:storage_health")
    logger.info(log_event(
        ctx,
        role="generator",
        event="streamlit_storage_health_start",
        module=logger.name,
        fields={"target_count": len(request.targets)},
    ))
    rows: list[StorageHealthRow] = []
    for target in request.targets:
        path = target.path.strip()
        task_id = f"streamlit:stat:{target.name}"
        try:
            stat = file_service.file_stat(
                FileStatRequest(schema_version="1.0", path=path),
                child_context(ctx, task_id=task_id),
            )
            rows.append(StorageHealthRow(
                schema_version="1.0",
                name=target.name,
                path=path,
                exists=bool(stat.exists),
                size_bytes=stat.size_bytes,
                modified_utc=_as_utc(stat.mtime_utc),
                error="",
            ))
        except AppError as exc:
            rows.append(StorageHealthRow(
                schema_version="1.0",
                name=target.name,
                path=path,
                exists=False,
                size_bytes=None,
                modified_utc="",
                error=exc.message,
            ))
    logger.info(log_event(
        ctx,
        role="generator",
        event="streamlit_storage_health_complete",
        module=logger.name,
        fields={"row_count": len(rows)},
    ))
    return StorageHealthResponse(schema_version="1.0", rows=rows)


def summarize_validation_artifacts(
    request: ValidationArtifactSummaryRequest,
    ctx: Optional[RunContext] = None,
) -> ValidationArtifactSummaryResponse:
    ctx = ctx or new_run_context(task_id="streamlit:validation_summary")
    limit = _normalized_limit(request.limit, default=200, maximum=2000)
    logger.info(log_event(
        ctx,
        role="generator",
        event="streamlit_validation_summary_start",
        module=logger.name,
        fields={"output_dir": request.output_dir, "limit": limit},
    ))
    try:
        response = file_service.list_directory(
            ListDirectoryRequest(
                schema_version="1.0",
                root_dir=request.output_dir,
                glob_pattern="validation*.json",
                recursive=True,
                include_files=True,
                include_dirs=False,
                limit=max(limit * 2, 500),
            ),
            child_context(ctx, task_id="streamlit:list_validation"),
        )
    except AppError as exc:
        logger.info(log_event(
            ctx,
            role="generator",
            event="streamlit_validation_summary_error",
            module=logger.name,
            fields={"code": exc.code, "message": exc.message},
        ))
        return ValidationArtifactSummaryResponse(schema_version="1.0", rows=[])

    files = row_dicts(response.entries, include_object_attrs=True)
    files.sort(key=lambda row: float(row.get("mtime_utc") or 0.0), reverse=True)
    rows: list[ValidationArtifactSummaryRow] = []
    for file_row in files[:limit]:
        path = str(file_row.get("path") or "")
        payload = read_json_payload(
            JsonPayloadReadRequest(schema_version="1.0", path=path),
            child_context(ctx, task_id="streamlit:validation_payload"),
        ).payload
        status = str(payload.get("status") if isinstance(payload, dict) else "")
        severity = str(payload.get("severity") if isinstance(payload, dict) else "")
        rows.append(ValidationArtifactSummaryRow(
            schema_version="1.0",
            path=path,
            status=status,
            severity=severity,
            chip_level=status_chip_level(severity or status),
            modified_utc=_as_utc(file_row.get("mtime_utc")),
        ))

    logger.info(log_event(
        ctx,
        role="generator",
        event="streamlit_validation_summary_complete",
        module=logger.name,
        fields={"row_count": len(rows)},
    ))
    return ValidationArtifactSummaryResponse(schema_version="1.0", rows=rows)


def load_report_rows(
    request: ReportRowsLoadRequest,
    ctx: Optional[RunContext] = None,
) -> ReportRowsLoadResponse:
    ctx = ctx or new_run_context(task_id="streamlit:load_report_rows")
    logger.info(log_event(
        ctx,
        role="generator",
        event="streamlit_load_report_rows_start",
        module=logger.name,
        fields={"reports_db": request.reports_db},
    ))
    reports_resp = report_store_service.list_metadata(
        ReportMetadataListRequest(schema_version="1.1", db_path=request.reports_db),
        child_context(ctx, task_id="streamlit:list_reports"),
    )
    rows = row_dicts(reports_resp.records, include_object_attrs=True)
    rows.sort(key=lambda row: int(row.get("updated_at") or 0), reverse=True)
    logger.info(log_event(
        ctx,
        role="generator",
        event="streamlit_load_report_rows_complete",
        module=logger.name,
        fields={"row_count": len(rows)},
    ))
    return ReportRowsLoadResponse(schema_version="1.0", rows=rows)


def load_state_rows(
    request: StateRowsLoadRequest,
    ctx: Optional[RunContext] = None,
) -> StateRowsLoadResponse:
    ctx = ctx or new_run_context(task_id=f"streamlit:load_state_rows:{request.kind}")
    kind = request.kind.strip().lower()
    limit = _normalized_limit(request.limit, default=1000, maximum=20000)
    logger.info(log_event(
        ctx,
        role="generator",
        event="streamlit_load_state_rows_start",
        module=logger.name,
        fields={"state_db": request.state_db, "kind": kind, "limit": limit},
    ))
    response_rows: Sequence[object]
    if kind == "processed":
        response_rows = state_service.list_processed(
            StateProcessedListRequest(schema_version="1.0", state_db=request.state_db, limit=limit),
            child_context(ctx, task_id="streamlit:list_processed"),
        ).rows
    elif kind == "published":
        response_rows = state_service.list_published(
            StatePublishedListRequest(schema_version="1.0", state_db=request.state_db, limit=limit),
            child_context(ctx, task_id="streamlit:list_published"),
        ).rows
    else:
        raise AppError(
            code="invalid_state_kind",
            message=f"Unsupported state row kind: {request.kind}",
            retryable=False,
            context={"kind": request.kind},
        )
    rows = row_dicts(response_rows, include_object_attrs=True)
    logger.info(log_event(
        ctx,
        role="generator",
        event="streamlit_load_state_rows_complete",
        module=logger.name,
        fields={"kind": kind, "row_count": len(rows)},
    ))
    return StateRowsLoadResponse(schema_version="1.0", rows=rows)


def load_lock_snapshot(
    request: LockSnapshotLoadRequest,
    ctx: Optional[RunContext] = None,
) -> LockSnapshot:
    ctx = ctx or new_run_context(task_id="streamlit:load_lock_snapshot")
    lock_path = request.lock_path.strip()
    logger.info(log_event(
        ctx,
        role="generator",
        event="streamlit_load_lock_start",
        module=logger.name,
        fields={"lock_path": lock_path},
    ))
    try:
        lock = lock_service.get_lock(
            LockGetRequest(schema_version="1.0", lock_path=lock_path),
            child_context(ctx, task_id="streamlit:get_lock"),
        )
    except AppError as exc:
        logger.info(log_event(
            ctx,
            role="generator",
            event="streamlit_load_lock_error",
            module=logger.name,
            fields={"code": exc.code, "message": exc.message},
        ))
        return LockSnapshot(schema_version="1.0", found=False, error=exc.message)

    snapshot = LockSnapshot(
        schema_version="1.0",
        found=bool(lock.found),
        owner_id=lock.lock.owner_id if lock.lock else "",
        pid=lock.lock.pid if lock.lock else None,
        error="",
    )
    logger.info(log_event(
        ctx,
        role="generator",
        event="streamlit_load_lock_complete",
        module=logger.name,
        fields={"found": snapshot.found, "owner_id": snapshot.owner_id, "pid": snapshot.pid},
    ))
    return snapshot


def load_ledger_entries(
    request: LedgerEntriesLoadRequest,
    ctx: Optional[RunContext] = None,
) -> LedgerEntriesLoadResponse:
    ctx = ctx or new_run_context(task_id="streamlit:load_ledger_entries")
    limit = _normalized_limit(request.limit, default=2000, maximum=20000)
    ledger_path = request.ledger_path.strip()
    logger.info(log_event(
        ctx,
        role="generator",
        event="streamlit_load_ledger_start",
        module=logger.name,
        fields={"ledger_path": ledger_path, "limit": limit},
    ))
    try:
        content = file_service.read_text(
            ReadTextRequest(schema_version="1.0", path=ledger_path),
            child_context(ctx, task_id="streamlit:read_ledger"),
        ).content
    except AppError as exc:
        logger.info(log_event(
            ctx,
            role="generator",
            event="streamlit_load_ledger_error",
            module=logger.name,
            fields={"code": exc.code, "message": exc.message},
        ))
        return LedgerEntriesLoadResponse(schema_version="1.0", entries=[])

    rows: list[dict[str, Any]] = []
    for line in content.splitlines():
        if not line.strip():
            continue
        payload = safe_json_loads(line.strip())
        if isinstance(payload, dict):
            rows.append(payload)
    rows = rows[-limit:]
    logger.info(log_event(
        ctx,
        role="generator",
        event="streamlit_load_ledger_complete",
        module=logger.name,
        fields={"entry_count": len(rows)},
    ))
    return LedgerEntriesLoadResponse(schema_version="1.0", entries=rows)


def collect_directory_counts(
    request: DirectoryCountsRequest,
    ctx: Optional[RunContext] = None,
) -> DirectoryCountsResponse:
    ctx = ctx or new_run_context(task_id="streamlit:collect_directory_counts")
    limit = _normalized_limit(request.limit, default=5000, maximum=50000)
    logger.info(log_event(
        ctx,
        role="generator",
        event="streamlit_collect_directory_counts_start",
        module=logger.name,
        fields={"check_count": len(request.checks), "limit": limit},
    ))
    rows: list[DirectoryCountRow] = []
    for check in request.checks:
        try:
            response = file_service.list_directory(
                ListDirectoryRequest(
                    schema_version="1.0",
                    root_dir=check.root_dir,
                    glob_pattern=check.glob_pattern,
                    recursive=check.recursive,
                    include_files=not check.include_dirs,
                    include_dirs=check.include_dirs,
                    limit=limit,
                ),
                child_context(ctx, task_id=f"streamlit:dir_count:{check.name}"),
            )
            rows.append(DirectoryCountRow(
                schema_version="1.0",
                name=check.name,
                root=check.root_dir,
                count=len(response.entries),
                error="",
            ))
        except AppError as exc:
            rows.append(DirectoryCountRow(
                schema_version="1.0",
                name=check.name,
                root=check.root_dir,
                count=0,
                error=exc.message,
            ))
    logger.info(log_event(
        ctx,
        role="generator",
        event="streamlit_collect_directory_counts_complete",
        module=logger.name,
        fields={"row_count": len(rows)},
    ))
    return DirectoryCountsResponse(schema_version="1.0", rows=rows)

def _normalized_limit(value: int, *, default: int, maximum: int) -> int:
    if value <= 0:
        return default
    return min(value, maximum)


def _as_utc(ts: int | float | None) -> str:
    if ts is None:
        return ""
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    except Exception:
        return ""
