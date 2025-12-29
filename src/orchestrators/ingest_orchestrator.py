from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Iterable, List, Optional

from src.contracts.pdf_utils import PdfEofCheckRequest
from src.services.pdf_utils_service import check_pdf_eof
from src.contracts.drive import DriveDownloadRequest, DriveListRequest, DriveFile
from src.contracts.ingest import IngestOutcome, IngestSettings
from src.generators.report_generator import generate_report
from src.services.drive_service import build_drive_client, download_pdf, list_pdfs
from src.services.state_service import StateStore
from src.services.state_service import already_processed as state_already_processed
from src.services.state_service import record as state_record
from src.contracts.state import StateCheckRequest, StateRecordRequest
from src.utils.logging import child_context, log_event, new_run_context
from src.utils.errors import AppError

logger = logging.getLogger("market_lense.ingest_orchestrator")


def _should_skip(file: DriveFile, md5: Optional[str], state: StateStore, ctx: RunContext) -> bool:
    if not md5:
        return False
    req = StateCheckRequest(schema_version="1.0", file_id=file.file_id, md5=md5)
    return state_already_processed(state, req, ctx)


def run_ingest(
    settings: IngestSettings,
    *,
    folder_id: Optional[str] = None,
    limit: Optional[int] = None,
) -> List[IngestOutcome]:
    ctx = new_run_context()
    log_event(
        logger,
        ctx,
        role="orchestrator",
        event="ingest_start",
        fields={"folder_id": folder_id or settings.gdrive_folder_id, "limit": limit},
    )

    drive = build_drive_client(settings.google_sa_path)
    list_req = DriveListRequest(schema_version="1.0", folder_id=folder_id or settings.gdrive_folder_id)
    max_n = limit if limit is not None else settings.batch_limit

    outcomes: List[IngestOutcome] = []
    processed = 0

    with StateStore(settings.state_db) as state:
        for file in list_pdfs(drive, list_req, ctx):
            if processed >= max_n:
                break

            try:
                file_ctx = child_context(ctx, task_id=file.file_id)
                dl_req = DriveDownloadRequest(schema_version="1.0", file=file, cache_dir=settings.cache_dir)
                dl_resp = download_pdf(drive, dl_req, file_ctx)
                eof_check = check_pdf_eof(
                    PdfEofCheckRequest(schema_version="1.0", path=dl_resp.local_path),
                    file_ctx,
                )
                if not eof_check.has_eof:
                    try:
                        Path(dl_resp.local_path).unlink()
                    except Exception:
                        logger.exception("Failed to remove cached PDF: %s", dl_resp.local_path)
                    dl_resp = download_pdf(drive, dl_req, file_ctx)
                eof_check = check_pdf_eof(
                    PdfEofCheckRequest(schema_version="1.0", path=dl_resp.local_path),
                    file_ctx,
                )
                if not eof_check.has_eof:
                    log_event(
                        logger,
                        file_ctx,
                        role="orchestrator",
                        event="pdf_missing_eof",
                        fields={"file_id": file.file_id, "path": dl_resp.local_path},
                    )
                    outcomes.append(IngestOutcome(
                        schema_version="1.0",
                        file_id=file.file_id,
                        name=file.name,
                        md5=dl_resp.md5,
                        html_path=None,
                        status="skipped",
                        error="pdf_missing_eof",
                    ))
                    continue

                if _should_skip(file, dl_resp.md5, state, file_ctx):
                    outcomes.append(IngestOutcome(
                        schema_version="1.0",
                        file_id=file.file_id,
                        name=file.name,
                        md5=dl_resp.md5,
                        html_path=None,
                        status="skipped",
                        error="already_processed",
                    ))
                    continue

                retries = 2
                for attempt in range(retries + 1):
                    try:
                        outcome = generate_report(file, dl_resp.local_path, settings, dl_resp.md5, file_ctx)
                        outcomes.append(outcome)
                        state_record(
                            state,
                            StateRecordRequest(
                                schema_version="1.0",
                                file_id=file.file_id,
                                md5=dl_resp.md5 or "",
                                openai_file_id="",
                            ),
                            file_ctx,
                        )
                        processed += 1
                        break
                    except AppError as exc:
                        if not exc.retryable or attempt >= retries:
                            raise
                        log_event(
                            logger,
                            file_ctx,
                            role="orchestrator",
                            event="report_retry",
                            fields={"file_id": file.file_id, "attempt": attempt + 1, "code": exc.code},
                        )
                        time.sleep(1 + attempt)
            except Exception as exc:
                logger.exception("Error processing %s", file.file_id)
                outcomes.append(IngestOutcome(
                    schema_version="1.0",
                    file_id=file.file_id,
                    name=file.name,
                    md5=None,
                    html_path=None,
                    status="error",
                    error=str(exc),
                ))

    log_event(
        logger,
        ctx,
        role="orchestrator",
        event="ingest_complete",
        fields={"processed": processed},
    )
    return outcomes
