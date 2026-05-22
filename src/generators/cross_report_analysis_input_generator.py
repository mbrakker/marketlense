from __future__ import annotations

import logging
import json
import re
from collections import Counter
from dataclasses import replace
from datetime import date
from typing import Any

from src.contracts.files import ListDirectoryRequest, ReadTextRequest
from src.contracts.cross_report_analysis import (
    CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
    CrossReportAnalysisRequest,
    CrossReportEvidenceAgreementType,
    CrossReportEvidenceAgreementGroup,
    CrossReportEvidenceAgreementResult,
    CrossReportEvidenceInputResult,
    CrossReportEvidenceReference,
    CrossReportProjectedDataReadResponse,
    CrossReportPublishabilityResult,
    CrossReportRawMetricReference,
    CrossReportSelectedSourceReport,
    CrossReportSelectedTheme,
    CrossReportSignalScore,
    CrossReportSignalScoreResult,
    CrossReportSourceReportCandidate,
    CrossReportSourceSelectionResult,
    CrossReportThemeCandidate,
    CrossReportThemeSelectionResult,
    CrossReportValidationResult,
    validate_cross_report_contract,
)
from src.contracts.run_context import RunContext
from src.services import file_service
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.cross_report_analysis_input_generator")
_DEFAULT_THEME_SCORE_WEIGHTS = {
    "density": 1.0,
    "diversity": 1.0,
    "recency": 1.0,
    "novelty": 1.0,
    "filter": 1.0,
}
_DEFAULT_SIGNAL_SCORE_WEIGHTS = {
    "contradiction": 0.5,
    "diversity": 1.0,
    "recency": 1.0,
    "recurrence": 1.0,
    "support": 1.0,
    "taxonomy_fit": 1.0,
}
_RAW_METRIC_POLICY = "raw_metrics_preserved_without_normalization"


def _clean_values(values: list[str]) -> list[str]:
    cleaned = {str(value).strip().casefold() for value in values if str(value).strip()}
    return sorted(cleaned)


def _topic_terms(topic: str) -> list[str]:
    terms = {
        token.casefold()
        for token in re.findall(r"[A-Za-z0-9]+", topic)
        if len(token) > 1
    }
    return sorted(terms)


def _slug(value: str) -> str:
    tokens = re.findall(r"[A-Za-z0-9]+", value.casefold())
    return "-".join(tokens)


def _taxonomy_sort_key(value: str) -> tuple[str, str]:
    return (value.casefold(), value)


def _normalize_iso_date_filter(raw_value: object, *, field_name: str) -> str | None:
    value = str(raw_value or "").strip()
    if not value:
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise AppError(
            code="cross_report_date_filter_invalid",
            message="Cross-report date filters must use YYYY-MM-DD dates",
            cause=exc,
            retryable=False,
            severity="error",
            context={"field": field_name, "value": value},
        ) from exc
    return parsed.isoformat()


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


def _candidate_date(candidate: CrossReportSourceReportCandidate) -> date | None:
    value = candidate.report_date.strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


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
            for value in candidate.category_labels
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
        value.strip().casefold() for value in candidate.category_labels if value.strip()
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


def _source_recency_scores(
    sources: list[CrossReportSelectedSourceReport],
) -> dict[str, float]:
    dated = {
        source.report_id: parsed
        for source in sources
        if (parsed := _selected_source_date(source)) is not None
    }
    if not dated:
        return {source.report_id: 0.0 for source in sources}
    latest = max(dated.values())
    earliest = min(dated.values())
    span_days = max((latest - earliest).days, 1)
    return {
        source.report_id: (
            max(0.0, 1.0 - ((latest - dated[source.report_id]).days / span_days))
            if source.report_id in dated
            else 0.0
        )
        for source in sources
    }


def _parse_iso_date(raw_value: object) -> date | None:
    value = str(raw_value or "").strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _selected_source_date(source: CrossReportSelectedSourceReport) -> date | None:
    value = source.report_date.strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _theme_score_weights(raw_weights: dict[str, float] | None) -> dict[str, float]:
    weights = dict(_DEFAULT_THEME_SCORE_WEIGHTS)
    if raw_weights:
        for key, value in raw_weights.items():
            if key in weights:
                weights[key] = float(value)
    return weights


def _weighted_theme_total(
    *,
    recency_score: float,
    density_score: float,
    diversity_score: float,
    novelty_score: float,
    filter_boost: float,
    weights: dict[str, float],
) -> float:
    return round(
        recency_score * weights["recency"]
        + density_score * weights["density"]
        + diversity_score * weights["diversity"]
        + novelty_score * weights["novelty"]
        + filter_boost * weights["filter"],
        6,
    )


def _display_value(values: list[str], normalized: str) -> str:
    for value in values:
        if value.strip().casefold() == normalized:
            return value.strip()
    return normalized


