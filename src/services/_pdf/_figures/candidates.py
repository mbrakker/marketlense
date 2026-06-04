from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pymupdf as fitz

from src.contracts.candidates import Candidate
from src.contracts.report_assets import (
    ExtractCandidatesRequest,
    ExtractCandidatesResponse,
    PdfCandidateExtractionStats,
    PdfDegradedPage,
)
from src.contracts.run_context import RunContext
from src.utils.logging import log_event
from src.utils.path_utils import safe_path_segment

from ..page_artifacts import PdfPageArtifactCache, create_page_artifact_cache
from ..shared import candidate_logger
from ..table_heuristics import _resolve_candidate_parallel_workers
from ..visual_heuristics import PDF_FIGURE_EXCEPTIONS
from .pruning import (
    _prune_charts_overlapping_ranked_tables,
    _prune_final_chart_candidates,
    _prune_tables_overlapping_chart_panels,
)
from .triage import (
    _CandidatePagePlan,
    _degraded_page_record,
    _plan_candidate_pages,
    _resolve_page_gate_recall_floor,
)

def _extract_charts_sequential(
    pdf_path: str,
    thumbs_dir: str,
    report_name: str,
    save_thumbs: bool = False,
    doc: Optional[fitz.Document] = None,
    pages: Optional[List[int]] = None,
    artifact_cache: Optional[PdfPageArtifactCache] = None,
) -> Tuple[List[Candidate], Dict[str, object]]:
    from ..visual_candidates import _extract_visuals_sequential

    return _extract_visuals_sequential(
        pdf_path,
        thumbs_dir,
        report_name,
        save_thumbs=save_thumbs,
        doc=doc,
        pages=pages,
        artifact_cache=artifact_cache,
    )


def _extract_charts(
    pdf_path: str,
    thumbs_dir: str,
    report_name: str,
    save_thumbs: bool = False,
    doc: Optional[fitz.Document] = None,
    parallel_workers: int = 1,
    pages: Optional[List[int]] = None,
    artifact_cache: Optional[PdfPageArtifactCache] = None,
) -> Tuple[List[Candidate], Dict[str, object]]:
    from ..visual_candidates import extract_visual_candidates

    return extract_visual_candidates(
        pdf_path,
        thumbs_dir,
        report_name,
        save_thumbs=save_thumbs,
        doc=doc,
        parallel_workers=parallel_workers,
        pages=pages,
        artifact_cache=artifact_cache,
    )


def _extract_tables_sequential(
    pdf_path: str,
    max_candidates: int = 0,
    pages: Optional[List[int]] = None,
    artifact_cache: Optional[PdfPageArtifactCache] = None,
) -> Tuple[List[Candidate], Dict[str, object]]:
    from ..table_candidates import _extract_tables_sequential as _run_tables_sequential

    return _run_tables_sequential(
        pdf_path,
        max_candidates=max_candidates,
        pages=pages,
        artifact_cache=artifact_cache,
    )


def _extract_tables(
    pdf_path: str,
    max_candidates: int = 0,
    parallel_workers: int = 1,
    pages: Optional[List[int]] = None,
    doc: Optional[fitz.Document] = None,
    artifact_cache: Optional[PdfPageArtifactCache] = None,
) -> Tuple[List[Candidate], Dict[str, object]]:
    from ..table_candidates import extract_table_candidates

    return extract_table_candidates(
        pdf_path,
        max_candidates=max_candidates,
        parallel_workers=parallel_workers,
        pages=pages,
        doc=doc,
        artifact_cache=artifact_cache,
    )

@dataclass
class _CandidateExtractionArtifacts:
    charts: List[Candidate]
    tables: List[Candidate]
    chart_stats: Dict[str, object]
    table_stats: Dict[str, object]
    chart_ranked_overlap_pruned: int = 0
    table_chart_overlap_pruned: int = 0
    final_chart_fragment_pruned: int = 0
    final_chart_header_reanchored: int = 0


def _initial_chart_candidate_stats() -> Dict[str, object]:
    return {"raw": 0, "kept": 0, "rejected": 0, "reasons": {}}


def _initial_table_candidate_stats() -> Dict[str, object]:
    return {
        "raw_lattice": 0,
        "raw_stream": 0,
        "validated": 0,
        "deduped": 0,
        "rejected": 0,
        "reasons": {},
    }


def _open_candidate_triage_doc(
    pdf_path: str,
    shared_doc: Optional[fitz.Document],
) -> tuple[Optional[fitz.Document], bool]:
    if shared_doc is not None:
        return shared_doc, False
    try:
        return fitz.open(pdf_path), True
    except PDF_FIGURE_EXCEPTIONS:
        return None, False

