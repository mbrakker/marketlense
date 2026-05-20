from __future__ import annotations

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, List, Optional

from src.contracts.categories import UncategorizedTagsFlushRequest
from src.services.pdf_service import check_pdf_eof
from src.contracts.drive import (
    DriveFileMetadataRequest,
    DriveListRequest,
    DriveFile,
)
from src.contracts.ingest import IngestOutcome, IngestSettings
from src.contracts.lock import LockAcquireRequest, LockReleaseRequest
from src.contracts.report_store import (
    ReportMetadataDbAccessRequest,
    ReportMetadataGetRequest,
)
from src.contracts.run_context import RunContext
from src.orchestrators.ingest_file_orchestrator import (
    FileProcessResult as _FileProcessResult,
    IngestFileDependencies,
    run_ingest_file,
)
from src.orchestrators.report_generation_orchestrator import (
    run_report_generation as generate_report,
)
from src.orchestrators.retry_orchestrator import run_step_with_default_policy
from src.orchestrators.report_pipeline_orchestrator import (
    run_report_pipeline as run_report_pipeline_orchestrator,
)
from src.services.drive_service import (
    download_pdf_to_path,
    get_file_metadata,
    list_pdfs,
)
from src.services.file_cache_service import (
    resolve_md5_sidecar,
    write_md5_sidecar,
)
from src.services.file_service import delete_file, file_stat
from src.contracts.files import FileStatRequest
from src.services.lock_service import acquire_lock, release_lock
from src.services.report_store_service import (
    check_report_db_access,
    get_metadata as get_report_metadata,
)
from src.services.state_service import (
    already_processed_batch as state_already_processed_batch,
)
from src.services.state_service import already_processed as state_already_processed
from src.services.state_service import get as state_get
from src.services.state_service import (
    check_state_db_access,
    get_ingest_cursor,
    set_ingest_cursor,
)
from src.services.state_service import record as state_record
from src.contracts.state import (
    StateBatchCheckItem,
    StateBatchCheckRequest,
    StateCheckRequest,
    StateDbAccessRequest,
    StateGetRequest,
    StateIngestCursorGetRequest,
    StateIngestCursorSetRequest,
)
from src.services.category_mapping_service import flush_uncategorized_tags
from src.utils.logging import child_context, log_event, new_run_context
from src.utils.errors import AppError
from src.utils.path_utils import safe_pdf_name

logger = logging.getLogger("market_lense.ingest_orchestrator")
DB_ACCESS_TIMEOUT_SECONDS = 0.0
EOF_RETRY_LIMIT = 1
STATE_PREFILTER_BATCH_SIZE = 200
DOC_MAP_EMPTY_ERROR_PREFIX = "doc_map_empty:"


@dataclass(frozen=True)
class IngestBatchDependencies:
    list_pdfs: Callable[[DriveListRequest, RunContext], Iterable[DriveFile]]
    batch_should_skip: Callable[
        [list[DriveFile], str, RunContext], dict[tuple[str, str], bool]
    ]
    process_file: Callable[
        [DriveFile, int, IngestSettings, RunContext], _FileProcessResult
    ]
    thread_pool_executor_factory: Callable[[int], Any]
    flush_uncategorized_tags: Callable[[UncategorizedTagsFlushRequest, RunContext], Any]

    @classmethod
    def default(cls) -> "IngestBatchDependencies":
        return cls(
            list_pdfs=list_pdfs,
            batch_should_skip=_batch_should_skip,
            process_file=_process_file,
            thread_pool_executor_factory=ThreadPoolExecutor,
            flush_uncategorized_tags=flush_uncategorized_tags,
        )


def _should_skip(
    file: DriveFile, md5: Optional[str], state_db: str, ctx: RunContext
) -> bool:
    if not md5:
        return False
    req = StateCheckRequest(
        schema_version="1.0",
        state_db=state_db,
        file_id=file.file_id,
        md5=md5,
    )
    if not state_already_processed(req, ctx):
        return False
    return _processed_state_should_skip(file.file_id, md5, state_db, ctx)


