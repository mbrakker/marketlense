# app/preview.py
from pathlib import Path
import fitz  # PyMuPDF

def first_page_png(pdf_path: str, out_dir: str, file_id: str, dpi: int = 144) -> str | None:
    """
    Render page 1 of PDF to PNG and return a path RELATIVE to the HTML (./out).
    Example returned value: "assets/<file_id>_page1.png"
    """
    try:
        out_root = Path(out_dir)
        out_root.mkdir(parents=True, exist_ok=True)

        img_dir = out_root / "assets"
        img_dir.mkdir(parents=True, exist_ok=True)

        abs_png = img_dir / f"{file_id}_page1.png"

        doc = fitz.open(pdf_path)
        if doc.page_count == 0:
            return None
        page = doc.load_page(0)
        zoom = dpi / 72.0
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        pix.save(abs_png.as_posix())
        doc.close()

        # Return RELATIVE path for use in <img src="..."> inside the HTML in ./out/
        rel_png = Path("assets") / abs_png.name
        return rel_png.as_posix()   # forward slashes for HTML

    except Exception:
        return None
