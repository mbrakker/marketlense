from __future__ import annotations

import logging

from pypdf import PdfReader
from pypdf.errors import PdfReadError, PdfStreamError
from pathlib import Path

from src.utils.pdf_utils import pdf_has_eof_marker as _pdf_has_eof_marker
from src.contracts.pdf_utils import PdfEofCheckRequest, PdfEofCheckResponse, PdfInfoRequest, PdfInfoResponse
from src.contracts.run_context import RunContext
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.pdf_utils_service")


def check_pdf_eof(request: PdfEofCheckRequest, ctx: RunContext) -> PdfEofCheckResponse:
    logger.info(log_event(
        ctx,
        role="service",
        event="pdf_eof_check_start",
        module=logger.name,
        fields={"path": request.path},
    ))
    try:
        data = Path(request.path).read_bytes()
    except FileNotFoundError as exc:
        raise AppError(
            code="pdf_not_found",
            message=f"PDF not found: {request.path}",
            cause=exc,
            retryable=False,
        ) from exc
    except Exception as exc:
        raise AppError(
            code="pdf_read_failed",
            message=f"Failed to read PDF bytes: {request.path}",
            cause=exc,
            retryable=True,
        ) from exc
    has_eof = _pdf_has_eof_marker(data)
    logger.info(log_event(
        ctx,
        role="service",
        event="pdf_eof_check_complete",
        module=logger.name,
        fields={"path": request.path, "has_eof": has_eof},
    ))
    return PdfEofCheckResponse(schema_version="1.0", path=request.path, has_eof=has_eof)


def _normalize_metadata(raw_meta) -> dict[str, str]:
    if not raw_meta:
        return {}
    normalized: dict[str, str] = {}
    try:
        items = raw_meta.items() if hasattr(raw_meta, "items") else []
    except Exception:
        return {}
    for key, value in items:
        if key is None or value is None:
            continue
        key_str = str(key).strip()
        if not key_str:
            continue
        if key_str.startswith("/"):
            key_str = key_str[1:]
        try:
            val_str = str(value).strip()
        except Exception:
            val_str = ""
        if not val_str:
            continue
        normalized[key_str] = val_str
    return normalized


def extract_pdf_info(request: PdfInfoRequest, ctx: RunContext) -> PdfInfoResponse:
    logger.info(log_event(
        ctx,
        role="service",
        event="pdf_info_extract_start",
        module=logger.name,
        fields={"path": request.path},
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
            code="pdf_info_read_failed",
            message=f"Failed to read PDF for info: {request.path}",
            cause=exc,
            retryable=True,
        ) from exc
    except Exception as exc:
        raise AppError(
            code="pdf_info_read_failed",
            message=f"Failed to read PDF for info: {request.path}",
            cause=exc,
            retryable=True,
        ) from exc

    page_count = len(reader.pages)
    metadata = _normalize_metadata(reader.metadata)
    response = PdfInfoResponse(
        schema_version="1.0",
        path=request.path,
        page_count=page_count,
        metadata=metadata,
    )
    logger.info(log_event(
        ctx,
        role="service",
        event="pdf_info_extract_complete",
        module=logger.name,
        fields={"path": request.path, "page_count": page_count, "metadata_keys": list(metadata.keys())},
    ))
    return response
