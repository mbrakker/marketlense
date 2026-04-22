from __future__ import annotations

import logging
from typing import Optional

from src.contracts.drive import DriveFile
from src.contracts.ingest import IngestOutcome, IngestSettings
from src.contracts.run_context import RunContext
from src.generators.report_generation_dependencies import ReportGeneratorDependencies
from src.generators.report_generation_shared import logger
from src.utils.errors import AppError
from src.utils.logging import log_event

logging.getLogger("market_lense.report_generator")


def generate_report(
    file: DriveFile,
    local_pdf_path: str,
    settings: IngestSettings,
    md5: Optional[str],
    ctx: RunContext,
    *,
    evidence_pack_openai_client=None,
    artifact_openai_client=None,
    dependencies: Optional[ReportGeneratorDependencies] = None,
) -> IngestOutcome:
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="invalid_generator_entrypoint",
            module=logger.name,
            fields={
                "file_id": file.file_id,
                "expected_entrypoint": "src.orchestrators.report_generation_orchestrator.run_report_generation",
            },
        )
    )
    raise AppError(
        code="invalid_generator_entrypoint",
        message=(
            "Report generation sequencing belongs to "
            "src.orchestrators.report_generation_orchestrator.run_report_generation."
        ),
        retryable=False,
        context={"file_id": file.file_id},
    )