def _theme_candidate_from_sources(
    *,
    theme_kind: str,
    theme_value: str,
    supporting_sources: list[CrossReportSelectedSourceReport],
    request: CrossReportAnalysisRequest,
    recency_scores: dict[str, float],
    weights: dict[str, float],
    recent_themes: list[dict[str, Any]],
) -> CrossReportThemeCandidate:
    report_ids = sorted(source.report_id for source in supporting_sources)
    publishers = {source.publisher.strip().casefold() for source in supporting_sources}
    evidence_count = sum(source.evidence_count for source in supporting_sources)
    all_tags = sorted(
        {
            tag.strip()
            for source in supporting_sources
            for tag in source.tags
            if tag.strip()
        },
        key=_taxonomy_sort_key,
    )
    all_categories = sorted(
        {
            category.strip()
            for source in supporting_sources
            for category in source.category_labels
            if category.strip()
        },
        key=_taxonomy_sort_key,
    )
    label = _display_value(
        all_tags if theme_kind == "tag" else all_categories, theme_value
    )
    recency_score = round(
        sum(recency_scores.get(source.report_id, 0.0) for source in supporting_sources)
        / max(len(supporting_sources), 1),
        6,
    )
    density_score = round(min(evidence_count / 10.0, 1.0), 6)
    diversity_score = round(min(len(publishers) / 3.0, 1.0), 6)
    novelty_score = 1.0
    filter_boost = 0.0
    if theme_kind == "tag" and theme_value in _clean_values(request.tag_filters):
        filter_boost = 0.6
    if theme_kind == "category" and theme_value in _clean_values(
        request.category_filters
    ):
        filter_boost = 0.55
    risks = []
    if len(publishers) < 2:
        risks.append("single_publisher")
    if evidence_count < 3:
        risks.append("thin_evidence")
    novelty_score, repetition_risks = _theme_novelty(
        theme_id=f"theme-{theme_kind}-{_slug(label)}",
        matched_tags=([label] if theme_kind == "tag" else all_tags),
        matched_categories=([label] if theme_kind == "category" else all_categories),
        recent_themes=recent_themes,
    )
    risks.extend(repetition_risks)
    total_score = _weighted_theme_total(
        recency_score=recency_score,
        density_score=density_score,
        diversity_score=diversity_score,
        novelty_score=novelty_score,
        filter_boost=filter_boost,
        weights=weights,
    )
    return CrossReportThemeCandidate(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        theme_id=f"theme-{theme_kind}-{_slug(label)}",
        label=label,
        rationale=(
            f"{theme_kind.title()} theme supported by {len(report_ids)} projected "
            f"source reports and {len(publishers)} publishers."
        ),
        matched_tags=([label] if theme_kind == "tag" else all_tags),
        matched_categories=([label] if theme_kind == "category" else all_categories),
        source_report_ids=report_ids,
        source_publisher_count=len(publishers),
        evidence_count=evidence_count,
        recency_score=recency_score,
        density_score=density_score,
        diversity_score=diversity_score,
        novelty_score=novelty_score,
        total_score=total_score,
        rejection_risks=risks,
    )


def _automatic_theme_candidates(
    request: CrossReportAnalysisRequest,
    sources: list[CrossReportSelectedSourceReport],
    *,
    recent_themes: list[dict[str, Any]],
    weights: dict[str, float],
) -> list[CrossReportThemeCandidate]:
    recency_scores = _source_recency_scores(sources)
    grouped: dict[tuple[str, str], list[CrossReportSelectedSourceReport]] = {}
    for source in sources:
        for tag in source.tags:
            if tag.strip():
                grouped.setdefault(("tag", tag.strip().casefold()), []).append(source)
        for category in source.category_labels:
            if category.strip():
                grouped.setdefault(
                    ("category", category.strip().casefold()), []
                ).append(source)
    candidates = [
        _theme_candidate_from_sources(
            theme_kind=theme_kind,
            theme_value=theme_value,
            supporting_sources=sorted(
                supporting_sources, key=lambda source: source.report_id
            ),
            request=request,
            recency_scores=recency_scores,
            weights=weights,
            recent_themes=recent_themes,
        )
        for (theme_kind, theme_value), supporting_sources in grouped.items()
    ]
    return sorted(
        candidates,
        key=lambda candidate: (
            -candidate.total_score,
            _theme_sort_priority(candidate, request),
            candidate.label.casefold(),
            candidate.theme_id,
        ),
    )


def _theme_sort_priority(
    candidate: CrossReportThemeCandidate, request: CrossReportAnalysisRequest
) -> int:
    filter_tags = set(_clean_values(request.tag_filters))
    filter_categories = set(_clean_values(request.category_filters))
    candidate_tags = {tag.strip().casefold() for tag in candidate.matched_tags}
    candidate_categories = {
        category.strip().casefold() for category in candidate.matched_categories
    }
    if candidate_tags.intersection(filter_tags):
        return 0
    if candidate_categories.intersection(filter_categories):
        return 1
    if candidate.theme_id.startswith("theme-category-"):
        return 2
    return 3


def _theme_novelty(
    *,
    theme_id: str,
    matched_tags: list[str],
    matched_categories: list[str],
    recent_themes: list[dict[str, Any]],
) -> tuple[float, list[str]]:
    risks: list[str] = []
    novelty_score = 1.0
    normalized_tags = {tag.strip().casefold() for tag in matched_tags if tag.strip()}
    normalized_categories = {
        category.strip().casefold()
        for category in matched_categories
        if category.strip()
    }
    for recent in recent_themes:
        if str(recent.get("theme_id", "")).strip() == theme_id:
            novelty_score = 0.0
            risks.append("recent_theme_repetition")
        recent_tags = {
            str(tag).strip().casefold()
            for tag in recent.get("matched_tags", [])
            if str(tag).strip()
        }
        recent_categories = {
            str(category).strip().casefold()
            for category in recent.get("matched_categories", [])
            if str(category).strip()
        }
        for tag in sorted(normalized_tags.intersection(recent_tags)):
            novelty_score = min(novelty_score, 0.5)
            risks.append(f"recent_tag_repetition:{tag}")
        for category in sorted(normalized_categories.intersection(recent_categories)):
            novelty_score = min(novelty_score, 0.5)
            risks.append(f"recent_category_repetition:{category}")
    if "recent_theme_repetition" in risks:
        novelty_score = 0.0
    return novelty_score, sorted(set(risks))


