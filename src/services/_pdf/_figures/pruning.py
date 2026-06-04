from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

import pymupdf as fitz

from src.contracts.candidates import Candidate
from src.utils.candidate_features import candidate_features

from ..table_heuristics import (
    _s,
    _table_containment_ratio,
    _table_iou,
)
from ..visual_heuristics import (
    PDF_FIGURE_EXCEPTIONS,
    _PageTextLine,
    _rect_overlap_area,
    _table_page_text_lines,
)

FIGURE_LINE_RX = re.compile(r"\b(fig(?:ure)?|exhibit|chart)\b\s*\d+", re.I)
FINAL_CHART_BARE_TITLE_RX = re.compile(
    r"^[A-Z][A-Za-z'’.-]*(?:\s+[A-Z][A-Za-z'’.-]*){0,2}$"
)
FINAL_CHART_SOURCE_OR_STATLINK_RX = re.compile(
    r"(?im)(?:^|\n)\s*(?:source:|statlink\b)"
)
FINAL_CHART_YEAR_RX = re.compile(r"\b(?:19|20)\d{2}[a-z]?\b")
FINAL_CHART_NUMBER_RX = re.compile(r"\b\d+(?:\.\d+)?\b")

PANEL_SHORT_PROPER_NAME_RX = re.compile(
    r"^[A-Z][A-Za-zÀ-ÖØ-öø-ÿ'’.-]+(?:\s+[A-Z][A-Za-zÀ-ÖØ-öø-ÿ'’.-]+){0,2}$"
)
CROP_REFINE_BBOX_PAD_X_FRAC = 0.012
CROP_REFINE_BBOX_PAD_Y_FRAC = 0.015
CROP_REFINE_BBOX_PAD_MIN = 4.0
CROP_REFINE_BBOX_PAD_MAX = 20.0
CROP_REFINE_EDGE_TOUCH_TOL = 1.5
CROP_REFINE_EDGE_MIN_OVERLAP = 0.2
CROP_REFINE_EDGE_INCLUDE_OVERLAP_RATIO = 0.35
CROP_REFINE_EDGE_TRIM_OVERLAP_RATIO = 0.1
TABLE_CHART_SHADOW_IOU = 0.6
TABLE_CHART_SHADOW_CONTAINMENT = 0.85
TABLE_CHART_SHADOW_TOTAL_OVERLAP_RATIO = 0.75
TABLE_CHART_SHADOW_STREAM_MIN_AREA = 0.18
TABLE_CHART_SHADOW_STREAM_MIN_ROWS = 8
TABLE_CHART_SHADOW_STREAM_MIN_COLS = 4
TABLE_CHART_SHADOW_STREAM_MAX_NUMERIC_RATIO = 0.05
TABLE_CHART_SHADOW_STREAM_MAX_AVG_WORDS = 2.5
TABLE_CHART_SHADOW_LATTICE_MIN_AREA = 0.08
TABLE_CHART_SHADOW_LATTICE_MAX_ROWS = 4
TABLE_CHART_SHADOW_LATTICE_MAX_COLS = 4
TABLE_CHART_SHADOW_LATTICE_MAX_NUMERIC_RATIO = 0.08
TABLE_CHART_SHADOW_LATTICE_MIN_AVG_WORDS = 4.0
PANEL_CHART_LOCAL_TITLE_MAX_WORDS = 6
PANEL_CHART_LOCAL_TITLE_MAX_CHARS = 64
TABLE_EXPAND_LATTICE_MAX_GAP_FRAC = 0.08
TABLE_EXPAND_MAX_BLOCK_HEIGHT_FRAC = 0.4
TABLE_EXPAND_MAX_LINES = 4
TABLE_EXPAND_MAX_AVG_LINE_LEN = 60
TABLE_EXPAND_MIN_V_OVERLAP = 0.2
CHART_RANKED_TABLE_DUP_IOU = 0.65
CHART_RANKED_TABLE_DUP_CONTAINMENT = 0.82

def _panel_title_looks_short_proper_name(text: str) -> bool:
    normalized = _s(text).strip()
    if not normalized or len(normalized) > 28:
        return False
    if any(ch.isdigit() for ch in normalized):
        return False
    words = normalized.split()
    if not (1 <= len(words) <= 3):
        return False
    if normalized.upper() == normalized:
        return False
    return PANEL_SHORT_PROPER_NAME_RX.fullmatch(normalized) is not None

