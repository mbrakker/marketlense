"""Extraction coordination for PDF visual candidates.

This module owns per-page candidate construction, ordering, overlap handling,
and worker orchestration while qualification policies remain in sibling modules.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, replace
from pathlib import Path
import re
from typing import Dict, List, Optional

import pymupdf as fitz

from src.contracts.candidates import Candidate, CandidateFeatures

from ..page_artifacts import PdfPageArtifactCache, PdfPageArtifacts, get_page_artifacts
from ..visual_heuristics import (
    CHART_CAPTIONED_DRAW_MAX_ASPECT,
    CHART_CAPTION_HINTS,
    CHART_EDGE_TEXT_HEADING_GAP_SCALE,
    CHART_EDGE_TEXT_HEADING_GAP_X_SCALE,
    CHART_MARGIN_FRAC,
    CHART_MARGIN_RELAX_FRAC,
    INFO_CHART_MAX_ASPECT,
    PANEL_CHART_INTERNAL_TITLE_EXTRA_TOP_PAD,
    _adjust_rect_for_text_margins,
    _candidate_index_from_id,
    _caption_near_top,
    _ChartRect,
    _chart_candidate_score,
    _infographic_is_label_dense_not_prose,
    _chart_is_label_dense_not_prose,
    _panel_chart_is_label_dense_not_prose,
    _chart_text_heavy,
    _clamp_bottom_to_next_chart_blocker,
    _clamp_bottom_to_note,
    _clamp_top_to_caption,
    _clamp_top_to_heading,
    _collect_chart_rects,
    _extend_chart_rect_with_adjacent_drawings,
    _expand_rect_into_whitespace,
    _extend_panel_with_adjacent_text_blocks,
    _extend_with_adjacent_text_blocks,
    _extend_with_heading_above,
    _extend_with_note_blocks,
    _find_overlapping_kept,
    _int_count,
    _is_page_number_text,
    _merge_caption_above,
    _merge_stats,
    _nearby_text,
    _nearest_caption_block,
    _nearest_heading_above,
    _note_block_bottom,
    _pad_rect,
    _panel_caption_looks_top_band,
    _panel_chart_has_data_signal,
    _panel_chart_has_compact_stat_card_signal,
    _panel_candidate_shadowed_by_heading_candidate,
    _panel_candidate_shadowed_by_larger_panel,
    _panel_chart_has_structured_card_signal,
    _panel_caption_looks_metric_stub,
    _panel_component_looks_like_guidance_card,
    _panel_component_looks_like_independent_data_panel,
    _panel_neighbor_x_bounds,
    _panel_stacked_bottom_clip_y,
    _panel_should_clamp_to_internal_caption,
    _panel_title_slice_bounds,
    _rect_iou,
    _resolve_candidate_parallel_workers,
    _save_thumb,
    _split_even_chunks,
    _tally_reason,
    _text_stats,
    _trim_top_page_number,
    _VisualCandidateRelationships,
)
from .raster import (
    _RasterProbeCache,
    _candidate_ocr_density,
    _chart_confidence_score,
    _embedded_visual_is_oversized_wrapper,
    _embedded_visual_looks_chart_like,
    _embedded_visual_looks_decorative,
    _embedded_visual_looks_photo_like,
    _embedded_visual_qualifies_contextual_card,
    _embedded_visual_qualifies_relaxed_geometry,
    _has_side_by_side_visual_sibling,
    _visual_probe_profile,
)
from .screening import (
    _SOURCE_OR_STATLINK_RX,
    _caption_has_figure_hint,
    _next_figure_caption_below,
    _page_has_chart_caption_blocks,
    _text_has_visual_context_hint,
    _visual_candidate_looks_bare_heading_fragment,
    _visual_candidate_looks_cover_art,
    _visual_candidate_looks_inline_numbered_panel,
    _visual_candidate_looks_narrative_panel_card,
    _visual_candidate_looks_note_fragment,
    _visual_candidate_looks_photo_narrative_card,
    _visual_candidate_looks_reference_or_prose,
    _visual_candidate_looks_section_opener_banner,
    _visual_candidate_looks_table_like,
    _visual_text_dense_recovery_allowed,
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
    candidate: Candidate,
    final_rect: fitz.Rect,
    score: float,
    local_sequence: int,
    legacy_order_candidate: bool,
    stats: Dict[str, object],
) -> int:
    overlap_index = _find_overlapping_kept(final_rect, kept)
    if overlap_index is not None:
        existing_score = kept[overlap_index][1]
        if score <= existing_score:
            stats["rejected"] = _int_count(stats["rejected"]) + 1
            _tally_reason(stats, "overlap_dup")
            return local_sequence
        page_index = kept[overlap_index][2]
        existing_entry = page_candidates[page_index]
        page_candidates[page_index] = _VisualPageCandidateEntry(
            candidate=candidate,
            rect=final_rect,
            score=score,
            sequence=existing_entry.sequence,
            recovered_only=existing_entry.recovered_only and not legacy_order_candidate,
        )
        kept[overlap_index] = (final_rect, score, page_index)
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


def _extract_visuals_sequential(
    pdf_path: str,
    thumbs_dir: str,
    report_name: str,
    save_thumbs: bool = False,
    doc: Optional[fitz.Document] = None,
    pages: Optional[List[int]] = None,
    artifact_cache: Optional[PdfPageArtifactCache] = None,
) -> tuple[List[Candidate], Dict[str, object]]:
    out: List[Candidate] = []
    stats = _initial_visual_stats()
    local_doc = doc or fitz.open(pdf_path)
    try:
        thumb_index = 0
        page_numbers = pages if pages is not None else list(range(len(local_doc)))
        for pno in page_numbers:
            if pno < 0 or pno >= len(local_doc):
                continue
            page = local_doc[pno]
            page_ctx = _build_visual_page_context(
                page,
                pno,
                stats,
                artifact_cache=artifact_cache,
            )
            if page_ctx is None:
                continue
            kept: List[tuple[fitz.Rect, float, int]] = []
            page_candidates: List[_VisualPageCandidateEntry] = []
            local_sequence = 0
            for rect_item in page_ctx.rect_items:
                stats["raw"] = _int_count(stats["raw"]) + 1
                rect_candidate = rect_item.rect
                base_rect = rect_candidate
                area_frac = rect_candidate.get_area() / page_ctx.page_rect.get_area()
                aspect = rect_candidate.width / max(1, rect_candidate.height)
                cap_rect = rect_item.caption_rect
                cap = rect_item.caption
                if cap_rect is None:
                    cap_rect, cap = _nearest_caption_block(
                        page_ctx.page,
                        rect_candidate,
                        CHART_CAPTION_HINTS,
                        blocks=page_ctx.artifacts.text_blocks,
                    )
                if not cap:
                    cap = _nearby_text(
                        page_ctx.page,
                        rect_candidate,
                        blocks=page_ctx.artifacts.text_blocks,
                    )
                if cap and _is_page_number_text(cap):
                    cap = ""
                cap_lower = (cap or "").lower()
                has_hint = _text_has_visual_context_hint(cap or "")
                has_context_hint = has_hint or rect_item.kind == "panel"
                aspect_max = (
                    INFO_CHART_MAX_ASPECT
                    if rect_item.kind
                    in (
                        "heading",
                        "panel",
                    )
                    else 2.5
                )
                if (
                    rect_item.kind == "draw"
                    and cap_rect is not None
                    and any(cap_lower.startswith(hint) for hint in CHART_CAPTION_HINTS)
                ):
                    aspect_max = max(aspect_max, CHART_CAPTIONED_DRAW_MAX_ASPECT)
                relaxed_image_geometry = False
                contextual_image_card = False
                if (
                    rect_item.kind in ("xref", "block")
                    and not has_hint
                    and not page_ctx.page_has_chart_captions
                ):
                    relaxed_image_geometry = (
                        _embedded_visual_qualifies_relaxed_geometry(
                            page_ctx.page,
                            rect_candidate,
                            area_frac=area_frac,
                            probe_cache=page_ctx.probe_cache,
                        )
                    )
                    contextual_image_card = _embedded_visual_qualifies_contextual_card(
                        page_ctx.page,
                        rect_candidate,
                        area_frac=area_frac,
                        blocks=page_ctx.artifacts.text_blocks,
                        probe_cache=page_ctx.probe_cache,
                    )
                min_aspect = (
                    0.45 if (relaxed_image_geometry or contextual_image_card) else 0.55
                )
                max_aspect = (
                    3.4
                    if (relaxed_image_geometry or contextual_image_card)
                    else aspect_max
                )
                if rect_item.kind == "panel" and aspect > max_aspect:
                    try:
                        pre_geom_panel_text = page_ctx.page.get_text(
                            "text", clip=rect_candidate
                        )
                    except Exception:
                        pre_geom_panel_text = ""
                    if _panel_chart_has_compact_stat_card_signal(pre_geom_panel_text):
                        max_aspect = max(max_aspect, 5.25)
                if area_frac < 0.05 or not (min_aspect <= aspect <= max_aspect):
                    stats["rejected"] = _int_count(stats["rejected"]) + 1
                    _tally_reason(stats, "geometry")
                    continue
                is_infographic = bool(
                    re.match(r"^\s*infographic\b", cap or "", re.IGNORECASE)
                )
                if (
                    rect_candidate.y0 < page_ctx.top_cut
                    or rect_candidate.y1 > page_ctx.bot_cut
                ):
                    if has_context_hint or contextual_image_card:
                        if (
                            rect_candidate.y0 < page_ctx.page_rect.y0 - 2.0
                            or rect_candidate.y1 > page_ctx.page_rect.y1 + 2.0
                        ):
                            stats["rejected"] = _int_count(stats["rejected"]) + 1
                            _tally_reason(stats, "margin")
                            continue
                    elif (
                        rect_candidate.y0 < page_ctx.relaxed_top
                        or rect_candidate.y1 > page_ctx.relaxed_bot
                    ):
                        stats["rejected"] = _int_count(stats["rejected"]) + 1
                        _tally_reason(stats, "margin")
                        continue
                if not has_hint and area_frac < 0.08:
                    stats["rejected"] = _int_count(stats["rejected"]) + 1
                    _tally_reason(stats, "caption_hint")
                    continue
                if (
                    rect_item.kind in ("block", "draw")
                    and not has_context_hint
                    and area_frac < 0.12
                ):
                    stats["rejected"] = _int_count(stats["rejected"]) + 1
                    _tally_reason(stats, "block_small_no_caption")
                    continue
                if (
                    rect_item.kind in ("block", "draw")
                    and not has_context_hint
                    and area_frac > 0.8
                ):
                    stats["rejected"] = _int_count(stats["rejected"]) + 1
                    _tally_reason(stats, "block_full_page_no_caption")
                    continue
                try:
                    raw_bbox_text = page_ctx.page.get_text("text", clip=rect_candidate)
                except Exception:
                    raw_bbox_text = ""
                raw_text_lines, raw_text_chars = _text_stats(raw_bbox_text)
                raw_text_ratio = (
                    (raw_text_chars / page_ctx.page_chars)
                    if page_ctx.page_chars
                    else 0.0
                )
                bbox_text = raw_bbox_text
                text_lines = raw_text_lines
                text_chars = raw_text_chars
                text_ratio = raw_text_ratio
                raw_text_heavy = _chart_text_heavy(
                    raw_text_lines, raw_text_chars, raw_text_ratio
                )
                image_chart_like = False
                image_decorative = False
                image_photo_like = False
                if rect_item.kind in ("xref", "block") and not has_hint:
                    if _embedded_visual_is_oversized_wrapper(
                        rect_item,
                        page_ctx.rect_items,
                        page_ctx.page_rect,
                        relationships=page_ctx.relationships,
                    ):
                        stats["rejected"] = _int_count(stats["rejected"]) + 1
                        _tally_reason(stats, "oversized_wrapper_image")
                        continue
                    image_chart_like = (
                        contextual_image_card
                        or _embedded_visual_looks_chart_like(
                            page_ctx.page,
                            rect_candidate,
                            probe_cache=page_ctx.probe_cache,
                        )
                    )
                    image_photo_like = _embedded_visual_looks_photo_like(
                        page_ctx.page,
                        rect_candidate,
                        probe_cache=page_ctx.probe_cache,
                    )
                    if not image_chart_like:
                        image_decorative = _embedded_visual_looks_decorative(
                            page_ctx.page,
                            rect_candidate,
                            probe_cache=page_ctx.probe_cache,
                        )
                text_dense_recovery_allowed = False
                infographic_dense_recovery_allowed = False
                panel_data_signal = False
                if (
                    rect_item.kind in ("draw", "panel")
                    and cap_rect is not None
                    and raw_text_heavy
                ):
                    try:
                        analysis_rect = _merge_caption_above(
                            rect_candidate,
                            cap_rect,
                            page_ctx.page_rect,
                        )
                        analysis_rect = _clamp_top_to_caption(
                            analysis_rect,
                            cap_rect,
                            page_ctx.page,
                            page_ctx.page_rect,
                        )
                        if rect_item.kind != "panel":
                            analysis_rect = _clamp_bottom_to_next_chart_blocker(
                                page_ctx.page,
                                analysis_rect,
                                cap_rect,
                            )
                        bbox_text = page_ctx.page.get_text("text", clip=analysis_rect)
                    except Exception:
                        bbox_text = raw_bbox_text
                    text_lines, text_chars = _text_stats(bbox_text)
                    text_ratio = (
                        (text_chars / page_ctx.page_chars)
                        if page_ctx.page_chars
                        else 0.0
                    )
                    text_dense_recovery_allowed = _visual_text_dense_recovery_allowed(
                        rect_item.kind,
                        bbox_text,
                        text_lines,
                        text_chars,
                        text_ratio,
                    )
                    if is_infographic:
                        infographic_dense_recovery_allowed = (
                            _infographic_is_label_dense_not_prose(bbox_text)
                            or _infographic_is_label_dense_not_prose(raw_bbox_text)
                        )
                if rect_item.kind == "panel":
                    panel_text = bbox_text if bbox_text else raw_bbox_text
                    panel_data_signal = _panel_chart_has_data_signal(panel_text) or (
                        _panel_component_looks_like_guidance_card(panel_text)
                    )
                    if _panel_candidate_shadowed_by_heading_candidate(
                        rect_item,
                        page_ctx.rect_items,
                        relationships=page_ctx.relationships,
                    ):
                        stats["rejected"] = _int_count(stats["rejected"]) + 1
                        _tally_reason(stats, "panel_shadowed_by_heading")
                        continue
                    if _panel_candidate_shadowed_by_larger_panel(
                        rect_item,
                        page_ctx.rect_items,
                        panel_text,
                        relationships=page_ctx.relationships,
                    ):
                        stats["rejected"] = _int_count(stats["rejected"]) + 1
                        _tally_reason(stats, "panel_shadowed_by_larger_panel")
                        continue
                    if not panel_data_signal and (
                        raw_text_heavy
                        or (
                            raw_text_lines >= 5
                            and raw_text_chars >= 150
                            and raw_text_ratio >= 0.25
                        )
                    ):
                        stats["rejected"] = _int_count(stats["rejected"]) + 1
                        _tally_reason(stats, "panel_no_data_signal")
                        continue
                if rect_item.kind in ("xref", "block") and not has_hint:
                    if (
                        image_photo_like
                        and not contextual_image_card
                        and not relaxed_image_geometry
                    ):
                        stats["rejected"] = _int_count(stats["rejected"]) + 1
                        _tally_reason(stats, "photo_panel")
                        continue
                    if (
                        not image_chart_like
                        and (not cap or len(cap.strip()) < 8)
                        and text_chars <= 8
                        and area_frac < 0.5
                    ):
                        stats["rejected"] = _int_count(stats["rejected"]) + 1
                        _tally_reason(stats, "decorative_image")
                        continue
                    if (
                        not image_chart_like
                        and text_chars <= 8
                        and area_frac <= 0.2
                        and _has_side_by_side_visual_sibling(
                            rect_item,
                            page_ctx.rect_items,
                            page_ctx.page_rect,
                            relationships=page_ctx.relationships,
                        )
                    ):
                        stats["rejected"] = _int_count(stats["rejected"]) + 1
                        _tally_reason(stats, "photo_panel")
                        continue
                    if (
                        rect_item.kind == "xref"
                        and not contextual_image_card
                        and not relaxed_image_geometry
                        and area_frac <= SMALL_DECORATIVE_RASTER_MAX_AREA_FRAC
                        and text_chars <= SMALL_DECORATIVE_RASTER_MAX_TEXT_CHARS
                    ):
                        stats["rejected"] = _int_count(stats["rejected"]) + 1
                        _tally_reason(stats, "small_decorative_image")
                        continue
                    if image_decorative and text_chars <= 24 and area_frac <= 0.5:
                        stats["rejected"] = _int_count(stats["rejected"]) + 1
                        _tally_reason(stats, "decorative_image")
                        continue
                if raw_text_heavy:
                    if (
                        rect_item.kind in ("draw", "panel")
                        and cap_rect is not None
                        and (
                            (has_context_hint and raw_text_ratio <= 0.55)
                            or (
                                rect_item.kind == "panel"
                                and (
                                    (
                                        panel_data_signal
                                        and raw_text_ratio
                                        <= PANEL_CHART_CONTEXT_TEXT_RATIO_MAX
                                    )
                                    or _panel_chart_is_label_dense_not_prose(
                                        bbox_text if bbox_text else raw_bbox_text
                                    )
                                    or _panel_component_looks_like_independent_data_panel(
                                        bbox_text if bbox_text else raw_bbox_text
                                    )
                                    or _panel_chart_has_structured_card_signal(
                                        bbox_text if bbox_text else raw_bbox_text
                                    )
                                )
                            )
                            or text_dense_recovery_allowed
                            or infographic_dense_recovery_allowed
                        )
                    ):
                        pass
                    else:
                        stats["rejected"] = _int_count(stats["rejected"]) + 1
                        _tally_reason(stats, "text_dense")
                        continue
                legacy_order_candidate = not raw_text_heavy or (
                    rect_item.kind in ("draw", "panel")
                    and has_context_hint
                    and raw_text_ratio <= 0.55
                )
                final_rect = rect_candidate
                expanded_with_heading = False
                if cap_rect is not None and has_context_hint:
                    final_rect = _merge_caption_above(
                        final_rect,
                        cap_rect,
                        page_ctx.page_rect,
                    )
                allow_adjacent = rect_item.kind in ("draw", "heading", "panel") or (
                    rect_item.kind == "xref" and has_context_hint
                )
                if allow_adjacent:
                    if rect_item.kind == "panel":
                        panel_min_x = None
                        panel_max_x = None
                        compact_stat_caption = _panel_caption_looks_metric_stub(
                            cap or ""
                        )
                        if (
                            cap_rect is not None
                            and not _caption_has_figure_hint(cap or "")
                            and not compact_stat_caption
                        ):
                            slice_bounds = _panel_title_slice_bounds(
                                page_ctx.page,
                                cap_rect,
                            )
                            if slice_bounds is not None:
                                panel_min_x, panel_max_x = slice_bounds
                                bound_pad = max(
                                    page_ctx.page_rect.width * 0.015,
                                    rect_candidate.width * 0.12,
                                )
                                panel_min_x = max(
                                    page_ctx.page.rect.x0,
                                    min(panel_min_x, rect_candidate.x0),
                                )
                                panel_min_x = max(
                                    panel_min_x,
                                    rect_candidate.x0 - bound_pad,
                                )
                                panel_max_x = min(
                                    page_ctx.page.rect.x1,
                                    max(panel_max_x, rect_candidate.x1),
                                )
                                panel_max_x = min(
                                    panel_max_x,
                                    rect_candidate.x1 + bound_pad,
                                )
                        neighbor_min_x, neighbor_max_x = _panel_neighbor_x_bounds(
                            rect_item,
                            page_ctx.rect_items,
                            page_ctx.page_rect,
                            relationships=page_ctx.relationships,
                        )
                        if neighbor_min_x is not None:
                            panel_min_x = (
                                neighbor_min_x
                                if panel_min_x is None
                                else max(panel_min_x, neighbor_min_x)
                            )
                        if neighbor_max_x is not None:
                            panel_max_x = (
                                neighbor_max_x
                                if panel_max_x is None
                                else min(panel_max_x, neighbor_max_x)
                            )
                        final_rect = _extend_panel_with_adjacent_text_blocks(
                            page_ctx.page,
                            final_rect,
                            min_x=panel_min_x,
                            max_x=panel_max_x,
                        )
                    else:
                        final_rect = _extend_with_adjacent_text_blocks(
                            page_ctx.page,
                            final_rect,
                        )
                    if rect_item.kind == "draw":
                        final_rect = _extend_chart_rect_with_adjacent_drawings(
                            page_ctx.page,
                            final_rect,
                        )
                if not has_hint and rect_item.kind == "heading":
                    expanded = _extend_with_heading_above(page_ctx.page, final_rect)
                    expanded_with_heading = expanded.y0 < final_rect.y0 - 1
                    final_rect = expanded
                if not has_hint and rect_item.kind not in ("heading", "xref", "panel"):
                    head_rect = _nearest_heading_above(page_ctx.page, final_rect)
                    if head_rect is not None:
                        final_rect = final_rect | head_rect
                if rect_item.kind != "xref" or has_hint:
                    final_rect = _pad_rect(final_rect, page_ctx.page_rect)
                if not has_hint and rect_item.kind in ("draw", "heading", "panel"):
                    if rect_item.kind == "heading":
                        final_rect = _adjust_rect_for_text_margins(
                            page_ctx.page,
                            final_rect,
                            gap_scale=CHART_EDGE_TEXT_HEADING_GAP_SCALE,
                            gap_scale_x=CHART_EDGE_TEXT_HEADING_GAP_X_SCALE,
                        )
                        final_rect = _expand_rect_into_whitespace(
                            page_ctx.page,
                            final_rect,
                            allow_top=False,
                        )
                    elif rect_item.kind == "panel":
                        pass
                    else:
                        final_rect = _adjust_rect_for_text_margins(
                            page_ctx.page,
                            final_rect,
                        )
                        final_rect = _expand_rect_into_whitespace(
                            page_ctx.page,
                            final_rect,
                        )
                if (
                    rect_item.kind == "heading"
                    and cap_rect is not None
                    and not expanded_with_heading
                ):
                    final_rect = _clamp_top_to_heading(
                        final_rect,
                        cap_rect,
                        page_ctx.page,
                        page_ctx.page_rect,
                    )
                if not has_hint and rect_item.kind not in ("heading", "xref", "panel"):
                    head_rect = _nearest_heading_above(page_ctx.page, final_rect)
                    if head_rect is not None:
                        final_rect = _clamp_top_to_heading(
                            final_rect,
                            head_rect,
                            page_ctx.page,
                            page_ctx.page_rect,
                        )
                final_rect = _extend_with_note_blocks(page_ctx.page, final_rect)
                if (
                    cap_rect is not None
                    and has_context_hint
                    and cap_rect.y0 < base_rect.y0
                ):
                    final_rect = _clamp_top_to_caption(
                        final_rect,
                        cap_rect,
                        page_ctx.page,
                        page_ctx.page_rect,
                    )
                note_bottom = _note_block_bottom(page_ctx.page, final_rect)
                note_included = note_bottom is not None
                stacked_bottom_clip_y = (
                    _panel_stacked_bottom_clip_y(
                        page_ctx.page,
                        rect_item,
                        page_ctx.rect_items,
                        relationships=page_ctx.relationships,
                    )
                    if rect_item.kind == "panel"
                    else None
                )
                panel_caption_is_top_band = (
                    rect_item.kind == "panel"
                    and cap_rect is not None
                    and _panel_caption_looks_top_band(
                        cap or "",
                        rect=rect_candidate,
                        cap_rect=cap_rect,
                    )
                )
                panel_caption_is_internal_label = (
                    rect_item.kind == "panel"
                    and cap_rect is not None
                    and cap_rect.y0 >= rect_candidate.y0 + 1.0
                    and not _caption_has_figure_hint(cap or "")
                    and not panel_caption_is_top_band
                )
                if note_bottom is not None:
                    final_rect = _clamp_bottom_to_note(
                        page_ctx.page,
                        final_rect,
                        note_bottom,
                        page_ctx.page_rect,
                    )
                if stacked_bottom_clip_y is not None:
                    final_rect.y1 = min(
                        final_rect.y1,
                        max(final_rect.y0 + 24.0, stacked_bottom_clip_y - 8.0),
                    )
                if (
                    rect_item.kind in ("draw", "panel")
                    and cap_rect is not None
                    and text_dense_recovery_allowed
                    and not panel_caption_is_internal_label
                ):
                    final_rect = _clamp_bottom_to_next_chart_blocker(
                        page_ctx.page,
                        final_rect,
                        cap_rect,
                    )
                if cap_rect is not None and _caption_near_top(final_rect, cap_rect):
                    if rect_item.kind == "panel" and panel_caption_is_internal_label:
                        pass
                    elif has_context_hint or rect_item.kind in ("panel", "draw"):
                        final_rect = _clamp_top_to_caption(
                            final_rect,
                            cap_rect,
                            page_ctx.page,
                            page_ctx.page_rect,
                            extra_pad=(
                                PANEL_CHART_INTERNAL_TITLE_EXTRA_TOP_PAD
                                if panel_caption_is_top_band
                                else 0.0
                            ),
                        )
                if cap_rect is not None and _panel_should_clamp_to_internal_caption(
                    rect_item,
                    page_ctx.rect_items,
                    relationships=page_ctx.relationships,
                ):
                    final_rect = _clamp_top_to_caption(
                        final_rect,
                        cap_rect,
                        page_ctx.page,
                        page_ctx.page_rect,
                        extra_pad=PANEL_CHART_INTERNAL_TITLE_EXTRA_TOP_PAD,
                    )
                final_rect = _trim_top_page_number(
                    final_rect,
                    page_ctx.page,
                    cap_rect if has_context_hint else None,
                )
                try:
                    bbox_text = page_ctx.page.get_text("text", clip=final_rect)
                except Exception:
                    bbox_text = ""
                text_lines, text_chars = _text_stats(bbox_text)
                text_ratio = (
                    (text_chars / page_ctx.page_chars) if page_ctx.page_chars else 0.0
                )
                if _visual_candidate_looks_table_like(
                    cap or "",
                    bbox_text,
                    kind=rect_item.kind,
                    panel_data_signal=panel_data_signal,
                ):
                    stats["rejected"] = _int_count(stats["rejected"]) + 1
                    _tally_reason(stats, "table_like_visual")
                    continue
                if _visual_candidate_looks_reference_or_prose(
                    cap or "",
                    bbox_text,
                    text_ratio=text_ratio,
                ):
                    stats["rejected"] = _int_count(stats["rejected"]) + 1
                    _tally_reason(stats, "reference_or_prose_visual")
                    continue
                if _visual_candidate_looks_note_fragment(
                    cap or "",
                    bbox_text,
                    kind=rect_item.kind,
                ):
                    stats["rejected"] = _int_count(stats["rejected"]) + 1
                    _tally_reason(stats, "note_fragment_visual")
                    continue
                if _visual_candidate_looks_bare_heading_fragment(
                    cap or "",
                    bbox_text,
                    kind=rect_item.kind,
                    area_frac=area_frac,
                    aspect=aspect,
                ):
                    stats["rejected"] = _int_count(stats["rejected"]) + 1
                    _tally_reason(stats, "bare_heading_fragment")
                    continue
                if _visual_candidate_looks_cover_art(
                    final_rect,
                    page_ctx.page_rect,
                    cap or "",
                    area_frac=area_frac,
                    text_chars=text_chars,
                ):
                    stats["rejected"] = _int_count(stats["rejected"]) + 1
                    _tally_reason(stats, "front_matter_visual")
                    continue
                if _visual_candidate_looks_photo_narrative_card(
                    page_ctx.page,
                    final_rect,
                    cap or "",
                    caption_rect=cap_rect,
                    kind=rect_item.kind,
                    area_frac=area_frac,
                    aspect=aspect,
                    text_chars=text_chars,
                    panel_data_signal=panel_data_signal,
                    probe_cache=page_ctx.probe_cache,
                ):
                    stats["rejected"] = _int_count(stats["rejected"]) + 1
                    _tally_reason(stats, "photo_panel")
                    continue
                if _visual_candidate_looks_narrative_panel_card(
                    cap or "",
                    bbox_text,
                    kind=rect_item.kind,
                    text_ratio=text_ratio,
                    area_frac=area_frac,
                ):
                    stats["rejected"] = _int_count(stats["rejected"]) + 1
                    _tally_reason(stats, "narrative_panel")
                    continue
                if _visual_candidate_looks_section_opener_banner(
                    final_rect,
                    page_ctx.page_rect,
                    cap or "",
                    bbox_text,
                    kind=rect_item.kind,
                    area_frac=area_frac,
                ):
                    stats["rejected"] = _int_count(stats["rejected"]) + 1
                    _tally_reason(stats, "section_opener_visual")
                    continue
                if _visual_candidate_looks_inline_numbered_panel(
                    cap or "",
                    bbox_text,
                    note_included=note_included,
                    area_frac=area_frac,
                    aspect=aspect,
                ):
                    stats["rejected"] = _int_count(stats["rejected"]) + 1
                    _tally_reason(stats, "inline_numbered_panel")
                    continue
                if (
                    rect_item.kind in ("draw", "heading")
                    and cap_rect is not None
                    and _caption_has_figure_hint(cap or "")
                    and cap_rect.y0
                    <= page_ctx.page_rect.y0 + page_ctx.page_rect.height * 0.1
                    and _SOURCE_OR_STATLINK_RX.search(bbox_text)
                ):
                    next_caption_rect = _next_figure_caption_below(
                        page_ctx.page,
                        cap_rect,
                        blocks=page_ctx.artifacts.text_blocks,
                    )
                else:
                    next_caption_rect = None
                weak_stacked_upper = (
                    next_caption_rect is not None
                    and _SOURCE_OR_STATLINK_RX.search(bbox_text)
                    and text_chars <= 260
                    and not _chart_is_label_dense_not_prose(bbox_text)
                    and not _panel_chart_has_data_signal(bbox_text)
                )
                if next_caption_rect is not None and (
                    final_rect.y1 >= next_caption_rect.y0 - 6.0 or weak_stacked_upper
                ):
                    stats["rejected"] = _int_count(stats["rejected"]) + 1
                    _tally_reason(stats, "stacked_top_figure")
                    continue
                pix = None
                if save_thumbs:
                    render_rect = final_rect
                    if (
                        rect_item.kind == "xref"
                        and rect_item.xref is not None
                        and _rect_iou(render_rect, rect_candidate) >= 0.98
                    ):
                        pix = fitz.Pixmap(local_doc, rect_item.xref)
                        if pix.alpha or (
                            pix.colorspace and pix.colorspace != fitz.csRGB
                        ):
                            pix = fitz.Pixmap(fitz.csRGB, pix)
                    else:
                        try:
                            pix = page_ctx.page.get_pixmap(
                                clip=render_rect,
                                alpha=False,
                            )
                        except Exception:
                            pix = None
                cid = f"chart-{pno}-pending-{local_sequence}"
                thumb = (
                    _save_thumb(pix, thumbs_dir, report_name, thumb_index)
                    if save_thumbs and pix
                    else None
                )
                if save_thumbs and thumb:
                    thumb_path = Path(thumb)
                    rel_thumb = Path(report_name) / "thumbs" / thumb_path.name
                    thumb = rel_thumb.as_posix()
                profile = _visual_probe_profile(
                    page_ctx.page,
                    final_rect,
                    probe_cache=page_ctx.probe_cache,
                )
                visual_entropy = (
                    round(float(profile.get("visual_entropy", 0.0) or 0.0), 3)
                    if profile is not None
                    else 0.0
                )
                chart_confidence = _chart_confidence_score(
                    area_frac=area_frac,
                    has_context_hint=has_context_hint,
                    caption=cap or "",
                    bbox_text=bbox_text,
                    text_lines=text_lines,
                    text_chars=text_chars,
                    note_included=note_included,
                    profile=profile,
                )
                features = CandidateFeatures(
                    schema_version="1.0",
                    area_frac=round(area_frac, 3),
                    aspect=round(aspect, 2),
                    text_lines=text_lines,
                    text_chars=text_chars,
                    text_ratio=round(text_ratio, 3),
                    ocr_density=_candidate_ocr_density(text_chars, area_frac),
                    visual_entropy=visual_entropy,
                    chart_confidence=chart_confidence,
                )
                candidate = Candidate(
                    schema_version="1.0",
                    id=cid,
                    kind="chart",
                    page=pno,
                    bbox=(
                        final_rect.x0,
                        final_rect.y0,
                        final_rect.x1,
                        final_rect.y1,
                    ),
                    preview_text=cap or "",
                    caption=cap,
                    thumb_path=thumb,
                    meta={
                        "area_frac": features.area_frac,
                        "aspect": features.aspect,
                        "text_lines": features.text_lines,
                        "text_chars": features.text_chars,
                        "text_ratio": features.text_ratio,
                        "ocr_density": features.ocr_density,
                        "visual_entropy": features.visual_entropy,
                        "chart_confidence": features.chart_confidence,
                    },
                    features=features,
                )
                score = _chart_candidate_score(
                    area_frac, has_context_hint, cap or "", note_included
                )
                if rect_item.kind == "panel":
                    score += 0.35
                elif rect_item.kind == "draw":
                    score += 0.15
                elif rect_item.kind == "heading":
                    score -= 0.05
                local_sequence = _append_visual_page_candidate(
                    page_candidates=page_candidates,
                    kept=kept,
                    candidate=candidate,
                    final_rect=final_rect,
                    score=score,
                    local_sequence=local_sequence,
                    legacy_order_candidate=legacy_order_candidate,
                    stats=stats,
                )
                if save_thumbs:
                    thumb_index += 1
            _emit_visual_page_candidates(
                out,
                page_number=pno,
                page_candidates=page_candidates,
            )
            probe_stats = page_ctx.probe_cache.stats()
            stats["raster_probe_cache_hits"] = (
                _int_count(stats.get("raster_probe_cache_hits", 0))
                + probe_stats["hits"]
            )
            stats["raster_probe_cache_misses"] = (
                _int_count(stats.get("raster_probe_cache_misses", 0))
                + probe_stats["misses"]
            )
            stats["raster_probe_image_entries"] = (
                _int_count(stats.get("raster_probe_image_entries", 0))
                + probe_stats["image_entries"]
            )
            stats["raster_probe_profile_entries"] = (
                _int_count(stats.get("raster_probe_profile_entries", 0))
                + probe_stats["profile_entries"]
            )
    finally:
        if doc is None:
            local_doc.close()
    return out, stats


def extract_visual_candidates(
    pdf_path: str,
    thumbs_dir: str,
    report_name: str,
    *,
    save_thumbs: bool = False,
    doc: Optional[fitz.Document] = None,
    parallel_workers: int = 1,
    pages: Optional[List[int]] = None,
    artifact_cache: Optional[PdfPageArtifactCache] = None,
) -> tuple[List[Candidate], Dict[str, object]]:
    if save_thumbs:
        return _extract_visuals_sequential(
            pdf_path,
            thumbs_dir,
            report_name,
            save_thumbs=save_thumbs,
            doc=doc,
            pages=pages,
            artifact_cache=artifact_cache,
        )
    if doc is not None:
        all_pages = list(range(len(doc)))
    else:
        temp_doc = fitz.open(pdf_path)
        try:
            all_pages = list(range(len(temp_doc)))
        finally:
            temp_doc.close()
    page_numbers = pages if pages is not None else all_pages
    worker_count = _resolve_candidate_parallel_workers(
        parallel_workers, len(page_numbers)
    )
    if worker_count <= 1 or len(page_numbers) <= 1:
        return _extract_visuals_sequential(
            pdf_path,
            thumbs_dir,
            report_name,
            save_thumbs=save_thumbs,
            doc=doc,
            pages=page_numbers,
            artifact_cache=artifact_cache,
        )
    chunks = _split_even_chunks(page_numbers, worker_count)
    merged_stats: Dict[str, object] = {
        "raw": 0,
        "kept": 0,
        "rejected": 0,
        "reasons": {},
    }
    merged_candidates: List[Candidate] = []
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(
                _extract_visuals_sequential,
                pdf_path,
                thumbs_dir,
                report_name,
                False,
                None,
                chunk,
                artifact_cache,
            ): chunk
            for chunk in chunks
        }
        for future in as_completed(futures):
            chunk_candidates, chunk_stats = future.result()
            merged_candidates.extend(chunk_candidates)
            merged_stats = _merge_stats(merged_stats, chunk_stats)
    merged_candidates.sort(
        key=lambda candidate: (candidate.page, _candidate_index_from_id(candidate.id))
    )
    return merged_candidates, merged_stats