def _load_recent_theme_metadata(
    *,
    recent_artifacts_root: str | None,
    theme_rotation_window_days: int,
    theme_rotation_reference_date: str | None,
    ctx: RunContext,
) -> list[dict[str, Any]]:
    if not recent_artifacts_root:
        return []
    reference_date = _parse_iso_date(theme_rotation_reference_date) or date.today()
    earliest_allowed = reference_date.toordinal() - int(theme_rotation_window_days)
    response = file_service.list_directory(
        ListDirectoryRequest(
            schema_version="1.0",
            root_dir=recent_artifacts_root,
            glob_pattern="*/analysis.json",
            recursive=True,
            include_files=True,
            include_dirs=False,
            limit=500,
        ),
        ctx,
    )
    recent: list[dict[str, Any]] = []
    skipped_old = 0
    skipped_undated = 0
    skipped_invalid_date = 0
    for entry in response.entries:
        text_response = file_service.read_text(
            ReadTextRequest(schema_version="1.0", path=entry.path), ctx
        )
        try:
            payload = json.loads(text_response.content)
        except json.JSONDecodeError as exc:
            raise AppError(
                code="cross_report_recent_artifact_invalid",
                message="Recent cross-report artifact metadata is not valid JSON",
                cause=exc,
                retryable=False,
                severity="error",
                context={"path": entry.path},
            ) from exc
        generated_at_raw = payload.get("generated_at_utc") or payload.get(
            "metadata", {}
        ).get("generated_at_utc")
        generated_at_value = str(generated_at_raw or "").strip()
        if not generated_at_value:
            skipped_undated += 1
            continue
        generated_at = _parse_iso_date(generated_at_value)
        if generated_at is None:
            skipped_invalid_date += 1
            continue
        if generated_at.toordinal() < earliest_allowed:
            skipped_old += 1
            continue
        selected_theme = payload.get("selected_theme") or payload.get(
            "generated_result", {}
        ).get("selected_theme")
        if isinstance(selected_theme, dict):
            recent.append(
                {
                    "theme_id": str(selected_theme.get("theme_id", "")).strip(),
                    "matched_tags": list(selected_theme.get("matched_tags", []) or []),
                    "matched_categories": list(
                        selected_theme.get("matched_categories", []) or []
                    ),
                    "source_report_ids": list(
                        selected_theme.get("source_report_ids", []) or []
                    ),
                }
            )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="cross_report_recent_theme_metadata_loaded",
            module=logger.name,
            fields={
                "recent_artifacts_root": recent_artifacts_root,
                "loaded_recent_themes": len(recent),
                "skipped_old_artifacts": skipped_old,
                "skipped_undated_artifacts": skipped_undated,
                "skipped_invalid_date_artifacts": skipped_invalid_date,
            },
        )
    )
    return recent


def _explicit_theme_candidate(
    request: CrossReportAnalysisRequest,
    sources: list[CrossReportSelectedSourceReport],
) -> CrossReportThemeCandidate:
    topic = request.topic.strip()
    source_report_ids = sorted(source.report_id for source in sources)
    publishers = {source.publisher.strip().casefold() for source in sources}
    evidence_count = sum(source.evidence_count for source in sources)
    matched_tags = sorted(
        {
            tag.strip()
            for source in sources
            for tag in source.tags
            if tag.strip()
            and (
                tag.strip().casefold() in _topic_terms(topic)
                or tag.strip().casefold() in _clean_values(request.tag_filters)
            )
        },
        key=_taxonomy_sort_key,
    )
    matched_categories = sorted(
        {
            category.strip()
            for source in sources
            for category in source.category_labels
            if category.strip()
            and category.strip().casefold() in _clean_values(request.category_filters)
        },
        key=_taxonomy_sort_key,
    )
    return CrossReportThemeCandidate(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        theme_id=f"theme-explicit-{_slug(topic)}",
        label=topic,
        rationale="Explicit operator topic selected without automatic theme choice.",
        matched_tags=matched_tags or _clean_values(request.tag_filters),
        matched_categories=matched_categories
        or _clean_values(request.category_filters),
        source_report_ids=source_report_ids,
        source_publisher_count=len(publishers),
        evidence_count=evidence_count,
        recency_score=1.0,
        density_score=round(min(evidence_count / 10.0, 1.0), 6),
        diversity_score=round(min(len(publishers) / 3.0, 1.0), 6),
        novelty_score=1.0,
        total_score=round(2.0 + min(evidence_count / 10.0, 1.0), 6),
        rejection_risks=[] if len(publishers) > 1 else ["single_publisher"],
    )


def _selected_theme(candidate: CrossReportThemeCandidate) -> CrossReportSelectedTheme:
    return CrossReportSelectedTheme(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        theme_id=candidate.theme_id,
        label=candidate.label,
        rationale=candidate.rationale,
        matched_tags=candidate.matched_tags,
        matched_categories=candidate.matched_categories,
        source_report_ids=candidate.source_report_ids,
        score_components={
            "recency": candidate.recency_score,
            "density": candidate.density_score,
            "diversity": candidate.diversity_score,
            "novelty": candidate.novelty_score,
            "total": candidate.total_score,
        },
        selection_reasons=[
            f"score:{candidate.total_score}",
            f"source_reports:{len(candidate.source_report_ids)}",
            f"source_publishers:{candidate.source_publisher_count}",
            f"evidence:{candidate.evidence_count}",
        ],
        rejection_risks=candidate.rejection_risks,
    )


