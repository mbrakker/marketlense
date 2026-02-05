from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from src.contracts.categories import UncategorizedTagsFlushRequest
from src.contracts.pdf_utils import PdfEofCheckRequest
from src.services.pdf_service import check_pdf_eof
from src.contracts.drive import (
    DriveDownloadToPathRequest,
    DriveFileMetadataRequest,
    DriveListRequest,
    DriveFile,
)
from src.contracts.ingest import IngestOutcome, IngestSettings
from src.contracts.lock import LockAcquireRequest, LockReleaseRequest
from src.contracts.report_store import ReportMetadataDbAccessRequest, ReportMetadataGetRequest
from src.contracts.run_context import RunContext
from src.generators.report_generator import generate_report
from src.services.drive_service import download_pdf_to_path, get_file_metadata, list_pdfs
from src.services.file_service import (
    delete_file,
    file_stat,
    read_text,
    write_bytes,
)
from src.contracts.files import (
    DeleteFileRequest,
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
    StateRecordRequest,
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

        had_errors = False

        for file in files_to_process:
            if processed >= max_n:
                break

            try:
                file_ctx = child_context(root_ctx, task_id=file.file_id)
                display_name = file.name or file.file_id
                cache_path = _cache_pdf_path(settings, file)
                sidecar_path = _md5_sidecar_path(cache_path)
                md5 = None
                drive_md5 = file.md5_checksum.strip() if file.md5_checksum else None
                state_checked_md5 = None
                report_checked_md5 = None

                if drive_md5 and _should_skip(file, drive_md5, settings.state_db, file_ctx):
                    logger.info(log_event(
                        file_ctx,
                        role="orchestrator",
                        event="already_processed_skip",
                        module=logger.name,
                        fields={"file_id": file.file_id, "md5": drive_md5},
                    ))
                    outcomes.append(IngestOutcome(
                        schema_version="1.0",
                        file_id=file.file_id,
                        name=display_name,
                        md5=drive_md5,
                        html_path=None,
                        status="skipped",
                        error="already_processed",
                    ))
                    continue
                if drive_md5:
                    state_checked_md5 = drive_md5
                    existing_html = _existing_report_html(file, drive_md5, settings, file_ctx)
                    report_checked_md5 = drive_md5
                    if existing_html:
                        logger.info(log_event(
                            file_ctx,
                            role="orchestrator",
                            event="report_html_skip",
                            module=logger.name,
                            fields={"file_id": file.file_id, "md5": drive_md5, "html_path": existing_html},
                        ))
                        outcomes.append(IngestOutcome(
                            schema_version="1.0",
                            file_id=file.file_id,
                            name=display_name,
                            md5=drive_md5,
                            html_path=existing_html,
                            status="skipped",
                            error="html_exists",
                        ))
                        continue

                cache_hit = False
                cache_reason = ""
                sidecar_used = False
                stat_resp = file_stat(FileStatRequest(schema_version="1.0", path=cache_path), file_ctx)
                if stat_resp.exists:
                    sidecar_payload = _load_md5_sidecar(sidecar_path, file.file_id, file_ctx)
                    md5 = _sidecar_md5_for_stat(sidecar_payload, stat_resp.size_bytes, stat_resp.mtime_utc)
                    if md5:
                        sidecar_used = True
                        logger.info(log_event(
                            file_ctx,
                            role="orchestrator",
                            event="md5_sidecar_hit",
                            module=logger.name,
                            fields={"file_id": file.file_id, "path": sidecar_path, "md5": md5},
                        ))
                    else:
                        if sidecar_payload:
                            logger.info(log_event(
                                file_ctx,
                                role="orchestrator",
                                event="md5_sidecar_mismatch",
                                module=logger.name,
                                fields={"file_id": file.file_id, "path": sidecar_path},
                            ))
                        stat_resp = file_stat(
                            FileStatRequest(schema_version="1.0", path=cache_path, compute_md5=True),
                            file_ctx,
                        )
                        md5 = stat_resp.md5
                        if md5:
                            _write_md5_sidecar(
                                sidecar_path,
                                file,
                                md5,
                                stat_resp.size_bytes,
                                stat_resp.mtime_utc,
                                file_ctx,
                            )
                    if drive_md5 and md5:
                        cache_hit = md5 == drive_md5
                        if not cache_hit:
                            cache_reason = "md5_mismatch"
                    else:
                        cache_hit = md5 is not None
                        if md5 is None:
                            cache_reason = "md5_unavailable"
                    logger.info(log_event(
                        file_ctx,
                        role="orchestrator",
                        event="pdf_cache_hit" if cache_hit else "pdf_cache_miss",
                        module=logger.name,
                        fields={
                            "file_id": file.file_id,
                            "path": cache_path,
                            "md5": md5,
                            "drive_md5": drive_md5 or "",
                            "reason": cache_reason or ("sidecar" if sidecar_used else "hashed"),
                        },
                    ))
                else:
                    cache_reason = "missing"
                    logger.info(log_event(
                        file_ctx,
                        role="orchestrator",
                        event="pdf_cache_miss",
                        module=logger.name,
                        fields={"file_id": file.file_id, "path": cache_path, "reason": cache_reason},
                    ))

                if not cache_hit:
                    dl_req = DriveDownloadToPathRequest(
                        schema_version="1.0",
                        file=file,
                        service_account_path=settings.google_sa_path,
                        output_path=cache_path,
                    )
                    eof_check = None
                    attempt = 0
                    while True:
                        dl_resp = _run_step_with_retry(
                            "download_pdf",
                            file_ctx,
                            lambda: download_pdf_to_path(dl_req, file_ctx),
                        )
                        md5 = dl_resp.md5 or drive_md5
                        eof_check = check_pdf_eof(
                            PdfEofCheckRequest(schema_version="1.0", path=cache_path),
                            file_ctx,
                        )
                        if eof_check.has_eof or attempt >= EOF_RETRY_LIMIT:
                            break
                        logger.info(log_event(
                            file_ctx,
                            role="orchestrator",
                            event="pdf_eof_retry",
                            module=logger.name,
                            fields={"file_id": file.file_id, "path": cache_path, "attempt": attempt + 1},
                        ))
                        delete_file(
                            DeleteFileRequest(schema_version="1.0", path=cache_path, missing_ok=True),
                            file_ctx,
                        )
                        attempt += 1
                    if eof_check and not eof_check.has_eof:
                        logger.info(log_event(
                            file_ctx,
                            role="orchestrator",
                            event="pdf_missing_eof",
                            module=logger.name,
                            fields={"file_id": file.file_id, "path": cache_path, "proceeding": True},
                        ))
                    stat_resp = file_stat(FileStatRequest(schema_version="1.0", path=cache_path), file_ctx)
                    _write_md5_sidecar(
                        sidecar_path,
                        file,
                        md5,
                        stat_resp.size_bytes,
                        stat_resp.mtime_utc,
                        file_ctx,
                    )

                if md5 and md5 != state_checked_md5 and _should_skip(file, md5, settings.state_db, file_ctx):
                    logger.info(log_event(
                        file_ctx,
                        role="orchestrator",
                        event="already_processed_skip",
                        module=logger.name,
                        fields={"file_id": file.file_id, "md5": md5},
                    ))
                    outcomes.append(IngestOutcome(
                        schema_version="1.0",
                        file_id=file.file_id,
                        name=display_name,
                        md5=md5,
                        html_path=None,
                        status="skipped",
                        error="already_processed",
                    ))
                    continue

                if md5 and md5 != report_checked_md5:
                    existing_html = _existing_report_html(file, md5, settings, file_ctx)
                    report_checked_md5 = md5
                    if existing_html:
                        logger.info(log_event(
                            file_ctx,
                            role="orchestrator",
                            event="report_html_skip",
                            module=logger.name,
                            fields={"file_id": file.file_id, "md5": md5, "html_path": existing_html},
                        ))
                        outcomes.append(IngestOutcome(
                            schema_version="1.0",
                            file_id=file.file_id,
                            name=display_name,
                            md5=md5,
                            html_path=existing_html,
                            status="skipped",
                            error="html_exists",
                        ))
                        continue

                file = _ensure_file_name(file, settings, file_ctx)
                display_name = file.name or file.file_id

                outcome = _run_step_with_retry(
                    "generate_report",
                    file_ctx,
                    lambda: generate_report(file, cache_path, settings, md5, file_ctx),
                    retries=2,
                )
                outcomes.append(outcome)
                if outcome.status == "error":
                    had_errors = True
                if outcome.vector_store_id:
                    logger.info(log_event(
                        file_ctx,
                        role="orchestrator",
                        event="VECTOR_STORE_CREATED",
                        module=logger.name,
                        fields={"file_id": file.file_id, "vector_store_id": outcome.vector_store_id},
                    ))
                if outcome.vector_store_status:
                    logger.info(log_event(
                        file_ctx,
                        role="orchestrator",
                        event="VECTOR_STORE_INDEXED",
                        module=logger.name,
                        fields={
                            "file_id": file.file_id,
                            "vector_store_id": outcome.vector_store_id or "",
                            "status": outcome.vector_store_status,
                            "indexed_at_utc": outcome.indexed_at_utc or "",
                        },
                    ))
                if outcome.evidence_packs:
                    logger.info(log_event(
                        file_ctx,
                        role="orchestrator",
                        event="EVIDENCE_READY",
                        module=logger.name,
                        fields={
                            "file_id": file.file_id,
                            "vector_store_id": outcome.vector_store_id or "",
                            "pack_count": len(outcome.evidence_packs),
                        },
                    ))
                if outcome.status == "error":
                    logger.info(log_event(
                        file_ctx,
                        role="orchestrator",
                        event="report_generation_failed",
                        module=logger.name,
                        fields={
                            "file_id": file.file_id,
                            "md5": md5 or "",
                            "error": outcome.error or "",
                            "vector_store_id": outcome.vector_store_id or "",
                        },
                    ))
                    if outcome.doc_map_summary:
                        summary = outcome.doc_map_summary
                        logger.info(log_event(
                            file_ctx,
                            role="orchestrator",
                            event="doc_map_validation_halt",
                            module=logger.name,
                            fields={
                                "file_id": file.file_id,
                                "md5": md5 or "",
                                "error": outcome.error or "",
                                "has_content": summary.get("has_content"),
                                "sections_count": summary.get("sections_count"),
                                "title_present": summary.get("title_present"),
                                "doc_id_present": summary.get("doc_id_present"),
                                "summary_present": summary.get("summary_present"),
                                "not_found_reason": summary.get("not_found_reason") or "",
                            },
                        ))
                last_error = outcome.vector_store_last_error
                if outcome.status == "error" and outcome.error:
                    last_error = outcome.error if not last_error else f"{last_error} | {outcome.error}"
                state_record(
                    StateRecordRequest(
                        schema_version="1.0",
                        state_db=settings.state_db,
                        file_id=file.file_id,
                        md5=md5 or "",
                        openai_file_id=outcome.openai_file_id or "",
                        vector_store_id=outcome.vector_store_id,
                        vector_store_status=outcome.vector_store_status,
                        indexed_at_utc=outcome.indexed_at_utc,
                        last_error=last_error,
                        text_validation_status=outcome.text_validation_status,
                        text_validation_reason=outcome.text_validation_reason,
                        text_validation_pages=outcome.text_validation_pages,
                        doc_map_summary=outcome.doc_map_summary,
                    ),
                    file_ctx,
                )
                processed += 1
            except Exception as exc:
                had_errors = True
                logger.info(log_event(
                    file_ctx,
                    role="orchestrator",
                    event="file_processing_error",
                    module=logger.name,
                    fields={
                        "file_id": file.file_id,
                        "error": str(exc),
                        "local_path": cache_path,
                        "md5": md5,
                    },
                ))
                outcomes.append(IngestOutcome(
                    schema_version="1.0",
                    file_id=file.file_id,
                    name=display_name,
                    md5=None,
                    html_path=None,
                    status="error",
                    error=str(exc),
                ))
                continue

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
