from __future__ import annotations

import math

# ruff: noqa: F401,F403,F405,F821
from src.contracts.pdf_contents import PdfContentsDetectionResponse
from src.contracts.pdf_text import PdfTextExtractResponse, PdfTextPage
from src.contracts.pdf_utils import PdfInfoResponse

from .shared import *  # noqa: F401,F403


def _cached_int(value: object) -> int | None:
    if type(value) is int:
        return value
    return None


def _cached_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _cached_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def _cached_str(value: object) -> str | None:
    if isinstance(value, str):
        return value
    return None


def _cached_metadata(value: object) -> dict[str, str] | None:
    if not isinstance(value, dict):
        return None
    metadata: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not isinstance(item, str):
            return None
        metadata[key] = item
    return metadata


def _adapt_cached_pdf_info(
    payload: dict[str, object],
    *,
    pdf_path: str,
) -> PdfInfoResponse | None:
    page_count = _cached_int(payload.get("page_count"))
    metadata = _cached_metadata(payload.get("metadata"))
    if page_count is None or page_count < 0 or metadata is None:
        return None
    return PdfInfoResponse(
        schema_version="1.0",
        path=pdf_path,
        page_count=page_count,
        metadata=metadata,
    )


def _adapt_cached_contents(
    payload: dict[str, object],
    *,
    analysis_pdf_path: str,
    source_page_count: int | None = None,
) -> PdfContentsDetectionResponse | None:
    has_contents = _cached_bool(payload.get("has_contents"))
    page_index = _cached_int(payload.get("page_index"))
    page_number = _cached_int(payload.get("page_number"))
    heading = _cached_str(payload.get("heading"))
    confidence = _cached_float(payload.get("confidence"))
    if (
        has_contents is None
        or page_index is None
        or page_number is None
        or heading is None
        or confidence is None
        or not math.isfinite(confidence)
        or confidence < 0.0
        or confidence > 1.0
    ):
        return None
    if has_contents:
        if (
            page_index < 0
            or page_number <= 0
            or page_number != page_index + 1
            or (source_page_count is not None and page_number > source_page_count)
        ):
            return None
    elif page_index != -1 or page_number != 0:
        return None
    return PdfContentsDetectionResponse(
        schema_version="1.0",
        path=analysis_pdf_path,
        has_contents=has_contents,
        page_index=page_index,
        page_number=page_number,
        heading=heading,
        confidence=confidence,
    )


def _adapt_cached_text(
    payload: dict[str, object],
    *,
    source_page_count: int | None = None,
) -> PdfTextExtractResponse | None:
    schema_version = _cached_str(payload.get("schema_version"))
    text = _cached_str(payload.get("text"))
    pages_extracted = _cached_int(payload.get("pages_extracted"))
    char_count = _cached_int(payload.get("char_count"))
    text_density = _cached_float(payload.get("text_density"))
    if (
        schema_version not in {"1.0", "2.0"}
        or text is None
        or pages_extracted is None
        or pages_extracted < 0
        or char_count is None
        or char_count < 0
        or char_count != len(text)
        or text_density is None
        or not math.isfinite(text_density)
        or text_density < 0.0
        or (source_page_count is not None and pages_extracted > source_page_count)
    ):
        return None
    raw_pages = payload.get("pages")
    if not isinstance(raw_pages, list) or len(raw_pages) != pages_extracted:
        return None
    pages = []
    previous_page_number = 0
    for item in raw_pages:
        if not isinstance(item, dict):
            return None
        page_number = _cached_int(item.get("page_number"))
        page_text = _cached_str(item.get("text"))
        if (
            page_number is None
            or page_number <= previous_page_number
            or (source_page_count is not None and page_number > source_page_count)
            or page_text is None
        ):
            return None
        pages.append(PdfTextPage(page_number=page_number, text=page_text))
        previous_page_number = page_number
    return PdfTextExtractResponse(
        schema_version="1.0",
        text=text,
        pages_extracted=pages_extracted,
        char_count=char_count,
        text_density=text_density,
        pages=pages,
    )


__all__ = [
    name
    for name in globals()
    if not name.startswith("__") and name not in {"annotations"}
]