def select_cross_report_theme(
    request: CrossReportAnalysisRequest,
    source_selection: CrossReportSourceSelectionResult,
    ctx: RunContext,
    *,
    recent_artifacts_root: str | None = None,
    theme_rotation_window_days: int = 30,
    theme_rotation_reference_date: str | None = None,
    theme_score_weights: dict[str, float] | None = None,
) -> CrossReportThemeSelectionResult:
    validate_cross_report_contract(request)
    validate_cross_report_contract(source_selection)
    if not request.auto_theme and not request.topic.strip():
        raise AppError(
            code="cross_report_topic_required",
            message="Cross-report theme selection requires a topic unless auto_theme is enabled",
            retryable=False,
            severity="error",
            context={"request_id": request.request_id},
        )
    weights = _theme_score_weights(theme_score_weights)
    automatic = request.auto_theme or not request.topic.strip()
    recent_themes = (
        _load_recent_theme_metadata(
            recent_artifacts_root=recent_artifacts_root,
            theme_rotation_window_days=theme_rotation_window_days,
            theme_rotation_reference_date=theme_rotation_reference_date,
            ctx=ctx,
        )
        if automatic
        else []
    )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="cross_report_theme_selection_start",
            module=logger.name,
            fields={
                "request_id": request.request_id,
                "auto_theme": request.auto_theme,
                "topic": request.topic,
                "selected_source_count": len(source_selection.selected_sources),
                "recent_theme_count": len(recent_themes),
                "theme_score_weights": weights,
            },
        )
    )

    sources = source_selection.selected_sources
    if not sources:
        logger.info(
            log_event(
                ctx,
                role="generator",
                event="cross_report_theme_selection_failed",
                module=logger.name,
                fields={
                    "request_id": request.request_id,
                    "reason": "no_selected_sources",
                },
            )
        )
        raise AppError(
            code="cross_report_no_theme_candidates",
            message="Cross-report theme selection found no eligible selected sources",
            retryable=False,
            severity="error",
            context={"request_id": request.request_id, "reason": "no_selected_sources"},
        )

    theme_candidates = (
        _automatic_theme_candidates(
            request,
            sources,
            recent_themes=recent_themes,
            weights=weights,
        )
        if automatic
        else [_explicit_theme_candidate(request, sources)]
    )
    if not theme_candidates:
        logger.info(
            log_event(
                ctx,
                role="generator",
                event="cross_report_theme_selection_failed",
                module=logger.name,
                fields={
                    "request_id": request.request_id,
                    "reason": "no_theme_candidates",
                },
            )
        )
        raise AppError(
            code="cross_report_no_theme_candidates",
            message="Cross-report theme selection found no deterministic theme candidates",
            retryable=False,
            severity="error",
            context={"request_id": request.request_id, "reason": "no_theme_candidates"},
        )

    selected = theme_candidates[0]
    result = CrossReportThemeSelectionResult(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        selected_theme=_selected_theme(selected),
        theme_candidates=theme_candidates,
        rejected_theme_candidates=[],
    )
    validate_cross_report_contract(result)
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="cross_report_theme_selection_complete",
            module=logger.name,
            fields={
                "theme_candidate_count": len(result.theme_candidates),
                "selected_theme_id": result.selected_theme.theme_id,
                "selected_source_report_ids": result.selected_theme.source_report_ids,
                "score_components": result.selected_theme.score_components,
                "rejection_risks": result.selected_theme.rejection_risks,
            },
        )
    )
    return result


def _publishability_issues(
    request: CrossReportAnalysisRequest,
    theme_selection: CrossReportThemeSelectionResult,
    source_selection: CrossReportSourceSelectionResult,
    *,
    min_source_reports: int,
    min_source_publishers: int,
    min_evidence_items: int,
    publish_requires_validation_pass: bool,
    validation_result: CrossReportValidationResult | None,
) -> tuple[list[str], int, int, int]:
    selected_sources = source_selection.selected_sources
    source_report_count = len(selected_sources)
    source_publisher_count = len(
        {source.publisher.strip().casefold() for source in selected_sources}
    )
    evidence_count = sum(source.evidence_count for source in selected_sources)
    issues: list[str] = []
    if source_report_count < min_source_reports:
        issues.append("source_report_count_below_minimum")
    if source_publisher_count < min_source_publishers:
        issues.append("source_publisher_count_below_minimum")
    if evidence_count < min_evidence_items:
        issues.append("evidence_count_below_minimum")
    risks = set(theme_selection.selected_theme.rejection_risks)
    if "recent_theme_repetition" in risks:
        issues.append("duplicate_theme_risk")
    if "metric_normalization_dependency" in risks:
        issues.append("metric_normalization_dependency")
    if (
        request.publication_mode in {"publish_dry_run", "publish_live"}
        and publish_requires_validation_pass
    ):
        if validation_result is None:
            issues.append("validation_result_required_for_publication")
        elif not validation_result.passed:
            issues.append("validation_not_passed")
    return (
        sorted(set(issues)),
        source_report_count,
        source_publisher_count,
        evidence_count,
    )


