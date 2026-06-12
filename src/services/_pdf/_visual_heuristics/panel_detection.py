"""Panel candidate coordination behind the PDF visual-heuristics facade."""

from __future__ import annotations

from typing import Any

from ._panel_detection import candidates as _candidates
from ._panel_detection import shadowing as _shadowing

_CANDIDATE_EXPORTS = {
    "_merge_panel_title_band_candidates",
    "_page_looks_like_contents_layout",
    "_panel_chart_rects",
}
_SHADOWING_EXPORTS = {
    "_panel_candidate_shadowed_by_heading_candidate",
    "_panel_candidate_shadowed_by_larger_panel",
    "_panel_neighbor_x_bounds",
    "_panel_should_clamp_to_internal_caption",
    "_panel_stacked_bottom_clip_y",
}


def __getattr__(name: str) -> Any:
    if name in _CANDIDATE_EXPORTS:
        return getattr(_candidates, name)
    if name in _SHADOWING_EXPORTS:
        return getattr(_shadowing, name)
    raise AttributeError(name)


__all__ = [
    "_panel_should_clamp_to_internal_caption",
    "_panel_candidate_shadowed_by_heading_candidate",
    "_panel_candidate_shadowed_by_larger_panel",
    "_panel_stacked_bottom_clip_y",
    "_panel_neighbor_x_bounds",
    "_page_looks_like_contents_layout",
    "_panel_chart_rects",
    "_merge_panel_title_band_candidates",
]