def _prune_charts_overlapping_ranked_tables(
    charts: List[Candidate], tables: List[Candidate]
) -> Tuple[List[Candidate], int]:
    ranked_tables_by_page: Dict[int, List[Candidate]] = {}
    table_overlap_candidates_by_page: Dict[int, List[Candidate]] = {}
    for table in tables:
        if table.kind != "table":
            continue
        method = _s(candidate_features(table).method).strip().lower()
        if method != "ranked":
            if _table_candidate_looks_like_chart_shadow(table):
                continue
            table_overlap_candidates_by_page.setdefault(int(table.page), []).append(
                table
            )
            continue
        ranked_tables_by_page.setdefault(int(table.page), []).append(table)
    if not ranked_tables_by_page and not table_overlap_candidates_by_page:
        return charts, 0

    kept: List[Candidate] = []
    pruned = 0
    for chart in charts:
        page_tables = ranked_tables_by_page.get(int(chart.page), [])
        overlap_tables = table_overlap_candidates_by_page.get(int(chart.page), [])
        if not page_tables and not overlap_tables:
            kept.append(chart)
            continue
        should_prune = False
        for table in page_tables:
            iou = _table_iou(chart.bbox, table.bbox)
            containment = _table_containment_ratio(chart.bbox, table.bbox)
            if (
                iou >= CHART_RANKED_TABLE_DUP_IOU
                or containment >= CHART_RANKED_TABLE_DUP_CONTAINMENT
            ):
                should_prune = True
                break
        if not should_prune and _chart_candidate_looks_like_table_shadow(chart):
            for table in overlap_tables:
                iou = _table_iou(chart.bbox, table.bbox)
                containment = _table_containment_ratio(chart.bbox, table.bbox)
                if iou >= CHART_RANKED_TABLE_DUP_IOU or containment >= 0.9:
                    should_prune = True
                    break
        if should_prune:
            pruned += 1
            continue
        kept.append(chart)
    return kept, pruned


def _chart_candidate_looks_like_table_shadow(chart: Candidate) -> bool:
    if chart.kind != "chart":
        return False
    caption = _s(chart.caption or chart.preview_text).strip().lower()
    if re.match(r"^\s*(?:figure|fig\.|chart|graph|exhibit|infographic)\b", caption):
        return False
    features = candidate_features(chart)
    text_lines = int(features.text_lines or 0)
    text_chars = int(features.text_chars or 0)
    text_ratio = float(features.text_ratio or 0.0)
    return (
        text_lines >= 16 and text_chars >= 240 and text_ratio >= 0.1
    ) or text_lines >= 40


def _table_candidate_looks_like_chart_shadow(table: Candidate) -> bool:
    if table.kind != "table":
        return False
    features = candidate_features(table)
    method = _s(features.method).strip().lower()
    rows = int(features.rows or 0)
    cols = int(features.cols or 0)
    numeric_ratio = float(features.numeric_ratio or 0.0)
    avg_words_per_cell = float(features.avg_words_per_cell or 0.0)
    area_frac = float(features.area_frac or 0.0)
    if method == "lattice":
        return (
            area_frac >= TABLE_CHART_SHADOW_LATTICE_MIN_AREA
            and rows <= TABLE_CHART_SHADOW_LATTICE_MAX_ROWS
            and cols <= TABLE_CHART_SHADOW_LATTICE_MAX_COLS
            and numeric_ratio <= TABLE_CHART_SHADOW_LATTICE_MAX_NUMERIC_RATIO
            and avg_words_per_cell >= TABLE_CHART_SHADOW_LATTICE_MIN_AVG_WORDS
        )
    if method == "stream":
        return (
            area_frac >= TABLE_CHART_SHADOW_STREAM_MIN_AREA
            and rows >= TABLE_CHART_SHADOW_STREAM_MIN_ROWS
            and cols >= TABLE_CHART_SHADOW_STREAM_MIN_COLS
            and numeric_ratio <= TABLE_CHART_SHADOW_STREAM_MAX_NUMERIC_RATIO
            and avg_words_per_cell <= TABLE_CHART_SHADOW_STREAM_MAX_AVG_WORDS
        )
    return False


def _prune_tables_overlapping_chart_panels(
    tables: List[Candidate], charts: List[Candidate]
) -> Tuple[List[Candidate], int]:
    charts_by_page: Dict[int, List[Candidate]] = {}
    for chart in charts:
        if chart.kind != "chart":
            continue
        charts_by_page.setdefault(int(chart.page), []).append(chart)
    if not charts_by_page:
        return tables, 0

    kept: List[Candidate] = []
    pruned = 0
    for table in tables:
        page_charts = charts_by_page.get(int(table.page), [])
        if not page_charts or not _table_candidate_looks_like_chart_shadow(table):
            kept.append(table)
            continue
        should_prune = False
        table_rect = fitz.Rect(*table.bbox)
        table_area = max(1.0, table_rect.get_area())
        total_overlap = 0.0
        for chart in page_charts:
            iou = _table_iou(chart.bbox, table.bbox)
            containment = _table_containment_ratio(chart.bbox, table.bbox)
            total_overlap += _rect_overlap_area(fitz.Rect(*chart.bbox), table_rect)
            if (
                iou >= TABLE_CHART_SHADOW_IOU
                or containment >= TABLE_CHART_SHADOW_CONTAINMENT
            ):
                should_prune = True
                break
        if (
            not should_prune
            and (total_overlap / table_area) >= TABLE_CHART_SHADOW_TOTAL_OVERLAP_RATIO
        ):
            should_prune = True
        if should_prune:
            pruned += 1
            continue
        kept.append(table)
    return kept, pruned


