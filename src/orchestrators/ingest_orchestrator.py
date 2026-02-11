from __future__ import annotations

import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from src.contracts.categories import UncategorizedTagsFlushRequest
from src.services.pdf_service import check_pdf_eof
from src.contracts.drive import (
    DriveFileMetadataRequest,
    DriveListRequest,
    DriveFile,
)
from src.contracts.ingest import IngestOutcome, IngestSettings
from src.contracts.lock import LockAcquireRequest, LockReleaseRequest
from src.contracts.report_store import ReportMetadataDbAccessRequest, ReportMetadataGetRequest
from src.contracts.run_context import RunContext
from src.generators.report_generator import generate_report
from src.orchestrators.ingest_file_orchestrator import (
    FileProcessResult as _FileProcessResult,
    IngestFileDependencies,
    run_ingest_file,
)
from src.orchestrators.report_pipeline_orchestrator import (
    run_report_pipeline as run_report_pipeline_orchestrator,
)
from src.services.drive_service import download_pdf_to_path, get_file_metadata, list_pdfs
from src.services.file_service import (
    delete_file,
    file_stat,
    read_text,
    write_bytes,
)
from src.contracts.files import (
    FileStatRequest,
    ReadTextRequest,
    WriteBytesRequest,
)
from src.services.lock_service import acquire_lock, release_lock
from src.services.report_store_service import check_report_db_access, get_metadata as get_report_metadata
from src.services.state_service import already_processed as state_already_processed
from src.services.state_service import check_state_db_access, get_ingest_cursor, set_ingest_cursor
from src.services.state_service import record as state_record
from src.contracts.state import (
    StateCheckRequest,
    StateDbAccessRequest,
    StateIngestCursorGetRequest,
    StateIngestCursorSetRequest,
)
from src.services.category_mapping_service import flush_uncategorized_tags
from src.utils.logging import child_context, log_event, new_run_context
from src.utils.errors import AppError
from src.utils.path_utils import safe_pdf_name

logger = logging.getLogger("market_lense.ingest_orchestrator")
DB_ACCESS_TIMEOUT_SECONDS = 0.0
MD5_SIDECAR_SUFFIX = ".md5.json"
MD5_SIDECAR_SCHEMA = "1.0"
EOF_RETRY_LIMIT = 1


def _should_skip(file: DriveFile, md5: Optional[str], state_db: str, ctx: RunContext) -> bool:
    if not md5:
        return False
    req = StateCheckRequest(
        schema_version="1.0",
        state_db=state_db,
        file_id=file.file_id,
        md5=md5,
    )
    return state_already_processed(req, ctx)


def _cache_pdf_path(settings: IngestSettings, file: DriveFile) -> str:
    cache_name = safe_pdf_name(file.file_id)
    return str(Path(settings.cache_dir) / cache_name)


def _md5_sidecar_path(cache_path: str) -> str:
    return f"{cache_path}{MD5_SIDECAR_SUFFIX}"


def _normalize_mtime(value: Optional[float]) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _load_md5_sidecar(path: str, file_id: str, ctx: RunContext) -> Optional[dict]:
    try:
        resp = read_text(ReadTextRequest(schema_version="1.0", path=path), ctx)
    except AppError as exc:
        if exc.code == "file_not_found":
            logger.info(log_event(
                ctx,
                role="orchestrator",
                event="md5_sidecar_missing",
                module=logger.name,
                fields={"file_id": file_id, "path": path},
            ))
            return None
        logger.info(log_event(
            ctx,
            role="orchestrator",
            event="md5_sidecar_read_failed",
            module=logger.name,
            fields={"file_id": file_id, "path": path, "error": exc.message},
        ))
        return None
    try:
        payload = json.loads(resp.content)
    except json.JSONDecodeError as exc:
        logger.info(log_event(
            ctx,
            role="orchestrator",
            event="md5_sidecar_invalid_json",
            module=logger.name,
            fields={"file_id": file_id, "path": path, "error": str(exc)},
        ))
        return None
    if not isinstance(payload, dict):
        logger.info(log_event(
            ctx,
            role="orchestrator",
            event="md5_sidecar_invalid_payload",
            module=logger.name,
            fields={"file_id": file_id, "path": path},
        ))
        return None
    logger.info(log_event(
        ctx,
        role="orchestrator",
        event="md5_sidecar_loaded",
        module=logger.name,
        fields={"file_id": file_id, "path": path},
    ))
    return payload


