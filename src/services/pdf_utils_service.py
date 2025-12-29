from __future__ import annotations

import logging

from src.utils.pdf_utils import pdf_has_eof_marker as _pdf_has_eof_marker
from src.contracts.pdf_utils import PdfEofCheckRequest, PdfEofCheckResponse
from src.contracts.run_context import RunContext
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.pdf_utils_service")


def check_pdf_eof(request: PdfEofCheckRequest, ctx: RunContext) -> PdfEofCheckResponse:
    log_event(
        logger,
        ctx,
        role="service",
        event="pdf_eof_check_start",
        fields={"path": request.path},
    )
    has_eof = _pdf_has_eof_marker(request.path)
    log_event(
        logger,
        ctx,
        role="service",
        event="pdf_eof_check_complete",
        fields={"path": request.path, "has_eof": has_eof},
    )
    return PdfEofCheckResponse(schema_version="1.0", path=request.path, has_eof=has_eof)
