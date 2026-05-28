"""Theme selection and publishability checks for cross-report inputs.

This module owns explicit and automatic theme candidates, recent-theme rotation
metadata, novelty scoring, and deterministic publishability validation.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from dataclasses import replace
from datetime import date
from typing import Any

from src.contracts.files import ListDirectoryRequest, ReadTextRequest
from src.contracts.cross_report_analysis import (
    CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
    CrossReportAnalysisRequest,
    CrossReportPublishabilityResult,
    CrossReportSelectedSourceReport,
    CrossReportSelectedTheme,
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

from .shared import (
    _DEFAULT_THEME_SCORE_WEIGHTS,
    _clean_values,
    _parse_iso_date,
    _selected_source_date,
    _slug,
    _source_recency_scores,
    _taxonomy_sort_key,
    _topic_terms,
)

logger = logging.getLogger("market_lense.cross_report_analysis_input_generator")

__all__ = (
    "_theme_score_weights",
    "_weighted_theme_total",
    "_display_value",
    "_theme_candidate_from_sources",
    "_automatic_theme_candidates",
    "_theme_sort_priority",
    "_theme_novelty",
    "_load_recent_theme_metadata",
    "_explicit_theme_candidate",
    "_selected_theme",
    "select_cross_report_theme",
    "_publishability_issues",
    "validate_cross_report_publishability",
)


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
    try:
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
    except AppError as exc:
        if exc.code != "directory_not_found" or exc.retryable:
            raise
        logger.info(
            log_event(
                ctx,
                role="generator",
                event="cross_report_recent_theme_metadata_loaded",
                module=logger.name,
                fields={
                    "recent_artifacts_root": recent_artifacts_root,
                    "theme_rotation_window_days": int(theme_rotation_window_days),
                    "theme_rotation_reference_date": reference_date.isoformat(),
                    "loaded_recent_themes": 0,
                    "skipped_old_artifacts": 0,
                    "skipped_undated_artifacts": 0,
                    "skipped_invalid_date_artifacts": 0,
                    "missing_recent_artifacts_root": True,
                },
            )
        )
        return []
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
                "theme_rotation_window_days": int(theme_rotation_window_days),
                "theme_rotation_reference_date": reference_date.isoformat(),
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
