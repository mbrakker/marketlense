from __future__ import annotations

import logging

import pymupdf as fitz
from pypdf import PdfReader
from pypdf.errors import PdfReadError, PdfStreamError

from src.contracts.pdf_context import PdfContext, PdfContextBuildRequest, PdfContextBuildResponse
from src.contracts.run_context import RunContext
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.pdf_context_service")


def build_pdf_context(request: PdfContextBuildRequest, ctx: RunContext) -> PdfContextBuildResponse:
    logger.info(log_event(
        ctx,
        role="service",
        event="pdf_context_build_start",
        module=logger.name,
        fields={"path": request.path, "load_fitz": request.load_fitz, "load_pypdf": request.load_pypdf},
    ))

    fitz_doc = None
    fitz_error = None
    if request.load_fitz:
        try:
            fitz_doc = fitz.open(request.path)
        except Exception as exc:
            fitz_error = str(exc)

    pypdf_reader = None
    pypdf_error = None
    if request.load_pypdf:
        try:
            pypdf_reader = PdfReader(request.path, strict=False)
        except FileNotFoundError as exc:
            raise AppError(
                code="pdf_not_found",
                message=f"PDF not found: {request.path}",
                cause=exc,
                retryable=False,
            ) from exc
        except (PdfReadError, PdfStreamError) as exc:
            pypdf_error = str(exc)
        except Exception as exc:
            pypdf_error = str(exc)

    context = PdfContext(
        schema_version="1.0",
        path=request.path,
        fitz_doc=fitz_doc,
        pypdf_reader=pypdf_reader,
    )

    logger.info(log_event(
        ctx,
        role="service",
        event="pdf_context_build_complete",
        module=logger.name,
        fields={
            "fitz_ready": fitz_doc is not None,
            "pypdf_ready": pypdf_reader is not None,
            "fitz_error": fitz_error or "",
            "pypdf_error": pypdf_error or "",
        },
    ))

    return PdfContextBuildResponse(
        schema_version="1.0",
        context=context,
        fitz_error=fitz_error,
        pypdf_error=pypdf_error,
    )