def _extract_candidate_artifacts(
    request: ExtractCandidatesRequest,
    *,
    triage_doc: Optional[fitz.Document],
    parallel_workers: int,
    page_plan: _CandidatePagePlan,
    artifact_cache: PdfPageArtifactCache,
) -> _CandidateExtractionArtifacts:
    artifacts = _CandidateExtractionArtifacts(
        charts=[],
        tables=[],
        chart_stats=_initial_chart_candidate_stats(),
        table_stats=_initial_table_candidate_stats(),
    )
    if page_plan.chart_pages == [] and page_plan.table_pages == []:
        return artifacts
    safe_report_name = safe_path_segment(request.report_name, fallback="report")
    thumbs = Path(request.out_dir) / safe_report_name / "thumbs"
    artifacts.charts, artifacts.chart_stats = _extract_charts(
        request.pdf_path,
        thumbs.as_posix(),
        safe_report_name,
        save_thumbs=False,
        doc=triage_doc if parallel_workers <= 1 else None,
        parallel_workers=parallel_workers,
        pages=page_plan.chart_pages,
        artifact_cache=artifact_cache,
    )
    artifacts.tables, artifacts.table_stats = _extract_tables(
        request.pdf_path,
        parallel_workers=parallel_workers,
        pages=page_plan.table_pages,
        doc=triage_doc if parallel_workers <= 1 else None,
        artifact_cache=artifact_cache,
    )
    (
        artifacts.charts,
        artifacts.chart_ranked_overlap_pruned,
    ) = _prune_charts_overlapping_ranked_tables(artifacts.charts, artifacts.tables)
    if artifacts.chart_ranked_overlap_pruned:
        artifacts.chart_stats["ranked_table_overlap_pruned"] = (
            artifacts.chart_ranked_overlap_pruned
        )
    (
        artifacts.tables,
        artifacts.table_chart_overlap_pruned,
    ) = _prune_tables_overlapping_chart_panels(artifacts.tables, artifacts.charts)
    if artifacts.table_chart_overlap_pruned:
        artifacts.table_stats["chart_overlap_pruned"] = (
            artifacts.table_chart_overlap_pruned
        )
    return artifacts


def _finalize_chart_collection(
    pdf_path: str,
    *,
    triage_doc: Optional[fitz.Document],
    charts: List[Candidate],
) -> tuple[List[Candidate], int, int]:
    final_doc = triage_doc
    close_doc = False
    if final_doc is None:
        final_doc = fitz.open(pdf_path)
        close_doc = True
    try:
        return _prune_final_chart_candidates(charts, doc=final_doc)
    finally:
        if close_doc and final_doc is not None:
            try:
                final_doc.close()
            except PDF_FIGURE_EXCEPTIONS:
                final_doc = None


def _annotate_degraded_candidates(
    candidates: List[Candidate],
    degraded_pages: List[PdfDegradedPage],
) -> List[Candidate]:
    if not degraded_pages:
        return candidates
    degraded_by_page: Dict[int, List[PdfDegradedPage]] = {}
    for page in degraded_pages:
        degraded_by_page.setdefault(int(page.page), []).append(page)
    annotated: List[Candidate] = []
    for candidate in candidates:
        page_reasons = degraded_by_page.get(int(candidate.page), [])
        if not page_reasons:
            annotated.append(candidate)
            continue
        existing_meta = dict(candidate.meta or {})
        existing_meta["degraded_page_reasons"] = [
            {
                "stage": reason.stage,
                "reason_code": reason.reason_code,
                "policy": reason.policy,
                "message": reason.message,
            }
            for reason in page_reasons
        ]
        annotated.append(
            Candidate(
                schema_version=candidate.schema_version,
                id=candidate.id,
                kind=candidate.kind,
                page=candidate.page,
                bbox=candidate.bbox,
                preview_text=candidate.preview_text,
                caption=candidate.caption,
                thumb_path=candidate.thumb_path,
                meta=existing_meta,
                features=candidate.features,
            )
        )
    return annotated


