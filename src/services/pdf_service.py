from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Tuple

import pymupdf as fitz
from pypdf import PdfReader
from pypdf.errors import PdfReadError, PdfStreamError

from src.contracts.pdf_context import PdfContext, PdfContextBuildRequest, PdfContextBuildResponse
from src.contracts.pdf_contents import PdfContentsDetectionRequest, PdfContentsDetectionResponse
from src.contracts.pdf_text import (
    PdfTextExtractRequest,
    PdfTextExtractResponse,
    PdfTextSample,
    PdfTextSampleRequest,
    PdfTextSampleResponse,
)
from src.contracts.pdf_utils import PdfEofCheckRequest, PdfEofCheckResponse, PdfInfoRequest, PdfInfoResponse
from src.contracts.run_context import RunContext
from src.utils.errors import AppError
from src.utils.logging import log_event
from src.utils.pdf_utils import pdf_has_eof_marker as _pdf_has_eof_marker

logger = logging.getLogger("market_lense.pdf_service")


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


def extract_pdf_text(request: PdfTextExtractRequest, ctx: RunContext) -> PdfTextExtractResponse:
    logger.info(log_event(
        ctx,
        role="service",
        event="pdf_text_extract_start",
        module=logger.name,
        fields={
            "path": request.path,
            "max_pages": request.max_pages,
            "max_chars": request.max_chars,
            "using_context": bool(request.pdf_context and request.pdf_context.pypdf_reader),
        },
    ))
    reader = request.pdf_context.pypdf_reader if request.pdf_context else None
    owns_reader = False
    if reader is None:
        try:
            reader = PdfReader(request.path, strict=False)
            owns_reader = True
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

    try:
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
        density = _compute_text_density(raw_text, pages)
        response = PdfTextExtractResponse(
            schema_version="1.0",
            text=text_out,
            pages_extracted=pages,
            char_count=len(text_out),
            text_density=density,
        )
        logger.info(log_event(
            ctx,
            role="service",
            event="pdf_text_extract_complete",
            module=logger.name,
            fields={"pages": response.pages_extracted, "chars": response.char_count, "text_density": response.text_density},
        ))
        return response
    finally:
        if owns_reader and reader is not None:
            _close_pypdf_reader(reader)


def sample_pdf_text(request: PdfTextSampleRequest, ctx: RunContext) -> PdfTextSampleResponse:
    logger.info(log_event(
        ctx,
        role="service",
        event="pdf_text_sample_start",
        module=logger.name,
        fields={
            "path": request.path,
            "page_indices": request.page_indices,
            "using_context": bool(request.pdf_context and request.pdf_context.pypdf_reader),
        },
    ))
    reader = request.pdf_context.pypdf_reader if request.pdf_context else None
    owns_reader = False
    if reader is None:
        try:
            reader = PdfReader(request.path, strict=False)
            owns_reader = True
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

    try:
        page_count = len(reader.pages)
        samples = []
        for idx in request.page_indices:
            if idx < 0 or idx >= page_count:
                continue
            text = _extract_text(reader, idx)
            char_count = len(text)
            samples.append(PdfTextSample(
                page_index=idx,
                page_number=idx + 1,
                char_count=char_count,
                has_text=bool(text.strip()),
            ))
        any_text = any(sample.has_text for sample in samples)
        response = PdfTextSampleResponse(
            schema_version="1.0",
            samples=samples,
            any_text=any_text,
        )
        logger.info(log_event(
            ctx,
            role="service",
            event="pdf_text_sample_complete",
            module=logger.name,
            fields={
                "sample_count": len(samples),
                "any_text": any_text,
                "page_indices": [sample.page_index for sample in samples],
            },
        ))
        return response
    finally:
        if owns_reader and reader is not None:
            _close_pypdf_reader(reader)