def validate_cross_report_publishability(
    request: CrossReportAnalysisRequest,
    theme_selection: CrossReportThemeSelectionResult,
    source_selection: CrossReportSourceSelectionResult,
    ctx: RunContext,
    *,
    min_source_reports: int = 2,
    min_source_publishers: int = 2,
    min_evidence_items: int = 6,
    publish_requires_validation_pass: bool = True,
    validation_result: CrossReportValidationResult | None = None,
) -> CrossReportPublishabilityResult:
    validate_cross_report_contract(request)
    validate_cross_report_contract(theme_selection)
    validate_cross_report_contract(source_selection)
    if validation_result is not None:
        validate_cross_report_contract(validation_result)
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="cross_report_publishability_check_start",
            module=logger.name,
            fields={
                "request_id": request.request_id,
                "selected_theme_id": theme_selection.selected_theme.theme_id,
                "min_source_reports": min_source_reports,
                "min_source_publishers": min_source_publishers,
                "min_evidence_items": min_evidence_items,
                "publication_mode": request.publication_mode,
                "override_publishability": request.override_publishability,
                "diagnostic": request.diagnostic,
            },
        )
    )
    (
        issues,
        source_report_count,
        source_publisher_count,
        evidence_count,
    ) = _publishability_issues(
        request,
        theme_selection,
        source_selection,
        min_source_reports=min_source_reports,
        min_source_publishers=min_source_publishers,
        min_evidence_items=min_evidence_items,
        publish_requires_validation_pass=publish_requires_validation_pass,
        validation_result=validation_result,
    )
    override_applied = bool(issues and request.override_publishability)
    diagnostic = bool(issues and request.diagnostic)
    publishable = not issues or override_applied
    result = CrossReportPublishabilityResult(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        selected_theme_id=theme_selection.selected_theme.theme_id,
        publishable=publishable,
        override_applied=override_applied,
        diagnostic=diagnostic,
        issues=issues,
        source_report_count=source_report_count,
        source_publisher_count=source_publisher_count,
        evidence_count=evidence_count,
        checked_policy_fields={
            "min_source_reports": min_source_reports,
            "min_source_publishers": min_source_publishers,
            "min_evidence_items": min_evidence_items,
            "publish_requires_validation_pass": publish_requires_validation_pass,
            "publication_mode": request.publication_mode,
        },
    )
    validate_cross_report_contract(result)
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="cross_report_publishability_check_complete",
            module=logger.name,
            fields={
                "request_id": request.request_id,
                "selected_theme_id": result.selected_theme_id,
                "publishable": result.publishable,
                "override_applied": result.override_applied,
                "diagnostic": result.diagnostic,
                "issues": result.issues,
                "source_report_count": result.source_report_count,
                "source_publisher_count": result.source_publisher_count,
                "evidence_count": result.evidence_count,
            },
        )
    )
    if issues and not request.diagnostic and not request.override_publishability:
        raise AppError(
            code="cross_report_publishability_failed",
            message="Cross-report selected theme is not publishable",
            retryable=False,
            severity="error",
            context={
                "request_id": request.request_id,
                "selected_theme_id": result.selected_theme_id,
                "issues": issues,
                "source_report_count": source_report_count,
                "source_publisher_count": source_publisher_count,
                "evidence_count": evidence_count,
            },
        )
    return result


def _ordered_selected_report_ids(
    source_selection: CrossReportSourceSelectionResult,
) -> list[str]:
    return [source.report_id for source in source_selection.selected_sources]


def _evidence_sort_key(
    evidence,
    selected_order: dict[str, int],
) -> tuple[int, int, str]:
    class_priority = {"claim": 0, "finding": 1, "quote": 2, "metric": 3}
    return (
        selected_order.get(evidence.report_id, 9999),
        class_priority.get(str(evidence.content_class), 99),
        evidence.evidence_id,
    )


def _raw_metric_sort_key(
    metric,
    selected_order: dict[str, int],
) -> tuple[int, str]:
    return (selected_order.get(metric.report_id, 9999), metric.metric_id)


def _prompt_input_chars(
    evidence,
    raw_metrics,
) -> int:
    evidence_chars = sum(
        len(item.evidence_id)
        + len(item.report_id)
        + len(item.publisher)
        + len(item.title)
        + len(item.source_table)
        + len(item.entity_uid)
        + len(str(item.content_class))
        + len(item.text)
        + len(json.dumps(item.source_metadata, sort_keys=True, default=str))
        for item in evidence
    )
    metric_chars = sum(
        len(item.metric_id)
        + len(item.report_id)
        + len(item.publisher)
        + len(item.label)
        + len(item.raw_value)
        + len(item.unit)
        + len(item.context)
        + len(item.evidence_id)
        + len(json.dumps(item.source_metadata, sort_keys=True, default=str))
        for item in raw_metrics
    )
    return evidence_chars + metric_chars


def _signal_score_weights(raw_weights: dict[str, float] | None) -> dict[str, float]:
    weights = dict(_DEFAULT_SIGNAL_SCORE_WEIGHTS)
    if raw_weights:
        for key, value in raw_weights.items():
            if key not in weights:
                raise AppError(
                    code="cross_report_signal_weight_invalid",
                    message=f"Unknown cross-report signal score weight: {key}",
                    retryable=False,
                    severity="error",
                    context={"weight": key},
                )
            parsed = float(value)
            if parsed < 0:
                raise AppError(
                    code="cross_report_signal_weight_invalid",
                    message=f"Cross-report signal score weight must be non-negative: {key}",
                    retryable=False,
                    severity="error",
                    context={"weight": key, "value": parsed},
                )
            weights[key] = parsed
    return dict(sorted(weights.items()))


def _signal_label(value: str) -> str:
    cleaned = str(value).strip()
    if cleaned.upper() == cleaned and len(cleaned) <= 5:
        return cleaned
    if len(cleaned) <= 3:
        return cleaned.upper()
    return " ".join(token.capitalize() for token in re.split(r"\s+", cleaned))


