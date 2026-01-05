from __future__ import annotations

import logging
from pathlib import Path
import re
from typing import Optional, Tuple, List

import pymupdf as fitz
from src.contracts.report_assets import FigureExtractRequest, FigureExtractResponse
from src.contracts.run_context import RunContext
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.figure_service")


def extract_best_figure(request: FigureExtractRequest, ctx: RunContext) -> FigureExtractResponse:
    logger.info(log_event(
        ctx,
        role="service",
        event="figure_extract_start",
        module=logger.name,
        fields={"pdf_path": request.pdf_path, "using_context": bool(request.pdf_context and request.pdf_context.fitz_doc)},
    ))
    img_path, caption = _extract_best_figure_png(
        request.pdf_path,
        request.out_dir,
        request.report_name,
        doc=request.pdf_context.fitz_doc if request.pdf_context else None,
    )
    logger.info(log_event(
        ctx,
        role="service",
        event="figure_extract_complete",
        module=logger.name,
        fields={"image_path": img_path or ""},
    ))
    return FigureExtractResponse(schema_version="1.0", image_path=img_path, caption=caption)


CAPTION_HINTS = {"figure", "fig.", "exhibit", "chart", "graph", "source", "panel", "table"}
METRIC_HINTS = {"%", "$", "growth", "share", "yoy", "cagr", "roi", "roas", "ctr", "conversion", "revenue", "impressions", "spend", "units"}
FIGURE_LINE_RX = re.compile(r"\\b(fig(?:ure)?|exhibit|chart)\\b\\s*\\d+", re.I)


def _score_text(text: str) -> int:
    if not text:
        return 0
    t = text.lower()
    s = 0
    s += sum(2 for k in CAPTION_HINTS if k in t)
    s += sum(1 for k in METRIC_HINTS if k in t)
    s += min(3, len(re.findall(r"\\d", t)) // 4)
    return s


def _nearest_block_text(page: fitz.Page, bbox: fitz.Rect, max_dist: float = 90.0) -> str:
    best = ("", 0, 1e9)
    for x0, y0, x1, y1, text, *_ in page.get_text("blocks"):
        if not text or text.isspace():
            continue
        rect = fitz.Rect(x0, y0, x1, y1)
        dy = rect.y0 - bbox.y1
        distance = (dy if dy >= 0 else abs(dy) + 24)
        if distance > max_dist:
            continue
        sc = _score_text(text)
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


def _distance(a: fitz.Rect, b: fitz.Rect) -> float:
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

                    caption = _nearest_block_text(page, bbox)
                    cap_score = _score_text(caption)

                    prox_bonus = 0
                    if figure_targets:
                        d = min(_distance(bbox, t) for t in figure_targets)
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
