"""Extraction coordination for PDF visual candidates.

This module owns per-page candidate construction, ordering, overlap handling,
and worker orchestration while qualification policies remain in sibling modules.
"""

from __future__ import annotations

from typing import Dict, List, Optional

import pymupdf as fitz

from src.contracts.candidates import Candidate
from src.services._pdf.page_artifacts import PdfPageArtifactCache
from src.services._pdf.visual_heuristics import (
    _candidate_index_from_id,
    _resolve_candidate_parallel_workers,
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
    # PyMuPDF is not thread-safe, even with separate document handles. Keep the
    # compatibility argument but perform page extraction in the current thread.
    candidates, stats = _extract_visuals_sequential(
        pdf_path,
        thumbs_dir,
        report_name,
        save_thumbs=save_thumbs,
        doc=doc,
        pages=pages,
        artifact_cache=artifact_cache,
    )
    if (
        not save_thumbs
        and pages is not None
        and _resolve_candidate_parallel_workers(parallel_workers, len(pages)) > 1
    ):
        candidates.sort(
            key=lambda candidate: (
                candidate.page,
                _candidate_index_from_id(candidate.id),
            )
        )
    return candidates, stats


__all__ = [
    "extract_visual_candidates",
]