def _signal_candidates(
    request: CrossReportAnalysisRequest,
    evidence_inputs: CrossReportEvidenceInputResult,
    theme_selection: CrossReportThemeSelectionResult,
) -> list[str]:
    selected_theme = theme_selection.selected_theme
    values: list[str] = [
        *selected_theme.matched_tags,
        *selected_theme.matched_categories,
        *request.tag_filters,
        *request.category_filters,
    ]
    for source in evidence_inputs.selected_sources:
        values.extend(source.tags)
        values.extend(source.category_labels)
    seen: set[str] = set()
    candidates: list[str] = []
    for value in values:
        normalized = str(value).strip().casefold()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        candidates.append(_signal_label(str(value)))
    if candidates:
        return candidates
    return [_signal_label(term) for term in _topic_terms(request.topic)]


def _source_taxonomy_tokens(source: CrossReportSelectedSourceReport) -> set[str]:
    return {
        value.strip().casefold()
        for value in [*source.tags, *source.category_labels]
        if value.strip()
    }


def _evidence_matches_signal(
    evidence,
    signal_label: str,
    source: CrossReportSelectedSourceReport | None,
) -> bool:
    normalized_label = signal_label.strip().casefold()
    text = evidence.text.casefold()
    text_tokens = _topic_terms(evidence.text)
    label_tokens = _topic_terms(signal_label)
    if normalized_label in text_tokens:
        return True
    if label_tokens:
        pattern = (
            r"(?<![A-Za-z0-9])"
            + r"\W+".join(re.escape(token) for token in label_tokens)
            + r"(?![A-Za-z0-9])"
        )
        if re.search(pattern, text, flags=re.IGNORECASE):
            return True
    if source is None:
        return False
    return normalized_label in _source_taxonomy_tokens(source)


def _contradiction_score(evidence) -> float:
    positive_markers = {
        "adoption",
        "accelerate",
        "growth",
        "higher",
        "increase",
        "increasing",
        "rise",
        "strong",
    }
    uncertainty_markers = {
        "decline",
        "decrease",
        "down",
        "fall",
        "risk",
        "slower",
        "uneven",
        "weak",
    }
    tokens = {
        token.casefold()
        for item in evidence
        for token in re.findall(r"[A-Za-z0-9]+", item.text)
    }
    return (
        1.0
        if tokens.intersection(positive_markers)
        and tokens.intersection(uncertainty_markers)
        else 0.0
    )


def _support_score(evidence) -> float:
    classes = {str(item.content_class) for item in evidence}
    if {"finding", "quote"}.intersection(classes):
        return 1.0
    if "claim" in classes:
        return 0.5
    return 0.0


def _weighted_signal_total(
    component_scores: dict[str, float],
    weights: dict[str, float],
) -> float:
    return round(
        sum(component_scores[key] * weights[key] for key in sorted(weights)),
        6,
    )


def score_cross_report_signals(
    request: CrossReportAnalysisRequest,
    evidence_inputs: CrossReportEvidenceInputResult,
    theme_selection: CrossReportThemeSelectionResult,
    ctx: RunContext,
    *,
    score_weights: dict[str, float] | None = None,
    max_signals: int = 8,
) -> CrossReportSignalScoreResult:
    validate_cross_report_contract(request)
    validate_cross_report_contract(evidence_inputs)
    validate_cross_report_contract(theme_selection)
    if max_signals < 1:
        raise AppError(
            code="cross_report_signal_limit_invalid",
            message="max_signals must be at least 1",
            retryable=False,
            severity="error",
            context={"max_signals": max_signals},
        )

    weights = _signal_score_weights(score_weights)
    selected_theme = theme_selection.selected_theme
    source_by_report_id = {
        source.report_id: source for source in evidence_inputs.selected_sources
    }
    recency_scores = _source_recency_scores(evidence_inputs.selected_sources)
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="cross_report_signal_scoring_start",
            module=logger.name,
            fields={
                "request_id": request.request_id,
                "selected_theme_id": selected_theme.theme_id,
                "evidence_count": len(evidence_inputs.evidence),
                "raw_metric_count": len(evidence_inputs.raw_metrics),
                "score_weights": weights,
                "raw_metric_policy": _RAW_METRIC_POLICY,
            },
        )
    )

    dropped: Counter[str] = Counter()
    signal_scores: list[CrossReportSignalScore] = []
    signal_slug_counts: Counter[str] = Counter()
    taxonomy_focus = {
        value.strip().casefold()
        for value in [
            *selected_theme.matched_tags,
            *selected_theme.matched_categories,
            *request.tag_filters,
            *request.category_filters,
        ]
        if value.strip()
    }
    for label in _signal_candidates(request, evidence_inputs, theme_selection):
        matched_evidence = [
            item
            for item in evidence_inputs.evidence
            if _evidence_matches_signal(
                item,
                label,
                source_by_report_id.get(item.report_id),
            )
        ]
        if not matched_evidence:
            dropped["no_matching_evidence"] += 1
            continue
        supporting_sources = {
            item.report_id
            for item in matched_evidence
            if item.report_id in source_by_report_id
        }
        supporting_publishers = {
            source_by_report_id[report_id].publisher.strip().casefold()
            for report_id in supporting_sources
        }
        normalized_label = label.strip().casefold()
        component_scores = {
            "contradiction": _contradiction_score(matched_evidence),
            "diversity": min(len(supporting_publishers) / 2.0, 1.0),
            "recency": max(
                (
                    recency_scores.get(report_id, 0.0)
                    for report_id in supporting_sources
                ),
                default=0.0,
            ),
            "recurrence": min(len(matched_evidence) / 3.0, 1.0),
            "support": _support_score(matched_evidence),
            "taxonomy_fit": 1.0 if normalized_label in taxonomy_focus else 0.0,
        }
        reasons = [
            f"evidence_recurrence:{len(matched_evidence)}",
            f"source_publishers:{len(supporting_publishers)}",
            f"taxonomy_fit:{component_scores['taxonomy_fit']}",
            f"support:{component_scores['support']}",
            "raw_metric_magnitude_ignored",
        ]
        if component_scores["contradiction"] > 0:
            reasons.append("contradiction_presence")
        signal_slug = _slug(label)
        signal_slug_counts[signal_slug] += 1
        signal_id = (
            f"signal-{signal_slug}"
            if signal_slug_counts[signal_slug] == 1
            else f"signal-{signal_slug}-{signal_slug_counts[signal_slug]}"
        )
        signal_scores.append(
            CrossReportSignalScore(
                schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
                signal_id=signal_id,
                label=label,
                evidence_ids=[item.evidence_id for item in matched_evidence],
                component_scores=dict(sorted(component_scores.items())),
                total_score=_weighted_signal_total(component_scores, weights),
                reasons=reasons,
            )
        )

    signal_scores.sort(
        key=lambda score: (-score.total_score, score.signal_id),
    )
    selected_scores = signal_scores[:max_signals]
    dropped_count = max(len(signal_scores) - len(selected_scores), 0)
    if dropped_count:
        dropped["max_signals_reached"] = dropped_count
    result = CrossReportSignalScoreResult(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        selected_theme=selected_theme,
        signal_scores=selected_scores,
        selected_signal_ids=[score.signal_id for score in selected_scores],
        score_weights=weights,
        raw_metric_policy=_RAW_METRIC_POLICY,
        dropped_signal_counts=dict(sorted(dropped.items())),
    )
    validate_cross_report_contract(result)
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="cross_report_signal_scoring_complete",
            module=logger.name,
            fields={
                "request_id": request.request_id,
                "selected_theme_id": selected_theme.theme_id,
                "selected_signal_ids": result.selected_signal_ids,
                "signal_components": [
                    {
                        "signal_id": score.signal_id,
                        "component_scores": score.component_scores,
                        "total_score": score.total_score,
                        "reasons": score.reasons,
                    }
                    for score in result.signal_scores
                ],
                "dropped_signal_counts": result.dropped_signal_counts,
                "raw_metric_policy": result.raw_metric_policy,
            },
        )
    )
    return result


