from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Iterable, List, Optional

from src.contracts.pdf_utils import PdfEofCheckRequest
from src.services.pdf_utils_service import check_pdf_eof
from src.contracts.drive import DriveDownloadRequest, DriveListRequest, DriveFile
from src.contracts.ingest import IngestOutcome, IngestSettings
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
from src.services.state_service import already_processed as state_already_processed
from src.services.state_service import record as state_record
from src.contracts.state import StateCheckRequest, StateRecordRequest
from src.utils.logging import child_context, log_event, new_run_context
from src.utils.errors import AppError
from src.utils.path_utils import safe_pdf_name

logger = logging.getLogger("market_lense.ingest_orchestrator")


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


def run_ingest(
    settings: IngestSettings,
    *,
    folder_id: Optional[str] = None,
    limit: Optional[int] = None,
) -> List[IngestOutcome]:
    ctx = new_run_context()
    logger.info(log_event(
        ctx,
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

    outcomes: List[IngestOutcome] = []
    processed = 0

    for file in list_pdfs(list_req, ctx):
        if processed >= max_n:
            break

        try:
            cache_path = ""
            md5 = None
            file_ctx = child_context(ctx, task_id=file.file_id)
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
                dl_resp = download_pdf(dl_req, file_ctx)
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
                dl_resp = download_pdf(dl_req, file_ctx)
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
                    fields={"file_id": file.file_id, "path": cache_path},
                ))
                outcomes.append(IngestOutcome(
                    schema_version="1.0",
                    file_id=file.file_id,
                    name=file.name,
                    md5=md5,
                    html_path=None,
                    status="skipped",
                    error="pdf_missing_eof",
                ))
                continue

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

            retries = 2
            for attempt in range(retries + 1):
                try:
                    outcome = generate_report(file, cache_path, settings, md5, file_ctx)
                    outcomes.append(outcome)
                    state_record(
                        StateRecordRequest(
                            schema_version="1.0",
                            state_db=settings.state_db,
                            file_id=file.file_id,
                            md5=md5 or "",
                            openai_file_id="",
                        ),
                        file_ctx,
                    )
                    processed += 1
                    break
                except AppError as exc:
                    if not exc.retryable or attempt >= retries:
                        raise
                    logger.info(log_event(
                        file_ctx,
                        role="orchestrator",
                        event="report_retry",
                        module=logger.name,
                        fields={"file_id": file.file_id, "attempt": attempt + 1, "code": exc.code},
                    ))
                    time.sleep(1 + attempt)
        except Exception as exc:
            logger.info(log_event(
                file_ctx,
                role="orchestrator",
                event="file_processing_exception",
                module=logger.name,
                fields={"file_id": file.file_id, "error": str(exc)},
            ))
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
        ctx,
        role="orchestrator",
        event="ingest_complete",
        module=logger.name,
        fields={"processed": processed},
    ))
    return outcomes
