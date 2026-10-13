from __future__ import annotations

import math
import re

# ruff: noqa: F401,F403,F405,F821
from src.contracts.pdf_contents import PdfContentsDetectionResponse
from src.contracts.pdf_text import (
    PdfTextChartIdentityEvidence,
    PdfTextExtractResponse,
    PdfTextLayoutEvidence,
    PdfTextPage,
)
from src.contracts.pdf_utils import PdfInfoResponse
from src.utils.pdf_text_layout import (
    has_two_panel_percent_chart_candidate,
    two_panel_chart_platform_names,
)

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
    require_chart_identity: bool = True,
    source_md5: str | None = None,
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
        raw_layout_evidence = item.get("layout_evidence", [])
        layout_analysis_complete = _cached_bool(item.get("layout_analysis_complete"))
        chart_identity_status = _cached_str(item.get("chart_identity_status"))
        raw_chart_identity = item.get("chart_identity_evidence")
        if (
            page_number is None
            or page_number <= previous_page_number
            or (source_page_count is not None and page_number > source_page_count)
            or page_text is None
            or not isinstance(raw_layout_evidence, list)
        ):
            return None
        if (
            require_chart_identity
            and has_two_panel_percent_chart_candidate(page_text)
            and (
                layout_analysis_complete is not True
                or chart_identity_status
                not in {"transcribed", "abstained", "geometry_unresolved"}
            )
        ):
            # Upgrade only stale chart pages; unrelated native-text caches remain valid.
            return None
        chart_identity_evidence = None
        if raw_chart_identity is not None:
            chart_identity_evidence = _adapt_cached_chart_identity(
                raw_chart_identity,
                page_number=page_number,
                page_text=page_text,
                source_md5=source_md5,
            )
            if chart_identity_evidence is None:
                return None
        if chart_identity_status in {"transcribed", "abstained"}:
            if (
                chart_identity_evidence is None
                or chart_identity_evidence.status != chart_identity_status
            ):
                return None
        elif chart_identity_evidence is not None:
            return None
        layout_evidence = []
        for raw_evidence in raw_layout_evidence:
            if not isinstance(raw_evidence, dict):
                return None
            evidence_schema_version = _cached_str(raw_evidence.get("schema_version"))
            evidence_kind = _cached_str(raw_evidence.get("evidence_kind"))
            evidence_text = _cached_str(raw_evidence.get("text"))
            if (
                evidence_schema_version != "1.0"
                or evidence_kind != "native_pdf_geometry"
                or not evidence_text
            ):
                return None
            layout_evidence.append(
                PdfTextLayoutEvidence(
                    schema_version=evidence_schema_version,
                    evidence_kind=evidence_kind,
                    text=evidence_text,
                )
            )
        pages.append(
            PdfTextPage(
                page_number=page_number,
                text=page_text,
                layout_evidence=layout_evidence,
                layout_analysis_complete=bool(layout_analysis_complete),
                chart_identity_status=chart_identity_status or "not_applicable",
                chart_identity_evidence=chart_identity_evidence,
            )
        )
        previous_page_number = page_number
    return PdfTextExtractResponse(
        schema_version="1.0",
        text=text,
        pages_extracted=pages_extracted,
        char_count=char_count,
        text_density=text_density,
        pages=pages,
    )


def _adapt_cached_chart_identity(
    payload: object,
    *,
    page_number: int,
    page_text: str,
    source_md5: str | None,
) -> PdfTextChartIdentityEvidence | None:
    if not isinstance(payload, dict):
        return None
    string_fields = (
        "schema_version",
        "status",
        "source_pdf_md5",
        "crop_image_path",
        "crop_image_sha256",
        "label_left",
        "label_right",
        "model",
        "request_id",
        "prompt_sha256",
    )
    values = {name: _cached_str(payload.get(name)) for name in string_fields}
    source_pdf_md5 = values["source_pdf_md5"] or ""
    physical_page = _cached_int(payload.get("physical_page_number"))
    confidence_left = _cached_float(payload.get("confidence_left"))
    confidence_right = _cached_float(payload.get("confidence_right"))
    if (
        any(value is None for value in values.values())
        or values["schema_version"] != "1.0"
        or values["status"] not in {"transcribed", "abstained"}
        or physical_page != page_number
        or not re.fullmatch(r"[0-9a-fA-F]{32}", source_pdf_md5)
        or (
            source_md5 is not None
            and source_pdf_md5.casefold() != source_md5.casefold()
        )
        or not re.fullmatch(r"[0-9a-fA-F]{64}", values["crop_image_sha256"] or "")
        or not re.fullmatch(r"[0-9a-fA-F]{64}", values["prompt_sha256"] or "")
        or not values["crop_image_path"]
        or not values["model"]
        or confidence_left is None
        or confidence_right is None
        or not 0.0 <= confidence_left <= 1.0
        or not 0.0 <= confidence_right <= 1.0
    ):
        return None
    if values["status"] == "transcribed":
        expected_labels = two_panel_chart_platform_names(page_text)
        if (
            not values["label_left"]
            or not values["label_right"]
            or values["label_left"].casefold() == values["label_right"].casefold()
            or expected_labels is None
            or {values["label_left"].casefold(), values["label_right"].casefold()}
            != {label.casefold() for label in expected_labels}
            or confidence_left < 0.9
            or confidence_right < 0.9
        ):
            return None
    elif values["label_left"] or values["label_right"]:
        return None
    return PdfTextChartIdentityEvidence(
        schema_version=values["schema_version"] or "1.0",
        status=values["status"] or "abstained",
        source_pdf_md5=source_pdf_md5,
        physical_page_number=physical_page,
        crop_image_path=values["crop_image_path"] or "",
        crop_image_sha256=values["crop_image_sha256"] or "",
        label_left=values["label_left"] or "",
        label_right=values["label_right"] or "",
        confidence_left=confidence_left,
        confidence_right=confidence_right,
        model=values["model"] or "",
        request_id=values["request_id"] or "",
        prompt_sha256=values["prompt_sha256"] or "",
    )


__all__ = [
    name
    for name in globals()
    if not name.startswith("__") and name not in {"annotations"}
]
