from __future__ import annotations
from pathlib import Path
from typing import Iterable, List, Optional
import fitz
from .models import CropItem

def crop_regions(pdf_path: str, out_dir: str, report_name: str, items: Iterable[CropItem], pad: int = 8, doc: Optional[fitz.Document] = None) -> List[str]:
    slices_dir = Path(out_dir) / report_name / "slices"
    slices_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    local_doc = doc or fitz.open(pdf_path)
    try:
        for idx, it in enumerate(items):
            pno = it.page
            x0, y0, x1, y1 = it.bbox
            r = fitz.Rect(x0-pad, y0-pad, x1+pad, y1+pad)
            page = local_doc[pno]
            pix = page.get_pixmap(matrix=fitz.Matrix(2,2), clip=r, alpha=False)
            # First file: {report_name}.png, subsequent: {report_name}1.png, {report_name}2.png, etc.
            if idx == 0:
                filename = f"{report_name}.png"
            else:
                filename = f"{report_name}{idx}.png"
            op = slices_dir / filename
            pix.save(op.as_posix())
            # Return a path relative to the HTML output directory
            rel = Path(report_name) / "slices" / filename
            paths.append(rel.as_posix())
    finally:
        if doc is None:
            local_doc.close()
    return paths
