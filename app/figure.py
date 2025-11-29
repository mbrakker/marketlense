# app/figure.py
from __future__ import annotations
from pathlib import Path
import re
from typing import Optional, Tuple, List
import fitz  # PyMuPDF

# Keywords & scoring
CAPTION_HINTS = {"figure", "fig.", "exhibit", "chart", "graph", "source", "panel", "table"}
METRIC_HINTS  = {"%", "$", "€", "£", "growth", "share", "yoy", "cagr", "roi", "roas", "ctr", "conversion", "revenue", "impressions", "spend", "units"}
FIGURE_LINE_RX = re.compile(r"\b(fig(?:ure)?|exhibit|chart)\b\s*\d+", re.I)

def _score_text(text: str) -> int:
    if not text: return 0
    t = text.lower()
    s = 0
    s += sum(2 for k in CAPTION_HINTS if k in t)
    s += sum(1 for k in METRIC_HINTS if k in t)
    # bonus for numbers (likely axes/titles)
    s += min(3, len(re.findall(r"\d", t)) // 4)
    return s

def _nearest_block_text(page: fitz.Page, bbox: fitz.Rect, max_dist: float = 90.0) -> str:
    best = ("", 0, 1e9)
    for x0, y0, x1, y1, text, *_ in page.get_text("blocks"):
        if not text or text.isspace(): 
            continue
        rect = fitz.Rect(x0, y0, x1, y1)
        # distance: prefer blocks below or touching
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
    # center-to-center distance
    ac = a.tl + (a.br - a.tl) * 0.5
    bc = b.tl + (b.br - b.tl) * 0.5
    return (ac - bc).magnitude

def extract_best_figure_png(
    pdf_path: str, out_dir: str, file_id: str,
    min_page_area_frac: float = 0.06,   # at least 6% of page area
) -> Tuple[Optional[str], Optional[str]]:
    """
    Returns (relative_png_path, inferred_caption) or (None, None).
    Heuristics try hard to avoid logos/headers and prefer chart-like images.
    """
    try:
        out_root = Path(out_dir); (out_root / "assets").mkdir(parents=True, exist_ok=True)
        best = (None, 0.0, "")  # (pixmap, score, caption)
        best_page = None

        with fitz.open(pdf_path) as doc:
            for pno, page in enumerate(doc):
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
                    # Skip headers/footers
                    if bbox.y0 < top_cut or bbox.y1 > bot_cut:
                        continue

                    area = bbox.get_area()
                    if area / page_area < min_page_area_frac:
                        continue

                    # Aspect filter: avoid ultra-wide banners / super-tall strips
                    aspect = bbox.width / max(1, bbox.height)
                    if not (0.6 <= aspect <= 2.2):
                        continue

                    # Caption score
                    caption = _nearest_block_text(page, bbox)
                    cap_score = _score_text(caption)

                    # Proximity bonus to a "Figure N" line
                    prox_bonus = 0
                    if figure_targets:
                        d = min(_distance(bbox, t) for t in figure_targets)
                        if d < 200: prox_bonus = 3
                        elif d < 350: prox_bonus = 1

                    # Main score: area^0.9 + text cues
                    score = (area ** 0.9) * (1 + 0.15 * cap_score + 0.10 * prox_bonus)

                    # Materialize pixmap only for new best to save memory
                    if score > best[1]:
                        pix = fitz.Pixmap(doc, xref)
                        if pix.width * pix.height < 80_000:  # hard floor
                            continue
                        # convert RGBA → RGB
                        if pix.n >= 4:
                            pix = fitz.Pixmap(fitz.csRGB, pix)
                        best = (pix, score, caption or f"Auto-selected image from page {pno+1}")
                        best_page = pno

        if best[0] is None:
            return None, None

        out_path = out_root / "assets" / f"{file_id}_figure.png"
        best[0].save(out_path.as_posix())
        rel = Path("assets") / out_path.name
        return rel.as_posix(), best[2]
    except Exception:
        return None, None
