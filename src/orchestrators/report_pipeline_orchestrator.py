from __future__ import annotations

import logging
import time
from typing import Callable, Optional

from src.contracts.drive import DriveFile
from src.contracts.ingest import IngestOutcome, IngestSettings
from src.contracts.run_context import RunContext
from src.generators.report_generator import generate_report as generate_report_generator
from src.orchestrators.retry_orchestrator import RetryPolicy, run_with_retry
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

    attempt_state = {"value": 0}

    def _report_attempt() -> IngestOutcome:
        current_attempt = attempt_state["value"]
        attempt_state["value"] += 1
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
                "attempt": current_attempt,
            },
        ))
        return outcome

    return run_with_retry(
        step_name="report_pipeline",
        operation=_report_attempt,
        ctx=ctx,
        logger=logger,
        module_name=logger.name,
        policy=RetryPolicy(retries=retries, base_delay_seconds=1.0, backoff_step_seconds=1.0),
        retry_event="report_pipeline_retry",
        retry_fields_builder=lambda exc, attempt: {
            "file_id": file.file_id,
            "attempt": attempt + 1,
            "code": exc.code if isinstance(exc, AppError) else "",
        },
        failure_event="report_pipeline_failed",
        failure_fields_builder=lambda exc, attempt, retryable: {
            "file_id": file.file_id,
            "code": exc.code if isinstance(exc, AppError) else "",
            "error": exc.message if isinstance(exc, AppError) else str(exc),
            "attempt": attempt,
            "retryable": retryable,
        },
        is_retryable=lambda exc: isinstance(exc, AppError) and exc.retryable,
        sleep_fn=time.sleep,
    )
