from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Iterable, List, Optional

from src.contracts.categories import UncategorizedTagsFlushRequest
from src.contracts.pdf_utils import PdfEofCheckRequest
from src.services.pdf_service import check_pdf_eof
from src.contracts.drive import DriveDownloadRequest, DriveListRequest, DriveFile
from src.contracts.ingest import IngestOutcome, IngestSettings
from src.contracts.lock import LockAcquireRequest, LockReleaseRequest
from src.contracts.report_store import ReportMetadataDbAccessRequest
from src.contracts.run_context import RunContext
from src.generators.report_generator import generate_report
from src.services.drive_service import download_pdf, list_pdfs
from src.services.file_service import (
    delete_file,
    file_exists,
    file_md5,
    write_bytes,
)
from src.contracts.files import DeleteFileRequest, FileExistsRequest, FileHashRequest, WriteBytesRequest
from src.services.lock_service import acquire_lock, release_lock
from src.services.report_store_service import check_report_db_access
from src.services.state_service import already_processed as state_already_processed
from src.services.state_service import check_state_db_access
from src.services.state_service import record as state_record
from src.contracts.state import StateCheckRequest, StateDbAccessRequest, StateRecordRequest
from src.services.category_mapping_service import flush_uncategorized_tags
from src.utils.logging import child_context, log_event, new_run_context
from src.utils.errors import AppError
from src.utils.path_utils import safe_pdf_name

logger = logging.getLogger("market_lense.ingest_orchestrator")
DB_ACCESS_TIMEOUT_SECONDS = 0.0


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

        list_req = DriveListRequest(
            schema_version="1.0",
            folder_id=folder_id or settings.gdrive_folder_id,
            service_account_path=settings.google_sa_path,
        )
        max_n = limit if limit is not None else settings.batch_limit

        for file in list_pdfs(list_req, root_ctx):
            if processed >= max_n:
                break

            try:
                cache_path = ""
                md5 = None
                file_ctx = child_context(root_ctx, task_id=file.file_id)
                cache_name = safe_pdf_name(file.name or f"{file.file_id}.pdf")
                cache_path = str(Path(settings.cache_dir) / cache_name)

                exists_resp = file_exists(
                    FileExistsRequest(schema_version="1.0", path=cache_path),
                    file_ctx,
                )
                cache_hit = False
                if exists_resp.exists and file.md5_checksum:
                    md5_resp = file_md5(
                        FileHashRequest(schema_version="1.0", path=cache_path),
                        file_ctx,
                    )
                    if md5_resp.md5 == file.md5_checksum:
                        md5 = md5_resp.md5
                        cache_hit = True
                if cache_hit:
                    logger.info(log_event(
                        file_ctx,
                        role="orchestrator",
                        event="pdf_cache_hit",
                        module=logger.name,
                        fields={"file_id": file.file_id, "path": cache_path, "md5": md5},
                    ))
                else:
                    logger.info(log_event(
                        file_ctx,
                        role="orchestrator",
                        event="pdf_cache_miss",
                        module=logger.name,
                        fields={"file_id": file.file_id, "path": cache_path},
                    ))

                if not cache_hit:
                    dl_req = DriveDownloadRequest(
                        schema_version="1.0",
                        file=file,
                        service_account_path=settings.google_sa_path,
                    )
                    dl_resp = _run_step_with_retry("download_pdf", file_ctx, lambda: download_pdf(dl_req, file_ctx))
                    write_resp = write_bytes(
                        WriteBytesRequest(schema_version="1.0", path=cache_path, content=dl_resp.content),
                        file_ctx,
                    )
                    md5 = write_resp.md5
                eof_check = check_pdf_eof(
                    PdfEofCheckRequest(schema_version="1.0", path=cache_path),
                    file_ctx,
                )
                if not eof_check.has_eof:
                    delete_file(
                        DeleteFileRequest(schema_version="1.0", path=cache_path, missing_ok=True),
                        file_ctx,
                    )
                    dl_req = DriveDownloadRequest(
                        schema_version="1.0",
                        file=file,
                        service_account_path=settings.google_sa_path,
                    )
                    dl_resp = _run_step_with_retry("download_pdf", file_ctx, lambda: download_pdf(dl_req, file_ctx))
                    write_resp = write_bytes(
                        WriteBytesRequest(schema_version="1.0", path=cache_path, content=dl_resp.content),
                        file_ctx,
                    )
                    md5 = write_resp.md5
                    eof_check = check_pdf_eof(
                        PdfEofCheckRequest(schema_version="1.0", path=cache_path),
                        file_ctx,
                    )
                if not eof_check.has_eof:
                    logger.info(log_event(
                        file_ctx,
                        role="orchestrator",
                        event="pdf_missing_eof",
                        module=logger.name,
                        fields={"file_id": file.file_id, "path": cache_path, "proceeding": True},
                    ))

                if _should_skip(file, md5, settings.state_db, file_ctx):
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
                        name=file.name,
                        md5=md5,
                        html_path=None,
                        status="skipped",
                        error="already_processed",
                    ))
                    continue

                outcome = _run_step_with_retry(
                    "generate_report",
                    file_ctx,
                    lambda: generate_report(file, cache_path, settings, md5, file_ctx),
                    retries=2,
                )
                outcomes.append(outcome)
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
                        last_error=outcome.vector_store_last_error,
                    ),
                    file_ctx,
                )
                processed += 1
            except Exception as exc:
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
                    name=file.name,
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
