"""Capability module for table-candidate extraction.

This split keeps `figures.collect_candidates()` as the single service boundary
while isolating pdfplumber/table heuristics into a dedicated upgrade surface.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
import math
from typing import Dict, List, Optional

import numpy as np
import pdfplumber
import pymupdf as fitz
from PIL import ImageFilter

from src.contracts.candidates import Candidate, CandidateFeatures

from .figures import (
    TABLE_SETTINGS_LATTICE,
    TABLE_SETTINGS_STREAM,
    TABLE_DEDUP_IOU,
    TABLE_WIDE_FIGURE_CONTEXT_HORIZONTAL_PAD,
    TABLE_WIDE_FIGURE_CONTEXT_MAX_DIST,
    TABLE_WIDE_FIGURE_CONTEXT_TOP_BAND,
    _TableCandidate,
    _avg_first_col_words,
    _avg_words_per_cell,
    _candidate_index_from_id,
    _cell_is_numeric,
    _col_consistency,
    _dedupe_table_candidates,
    _detect_ranked_table_candidates,
    _expand_table_bbox,
    _extract_text_in_bbox,
    _has_caption_hint,
    _has_figure_context_hint,
    _index_page_ratio,
    _int_count,
    _numeric_char_ratio,
    _row_len_cv,
    _row_nonempty_counts,
    _row_text_lengths,
    _split_even_chunks,
    _resolve_candidate_parallel_workers,
    _s,
    _suppress_pdfminer_warnings,
    _table_preview,
    _table_containment_ratio,
    _table_iou,
    _table_page_text_blocks,
    _table_text_bands,
    _table_quality,
    _table_sort_key,
    _prefer_inner_lattice_table,
    _tally_reason,
    _text_block_stats,
    _text_stats,
    _validate_table_candidate,
)
from .page_artifacts import PdfPageArtifactCache, get_page_artifacts
from .visual_candidates import _render_visual_probe_image, _visual_probe_profile


def _bounded_quality(value: float) -> float:
    if not math.isfinite(value):
        return 0.0
    return min(1.0, max(0.0, value))


def _candidate_ocr_density(text_chars: int, area_frac: float) -> float:
    if text_chars <= 0 or area_frac <= 0.0:
        return 0.0
    return round(float(text_chars) / max(1.0, float(area_frac) * 100.0), 2)


def _table_confidence_score(candidate: _TableCandidate) -> float:
    method_score = {
        "ranked": 0.24,
        "lattice": 0.22,
        "stream": 0.16,
        "full_page_image": 0.18,
    }.get(candidate.method, 0.12)
    structure_score = (
        _bounded_quality(candidate.row_count / 8.0) * 0.16
        + _bounded_quality(candidate.col_count / 5.0) * 0.12
        + _bounded_quality(candidate.col_consistency) * 0.12
    )
    data_score = _bounded_quality(candidate.numeric_ratio / 0.35) * 0.18
    compactness_score = (
        _bounded_quality(1.0 - max(0.0, candidate.avg_words_per_cell - 3.0) / 9.0)
        * 0.1
    )
    area_score = _bounded_quality(candidate.area_frac / 0.16) * 0.08
    return round(
        _bounded_quality(
            method_score
            + structure_score
            + data_score
            + compactness_score
            + area_score
        ),
        3,
    )


def _table_candidate_features(
    candidate: _TableCandidate, *, visual_entropy: float = 0.0
) -> CandidateFeatures:
    return CandidateFeatures(
        schema_version="1.0",
        area_frac=round(candidate.area_frac, 4),
        aspect=round(candidate.aspect, 2),
        text_chars=candidate.text_len,
        rows=candidate.row_count,
        cols=candidate.col_count,
        numeric_ratio=round(candidate.numeric_ratio, 3),
        avg_words_per_cell=round(candidate.avg_words_per_cell, 2),
        ocr_density=_candidate_ocr_density(candidate.text_len, candidate.area_frac),
        visual_entropy=round(float(visual_entropy or 0.0), 3),
        table_confidence=_table_confidence_score(candidate),
        method=candidate.method,
    )


def _table_candidate_meta(
    candidate: _TableCandidate, *, visual_entropy: float = 0.0
) -> dict[str, object]:
    features = _table_candidate_features(candidate, visual_entropy=visual_entropy)
    return {
        "method": features.method,
        "rows": features.rows,
        "cols": features.cols,
        "non_empty_cells": candidate.non_empty_cells,
        "numeric_ratio": features.numeric_ratio,
        "avg_words_per_cell": features.avg_words_per_cell,
        "index_page_ratio": round(candidate.index_page_ratio, 2),
        "text_len": candidate.text_len,
        "area_frac": features.area_frac,
        "aspect": features.aspect,
        "ocr_density": features.ocr_density,
        "visual_entropy": features.visual_entropy,
        "table_confidence": features.table_confidence,
    }


def _mask_run_count(mask: np.ndarray) -> int:
    count = 0
    in_run = False
    for value in mask.tolist():
        if value and not in_run:
            count += 1
            in_run = True
        elif not value:
            in_run = False
    return count


def _full_page_image_table_candidate(
    fitz_page: fitz.Page,
) -> Optional[_TableCandidate]:
    text_dict = fitz_page.get_text("dict")
    if any(block.get("type") == 0 for block in text_dict.get("blocks", [])):
        return None
    images = fitz_page.get_image_info(xrefs=True) or []
    if len(images) != 1:
        return None
    rect = fitz.Rect(images[0]["bbox"]) & fitz_page.rect
    if rect.is_empty:
        return None
    area_frac = rect.get_area() / max(1.0, fitz_page.rect.get_area())
    if area_frac < 0.75:
        return None
    profile = _visual_probe_profile(fitz_page, rect)
    if profile is None:
        return None
    image = _render_visual_probe_image(fitz_page, rect, max_dim_px=420)
    if image is None:
        return None
    gray = np.asarray(image.convert("L"))
    edges = np.asarray(image.convert("L").filter(ImageFilter.FIND_EDGES))
    edge_mask = edges > 40
    row_cov = edge_mask.mean(axis=1)
    col_cov = edge_mask.mean(axis=0)
    row_groups = _mask_run_count(row_cov > 0.08)
    col_groups = _mask_run_count(col_cov > 0.08)
    gray_std = float(gray.std())
    if not (
        profile["white_frac"] <= 0.05
        and profile["sat_mean"] >= 180.0
        and profile["edge_density"] >= 0.12
        and gray_std <= 32.0
        and row_groups >= 20
        and col_groups >= 5
    ):
        return None
    width = max(1.0, rect.width)
    height = max(1.0, rect.height)
    return _TableCandidate(
        bbox=(rect.x0, rect.y0, rect.x1, rect.y1),
        method="image",
        row_count=row_groups,
        col_count=col_groups,
        col_consistency=1.0,
        row_len_cv=0.0,
        non_empty_cells=row_groups * col_groups,
        total_cells=row_groups * col_groups,
        numeric_cells=0,
        numeric_ratio=0.0,
        avg_words_per_cell=0.0,
        avg_first_col_words=0.0,
        index_page_ratio=0.0,
        preview="",
        text="",
        text_len=0,
        line_count=0,
        avg_line_len=0.0,
        text_block_area_frac=0.0,
        text_block_line_count=0,
        text_block_avg_line_len=0.0,
        caption_hint=False,
        figure_context_hint=False,
        wide_figure_context_hint=False,
        area_frac=area_frac,
        width_frac=width / max(1.0, float(fitz_page.rect.width)),
        height_frac=height / max(1.0, float(fitz_page.rect.height)),
        aspect=width / max(1.0, height),
    )


def _find_tables_safe(page: pdfplumber.page.Page, settings: Dict[str, object]):
    try:
        return page.find_tables(table_settings=settings) or []
    except Exception:
        return []


def _build_table_candidate(
    page: pdfplumber.page.Page,
    table: pdfplumber.table.Table,
    method: str,
    fitz_page: Optional[fitz.Page] = None,
    text_blocks: Optional[List[tuple[float, float, float, float, str]]] = None,
) -> Optional[_TableCandidate]:
    try:
        x0, y0, x1, y1 = map(float, table.bbox)
    except Exception:
        return None
    rows: list[list[object]] = []
    try:
        rows = table.extract() or []
    except Exception:
        rows = []
    non_empty_rows = [row for row in rows if row and any(_s(c).strip() for c in row)]
    row_count = len(non_empty_rows)
    col_count = max((len(row) for row in non_empty_rows), default=0)
    row_col_counts = _row_nonempty_counts(rows)
    col_consistency = _col_consistency(row_col_counts)
    row_len_cv = _row_len_cv(_row_text_lengths(rows))
    non_empty_cells = sum(1 for row in non_empty_rows for c in row if _s(c).strip())
    total_cells = sum(len(row) for row in non_empty_rows)
    numeric_cells = sum(
        1 for row in non_empty_rows for c in row if _cell_is_numeric(_s(c))
    )
    numeric_chars, total_chars = _numeric_char_ratio(non_empty_rows)
    numeric_ratio = numeric_chars / max(1, total_chars)
    avg_words_per_cell = _avg_words_per_cell(non_empty_rows)
    avg_first_col_words = _avg_first_col_words(non_empty_rows)
    index_page_ratio = _index_page_ratio(non_empty_rows)
    preview = _table_preview(rows)
    text = _extract_text_in_bbox(page, (x0, y0, x1, y1))
    line_count, text_chars = _text_stats(text)
    avg_line_len = (text_chars / line_count) if line_count else 0.0
    text_len = len(text.strip())
    page_area = max(1.0, float(page.width * page.height))
    width = max(1.0, x1 - x0)
    height = max(1.0, y1 - y0)
    area_frac = (width * height) / page_area
    width_frac = width / max(1.0, float(page.width))
    height_frac = height / max(1.0, float(page.height))
    aspect = width / max(1.0, height)
    text_block_area_frac = 0.0
    text_block_line_count = 0
    text_block_avg_line_len = 0.0
    caption_hint = False
    figure_context_hint = False
    wide_figure_context_hint = False
    if fitz_page is not None:
        caption_hint = _has_caption_hint(fitz_page, (x0, y0, x1, y1))
        figure_context_hint = _has_figure_context_hint(fitz_page, (x0, y0, x1, y1))
        wide_figure_context_hint = _has_figure_context_hint(
            fitz_page,
            (x0, y0, x1, y1),
            max_dist=TABLE_WIDE_FIGURE_CONTEXT_MAX_DIST,
            top_band_height=TABLE_WIDE_FIGURE_CONTEXT_TOP_BAND,
            horizontal_pad=TABLE_WIDE_FIGURE_CONTEXT_HORIZONTAL_PAD,
        )
        text_block_area_frac, text_block_line_count, text_block_avg_line_len = (
            _text_block_stats(
                fitz_page,
                (x0, y0, x1, y1),
                blocks=text_blocks,
            )
        )
    return _TableCandidate(
        bbox=(x0, y0, x1, y1),
        method=method,
        row_count=row_count,
        col_count=col_count,
        col_consistency=col_consistency,
        row_len_cv=row_len_cv,
        non_empty_cells=non_empty_cells,
        total_cells=total_cells,
        numeric_cells=numeric_cells,
        numeric_ratio=numeric_ratio,
        avg_words_per_cell=avg_words_per_cell,
        avg_first_col_words=avg_first_col_words,
        index_page_ratio=index_page_ratio,
        preview=preview[:400],
        text=text,
        text_len=text_len,
        line_count=line_count,
        avg_line_len=avg_line_len,
        text_block_area_frac=text_block_area_frac,
        text_block_line_count=text_block_line_count,
        text_block_avg_line_len=text_block_avg_line_len,
        caption_hint=caption_hint,
        figure_context_hint=figure_context_hint,
        wide_figure_context_hint=wide_figure_context_hint,
        area_frac=area_frac,
        width_frac=width_frac,
        height_frac=height_frac,
        aspect=aspect,
    )


def _extract_tables_sequential(
    pdf_path: str,
    max_candidates: int = 0,
    pages: Optional[List[int]] = None,
    doc: Optional[fitz.Document] = None,
    artifact_cache: Optional[PdfPageArtifactCache] = None,
) -> tuple[List[Candidate], Dict[str, object]]:
    out: List[Candidate] = []
    stats: Dict[str, object] = {
        "raw_lattice": 0,
        "raw_stream": 0,
        "validated": 0,
        "deduped": 0,
        "rejected": 0,
        "reasons": {},
    }
    _suppress_pdfminer_warnings()

    fitz_doc = doc
    close_fitz_doc = False
    if fitz_doc is None:
        try:
            fitz_doc = fitz.open(pdf_path)
            close_fitz_doc = True
        except Exception:
            fitz_doc = None

    try:
        with pdfplumber.open(pdf_path) as pdf:
            page_numbers = pages if pages is not None else list(range(len(pdf.pages)))
            for pno in page_numbers:
                if pno < 0 or pno >= len(pdf.pages):
                    continue
                p = pdf.pages[pno]
                fitz_page = None
                page_artifacts = None
                page_text_blocks = None
                page_text_bands = None
                text_blocks = None
                if fitz_doc is not None and pno < len(fitz_doc):
                    try:
                        fitz_page = fitz_doc[pno]
                        page_artifacts = get_page_artifacts(
                            fitz_page,
                            cache=artifact_cache,
                        )
                        if page_artifacts.full_page_scan_without_text:
                            image_table_candidate = _full_page_image_table_candidate(
                                fitz_page
                            )
                            if image_table_candidate is not None:
                                profile = _visual_probe_profile(
                                    fitz_page,
                                    fitz.Rect(image_table_candidate.bbox),
                                )
                                visual_entropy = (
                                    float(
                                        profile.get("visual_entropy", 0.0) or 0.0
                                    )
                                    if profile is not None
                                    else 0.0
                                )
                                features = _table_candidate_features(
                                    image_table_candidate,
                                    visual_entropy=visual_entropy,
                                )
                                out.append(
                                    Candidate(
                                        schema_version="1.0",
                                        id=f"table-{pno}-0",
                                        kind="table",
                                        page=pno,
                                        bbox=image_table_candidate.bbox,
                                        preview_text="",
                                        caption=None,
                                        thumb_path=None,
                                        meta=_table_candidate_meta(
                                            image_table_candidate,
                                            visual_entropy=visual_entropy,
                                        ),
                                        features=features,
                                    )
                                )
                                continue
                            stats["skipped_pages"] = (
                                _int_count(stats.get("skipped_pages", 0)) + 1
                            )
                            _tally_reason(stats, "page_full_scan_no_text")
                            continue
                    except Exception:
                        fitz_page = None
                        page_artifacts = None
                if fitz_page is not None and page_artifacts is not None:
                    page_text_blocks = _table_page_text_blocks(
                        fitz_page,
                        text_dict=page_artifacts.text_dict,
                    )
                    page_text_bands = _table_text_bands(
                        fitz_page,
                        text_dict=page_artifacts.text_dict,
                    )
                    text_blocks = list(page_artifacts.text_blocks)

                lattice_tables = _find_tables_safe(p, TABLE_SETTINGS_LATTICE)
                stream_tables = _find_tables_safe(p, TABLE_SETTINGS_STREAM)
                stats["raw_lattice"] = _int_count(stats["raw_lattice"]) + len(
                    lattice_tables
                )
                stats["raw_stream"] = _int_count(stats["raw_stream"]) + len(
                    stream_tables
                )

                raw_candidates: list[tuple[pdfplumber.table.Table, str]] = []
                raw_candidates.extend((table, "lattice") for table in lattice_tables)
                raw_candidates.extend((table, "stream") for table in stream_tables)

                validated: List[_TableCandidate] = []
                for table, method in raw_candidates:
                    candidate = _build_table_candidate(
                        p,
                        table,
                        method,
                        fitz_page=fitz_page,
                        text_blocks=text_blocks,
                    )
                    if not candidate:
                        stats["rejected"] = _int_count(stats["rejected"]) + 1
                        _tally_reason(stats, "build_failed")
                        continue
                    ok, reason = _validate_table_candidate(candidate)
                    if not ok:
                        stats["rejected"] = _int_count(stats["rejected"]) + 1
                        _tally_reason(stats, reason or "filtered")
                        continue
                    stats["validated"] = _int_count(stats["validated"]) + 1
                    validated.append(candidate)

                deduped = _dedupe_table_candidates(validated)
                stats["deduped"] = _int_count(stats["deduped"]) + len(deduped)

                final_candidates: List[_TableCandidate] = []
                for candidate in deduped:
                    x0, y0, x1, y1 = candidate.bbox
                    if fitz_page is not None:
                        x0, y0, x1, y1 = _expand_table_bbox(
                            fitz_page,
                            (x0, y0, x1, y1),
                            candidate.method,
                            page_text_blocks=page_text_blocks,
                            page_text_bands=page_text_bands,
                        )
                    final_candidates.append(replace(candidate, bbox=(x0, y0, x1, y1)))
                if fitz_page is not None:
                    image_table_candidate = _full_page_image_table_candidate(fitz_page)
                    if image_table_candidate is not None:
                        final_candidates.append(image_table_candidate)
                    final_candidates.extend(
                        _detect_ranked_table_candidates(
                            p,
                            fitz_page,
                            page_text_blocks=page_text_blocks,
                        )
                    )

                final_deduped: List[_TableCandidate] = []
                for candidate in final_candidates:
                    merged = False
                    for idx, existing in enumerate(final_deduped):
                        iou = _table_iou(candidate.bbox, existing.bbox)
                        containment = _table_containment_ratio(
                            candidate.bbox, existing.bbox
                        )
                        ranked_overlap = containment >= 0.8 and (
                            "ranked" in (candidate.method, existing.method)
                        )
                        if (
                            iou < TABLE_DEDUP_IOU
                            and containment < 0.98
                            and not ranked_overlap
                        ):
                            continue
                        preferred = candidate
                        if containment >= 0.98:
                            area_candidate = max(
                                0.0,
                                (candidate.bbox[2] - candidate.bbox[0])
                                * (candidate.bbox[3] - candidate.bbox[1]),
                            )
                            area_existing = max(
                                0.0,
                                (existing.bbox[2] - existing.bbox[0])
                                * (existing.bbox[3] - existing.bbox[1]),
                            )
                            smaller, larger = (
                                (candidate, existing)
                                if area_candidate <= area_existing
                                else (existing, candidate)
                            )
                            preferred = (
                                smaller
                                if _prefer_inner_lattice_table(smaller, larger)
                                else larger
                            )
                            if _table_quality(candidate) <= _table_quality(existing):
                                preferred = existing
                        elif _table_quality(candidate) <= _table_quality(existing):
                            preferred = existing
                        final_deduped[idx] = preferred
                        merged = True
                        break
                    if not merged:
                        final_deduped.append(candidate)

                for index, candidate in enumerate(
                    sorted(final_deduped, key=_table_sort_key)
                ):
                    x0, y0, x1, y1 = candidate.bbox
                    cid = f"table-{pno}-{index}"
                    profile = (
                        _visual_probe_profile(fitz_page, fitz.Rect(candidate.bbox))
                        if fitz_page is not None
                        else None
                    )
                    visual_entropy = (
                        float(profile.get("visual_entropy", 0.0) or 0.0)
                        if profile is not None
                        else 0.0
                    )
                    features = _table_candidate_features(
                        candidate,
                        visual_entropy=visual_entropy,
                    )
                    out.append(
                        Candidate(
                            schema_version="1.0",
                            id=cid,
                            kind="table",
                            page=pno,
                            bbox=(x0, y0, x1, y1),
                            preview_text=candidate.preview,
                            caption=None,
                            thumb_path=None,
                            meta=_table_candidate_meta(
                                candidate,
                                visual_entropy=visual_entropy,
                            ),
                            features=features,
                        )
                    )
                    if max_candidates > 0 and len(out) >= max_candidates:
                        break

                if max_candidates > 0 and len(out) >= max_candidates:
                    break
    finally:
        if close_fitz_doc and fitz_doc is not None:
            try:
                fitz_doc.close()
            except Exception:
                pass

    return out, stats


def extract_table_candidates(
    pdf_path: str,
    *,
    max_candidates: int = 0,
    parallel_workers: int = 1,
    pages: Optional[List[int]] = None,
    doc: Optional[fitz.Document] = None,
    artifact_cache: Optional[PdfPageArtifactCache] = None,
) -> tuple[List[Candidate], Dict[str, object]]:
    try:
        if doc is not None:
            all_pages = list(range(len(doc)))
        else:
            temp_doc = fitz.open(pdf_path)
            try:
                all_pages = list(range(len(temp_doc)))
            finally:
                temp_doc.close()
    except Exception:
        return _extract_tables_sequential(
            pdf_path,
            max_candidates=max_candidates,
            pages=pages,
            doc=doc,
            artifact_cache=artifact_cache,
        )
    page_numbers = pages if pages is not None else all_pages
    worker_count = _resolve_candidate_parallel_workers(
        parallel_workers, len(page_numbers)
    )
    if worker_count <= 1 or len(page_numbers) <= 1:
        return _extract_tables_sequential(
            pdf_path,
            max_candidates=max_candidates,
            pages=page_numbers,
            doc=doc,
            artifact_cache=artifact_cache,
        )
    chunks = _split_even_chunks(page_numbers, worker_count)
    merged_stats: Dict[str, object] = {
        "raw_lattice": 0,
        "raw_stream": 0,
        "validated": 0,
        "deduped": 0,
        "rejected": 0,
        "reasons": {},
    }
    merged_candidates: List[Candidate] = []
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(
                _extract_tables_sequential,
                pdf_path,
                0,
                chunk,
                None,
                artifact_cache,
            ): chunk
            for chunk in chunks
        }
        for future in as_completed(futures):
            chunk_candidates, chunk_stats = future.result()
            merged_candidates.extend(chunk_candidates)
            for key, value in chunk_stats.items():
                if key == "reasons":
                    reasons = value if isinstance(value, dict) else {}
                    for reason, count in reasons.items():
                        for _ in range(max(0, _int_count(count))):
                            _tally_reason(merged_stats, str(reason))
                    continue
                merged_stats[key] = _int_count(merged_stats.get(key, 0)) + _int_count(
                    value
                )
    merged_candidates.sort(
        key=lambda candidate: (candidate.page, _candidate_index_from_id(candidate.id))
    )
    if max_candidates > 0:
        merged_candidates = merged_candidates[:max_candidates]
    return merged_candidates, merged_stats
