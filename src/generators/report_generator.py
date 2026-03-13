from __future__ import annotations

import logging
from typing import Optional

from src.contracts.drive import DriveFile
from src.contracts.ingest import IngestOutcome, IngestSettings
from src.contracts.run_context import RunContext
from src.generators.report_generation_dependencies import ReportGeneratorDependencies
from src.generators.report_generation_shared import logger
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
            event="report_generate_delegate",
            module=logger.name,
            fields={
                "file_id": file.file_id,
                "delegated_to": "src.orchestrators.report_generation_orchestrator.run_report_generation",
            },
        )
    )
    from src.orchestrators.report_generation_orchestrator import run_report_generation

    return run_report_generation(
        file,
        local_pdf_path,
        settings,
        md5,
        ctx,
        evidence_pack_openai_client=evidence_pack_openai_client,
        artifact_openai_client=artifact_openai_client,
        dependencies=dependencies,
    )
