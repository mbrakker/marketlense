from __future__ import annotations

# ruff: noqa: F401,F403,F405,F821

from src.contracts.pdf_contents import PdfContentsDetectionResponse
from src.contracts.pdf_text import PdfTextExtractResponse
from src.contracts.pdf_utils import PdfInfoResponse

from .shared import *  # noqa: F401,F403


def _cached_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
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
    if page_count is None or metadata is None:
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
    ):
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


def _adapt_cached_text(payload: dict[str, object]) -> PdfTextExtractResponse | None:
    text = _cached_str(payload.get("text"))
    pages_extracted = _cached_int(payload.get("pages_extracted"))
    char_count = _cached_int(payload.get("char_count"))
    text_density = _cached_float(payload.get("text_density"))
    if (
        text is None
        or pages_extracted is None
        or char_count is None
        or text_density is None
    ):
        return None
    return PdfTextExtractResponse(
        schema_version="1.0",
        text=text,
        pages_extracted=pages_extracted,
        char_count=char_count,
        text_density=text_density,
    )


__all__ = [
    name
    for name in globals()
    if not name.startswith("__") and name not in {"annotations"}
]