def _sidecar_md5_for_stat(payload: dict, size_bytes: Optional[int], mtime_utc: Optional[float]) -> Optional[str]:
    if not payload:
        return None
    md5 = str(payload.get("md5") or "").strip()
    if not md5:
        return None
    try:
        sidecar_size = int(payload.get("size_bytes"))
    except (TypeError, ValueError):
        return None
    sidecar_mtime = _normalize_mtime(payload.get("mtime_utc"))
    stat_mtime = _normalize_mtime(mtime_utc)
    if size_bytes is None or sidecar_size != size_bytes:
        return None
    if sidecar_mtime is None or stat_mtime is None or sidecar_mtime != stat_mtime:
        return None
    return md5


def _ensure_file_name(file: DriveFile, settings: IngestSettings, ctx: RunContext) -> DriveFile:
    if file.name:
        return file
    try:
        meta = get_file_metadata(
            DriveFileMetadataRequest(
                schema_version="1.0",
                file_id=file.file_id,
                service_account_path=settings.google_sa_path,
            ),
            ctx,
        ).file
        return DriveFile(
            schema_version="1.0",
            file_id=file.file_id,
            name=meta.name or file.file_id,
            modified_time=meta.modified_time or file.modified_time,
            md5_checksum=file.md5_checksum or meta.md5_checksum,
        )
    except AppError as exc:
        logger.info(log_event(
            ctx,
            role="orchestrator",
            event="drive_file_metadata_failed",
            module=logger.name,
            fields={"file_id": file.file_id, "error": exc.message},
        ))
        return DriveFile(
            schema_version="1.0",
            file_id=file.file_id,
            name=file.file_id,
            modified_time=file.modified_time,
            md5_checksum=file.md5_checksum,
        )


def _write_md5_sidecar(
    path: str,
    file: DriveFile,
    md5: Optional[str],
    size_bytes: Optional[int],
    mtime_utc: Optional[float],
    ctx: RunContext,
) -> None:
    if not md5 or size_bytes is None or mtime_utc is None:
        return
    payload = {
        "schema_version": MD5_SIDECAR_SCHEMA,
        "file_id": file.file_id,
        "name": file.name or "",
        "md5": md5,
        "size_bytes": int(size_bytes),
        "mtime_utc": _normalize_mtime(mtime_utc),
    }
    content = json.dumps(payload, ensure_ascii=True)
    write_bytes(
        WriteBytesRequest(schema_version="1.0", path=path, content=content.encode("utf-8")),
        ctx,
    )
    logger.info(log_event(
        ctx,
        role="orchestrator",
        event="md5_sidecar_written",
        module=logger.name,
        fields={"file_id": file.file_id, "path": path, "size_bytes": size_bytes},
    ))


def _existing_report_html(
    file: DriveFile,
    md5: str,
    settings: IngestSettings,
    ctx: RunContext,
) -> Optional[str]:
    if not md5:
        return None
    try:
        metadata = get_report_metadata(
            ReportMetadataGetRequest(
                schema_version="1.0",
                db_path=settings.reports_db,
                file_id=file.file_id,
            ),
            ctx,
        )
    except Exception as exc:
        logger.info(log_event(
            ctx,
            role="orchestrator",
            event="report_metadata_lookup_failed",
            module=logger.name,
            fields={"file_id": file.file_id, "error": str(exc)},
        ))
        return None
    if not metadata or not metadata.md5 or metadata.md5 != md5:
        return None
    html_path = (metadata.html_path or "").strip()
    if not html_path:
        return None
    html_stat = file_stat(FileStatRequest(schema_version="1.0", path=html_path), ctx)
    if not html_stat.exists:
        logger.info(log_event(
            ctx,
            role="orchestrator",
            event="report_html_missing",
            module=logger.name,
            fields={"file_id": file.file_id, "md5": md5, "html_path": html_path},
        ))
        return None
    logger.info(log_event(
        ctx,
        role="orchestrator",
        event="report_html_cache_hit",
        module=logger.name,
        fields={"file_id": file.file_id, "md5": md5, "html_path": html_path},
    ))
    return html_path


