from __future__ import annotations

"""Capability module for table-candidate extraction.

This split keeps `figures.collect_candidates()` as the single service boundary
while isolating pdfplumber/table heuristics into a dedicated upgrade surface.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional

import pdfplumber
import pymupdf as fitz

from src.contracts.candidates import Candidate

from .figures import (
    TABLE_SETTINGS_LATTICE,
    TABLE_SETTINGS_STREAM,
    _TableCandidate,
    _avg_first_col_words,
    _avg_words_per_cell,
    _candidate_index_from_id,
    _cell_is_numeric,
    _col_consistency,
    _dedupe_table_candidates,
    _expand_table_bbox,
    _extract_text_in_bbox,
    _has_caption_hint,
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
    _table_sort_key,
    _tally_reason,
    _text_block_stats,
    _text_stats,
    _validate_table_candidate,
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
    if fitz_page is not None:
        caption_hint = _has_caption_hint(fitz_page, (x0, y0, x1, y1))
        text_block_area_frac, text_block_line_count, text_block_avg_line_len = (
            _text_block_stats(
                fitz_page,
                (x0, y0, x1, y1),
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
        area_frac=area_frac,
        width_frac=width_frac,
        height_frac=height_frac,
        aspect=aspect,
    )


def _extract_tables_sequential(
    pdf_path: str,
    max_candidates: int = 0,
    pages: Optional[List[int]] = None,
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

    fitz_doc = None
    try:
        fitz_doc = fitz.open(pdf_path)
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
                if fitz_doc is not None and pno < len(fitz_doc):
                    try:
                        fitz_page = fitz_doc[pno]
                    except Exception:
                        fitz_page = None

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
                        p, table, method, fitz_page=fitz_page
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

                for index, candidate in enumerate(sorted(deduped, key=_table_sort_key)):
                    x0, y0, x1, y1 = candidate.bbox
                    if fitz_page is not None:
                        x0, y0, x1, y1 = _expand_table_bbox(
                            fitz_page, (x0, y0, x1, y1), candidate.method
                        )
                    cid = f"table-{pno}-{index}"
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
                            meta={
                                "method": candidate.method,
                                "rows": candidate.row_count,
                                "cols": candidate.col_count,
                                "non_empty_cells": candidate.non_empty_cells,
                                "numeric_ratio": round(candidate.numeric_ratio, 3),
                                "avg_words_per_cell": round(
                                    candidate.avg_words_per_cell, 2
                                ),
                                "index_page_ratio": round(
                                    candidate.index_page_ratio, 2
                                ),
                                "text_len": candidate.text_len,
                                "area_frac": round(candidate.area_frac, 4),
                                "aspect": round(candidate.aspect, 2),
                            },
                        )
                    )
                    if max_candidates > 0 and len(out) >= max_candidates:
                        break

                if max_candidates > 0 and len(out) >= max_candidates:
                    break
    finally:
        if fitz_doc is not None:
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
) -> tuple[List[Candidate], Dict[str, object]]:
    try:
        temp_doc = fitz.open(pdf_path)
        try:
            page_count = len(temp_doc)
        finally:
            temp_doc.close()
    except Exception:
        return _extract_tables_sequential(pdf_path, max_candidates=max_candidates)
    worker_count = _resolve_candidate_parallel_workers(parallel_workers, page_count)
    if worker_count <= 1 or page_count <= 1:
        return _extract_tables_sequential(pdf_path, max_candidates=max_candidates)
    chunks = _split_even_chunks(list(range(page_count)), worker_count)
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
            executor.submit(_extract_tables_sequential, pdf_path, 0, chunk): chunk
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
