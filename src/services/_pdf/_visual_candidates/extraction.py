"""Extraction coordination for PDF visual candidates.

This module owns per-page candidate construction, ordering, overlap handling,
and worker orchestration while qualification policies remain in sibling modules.
"""

from __future__ import annotations

from src.services._pdf._visual_candidates._extraction.context import (
    _VisualPageContext,
    _VisualPageCandidateEntry,
    _initial_visual_stats,
    _build_visual_page_context,
    _append_visual_page_candidate,
    _emit_visual_page_candidates,
)

from src.services._pdf._visual_candidates._extraction.sequential import (
    _extract_visuals_sequential,
)

from src.services._pdf._visual_candidates._extraction.workflow import (
    extract_visual_candidates,
)

__all__ = [
    "PANEL_CHART_CONTEXT_TEXT_RATIO_MAX",
    "SMALL_DECORATIVE_RASTER_MAX_AREA_FRAC",
    "SMALL_DECORATIVE_RASTER_MAX_TEXT_CHARS",
    "_VisualPageContext",
    "_VisualPageCandidateEntry",
    "_initial_visual_stats",
    "_build_visual_page_context",
    "_append_visual_page_candidate",
    "_emit_visual_page_candidates",
    "_extract_visuals_sequential",
    "extract_visual_candidates",
]
PANEL_CHART_CONTEXT_TEXT_RATIO_MAX = 0.85
SMALL_DECORATIVE_RASTER_MAX_AREA_FRAC = 0.12
SMALL_DECORATIVE_RASTER_MAX_TEXT_CHARS = 180

__all__ = [
    "_VisualPageContext",
    "_VisualPageCandidateEntry",
    "_initial_visual_stats",
    "_build_visual_page_context",
    "_append_visual_page_candidate",
    "_emit_visual_page_candidates",
    "_extract_visuals_sequential",
    "extract_visual_candidates",
]