def _directional_markers(evidence) -> tuple[set[str], set[str]]:
    positive_markers = {
        "accelerating",
        "growth",
        "increase",
        "increasing",
        "rising",
        "strong",
    }
    negative_markers = {
        "decline",
        "declining",
        "decrease",
        "decreasing",
        "falling",
        "slower",
        "weak",
    }
    positive_evidence: set[str] = set()
    negative_evidence: set[str] = set()
    for item in evidence:
        tokens = {token.casefold() for token in re.findall(r"[A-Za-z0-9]+", item.text)}
        if tokens.intersection(positive_markers):
            positive_evidence.add(item.evidence_id)
        if tokens.intersection(negative_markers):
            negative_evidence.add(item.evidence_id)
    return positive_evidence, negative_evidence


def _agreement_type_and_reasons(
    evidence: list[CrossReportEvidenceReference],
    *,
    publisher_count: int,
    report_count: int,
) -> tuple[CrossReportEvidenceAgreementType, list[str]]:
    if publisher_count < 2 or report_count < 2:
        return "thin_coverage", ["single_report_coverage"]
    positive_evidence, negative_evidence = _directional_markers(evidence)
    positive_only = positive_evidence - negative_evidence
    negative_only = negative_evidence - positive_evidence
    if positive_only and negative_only:
        return "divergent", ["opposed_directional_language"]
    return "convergent", ["multi_publisher_alignment"]


