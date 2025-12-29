from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import List, Optional

import pymupdf as fitz
import pdfplumber
from PIL import Image

from src.contracts.candidates import Candidate
from src.contracts.report_assets import ExtractCandidatesRequest, ExtractCandidatesResponse
from src.contracts.run_context import RunContext
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.candidate_extraction_service")

CAPTION_HINTS = ("figure", "fig.", "exhibit", "chart", "graph", "source")


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
) -> List[Candidate]:
    out: List[Candidate] = []
    local_doc = doc or fitz.open(pdf_path)
    try:
        thumb_index = 0
        for pno in range(len(local_doc)):
            page = local_doc[pno]
            rect = page.rect
            top_cut = rect.y0 + rect.height * 0.12
            bot_cut = rect.y1 - rect.height * 0.12
            local = 0
            for xref, *_ in page.get_images(full=True):
                rects = page.get_image_rects(xref)
                if not rects:
                    continue
                r = rects[0]
                if r.y0 < top_cut or r.y1 > bot_cut:
                    continue
                area_frac = r.get_area() / rect.get_area()
                aspect = r.width / max(1, r.height)
                if area_frac < 0.05 or not (0.55 <= aspect <= 2.5):
                    continue
                cap = _nearby_text(page, r)
                if not any(k in (cap or "").lower() for k in CAPTION_HINTS) and area_frac < 0.08:
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
                    meta={"area_frac": round(area_frac, 3), "aspect": round(aspect, 2)},
                ))
                if save_thumbs:
                    thumb_index += 1
                local += 1
    finally:
        if doc is None:
            local_doc.close()
    return out


def _extract_tables(pdf_path: str, max_candidates: int = 10) -> List[Candidate]:
    out: List[Candidate] = []

    def _s(v):
        if v is None:
            return ""
        try:
            return str(v)
        except Exception:
            return ""

    with pdfplumber.open(pdf_path) as pdf:
        for pno, p in enumerate(pdf.pages):
            tables = p.find_tables(table_settings={
                "vertical_strategy": "lines",
                "horizontal_strategy": "lines",
            })

            for i, t in enumerate(tables or []):
                x0, y0, x1, y1 = map(float, t.bbox)
                try:
                    rows = (t.extract() or [])[:3]
                except Exception:
                    rows = []

                preview_lines = []
                for row in rows:
                    if not row:
                        continue
                    preview_lines.append(" | ".join(_s(c) for c in row[:6]))
                preview = "\n".join(preview_lines)[:400]

                cid = f"table-{pno}-{i}"
                out.append(Candidate(
                    schema_version="1.0",
                    id=cid,
                    kind="table",
                    page=pno,
                    bbox=(x0, y0, x1, y1),
                    preview_text=preview,
                    caption=None,
                    thumb_path=None,
                    meta={"rows_peek": len(rows)},
                ))

            if len(out) >= max_candidates:
                break

    return out


def collect_candidates(request: ExtractCandidatesRequest, ctx: RunContext) -> ExtractCandidatesResponse:
    log_event(
        logger,
        ctx,
        role="service",
        event="extract_candidates_start",
        fields={"pdf_path": request.pdf_path},
    )
    thumbs = Path(request.out_dir) / request.report_name / "thumbs"
    candidates = _extract_charts(
        request.pdf_path,
        thumbs.as_posix(),
        request.report_name,
        save_thumbs=False,
        doc=None,
    ) + _extract_tables(request.pdf_path)
    log_event(
        logger,
        ctx,
        role="service",
        event="extract_candidates_complete",
        fields={"count": len(candidates)},
    )
    return ExtractCandidatesResponse(schema_version="1.0", candidates=candidates)
