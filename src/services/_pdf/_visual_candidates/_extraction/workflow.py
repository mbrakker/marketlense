"""Extraction coordination for PDF visual candidates.

This module owns per-page candidate construction, ordering, overlap handling,
and worker orchestration while qualification policies remain in sibling modules.
"""

from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional
import pymupdf as fitz
from src.contracts.candidates import Candidate
from src.services._pdf.page_artifacts import PdfPageArtifactCache
from src.services._pdf.visual_heuristics import (
    _candidate_index_from_id,
    _merge_stats,
    _resolve_candidate_parallel_workers,
    _split_even_chunks,
)

from .sequential import (
    _extract_visuals_sequential,
)

PANEL_CHART_CONTEXT_TEXT_RATIO_MAX = 0.85
SMALL_DECORATIVE_RASTER_MAX_AREA_FRAC = 0.12
SMALL_DECORATIVE_RASTER_MAX_TEXT_CHARS = 180


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


__all__ = [
    "extract_visual_candidates",
]
