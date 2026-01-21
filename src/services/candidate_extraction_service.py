from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pymupdf as fitz
import pdfplumber
from PIL import Image

from src.contracts.candidates import Candidate
from src.contracts.report_assets import ExtractCandidatesRequest, ExtractCandidatesResponse
from src.contracts.run_context import RunContext
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.candidate_extraction_service")
_PDFMINER_LOGGERS = ("pdfminer", "pdfminer.pdfinterp", "pdfminer.cmapdb", "pdfminer.layout")

CAPTION_HINTS = ("figure", "fig.", "exhibit", "chart", "graph", "source")
CHART_TEXT_MAX_LINES = 6
CHART_TEXT_MIN_CHARS = 60
CHART_TEXT_RATIO_THRESHOLD = 0.35
TABLE_SETTINGS_LATTICE = {
    "vertical_strategy": "lines",
    "horizontal_strategy": "lines",
}
TABLE_SETTINGS_STREAM = {
    "vertical_strategy": "text",
    "horizontal_strategy": "text",
    "snap_tolerance": 3,
    "join_tolerance": 3,
    "intersection_tolerance": 6,
    "edge_min_length": 3,
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
_PAGE_NUMBER_RX = re.compile(r"^\s*\d{1,4}(?:\s*[–-]\s*\d{1,4})?\s*$")


@dataclass(frozen=True)
class _TableCandidate:
    bbox: Tuple[float, float, float, float]
    method: str
    row_count: int
    col_count: int
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
    area_frac: float
    width_frac: float
    height_frac: float
    aspect: float


def _s(value: object) -> str:
    if value is None:
        return ""
    try:
        return str(value)
    except Exception:
        return ""


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
            top_cut = rect.y0 + rect.height * 0.12
            bot_cut = rect.y1 - rect.height * 0.12
            local = 0
            for xref, *_ in page.get_images(full=True):
                stats["raw"] = int(stats["raw"]) + 1
                rects = page.get_image_rects(xref)
                if not rects:
                    stats["rejected"] = int(stats["rejected"]) + 1
                    _tally_reason(stats, "no_rect")
                    continue
                r = rects[0]
                if r.y0 < top_cut or r.y1 > bot_cut:
                    stats["rejected"] = int(stats["rejected"]) + 1
                    _tally_reason(stats, "margin")
                    continue
                area_frac = r.get_area() / rect.get_area()
                aspect = r.width / max(1, r.height)
                if area_frac < 0.05 or not (0.55 <= aspect <= 2.5):
                    stats["rejected"] = int(stats["rejected"]) + 1
                    _tally_reason(stats, "geometry")
                    continue
                cap = _nearby_text(page, r)
                if not any(k in (cap or "").lower() for k in CAPTION_HINTS) and area_frac < 0.08:
                    stats["rejected"] = int(stats["rejected"]) + 1
                    _tally_reason(stats, "caption_hint")
                    continue
                try:
                    bbox_text = page.get_text("text", clip=r)
                except Exception:
                    bbox_text = ""
                text_lines, text_chars = _text_stats(bbox_text)
                text_ratio = (text_chars / page_chars) if page_chars else 0.0
                if _chart_text_heavy(text_lines, text_chars, text_ratio):
                    stats["rejected"] = int(stats["rejected"]) + 1
                    _tally_reason(stats, "text_dense")
                    continue
                pix = fitz.Pixmap(local_doc, xref)
                if pix.alpha or (pix.colorspace and pix.colorspace != fitz.csRGB):
                    pix = fitz.Pixmap(fitz.csRGB, pix)
                cid = f"chart-{pno}-{local}"
                thumb = _save_thumb(pix, thumbs_dir, report_name, thumb_index) if save_thumbs else None
                if save_thumbs and thumb:
                    thumb_path = Path(thumb)
                    rel_thumb = Path(report_name) / "thumbs" / thumb_path.name
                    thumb = rel_thumb.as_posix()
                out.append(Candidate(
                    schema_version="1.0",
                    id=cid,
                    kind="chart",
                    page=pno,
                    bbox=(r.x0, r.y0, r.x1, r.y1),
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
                ))
                if save_thumbs:
                    thumb_index += 1
                stats["kept"] = int(stats["kept"]) + 1
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

    with pdfplumber.open(pdf_path) as pdf:
        for pno, p in enumerate(pdf.pages):
            lattice_tables = _find_tables_safe(p, TABLE_SETTINGS_LATTICE)
            stream_tables = _find_tables_safe(p, TABLE_SETTINGS_STREAM)
            stats["raw_lattice"] = int(stats["raw_lattice"]) + len(lattice_tables)
            stats["raw_stream"] = int(stats["raw_stream"]) + len(stream_tables)

            raw_candidates = []
            raw_candidates.extend((t, "lattice") for t in lattice_tables)
            raw_candidates.extend((t, "stream") for t in stream_tables)

            validated: List[_TableCandidate] = []
            for t, method in raw_candidates:
                cand = _build_table_candidate(p, t, method)
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
    text_len = len(text.strip())
    page_area = max(1.0, float(page.width * page.height))
    width = max(1.0, x1 - x0)
    height = max(1.0, y1 - y0)
    area_frac = (width * height) / page_area
    width_frac = width / max(1.0, float(page.width))
    height_frac = height / max(1.0, float(page.height))
    aspect = width / max(1.0, height)
    return _TableCandidate(
        bbox=(x0, y0, x1, y1),
        method=method,
        row_count=row_count,
        col_count=col_count,
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


def _cell_is_page_number(text: str) -> bool:
    return bool(_PAGE_NUMBER_RX.match(text))


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
    return True, ""


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
    logger.info(log_event(
        ctx,
        role="service",
        event="extract_candidates_start",
        module=logger.name,
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
    logger.info(log_event(
        ctx,
        role="service",
        event="extract_candidates_complete",
        module=logger.name,
        fields={
            "count": len(candidates),
            "chart_count": len(charts),
            "table_count": len(tables),
            "chart_stats": chart_stats,
            "table_stats": table_stats,
        },
    ))
    return ExtractCandidatesResponse(schema_version="1.0", candidates=candidates)
