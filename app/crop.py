from __future__ import annotations
from pathlib import Path
from typing import Iterable, Dict, Any, List
import fitz

def crop_regions(pdf_path: str, out_dir: str, items: Iterable[Dict[str, Any]], pad: int = 8) -> List[str]:
    Path(out_dir, "slices").mkdir(parents=True, exist_ok=True)
    paths = []
    with fitz.open(pdf_path) as doc:
        for it in items:
            pno = it["page"]; x0,y0,x1,y1 = it["bbox"]
            r = fitz.Rect(x0-pad, y0-pad, x1+pad, y1+pad)
            page = doc[pno]
            pix = page.get_pixmap(matrix=fitz.Matrix(2,2), clip=r, alpha=False)
            op = Path(out_dir)/"slices"/f"{it['id']}.png"
            pix.save(op.as_posix())
            # Return a path relative to the HTML output directory (so templates use
            # "slices/...png" rather than "out/slices/...png" which causes "out/out/..." links).
            rel = Path("slices") / op.name
            paths.append(rel.as_posix())
    return paths
