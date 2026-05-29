from __future__ import annotations

import pymupdf as fitz

from src.services._pdf._table_heuristics.layout import _table_block_is_note_like
from src.services._pdf._table_heuristics.models import _PageTextBlock


def _block(text: str) -> _PageTextBlock:
    return _PageTextBlock(
        rect=fitz.Rect(0, 0, 100, 20),
        text=text,
        lines=1,
        chars=len(text),
        avg_line_len=float(len(text)),
        max_font_size=10.0,
        min_font_size=10.0,
    )


def test_table_note_like_detects_urls_without_arbitrary_doi_substrings() -> None:
    assert _table_block_is_note_like(_block("Source: https://doi.org/10.1000/demo"))
    assert not _table_block_is_note_like(
        _block("This table discusses pseudoi.org metrics without a URL.")
    )