def _run_step_with_retry(step_name: str, ctx: RunContext, func, retries: int = 2):
    attempt = 0
    while True:
        try:
            return func()
        except AppError as exc:
            if not exc.retryable or attempt >= retries:
                raise
            logger.info(log_event(
                ctx,
                role="orchestrator",
                event="step_retry",
                module=logger.name,
                fields={"step": step_name, "attempt": attempt + 1, "code": exc.code},
            ))
            time.sleep(1 + attempt)
            attempt += 1


def _process_file(
    file: DriveFile,
    index: int,
    settings: IngestSettings,
    root_ctx: RunContext,
) -> _FileProcessResult:
    dependencies = IngestFileDependencies(
        should_skip=_should_skip,
        cache_pdf_path=_cache_pdf_path,
        md5_sidecar_path=_md5_sidecar_path,
        load_md5_sidecar=_load_md5_sidecar,
        sidecar_md5_for_stat=_sidecar_md5_for_stat,
        ensure_file_name=_ensure_file_name,
        write_md5_sidecar=_write_md5_sidecar,
        existing_report_html=_existing_report_html,
        run_step_with_retry=_run_step_with_retry,
        file_stat=file_stat,
        download_pdf_to_path=download_pdf_to_path,
        check_pdf_eof=check_pdf_eof,
        delete_file=delete_file,
        run_report_pipeline=lambda current_file, local_pdf_path, current_settings, current_md5, current_ctx: (
            run_report_pipeline_orchestrator(
                current_file,
                local_pdf_path,
                current_settings,
                current_md5,
                current_ctx,
                retries=0,
                generate_report_fn=generate_report,
            )
        ),
        state_record=state_record,
        eof_retry_limit=EOF_RETRY_LIMIT,
    )
    return run_ingest_file(
        file=file,
        index=index,
        settings=settings,
        root_ctx=root_ctx,
        dependencies=dependencies,
        logger_name=logger.name,
    )