def group_cross_report_evidence_agreement(
    request: CrossReportAnalysisRequest,
    evidence_inputs: CrossReportEvidenceInputResult,
    signal_result: CrossReportSignalScoreResult,
    ctx: RunContext,
) -> CrossReportEvidenceAgreementResult:
    validate_cross_report_contract(request)
    validate_cross_report_contract(evidence_inputs)
    validate_cross_report_contract(signal_result)
    evidence_by_id = {item.evidence_id: item for item in evidence_inputs.evidence}
    source_by_report_id = {
        source.report_id: source for source in evidence_inputs.selected_sources
    }
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="cross_report_evidence_agreement_grouping_start",
            module=logger.name,
            fields={
                "request_id": request.request_id,
                "selected_theme_id": signal_result.selected_theme.theme_id,
                "signal_count": len(signal_result.signal_scores),
                "evidence_count": len(evidence_inputs.evidence),
            },
        )
    )

    groups: list[CrossReportEvidenceAgreementGroup] = []
    prompt_inputs: list[dict[str, Any]] = []
    for signal in signal_result.signal_scores:
        group_evidence = [
            evidence_by_id[evidence_id]
            for evidence_id in signal.evidence_ids
            if evidence_id in evidence_by_id
        ]
        if not group_evidence:
            continue
        source_report_ids = sorted({item.report_id for item in group_evidence})
        publishers = {
            source_by_report_id[report_id].publisher.strip().casefold()
            for report_id in source_report_ids
            if report_id in source_by_report_id
        }
        agreement_type, uncertainty_reasons = _agreement_type_and_reasons(
            group_evidence,
            publisher_count=len(publishers),
            report_count=len(source_report_ids),
        )
        group = CrossReportEvidenceAgreementGroup(
            schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
            group_id=f"group-{signal.signal_id}",
            label=signal.label,
            agreement_type=agreement_type,
            signal_ids=[signal.signal_id],
            evidence_ids=[item.evidence_id for item in group_evidence],
            source_report_ids=source_report_ids,
            publisher_count=len(publishers),
            uncertainty_reasons=uncertainty_reasons,
            prompt_input_label=f"{agreement_type}: {signal.label}",
        )
        groups.append(group)
        prompt_inputs.append(
            {
                "group_id": group.group_id,
                "label": group.label,
                "agreement_type": group.agreement_type,
                "evidence_ids": group.evidence_ids,
                "source_report_ids": group.source_report_ids,
                "uncertainty_reasons": group.uncertainty_reasons,
                "prompt_input_label": group.prompt_input_label,
            }
        )

    agreement_counts: dict[str, int] = dict(
        sorted(Counter(group.agreement_type for group in groups).items())
    )
    result = CrossReportEvidenceAgreementResult(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        selected_theme=signal_result.selected_theme,
        evidence_groups=groups,
        prompt_uncertainty_inputs=prompt_inputs,
        agreement_counts=agreement_counts,
    )
    validate_cross_report_contract(result)
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="cross_report_evidence_agreement_grouping_complete",
            module=logger.name,
            fields={
                "request_id": request.request_id,
                "selected_theme_id": signal_result.selected_theme.theme_id,
                "agreement_counts": result.agreement_counts,
                "groups": [
                    {
                        "group_id": group.group_id,
                        "agreement_type": group.agreement_type,
                        "evidence_ids": group.evidence_ids,
                        "uncertainty_reasons": group.uncertainty_reasons,
                    }
                    for group in result.evidence_groups
                ],
            },
        )
    )
    return result


def assemble_cross_report_analysis_inputs(
    request: CrossReportAnalysisRequest,
    source_selection: CrossReportSourceSelectionResult,
    projected_data: CrossReportProjectedDataReadResponse,
    ctx: RunContext,
    *,
    max_evidence_items: int = 48,
) -> CrossReportEvidenceInputResult:
    validate_cross_report_contract(request)
    validate_cross_report_contract(source_selection)
    validate_cross_report_contract(projected_data)
    if max_evidence_items < 1:
        raise AppError(
            code="cross_report_evidence_limit_invalid",
            message="max_evidence_items must be at least 1",
            retryable=False,
            severity="error",
            context={"max_evidence_items": max_evidence_items},
        )
    selected_report_ids = _ordered_selected_report_ids(source_selection)
    selected_set = set(selected_report_ids)
    selected_order = {
        report_id: index for index, report_id in enumerate(selected_report_ids)
    }
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="cross_report_evidence_input_assembly_start",
            module=logger.name,
            fields={
                "request_id": request.request_id,
                "selected_report_ids": selected_report_ids,
                "projected_evidence_count": len(projected_data.evidence),
                "projected_raw_metric_count": len(projected_data.raw_metrics),
                "max_evidence_items": max_evidence_items,
            },
        )
    )
    dropped: Counter[str] = Counter()
    seen_evidence_keys: set[tuple[str, str]] = set()
    candidate_evidence: list[CrossReportEvidenceReference] = []
    for item in sorted(
        projected_data.evidence,
        key=lambda evidence: _evidence_sort_key(evidence, selected_order),
    ):
        if item.report_id not in selected_set:
            dropped["unselected_report"] += 1
            continue
        evidence_key = (item.report_id, item.evidence_id)
        if evidence_key in seen_evidence_keys:
            dropped["duplicate_evidence_id_same_report"] += 1
            continue
        seen_evidence_keys.add(evidence_key)
        candidate_evidence.append(item)

    bounded_evidence: list[CrossReportEvidenceReference] = []
    for item in candidate_evidence:
        if len(bounded_evidence) >= max_evidence_items:
            dropped["max_evidence_items_reached"] += 1
            continue
        bounded_evidence.append(item)

    raw_metrics: list[CrossReportRawMetricReference] = []
    for metric in sorted(
        projected_data.raw_metrics,
        key=lambda metric: _raw_metric_sort_key(metric, selected_order),
    ):
        if metric.report_id not in selected_set:
            dropped["unselected_raw_metric_report"] += 1
            continue
        raw_metrics.append(metric)

    evidence_by_report: dict[str, list[str]] = {
        report_id: [] for report_id in selected_report_ids
    }
    for item in bounded_evidence:
        evidence_by_report.setdefault(item.report_id, []).append(item.evidence_id)
    evidence_by_report = {
        report_id: evidence_ids
        for report_id, evidence_ids in evidence_by_report.items()
        if evidence_ids
    }
    result = CrossReportEvidenceInputResult(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        selected_sources=source_selection.selected_sources,
        evidence=bounded_evidence,
        raw_metrics=raw_metrics,
        evidence_by_report_id=evidence_by_report,
        dropped_evidence_counts=dict(sorted(dropped.items())),
        prompt_input_chars=_prompt_input_chars(bounded_evidence, raw_metrics),
    )
    validate_cross_report_contract(result)
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="cross_report_evidence_input_assembly_complete",
            module=logger.name,
            fields={
                "request_id": request.request_id,
                "selected_report_ids": selected_report_ids,
                "evidence_count": len(result.evidence),
                "raw_metric_count": len(result.raw_metrics),
                "prompt_input_chars": result.prompt_input_chars,
                "dropped_evidence_counts": result.dropped_evidence_counts,
            },
        )
    )
    return result


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
