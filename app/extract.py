from __future__ import annotations
from pathlib import Path
from typing import List
import fitz, pdfplumber
from PIL import Image
import io
from .candidates import Candidate

CAPTION_HINTS = ("figure","fig.","exhibit","chart","graph","source")

def _save_thumb(pix: fitz.Pixmap, out_dir: str, name: str, max_w: int = 480) -> str:
    # Ensure RGB (no alpha / no CMYK)
    if pix.alpha:                       # has alpha channel
        pix = fitz.Pixmap(fitz.csRGB, pix)
    elif pix.colorspace and pix.colorspace != fitz.csRGB:
        pix = fitz.Pixmap(fitz.csRGB, pix)

    # Get PNG bytes directly from PyMuPDF (robust vs. colorspaces)
    png_bytes = pix.tobytes("png")
    img = Image.open(io.BytesIO(png_bytes)).convert("RGB")

    if img.width > max_w:
        new_h = int(img.height * max_w / img.width)
        img = img.resize((max_w, new_h), Image.LANCZOS)

    Path(out_dir).mkdir(parents=True, exist_ok=True)
    p = Path(out_dir) / f"{name}.png"
    img.save(p.as_posix(), format="PNG")
    return p.as_posix()

def _nearby_text(page: fitz.Page, rect: fitz.Rect, max_dist: float = 90) -> str:
    best = ("", 1e9)
    for x0,y0,x1,y1,text,*_ in page.get_text("blocks"):
        if not text: continue
        r = fitz.Rect(x0,y0,x1,y1)
        dy = r.y0 - rect.y1
        dist = (dy if dy >= 0 else abs(dy) + 24)
        if dist <= max_dist and dist < best[1]:
            best = (text.strip(), dist)
    return best[0]

def extract_charts(pdf_path: str, thumbs_dir: str) -> List[Candidate]:
    out: List[Candidate] = []
    with fitz.open(pdf_path) as doc:
        for pno in range(len(doc)):
            page = doc[pno]; rect = page.rect
            top_cut = rect.y0 + rect.height * 0.12
            bot_cut = rect.y1 - rect.height * 0.12
            local = 0
            for xref,*_ in page.get_images(full=True):
                rects = page.get_image_rects(xref)
                if not rects: continue
                r = rects[0]
                if r.y0 < top_cut or r.y1 > bot_cut: continue
                area_frac = r.get_area()/rect.get_area()
                aspect = r.width/max(1,r.height)
                if area_frac < 0.05 or not (0.55 <= aspect <= 2.5): continue
                cap = _nearby_text(page, r)
                if not any(k in (cap or "").lower() for k in CAPTION_HINTS) and area_frac < 0.08:
                    continue
                pix = fitz.Pixmap(doc, xref)
                if pix.alpha or (pix.colorspace and pix.colorspace != fitz.csRGB):
                    pix = fitz.Pixmap(fitz.csRGB, pix)
                cid = f"chart-{pno}-{local}"
                thumb = _save_thumb(pix, thumbs_dir, cid)
                out.append(Candidate(
                    id=cid, kind="chart", page=pno,
                    bbox=(r.x0,r.y0,r.x1,r.y1),
                    preview_text=cap or "", caption=cap, thumb_path=thumb,
                    meta={"area_frac": round(area_frac,3), "aspect": round(aspect,2)}
                ))
                local += 1
    return out

def extract_tables(pdf_path: str, max_candidates: int = 10) -> List[Candidate]:
    out: List[Candidate] = []

    def _s(v):  # normalize any cell to string (avoid None in join)
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
                "horizontal_strategy": "lines"
            })

            for i, t in enumerate(tables or []):
                # bbox values can be Decimals; cast to float
                x0, y0, x1, y1 = map(float, t.bbox)

                # t.extract() may return None or mixed types (None cells)
                try:
                    rows = (t.extract() or [])[:3]
                except Exception:
                    rows = []

                # Build a compact preview (first 3 rows, first 6 cols), coercing cells to str
                preview_lines = []
                for row in rows:
                    if not row:
                        continue
                    preview_lines.append(" | ".join(_s(c) for c in row[:6]))
                preview = "\n".join(preview_lines)[:400]

                cid = f"table-{pno}-{i}"
                out.append(Candidate(
                    id=cid,
                    kind="table",
                    page=pno,
                    bbox=(x0, y0, x1, y1),
                    preview_text=preview,
                    caption=None,
                    thumb_path=None,
                    meta={"rows_peek": len(rows)}
                ))

            if len(out) >= max_candidates:
                break

    return out

def collect_candidates(pdf_path: str, work_dir: str):
    thumbs = Path(work_dir)/"thumbs"
    return extract_charts(pdf_path, thumbs.as_posix()) + extract_tables(pdf_path)
