"""Source-report selection for cross-report analysis inputs.

This module owns deterministic source filtering, scoring, rejection accounting,
and publisher-diverse source selection. It does not read files, assemble prompt
evidence, or perform synthesis.
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import replace
from typing import Any

from src.contracts.cross_report_analysis import (
    CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
    CrossReportAnalysisRequest,
    CrossReportProjectedDataReadResponse,
    CrossReportSelectedSourceReport,
    CrossReportSourceReportCandidate,
    CrossReportSourceSelectionResult,
    validate_cross_report_contract,
)
from src.contracts.run_context import RunContext
from src.utils.errors import AppError
from src.utils.logging import log_event

from .shared import (
    _candidate_date,
    _clean_values,
    _normalize_iso_date_filter,
    _parse_iso_date,
    _topic_terms,
)

logger = logging.getLogger("market_lense.cross_report_analysis_input_generator")

__all__ = (
    "_cleaned_filters",
    "_filter_rejection_reasons",
    "_projection_readiness_rejection_reasons",
    "_relevance_score",
    "_recency_scores",
    "_score_candidates",
    "_select_diverse_sources",
    "_count_rejection_reasons",
    "select_cross_report_source_reports",
)


def _cleaned_filters(request: CrossReportAnalysisRequest) -> dict[str, Any]:
    return {
        "category_filters": _clean_values(request.category_filters),
        "tag_filters": _clean_values(request.tag_filters),
        "publisher_filters": _clean_values(request.publisher_filters),
        "date_range_start": _normalize_iso_date_filter(
            request.date_range_start,
            field_name="date_range_start",
        ),
        "date_range_end": _normalize_iso_date_filter(
            request.date_range_end,
            field_name="date_range_end",
        ),
        "topic_terms": _topic_terms(request.topic),
    }


def _filter_rejection_reasons(
    candidate: CrossReportSourceReportCandidate,
    cleaned_filters: dict[str, Any],
) -> list[str]:
    reasons: list[str] = []
    candidate_date = _candidate_date(candidate)
    date_range_start = _parse_iso_date(cleaned_filters["date_range_start"])
    date_range_end = _parse_iso_date(cleaned_filters["date_range_end"])
    if date_range_start is not None and (
        candidate_date is None or candidate_date < date_range_start
    ):
        reasons.append("date_before_start")
    if date_range_end is not None and (
        candidate_date is None or candidate_date > date_range_end
    ):
        reasons.append("date_after_end")

    publisher_filters = set(cleaned_filters["publisher_filters"])
    if publisher_filters:
        publisher_values = {
            candidate.publisher.strip().casefold(),
            candidate.publisher_id.strip().casefold(),
        }
        if not publisher_filters.intersection(publisher_values):
            reasons.append("publisher_filter_mismatch")

    category_filters = set(cleaned_filters["category_filters"])
    if category_filters:
        categories = {
            value.strip().casefold()
            for value in [*candidate.category_ids, *candidate.category_labels]
            if value.strip()
        }
        if not category_filters.intersection(categories):
            reasons.append("category_filter_mismatch")

    tag_filters = set(cleaned_filters["tag_filters"])
    if tag_filters:
        tags = {value.strip().casefold() for value in candidate.tags if value.strip()}
        if not tag_filters.intersection(tags):
            reasons.append("tag_filter_mismatch")

    return reasons


def _projection_readiness_rejection_reasons(
    candidate: CrossReportSourceReportCandidate,
    request: CrossReportAnalysisRequest,
) -> list[str]:
    if request.diagnostic or candidate.projection_status == "projected":
        return []
    return [f"projection_status_{candidate.projection_status}"]


def _relevance_score(
    candidate: CrossReportSourceReportCandidate,
    cleaned_filters: dict[str, Any],
) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []
    tags = {value.strip().casefold() for value in candidate.tags if value.strip()}
    categories = {
        value.strip().casefold()
        for value in [*candidate.category_ids, *candidate.category_labels]
        if value.strip()
    }
    title = candidate.title.casefold()

    matched_tags = sorted(set(cleaned_filters["tag_filters"]).intersection(tags))
    if matched_tags:
        score += 1.0
        reasons.append("tag_match:" + ",".join(matched_tags))

    matched_categories = sorted(
        set(cleaned_filters["category_filters"]).intersection(categories)
    )
    if matched_categories:
        score += 1.0
        reasons.append("category_match:" + ",".join(matched_categories))

    topic_matches = [
        term
        for term in cleaned_filters["topic_terms"]
        if term in tags or term in categories or term in title
    ]
    if topic_matches:
        score += min(len(topic_matches) * 0.25, 0.75)
        reasons.append("topic_match:" + ",".join(topic_matches))

    return score, reasons


def _recency_scores(
    candidates: list[CrossReportSourceReportCandidate],
) -> dict[str, float]:
    dated = {
        candidate.report_id: parsed
        for candidate in candidates
        if (parsed := _candidate_date(candidate)) is not None
    }
    if not dated:
        return {candidate.report_id: 0.0 for candidate in candidates}
    latest = max(dated.values())
    earliest = min(dated.values())
    span_days = max((latest - earliest).days, 1)
    scores: dict[str, float] = {}
    for candidate in candidates:
        parsed = dated.get(candidate.report_id)
        if parsed is None:
            scores[candidate.report_id] = 0.0
            continue
        scores[candidate.report_id] = max(
            0.0, 1.0 - ((latest - parsed).days / span_days)
        )
    return scores


def _score_candidates(
    candidates: list[CrossReportSourceReportCandidate],
    cleaned_filters: dict[str, Any],
) -> list[CrossReportSourceReportCandidate]:
    recency_scores = _recency_scores(candidates)
    scored = []
    for candidate in candidates:
        relevance_score, relevance_reasons = _relevance_score(
            candidate, cleaned_filters
        )
        density_score = min(
            (candidate.claim_count + candidate.finding_count + candidate.quote_count)
            / 10.0,
            1.0,
        )
        recency_score = recency_scores[candidate.report_id]
        total_score = round(relevance_score + density_score + recency_score, 6)
        scored.append(
            replace(
                candidate,
                recency_score=recency_score,
                relevance_score=relevance_score,
                density_score=density_score,
                diversity_score=0.0,
                total_score=total_score,
                selection_reasons=[
                    *relevance_reasons,
                    f"evidence_density:{candidate.evidence_count}",
                    f"report_date:{candidate.report_date}",
                ],
                rejection_reasons=[],
            )
        )
    return sorted(
        scored,
        key=lambda candidate: (
            -candidate.total_score,
            candidate.publisher.casefold(),
            candidate.report_date,
            candidate.report_id,
        ),
    )


def _select_diverse_sources(
    ranked_candidates: list[CrossReportSourceReportCandidate],
    max_source_reports: int,
) -> tuple[
    list[CrossReportSelectedSourceReport], list[CrossReportSourceReportCandidate]
]:
    remaining = list(ranked_candidates)
    selected: list[CrossReportSelectedSourceReport] = []
    rejected: list[CrossReportSourceReportCandidate] = []
    selected_publishers: set[str] = set()
    rank = 1
    while remaining and len(selected) < max_source_reports:
        rescored: list[CrossReportSourceReportCandidate] = []
        for candidate in remaining:
            publisher_key = candidate.publisher.strip().casefold()
            diversity_score = 0.75 if publisher_key not in selected_publishers else 0.0
            rescored.append(
                replace(
                    candidate,
                    diversity_score=diversity_score,
                    total_score=round(candidate.total_score + diversity_score, 6),
                    selection_reasons=[
                        *candidate.selection_reasons,
                        *(
                            ["publisher_diversity"]
                            if diversity_score > 0
                            else ["same_publisher_already_selected"]
                        ),
                    ],
                )
            )
        rescored.sort(
            key=lambda candidate: (
                -candidate.total_score,
                candidate.publisher.casefold(),
                candidate.report_date,
                candidate.report_id,
            )
        )
        winner = rescored[0]
        selected_publishers.add(winner.publisher.strip().casefold())
        selected.append(
            CrossReportSelectedSourceReport(
                schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
                report_id=winner.report_id,
                title=winner.title,
                publisher=winner.publisher,
                publisher_id=winner.publisher_id,
                report_date=winner.report_date,
                projection_status=winner.projection_status,
                content_hash=winner.content_hash,
                rank=rank,
                selection_reasons=winner.selection_reasons,
                evidence_count=winner.evidence_count,
                category_labels=winner.category_labels,
                tags=winner.tags,
                category_ids=winner.category_ids,
                source_url=winner.source_url,
            )
        )
        rank += 1
        remaining = [
            candidate
            for candidate in rescored[1:]
            if candidate.report_id != winner.report_id
        ]

    rejected.extend(
        replace(candidate, rejection_reasons=["max_source_reports_reached"])
        for candidate in remaining
    )
    return selected, rejected


def _count_rejection_reasons(
    candidates: list[CrossReportSourceReportCandidate],
) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for candidate in candidates:
        for reason in candidate.rejection_reasons:
            counts[reason] += 1
    return dict(sorted(counts.items()))


def select_cross_report_source_reports(
    request: CrossReportAnalysisRequest,
    projected_data: CrossReportProjectedDataReadResponse,
    ctx: RunContext,
) -> CrossReportSourceSelectionResult:
    validate_cross_report_contract(request)
    validate_cross_report_contract(projected_data)
    if request.max_source_reports < 1:
        raise AppError(
            code="cross_report_source_selection_limit_invalid",
            message="max_source_reports must be at least 1",
            retryable=False,
            severity="error",
            context={"max_source_reports": request.max_source_reports},
        )

    cleaned_filters = _cleaned_filters(request)
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="cross_report_source_selection_start",
            module=logger.name,
            fields={
                "request_id": request.request_id,
                "candidate_count": len(projected_data.source_candidates),
                "cleaned_filters": cleaned_filters,
                "max_source_reports": request.max_source_reports,
            },
        )
    )

    eligible: list[CrossReportSourceReportCandidate] = []
    rejected: list[CrossReportSourceReportCandidate] = []
    for candidate in projected_data.source_candidates:
        reasons = _projection_readiness_rejection_reasons(candidate, request)
        if not reasons:
            reasons = _filter_rejection_reasons(candidate, cleaned_filters)
        if reasons:
            rejected.append(replace(candidate, rejection_reasons=reasons))
        else:
            eligible.append(candidate)

    if not eligible:
        excluded_counts = _count_rejection_reasons(rejected)
        logger.info(
            log_event(
                ctx,
                role="generator",
                event="cross_report_source_selection_failed",
                module=logger.name,
                fields={
                    "request_id": request.request_id,
                    "candidate_count": len(projected_data.source_candidates),
                    "excluded_report_counts": excluded_counts,
                    "diagnostic": request.diagnostic,
                },
            )
        )
        raise AppError(
            code="cross_report_no_projected_sources",
            message="Cross-report source selection found no eligible projected sources",
            retryable=False,
            severity="error",
            context={
                "request_id": request.request_id,
                "candidate_count": len(projected_data.source_candidates),
                "excluded_report_counts": excluded_counts,
                "diagnostic": request.diagnostic,
            },
        )

    ranked_candidates = _score_candidates(eligible, cleaned_filters)
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="cross_report_source_selection_ranked",
            module=logger.name,
            fields={
                "ranked_report_ids": [
                    candidate.report_id for candidate in ranked_candidates
                ],
                "ranking_decisions": [
                    {
                        "report_id": candidate.report_id,
                        "total_score": candidate.total_score,
                        "selection_reasons": candidate.selection_reasons,
                    }
                    for candidate in ranked_candidates
                ],
            },
        )
    )

    selected_sources, cap_rejected = _select_diverse_sources(
        ranked_candidates, request.max_source_reports
    )
    rejected.extend(cap_rejected)
    excluded_counts = _count_rejection_reasons(rejected)
    result = CrossReportSourceSelectionResult(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        selected_sources=selected_sources,
        ranked_candidates=ranked_candidates,
        rejected_candidates=sorted(
            rejected,
            key=lambda candidate: (
                candidate.report_id,
                ",".join(candidate.rejection_reasons),
            ),
        ),
        cleaned_filters=cleaned_filters,
        excluded_report_counts=excluded_counts,
    )
    validate_cross_report_contract(result)
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="cross_report_source_selection_complete",
            module=logger.name,
            fields={
                "selected_report_ids": [
                    source.report_id for source in result.selected_sources
                ],
                "rejected_report_count": len(result.rejected_candidates),
                "excluded_report_counts": result.excluded_report_counts,
            },
        )
    )
    return result
