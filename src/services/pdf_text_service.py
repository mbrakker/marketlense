from __future__ import annotations

import logging

from pypdf import PdfReader
from pypdf.errors import PdfReadError, PdfStreamError

from src.contracts.pdf_text import PdfTextExtractRequest, PdfTextExtractResponse
from src.contracts.run_context import RunContext
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.pdf_text_service")


def extract_pdf_text(request: PdfTextExtractRequest, ctx: RunContext) -> PdfTextExtractResponse:
    logger.info(log_event(
        ctx,
        role="service",
        event="pdf_text_extract_start",
        module=logger.name,
        fields={"path": request.path, "max_pages": request.max_pages, "max_chars": request.max_chars},
    ))
    try:
        reader = PdfReader(request.path, strict=False)
    except FileNotFoundError as exc:
        raise AppError(
            code="pdf_not_found",
            message=f"PDF not found: {request.path}",
            cause=exc,
            retryable=False,
        ) from exc
    except (PdfReadError, PdfStreamError) as exc:
        raise AppError(
            code="pdf_read_failed",
            message=f"Failed to read PDF: {request.path}",
            cause=exc,
            retryable=True,
        ) from exc
    except Exception as exc:
        raise AppError(
            code="pdf_read_failed",
            message=f"Failed to read PDF: {request.path}",
            cause=exc,
            retryable=True,
        ) from exc

    pages = min(len(reader.pages), max(request.max_pages, 0))
    chunks = []
    for i in range(pages):
        try:
            text = reader.pages[i].extract_text() or ""
        except Exception:
            text = ""
        chunks.append(text)
    raw_text = "\n\n".join(chunks)
    text_out = raw_text[: max(request.max_chars, 0)]
    response = PdfTextExtractResponse(
        schema_version="1.0",
        text=text_out,
        pages_extracted=pages,
        char_count=len(text_out),
    )
    logger.info(log_event(
        ctx,
        role="service",
        event="pdf_text_extract_complete",
        module=logger.name,
        fields={"pages": response.pages_extracted, "chars": response.char_count},
    ))
    return response
