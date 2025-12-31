from __future__ import annotations

import logging

from src.contracts.report_assets import ExtractCandidatesRequest, ExtractCandidatesResponse
from src.contracts.run_context import RunContext
from src.services.candidate_extraction_service import collect_candidates as _collect_candidates
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.extract_service")


def collect_candidates(request: ExtractCandidatesRequest, ctx: RunContext) -> ExtractCandidatesResponse:
    logger.info(log_event(
        ctx,
        role="service",
        event="extract_candidates_start",
        module=logger.name,
        fields={"pdf_path": request.pdf_path},
    ))
    candidates = _collect_candidates(request, ctx).candidates
    logger.info(log_event(
        ctx,
        role="service",
        event="extract_candidates_complete",
        module=logger.name,
        fields={"count": len(candidates)},
    ))
    return ExtractCandidatesResponse(schema_version="1.0", candidates=candidates)
