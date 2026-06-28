"""Extraction coordination for PDF visual candidates.

This module owns per-page candidate construction, ordering, overlap handling,
and worker orchestration while qualification policies remain in sibling modules.
"""

from __future__ import annotations
from dataclasses import dataclass, replace
from typing import Dict, List, Optional
import pymupdf as fitz
from src.contracts.candidates import Candidate
from src.services._pdf.page_artifacts import (
    PdfPageArtifactCache,
    PdfPageArtifacts,
    get_page_artifacts,
)
from src.services._pdf.visual_heuristics import (
    CHART_MARGIN_FRAC,
    CHART_MARGIN_RELAX_FRAC,
    _ChartRect,
    _collect_chart_rects,
    _find_overlapping_kept,
    _int_count,
    _tally_reason,
    _VisualCandidateRelationships,
    _VisualOverlapIndex,
)
from src.services._pdf._visual_candidates.raster import (
    _RasterProbeCache,
)
from src.services._pdf._visual_candidates.screening import (
    _page_has_chart_caption_blocks,
)

PANEL_CHART_CONTEXT_TEXT_RATIO_MAX = 0.85
SMALL_DECORATIVE_RASTER_MAX_AREA_FRAC = 0.12
SMALL_DECORATIVE_RASTER_MAX_TEXT_CHARS = 180


@dataclass(frozen=True)
class _VisualPageContext:
    page_number: int
    page: fitz.Page
    page_rect: fitz.Rect
    page_chars: int
    top_cut: float
    bot_cut: float
    relaxed_top: float
    relaxed_bot: float
    page_has_chart_captions: bool
    artifacts: PdfPageArtifacts
    rect_items: List[_ChartRect]
    relationships: _VisualCandidateRelationships
    probe_cache: _RasterProbeCache


@dataclass
class _VisualPageCandidateEntry:
    candidate: Candidate
    rect: fitz.Rect
    score: float
    sequence: int
    recovered_only: bool


def _initial_visual_stats() -> Dict[str, object]:
    return {"raw": 0, "kept": 0, "rejected": 0, "reasons": {}}


def _build_visual_page_context(
    page: fitz.Page,
    page_number: int,
    stats: Dict[str, object],
    *,
    artifact_cache: Optional[PdfPageArtifactCache] = None,
) -> Optional[_VisualPageContext]:
    artifacts = get_page_artifacts(page, cache=artifact_cache)
    if artifacts.full_page_scan_without_text:
        stats["skipped_pages"] = _int_count(stats.get("skipped_pages", 0)) + 1
        _tally_reason(stats, "page_full_scan_no_text")
        return None
    page_chars = artifacts.text_char_count
    page_rect = page.rect
    rect_items = _collect_chart_rects(
        page,
        text_dict=artifacts.text_dict,
        blocks=artifacts.text_blocks,
    )
    relationship_items = [
        item
        for item in rect_items
        if item.kind in {"xref", "block", "panel", "heading"}
    ]
    return _VisualPageContext(
        page_number=page_number,
        page=page,
        page_rect=page_rect,
        page_chars=page_chars,
        top_cut=page_rect.y0 + page_rect.height * CHART_MARGIN_FRAC,
        bot_cut=page_rect.y1 - page_rect.height * CHART_MARGIN_FRAC,
        relaxed_top=page_rect.y0 + page_rect.height * CHART_MARGIN_RELAX_FRAC,
        relaxed_bot=page_rect.y1 - page_rect.height * CHART_MARGIN_RELAX_FRAC,
        page_has_chart_captions=_page_has_chart_caption_blocks(artifacts.text_blocks),
        artifacts=artifacts,
        rect_items=rect_items,
        relationships=_VisualCandidateRelationships.build(
            relationship_items,
            page_rect=page_rect,
        ),
        probe_cache=_RasterProbeCache(images={}, profiles={}),
    )


def _append_visual_page_candidate(
    *,
    page_candidates: List[_VisualPageCandidateEntry],
    kept: list[tuple[fitz.Rect, float, int]],
    overlap_index: Optional[_VisualOverlapIndex],
    candidate: Candidate,
    final_rect: fitz.Rect,
    score: float,
    local_sequence: int,
    legacy_order_candidate: bool,
    stats: Dict[str, object],
) -> int:
    overlapping_index = _find_overlapping_kept(
        final_rect,
        kept,
        overlap_index=overlap_index,
    )
    if overlapping_index is not None:
        existing_score = kept[overlapping_index][1]
        if score <= existing_score:
            stats["rejected"] = _int_count(stats["rejected"]) + 1
            _tally_reason(stats, "overlap_dup")
            return local_sequence
        page_index = kept[overlapping_index][2]
        existing_entry = page_candidates[page_index]
        page_candidates[page_index] = _VisualPageCandidateEntry(
            candidate=candidate,
            rect=final_rect,
            score=score,
            sequence=existing_entry.sequence,
            recovered_only=existing_entry.recovered_only and not legacy_order_candidate,
        )
        kept[overlapping_index] = (final_rect, score, page_index)
        if overlap_index is not None:
            overlap_index.add(overlapping_index, final_rect)
        stats["replaced"] = _int_count(stats.get("replaced", 0)) + 1
        return local_sequence
    page_candidates.append(
        _VisualPageCandidateEntry(
            candidate=candidate,
            rect=final_rect,
            score=score,
            sequence=local_sequence,
            recovered_only=not legacy_order_candidate,
        )
    )
    kept.append((final_rect, score, len(page_candidates) - 1))
    if overlap_index is not None:
        overlap_index.add(len(kept) - 1, final_rect)
    stats["kept"] = _int_count(stats["kept"]) + 1
    return local_sequence + 1


def _emit_visual_page_candidates(
    out: List[Candidate],
    *,
    page_number: int,
    page_candidates: List[_VisualPageCandidateEntry],
) -> None:
    page_candidates.sort(key=lambda entry: (entry.recovered_only, entry.sequence))
    for local_index, entry in enumerate(page_candidates):
        out.append(replace(entry.candidate, id=f"chart-{page_number}-{local_index}"))


__all__ = [
    "_VisualPageContext",
    "_VisualPageCandidateEntry",
    "_initial_visual_stats",
    "_build_visual_page_context",
    "_append_visual_page_candidate",
    "_emit_visual_page_candidates",
]
