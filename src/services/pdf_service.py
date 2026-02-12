from __future__ import annotations

import io
import logging
import math
import re
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import pymupdf as fitz
import pdfplumber
from PIL import Image
from pypdf import PdfReader
from pypdf.errors import PdfReadError, PdfStreamError

from src.contracts.candidates import Candidate
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
from src.contracts.report_assets import (
    CropRequest,
    CropResponse,
    ExtractCandidatesRequest,
    ExtractCandidatesResponse,
    FigureExtractRequest,
    FigureExtractResponse,
    PreviewRequest,
    PreviewResponse,
)
from src.contracts.report_models import CropItem
from src.contracts.run_context import RunContext
from src.utils.errors import AppError
from src.utils.logging import log_event
from src.utils.pdf_utils import pdf_has_eof_marker as _pdf_has_eof_marker
from src.utils.slugify import slugify

logger = logging.getLogger("market_lense.pdf_service")
candidate_logger = logging.getLogger("market_lense.pdf_service.candidate_extraction")
crop_logger = logging.getLogger("market_lense.pdf_service.crop")
preview_logger = logging.getLogger("market_lense.pdf_service.preview")
figure_logger = logging.getLogger("market_lense.pdf_service.figure")
EOF_TAIL_BYTES = 2048


def check_pdf_eof(request: PdfEofCheckRequest, ctx: RunContext) -> PdfEofCheckResponse:
    logger.info(log_event(
        ctx,
        role="service",
        event="pdf_eof_check_start",
        module=logger.name,
        fields={"path": request.path, "tail_bytes": EOF_TAIL_BYTES},
    ))
    try:
        path = Path(request.path)
        with path.open("rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            if size <= 0:
                data = b""
            else:
                start = max(size - EOF_TAIL_BYTES, 0)
                fh.seek(start)
                data = fh.read()
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
        fields={"path": request.path, "has_eof": has_eof, "tail_bytes": EOF_TAIL_BYTES},
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
        fields={"path": request.path, "using_context": bool(request.pdf_context and request.pdf_context.pypdf_reader)},
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
    try:
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
    finally:
        if owns_reader and reader is not None:
            _close_pypdf_reader(reader)


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


# BEGIN PDF CANDIDATE EXTRACTION
_PDFMINER_LOGGERS = ("pdfminer", "pdfminer.pdfinterp", "pdfminer.cmapdb", "pdfminer.layout")

CAPTION_HINTS = ("figure", "fig.", "exhibit", "chart", "graph", "source")
CHART_CAPTION_HINTS = ("figure", "fig.", "exhibit", "chart", "graph")
TABLE_CAPTION_HINTS = CAPTION_HINTS + ("table",)
CHART_TEXT_MAX_LINES = 6
CHART_TEXT_MIN_CHARS = 60
CHART_TEXT_RATIO_THRESHOLD = 0.35
CHART_DEDUP_IOU = 0.9
CHART_OVERLAP_IOU = 0.85
CHART_OVERLAP_CONTAINMENT = 0.88
CHART_MARGIN_FRAC = 0.12
CHART_MARGIN_RELAX_FRAC = 0.05
CHART_PAD_X_FRAC = 0.01
CHART_PAD_Y_FRAC = 0.008
CHART_NOTE_MAX_DIST = 140
CHART_NOTE_MAX_GAP_X_FRAC = 0.25
CHART_CAPTION_TOP_PAD_PX = 16.0
CHART_CAPTION_TOP_PAD_FRAC = 0.35
CHART_CAPTION_TOP_SEARCH_FRAC = 0.2
CHART_CAPTION_TOP_GUARD_FRAC = 0.01
CHART_CAPTION_TOP_BLOCK_H_OVERLAP = 0.3
CHART_CAPTION_MERGE_MAX_GAP_FRAC = 0.18
CHART_CROP_PAD_COMPENSATION = 0
CHART_NOTE_PAD_EXTRA = 24
CHART_NOTE_BELOW_GUARD_PX = 3
CHART_NOTE_BELOW_MIN_H_OVERLAP = 0.2
CHART_LABEL_MAX_GAP_FRAC = 0.06
CHART_LABEL_MAX_V_GAP_FRAC = 0.05
CHART_LABEL_MIN_V_OVERLAP = 0.35
CHART_LABEL_MIN_H_OVERLAP = 0.35
CHART_LABEL_PARAGRAPH_MIN_LINES = 3
CHART_LABEL_PARAGRAPH_MAX_AVG_LINE_LEN = 32
CHART_LABEL_MAX_LINES = 6
CHART_LABEL_MAX_AVG_LINE_LEN = 40
CHART_LABEL_MAX_HEIGHT_FRAC = 0.5
CHART_EDGE_TEXT_MIN_GAP_FRAC = 0.08
CHART_EDGE_TEXT_MAX_PAD_FRAC = 0.12
CHART_EDGE_TEXT_MIN_GAP_X_FRAC = 0.04
CHART_EDGE_TEXT_MAX_PAD_X_FRAC = 0.06
CHART_EDGE_TEXT_HEADING_GAP_SCALE = 0.4
CHART_EDGE_TEXT_HEADING_GAP_X_SCALE = 0.5
CHART_WHITESPACE_GUARD_GAP_FRAC = 0.02
CHART_WHITESPACE_GUARD_GAP_X_FRAC = 0.02
CHART_WHITESPACE_MAX_PAD_FRAC = 0.06
CHART_WHITESPACE_MAX_PAD_X_FRAC = 0.05
CHART_WHITESPACE_MIN_OVERLAP = 0.3
CHART_HEADING_TOP_MAX_PAD_FRAC = 0.0
CHART_HEADING_TOP_SEARCH_FRAC = 0.25
CHART_HEADING_TOP_GUARD_FRAC = 0.01
CHART_HEADING_TOP_BLOCK_H_OVERLAP = 0.3
CHART_HEADING_MERGE_MAX_GAP_FRAC = 0.08
DRAWING_MIN_RECT_DIM = 6.0
DRAWING_MIN_RECT_AREA = 200.0
DRAWING_BACKGROUND_MIN_AREA_FRAC = 0.9
DRAWING_BACKGROUND_MAX_STROKE = 1.0
TABLE_SETTINGS_LATTICE = {
    "vertical_strategy": "lines",
    "horizontal_strategy": "lines",
}
TABLE_SETTINGS_STREAM = {
    "vertical_strategy": "text",
    "horizontal_strategy": "text",
    "snap_tolerance": 5,
    "join_tolerance": 5,
    "intersection_tolerance": 10,
    "edge_min_length": 8,
}
TABLE_DEDUP_IOU = 0.8
TABLE_MIN_ROWS = 2
TABLE_MIN_COLS = 2
TABLE_MIN_NONEMPTY_CELLS = 4
TABLE_MIN_TEXT_CHARS = 12
TABLE_MIN_AREA_FRAC = 0.006
TABLE_MIN_WIDTH_FRAC = 0.08
TABLE_MIN_HEIGHT_FRAC = 0.06
TABLE_MIN_ASPECT = 0.15
TABLE_MAX_ASPECT = 6.5
TABLE_TEXT_HEAVY_MAX_NUMERIC_RATIO = 0.05
TABLE_TEXT_HEAVY_MIN_AVG_WORDS = 6.0
TABLE_TEXT_HEAVY_MIN_ROWS = 4
TABLE_INDEX_MIN_ROWS = 6
TABLE_INDEX_MAX_COLS = 3
TABLE_INDEX_PAGE_RATIO = 0.6
TABLE_INDEX_MIN_FIRST_COL_WORDS = 5
TABLE_STREAM_MIN_ROWS_FOR_LIKENESS = 4
TABLE_STREAM_MIN_COLS_FOR_LIKENESS = 4
TABLE_STREAM_MIN_COL_CONSISTENCY = 0.5
TABLE_STREAM_MAX_ROW_LEN_CV = 0.9
TABLE_STREAM_TEXTY_MIN_COLS = 5
TABLE_STREAM_TEXTY_MIN_ROWS = 6
TABLE_STREAM_TEXTY_MIN_LINES = 6
TABLE_STREAM_TEXTY_MIN_AREA = 0.45
TABLE_STREAM_TEXTY_MAX_NUMERIC_RATIO = 0.07
TABLE_STREAM_TEXTY_MIN_AVG_LINE_LEN = 35
TABLE_STREAM_TEXTBLOCK_MIN_AREA = 0.45
TABLE_STREAM_TEXTBLOCK_MIN_LINES = 10
TABLE_STREAM_TEXTBLOCK_MIN_AVG_LINE_LEN = 30
TABLE_STREAM_TEXTBLOCK_MAX_NUMERIC_RATIO = 0.07
TABLE_STREAM_TEXTBLOCK_MAX_FILL_RATIO = 0.6
TABLE_STREAM_TEXTBLOCK_MAX_COL_CONSISTENCY = 0.4
TABLE_STREAM_TEXTBLOCK_MIN_ROW_LEN_CV = 0.6
TABLE_STREAM_INFOBOX_MIN_AREA = 0.3
TABLE_STREAM_INFOBOX_MIN_ROWS = 12
TABLE_STREAM_INFOBOX_MAX_COLS = 6
TABLE_STREAM_INFOBOX_MAX_NUMERIC_RATIO = 0.08
TABLE_STREAM_INFOBOX_MAX_AVG_WORDS = 3.5
TABLE_STREAM_INFOBOX_MIN_LINES = 18
TABLE_STREAM_INFOBOX_MAX_ROW_LEN_CV = 0.7
TABLE_STREAM_LIST_MIN_ROWS = 6
TABLE_STREAM_LIST_MAX_COLS = 3
TABLE_STREAM_LIST_MAX_AVG_WORDS = 2.2
TABLE_STREAM_LIST_MAX_NUMERIC_RATIO = 0.08
TABLE_STREAM_LIST_MAX_AREA_FRAC = 0.12
TABLE_STREAM_PANEL_MIN_AREA_FRAC = 0.25
TABLE_STREAM_PANEL_MIN_ROWS = 8
TABLE_STREAM_PANEL_MAX_COLS = 4
TABLE_STREAM_PANEL_MAX_AVG_WORDS = 2.6
TABLE_STREAM_PANEL_MAX_NUMERIC_RATIO = 0.08
TABLE_STREAM_SPARSE_MIN_AREA = 0.6
TABLE_STREAM_SPARSE_MAX_LINES = 15
TABLE_STREAM_SPARSE_MIN_AVG_LINE_LEN = 55
TABLE_STREAM_SPARSE_MAX_NUMERIC_RATIO = 0.05
TABLE_STREAM_SPARSE_MAX_COLS = 5
INFO_HEADING_MIN_WORDS = 3
INFO_HEADING_MIN_ALPHA_RATIO = 0.55
INFO_HEADING_MIN_SIZE = 12.0
INFO_HEADING_SIZE_DELTA = 2.0
INFO_HEADING_MAX_WORDS = 30
INFO_HEADING_MAX_CHARS = 160
INFO_HEADING_MAX_SENTENCES = 2
INFO_HEADING_MERGE_GAP_FRAC = 0.012
INFO_HEADING_MERGE_SIZE_DELTA = 2.0
INFO_HEADING_MERGE_H_OVERLAP = 0.4
INFO_CHART_MIN_DRAWINGS = 5
INFO_CHART_MIN_AREA_FRAC = 0.04
INFO_CHART_BAND_FRAC = 0.6
INFO_CHART_MAX_GAP_FRAC = 0.25
INFO_CHART_CLUSTER_GAP_FRAC = 0.05
INFO_CHART_MAX_ASPECT = 4.0
TABLE_EXPAND_MAX_GAP_FRAC = 0.12
TABLE_EXPAND_LATTICE_MAX_GAP_FRAC = 0.08
TABLE_EXPAND_MAX_BLOCK_HEIGHT_FRAC = 0.4
TABLE_EXPAND_MAX_LINES = 4
TABLE_EXPAND_MAX_AVG_LINE_LEN = 60
TABLE_EXPAND_HEADING_MAX_LINES = 2
TABLE_EXPAND_HEADING_MAX_AVG_LINE_LEN = 120
TABLE_EXPAND_HEADING_MIN_ALPHA_RATIO = 0.55
TABLE_EXPAND_HEADING_MAX_SENTENCES = 2
TABLE_EXPAND_MIN_H_OVERLAP = 0.2
TABLE_EXPAND_MIN_V_OVERLAP = 0.2
TABLE_EXPAND_STREAM_WIDE_MIN_WIDTH_FRAC = 0.85
TABLE_EXPAND_STREAM_WIDE_MIN_HEIGHT_FRAC = 0.4
TEXT_BLOCK_MIN_LINES = 8
TEXT_BLOCK_MIN_AVG_LINE_LEN = 35
TEXT_BLOCK_MIN_AREA_FRAC = 0.55
TEXT_BLOCK_MAX_NUMERIC_RATIO = 0.07
TEXT_BLOCK_LOOSE_MIN_LINES = 18
TEXT_BLOCK_LOOSE_MIN_AVG_LINE_LEN = 24
TEXT_BLOCK_LOOSE_MAX_NUMERIC_RATIO = 0.05
_PAGE_NUMBER_RX = re.compile(r"^\s*[^0-9]*\d{1,4}(?:\s*[-–]\s*\d{1,4})?\s*$")


@dataclass(frozen=True)
class _TableCandidate:
    bbox: Tuple[float, float, float, float]
    method: str
    row_count: int
    col_count: int
    col_consistency: float
    row_len_cv: float
    non_empty_cells: int
    total_cells: int
    numeric_cells: int
    numeric_ratio: float
    avg_words_per_cell: float
    avg_first_col_words: float
    index_page_ratio: float
    preview: str
    text: str
    text_len: int
    line_count: int
    avg_line_len: float
    text_block_area_frac: float
    text_block_line_count: int
    text_block_avg_line_len: float
    caption_hint: bool
    area_frac: float
    width_frac: float
    height_frac: float
    aspect: float


@dataclass(frozen=True)
class _ChartRect:
    rect: fitz.Rect
    kind: str
    xref: Optional[int] = None
    caption: Optional[str] = None
    caption_rect: Optional[fitz.Rect] = None


def _s(value: object) -> str:
    if value is None:
        return ""
    try:
        return str(value)
    except Exception:
        return ""


def _rect_iou(a: fitz.Rect, b: fitz.Rect) -> float:
    inter = a & b
    if inter.is_empty:
        return 0.0
    inter_area = inter.get_area()
    if inter_area <= 0.0:
        return 0.0
    union = a.get_area() + b.get_area() - inter_area
    if union <= 0.0:
        return 0.0
    return inter_area / union


def _rect_containment_ratio(a: fitz.Rect, b: fitz.Rect) -> float:
    inter = a & b
    if inter.is_empty:
        return 0.0
    inter_area = inter.get_area()
    if inter_area <= 0.0:
        return 0.0
    denom = min(a.get_area(), b.get_area())
    if denom <= 0.0:
        return 0.0
    return inter_area / denom


def _rect_seen(rect: fitz.Rect, seen: List[fitz.Rect]) -> bool:
    for existing in seen:
        if _rect_iou(rect, existing) >= CHART_DEDUP_IOU:
            return True
    return False


def _chart_candidate_score(
    area_frac: float,
    has_hint: bool,
    caption: str,
    note_included: bool,
) -> float:
    score = area_frac
    if has_hint:
        score += 0.2
    if caption:
        score += min(0.2, len(caption) / 200.0)
    if note_included:
        score += 0.1
    return score


def _find_overlapping_kept(
    rect: fitz.Rect,
    kept: List[Tuple[fitz.Rect, float, int]],
) -> Optional[int]:
    for idx, (existing, _score, _out_idx) in enumerate(kept):
        if _rect_iou(rect, existing) >= CHART_OVERLAP_IOU:
            return idx
        if _rect_containment_ratio(rect, existing) >= CHART_OVERLAP_CONTAINMENT:
            return idx
        if _rect_containment_ratio(existing, rect) >= CHART_OVERLAP_CONTAINMENT:
            return idx
    return None


def _image_block_rects(page: fitz.Page) -> List[fitz.Rect]:
    try:
        text_dict = page.get_text("dict")
    except Exception:
        return []
    blocks = text_dict.get("blocks") or []
    rects: List[fitz.Rect] = []
    for block in blocks:
        if block.get("type") != 1:
            continue
        bbox = block.get("bbox")
        if not bbox or len(bbox) != 4:
            continue
        try:
            rects.append(fitz.Rect(*bbox))
        except Exception:
            continue
    return rects


def _collect_chart_rects(page: fitz.Page) -> List[_ChartRect]:
    rects: List[_ChartRect] = []
    for xref, *_ in page.get_images(full=True):
        try:
            image_rects = page.get_image_rects(xref)
        except Exception:
            image_rects = []
        if not image_rects:
            continue
        rects.append(_ChartRect(rect=image_rects[0], kind="xref", xref=xref))
    for rect in _image_block_rects(page):
        rects.append(_ChartRect(rect=rect, kind="block", xref=None))
    for rect, caption, cap_rect in _drawing_caption_rects(page):
        rects.append(_ChartRect(rect=rect, kind="draw", xref=None, caption=caption, caption_rect=cap_rect))
    for rect, caption, cap_rect in _heading_chart_rects(page):
        rects.append(_ChartRect(rect=rect, kind="heading", xref=None, caption=caption, caption_rect=cap_rect))
    return rects


def _drawing_rects(page: fitz.Page) -> List[fitz.Rect]:
    try:
        drawings = page.get_drawings()
    except Exception:
        return []
    page_area = max(1.0, page.rect.get_area())
    rects: List[fitz.Rect] = []
    for drawing in drawings:
        rect = drawing.get("rect")
        if rect is None:
            continue
        try:
            r = fitz.Rect(rect)
        except Exception:
            continue
        if r.width < DRAWING_MIN_RECT_DIM and r.height < DRAWING_MIN_RECT_DIM:
            continue
        if r.get_area() < DRAWING_MIN_RECT_AREA:
            continue
        area_frac = r.get_area() / page_area
        if area_frac >= DRAWING_BACKGROUND_MIN_AREA_FRAC:
            fill = drawing.get("fill")
            width = drawing.get("width")
            if fill is not None and (width is None or float(width) <= DRAWING_BACKGROUND_MAX_STROKE):
                continue
        rects.append(r)
    return rects


def _drawing_caption_rects(page: fitz.Page) -> List[Tuple[fitz.Rect, str, fitz.Rect]]:
    captions = _caption_blocks(page, CHART_CAPTION_HINTS)
    if not captions:
        return []
    drawings = _drawing_rects(page)
    if not drawings:
        return []
    page_rect = page.rect
    bottom_limit = page_rect.y1 - page_rect.height * 0.1
    candidates: List[Tuple[fitz.Rect, str, fitz.Rect]] = []
    for cap_rect, cap_text in captions:
        band_top = cap_rect.y1 - 2
        band_bot = min(bottom_limit, cap_rect.y1 + page_rect.height * 0.55)
        if band_bot <= band_top:
            continue
        band = fitz.Rect(page_rect.x0, band_top, page_rect.x1, band_bot)
        selected = []
        for r in drawings:
            if not r.intersects(band):
                continue
            if r.y0 < cap_rect.y0 - 4:
                continue
            if r.y1 <= cap_rect.y1:
                continue
            if _horizontal_overlap_ratio(r, cap_rect) < 0.25:
                continue
            selected.append(r)
        if not selected:
            continue
        merged = selected[0]
        for r in selected[1:]:
            merged |= r
        if merged.width / max(1.0, page_rect.width) < 0.6:
            expanded = list(selected)
            for r in drawings:
                if not r.intersects(band):
                    continue
                if _vertical_overlap_ratio(r, merged) < 0.3:
                    continue
                expanded.append(r)
            merged = expanded[0]
            for r in expanded[1:]:
                merged |= r
        merged |= cap_rect
        merged = _pad_rect(merged, page_rect)
        merged = _clamp_top_to_caption(merged, cap_rect, page, page_rect)
        merged = _extend_with_note_blocks(page, merged)
        if merged.get_area() <= 0:
            continue
        candidates.append((merged, cap_text, cap_rect))
    deduped: List[Tuple[fitz.Rect, str, fitz.Rect]] = []
    for rect, cap_text, cap_rect in candidates:
        if not _rect_seen(rect, [r for r, _, _ in deduped]):
            deduped.append((rect, cap_text, cap_rect))
    return deduped


def _caption_blocks(page: fitz.Page, hints: Tuple[str, ...]) -> List[Tuple[fitz.Rect, str]]:
    rects: List[Tuple[fitz.Rect, str]] = []
    try:
        blocks = page.get_text("blocks")
    except Exception:
        return rects
    for x0, y0, x1, y1, text, *_ in blocks:
        if not text:
            continue
        lines = [line.strip().lower() for line in str(text).splitlines() if line.strip()]
        if any(any(line.startswith(hint) for hint in hints) for line in lines):
            first_line = next((line for line in lines if line), "")
            rects.append((fitz.Rect(x0, y0, x1, y1), first_line))
    return rects


def _alpha_ratio(text: str) -> float:
    if not text:
        return 0.0
    alpha = sum(1 for ch in text if ch.isalpha())
    total = len(text)
    return alpha / total if total else 0.0


def _is_page_number_text(text: str) -> bool:
    if not text:
        return False
    cleaned = text.strip()
    if not _PAGE_NUMBER_RX.match(cleaned):
        return False
    return _alpha_ratio(cleaned) <= 0.3


def _heading_lines(page: fitz.Page) -> List[Tuple[fitz.Rect, str]]:
    try:
        data = page.get_text("dict")
    except Exception:
        return []
    sizes = []
    lines_data = []
    for block in data.get("blocks", []):
        block_lines: List[Tuple[fitz.Rect, str, float]] = []
        block_chars = 0
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            if not spans:
                continue
            text = "".join(span.get("text", "") for span in spans).strip()
            if not text:
                continue
            size_vals = [float(span.get("size", 0.0)) for span in spans if span.get("text")]
            size = sum(size_vals) / max(1, len(size_vals))
            bbox = line.get("bbox")
            if bbox and len(bbox) == 4:
                block_lines.append((fitz.Rect(*bbox), text, size))
            if _alpha_ratio(text) >= INFO_HEADING_MIN_ALPHA_RATIO:
                sizes.append(size)
            block_chars += len(text)
        if not block_lines:
            continue
        block_line_count = len(block_lines)
        avg_block_line_len = block_chars / max(1, block_line_count)
        if (
            block_line_count >= CHART_LABEL_PARAGRAPH_MIN_LINES
            and avg_block_line_len > CHART_LABEL_PARAGRAPH_MAX_AVG_LINE_LEN
        ):
            continue
        lines_data.extend(block_lines)
    if not sizes:
        return []
    try:
        median_size = statistics.median(sizes)
    except Exception:
        median_size = 0.0
    min_size = max(INFO_HEADING_MIN_SIZE, median_size + INFO_HEADING_SIZE_DELTA)
    headings: List[Tuple[fitz.Rect, str, float]] = []
    for rect, text, size in lines_data:
        if size < min_size:
            continue
        if _alpha_ratio(text) < INFO_HEADING_MIN_ALPHA_RATIO:
            continue
        if len(text.split()) < INFO_HEADING_MIN_WORDS:
            continue
        if len(text) > INFO_HEADING_MAX_CHARS:
            continue
        if len(text.split()) > INFO_HEADING_MAX_WORDS:
            continue
        sentence_marks = text.count(".") + text.count("!") + text.count("?")
        if sentence_marks > INFO_HEADING_MAX_SENTENCES:
            continue
        lowered = text.lower()
        if any(hint in lowered for hint in TABLE_CAPTION_HINTS):
            continue
        headings.append((rect, text, size))
    if not headings:
        return []
    headings_sorted = sorted(headings, key=lambda item: (item[0].y0, item[0].x0))
    gap_thresh = max(page.rect.height * INFO_HEADING_MERGE_GAP_FRAC, 2.0)
    merged: List[Tuple[fitz.Rect, str, float]] = []
    for rect, text, size in headings_sorted:
        if merged:
            last_rect, last_text, last_size = merged[-1]
            if (
                abs(size - last_size) <= INFO_HEADING_MERGE_SIZE_DELTA
                and _horizontal_overlap_ratio(rect, last_rect) >= INFO_HEADING_MERGE_H_OVERLAP
                and rect.y0 - last_rect.y1 <= gap_thresh
            ):
                merged[-1] = (last_rect | rect, f"{last_text} {text}".strip(), max(last_size, size))
                continue
        merged.append((rect, text, size))
    return [(rect, text) for rect, text, _ in merged]


def _cluster_rects_by_y(rects: List[fitz.Rect], gap: float) -> List[List[fitz.Rect]]:
    if not rects:
        return []
    rects_sorted = sorted(rects, key=lambda r: r.y0)
    clusters: List[List[fitz.Rect]] = []
    current = [rects_sorted[0]]
    current_bottom = rects_sorted[0].y1
    for r in rects_sorted[1:]:
        if r.y0 - current_bottom <= gap:
            current.append(r)
            current_bottom = max(current_bottom, r.y1)
        else:
            clusters.append(current)
            current = [r]
            current_bottom = r.y1
    clusters.append(current)
    return clusters


def _has_intervening_paragraph(
    page: fitz.Page,
    head_rect: fitz.Rect,
    chart_rect: fitz.Rect,
) -> bool:
    if chart_rect.y0 <= head_rect.y1:
        return False
    try:
        blocks = page.get_text("blocks")
    except Exception:
        return False
    for x0, y0, x1, y1, text, *_ in blocks:
        if not text:
            continue
        block = fitz.Rect(x0, y0, x1, y1)
        if block.y0 < head_rect.y1 or block.y1 > chart_rect.y0:
            continue
        if _horizontal_overlap_ratio(block, chart_rect) < CHART_HEADING_TOP_BLOCK_H_OVERLAP:
            continue
        lines, chars = _text_stats(str(text))
        if lines == 0:
            continue
        avg_line_len = chars / max(1, lines)
        if lines >= CHART_LABEL_PARAGRAPH_MIN_LINES and avg_line_len > CHART_LABEL_PARAGRAPH_MAX_AVG_LINE_LEN:
            return True
    return False


def _heading_chart_rects(page: fitz.Page) -> List[Tuple[fitz.Rect, str, fitz.Rect]]:
    headings = _heading_lines(page)
    if not headings:
        return []
    drawings = _drawing_rects(page)
    if not drawings:
        return []
    page_rect = page.rect
    max_gap = page_rect.height * INFO_CHART_MAX_GAP_FRAC
    band_height = page_rect.height * INFO_CHART_BAND_FRAC
    cluster_gap = page_rect.height * INFO_CHART_CLUSTER_GAP_FRAC
    candidates: List[Tuple[fitz.Rect, str, fitz.Rect]] = []
    for head_rect, head_text in headings:
        band = fitz.Rect(page_rect.x0, head_rect.y1, page_rect.x1, min(page_rect.y1, head_rect.y1 + band_height))
        selected = [r for r in drawings if r.intersects(band) and r.y0 >= head_rect.y1 - 2]
        if len(selected) < INFO_CHART_MIN_DRAWINGS:
            continue
        clusters = _cluster_rects_by_y(selected, cluster_gap)
        if not clusters:
            continue
        primary = max(clusters, key=lambda cluster: sum(r.get_area() for r in cluster))
        if len(primary) < INFO_CHART_MIN_DRAWINGS:
            continue
        merged = primary[0]
        for r in primary[1:]:
            merged |= r
        if merged.get_area() / max(1.0, page_rect.get_area()) < INFO_CHART_MIN_AREA_FRAC:
            continue
        gap = merged.y0 - head_rect.y1
        if gap > max_gap:
            continue
        if _has_intervening_paragraph(page, head_rect, merged):
            continue
        merged |= head_rect
        merged = _pad_rect(merged, page_rect)
        merged = _clamp_top_to_caption(merged, head_rect, page, page_rect)
        candidates.append((merged, head_text, head_rect))
    deduped: List[Tuple[fitz.Rect, str, fitz.Rect]] = []
    for rect, text, head_rect in candidates:
        if not _rect_seen(rect, [r for r, _, _ in deduped]):
            deduped.append((rect, text, head_rect))
    return deduped


def _nearest_caption_block(
    page: fitz.Page,
    rect: fitz.Rect,
    hints: Tuple[str, ...],
    max_dist: float = 180.0,
) -> Tuple[Optional[fitz.Rect], str]:
    candidates = _caption_blocks(page, hints)
    if not candidates:
        return None, ""
    best_penalty = 2
    best_dist = 1e9
    best_rect: Optional[fitz.Rect] = None
    best_text = ""
    for cap_rect, cap_text in candidates:
        if _horizontal_overlap_ratio(cap_rect, rect) < 0.3:
            continue
        if cap_rect.y1 <= rect.y0:
            dist = rect.y0 - cap_rect.y1
            penalty = 0
        elif cap_rect.y0 >= rect.y1:
            dist = cap_rect.y0 - rect.y1
            penalty = 1
        else:
            dist = 0.0
            penalty = 0
        if dist > max_dist:
            continue
        if (penalty, dist) < (best_penalty, best_dist):
            best_penalty = penalty
            best_dist = dist
            best_rect = cap_rect
            best_text = cap_text
    if best_rect is None:
        return None, ""
    return best_rect, best_text


def _horizontal_overlap_ratio(a: fitz.Rect, b: fitz.Rect) -> float:
    left = max(a.x0, b.x0)
    right = min(a.x1, b.x1)
    overlap = max(0.0, right - left)
    if overlap <= 0.0:
        return 0.0
    denom = min(a.width, b.width)
    if denom <= 0.0:
        return 0.0
    return overlap / denom


def _vertical_overlap_ratio(a: fitz.Rect, b: fitz.Rect) -> float:
    top = max(a.y0, b.y0)
    bot = min(a.y1, b.y1)
    overlap = max(0.0, bot - top)
    if overlap <= 0.0:
        return 0.0
    denom = min(a.height, b.height)
    if denom <= 0.0:
        return 0.0
    return overlap / denom


def _pad_rect(rect: fitz.Rect, page_rect: fitz.Rect) -> fitz.Rect:
    pad_x = max(page_rect.width * CHART_PAD_X_FRAC, 2.0)
    pad_y = max(page_rect.height * CHART_PAD_Y_FRAC, 2.0)
    x0 = max(page_rect.x0, rect.x0 - pad_x)
    y0 = max(page_rect.y0, rect.y0 - pad_y)
    x1 = min(page_rect.x1, rect.x1 + pad_x)
    y1 = min(page_rect.y1, rect.y1 + pad_y)
    return fitz.Rect(x0, y0, x1, y1)


def _clamp_top_to_caption(
    rect: fitz.Rect,
    cap_rect: fitz.Rect,
    page: fitz.Page,
    page_rect: fitz.Rect,
) -> fitz.Rect:
    pad = max(CHART_CAPTION_TOP_PAD_PX, cap_rect.height * CHART_CAPTION_TOP_PAD_FRAC, 0.0)
    target_top = max(page_rect.y0, cap_rect.y0 - pad)
    block_limit = _caption_top_block_limit(page, cap_rect, page_rect)
    if block_limit is not None:
        target_top = max(target_top, block_limit)
    if rect.y0 != target_top:
        return fitz.Rect(rect.x0, target_top, rect.x1, rect.y1)
    return rect


def _clamp_top_to_heading(
    rect: fitz.Rect,
    head_rect: fitz.Rect,
    page: fitz.Page,
    page_rect: fitz.Rect,
) -> fitz.Rect:
    if _has_internal_top_text(page, rect, head_rect):
        return rect
    max_pad = max(page_rect.height * CHART_HEADING_TOP_MAX_PAD_FRAC, 0.0)
    min_top = max(page_rect.y0, head_rect.y0 - max_pad)
    block_limit = _heading_top_block_limit(page, head_rect, page_rect)
    if block_limit is not None:
        min_top = max(min_top, block_limit)
    if rect.y0 < min_top:
        return fitz.Rect(rect.x0, min_top, rect.x1, rect.y1)
    return rect


def _heading_top_block_limit(
    page: fitz.Page,
    head_rect: fitz.Rect,
    page_rect: fitz.Rect,
) -> Optional[float]:
    search = page_rect.height * CHART_HEADING_TOP_SEARCH_FRAC
    guard = max(page_rect.height * CHART_HEADING_TOP_GUARD_FRAC, 2.0)
    best_y1 = None
    try:
        blocks = page.get_text("blocks")
    except Exception:
        return None
    for x0, y0, x1, y1, text, *_ in blocks:
        if not text:
            continue
        if _is_page_number_text(text):
            continue
        block = fitz.Rect(x0, y0, x1, y1)
        if block.y1 > head_rect.y0:
            continue
        if head_rect.y0 - block.y1 > search:
            continue
        if _horizontal_overlap_ratio(block, head_rect) < CHART_HEADING_TOP_BLOCK_H_OVERLAP:
            continue
        if best_y1 is None or block.y1 > best_y1:
            best_y1 = block.y1
    if best_y1 is None:
        return None
    return min(page_rect.y1, best_y1 + guard)


def _caption_top_block_limit(
    page: fitz.Page,
    cap_rect: fitz.Rect,
    page_rect: fitz.Rect,
) -> Optional[float]:
    search = page_rect.height * CHART_CAPTION_TOP_SEARCH_FRAC
    guard = max(page_rect.height * CHART_CAPTION_TOP_GUARD_FRAC, 2.0)
    best_y1 = None
    try:
        blocks = page.get_text("blocks")
    except Exception:
        return None
    for x0, y0, x1, y1, text, *_ in blocks:
        if not text:
            continue
        if _is_page_number_text(text):
            continue
        block = fitz.Rect(x0, y0, x1, y1)
        if block.y1 > cap_rect.y0:
            continue
        if cap_rect.y0 - block.y1 > search:
            continue
        if _horizontal_overlap_ratio(block, cap_rect) < CHART_CAPTION_TOP_BLOCK_H_OVERLAP:
            continue
        if best_y1 is None or block.y1 > best_y1:
            best_y1 = block.y1
    if best_y1 is None:
        return None
    return min(page_rect.y1, best_y1 + guard)


def _extend_with_note_blocks(page: fitz.Page, rect: fitz.Rect) -> fitz.Rect:
    page_rect = page.rect
    limit = min(page_rect.y1, rect.y1 + CHART_NOTE_MAX_DIST)
    max_gap_x = page_rect.width * CHART_NOTE_MAX_GAP_X_FRAC
    expanded = rect
    try:
        blocks = page.get_text("blocks")
    except Exception:
        return rect
    for x0, y0, x1, y1, text, *_ in blocks:
        if y0 < rect.y1 - 2 or y0 > limit:
            continue
        lines = [line.strip() for line in str(text).splitlines() if line.strip()]
        if not lines:
            continue
        first = lines[0].lower()
        if not (first.startswith("note:") or first.startswith("source:") or first.startswith("statlink")):
            continue
        block = fitz.Rect(x0, y0, x1, y1)
        h_overlap = _horizontal_overlap_ratio(block, rect)
        gap_ok = (
            (block.x0 >= rect.x1 and block.x0 - rect.x1 <= max_gap_x)
            or (block.x1 <= rect.x0 and rect.x0 - block.x1 <= max_gap_x)
        )
        if h_overlap < 0.3 and not gap_ok:
            continue
        expanded |= block
    return expanded


def _extend_with_adjacent_text_blocks(page: fitz.Page, rect: fitz.Rect) -> fitz.Rect:
    page_rect = page.rect
    max_gap = page_rect.width * CHART_LABEL_MAX_GAP_FRAC
    max_v_gap = page_rect.height * CHART_LABEL_MAX_V_GAP_FRAC
    expanded = rect
    try:
        blocks = page.get_text("blocks")
    except Exception:
        return rect
    for x0, y0, x1, y1, text, *_ in blocks:
        if not text:
            continue
        block = fitz.Rect(x0, y0, x1, y1)
        if block.height > rect.height * CHART_LABEL_MAX_HEIGHT_FRAC:
            continue
        lines, chars = _text_stats(str(text))
        if lines == 0:
            continue
        avg_line_len = chars / max(1, lines)
        if lines >= CHART_LABEL_PARAGRAPH_MIN_LINES and avg_line_len > CHART_LABEL_PARAGRAPH_MAX_AVG_LINE_LEN:
            continue
        if lines > CHART_LABEL_MAX_LINES:
            continue
        if avg_line_len > CHART_LABEL_MAX_AVG_LINE_LEN:
            continue
        v_overlap = _vertical_overlap_ratio(block, rect)
        h_overlap = _horizontal_overlap_ratio(block, rect)
        if v_overlap >= CHART_LABEL_MIN_V_OVERLAP:
            if block.x0 >= rect.x1 and block.x0 - rect.x1 <= max_gap:
                expanded |= block
            elif block.x1 <= rect.x0 and rect.x0 - block.x1 <= max_gap:
                expanded |= block
            elif block.x1 > rect.x1 and block.x1 - rect.x1 <= max_gap:
                expanded |= block
            elif block.x0 < rect.x0 and rect.x0 - block.x0 <= max_gap:
                expanded |= block
        if h_overlap >= CHART_LABEL_MIN_H_OVERLAP:
            if block.y1 <= rect.y0 and rect.y0 - block.y1 <= max_v_gap:
                expanded |= block
            elif block.y0 >= rect.y1 and block.y0 - rect.y1 <= max_v_gap:
                expanded |= block
            elif block.y0 < rect.y0 and rect.y0 - block.y0 <= max_v_gap:
                expanded |= block
            elif block.y1 > rect.y1 and block.y1 - rect.y1 <= max_v_gap:
                expanded |= block
    return expanded


def _has_internal_top_text(
    page: fitz.Page,
    rect: fitz.Rect,
    head_rect: fitz.Rect,
) -> bool:
    search = page.rect.height * CHART_HEADING_TOP_SEARCH_FRAC
    try:
        blocks = page.get_text("blocks")
    except Exception:
        return False
    for x0, y0, x1, y1, text, *_ in blocks:
        if not text:
            continue
        if _is_page_number_text(text):
            continue
        block = fitz.Rect(x0, y0, x1, y1)
        if not block.intersects(rect):
            continue
        if block.y0 >= head_rect.y0:
            continue
        if head_rect.y0 - block.y1 > search:
            continue
        if _horizontal_overlap_ratio(block, rect) < CHART_HEADING_TOP_BLOCK_H_OVERLAP:
            continue
        lines, chars = _text_stats(str(text))
        if lines == 0:
            continue
        avg_line_len = chars / max(1, lines)
        if lines >= CHART_LABEL_PARAGRAPH_MIN_LINES and avg_line_len > CHART_LABEL_PARAGRAPH_MAX_AVG_LINE_LEN:
            continue
        return True
    return False


def _extend_with_heading_above(page: fitz.Page, rect: fitz.Rect) -> fitz.Rect:
    head_rect = _nearest_heading_above(page, rect)
    if head_rect is None:
        return rect
    return rect | head_rect


def _adjust_rect_for_text_margins(
    page: fitz.Page,
    rect: fitz.Rect,
    gap_scale: float = 1.0,
    gap_scale_x: float = 1.0,
) -> fitz.Rect:
    page_rect = page.rect
    min_gap = page_rect.height * CHART_EDGE_TEXT_MIN_GAP_FRAC * gap_scale
    max_pad = page_rect.height * CHART_EDGE_TEXT_MAX_PAD_FRAC
    min_gap_x = page_rect.width * CHART_EDGE_TEXT_MIN_GAP_X_FRAC * gap_scale_x
    max_pad_x = page_rect.width * CHART_EDGE_TEXT_MAX_PAD_X_FRAC
    top_text = None
    bottom_text = None
    left_text = None
    right_text = None
    try:
        blocks = page.get_text("blocks")
    except Exception:
        return rect
    for x0, y0, x1, y1, text, *_ in blocks:
        if not text:
            continue
        block = fitz.Rect(x0, y0, x1, y1)
        if _rect_intersection_area(block, rect) <= 0.0:
            continue
        top_text = y0 if top_text is None else min(top_text, y0)
        bottom_text = y1 if bottom_text is None else max(bottom_text, y1)
        left_text = x0 if left_text is None else min(left_text, x0)
        right_text = x1 if right_text is None else max(right_text, x1)
    if top_text is not None:
        gap = top_text - rect.y0
        if gap < min_gap:
            pad = min(max_pad, min_gap - gap)
            rect = fitz.Rect(rect.x0, max(page_rect.y0, rect.y0 - pad), rect.x1, rect.y1)
    if bottom_text is not None:
        gap = rect.y1 - bottom_text
        if gap < min_gap:
            pad = min(max_pad, min_gap - gap)
            rect = fitz.Rect(rect.x0, rect.y0, rect.x1, min(page_rect.y1, rect.y1 + pad))
    if left_text is not None:
        gap = left_text - rect.x0
        if gap < min_gap_x:
            pad = min(max_pad_x, min_gap_x - gap)
            rect = fitz.Rect(max(page_rect.x0, rect.x0 - pad), rect.y0, rect.x1, rect.y1)
    if right_text is not None:
        gap = rect.x1 - right_text
        if gap < min_gap_x:
            pad = min(max_pad_x, min_gap_x - gap)
            rect = fitz.Rect(rect.x0, rect.y0, min(page_rect.x1, rect.x1 + pad), rect.y1)
    return rect


def _expand_rect_into_whitespace(
    page: fitz.Page,
    rect: fitz.Rect,
    allow_top: bool = True,
    allow_bottom: bool = True,
    allow_left: bool = True,
    allow_right: bool = True,
) -> fitz.Rect:
    page_rect = page.rect
    guard_y = page_rect.height * CHART_WHITESPACE_GUARD_GAP_FRAC
    guard_x = page_rect.width * CHART_WHITESPACE_GUARD_GAP_X_FRAC
    max_pad_y = page_rect.height * CHART_WHITESPACE_MAX_PAD_FRAC
    max_pad_x = page_rect.width * CHART_WHITESPACE_MAX_PAD_X_FRAC
    top_dist = None
    bottom_dist = None
    left_dist = None
    right_dist = None

    blockers: List[fitz.Rect] = []
    try:
        for x0, y0, x1, y1, text, *_ in page.get_text("blocks"):
            if not text:
                continue
            blockers.append(fitz.Rect(x0, y0, x1, y1))
    except Exception:
        blockers = []

    blockers.extend(_drawing_rects(page))
    blockers.extend(_image_block_rects(page))

    for block in blockers:
        if _rect_intersection_area(block, rect) > 0.0:
            continue
        if _horizontal_overlap_ratio(block, rect) >= CHART_WHITESPACE_MIN_OVERLAP:
            if block.y1 <= rect.y0:
                dist = rect.y0 - block.y1
                top_dist = dist if top_dist is None else min(top_dist, dist)
            elif block.y0 >= rect.y1:
                dist = block.y0 - rect.y1
                bottom_dist = dist if bottom_dist is None else min(bottom_dist, dist)
        if _vertical_overlap_ratio(block, rect) >= CHART_WHITESPACE_MIN_OVERLAP:
            if block.x1 <= rect.x0:
                dist = rect.x0 - block.x1
                left_dist = dist if left_dist is None else min(left_dist, dist)
            elif block.x0 >= rect.x1:
                dist = block.x0 - rect.x1
                right_dist = dist if right_dist is None else min(right_dist, dist)

    top_limit = rect.y0 - page_rect.y0
    if top_dist is None:
        top_pad = min(max_pad_y, top_limit)
    else:
        top_pad = min(max_pad_y, max(0.0, top_dist - guard_y))
    bottom_limit = page_rect.y1 - rect.y1
    if bottom_dist is None:
        bottom_pad = min(max_pad_y, bottom_limit)
    else:
        bottom_pad = min(max_pad_y, max(0.0, bottom_dist - guard_y))
    left_limit = rect.x0 - page_rect.x0
    if left_dist is None:
        left_pad = min(max_pad_x, left_limit)
    else:
        left_pad = min(max_pad_x, max(0.0, left_dist - guard_x))
    right_limit = page_rect.x1 - rect.x1
    if right_dist is None:
        right_pad = min(max_pad_x, right_limit)
    else:
        right_pad = min(max_pad_x, max(0.0, right_dist - guard_x))

    if not allow_top:
        top_pad = 0.0
    if not allow_bottom:
        bottom_pad = 0.0
    if not allow_left:
        left_pad = 0.0
    if not allow_right:
        right_pad = 0.0

    return fitz.Rect(
        max(page_rect.x0, rect.x0 - left_pad),
        max(page_rect.y0, rect.y0 - top_pad),
        min(page_rect.x1, rect.x1 + right_pad),
        min(page_rect.y1, rect.y1 + bottom_pad),
    )


def _caption_near_top(rect: fitz.Rect, cap_rect: fitz.Rect, frac: float = 0.35) -> bool:
    if rect.height <= 0:
        return False
    return cap_rect.y0 <= rect.y0 + rect.height * frac


def _merge_caption_above(
    rect: fitz.Rect,
    cap_rect: fitz.Rect,
    page_rect: fitz.Rect,
) -> fitz.Rect:
    max_gap = page_rect.height * CHART_CAPTION_MERGE_MAX_GAP_FRAC
    if cap_rect.y1 <= rect.y0 and rect.y0 - cap_rect.y1 <= max_gap:
        return rect | cap_rect
    if cap_rect.y0 < rect.y0 and cap_rect.y1 > rect.y0:
        return rect | cap_rect
    return rect


def _nearest_heading_above(page: fitz.Page, rect: fitz.Rect) -> Optional[fitz.Rect]:
    headings = _heading_lines(page)
    if not headings:
        return None
    page_rect = page.rect
    max_gap = page_rect.height * CHART_HEADING_MERGE_MAX_GAP_FRAC
    best_rect: Optional[fitz.Rect] = None
    best_dist = 1e9
    for head_rect, _ in headings:
        if _horizontal_overlap_ratio(head_rect, rect) < CHART_HEADING_TOP_BLOCK_H_OVERLAP:
            continue
        if head_rect.y1 <= rect.y0:
            if rect.y0 - head_rect.y1 <= max_gap:
                if _has_intervening_paragraph(page, head_rect, rect):
                    continue
                dist = rect.y0 - head_rect.y1
                if dist < best_dist:
                    best_rect = head_rect
                    best_dist = dist
            continue
        if head_rect.intersects(rect) and head_rect.y0 <= rect.y0 + rect.height * 0.4:
            if 0.0 < best_dist:
                best_rect = head_rect
                best_dist = 0.0
    return best_rect


def _note_block_bottom(page: fitz.Page, rect: fitz.Rect) -> Optional[float]:
    min_y0 = rect.y0 + rect.height * 0.45
    best: Optional[float] = None
    page_rect = page.rect
    max_gap_x = page_rect.width * CHART_NOTE_MAX_GAP_X_FRAC
    try:
        blocks = page.get_text("blocks")
    except Exception:
        return None
    for x0, y0, x1, y1, text, *_ in blocks:
        if y0 < min_y0 or y1 > rect.y1 + 2:
            continue
        lines = [line.strip() for line in str(text).splitlines() if line.strip()]
        if not lines:
            continue
        first = lines[0].lower()
        if not (first.startswith("note:") or first.startswith("source:") or first.startswith("statlink")):
            continue
        block = fitz.Rect(x0, y0, x1, y1)
        h_overlap = _horizontal_overlap_ratio(block, rect)
        gap_ok = (
            (block.x0 >= rect.x1 and block.x0 - rect.x1 <= max_gap_x)
            or (block.x1 <= rect.x0 and rect.x0 - block.x1 <= max_gap_x)
        )
        if h_overlap < 0.3 and not gap_ok:
            continue
        if best is None or y1 > best:
            best = y1
    return best


def _next_block_top_below(
    page: fitz.Page,
    rect: fitz.Rect,
    min_y: float,
    max_y: float,
) -> Optional[float]:
    best: Optional[float] = None
    blocks: List[fitz.Rect] = []
    try:
        for x0, y0, x1, y1, text, *_ in page.get_text("blocks"):
            if not text:
                continue
            blocks.append(fitz.Rect(x0, y0, x1, y1))
    except Exception:
        blocks = []
    blocks.extend(_drawing_rects(page))
    blocks.extend(_image_block_rects(page))
    for block in blocks:
        if block.y0 < min_y or block.y0 > max_y:
            continue
        if _horizontal_overlap_ratio(block, rect) < CHART_NOTE_BELOW_MIN_H_OVERLAP:
            continue
        if best is None or block.y0 < best:
            best = block.y0
    return best


def _clamp_bottom_to_note(
    page: fitz.Page,
    rect: fitz.Rect,
    note_bottom: float,
    page_rect: fitz.Rect,
) -> fitz.Rect:
    max_bottom = min(
        page_rect.y1,
        note_bottom - CHART_CROP_PAD_COMPENSATION + CHART_NOTE_PAD_EXTRA,
    )
    blocker_top = _next_block_top_below(
        page,
        rect,
        note_bottom + 1,
        max_bottom + CHART_NOTE_BELOW_GUARD_PX,
    )
    if blocker_top is not None:
        max_bottom = min(max_bottom, blocker_top - CHART_NOTE_BELOW_GUARD_PX)
    if max_bottom <= rect.y0:
        return rect
    if rect.y1 > max_bottom:
        return fitz.Rect(rect.x0, rect.y0, rect.x1, max_bottom)
    if rect.y1 < max_bottom:
        return fitz.Rect(rect.x0, rect.y0, rect.x1, max_bottom)
    return rect


def _expand_table_bbox(
    page: fitz.Page,
    bbox: Tuple[float, float, float, float],
    method: str,
) -> Tuple[float, float, float, float]:
    if method not in ("stream", "lattice"):
        return bbox
    rect = fitz.Rect(*bbox)
    page_rect = page.rect
    gap_frac = TABLE_EXPAND_MAX_GAP_FRAC if method == "stream" else TABLE_EXPAND_LATTICE_MAX_GAP_FRAC
    max_gap_x = page_rect.width * gap_frac
    max_gap_y = page_rect.height * gap_frac
    expanded = rect

    try:
        blocks = page.get_text("blocks")
    except Exception:
        blocks = []

    for x0, y0, x1, y1, text, *_ in blocks:
        if not text:
            continue
        block = fitz.Rect(x0, y0, x1, y1)
        if block.height > rect.height * TABLE_EXPAND_MAX_BLOCK_HEIGHT_FRAC:
            continue
        text_str = str(text)
        lines, chars = _text_stats(text_str)
        if lines == 0:
            continue
        avg_line_len = chars / max(1, lines)
        heading_like = _heading_like_block(text_str, lines, avg_line_len)
        if not heading_like and (lines > TABLE_EXPAND_MAX_LINES or avg_line_len > TABLE_EXPAND_MAX_AVG_LINE_LEN):
            continue

        inter_area = _rect_intersection_area(block, rect)
        if inter_area > 0.0:
            if block.x0 < rect.x0 and rect.x0 - block.x0 <= max_gap_x:
                expanded |= block
            if block.x1 > rect.x1 and block.x1 - rect.x1 <= max_gap_x:
                expanded |= block
            if block.y0 < rect.y0 and rect.y0 - block.y0 <= max_gap_y:
                expanded |= block
            if block.y1 > rect.y1 and block.y1 - rect.y1 <= max_gap_y:
                expanded |= block
            continue

        if block.y1 <= rect.y0 and rect.y0 - block.y1 <= max_gap_y:
            if _horizontal_overlap_ratio(block, rect) >= TABLE_EXPAND_MIN_H_OVERLAP:
                expanded |= block
        elif block.y0 >= rect.y1 and block.y0 - rect.y1 <= max_gap_y:
            if _horizontal_overlap_ratio(block, rect) >= TABLE_EXPAND_MIN_H_OVERLAP:
                expanded |= block
        elif block.x1 <= rect.x0 and rect.x0 - block.x1 <= max_gap_x:
            if _vertical_overlap_ratio(block, rect) >= TABLE_EXPAND_MIN_V_OVERLAP:
                expanded |= block
        elif block.x0 >= rect.x1 and block.x0 - rect.x1 <= max_gap_x:
            if _vertical_overlap_ratio(block, rect) >= TABLE_EXPAND_MIN_V_OVERLAP:
                expanded |= block

    drawings = _drawing_rects(page) + _image_block_rects(page)
    for block in drawings:
        if _rect_intersection_area(block, rect) > 0.0:
            if block.x0 < rect.x0 and rect.x0 - block.x0 <= max_gap_x:
                expanded |= block
            if block.x1 > rect.x1 and block.x1 - rect.x1 <= max_gap_x:
                expanded |= block
            if block.y0 < rect.y0 and rect.y0 - block.y0 <= max_gap_y:
                expanded |= block
            if block.y1 > rect.y1 and block.y1 - rect.y1 <= max_gap_y:
                expanded |= block
            continue
        if block.x1 <= rect.x0 and rect.x0 - block.x1 <= max_gap_x:
            if _vertical_overlap_ratio(block, rect) >= TABLE_EXPAND_MIN_V_OVERLAP:
                expanded |= block
        elif block.x0 >= rect.x1 and block.x0 - rect.x1 <= max_gap_x:
            if _vertical_overlap_ratio(block, rect) >= TABLE_EXPAND_MIN_V_OVERLAP:
                expanded |= block
        elif block.y1 <= rect.y0 and rect.y0 - block.y1 <= max_gap_y:
            if _horizontal_overlap_ratio(block, rect) >= TABLE_EXPAND_MIN_H_OVERLAP:
                expanded |= block
        elif block.y0 >= rect.y1 and block.y0 - rect.y1 <= max_gap_y:
            if _horizontal_overlap_ratio(block, rect) >= TABLE_EXPAND_MIN_H_OVERLAP:
                expanded |= block

    if method == "stream":
        width_frac = expanded.width / max(1.0, page_rect.width)
        height_frac = expanded.height / max(1.0, page_rect.height)
        if width_frac >= TABLE_EXPAND_STREAM_WIDE_MIN_WIDTH_FRAC and height_frac >= TABLE_EXPAND_STREAM_WIDE_MIN_HEIGHT_FRAC:
            if page_rect.x1 - expanded.x1 <= max_gap_x:
                expanded = fitz.Rect(expanded.x0, expanded.y0, page_rect.x1, expanded.y1)
            if expanded.x0 - page_rect.x0 <= max_gap_x:
                expanded = fitz.Rect(page_rect.x0, expanded.y0, expanded.x1, expanded.y1)

    expanded &= page_rect
    if expanded.is_empty:
        return bbox
    return (expanded.x0, expanded.y0, expanded.x1, expanded.y1)


def _save_thumb(pix: fitz.Pixmap, out_dir: str, report_name: str, index: int, max_w: int = 480) -> str:
    if pix.alpha:
        pix = fitz.Pixmap(fitz.csRGB, pix)
    elif pix.colorspace and pix.colorspace != fitz.csRGB:
        pix = fitz.Pixmap(fitz.csRGB, pix)

    png_bytes = pix.tobytes("png")
    img = Image.open(io.BytesIO(png_bytes)).convert("RGB")

    if img.width > max_w:
        new_h = int(img.height * max_w / img.width)
        img = img.resize((max_w, new_h), Image.LANCZOS)

    Path(out_dir).mkdir(parents=True, exist_ok=True)
    if index == 0:
        filename = f"{report_name}.png"
    else:
        filename = f"{report_name}{index}.png"
    p = Path(out_dir) / filename
    img.save(p.as_posix(), format="PNG")
    return p.as_posix()


def _nearby_text(page: fitz.Page, rect: fitz.Rect, max_dist: float = 90) -> str:
    best = ("", 1e9)
    for x0, y0, x1, y1, text, *_ in page.get_text("blocks"):
        if not text:
            continue
        if _is_page_number_text(text):
            continue
        r = fitz.Rect(x0, y0, x1, y1)
        dy = r.y0 - rect.y1
        dist = (dy if dy >= 0 else abs(dy) + 24)
        if dist <= max_dist and dist < best[1]:
            best = (text.strip(), dist)
    return best[0]


def _extract_charts(
    pdf_path: str,
    thumbs_dir: str,
    report_name: str,
    save_thumbs: bool = False,
    doc: Optional[fitz.Document] = None,
) -> Tuple[List[Candidate], Dict[str, object]]:
    out: List[Candidate] = []
    stats: Dict[str, object] = {"raw": 0, "kept": 0, "rejected": 0, "reasons": {}}
    page_text_cache: Dict[int, Tuple[int, int]] = {}
    local_doc = doc or fitz.open(pdf_path)
    try:
        thumb_index = 0
        for pno in range(len(local_doc)):
            page = local_doc[pno]
            if pno not in page_text_cache:
                try:
                    page_text_cache[pno] = _text_stats(page.get_text("text"))
                except Exception:
                    page_text_cache[pno] = (0, 0)
            page_chars = page_text_cache[pno][1]
            rect = page.rect
            top_cut = rect.y0 + rect.height * CHART_MARGIN_FRAC
            bot_cut = rect.y1 - rect.height * CHART_MARGIN_FRAC
            relaxed_top = rect.y0 + rect.height * CHART_MARGIN_RELAX_FRAC
            relaxed_bot = rect.y1 - rect.height * CHART_MARGIN_RELAX_FRAC
            local = 0
            kept: List[Tuple[fitz.Rect, float, int]] = []
            candidates = _collect_chart_rects(page)
            for rect_item in candidates:
                stats["raw"] = int(stats["raw"]) + 1
                r = rect_item.rect
                base_rect = r
                area_frac = r.get_area() / rect.get_area()
                aspect = r.width / max(1, r.height)
                aspect_max = INFO_CHART_MAX_ASPECT if rect_item.kind == "heading" else 2.5
                if area_frac < 0.05 or not (0.55 <= aspect <= aspect_max):
                    stats["rejected"] = int(stats["rejected"]) + 1
                    _tally_reason(stats, "geometry")
                    continue
                cap_rect = rect_item.caption_rect
                cap = rect_item.caption
                if cap_rect is None:
                    cap_rect, cap = _nearest_caption_block(page, r, CHART_CAPTION_HINTS)
                if not cap:
                    cap = _nearby_text(page, r)
                if cap and _is_page_number_text(cap):
                    cap = ""
                cap_lower = (cap or "").lower()
                has_hint = any(k in cap_lower for k in CAPTION_HINTS)
                if r.y0 < top_cut or r.y1 > bot_cut:
                    if not has_hint or r.y0 < relaxed_top or r.y1 > relaxed_bot:
                        stats["rejected"] = int(stats["rejected"]) + 1
                        _tally_reason(stats, "margin")
                        continue
                if not has_hint and area_frac < 0.08:
                    stats["rejected"] = int(stats["rejected"]) + 1
                    _tally_reason(stats, "caption_hint")
                    continue
                if rect_item.kind in ("block", "draw") and not has_hint and area_frac < 0.12:
                    stats["rejected"] = int(stats["rejected"]) + 1
                    _tally_reason(stats, "block_small_no_caption")
                    continue
                if rect_item.kind in ("block", "draw") and not has_hint and area_frac > 0.8:
                    stats["rejected"] = int(stats["rejected"]) + 1
                    _tally_reason(stats, "block_full_page_no_caption")
                    continue
                try:
                    bbox_text = page.get_text("text", clip=r)
                except Exception:
                    bbox_text = ""
                text_lines, text_chars = _text_stats(bbox_text)
                text_ratio = (text_chars / page_chars) if page_chars else 0.0
                if rect_item.kind in ("xref", "block") and not has_hint:
                    if (not cap or len(cap.strip()) < 8) and text_chars <= 8 and area_frac < 0.5:
                        stats["rejected"] = int(stats["rejected"]) + 1
                        _tally_reason(stats, "decorative_image")
                        continue
                if _chart_text_heavy(text_lines, text_chars, text_ratio):
                    if rect_item.kind == "draw" and has_hint and text_ratio <= 0.55:
                        pass
                    else:
                        stats["rejected"] = int(stats["rejected"]) + 1
                        _tally_reason(stats, "text_dense")
                        continue
                r_final = r
                expanded_with_heading = False
                if cap_rect is not None and has_hint:
                    r_final = _merge_caption_above(r_final, cap_rect, rect)
                allow_adjacent = rect_item.kind in ("draw", "heading") or (
                    rect_item.kind == "xref" and has_hint
                )
                if allow_adjacent:
                    r_final = _extend_with_adjacent_text_blocks(page, r_final)
                if not has_hint and rect_item.kind == "heading":
                    expanded = _extend_with_heading_above(page, r_final)
                    expanded_with_heading = expanded.y0 < r_final.y0 - 1
                    r_final = expanded
                if not has_hint and rect_item.kind not in ("heading", "xref"):
                    head_rect = _nearest_heading_above(page, r_final)
                    if head_rect is not None:
                        r_final = r_final | head_rect
                if rect_item.kind != "xref" or has_hint:
                    r_final = _pad_rect(r_final, rect)
                if not has_hint and rect_item.kind in ("draw", "heading"):
                    if rect_item.kind == "heading":
                        r_final = _adjust_rect_for_text_margins(
                            page,
                            r_final,
                            gap_scale=CHART_EDGE_TEXT_HEADING_GAP_SCALE,
                            gap_scale_x=CHART_EDGE_TEXT_HEADING_GAP_X_SCALE,
                        )
                        r_final = _expand_rect_into_whitespace(
                            page,
                            r_final,
                            allow_top=False,
                        )
                    else:
                        r_final = _adjust_rect_for_text_margins(page, r_final)
                        r_final = _expand_rect_into_whitespace(page, r_final)
                if rect_item.kind == "heading" and cap_rect is not None and not expanded_with_heading:
                    r_final = _clamp_top_to_heading(r_final, cap_rect, page, rect)
                if not has_hint and rect_item.kind not in ("heading", "xref"):
                    head_rect = _nearest_heading_above(page, r_final)
                    if head_rect is not None:
                        r_final = _clamp_top_to_heading(r_final, head_rect, page, rect)
                r_final = _extend_with_note_blocks(page, r_final)
                if cap_rect is not None and has_hint and cap_rect.y0 < base_rect.y0:
                    r_final = _clamp_top_to_caption(r_final, cap_rect, page, rect)
                note_bottom = _note_block_bottom(page, r_final)
                note_included = note_bottom is not None
                if note_bottom is not None:
                    r_final = _clamp_bottom_to_note(page, r_final, note_bottom, rect)
                if cap_rect is not None and _caption_near_top(r_final, cap_rect):
                    if has_hint or rect_item.kind != "heading":
                        r_final = _clamp_top_to_caption(r_final, cap_rect, page, rect)
                r_final = _trim_top_page_number(r_final, page, cap_rect if has_hint else None)
                try:
                    bbox_text = page.get_text("text", clip=r_final)
                except Exception:
                    bbox_text = ""
                text_lines, text_chars = _text_stats(bbox_text)
                text_ratio = (text_chars / page_chars) if page_chars else 0.0
                pix = None
                if save_thumbs:
                    render_rect = r_final
                    if (
                        rect_item.kind == "xref"
                        and rect_item.xref is not None
                        and _rect_iou(render_rect, r) >= 0.98
                    ):
                        pix = fitz.Pixmap(local_doc, rect_item.xref)
                        if pix.alpha or (pix.colorspace and pix.colorspace != fitz.csRGB):
                            pix = fitz.Pixmap(fitz.csRGB, pix)
                    else:
                        try:
                            pix = page.get_pixmap(clip=render_rect, alpha=False)
                        except Exception:
                            pix = None
                cid = f"chart-{pno}-{local}"
                thumb = _save_thumb(pix, thumbs_dir, report_name, thumb_index) if save_thumbs and pix else None
                if save_thumbs and thumb:
                    thumb_path = Path(thumb)
                    rel_thumb = Path(report_name) / "thumbs" / thumb_path.name
                    thumb = rel_thumb.as_posix()
                candidate = Candidate(
                    schema_version="1.0",
                    id=cid,
                    kind="chart",
                    page=pno,
                    bbox=(r_final.x0, r_final.y0, r_final.x1, r_final.y1),
                    preview_text=cap or "",
                    caption=cap,
                    thumb_path=thumb,
                    meta={
                        "area_frac": round(area_frac, 3),
                        "aspect": round(aspect, 2),
                        "text_lines": text_lines,
                        "text_chars": text_chars,
                        "text_ratio": round(text_ratio, 3),
                    },
                )
                score = _chart_candidate_score(area_frac, has_hint, cap or "", note_included)
                overlap_idx = _find_overlapping_kept(r_final, kept)
                if overlap_idx is not None:
                    existing_score = kept[overlap_idx][1]
                    if score <= existing_score:
                        stats["rejected"] = int(stats["rejected"]) + 1
                        _tally_reason(stats, "overlap_dup")
                        continue
                    out_idx = kept[overlap_idx][2]
                    out[out_idx] = candidate
                    kept[overlap_idx] = (r_final, score, out_idx)
                    stats["replaced"] = int(stats.get("replaced", 0)) + 1
                else:
                    out.append(candidate)
                    kept.append((r_final, score, len(out) - 1))
                    stats["kept"] = int(stats["kept"]) + 1
                if save_thumbs:
                    thumb_index += 1
                local += 1
    finally:
        if doc is None:
            local_doc.close()
    return out, stats


def _extract_tables(pdf_path: str, max_candidates: int = 10) -> Tuple[List[Candidate], Dict[str, object]]:
    out: List[Candidate] = []
    stats: Dict[str, object] = {
        "raw_lattice": 0,
        "raw_stream": 0,
        "validated": 0,
        "deduped": 0,
        "rejected": 0,
        "reasons": {},
    }
    _suppress_pdfminer_warnings()

    fitz_doc = None
    try:
        fitz_doc = fitz.open(pdf_path)
    except Exception:
        fitz_doc = None

    try:
        with pdfplumber.open(pdf_path) as pdf:
            for pno, p in enumerate(pdf.pages):
                fitz_page = None
                if fitz_doc is not None and pno < len(fitz_doc):
                    try:
                        fitz_page = fitz_doc[pno]
                    except Exception:
                        fitz_page = None

                lattice_tables = _find_tables_safe(p, TABLE_SETTINGS_LATTICE)
                stream_tables = _find_tables_safe(p, TABLE_SETTINGS_STREAM)
                stats["raw_lattice"] = int(stats["raw_lattice"]) + len(lattice_tables)
                stats["raw_stream"] = int(stats["raw_stream"]) + len(stream_tables)

                raw_candidates = []
                raw_candidates.extend((t, "lattice") for t in lattice_tables)
                raw_candidates.extend((t, "stream") for t in stream_tables)

                validated: List[_TableCandidate] = []
                for t, method in raw_candidates:
                    cand = _build_table_candidate(p, t, method, fitz_page=fitz_page)
                    if not cand:
                        stats["rejected"] = int(stats["rejected"]) + 1
                        _tally_reason(stats, "build_failed")
                        continue
                    ok, reason = _validate_table_candidate(cand)
                    if not ok:
                        stats["rejected"] = int(stats["rejected"]) + 1
                        _tally_reason(stats, reason or "filtered")
                        continue
                    stats["validated"] = int(stats["validated"]) + 1
                    validated.append(cand)

                deduped = _dedupe_table_candidates(validated)
                stats["deduped"] = int(stats["deduped"]) + len(deduped)

                for i, cand in enumerate(sorted(deduped, key=_table_sort_key)):
                    x0, y0, x1, y1 = cand.bbox
                    if fitz_page is not None:
                        x0, y0, x1, y1 = _expand_table_bbox(fitz_page, (x0, y0, x1, y1), cand.method)
                    cid = f"table-{pno}-{i}"
                    out.append(Candidate(
                        schema_version="1.0",
                        id=cid,
                        kind="table",
                        page=pno,
                        bbox=(x0, y0, x1, y1),
                        preview_text=cand.preview,
                        caption=None,
                        thumb_path=None,
                        meta={
                            "method": cand.method,
                            "rows": cand.row_count,
                            "cols": cand.col_count,
                            "non_empty_cells": cand.non_empty_cells,
                            "numeric_ratio": round(cand.numeric_ratio, 3),
                            "avg_words_per_cell": round(cand.avg_words_per_cell, 2),
                            "index_page_ratio": round(cand.index_page_ratio, 2),
                            "text_len": cand.text_len,
                            "area_frac": round(cand.area_frac, 4),
                            "aspect": round(cand.aspect, 2),
                        },
                    ))
                    if len(out) >= max_candidates:
                        break

                if len(out) >= max_candidates:
                    break
    finally:
        if fitz_doc is not None:
            try:
                fitz_doc.close()
            except Exception:
                pass

    return out, stats


def _find_tables_safe(page: pdfplumber.page.Page, settings: Dict[str, object]):
    try:
        return page.find_tables(table_settings=settings) or []
    except Exception:
        return []


def _build_table_candidate(
    page: pdfplumber.page.Page,
    table: pdfplumber.table.Table,
    method: str,
    fitz_page: Optional[fitz.Page] = None,
) -> Optional[_TableCandidate]:
    try:
        x0, y0, x1, y1 = map(float, table.bbox)
    except Exception:
        return None
    rows = []
    try:
        rows = table.extract() or []
    except Exception:
        rows = []
    non_empty_rows = [row for row in rows if row and any(_s(c).strip() for c in row)]
    row_count = len(non_empty_rows)
    col_count = max((len(row) for row in non_empty_rows), default=0)
    row_col_counts = _row_nonempty_counts(rows)
    col_consistency = _col_consistency(row_col_counts)
    row_len_cv = _row_len_cv(_row_text_lengths(rows))
    non_empty_cells = sum(1 for row in non_empty_rows for c in row if _s(c).strip())
    total_cells = sum(len(row) for row in non_empty_rows)
    numeric_cells = sum(1 for row in non_empty_rows for c in row if _cell_is_numeric(_s(c)))
    numeric_chars, total_chars = _numeric_char_ratio(non_empty_rows)
    numeric_ratio = numeric_chars / max(1, total_chars)
    avg_words_per_cell = _avg_words_per_cell(non_empty_rows)
    avg_first_col_words = _avg_first_col_words(non_empty_rows)
    index_page_ratio = _index_page_ratio(non_empty_rows)
    preview = _table_preview(rows)
    text = _extract_text_in_bbox(page, (x0, y0, x1, y1))
    line_count, text_chars = _text_stats(text)
    avg_line_len = (text_chars / line_count) if line_count else 0.0
    text_len = len(text.strip())
    page_area = max(1.0, float(page.width * page.height))
    width = max(1.0, x1 - x0)
    height = max(1.0, y1 - y0)
    area_frac = (width * height) / page_area
    width_frac = width / max(1.0, float(page.width))
    height_frac = height / max(1.0, float(page.height))
    aspect = width / max(1.0, height)
    text_block_area_frac = 0.0
    text_block_line_count = 0
    text_block_avg_line_len = 0.0
    caption_hint = False
    if fitz_page is not None:
        caption_hint = _has_caption_hint(fitz_page, (x0, y0, x1, y1))
        text_block_area_frac, text_block_line_count, text_block_avg_line_len = _text_block_stats(
            fitz_page,
            (x0, y0, x1, y1),
        )
    return _TableCandidate(
        bbox=(x0, y0, x1, y1),
        method=method,
        row_count=row_count,
        col_count=col_count,
        col_consistency=col_consistency,
        row_len_cv=row_len_cv,
        non_empty_cells=non_empty_cells,
        total_cells=total_cells,
        numeric_cells=numeric_cells,
        numeric_ratio=numeric_ratio,
        avg_words_per_cell=avg_words_per_cell,
        avg_first_col_words=avg_first_col_words,
        index_page_ratio=index_page_ratio,
        preview=preview[:400],
        text=text,
        text_len=text_len,
        line_count=line_count,
        avg_line_len=avg_line_len,
        text_block_area_frac=text_block_area_frac,
        text_block_line_count=text_block_line_count,
        text_block_avg_line_len=text_block_avg_line_len,
        caption_hint=caption_hint,
        area_frac=area_frac,
        width_frac=width_frac,
        height_frac=height_frac,
        aspect=aspect,
    )


def _table_preview(rows: List[List[object]]) -> str:
    preview_lines = []
    for row in rows[:3]:
        if not row:
            continue
        preview_lines.append(" | ".join(_s(c) for c in row[:6]))
    return "\n".join(preview_lines)


def _extract_text_in_bbox(page: pdfplumber.page.Page, bbox: Tuple[float, float, float, float]) -> str:
    try:
        return page.within_bbox(bbox).extract_text() or ""
    except Exception:
        return ""


def _text_stats(text: str) -> Tuple[int, int]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    char_count = sum(len(line) for line in lines)
    return len(lines), char_count


def _chart_text_heavy(lines: int, chars: int, ratio: float) -> bool:
    if lines <= CHART_TEXT_MAX_LINES:
        return False
    if chars < CHART_TEXT_MIN_CHARS:
        return False
    return ratio >= CHART_TEXT_RATIO_THRESHOLD


def _cell_is_numeric(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    for ch in stripped:
        if ch.isdigit():
            continue
        if ch in {".", ",", "%", "+", "-", "–"}:
            continue
        return False
    return any(ch.isdigit() for ch in stripped)


def _cell_words(text: str) -> int:
    return len([w for w in text.split() if w.strip()])


def _numeric_char_ratio(rows: List[List[object]]) -> Tuple[int, int]:
    numeric_chars = 0
    total_chars = 0
    for row in rows:
        for cell in row:
            text = _s(cell).strip()
            if not text:
                continue
            total_chars += len(text)
            numeric_chars += sum(1 for ch in text if ch.isdigit())
    return numeric_chars, total_chars


def _avg_words_per_cell(rows: List[List[object]]) -> float:
    words = 0
    cells = 0
    for row in rows:
        for cell in row:
            text = _s(cell).strip()
            if not text:
                continue
            cells += 1
            words += _cell_words(text)
    return (words / cells) if cells else 0.0


def _avg_first_col_words(rows: List[List[object]]) -> float:
    words = 0
    rows_counted = 0
    for row in rows:
        for cell in row:
            text = _s(cell).strip()
            if not text:
                continue
            rows_counted += 1
            words += _cell_words(text)
            break
    return (words / rows_counted) if rows_counted else 0.0


def _row_nonempty_counts(rows: List[List[object]]) -> List[int]:
    counts = []
    for row in rows:
        if not row:
            continue
        count = sum(1 for c in row if _s(c).strip())
        if count:
            counts.append(count)
    return counts


def _row_text_lengths(rows: List[List[object]]) -> List[int]:
    lengths = []
    for row in rows:
        if not row:
            continue
        texts = [_s(c).strip() for c in row]
        if not any(texts):
            continue
        lengths.append(sum(len(t) for t in texts))
    return lengths


def _col_consistency(row_counts: List[int]) -> float:
    if not row_counts:
        return 0.0
    counts: Dict[int, int] = {}
    for count in row_counts:
        counts[count] = counts.get(count, 0) + 1
    return max(counts.values()) / max(1, len(row_counts))


def _row_len_cv(lengths: List[int]) -> float:
    if len(lengths) < 2:
        return 0.0
    mean = sum(lengths) / len(lengths)
    if mean <= 0:
        return 0.0
    var = sum((length - mean) ** 2 for length in lengths) / len(lengths)
    return math.sqrt(var) / mean


def _cell_is_page_number(text: str) -> bool:
    return _is_page_number_text(text)


def _trim_top_page_number(
    rect: fitz.Rect,
    page: fitz.Page,
    cap_rect: Optional[fitz.Rect],
) -> fitz.Rect:
    page_rect = page.rect
    top_band = page_rect.height * 0.15
    right_band = page_rect.x0 + page_rect.width * 0.55
    guard = max(page_rect.height * 0.008, 6.0)
    best_y1: Optional[float] = None
    try:
        blocks = page.get_text("blocks")
    except Exception:
        return rect
    for x0, y0, x1, y1, text, *_ in blocks:
        if not text:
            continue
        if not _is_page_number_text(text):
            continue
        block = fitz.Rect(x0, y0, x1, y1)
        if block.y0 > page_rect.y0 + top_band:
            continue
        if block.x0 < right_band:
            continue
        if not block.intersects(rect):
            continue
        if cap_rect is not None and block.y1 >= cap_rect.y0 - guard:
            continue
        if best_y1 is None or block.y1 > best_y1:
            best_y1 = block.y1
    if best_y1 is None:
        return rect
    new_top = max(rect.y0, best_y1 + guard)
    if new_top >= rect.y1:
        return rect
    return fitz.Rect(rect.x0, new_top, rect.x1, rect.y1)


def _index_page_ratio(rows: List[List[object]]) -> float:
    index_rows = 0
    total_rows = 0
    for row in rows:
        row_cells = [c for c in row if _s(c).strip()]
        if len(row_cells) < 2:
            continue
        total_rows += 1
        first_text = _s(row_cells[0]).strip()
        last_text = _s(row_cells[-1]).strip()
        if _cell_words(first_text) >= TABLE_INDEX_MIN_FIRST_COL_WORDS and _cell_is_page_number(last_text):
            index_rows += 1
    return (index_rows / total_rows) if total_rows else 0.0


def _rect_intersection_area(a: fitz.Rect, b: fitz.Rect) -> float:
    inter = a & b
    if inter.is_empty:
        return 0.0
    return max(0.0, inter.get_area())


def _heading_like_block(text: str, lines: int, avg_line_len: float) -> bool:
    if lines == 0:
        return False
    if lines > TABLE_EXPAND_HEADING_MAX_LINES:
        return False
    if avg_line_len > TABLE_EXPAND_HEADING_MAX_AVG_LINE_LEN:
        return False
    if _alpha_ratio(text) < TABLE_EXPAND_HEADING_MIN_ALPHA_RATIO:
        return False
    sentence_marks = text.count(".") + text.count("!") + text.count("?")
    if sentence_marks > TABLE_EXPAND_HEADING_MAX_SENTENCES:
        return False
    return True




def _text_block_stats(page: fitz.Page, bbox: Tuple[float, float, float, float]) -> Tuple[float, int, float]:
    rect = fitz.Rect(*bbox)
    rect_area = max(1.0, rect.get_area())
    block_area = 0.0
    line_count = 0
    total_line_len = 0
    try:
        blocks = page.get_text("blocks")
    except Exception:
        blocks = []
    for x0, y0, x1, y1, text, *_ in blocks:
        if not text:
            continue
        block_rect = fitz.Rect(x0, y0, x1, y1)
        inter_area = _rect_intersection_area(rect, block_rect)
        if inter_area <= 0.0:
            continue
        block_area += inter_area
        lines = [line.strip() for line in str(text).splitlines() if line.strip()]
        line_count += len(lines)
        total_line_len += sum(len(line) for line in lines)
    avg_line_len = (total_line_len / line_count) if line_count else 0.0
    return block_area / rect_area, line_count, avg_line_len


def _has_caption_hint(page: fitz.Page, bbox: Tuple[float, float, float, float], max_dist: float = 60) -> bool:
    rect = fitz.Rect(*bbox)
    page_rect = page.rect
    above = fitz.Rect(rect.x0, max(page_rect.y0, rect.y0 - max_dist), rect.x1, rect.y0)
    below = fitz.Rect(rect.x0, rect.y1, rect.x1, min(page_rect.y1, rect.y1 + max_dist))
    text = ""
    try:
        text += page.get_text("text", clip=above) or ""
    except Exception:
        pass
    try:
        text += " " + (page.get_text("text", clip=below) or "")
    except Exception:
        pass
    lowered = text.lower()
    return any(hint in lowered for hint in TABLE_CAPTION_HINTS)


def _validate_table_candidate(cand: _TableCandidate) -> Tuple[bool, str]:
    if cand.row_count < TABLE_MIN_ROWS or cand.col_count < TABLE_MIN_COLS:
        return False, "too_few_rows_cols"
    if cand.non_empty_cells < TABLE_MIN_NONEMPTY_CELLS:
        return False, "too_few_cells"
    if cand.text_len < TABLE_MIN_TEXT_CHARS:
        return False, "no_text"
    if cand.area_frac < TABLE_MIN_AREA_FRAC and cand.text_len < TABLE_MIN_TEXT_CHARS * 2:
        return False, "too_small"
    if (cand.aspect < TABLE_MIN_ASPECT or cand.aspect > TABLE_MAX_ASPECT) and cand.text_len < TABLE_MIN_TEXT_CHARS * 3:
        return False, "extreme_aspect"
    if cand.width_frac < TABLE_MIN_WIDTH_FRAC and cand.text_len < TABLE_MIN_TEXT_CHARS * 2:
        return False, "too_narrow"
    if cand.height_frac < TABLE_MIN_HEIGHT_FRAC and cand.text_len < TABLE_MIN_TEXT_CHARS * 2:
        return False, "too_short"
    if cand.method == "stream":
        if (
            cand.row_count >= TABLE_TEXT_HEAVY_MIN_ROWS
            and cand.col_count <= TABLE_INDEX_MAX_COLS
            and cand.numeric_ratio <= TABLE_TEXT_HEAVY_MAX_NUMERIC_RATIO
            and cand.avg_words_per_cell >= TABLE_TEXT_HEAVY_MIN_AVG_WORDS
        ):
            return False, "text_heavy_stream"
        if (
            cand.row_count >= TABLE_INDEX_MIN_ROWS
            and cand.col_count <= TABLE_INDEX_MAX_COLS
            and cand.index_page_ratio >= TABLE_INDEX_PAGE_RATIO
            and cand.avg_first_col_words >= TABLE_INDEX_MIN_FIRST_COL_WORDS
        ):
            return False, "index_like"
        if _stream_text_layout_like(cand):
            return False, "stream_text_layout"
        if _stream_text_block_like(cand):
            return False, "stream_text_block"
        if _stream_infobox_like(cand):
            return False, "stream_infobox"
        if _stream_list_like(cand):
            return False, "stream_list"
        if _stream_panel_like(cand):
            return False, "stream_panel"
        if _stream_sparse_text_like(cand):
            return False, "stream_sparse_text"
        if _stream_low_consistency(cand):
            return False, "stream_low_consistency"
        if _text_block_like_loose(cand):
            return False, "text_block_like_loose"
        if _text_block_like(cand):
            return False, "text_block_like"
    return True, ""


def _stream_text_layout_like(cand: _TableCandidate) -> bool:
    if cand.caption_hint:
        return False
    if cand.row_count < TABLE_STREAM_TEXTY_MIN_ROWS or cand.col_count < TABLE_STREAM_TEXTY_MIN_COLS:
        return False
    if cand.area_frac < TABLE_STREAM_TEXTY_MIN_AREA:
        return False
    if cand.numeric_ratio > TABLE_STREAM_TEXTY_MAX_NUMERIC_RATIO:
        return False
    if cand.line_count < TABLE_STREAM_TEXTY_MIN_LINES:
        return False
    if cand.avg_line_len < TABLE_STREAM_TEXTY_MIN_AVG_LINE_LEN:
        return False
    return True


def _stream_text_block_like(cand: _TableCandidate) -> bool:
    if cand.caption_hint:
        return False
    if cand.area_frac < TABLE_STREAM_TEXTBLOCK_MIN_AREA:
        return False
    if cand.numeric_ratio > TABLE_STREAM_TEXTBLOCK_MAX_NUMERIC_RATIO:
        return False
    if cand.line_count < TABLE_STREAM_TEXTBLOCK_MIN_LINES:
        return False
    if cand.avg_line_len < TABLE_STREAM_TEXTBLOCK_MIN_AVG_LINE_LEN:
        return False
    if cand.col_consistency > TABLE_STREAM_TEXTBLOCK_MAX_COL_CONSISTENCY:
        return False
    if cand.row_len_cv < TABLE_STREAM_TEXTBLOCK_MIN_ROW_LEN_CV:
        return False
    fill_ratio = cand.non_empty_cells / max(1, cand.total_cells)
    if fill_ratio > TABLE_STREAM_TEXTBLOCK_MAX_FILL_RATIO:
        return False
    return True


def _stream_infobox_like(cand: _TableCandidate) -> bool:
    if cand.caption_hint:
        return False
    if cand.area_frac < TABLE_STREAM_INFOBOX_MIN_AREA:
        return False
    if cand.row_count < TABLE_STREAM_INFOBOX_MIN_ROWS:
        return False
    if cand.col_count > TABLE_STREAM_INFOBOX_MAX_COLS:
        return False
    if cand.numeric_ratio > TABLE_STREAM_INFOBOX_MAX_NUMERIC_RATIO:
        return False
    if cand.avg_words_per_cell > TABLE_STREAM_INFOBOX_MAX_AVG_WORDS:
        return False
    if cand.line_count < TABLE_STREAM_INFOBOX_MIN_LINES:
        return False
    if cand.row_len_cv > TABLE_STREAM_INFOBOX_MAX_ROW_LEN_CV:
        return False
    return True


def _stream_list_like(cand: _TableCandidate) -> bool:
    if cand.caption_hint:
        return False
    if cand.row_count < TABLE_STREAM_LIST_MIN_ROWS:
        return False
    if cand.col_count > TABLE_STREAM_LIST_MAX_COLS:
        return False
    if cand.area_frac > TABLE_STREAM_LIST_MAX_AREA_FRAC:
        return False
    if cand.avg_words_per_cell > TABLE_STREAM_LIST_MAX_AVG_WORDS:
        return False
    if cand.numeric_ratio > TABLE_STREAM_LIST_MAX_NUMERIC_RATIO:
        return False
    return True


def _stream_panel_like(cand: _TableCandidate) -> bool:
    if cand.caption_hint:
        return False
    if cand.area_frac < TABLE_STREAM_PANEL_MIN_AREA_FRAC:
        return False
    if cand.row_count < TABLE_STREAM_PANEL_MIN_ROWS:
        return False
    if cand.col_count > TABLE_STREAM_PANEL_MAX_COLS:
        return False
    if cand.avg_words_per_cell > TABLE_STREAM_PANEL_MAX_AVG_WORDS:
        return False
    if cand.numeric_ratio > TABLE_STREAM_PANEL_MAX_NUMERIC_RATIO:
        return False
    return True


def _stream_sparse_text_like(cand: _TableCandidate) -> bool:
    if cand.caption_hint:
        return False
    if cand.area_frac < TABLE_STREAM_SPARSE_MIN_AREA:
        return False
    if cand.line_count > TABLE_STREAM_SPARSE_MAX_LINES:
        return False
    if cand.avg_line_len < TABLE_STREAM_SPARSE_MIN_AVG_LINE_LEN:
        return False
    if cand.numeric_ratio > TABLE_STREAM_SPARSE_MAX_NUMERIC_RATIO:
        return False
    if cand.col_count > TABLE_STREAM_SPARSE_MAX_COLS:
        return False
    return True


def _stream_low_consistency(cand: _TableCandidate) -> bool:
    if cand.caption_hint:
        return False
    if cand.row_count < TABLE_STREAM_MIN_ROWS_FOR_LIKENESS or cand.col_count < TABLE_STREAM_MIN_COLS_FOR_LIKENESS:
        return False
    if cand.col_consistency >= TABLE_STREAM_MIN_COL_CONSISTENCY:
        return False
    if cand.row_len_cv <= TABLE_STREAM_MAX_ROW_LEN_CV:
        return False
    return True


def _text_block_like(cand: _TableCandidate) -> bool:
    if cand.caption_hint:
        return False
    if cand.text_block_area_frac < TEXT_BLOCK_MIN_AREA_FRAC:
        return False
    if cand.text_block_line_count < TEXT_BLOCK_MIN_LINES:
        return False
    if cand.text_block_avg_line_len < TEXT_BLOCK_MIN_AVG_LINE_LEN:
        return False
    if cand.numeric_ratio > TEXT_BLOCK_MAX_NUMERIC_RATIO:
        return False
    return True


def _text_block_like_loose(cand: _TableCandidate) -> bool:
    if cand.caption_hint:
        return False
    if cand.text_block_area_frac < TEXT_BLOCK_MIN_AREA_FRAC:
        return False
    if cand.text_block_line_count < TEXT_BLOCK_LOOSE_MIN_LINES:
        return False
    if cand.text_block_avg_line_len < TEXT_BLOCK_LOOSE_MIN_AVG_LINE_LEN:
        return False
    if cand.numeric_ratio > TEXT_BLOCK_LOOSE_MAX_NUMERIC_RATIO:
        return False
    return True


def _table_sort_key(cand: _TableCandidate) -> Tuple[float, float]:
    return (cand.bbox[1], cand.bbox[0])


def _table_quality(cand: _TableCandidate) -> Tuple[int, int, int]:
    return (cand.row_count * cand.col_count, cand.non_empty_cells, cand.text_len)


def _table_iou(a: Tuple[float, float, float, float], b: Tuple[float, float, float, float]) -> float:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    inter_w = max(0.0, min(ax1, bx1) - max(ax0, bx0))
    inter_h = max(0.0, min(ay1, by1) - max(ay0, by0))
    inter = inter_w * inter_h
    if inter <= 0.0:
        return 0.0
    area_a = max(0.0, (ax1 - ax0)) * max(0.0, (ay1 - ay0))
    area_b = max(0.0, (bx1 - bx0)) * max(0.0, (by1 - by0))
    union = area_a + area_b - inter
    if union <= 0.0:
        return 0.0
    return inter / union


def _dedupe_table_candidates(candidates: List[_TableCandidate]) -> List[_TableCandidate]:
    kept: List[_TableCandidate] = []
    for cand in candidates:
        replaced = False
        for idx, existing in enumerate(kept):
            if _table_iou(cand.bbox, existing.bbox) >= TABLE_DEDUP_IOU:
                if _table_quality(cand) > _table_quality(existing):
                    kept[idx] = cand
                replaced = True
                break
        if not replaced:
            kept.append(cand)
    return kept


def _tally_reason(stats: Dict[str, object], reason: str) -> None:
    reasons = stats.get("reasons")
    if not isinstance(reasons, dict):
        reasons = {}
        stats["reasons"] = reasons
    reasons[reason] = int(reasons.get(reason, 0)) + 1


def _suppress_pdfminer_warnings() -> None:
    """Force pdfminer loggers to ERROR to avoid noisy color warnings."""
    for name in _PDFMINER_LOGGERS:
        try:
            logging.getLogger(name).setLevel(logging.ERROR)
        except Exception:
            continue


def collect_candidates(request: ExtractCandidatesRequest, ctx: RunContext) -> ExtractCandidatesResponse:
    candidate_logger.info(log_event(
        ctx,
        role="service",
        event="extract_candidates_start",
        module=candidate_logger.name,
        fields={
            "pdf_path": request.pdf_path,
            "using_context": bool(request.pdf_context and request.pdf_context.fitz_doc),
        },
    ))
    thumbs = Path(request.out_dir) / request.report_name / "thumbs"
    charts, chart_stats = _extract_charts(
        request.pdf_path,
        thumbs.as_posix(),
        request.report_name,
        save_thumbs=False,
        doc=request.pdf_context.fitz_doc if request.pdf_context else None,
    )
    tables, table_stats = _extract_tables(request.pdf_path)
    candidates = charts + tables
    candidate_logger.info(log_event(
        ctx,
        role="service",
        event="extract_candidates_complete",
        module=candidate_logger.name,
        fields={
            "count": len(candidates),
            "chart_count": len(charts),
            "table_count": len(tables),
            "chart_stats": chart_stats,
            "table_stats": table_stats,
        },
    ))
    return ExtractCandidatesResponse(schema_version="1.0", candidates=candidates)


# BEGIN PDF CROPPING
CROP_TRIM_MAX_FRAC = 0.08
CROP_TRIM_MIN_PX = 12
CROP_TRIM_KEEP_PX = 8
CROP_TRIM_TOLERANCE = 8
CROP_TRIM_MIN_BG_FRAC = 0.9995
CROP_TRIM_SAMPLES = 60


def _dominant_border_color(img: Image.Image, box: int = 4) -> tuple[int, int, int]:
    width, height = img.size
    corners = [
        (0, 0),
        (max(0, width - box), 0),
        (0, max(0, height - box)),
        (max(0, width - box), max(0, height - box)),
    ]
    colors: List[tuple[int, int, int]] = []
    for x0, y0 in corners:
        for y in range(y0, min(height, y0 + box)):
            for x in range(x0, min(width, x0 + box)):
                colors.append(img.getpixel((x, y)))
    if not colors:
        return img.getpixel((0, 0))
    counts: dict[tuple[int, int, int], int] = {}
    for color in colors:
        counts[color] = counts.get(color, 0) + 1
    return max(counts, key=counts.get)


def _row_is_bg(img: Image.Image, y: int, bg: tuple[int, int, int], tol: int) -> bool:
    width, _ = img.size
    step = 1
    samples = 0
    match = 0
    for x in range(0, width, step):
        samples += 1
        px = img.getpixel((x, y))
        if all(abs(px[i] - bg[i]) <= tol for i in range(3)):
            match += 1
    return (match / max(1, samples)) >= CROP_TRIM_MIN_BG_FRAC


def _col_is_bg(img: Image.Image, x: int, bg: tuple[int, int, int], tol: int) -> bool:
    _, height = img.size
    step = 1
    samples = 0
    match = 0
    for y in range(0, height, step):
        samples += 1
        px = img.getpixel((x, y))
        if all(abs(px[i] - bg[i]) <= tol for i in range(3)):
            match += 1
    return (match / max(1, samples)) >= CROP_TRIM_MIN_BG_FRAC


def _trim_uniform_border(
    img: Image.Image,
    allow_top: bool = True,
    allow_bottom: bool = True,
    allow_left: bool = True,
    allow_right: bool = True,
) -> Image.Image:
    width, height = img.size
    if width == 0 or height == 0:
        return img
    bg = _dominant_border_color(img)
    max_trim_y = int(height * CROP_TRIM_MAX_FRAC)
    max_trim_x = int(width * CROP_TRIM_MAX_FRAC)

    top = 0
    while allow_top and top < max_trim_y and _row_is_bg(img, top, bg, CROP_TRIM_TOLERANCE):
        top += 1
    bottom = 0
    while allow_bottom and bottom < max_trim_y and _row_is_bg(img, height - 1 - bottom, bg, CROP_TRIM_TOLERANCE):
        bottom += 1
    left = 0
    while allow_left and left < max_trim_x and _col_is_bg(img, left, bg, CROP_TRIM_TOLERANCE):
        left += 1
    right = 0
    while allow_right and right < max_trim_x and _col_is_bg(img, width - 1 - right, bg, CROP_TRIM_TOLERANCE):
        right += 1

    if top < CROP_TRIM_MIN_PX:
        top = 0
    if bottom < CROP_TRIM_MIN_PX:
        bottom = 0
    if left < CROP_TRIM_MIN_PX:
        left = 0
    if right < CROP_TRIM_MIN_PX:
        right = 0

    if top == 0 and bottom == 0 and left == 0 and right == 0:
        return img

    top = max(0, top - CROP_TRIM_KEEP_PX)
    bottom = max(0, bottom - CROP_TRIM_KEEP_PX)
    left = max(0, left - CROP_TRIM_KEEP_PX)
    right = max(0, right - CROP_TRIM_KEEP_PX)

    new_left = left
    new_top = top
    new_right = max(new_left + 1, width - right)
    new_bottom = max(new_top + 1, height - bottom)
    return img.crop((new_left, new_top, new_right, new_bottom))


def crop_regions(request: CropRequest, ctx: RunContext) -> CropResponse:
    crop_logger.info(log_event(
        ctx,
        role="service",
        event="crop_regions_start",
        module=crop_logger.name,
        fields={
            "pdf_path": request.pdf_path,
            "count": len(request.items),
            "subdir": request.subdir,
            "using_context": bool(request.pdf_context and request.pdf_context.fitz_doc),
        },
    ))
    paths = _crop_regions(
        request.pdf_path,
        request.out_dir,
        request.report_name,
        request.subdir,
        request.items,
        pad=request.pad,
        doc=request.pdf_context.fitz_doc if request.pdf_context else None,
    )
    crop_logger.info(log_event(
        ctx,
        role="service",
        event="crop_regions_complete",
        module=crop_logger.name,
        fields={"count": len(paths)},
    ))
    return CropResponse(schema_version="1.0", paths=paths)


def _crop_regions(
    pdf_path: str,
    out_dir: str,
    report_name: str,
    subdir: str,
    items: Iterable[CropItem],
    pad: int = 8,
    doc: Optional[fitz.Document] = None,
) -> List[str]:
    safe_subdir = subdir or "slices"
    output_dir = Path(out_dir) / report_name / safe_subdir
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    local_doc = doc or fitz.open(pdf_path)
    try:
        for idx, it in enumerate(items):
            pno = it.page
            x0, y0, x1, y1 = it.bbox
            page = local_doc[pno]
            r = fitz.Rect(x0 - pad, y0 - pad, x1 + pad, y1 + pad)
            r = r & page.rect
            if r.is_empty:
                continue
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=r, alpha=False)
            img = None
            if it.type == "chart":
                try:
                    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                    img = _trim_uniform_border(img, allow_bottom=False, allow_right=False)
                except Exception:
                    img = None
            if idx == 0:
                filename = f"{report_name}.png"
            else:
                filename = f"{report_name}{idx}.png"
            op = output_dir / filename
            if img is not None:
                img.save(op.as_posix())
            else:
                pix.save(op.as_posix())
            rel = Path(report_name) / safe_subdir / filename
            paths.append(rel.as_posix())
    finally:
        if doc is None:
            local_doc.close()
    return paths


# BEGIN PDF PREVIEW
def render_preview(request: PreviewRequest, ctx: RunContext) -> PreviewResponse:
    preview_logger.info(log_event(
        ctx,
        role="service",
        event="preview_render_start",
        module=preview_logger.name,
        fields={
            "pdf_path": request.pdf_path,
            "dpi": request.dpi,
            "page_number": request.page_number,
            "variant": request.variant,
            "using_context": bool(request.pdf_context and request.pdf_context.fitz_doc),
        },
    ))
    try:
        img_path = _page_png(
            request.pdf_path,
            request.out_dir,
            request.report_name,
            page_number=max(request.page_number, 0),
            dpi=request.dpi,
            variant=request.variant,
            doc=request.pdf_context.fitz_doc if request.pdf_context else None,
        )
    except Exception as exc:
        preview_logger.info(log_event(
            ctx,
            role="service",
            event="preview_render_failed",
            module=preview_logger.name,
            fields={
                "pdf_path": request.pdf_path,
                "page_number": request.page_number,
                "error": str(exc),
            },
        ))
        img_path = None
    preview_logger.info(log_event(
        ctx,
        role="service",
        event="preview_render_complete",
        module=preview_logger.name,
        fields={"image_path": img_path or "", "page_number": request.page_number},
    ))
    return PreviewResponse(schema_version="1.1", image_path=img_path, page_number=max(request.page_number, 0))


def _page_png(
    pdf_path: str,
    out_dir: str,
    report_name: str,
    page_number: int = 0,
    dpi: int = 144,
    variant: str | None = None,
    doc: Optional[fitz.Document] = None,
) -> Optional[str]:
    out_root = Path(out_dir)
    out_root.mkdir(parents=True, exist_ok=True)

    img_dir = out_root / report_name / "assets"
    img_dir.mkdir(parents=True, exist_ok=True)

    variant_slug = slugify(variant) if variant else ""
    suffix = f"-{variant_slug}" if variant_slug else ""
    abs_png = img_dir / f"{report_name}{suffix}.png"

    local_doc = doc or fitz.open(pdf_path)
    try:
        if local_doc.page_count == 0 or page_number >= local_doc.page_count:
            return None
        page = local_doc.load_page(page_number)
        zoom = dpi / 72.0
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        pix.save(abs_png.as_posix())
    finally:
        if doc is None:
            local_doc.close()

    rel_png = Path(report_name) / "assets" / abs_png.name
    return rel_png.as_posix()


# BEGIN PDF FIGURE EXTRACTION
def extract_best_figure(request: FigureExtractRequest, ctx: RunContext) -> FigureExtractResponse:
    figure_logger.info(log_event(
        ctx,
        role="service",
        event="figure_extract_start",
        module=figure_logger.name,
        fields={"pdf_path": request.pdf_path, "using_context": bool(request.pdf_context and request.pdf_context.fitz_doc)},
    ))
    img_path, caption = _extract_best_figure_png(
        request.pdf_path,
        request.out_dir,
        request.report_name,
        doc=request.pdf_context.fitz_doc if request.pdf_context else None,
    )
    figure_logger.info(log_event(
        ctx,
        role="service",
        event="figure_extract_complete",
        module=figure_logger.name,
        fields={"image_path": img_path or ""},
    ))
    return FigureExtractResponse(schema_version="1.0", image_path=img_path, caption=caption)


FIGURE_CAPTION_HINTS = {"figure", "fig.", "exhibit", "chart", "graph", "source", "panel", "table"}
FIGURE_METRIC_HINTS = {"%", "$", "growth", "share", "yoy", "cagr", "roi", "roas", "ctr", "conversion", "revenue", "impressions", "spend", "units"}
FIGURE_LINE_RX = re.compile(r"\\b(fig(?:ure)?|exhibit|chart)\\b\\s*\\d+", re.I)


def _figure_score_text(text: str) -> int:
    if not text:
        return 0
    t = text.lower()
    s = 0
    s += sum(2 for k in FIGURE_CAPTION_HINTS if k in t)
    s += sum(1 for k in FIGURE_METRIC_HINTS if k in t)
    s += min(3, len(re.findall(r"\\d", t)) // 4)
    return s


def _figure_nearest_block_text(page: fitz.Page, bbox: fitz.Rect, max_dist: float = 90.0) -> str:
    best = ("", 0, 1e9)
    for x0, y0, x1, y1, text, *_ in page.get_text("blocks"):
        if not text or text.isspace():
            continue
        rect = fitz.Rect(x0, y0, x1, y1)
        dy = rect.y0 - bbox.y1
        distance = (dy if dy >= 0 else abs(dy) + 24)
        if distance > max_dist:
            continue
        sc = _figure_score_text(text)
        if sc > best[1] or (sc == best[1] and distance < best[2]):
            best = (text.strip(), sc, distance)
    return best[0]


def _figure_line_targets(page: fitz.Page) -> List[fitz.Rect]:
    targets = []
    for x0, y0, x1, y1, text, *_ in page.get_text("blocks"):
        if not text:
            continue
        if FIGURE_LINE_RX.search(text):
            targets.append(fitz.Rect(x0, y0, x1, y1))
    return targets


def _figure_distance(a: fitz.Rect, b: fitz.Rect) -> float:
    ac = a.tl + (a.br - a.tl) * 0.5
    bc = b.tl + (b.br - b.tl) * 0.5
    return (ac - bc).magnitude


def _extract_best_figure_png(
    pdf_path: str,
    out_dir: str,
    report_name: str,
    min_page_area_frac: float = 0.06,
    doc: Optional[fitz.Document] = None,
) -> Tuple[Optional[str], Optional[str]]:
    try:
        out_root = Path(out_dir)
        img_dir = out_root / report_name / "assets"
        img_dir.mkdir(parents=True, exist_ok=True)
        best = (None, 0.0, "")

        local_doc = doc or fitz.open(pdf_path)
        try:
            for pno, page in enumerate(local_doc):
                page_rect = page.rect
                page_area = page_rect.get_area()
                top_cut = page_rect.y0 + page_rect.height * 0.12
                bot_cut = page_rect.y1 - page_rect.height * 0.12

                figure_targets = _figure_line_targets(page)

                for xref, *_ in page.get_images(full=True):
                    rects = page.get_image_rects(xref)
                    if not rects:
                        continue
                    bbox = rects[0]
                    if bbox.y0 < top_cut or bbox.y1 > bot_cut:
                        continue

                    area = bbox.get_area()
                    if area / page_area < min_page_area_frac:
                        continue

                    aspect = bbox.width / max(1, bbox.height)
                    if not (0.6 <= aspect <= 2.2):
                        continue

                    caption = _figure_nearest_block_text(page, bbox)
                    cap_score = _figure_score_text(caption)

                    prox_bonus = 0
                    if figure_targets:
                        d = min(_figure_distance(bbox, t) for t in figure_targets)
                        if d < 200:
                            prox_bonus = 3
                        elif d < 350:
                            prox_bonus = 1

                    score = (area ** 0.9) * (1 + 0.15 * cap_score + 0.10 * prox_bonus)

                    if score > best[1]:
                        pix = fitz.Pixmap(local_doc, xref)
                        if pix.width * pix.height < 80_000:
                            continue
                        if pix.n >= 4:
                            pix = fitz.Pixmap(fitz.csRGB, pix)
                        best = (pix, score, caption or f"Auto-selected image from page {pno+1}")
        finally:
            if doc is None and 'local_doc' in locals():
                local_doc.close()

        if best[0] is None:
            return None, None

        out_path = img_dir / f"{report_name}.png"
        best[0].save(out_path.as_posix())
        rel = Path(report_name) / "assets" / out_path.name
        return rel.as_posix(), best[2]
    except Exception:
        return None, None
