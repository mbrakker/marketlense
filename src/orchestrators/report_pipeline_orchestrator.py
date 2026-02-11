from __future__ import annotations

import logging
import time
from typing import Callable, Optional

from src.contracts.drive import DriveFile
from src.contracts.ingest import IngestOutcome, IngestSettings
from src.contracts.run_context import RunContext
from src.generators.report_generator import generate_report as generate_report_generator
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.report_pipeline_orchestrator")


def run_report_pipeline(
    file: DriveFile,
    local_pdf_path: str,
    settings: IngestSettings,
    md5: Optional[str],
    ctx: RunContext,
    *,
    retries: int = 2,
    generate_report_fn: Optional[
        Callable[[DriveFile, str, IngestSettings, Optional[str], RunContext], IngestOutcome]
    ] = None,
) -> IngestOutcome:
    report_fn = generate_report_fn or generate_report_generator
    logger.info(log_event(
        ctx,
        role="orchestrator",
        event="report_pipeline_start",
        module=logger.name,
        fields={
            "file_id": file.file_id,
            "md5": md5 or "",
            "local_pdf_path": local_pdf_path,
            "retries": retries,
        },
    ))

    attempt = 0
    while True:
        try:
            outcome = report_fn(file, local_pdf_path, settings, md5, ctx)
            logger.info(log_event(
                ctx,
                role="orchestrator",
                event="report_pipeline_complete",
                module=logger.name,
                fields={
                    "file_id": file.file_id,
                    "status": outcome.status,
                    "html_path": outcome.html_path or "",
                    "error": outcome.error or "",
                    "attempt": attempt,
                },
            ))
            return outcome
        except AppError as exc:
            if not exc.retryable or attempt >= retries:
                logger.info(log_event(
                    ctx,
                    role="orchestrator",
                    event="report_pipeline_failed",
                    module=logger.name,
                    fields={
                        "file_id": file.file_id,
                        "code": exc.code,
                        "error": exc.message,
                        "attempt": attempt,
                        "retryable": exc.retryable,
                    },
                ))
                raise
            logger.info(log_event(
                ctx,
                role="orchestrator",
                event="report_pipeline_retry",
                module=logger.name,
                fields={"file_id": file.file_id, "attempt": attempt + 1, "code": exc.code},
            ))
            time.sleep(1 + attempt)
            attempt += 1
