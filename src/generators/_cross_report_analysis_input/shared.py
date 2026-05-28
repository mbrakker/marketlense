"""Shared deterministic helpers for cross-report input preparation.

This module owns constants, text normalization, date parsing, taxonomy sorting,
and source recency helpers used by the focused input-preparation modules.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from src.contracts.cross_report_analysis import (
    CrossReportAnalysisRequest,
    CrossReportSelectedSourceReport,
    CrossReportSourceReportCandidate,
)
from src.utils.errors import AppError

__all__ = (
    "_DEFAULT_THEME_SCORE_WEIGHTS",
    "_DEFAULT_SIGNAL_SCORE_WEIGHTS",
    "_RAW_METRIC_POLICY",
    "_clean_values",
    "_topic_terms",
    "_slug",
    "_taxonomy_sort_key",
    "_normalize_iso_date_filter",
    "_parse_iso_date",
    "_candidate_date",
    "_selected_source_date",
    "_source_recency_scores",
)


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


def _parse_iso_date(raw_value: object) -> date | None:
    value = str(raw_value or "").strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _candidate_date(candidate: CrossReportSourceReportCandidate) -> date | None:
    value = candidate.report_date.strip()
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
