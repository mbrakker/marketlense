from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional, Tuple

import pymupdf as fitz

from src.contracts.report_assets import FigureExtractRequest, FigureExtractResponse
from src.contracts.run_context import RunContext
from src.utils.logging import log_event
from src.utils.path_utils import safe_path_segment

from ..shared import figure_logger
from ..visual_heuristics import PDF_FIGURE_EXCEPTIONS

def extract_best_figure(
    request: FigureExtractRequest, ctx: RunContext
) -> FigureExtractResponse:
    figure_logger.info(
        log_event(
            ctx,
            role="service",
            event="figure_extract_start",
            module=figure_logger.name,
            fields={
                "pdf_path": request.pdf_path,
                "using_context": bool(
                    request.pdf_context and request.pdf_context.fitz_doc
                ),
            },
        )
    )
    img_path, caption, page = _extract_best_figure_png(
        request.pdf_path,
        request.out_dir,
        request.report_name,
        doc=request.pdf_context.fitz_doc if request.pdf_context else None,
    )
    figure_logger.info(
        log_event(
            ctx,
            role="service",
            event="figure_extract_complete",
            module=figure_logger.name,
            fields={"image_path": img_path or ""},
        )
    )
    return FigureExtractResponse(
        schema_version="1.0",
        image_path=img_path,
        caption=caption,
        page=page,
    )


FIGURE_CAPTION_HINTS = {
    "figure",
    "fig.",
    "exhibit",
    "chart",
    "graph",
    "source",
    "panel",
    "table",
}
FIGURE_METRIC_HINTS = {
    "%",
    "$",
    "growth",
    "share",
    "yoy",
    "cagr",
    "roi",
    "roas",
    "ctr",
    "conversion",
    "revenue",
    "impressions",
    "spend",
    "units",
}
FIGURE_LINE_RX = re.compile(r"\\b(fig(?:ure)?|exhibit|chart)\\b\\s*\\d+", re.I)
FINAL_CHART_BARE_TITLE_RX = re.compile(
    r"^[A-Z][A-Za-z'’.-]*(?:\s+[A-Z][A-Za-z'’.-]*){0,2}$"
)
FINAL_CHART_SOURCE_OR_STATLINK_RX = re.compile(
    r"(?im)(?:^|\n)\s*(?:source:|statlink\b)"
)
FINAL_CHART_YEAR_RX = re.compile(r"\b(?:19|20)\d{2}[a-z]?\b")
FINAL_CHART_NUMBER_RX = re.compile(r"\b\d+(?:\.\d+)?\b")


def _figure_score_text(text: str) -> int:
    if not text:
        return 0
    t = text.lower()
    s = 0
    s += sum(2 for k in FIGURE_CAPTION_HINTS if k in t)
    s += sum(1 for k in FIGURE_METRIC_HINTS if k in t)
    s += min(3, len(re.findall(r"\\d", t)) // 4)
    return s


def _figure_nearest_block_text(
    page: fitz.Page, bbox: fitz.Rect, max_dist: float = 90.0
) -> str:
    best = ("", 0, 1e9)
    for x0, y0, x1, y1, text, *_ in page.get_text("blocks"):
        if not text or text.isspace():
            continue
        rect = fitz.Rect(x0, y0, x1, y1)
        dy = rect.y0 - bbox.y1
        distance = dy if dy >= 0 else abs(dy) + 24
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
) -> Tuple[Optional[str], Optional[str], int]:
    try:
        out_root = Path(out_dir)
        safe_report_name = safe_path_segment(report_name, fallback="report")
        img_dir = out_root / safe_report_name / "assets"
        img_dir.mkdir(parents=True, exist_ok=True)
        best = (None, 0.0, "", -1)

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

                    score = (area**0.9) * (1 + 0.15 * cap_score + 0.10 * prox_bonus)

                    if score > best[1]:
                        pix = fitz.Pixmap(local_doc, xref)
                        if pix.width * pix.height < 80_000:
                            continue
                        if pix.n >= 4:
                            pix = fitz.Pixmap(fitz.csRGB, pix)
                        best = (
                            pix,
                            score,
                            caption or f"Auto-selected image from page {pno + 1}",
                            pno,
                        )
        finally:
            if doc is None and "local_doc" in locals():
                local_doc.close()

        if best[0] is None:
            return None, None, -1

        out_path = img_dir / f"{safe_report_name}.png"
        best[0].save(out_path.as_posix())
        rel = Path(safe_report_name) / "assets" / out_path.name
        return rel.as_posix(), best[2], int(best[3])
    except PDF_FIGURE_EXCEPTIONS:
        return None, None, -1
