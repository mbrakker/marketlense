from __future__ import annotations

"""Capability module for chart and infographic candidate extraction.

This split keeps `figures.collect_candidates()` as the single service boundary
while isolating visual-candidate orchestration into its own upgrade surface.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from pathlib import Path
from typing import Dict, List, Optional

import pymupdf as fitz

from src.contracts.candidates import Candidate

from .figures import (
    CHART_CAPTION_HINTS,
    CHART_DENSE_RECOVERY_MIN_CHARS,
    CHART_DENSE_RECOVERY_MIN_LINES,
    CHART_EDGE_TEXT_HEADING_GAP_SCALE,
    CHART_EDGE_TEXT_HEADING_GAP_X_SCALE,
    CHART_MARGIN_FRAC,
    CHART_MARGIN_RELAX_FRAC,
    INFO_CHART_MAX_ASPECT,
    VISUAL_CONTEXT_HINTS,
    _adjust_rect_for_text_margins,
    _candidate_index_from_id,
    _caption_near_top,
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
    _nearest_caption_block,
    _nearest_heading_above,
    _nearby_text,
    _note_block_bottom,
    _pad_rect,
    _rect_iou,
    _resolve_candidate_parallel_workers,
    _save_thumb,
    _split_even_chunks,
    _tally_reason,
    _text_stats,
    _trim_top_page_number,
    _vertical_overlap_ratio,
)
from .page_artifacts import build_page_artifacts, is_full_page_scan_without_text


def _has_side_by_side_visual_sibling(
    rect_item,
    candidates,
    page_rect: fitz.Rect,
) -> bool:
    for other in candidates:
        if other is rect_item:
            continue
        if other.kind not in ("xref", "block"):
            continue
        other_rect = other.rect
        if _vertical_overlap_ratio(other_rect, rect_item.rect) < 0.6:
            continue
        horizontal_gap = max(
            0.0,
            max(rect_item.rect.x0, other_rect.x0) - min(rect_item.rect.x1, other_rect.x1),
        )
        if horizontal_gap > page_rect.width * 0.12:
            continue
        if other_rect.get_area() <= 0.0:
            continue
        area_ratio = rect_item.rect.get_area() / other_rect.get_area()
        if area_ratio < 0.45 or area_ratio > 2.2:
            continue
        return True
    return False


def _visual_text_dense_recovery_allowed(
    kind: str,
    text: str,
    text_lines: int,
    text_chars: int,
    text_ratio: float,
) -> bool:
    return _chart_is_label_dense_not_prose(text) or (
        kind == "panel" and _panel_chart_is_label_dense_not_prose(text)
    ) or (
        text_lines >= CHART_DENSE_RECOVERY_MIN_LINES
        and text_chars >= CHART_DENSE_RECOVERY_MIN_CHARS
        and not _chart_text_heavy(text_lines, text_chars, text_ratio)
    )


def _extract_visuals_sequential(
    pdf_path: str,
    thumbs_dir: str,
    report_name: str,
    save_thumbs: bool = False,
    doc: Optional[fitz.Document] = None,
    pages: Optional[List[int]] = None,
) -> tuple[List[Candidate], Dict[str, object]]:
    out: List[Candidate] = []
    stats: Dict[str, object] = {"raw": 0, "kept": 0, "rejected": 0, "reasons": {}}
    local_doc = doc or fitz.open(pdf_path)
    try:
        thumb_index = 0
        page_numbers = pages if pages is not None else list(range(len(local_doc)))
        for pno in page_numbers:
            if pno < 0 or pno >= len(local_doc):
                continue
            page = local_doc[pno]
            try:
                page_text = page.get_text("text") or ""
            except Exception:
                page_text = ""
            if is_full_page_scan_without_text(page, page_text=page_text):
                stats["skipped_pages"] = _int_count(stats.get("skipped_pages", 0)) + 1
                _tally_reason(stats, "page_full_scan_no_text")
                continue
            artifacts = build_page_artifacts(page)
            page_chars = artifacts.text_char_count
            if page_chars <= 0:
                page_chars = _text_stats(page_text)[1]
            rect = page.rect
            top_cut = rect.y0 + rect.height * CHART_MARGIN_FRAC
            bot_cut = rect.y1 - rect.height * CHART_MARGIN_FRAC
            relaxed_top = rect.y0 + rect.height * CHART_MARGIN_RELAX_FRAC
            relaxed_bot = rect.y1 - rect.height * CHART_MARGIN_RELAX_FRAC
            kept: List[tuple[fitz.Rect, float, int]] = []
            page_candidates: List[Dict[str, object]] = []
            local_sequence = 0
            candidates = _collect_chart_rects(
                page,
                text_dict=artifacts.text_dict,
                blocks=artifacts.text_blocks,
            )
            for rect_item in candidates:
                stats["raw"] = _int_count(stats["raw"]) + 1
                rect_candidate = rect_item.rect
                base_rect = rect_candidate
                area_frac = rect_candidate.get_area() / rect.get_area()
                aspect = rect_candidate.width / max(1, rect_candidate.height)
                aspect_max = (
                    INFO_CHART_MAX_ASPECT
                    if rect_item.kind in ("heading", "panel")
                    else 2.5
                )
                if area_frac < 0.05 or not (0.55 <= aspect <= aspect_max):
                    stats["rejected"] = _int_count(stats["rejected"]) + 1
                    _tally_reason(stats, "geometry")
                    continue
                cap_rect = rect_item.caption_rect
                cap = rect_item.caption
                if cap_rect is None:
                    cap_rect, cap = _nearest_caption_block(
                        page,
                        rect_candidate,
                        CHART_CAPTION_HINTS,
                        blocks=artifacts.text_blocks,
                    )
                if not cap:
                    cap = _nearby_text(
                        page,
                        rect_candidate,
                        blocks=artifacts.text_blocks,
                    )
                if cap and _is_page_number_text(cap):
                    cap = ""
                cap_lower = (cap or "").lower()
                has_hint = any(hint in cap_lower for hint in VISUAL_CONTEXT_HINTS)
                has_context_hint = has_hint or rect_item.kind == "panel"
                is_infographic = "infographic" in cap_lower
                if rect_candidate.y0 < top_cut or rect_candidate.y1 > bot_cut:
                    if (
                        not has_context_hint
                        or rect_candidate.y0 < relaxed_top
                        or rect_candidate.y1 > relaxed_bot
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
                    raw_bbox_text = page.get_text("text", clip=rect_candidate)
                except Exception:
                    raw_bbox_text = ""
                raw_text_lines, raw_text_chars = _text_stats(raw_bbox_text)
                raw_text_ratio = (raw_text_chars / page_chars) if page_chars else 0.0
                bbox_text = raw_bbox_text
                text_lines = raw_text_lines
                text_chars = raw_text_chars
                text_ratio = raw_text_ratio
                raw_text_heavy = _chart_text_heavy(
                    raw_text_lines, raw_text_chars, raw_text_ratio
                )
                text_dense_recovery_allowed = False
                infographic_dense_recovery_allowed = False
                if (
                    rect_item.kind in ("draw", "panel")
                    and cap_rect is not None
                    and raw_text_heavy
                ):
                    try:
                        analysis_rect = _merge_caption_above(rect_candidate, cap_rect, rect)
                        analysis_rect = _clamp_top_to_caption(
                            analysis_rect, cap_rect, page, rect
                        )
                        analysis_rect = _clamp_bottom_to_next_chart_blocker(
                            page, analysis_rect, cap_rect
                        )
                        bbox_text = page.get_text("text", clip=analysis_rect)
                    except Exception:
                        bbox_text = raw_bbox_text
                    text_lines, text_chars = _text_stats(bbox_text)
                    text_ratio = (text_chars / page_chars) if page_chars else 0.0
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
                if rect_item.kind in ("xref", "block") and not has_hint:
                    if (
                        (not cap or len(cap.strip()) < 8)
                        and text_chars <= 8
                        and area_frac < 0.5
                    ):
                        stats["rejected"] = _int_count(stats["rejected"]) + 1
                        _tally_reason(stats, "decorative_image")
                        continue
                    if (
                        text_chars <= 8
                        and area_frac <= 0.2
                        and _has_side_by_side_visual_sibling(
                            rect_item, candidates, rect
                        )
                    ):
                        stats["rejected"] = _int_count(stats["rejected"]) + 1
                        _tally_reason(stats, "photo_panel")
                        continue
                if raw_text_heavy:
                    if (
                        rect_item.kind in ("draw", "panel")
                        and cap_rect is not None
                        and (
                            (has_context_hint and raw_text_ratio <= 0.55)
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
                    final_rect = _merge_caption_above(final_rect, cap_rect, rect)
                allow_adjacent = rect_item.kind in ("draw", "heading", "panel") or (
                    rect_item.kind == "xref" and has_context_hint
                )
                if allow_adjacent:
                    if rect_item.kind == "panel":
                        final_rect = _extend_panel_with_adjacent_text_blocks(
                            page, final_rect
                        )
                    else:
                        final_rect = _extend_with_adjacent_text_blocks(page, final_rect)
                if not has_hint and rect_item.kind == "heading":
                    expanded = _extend_with_heading_above(page, final_rect)
                    expanded_with_heading = expanded.y0 < final_rect.y0 - 1
                    final_rect = expanded
                if not has_hint and rect_item.kind not in ("heading", "xref"):
                    head_rect = _nearest_heading_above(page, final_rect)
                    if head_rect is not None:
                        final_rect = final_rect | head_rect
                if rect_item.kind != "xref" or has_hint:
                    final_rect = _pad_rect(final_rect, rect)
                if not has_hint and rect_item.kind in ("draw", "heading", "panel"):
                    if rect_item.kind == "heading":
                        final_rect = _adjust_rect_for_text_margins(
                            page,
                            final_rect,
                            gap_scale=CHART_EDGE_TEXT_HEADING_GAP_SCALE,
                            gap_scale_x=CHART_EDGE_TEXT_HEADING_GAP_X_SCALE,
                        )
                        final_rect = _expand_rect_into_whitespace(
                            page,
                            final_rect,
                            allow_top=False,
                        )
                    elif rect_item.kind == "panel":
                        pass
                    else:
                        final_rect = _adjust_rect_for_text_margins(page, final_rect)
                        final_rect = _expand_rect_into_whitespace(page, final_rect)
                if (
                    rect_item.kind == "heading"
                    and cap_rect is not None
                    and not expanded_with_heading
                ):
                    final_rect = _clamp_top_to_heading(
                        final_rect, cap_rect, page, rect
                    )
                if not has_hint and rect_item.kind not in ("heading", "xref"):
                    head_rect = _nearest_heading_above(page, final_rect)
                    if head_rect is not None:
                        final_rect = _clamp_top_to_heading(
                            final_rect, head_rect, page, rect
                        )
                final_rect = _extend_with_note_blocks(page, final_rect)
                if (
                    cap_rect is not None
                    and has_context_hint
                    and cap_rect.y0 < base_rect.y0
                ):
                    final_rect = _clamp_top_to_caption(final_rect, cap_rect, page, rect)
                note_bottom = _note_block_bottom(page, final_rect)
                note_included = note_bottom is not None
                if note_bottom is not None:
                    final_rect = _clamp_bottom_to_note(
                        page, final_rect, note_bottom, rect
                    )
                if (
                    rect_item.kind in ("draw", "panel")
                    and cap_rect is not None
                    and text_dense_recovery_allowed
                ):
                    final_rect = _clamp_bottom_to_next_chart_blocker(
                        page, final_rect, cap_rect
                    )
                if cap_rect is not None and _caption_near_top(final_rect, cap_rect):
                    if has_context_hint or rect_item.kind in ("panel", "draw"):
                        final_rect = _clamp_top_to_caption(
                            final_rect, cap_rect, page, rect
                        )
                final_rect = _trim_top_page_number(
                    final_rect, page, cap_rect if has_context_hint else None
                )
                try:
                    bbox_text = page.get_text("text", clip=final_rect)
                except Exception:
                    bbox_text = ""
                text_lines, text_chars = _text_stats(bbox_text)
                text_ratio = (text_chars / page_chars) if page_chars else 0.0
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
                            pix = page.get_pixmap(clip=render_rect, alpha=False)
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
                        "area_frac": round(area_frac, 3),
                        "aspect": round(aspect, 2),
                        "text_lines": text_lines,
                        "text_chars": text_chars,
                        "text_ratio": round(text_ratio, 3),
                    },
                )
                score = _chart_candidate_score(
                    area_frac, has_context_hint, cap or "", note_included
                )
                overlap_index = _find_overlapping_kept(final_rect, kept)
                if overlap_index is not None:
                    existing_score = kept[overlap_index][1]
                    if score <= existing_score:
                        stats["rejected"] = _int_count(stats["rejected"]) + 1
                        _tally_reason(stats, "overlap_dup")
                        continue
                    page_index = kept[overlap_index][2]
                    existing_entry = page_candidates[page_index]
                    page_candidates[page_index] = {
                        "candidate": candidate,
                        "rect": final_rect,
                        "score": score,
                        "sequence": existing_entry["sequence"],
                        "recovered_only": bool(existing_entry["recovered_only"])
                        and not legacy_order_candidate,
                    }
                    kept[overlap_index] = (final_rect, score, page_index)
                    stats["replaced"] = _int_count(stats.get("replaced", 0)) + 1
                else:
                    page_candidates.append(
                        {
                            "candidate": candidate,
                            "rect": final_rect,
                            "score": score,
                            "sequence": local_sequence,
                            "recovered_only": not legacy_order_candidate,
                        }
                    )
                    kept.append((final_rect, score, len(page_candidates) - 1))
                    stats["kept"] = _int_count(stats["kept"]) + 1
                    local_sequence += 1
                if save_thumbs:
                    thumb_index += 1
            page_candidates.sort(
                key=lambda entry: (
                    bool(entry["recovered_only"]),
                    int(entry["sequence"]),
                )
            )
            for local_index, entry in enumerate(page_candidates):
                candidate = entry["candidate"]
                out.append(replace(candidate, id=f"chart-{pno}-{local_index}"))
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
) -> tuple[List[Candidate], Dict[str, object]]:
    if save_thumbs:
        return _extract_visuals_sequential(
            pdf_path,
            thumbs_dir,
            report_name,
            save_thumbs=save_thumbs,
            doc=doc,
            pages=pages,
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
    worker_count = _resolve_candidate_parallel_workers(parallel_workers, len(page_numbers))
    if worker_count <= 1 or len(page_numbers) <= 1:
        return _extract_visuals_sequential(
            pdf_path,
            thumbs_dir,
            report_name,
            save_thumbs=save_thumbs,
            doc=doc,
            pages=page_numbers,
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