def run_ingest(
    settings: IngestSettings,
    *,
    folder_id: Optional[str] = None,
    limit: Optional[int] = None,
    ctx: Optional[RunContext] = None,
) -> List[IngestOutcome]:
    root_ctx = ctx or new_run_context()
    lock_ctx = child_context(root_ctx, task_id="ingest_lock")
    lock_info = None
    outcomes: List[IngestOutcome] = []
    processed = 0
    try:
        lock_resp = acquire_lock(
            LockAcquireRequest(
                schema_version="1.0",
                lock_path=settings.ingest_lock_path,
                owner_id=f"ingest:{root_ctx.run_id}",
                pid=os.getpid(),
                ttl_seconds=settings.ingest_lock_ttl_seconds,
            ),
            lock_ctx,
        )
        if not lock_resp.acquired:
            conflict = lock_resp.conflict
            logger.info(log_event(
                lock_ctx,
                role="orchestrator",
                event="ingest_lock_conflict",
                module=logger.name,
                fields={
                    "lock_path": settings.ingest_lock_path,
                    "existing_owner": conflict.owner_id if conflict else None,
                    "existing_pid": conflict.pid if conflict else None,
                },
            ))
            raise AppError(
                code="ingest_locked",
                message="Another ingest run is already active",
                retryable=False,
                context={
                    "lock_path": settings.ingest_lock_path,
                    "owner_id": conflict.owner_id if conflict else None,
                    "pid": conflict.pid if conflict else None,
                },
            )
        lock_info = lock_resp.lock
        logger.info(log_event(
            lock_ctx,
            role="orchestrator",
            event="ingest_lock_acquired",
            module=logger.name,
            fields={
                "lock_path": settings.ingest_lock_path,
                "owner_id": lock_info.owner_id if lock_info else "",
                "pid": lock_info.pid if lock_info else None,
            },
        ))

        db_ctx = child_context(root_ctx, task_id="ingest_db_access")
        logger.info(log_event(
            db_ctx,
            role="orchestrator",
            event="ingest_db_access_start",
            module=logger.name,
            fields={"state_db": settings.state_db, "reports_db": settings.reports_db},
        ))
        state_access = check_state_db_access(
            StateDbAccessRequest(
                schema_version="1.0",
                state_db=settings.state_db,
                timeout_seconds=DB_ACCESS_TIMEOUT_SECONDS,
            ),
            db_ctx,
        )
        report_access = check_report_db_access(
            ReportMetadataDbAccessRequest(
                schema_version="1.0",
                db_path=settings.reports_db,
                timeout_seconds=DB_ACCESS_TIMEOUT_SECONDS,
            ),
            db_ctx,
        )
        if not state_access.accessible or not report_access.accessible:
            locked = []
            if state_access.locked:
                locked.append(f"state_db={settings.state_db}")
            if report_access.locked:
                locked.append(f"reports_db={settings.reports_db}")
            reason = ", ".join(locked) if locked else "unknown"
            logger.info(log_event(
                db_ctx,
                role="orchestrator",
                event="ingest_db_access_blocked",
                module=logger.name,
                fields={
                    "state_db_accessible": state_access.accessible,
                    "state_db_locked": state_access.locked,
                    "reports_db_accessible": report_access.accessible,
                    "reports_db_locked": report_access.locked,
                    "reason": reason,
                },
            ))
            raise AppError(
                code="db_locked",
                message=f"Database locked: {reason}",
                retryable=False,
                context={
                    "state_db": settings.state_db,
                    "reports_db": settings.reports_db,
                    "state_db_locked": state_access.locked,
                    "reports_db_locked": report_access.locked,
                },
            )
        logger.info(log_event(
            db_ctx,
            role="orchestrator",
            event="ingest_db_access_complete",
            module=logger.name,
            fields={
                "state_db": settings.state_db,
                "reports_db": settings.reports_db,
            },
        ))

        logger.info(log_event(
            root_ctx,
            role="orchestrator",
            event="ingest_start",
            module=logger.name,
            fields={"folder_id": folder_id or settings.gdrive_folder_id, "limit": limit},
        ))

        modified_after = None
        if limit is None:
            cursor_resp = get_ingest_cursor(
                StateIngestCursorGetRequest(schema_version="1.0", state_db=settings.state_db),
                root_ctx,
            )
            modified_after = cursor_resp.last_successful_ingest_utc
            if modified_after:
                logger.info(log_event(
                    root_ctx,
                    role="orchestrator",
                    event="ingest_modified_after_loaded",
                    module=logger.name,
                    fields={"modified_after": modified_after},
                ))
        else:
            logger.info(log_event(
                root_ctx,
                role="orchestrator",
                event="ingest_modified_after_ignored",
                module=logger.name,
                fields={"reason": "limit_override", "limit": limit},
            ))

        max_n = limit if limit is not None else settings.batch_limit
        page_size = min(max_n, 1000) if limit is not None else None
        order_by = "modifiedTime desc" if limit is not None else None
        list_req = DriveListRequest(
            schema_version="1.0",
            folder_id=folder_id or settings.gdrive_folder_id,
            service_account_path=settings.google_sa_path,
            page_size=page_size,
            order_by=order_by,
            modified_after=modified_after,
            list_mode=settings.drive_list_mode,
            supports_all_drives=settings.drive_supports_all_drives,
            include_items_from_all_drives=settings.drive_include_items_from_all_drives,
            drive_id=settings.drive_id,
        )

        files_to_process: list[DriveFile] = []
        for file in list_pdfs(list_req, root_ctx):
            drive_md5 = file.md5_checksum.strip() if file.md5_checksum else None
            if drive_md5 and _should_skip(file, drive_md5, settings.state_db, root_ctx):
                logger.info(log_event(
                    root_ctx,
                    role="orchestrator",
                    event="drive_list_skip_processed",
                    module=logger.name,
                    fields={"file_id": file.file_id, "md5": drive_md5},
                ))
                continue
            files_to_process.append(file)
            if len(files_to_process) >= max_n:
                break
        logger.info(log_event(
            root_ctx,
            role="orchestrator",
            event="drive_list_materialized",
            module=logger.name,
            fields={"count": len(files_to_process), "limit": max_n},
        ))

        worker_limit = settings.ingest_worker_limit
        try:
            worker_limit = int(worker_limit)
        except (TypeError, ValueError):
            worker_limit = 1
        if worker_limit < 1:
            worker_limit = 1
        logger.info(log_event(
            root_ctx,
            role="orchestrator",
            event="ingest_worker_config",
            module=logger.name,
            fields={"worker_limit": worker_limit, "file_count": len(files_to_process)},
        ))

        results: list[_FileProcessResult] = []
        if worker_limit <= 1 or len(files_to_process) <= 1:
            for idx, file in enumerate(files_to_process):
                results.append(_process_file(file, idx, settings, root_ctx))
        else:
            with ThreadPoolExecutor(max_workers=worker_limit) as executor:
                futures = {
                    executor.submit(_process_file, file, idx, settings, root_ctx): (idx, file)
                    for idx, file in enumerate(files_to_process)
                }
                for future in as_completed(futures):
                    idx, file = futures[future]
                    try:
                        result = future.result()
                    except Exception as exc:  # pragma: no cover - defensive fallback
                        file_ctx = child_context(root_ctx, task_id=file.file_id)
                        logger.info(log_event(
                            file_ctx,
                            role="orchestrator",
                            event="file_processing_error",
                            module=logger.name,
                            fields={
                                "file_id": file.file_id,
                                "error": str(exc),
                                "local_path": _cache_pdf_path(settings, file),
                                "md5": file.md5_checksum or "",
                            },
                        ))
                        result = _FileProcessResult(
                            index=idx,
                            outcome=IngestOutcome(
                                schema_version="1.0",
                                file_id=file.file_id,
                                name=file.name or file.file_id,
                                md5=None,
                                html_path=None,
                                status="error",
                                error=str(exc),
                            ),
                            processed=0,
                            had_error=True,
                        )
                    results.append(result)

        results.sort(key=lambda r: r.index)
        outcomes.extend([result.outcome for result in results])
        processed = sum(result.processed for result in results)
        had_errors = any(result.had_error for result in results)

        logger.info(log_event(
            root_ctx,
            role="orchestrator",
            event="ingest_complete",
            module=logger.name,
            fields={"processed": processed},
        ))
        if not had_errors and processed > 0 and limit is None:
            try:
                now_utc = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
                set_ingest_cursor(
                    StateIngestCursorSetRequest(
                        schema_version="1.0",
                        state_db=settings.state_db,
                        last_successful_ingest_utc=now_utc,
                    ),
                    root_ctx,
                )
                logger.info(log_event(
                    root_ctx,
                    role="orchestrator",
                    event="ingest_cursor_updated",
                    module=logger.name,
                    fields={"last_successful_ingest_utc": now_utc},
                ))
            except Exception as exc:
                logger.info(log_event(
                    root_ctx,
                    role="orchestrator",
                    event="ingest_cursor_update_failed",
                    module=logger.name,
                    fields={"error": str(exc)},
                ))
        else:
            logger.info(log_event(
                root_ctx,
                role="orchestrator",
                event="ingest_cursor_skipped",
                module=logger.name,
                fields={
                    "reason": "errors_detected" if had_errors else "no_processed_or_limit_override",
                    "processed": processed,
                    "limit": limit,
                },
            ))
        return outcomes
    finally:
        try:
            flush_uncategorized_tags(
                UncategorizedTagsFlushRequest(
                    schema_version="1.0",
                    path=settings.category_mapping_path,
                ),
                root_ctx,
            )
        except Exception as exc:
            logger.info(log_event(
                root_ctx,
                role="orchestrator",
                event="ingest_uncategorized_flush_failed",
                module=logger.name,
                fields={"path": settings.category_mapping_path, "error": str(exc)},
            ))
        if lock_info:
            try:
                release_lock(
                    LockReleaseRequest(
                        schema_version="1.0",
                        lock_path=lock_info.lock_path,
                        owner_id=lock_info.owner_id,
                        pid=lock_info.pid,
                    ),
                    lock_ctx,
                )
                logger.info(log_event(
                    lock_ctx,
                    role="orchestrator",
                    event="ingest_lock_released",
                    module=logger.name,
                    fields={"lock_path": lock_info.lock_path},
                ))
            except Exception as exc:
                logger.info(log_event(
                    lock_ctx,
                    role="orchestrator",
                    event="ingest_lock_release_failed",
                    module=logger.name,
                    fields={"lock_path": settings.ingest_lock_path, "error": str(exc)},
                ))
