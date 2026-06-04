from __future__ import annotations

import math
import re
from dataclasses import dataclass, replace
from typing import List, Optional

import pymupdf as fitz

from src.contracts.report_assets import (
    PdfCandidatePageTriageRecord,
    PdfDegradedPage,
)
from src.utils.errors import AppError

from ..page_artifacts import PdfPageArtifactCache, get_page_artifacts
from ..visual_heuristics import CAPTION_HINTS, PDF_FIGURE_EXCEPTIONS

PDF_FIGURE_TRIAGE_EXCEPTIONS = (AppError,) + PDF_FIGURE_EXCEPTIONS

VISUAL_CONTEXT_HINTS = CAPTION_HINTS + ("infographic",)

@dataclass(frozen=True)
class _CandidatePagePlan:
    chart_pages: Optional[List[int]]
    table_pages: Optional[List[int]]
    excluded_count: int
    triaged_full_scan_pages: int
    page_triage_records: List[PdfCandidatePageTriageRecord]
    page_triage_skipped_pages: int
    degraded_pages: List[PdfDegradedPage]


@dataclass(frozen=True)
class _CandidatePageScore:
    page: int
    score: float
    reasons: tuple[str, ...]
    text_chars: int
    text_blocks: int
    image_blocks: int
    drawing_count: int

def _candidate_page_text(artifacts) -> str:
    return "\n".join(
        str(block[4] or "").strip()
        for block in artifacts.text_blocks
        if str(block[4] or "").strip()
    )


def _candidate_page_drawing_count(page: fitz.Page) -> int:
    try:
        return len(page.get_drawings() or [])
    except PDF_FIGURE_TRIAGE_EXCEPTIONS:
        return 0


def _candidate_page_image_area_fraction(page: fitz.Page, artifacts) -> float:
    page_area = max(1.0, float(page.rect.get_area()))
    image_area = sum(max(0.0, float(rect.get_area())) for rect in artifacts.image_block_rects)
    return min(1.0, image_area / page_area)


def _candidate_page_numeric_line_count(text: str) -> int:
    numeric_lines = 0
    for line in str(text or "").splitlines():
        numeric_tokens = re.findall(r"\b\d+(?:[.,]\d+)?%?\b", line)
        if len(numeric_tokens) >= 2:
            numeric_lines += 1
    return numeric_lines


def _score_candidate_page(
    page: fitz.Page,
    artifacts,
) -> _CandidatePageScore:
    text = _candidate_page_text(artifacts)
    text_lower = text.casefold()
    drawing_count = _candidate_page_drawing_count(page)
    image_area_frac = _candidate_page_image_area_fraction(page, artifacts)
    numeric_line_count = _candidate_page_numeric_line_count(text)
    score = 0.0
    reasons: list[str] = []

    if drawing_count > 0:
        score += min(0.36, 0.08 + drawing_count * 0.035)
        reasons.append("visual_drawing_signal")
    if image_area_frac >= 0.03:
        score += min(0.28, image_area_frac * 0.55)
        reasons.append("image_area_signal")
    if re.search(
        r"\b(fig(?:ure)?|chart|exhibit|table|source|market|growth|forecast|revenue|cagr)\b",
        text_lower,
    ):
        score += 0.18
        reasons.append("visual_or_table_text_marker")
    if numeric_line_count >= 2:
        score += min(0.3, 0.14 + numeric_line_count * 0.035)
        reasons.append("tabular_text_signal")
    elif numeric_line_count == 1:
        score += 0.08
        reasons.append("numeric_text_signal")
    if artifacts.text_block_count >= 3 and artifacts.text_char_count >= 180:
        score += 0.04
        reasons.append("structured_text_density")

    if not reasons:
        reasons.append("low_signal")
    return _CandidatePageScore(
        page=int(getattr(page, "number", 0) or 0),
        score=round(min(1.0, max(0.0, score)), 3),
        reasons=tuple(reasons),
        text_chars=int(artifacts.text_char_count),
        text_blocks=int(artifacts.text_block_count),
        image_blocks=len(artifacts.image_block_rects),
        drawing_count=int(drawing_count),
    )


def _page_triage_record(
    score: _CandidatePageScore,
    *,
    threshold: float,
    action: str,
) -> PdfCandidatePageTriageRecord:
    return PdfCandidatePageTriageRecord(
        schema_version="1.0",
        page=score.page,
        score=score.score,
        threshold=round(float(threshold), 3),
        action=action,
        reasons=list(score.reasons),
        text_chars=score.text_chars,
        text_blocks=score.text_blocks,
        image_blocks=score.image_blocks,
        drawing_count=score.drawing_count,
    )


def _resolve_page_gate_recall_floor(
    requested_count: int,
    *,
    min_recall_pages: int,
    min_recall_page_fraction: float,
) -> int:
    if requested_count <= 0:
        return 0
    fraction = min(1.0, max(0.0, float(min_recall_page_fraction)))
    page_count_floor = max(0, int(min_recall_pages))
    fraction_floor = math.ceil(requested_count * fraction)
    return min(requested_count, max(page_count_floor, fraction_floor))


