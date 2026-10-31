"""Extraction coordination for PDF visual candidates.

This module owns per-page candidate construction, ordering, overlap handling,
and worker orchestration while qualification policies remain in sibling modules.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import pymupdf as fitz

from src.contracts.candidates import Candidate, CandidateFeatures
from src.services._pdf._visual_candidates.raster import (
    _candidate_ocr_density,
    _chart_confidence_score,
    _visual_probe_profile,
)
from src.services._pdf._visual_candidates.screening import (
    _caption_has_figure_hint,
    _text_has_visual_context_hint,
    _visual_text_dense_recovery_allowed,
)
from src.services._pdf.page_artifacts import PdfPageArtifactCache
from src.services._pdf.visual_heuristics import (
    CHART_CAPTION_HINTS,
    CHART_EDGE_TEXT_HEADING_GAP_SCALE,
    CHART_EDGE_TEXT_HEADING_GAP_X_SCALE,
    PANEL_CHART_INTERNAL_TITLE_EXTRA_TOP_PAD,
    _adjust_rect_for_text_margins,
    _caption_near_top,
    _chart_candidate_score,
    _chart_text_heavy,
    _clamp_bottom_to_next_chart_blocker,
    _clamp_bottom_to_note,
    _clamp_top_to_caption,
    _clamp_top_to_heading,
    _expand_rect_into_whitespace,
    _extend_chart_rect_with_adjacent_drawings,
    _extend_panel_with_adjacent_text_blocks,
    _extend_with_adjacent_text_blocks,
    _extend_with_heading_above,
    _extend_with_note_blocks,
    _int_count,
    _is_page_number_text,
    _merge_caption_above,
    _nearby_text,
    _nearest_caption_block,
    _nearest_heading_above,
    _note_block_bottom,
    _pad_rect,
    _panel_caption_looks_like_compact_metric,
    _panel_caption_looks_top_band,
    _panel_neighbor_x_bounds,
    _panel_should_clamp_to_internal_caption,
    _panel_stacked_bottom_clip_y,
    _panel_title_slice_bounds,
    _rect_iou,
    _save_thumb,
    _tally_reason,
    _text_stats,
    _trim_top_page_number,
    _VisualOverlapIndex,
)

from .context import (
    _append_visual_page_candidate,
    _build_visual_page_context,
    _emit_visual_page_candidates,
    _initial_visual_stats,
    _VisualPageCandidateEntry,
)

VISUAL_OVERLAP_INDEX_MIN_KEPT = 8


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
            overlap_index: Optional[_VisualOverlapIndex] = None
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
                has_hint = _text_has_visual_context_hint(cap or "")
                has_context_hint = has_hint or rect_item.kind == "panel"
                if rect_candidate.width <= 0 or rect_candidate.height <= 0:
                    stats["rejected"] = _int_count(stats["rejected"]) + 1
                    _tally_reason(stats, "geometry")
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
                text_dense_recovery_allowed = False
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
                if raw_text_heavy:
                    # Text density is retrieval telemetry only.  Text-heavy
                    # visuals may contain the report's most important tables,
                    # composite metrics or labelled charts; let the visual
                    # model decide their semantic usefulness.
                    _tally_reason(stats, "text_dense_observed")
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
                        compact_stat_caption = _panel_caption_looks_like_compact_metric(
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
                # Caption, text, table, photo and panel semantics are model
                # decisions.  Keep these observations in the candidate set so
                # no viable visual source is removed before visual review.
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
                if overlap_index is None and len(kept) >= VISUAL_OVERLAP_INDEX_MIN_KEPT:
                    overlap_index = _VisualOverlapIndex(page_rect=page_ctx.page_rect)
                    for kept_index, (kept_rect, _score, _page_index) in enumerate(kept):
                        overlap_index.add(kept_index, kept_rect)
                local_sequence = _append_visual_page_candidate(
                    page_candidates=page_candidates,
                    kept=kept,
                    overlap_index=overlap_index,
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


__all__ = [
    "_extract_visuals_sequential",
]