def collect_candidates(
    request: ExtractCandidatesRequest, ctx: RunContext
) -> ExtractCandidatesResponse:
    parallel_workers = _resolve_candidate_parallel_workers(request.parallel_workers, 8)
    excluded_pages = {
        int(page)
        for page in (request.exclude_page_indices or [])
        if isinstance(page, int) and page >= 0
    }
    candidate_logger.info(
        log_event(
            ctx,
            role="service",
            event="extract_candidates_start",
            module=candidate_logger.name,
            fields={
                "pdf_path": request.pdf_path,
                "using_context": bool(
                    request.pdf_context and request.pdf_context.fitz_doc
                ),
                "parallel_workers": parallel_workers,
                "exclude_page_indices": sorted(excluded_pages),
                "page_gate_enabled": bool(request.page_gate_enabled),
                "page_gate_min_score": round(float(request.page_gate_min_score), 3),
                "page_gate_min_recall_pages": int(
                    request.page_gate_min_recall_pages
                ),
                "page_gate_min_recall_page_fraction": round(
                    float(request.page_gate_min_recall_page_fraction), 3
                ),
            },
        )
    )
    shared_doc = (
        request.pdf_context.fitz_doc
        if request.pdf_context and parallel_workers <= 1
        else None
    )
    triage_doc: Optional[fitz.Document] = None
    close_doc = False
    page_plan = _CandidatePagePlan(
        chart_pages=None,
        table_pages=None,
        excluded_count=0,
        triaged_full_scan_pages=0,
        page_triage_records=[],
        page_triage_skipped_pages=0,
        degraded_pages=[],
    )
    artifact_cache = (
        getattr(request.pdf_context, "page_artifact_cache", None)
        if request.pdf_context is not None
        else None
    ) or create_page_artifact_cache()
    artifacts = _CandidateExtractionArtifacts(
        charts=[],
        tables=[],
        chart_stats=_initial_chart_candidate_stats(),
        table_stats=_initial_table_candidate_stats(),
    )
    candidates: List[Candidate] = []
    try:
        triage_doc, close_doc = _open_candidate_triage_doc(request.pdf_path, shared_doc)
        if triage_doc is not None:
            page_plan = _plan_candidate_pages(
                triage_doc,
                excluded_pages,
                artifact_cache=artifact_cache,
                degraded_page_policy=request.degraded_page_policy,
                page_gate_enabled=request.page_gate_enabled,
                page_gate_min_score=request.page_gate_min_score,
                page_gate_min_recall_pages=request.page_gate_min_recall_pages,
                page_gate_min_recall_page_fraction=(
                    request.page_gate_min_recall_page_fraction
                ),
            )
        artifacts = _extract_candidate_artifacts(
            request,
            triage_doc=triage_doc,
            parallel_workers=parallel_workers,
            page_plan=page_plan,
            artifact_cache=artifact_cache,
        )
        (
            artifacts.charts,
            artifacts.final_chart_fragment_pruned,
            artifacts.final_chart_header_reanchored,
        ) = _finalize_chart_collection(
            request.pdf_path,
            triage_doc=triage_doc,
            charts=artifacts.charts,
        )
        if artifacts.final_chart_fragment_pruned:
            artifacts.chart_stats["final_fragment_pruned"] = (
                artifacts.final_chart_fragment_pruned
            )
        if artifacts.final_chart_header_reanchored:
            artifacts.chart_stats["final_header_reanchored"] = (
                artifacts.final_chart_header_reanchored
            )
        candidates = _annotate_degraded_candidates(
            artifacts.charts + artifacts.tables,
            page_plan.degraded_pages,
        )
    finally:
        if close_doc and triage_doc is not None:
            try:
                triage_doc.close()
            except PDF_FIGURE_EXCEPTIONS as exc:
                page_plan.degraded_pages.append(
                    _degraded_page_record(
                        page=-1,
                        stage="cleanup",
                        reason_code="pdf_candidate_triage_doc_close_failed",
                        policy="include_with_warning",
                        message=str(exc),
                    )
                )
    chart_count = sum(1 for candidate in candidates if candidate.kind == "chart")
    table_count = sum(1 for candidate in candidates if candidate.kind == "table")
    candidate_logger.info(
        log_event(
            ctx,
            role="service",
            event="extract_candidates_complete",
            module=candidate_logger.name,
            fields={
                "count": len(candidates),
                "chart_count": chart_count,
                "table_count": table_count,
                "chart_stats": artifacts.chart_stats,
                "table_stats": artifacts.table_stats,
                "ranked_table_overlap_pruned": artifacts.chart_ranked_overlap_pruned,
                "table_chart_overlap_pruned": artifacts.table_chart_overlap_pruned,
                "excluded_count": page_plan.excluded_count,
                "triaged_full_scan_pages": page_plan.triaged_full_scan_pages,
                "page_triage_evaluated_count": len(page_plan.page_triage_records),
                "page_triage_skipped_count": page_plan.page_triage_skipped_pages,
                "page_triage_threshold": round(float(request.page_gate_min_score), 3),
                "page_triage_recall_floor": _resolve_page_gate_recall_floor(
                    len(page_plan.page_triage_records),
                    min_recall_pages=request.page_gate_min_recall_pages,
                    min_recall_page_fraction=(
                        request.page_gate_min_recall_page_fraction
                    ),
                ),
                "page_triage_records": [
                    {
                        "page": item.page,
                        "score": item.score,
                        "threshold": item.threshold,
                        "action": item.action,
                        "reasons": item.reasons,
                    }
                    for item in page_plan.page_triage_records
                ],
                "degraded_page_count": len(page_plan.degraded_pages),
                "degraded_pages": [
                    {
                        "page": item.page,
                        "stage": item.stage,
                        "reason_code": item.reason_code,
                        "policy": item.policy,
                    }
                    for item in page_plan.degraded_pages
                ],
                "page_artifact_cache": artifact_cache.stats(),
            },
        )
    )
    return ExtractCandidatesResponse(
        schema_version="1.0",
        candidates=candidates,
        stats=PdfCandidateExtractionStats(
            schema_version="1.0",
            degraded_pages=page_plan.degraded_pages,
            triage_failure_count=len(
                [item for item in page_plan.degraded_pages if item.stage == "triage"]
            ),
            extraction_failure_count=len(
                [item for item in page_plan.degraded_pages if item.stage != "triage"]
            ),
            page_triage_records=page_plan.page_triage_records,
            page_triage_evaluated_count=len(page_plan.page_triage_records),
            page_triage_skipped_count=page_plan.page_triage_skipped_pages,
        ),
    )
