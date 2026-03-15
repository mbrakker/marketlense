from __future__ import annotations

from src.services._pdf.contents import detect_contents_page
from src.services._pdf.crop import (
    apply_crop_refine_bbox,
    crop_regions,
    render_page_for_crop_refine,
    render_preview,
)
from src.services._pdf.figures import collect_candidates, extract_best_figure
from src.services._pdf.text import (
    build_pdf_context,
    check_pdf_eof,
    extract_pdf_info,
    extract_pdf_text,
    render_text_pdf,
    split_pdf_for_ocr,
    sample_pdf_text,
)

__all__ = [
    "apply_crop_refine_bbox",
    "build_pdf_context",
    "check_pdf_eof",
    "collect_candidates",
    "crop_regions",
    "detect_contents_page",
    "extract_best_figure",
    "extract_pdf_info",
    "extract_pdf_text",
    "render_page_for_crop_refine",
    "render_preview",
    "render_text_pdf",
    "split_pdf_for_ocr",
    "sample_pdf_text",
]
