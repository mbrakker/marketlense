from __future__ import annotations

# ruff: noqa: E402,F401,F403,F405,F821

from typing import TYPE_CHECKING, Any, List, Optional, Tuple, TypeAlias

import pymupdf as fitz

from ..visual_heuristics import *
from .chart_layout import *
from .panel_detection import *

if TYPE_CHECKING:
    _ChartRect: TypeAlias = Any
    PDF_FIGURE_EXCEPTIONS: tuple[type[BaseException], ...]

    def _image_block_rects(
        page: fitz.Page,
        text_dict: Optional[dict[str, Any]] = None,
    ) -> List[fitz.Rect]: ...

    def _drawing_caption_rects(
        page: fitz.Page,
        *,
        blocks: Optional[List[Tuple[float, float, float, float, str]]] = None,
    ) -> List[Tuple[fitz.Rect, str, fitz.Rect]]: ...

    def _panel_chart_rects(
        page: fitz.Page,
        *,
        text_dict: Optional[dict[str, Any]] = None,
        blocks: Optional[List[Tuple[float, float, float, float, str]]] = None,
    ) -> List[Tuple[fitz.Rect, str, fitz.Rect]]: ...

    def _heading_chart_rects(
        page: fitz.Page,
        *,
        text_dict: Optional[dict[str, Any]] = None,
        blocks: Optional[List[Tuple[float, float, float, float, str]]] = None,
    ) -> List[Tuple[fitz.Rect, str, fitz.Rect]]: ...


def _collect_chart_rects(
    page: fitz.Page,
    *,
    text_dict: Optional[dict[str, Any]] = None,
    blocks: Optional[List[Tuple[float, float, float, float, str]]] = None,
) -> List[_ChartRect]:
    rects: List[_ChartRect] = []
    for xref, *_ in page.get_images(full=True):
        try:
            image_rects = page.get_image_rects(xref)
        except PDF_FIGURE_EXCEPTIONS:
            image_rects = []
        if not image_rects:
            continue
        rects.append(_ChartRect(rect=image_rects[0], kind="xref", xref=xref))
    for rect in _image_block_rects(page, text_dict=text_dict):
        rects.append(_ChartRect(rect=rect, kind="block", xref=None))
    for rect, caption, cap_rect in _drawing_caption_rects(page, blocks=blocks):
        rects.append(
            _ChartRect(
                rect=rect,
                kind="draw",
                xref=None,
                caption=caption,
                caption_rect=cap_rect,
            )
        )
    for rect, caption, cap_rect in _panel_chart_rects(
        page,
        text_dict=text_dict,
        blocks=blocks,
    ):
        rects.append(
            _ChartRect(
                rect=rect,
                kind="panel",
                xref=None,
                caption=caption,
                caption_rect=cap_rect,
            )
        )
    for rect, caption, cap_rect in _heading_chart_rects(
        page,
        text_dict=text_dict,
        blocks=blocks,
    ):
        rects.append(
            _ChartRect(
                rect=rect,
                kind="heading",
                xref=None,
                caption=caption,
                caption_rect=cap_rect,
            )
        )
    return rects


__all__ = ["_collect_chart_rects"]
