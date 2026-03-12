from __future__ import annotations

import re
from typing import Tuple

from pypdf import PdfReader
from pypdf.errors import PdfReadError, PdfStreamError

from src.contracts.pdf_contents import (
    PdfContentsDetectionRequest,
    PdfContentsDetectionResponse,
)
from src.contracts.run_context import RunContext
from src.utils.errors import AppError
from src.utils.logging import log_event

from .shared import logger
from .text import _close_pypdf_reader, _extract_text

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