def detect_contents_page(request: PdfContentsDetectionRequest, ctx: RunContext) -> PdfContentsDetectionResponse:
    logger.info(log_event(
        ctx,
        role="service",
        event="pdf_contents_detect_start",
        module=logger.name,
        fields={
            "path": request.path,
            "max_pages": request.max_pages,
            "min_headings": request.min_headings,
            "keyword_count": len(request.keywords or []),
            "using_context": bool(request.pdf_context and request.pdf_context.pypdf_reader),
        },
    ))
    reader = request.pdf_context.pypdf_reader if request.pdf_context else None
    owns_reader = False
    if reader is None:
        try:
            reader = PdfReader(request.path, strict=False)
            owns_reader = True
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
                message=f"Failed to read PDF for contents detection: {request.path}",
                cause=exc,
                retryable=True,
            ) from exc
        except Exception as exc:
            raise AppError(
                code="pdf_read_failed",
                message=f"Failed to read PDF for contents detection: {request.path}",
                cause=exc,
                retryable=True,
            ) from exc

    page_index = -1
    heading = ""
    confidence = 0.0
    try:
        page_count = len(reader.pages)
        max_pages = min(max(request.max_pages, 0), page_count)
        for i in range(max_pages):
            text = _extract_text(reader, i)
            if not text.strip():
                continue
            score, matched_heading = _score_page(text, request.keywords or [], request.min_headings)
            if score > confidence:
                confidence = score
                page_index = i
                heading = matched_heading
        has_contents = page_index >= 0
        page_number = page_index + 1 if has_contents else 0
        response = PdfContentsDetectionResponse(
            schema_version="1.0",
            path=request.path,
            has_contents=has_contents,
            page_index=page_index,
            page_number=page_number,
            heading=heading,
            confidence=confidence,
        )
        logger.info(log_event(
            ctx,
            role="service",
            event="pdf_contents_detect_complete",
            module=logger.name,
            fields={
                "has_contents": has_contents,
                "page_index": page_index,
                "page_number": page_number,
                "confidence": round(confidence, 3),
                "heading": heading,
                "scanned_pages": max_pages,
            },
        ))
        return response
    finally:
        if owns_reader and reader is not None:
            _close_pypdf_reader(reader)


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


def _extract_text(reader: PdfReader, page_index: int) -> str:
    try:
        return reader.pages[page_index].extract_text() or ""
    except Exception:
        return ""


def _score_page(text: str, keywords: list[str], min_headings: int) -> Tuple[float, str]:
    lowered = text.lower()
    heading_match = ""
    for kw in keywords:
        kw_norm = kw.lower().strip()
        if not kw_norm:
            continue
        if kw_norm in lowered:
            heading_match = kw_norm
            break
    if not heading_match:
        return 0.0, ""

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    entry_lines = []
    tail_digit_re = re.compile(r"\d{1,3}\s*$")
    for line in lines:
        line_lower = line.lower()
        if heading_match in line_lower:
            continue
        if len(line) < 4:
            continue
        if tail_digit_re.search(line):
            entry_lines.append(line)
            continue
        dotted_tail = line.rsplit(" ", 1)[-1]
        if dotted_tail.isdigit():
            entry_lines.append(line)

    if not entry_lines:
        return 0.2, heading_match

    structured_hits = sum(1 for line in entry_lines if "." in line)
    length_factor = min(len(entry_lines), max(min_headings, 1))
    score = 0.4 + 0.1 * length_factor + 0.05 * min(structured_hits, 3)
    if len(entry_lines) >= min_headings:
        score += 0.2
    return min(score, 1.0), heading_match


def _close_pypdf_reader(reader: PdfReader) -> None:
    try:
        stream = getattr(reader, "stream", None)
        if stream is None:
            return
        close_fn = getattr(stream, "close", None)
        if callable(close_fn):
            close_fn()
    except Exception:
        pass


def _compute_text_density(text: str, pages: int) -> float:
    if not pages or pages <= 0:
        return 0.0
    try:
        return len(text or "") / float(pages)
    except Exception:
        return 0.0