def _processed_state_should_skip(
    file_id: str,
    md5: str,
    state_db: str,
    ctx: RunContext,
) -> bool:
    record = state_get(
        StateGetRequest(schema_version="1.0", state_db=state_db, file_id=file_id),
        ctx,
    )
    if record is None or record.md5 != md5:
        return False
    last_error = str(record.last_error or "").strip()
    text_validation_status = str(record.text_validation_status or "").strip().lower()
    if not last_error and text_validation_status not in {"pass", "fail"}:
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="processed_state_progress_retry_selected",
                module=logger.name,
                fields={
                    "file_id": file_id,
                    "md5": md5,
                    "vector_store_status": record.vector_store_status or "",
                },
            )
        )
        return False
    if (
        last_error.startswith(DOC_MAP_EMPTY_ERROR_PREFIX)
        and text_validation_status == "pass"
    ):
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="processed_state_doc_map_retry_selected",
                module=logger.name,
                fields={
                    "file_id": file_id,
                    "md5": md5,
                    "last_error": last_error,
                    "text_validation_status": text_validation_status,
                },
            )
        )
        return False
    return True


def _batch_should_skip(
    files: list[DriveFile],
    state_db: str,
    ctx: RunContext,
) -> dict[tuple[str, str], bool]:
    items = []
    for file in files:
        md5 = file.md5_checksum.strip() if file.md5_checksum else ""
        if not md5:
            continue
        items.append(
            StateBatchCheckItem(schema_version="1.0", file_id=file.file_id, md5=md5)
        )
    if not items:
        return {}
    response = state_already_processed_batch(
        StateBatchCheckRequest(
            schema_version="1.0",
            state_db=state_db,
            items=items,
        ),
        ctx,
    )
    processed = {(item.file_id, item.md5) for item in response.processed_items}
    lookup: dict[tuple[str, str], bool] = {}
    retryable_matches = 0
    for item in items:
        key = (item.file_id, item.md5)
        if key not in processed:
            lookup[key] = False
            continue
        should_skip = _processed_state_should_skip(
            item.file_id,
            item.md5,
            state_db,
            ctx,
        )
        if not should_skip:
            retryable_matches += 1
        lookup[key] = should_skip
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="drive_list_state_batch_checked",
            module=logger.name,
            fields={
                "checked": len(items),
                "matched": len(processed),
                "skipped": sum(1 for should_skip in lookup.values() if should_skip),
                "retryable_matches": retryable_matches,
            },
        )
    )
    return lookup


def _cache_pdf_path(settings: IngestSettings, file: DriveFile) -> str:
    cache_name = safe_pdf_name(file.file_id)
    return str(Path(settings.cache_dir) / cache_name)


def _ensure_file_name(
    file: DriveFile, settings: IngestSettings, ctx: RunContext
) -> DriveFile:
    if file.name:
        return file
    try:
        meta = get_file_metadata(
            DriveFileMetadataRequest(
                schema_version="1.0",
                file_id=file.file_id,
                service_account_path=settings.google_sa_path,
                auth_mode=settings.drive_auth_mode,
                oauth_client_path=settings.google_oauth_client_path,
                oauth_token_path=settings.google_oauth_token_path,
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
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="drive_file_metadata_failed",
                module=logger.name,
                fields={"file_id": file.file_id, "error": exc.message},
            )
        )
        return DriveFile(
            schema_version="1.0",
            file_id=file.file_id,
            name=file.file_id,
            modified_time=file.modified_time,
            md5_checksum=file.md5_checksum,
        )


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
    except AppError as exc:
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="report_metadata_lookup_failed",
                module=logger.name,
                fields={"file_id": file.file_id, "error": str(exc)},
            )
        )
        return None
    if not metadata or not metadata.md5 or metadata.md5 != md5:
        return None
    html_path = (metadata.html_path or "").strip()
    if not html_path:
        return None
    html_stat = file_stat(FileStatRequest(schema_version="1.0", path=html_path), ctx)
    if not html_stat.exists:
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="report_html_missing",
                module=logger.name,
                fields={"file_id": file.file_id, "md5": md5, "html_path": html_path},
            )
        )
        return None
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="report_html_cache_hit",
            module=logger.name,
            fields={"file_id": file.file_id, "md5": md5, "html_path": html_path},
        )
    )
    return html_path


def _run_step_with_retry(step_name: str, ctx: RunContext, func, retries: int = 2):
    return run_step_with_default_policy(
        step_name=step_name,
        operation=func,
        ctx=ctx,
        logger=logger,
        module_name=logger.name,
        retries=retries,
        sleep_fn=time.sleep,
    )