def _final_chart_candidate_looks_heading_slice(
    candidate: Candidate,
    text: str,
) -> bool:
    caption = _s(candidate.caption or "").strip()
    if not caption or FIGURE_LINE_RX.search(caption):
        return False
    if any(ch.isdigit() for ch in caption):
        return False
    if not FINAL_CHART_BARE_TITLE_RX.fullmatch(caption):
        return False
    if FINAL_CHART_SOURCE_OR_STATLINK_RX.search(text):
        return False
    x0, y0, x1, y1 = candidate.bbox
    if (y1 - y0) > 96.0:
        return False
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    if not lines or len(lines) > 2:
        return False
    normalized = [re.sub(r"\s+", " ", line) for line in lines]
    return all(line == caption for line in normalized)


def _final_chart_candidate_looks_forecast_table(
    candidate: Candidate,
    text: str,
) -> bool:
    caption = _s(candidate.caption or "").strip()
    if not caption or FIGURE_LINE_RX.search(caption):
        return False
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    if len(lines) < 6:
        return False
    lower_lines = [line.lower() for line in lines]
    lower_text = "\n".join(lower_lines)
    dense_year_header = any(
        len(FINAL_CHART_YEAR_RX.findall(line)) >= 3
        for line in lines[: min(4, len(lines))]
    )
    if not dense_year_header:
        dense_year_header = (
            sum(
                len(FINAL_CHART_YEAR_RX.findall(line))
                for line in lines[: min(12, len(lines))]
            )
            >= 4
        )
    numeric_row_hits = sum(
        1 for line in lines if len(FINAL_CHART_NUMBER_RX.findall(line)) >= 3
    )
    return (
        dense_year_header
        and any("current prices" in line for line in lower_lines)
        and (
            any("percentage changes" in line for line in lower_lines)
            or any("volume" in line for line in lower_lines)
        )
        and (
            numeric_row_hits >= 1
            or "memorandum items" in lower_text
            or len(lines) >= 10
        )
    )


def _final_chart_header_reanchor_line(
    candidate: Candidate,
    page: fitz.Page,
    text: str,
) -> Optional[_PageTextLine]:
    if candidate.kind != "chart":
        return None
    caption = _s(candidate.caption or "").strip()
    if not caption or FIGURE_LINE_RX.search(caption):
        return None
    words = caption.split()
    if len(words) < 8 and not caption[:1].islower():
        return None
    lower_text = str(text or "").lower()
    if "source:" not in lower_text and "statlink" not in lower_text:
        return None
    rect = fitz.Rect(candidate.bbox)
    best: Optional[_PageTextLine] = None
    best_key: tuple[float, float, float] | None = None
    for line in _table_page_text_lines(page):
        line_text = _s(line.text).strip()
        if not _panel_title_looks_short_proper_name(line_text):
            continue
        if line.rect.y1 > rect.y0 + 2.0:
            continue
        gap = rect.y0 - line.rect.y1
        if gap > 72.0:
            continue
        if line.rect.x0 > rect.x0 + rect.width * 0.2:
            continue
        key = (gap, abs(line.rect.x0 - rect.x0), line.rect.y0)
        if best_key is None or key < best_key:
            best = line
            best_key = key
    return best


def _prune_final_chart_candidates(
    charts: List[Candidate],
    *,
    doc: fitz.Document,
) -> tuple[List[Candidate], int, int]:
    kept: List[Candidate] = []
    pruned = 0
    adjusted = 0
    for candidate in charts:
        if candidate.kind != "chart":
            kept.append(candidate)
            continue
        try:
            page = doc[int(candidate.page)]
            text = page.get_text("text", clip=fitz.Rect(candidate.bbox))
        except PDF_FIGURE_EXCEPTIONS:
            kept.append(candidate)
            continue
        header_line = _final_chart_header_reanchor_line(candidate, page, text)
        if header_line is not None:
            x0, y0, x1, y1 = candidate.bbox
            candidate = Candidate(
                schema_version=candidate.schema_version,
                id=candidate.id,
                kind=candidate.kind,
                page=candidate.page,
                bbox=(
                    min(x0, header_line.rect.x0),
                    min(y0, header_line.rect.y0),
                    x1,
                    y1,
                ),
                preview_text=header_line.text,
                caption=header_line.text,
                thumb_path=candidate.thumb_path,
                meta=candidate.meta,
                features=candidate.features,
            )
            adjusted += 1
            try:
                text = page.get_text("text", clip=fitz.Rect(candidate.bbox))
            except PDF_FIGURE_EXCEPTIONS:
                text = ""
        if _final_chart_candidate_looks_forecast_table(candidate, text):
            pruned += 1
            continue
        if _final_chart_candidate_looks_heading_slice(candidate, text):
            pruned += 1
            continue
        kept.append(candidate)
    return kept, pruned, adjusted