def _plan_candidate_pages(
    triage_doc: fitz.Document,
    excluded_pages: set[int],
    *,
    artifact_cache: PdfPageArtifactCache,
    degraded_page_policy: str = "include_with_warning",
    page_gate_enabled: bool = True,
    page_gate_min_score: float = 0.2,
    page_gate_min_recall_pages: int = 12,
    page_gate_min_recall_page_fraction: float = 0.65,
) -> _CandidatePagePlan:
    requested_pages = [
        index for index in range(len(triage_doc)) if index not in excluded_pages
    ]
    triaged_pages: list[int] = []
    table_pages: list[int] = []
    triaged_full_scan_pages = 0
    degraded_pages: list[PdfDegradedPage] = []
    page_triage_records: list[PdfCandidatePageTriageRecord] = []
    skipped_score_candidates: list[tuple[int, _CandidatePageScore]] = []
    threshold = min(1.0, max(0.0, float(page_gate_min_score)))
    for index in requested_pages:
        try:
            page = triage_doc[index]
            artifacts = get_page_artifacts(
                page,
                cache=artifact_cache,
            )
            score = _score_candidate_page(page, artifacts)
            if not page_gate_enabled:
                triaged_pages.append(index)
                table_pages.append(index)
                page_triage_records.append(
                    _page_triage_record(
                        score,
                        threshold=threshold,
                        action="include_disabled",
                    )
                )
                continue
            if artifacts.full_page_scan_without_text:
                triaged_full_scan_pages += 1
                table_pages.append(index)
                page_triage_records.append(
                    _page_triage_record(
                        score,
                        threshold=threshold,
                        action="include_table_only_full_scan",
                    )
                )
                continue
        except PDF_FIGURE_TRIAGE_EXCEPTIONS as exc:
            degraded_page = _degraded_page_record(
                page=index,
                stage="triage",
                reason_code="pdf_candidate_page_triage_failed",
                policy=degraded_page_policy,
                message=str(exc),
            )
            action = _resolve_degraded_page_action(
                degraded_page=degraded_page,
            )
            degraded_pages.append(degraded_page)
            if action == "fail":
                raise AppError(
                    code=degraded_page.reason_code,
                    message="PDF candidate page triage failed",
                    cause=exc,
                    retryable=False,
                    context={
                        "page": index,
                        "policy": degraded_page.policy,
                        "stage": degraded_page.stage,
                    },
                ) from exc
            if action == "skip":
                page_triage_records.append(
                    PdfCandidatePageTriageRecord(
                        schema_version="1.0",
                        page=index,
                        score=0.0,
                        threshold=round(threshold, 3),
                        action="degraded_skip",
                        reasons=["triage_failed"],
                    )
                )
                continue
            page_triage_records.append(
                PdfCandidatePageTriageRecord(
                    schema_version="1.0",
                    page=index,
                    score=0.0,
                    threshold=round(threshold, 3),
                    action="degraded_include",
                    reasons=["triage_failed"],
                )
            )
            table_pages.append(index)
            triaged_pages.append(index)
            continue
        if score.score >= threshold:
            triaged_pages.append(index)
            table_pages.append(index)
            page_triage_records.append(
                _page_triage_record(
                    score,
                    threshold=threshold,
                    action="include_score",
                )
            )
            continue
        skipped_score_candidates.append((index, score))
        page_triage_records.append(
            _page_triage_record(
                score,
                threshold=threshold,
                action="skip_low_score",
            )
        )
    recall_floor = _resolve_page_gate_recall_floor(
        len(requested_pages),
        min_recall_pages=page_gate_min_recall_pages,
        min_recall_page_fraction=page_gate_min_recall_page_fraction,
    )
    included_pages = set(triaged_pages) | set(table_pages)
    if page_gate_enabled and len(included_pages) < recall_floor:
        need = recall_floor - len(included_pages)
        recall_candidates = sorted(
            skipped_score_candidates,
            key=lambda item: (-item[1].score, item[0]),
        )[:need]
        record_by_page = {record.page: idx for idx, record in enumerate(page_triage_records)}
        for index, score in recall_candidates:
            if index not in triaged_pages:
                triaged_pages.append(index)
            if index not in table_pages:
                table_pages.append(index)
            record_index = record_by_page.get(index)
            if record_index is not None:
                page_triage_records[record_index] = replace(
                    page_triage_records[record_index],
                    action="include_recall_floor",
                    reasons=list(score.reasons) + ["recall_floor"],
                )
    triaged_pages.sort()
    table_pages.sort()
    page_triage_skipped_pages = sum(
        1 for record in page_triage_records if record.action == "skip_low_score"
    )
    return _CandidatePagePlan(
        chart_pages=triaged_pages,
        table_pages=table_pages,
        excluded_count=max(0, len(triage_doc) - len(requested_pages)),
        triaged_full_scan_pages=triaged_full_scan_pages,
        page_triage_records=page_triage_records,
        page_triage_skipped_pages=page_triage_skipped_pages,
        degraded_pages=degraded_pages,
    )


def _degraded_page_record(
    *,
    page: int,
    stage: str,
    reason_code: str,
    policy: str,
    message: str,
) -> PdfDegradedPage:
    return PdfDegradedPage(
        schema_version="1.0",
        page=int(page),
        stage=str(stage or "").strip() or "unknown",
        reason_code=str(reason_code or "").strip() or "pdf_candidate_degraded",
        policy=str(policy or "").strip() or "include_with_warning",
        message=str(message or "").strip()[:500],
    )


def _resolve_degraded_page_action(*, degraded_page: PdfDegradedPage) -> str:
    policy = str(degraded_page.policy or "").strip().lower()
    if policy == "fail":
        return "fail"
    if policy == "skip_with_warning":
        return "skip"
    if policy == "include_with_warning":
        return "include"
    raise AppError(
        code="pdf_candidate_degraded_policy_invalid",
        message="Unsupported PDF candidate degraded-page policy",
        retryable=False,
        context={"policy": degraded_page.policy},
    )