def _process_file(
    file: DriveFile,
    index: int,
    settings: IngestSettings,
    root_ctx: RunContext,
) -> _FileProcessResult:
    dependencies = IngestFileDependencies(
        should_skip=_should_skip,
        cache_pdf_path=_cache_pdf_path,
        resolve_md5_sidecar=resolve_md5_sidecar,
        ensure_file_name=_ensure_file_name,
        write_md5_sidecar=write_md5_sidecar,
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
                retries=2,
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


def _acquire_ingest_lock(settings: IngestSettings, lock_ctx: RunContext):
    lock_resp = acquire_lock(
        LockAcquireRequest(
            schema_version="1.0",
            lock_path=settings.ingest_lock_path,
            owner_id=f"ingest:{lock_ctx.run_id}",
            pid=os.getpid(),
            ttl_seconds=settings.ingest_lock_ttl_seconds,
        ),
        lock_ctx,
    )
    if lock_resp.acquired:
        lock_info = lock_resp.lock
        logger.info(
            log_event(
                lock_ctx,
                role="orchestrator",
                event="ingest_lock_acquired",
                module=logger.name,
                fields={
                    "lock_path": settings.ingest_lock_path,
                    "owner_id": lock_info.owner_id if lock_info else "",
                    "pid": lock_info.pid if lock_info else None,
                },
            )
        )
        return lock_info
    conflict = lock_resp.conflict
    logger.info(
        log_event(
            lock_ctx,
            role="orchestrator",
            event="ingest_lock_conflict",
            module=logger.name,
            fields={
                "lock_path": settings.ingest_lock_path,
                "existing_owner": conflict.owner_id if conflict else None,
                "existing_pid": conflict.pid if conflict else None,
            },
        )
    )
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


def _verify_ingest_db_access(settings: IngestSettings, root_ctx: RunContext) -> None:
    db_ctx = child_context(root_ctx, task_id="ingest_db_access")
    logger.info(
        log_event(
            db_ctx,
            role="orchestrator",
            event="ingest_db_access_start",
            module=logger.name,
            fields={
                "state_db": settings.state_db,
                "reports_db": settings.reports_db,
            },
        )
    )
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
    if state_access.accessible and report_access.accessible:
        logger.info(
            log_event(
                db_ctx,
                role="orchestrator",
                event="ingest_db_access_complete",
                module=logger.name,
                fields={
                    "state_db": settings.state_db,
                    "reports_db": settings.reports_db,
                },
            )
        )
        return
    locked = []
    if state_access.locked:
        locked.append(f"state_db={settings.state_db}")
    if report_access.locked:
        locked.append(f"reports_db={settings.reports_db}")
    reason = ", ".join(locked) if locked else "unknown"
    logger.info(
        log_event(
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
        )
    )
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


def _resolve_modified_after(
    settings: IngestSettings,
    *,
    limit: Optional[int],
    root_ctx: RunContext,
) -> Optional[str]:
    if limit is not None:
        logger.info(
            log_event(
                root_ctx,
                role="orchestrator",
                event="ingest_modified_after_ignored",
                module=logger.name,
                fields={"reason": "limit_override", "limit": limit},
            )
        )
        return None
    cursor_resp = get_ingest_cursor(
        StateIngestCursorGetRequest(
            schema_version="1.0",
            state_db=settings.state_db,
        ),
        root_ctx,
    )
    modified_after = cursor_resp.last_successful_ingest_utc
    if modified_after:
        logger.info(
            log_event(
                root_ctx,
                role="orchestrator",
                event="ingest_modified_after_loaded",
                module=logger.name,
                fields={"modified_after": modified_after},
            )
        )
    return modified_after


def _build_drive_list_request(
    settings: IngestSettings,
    *,
    folder_id: Optional[str],
    limit: Optional[int],
    modified_after: Optional[str],
) -> DriveListRequest:
    max_n = limit if limit is not None else settings.batch_limit
    return DriveListRequest(
        schema_version="1.0",
        folder_id=folder_id or settings.gdrive_folder_id,
        service_account_path=settings.google_sa_path,
        auth_mode=settings.drive_auth_mode,
        oauth_client_path=settings.google_oauth_client_path,
        oauth_token_path=settings.google_oauth_token_path,
        page_size=min(max_n, 1000) if limit is not None else None,
        order_by="modifiedTime desc" if limit is not None else None,
        modified_after=modified_after,
        list_mode=settings.drive_list_mode,
        supports_all_drives=settings.drive_supports_all_drives,
        include_items_from_all_drives=settings.drive_include_items_from_all_drives,
        drive_id=settings.drive_id,
    )


def _materialize_files_to_process(
    list_req: DriveListRequest,
    *,
    settings: IngestSettings,
    max_n: int,
    deps: IngestBatchDependencies,
    root_ctx: RunContext,
) -> list[DriveFile]:
    files_to_process: list[DriveFile] = []
    pending_md5_files: list[DriveFile] = []

    def _flush_pending_md5_files() -> None:
        nonlocal pending_md5_files
        if not pending_md5_files:
            return
        lookup = deps.batch_should_skip(pending_md5_files, settings.state_db, root_ctx)
        for pending in pending_md5_files:
            drive_md5 = pending.md5_checksum.strip() if pending.md5_checksum else ""
            if drive_md5 and lookup.get((pending.file_id, drive_md5), False):
                logger.info(
                    log_event(
                        root_ctx,
                        role="orchestrator",
                        event="drive_list_skip_processed",
                        module=logger.name,
                        fields={"file_id": pending.file_id, "md5": drive_md5},
                    )
                )
                continue
            files_to_process.append(pending)
            if len(files_to_process) >= max_n:
                break
        pending_md5_files = []

    for file in deps.list_pdfs(list_req, root_ctx):
        drive_md5 = file.md5_checksum.strip() if file.md5_checksum else None
        if drive_md5:
            pending_md5_files.append(file)
            if len(pending_md5_files) >= STATE_PREFILTER_BATCH_SIZE:
                _flush_pending_md5_files()
                if len(files_to_process) >= max_n:
                    break
            continue
        files_to_process.append(file)
        if len(files_to_process) >= max_n:
            break

    if len(files_to_process) < max_n:
        _flush_pending_md5_files()
    logger.info(
        log_event(
            root_ctx,
            role="orchestrator",
            event="drive_list_materialized",
            module=logger.name,
            fields={"count": len(files_to_process), "limit": max_n},
        )
    )
    return files_to_process


def _resolve_worker_limit(
    settings: IngestSettings,
    *,
    file_count: int,
    root_ctx: RunContext,
) -> int:
    worker_limit = settings.ingest_worker_limit
    try:
        worker_limit = int(worker_limit)
    except (TypeError, ValueError):
        worker_limit = 1
    if worker_limit < 1:
        worker_limit = 1
    logger.info(
        log_event(
            root_ctx,
            role="orchestrator",
            event="ingest_worker_config",
            module=logger.name,
            fields={
                "worker_limit": worker_limit,
                "file_count": file_count,
            },
        )
    )
    return worker_limit


def _process_ingest_batch(
    files_to_process: list[DriveFile],
    *,
    settings: IngestSettings,
    deps: IngestBatchDependencies,
    root_ctx: RunContext,
) -> list[_FileProcessResult]:
    worker_limit = _resolve_worker_limit(
        settings,
        file_count=len(files_to_process),
        root_ctx=root_ctx,
    )
    results: list[_FileProcessResult] = []
    if worker_limit <= 1 or len(files_to_process) <= 1:
        for idx, file in enumerate(files_to_process):
            results.append(deps.process_file(file, idx, settings, root_ctx))
        return results

    with deps.thread_pool_executor_factory(worker_limit) as executor:
        futures = {
            executor.submit(deps.process_file, file, idx, settings, root_ctx): (
                idx,
                file,
            )
            for idx, file in enumerate(files_to_process)
        }
        for future in as_completed(futures):
            idx, file = futures[future]
            try:
                result = future.result()
            except (
                AppError,
                OSError,
                RuntimeError,
                ValueError,
                TypeError,
            ) as exc:  # pragma: no cover - defensive fallback
                file_ctx = child_context(root_ctx, task_id=file.file_id)
                logger.info(
                    log_event(
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
                    )
                )
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
    return results


def _update_ingest_cursor(
    settings: IngestSettings,
    *,
    processed: int,
    had_errors: bool,
    limit: Optional[int],
    root_ctx: RunContext,
) -> None:
    if not had_errors and processed > 0 and limit is None:
        try:
            now_utc = (
                datetime.now(timezone.utc)
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z")
            )
            set_ingest_cursor(
                StateIngestCursorSetRequest(
                    schema_version="1.0",
                    state_db=settings.state_db,
                    last_successful_ingest_utc=now_utc,
                ),
                root_ctx,
            )
            logger.info(
                log_event(
                    root_ctx,
                    role="orchestrator",
                    event="ingest_cursor_updated",
                    module=logger.name,
                    fields={"last_successful_ingest_utc": now_utc},
                )
            )
        except AppError as exc:
            logger.info(
                log_event(
                    root_ctx,
                    role="orchestrator",
                    event="ingest_cursor_update_failed",
                    module=logger.name,
                    fields={"error": str(exc)},
                )
            )
        return
    logger.info(
        log_event(
            root_ctx,
            role="orchestrator",
            event="ingest_cursor_skipped",
            module=logger.name,
            fields={
                "reason": "errors_detected"
                if had_errors
                else "no_processed_or_limit_override",
                "processed": processed,
                "limit": limit,
            },
        )
    )


def _finalize_ingest_run(
    settings: IngestSettings,
    *,
    deps: IngestBatchDependencies,
    root_ctx: RunContext,
    lock_ctx: RunContext,
    lock_info,
) -> None:
    try:
        deps.flush_uncategorized_tags(
            UncategorizedTagsFlushRequest(
                schema_version="1.0",
                path=settings.category_mapping_path,
            ),
            root_ctx,
        )
    except AppError as exc:
        logger.info(
            log_event(
                root_ctx,
                role="orchestrator",
                event="ingest_uncategorized_flush_failed",
                module=logger.name,
                fields={"path": settings.category_mapping_path, "error": str(exc)},
            )
        )
    if not lock_info:
        return
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
        logger.info(
            log_event(
                lock_ctx,
                role="orchestrator",
                event="ingest_lock_released",
                module=logger.name,
                fields={"lock_path": lock_info.lock_path},
            )
        )
    except AppError as exc:
        logger.info(
            log_event(
                lock_ctx,
                role="orchestrator",
                event="ingest_lock_release_failed",
                module=logger.name,
                fields={
                    "lock_path": settings.ingest_lock_path,
                    "error": str(exc),
                },
            )
        )


def run_ingest(
    settings: IngestSettings,
    *,
    folder_id: Optional[str] = None,
    limit: Optional[int] = None,
    ctx: Optional[RunContext] = None,
    dependencies: Optional[IngestBatchDependencies] = None,
) -> List[IngestOutcome]:
    deps = dependencies or IngestBatchDependencies.default()
    root_ctx = ctx or new_run_context()
    lock_ctx = child_context(root_ctx, task_id="ingest_lock")
    lock_info = None
    try:
        lock_info = _acquire_ingest_lock(settings, lock_ctx)
        _verify_ingest_db_access(settings, root_ctx)

        logger.info(
            log_event(
                root_ctx,
                role="orchestrator",
                event="ingest_start",
                module=logger.name,
                fields={
                    "folder_id": folder_id or settings.gdrive_folder_id,
                    "limit": limit,
                },
            )
        )

        modified_after = _resolve_modified_after(
            settings,
            limit=limit,
            root_ctx=root_ctx,
        )
        max_n = limit if limit is not None else settings.batch_limit
        list_req = _build_drive_list_request(
            settings,
            folder_id=folder_id,
            limit=limit,
            modified_after=modified_after,
        )
        files_to_process = _run_step_with_retry(
            "materialize_drive_files",
            root_ctx,
            lambda: _materialize_files_to_process(
                list_req,
                settings=settings,
                max_n=max_n,
                deps=deps,
                root_ctx=root_ctx,
            ),
            2,
        )
        results = _process_ingest_batch(
            files_to_process,
            settings=settings,
            deps=deps,
            root_ctx=root_ctx,
        )
        results.sort(key=lambda r: r.index)
        outcomes = [result.outcome for result in results]
        processed = sum(result.processed for result in results)
        had_errors = any(result.had_error for result in results)

        logger.info(
            log_event(
                root_ctx,
                role="orchestrator",
                event="ingest_complete",
                module=logger.name,
                fields={"processed": processed},
            )
        )
        _update_ingest_cursor(
            settings,
            processed=processed,
            had_errors=had_errors,
            limit=limit,
            root_ctx=root_ctx,
        )
        return outcomes
    finally:
        _finalize_ingest_run(
            settings,
            deps=deps,
            root_ctx=root_ctx,
            lock_ctx=lock_ctx,
            lock_info=lock_info,
        )
