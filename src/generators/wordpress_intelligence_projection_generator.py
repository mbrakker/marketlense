"""Builds public WordPress intelligence projections from approved entity records."""

from __future__ import annotations

# ruff: noqa: E501
from collections import Counter
from datetime import datetime, timedelta, timezone

from src.contracts.wordpress_intelligence_projection import (
    WORDPRESS_INTELLIGENCE_PROJECTION_VERSION,
    WORDPRESS_INTELLIGENCE_SCHEMA_VERSION,
    WordPressHomepageMetrics,
    WordPressIntelligenceBuildRequest,
    WordPressIntelligenceEntity,
    WordPressIntelligenceMetric,
    WordPressIntelligenceProjection,
    WordPressIntelligenceTerm,
    WordPressWeeklyIntelligence,
)
from src.utils.errors import AppError

_WINDOW_DAYS = 30
_ITEM_LIMIT = 6


def _parsed_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AppError(
            code="wordpress_intelligence_source_timestamp_invalid",
            message="Published WordPress entity timestamp is invalid",
            cause=exc,
            retryable=False,
            severity="error",
            context={"published_at_utc": value},
        ) from exc
    return parsed.astimezone(timezone.utc)


def _terms_by_entity(
    entities: list[WordPressIntelligenceEntity], *, publisher: bool
) -> dict[str, WordPressIntelligenceTerm]:
    terms: dict[str, WordPressIntelligenceTerm] = {}
    for entity in entities:
        for term in entity.publishers if publisher else entity.topics:
            key = term.name.casefold()
            if key and key not in terms:
                terms[key] = term
    return terms


def _count_terms(
    entities: list[WordPressIntelligenceEntity], *, publisher: bool
) -> Counter[str]:
    counts: Counter[str] = Counter()
    for entity in entities:
        terms = entity.publishers if publisher else entity.topics
        counts.update({term.name.casefold() for term in terms if term.name.strip()})
    return counts


def _metrics(
    current: Counter[str],
    previous: Counter[str],
    terms: dict[str, WordPressIntelligenceTerm],
    *,
    include_delta: bool,
    limit: int = _ITEM_LIMIT,
) -> list[WordPressIntelligenceMetric]:
    ranked = sorted(
        current, key=lambda key: (-current[key], terms[key].name.casefold())
    )[:limit]
    return [
        WordPressIntelligenceMetric(
            schema_version=WORDPRESS_INTELLIGENCE_SCHEMA_VERSION,
            name=terms[key].name,
            count=current[key],
            delta=(current[key] - previous[key])
            if include_delta and current[key] != previous[key]
            else None,
            url=terms[key].url,
            homepage=terms[key].homepage,
        )
        for key in ranked
    ]


def _latest_label(
    entities: list[WordPressIntelligenceEntity], generated_at_utc: str
) -> str:
    if not entities:
        return ""
    generated = _parsed_timestamp(generated_at_utc)
    latest = max(_parsed_timestamp(entity.published_at_utc) for entity in entities)
    if generated.date() == latest.date():
        return "Updated today"
    return f"Updated {latest.date().isoformat()}"


def build_wordpress_intelligence_projection(
    request: WordPressIntelligenceBuildRequest,
) -> WordPressIntelligenceProjection:
    """Aggregate only approved entities; no model call or filesystem access occurs here."""
    generated = _parsed_timestamp(request.generated_at_utc)
    entities = request.source.entities
    current_start = generated - timedelta(days=_WINDOW_DAYS)
    previous_start = current_start - timedelta(days=_WINDOW_DAYS)
    current = [
        entity
        for entity in entities
        if current_start <= _parsed_timestamp(entity.published_at_utc) <= generated
    ]
    previous = [
        entity
        for entity in entities
        if previous_start <= _parsed_timestamp(entity.published_at_utc) < current_start
    ]
    topic_terms = _terms_by_entity(entities, publisher=False)
    publisher_terms = _terms_by_entity(entities, publisher=True)
    topic_current = _count_terms(current, publisher=False)
    topic_previous = _count_terms(previous, publisher=False)
    publisher_current = _count_terms(current, publisher=True)
    publisher_previous = _count_terms(previous, publisher=True)
    trending_topics = _metrics(
        topic_current, topic_previous, topic_terms, include_delta=True
    )
    emerging_themes = [
        item for item in trending_topics if item.delta is not None and item.delta > 0
    ]
    if not emerging_themes:
        emerging_themes = trending_topics
    report_count = sum(entity.entity_type == "ml_report" for entity in entities)
    briefing_count = sum(entity.entity_type == "ml_briefing" for entity in entities)
    signal_count = sum(entity.entity_type == "ml_signal" for entity in entities)
    return WordPressIntelligenceProjection(
        schema_version=WORDPRESS_INTELLIGENCE_SCHEMA_VERSION,
        projection_version=WORDPRESS_INTELLIGENCE_PROJECTION_VERSION,
        generated_at_utc=request.generated_at_utc,
        homepage_metrics=WordPressHomepageMetrics(
            schema_version=WORDPRESS_INTELLIGENCE_SCHEMA_VERSION,
            report_count=report_count,
            publisher_count=len(publisher_terms),
            topic_count=len(topic_terms),
            briefing_count=briefing_count,
            signal_count=signal_count,
            signal_label="Published signals",
            citation_count=0,
            latest_label=_latest_label(entities, request.generated_at_utc),
        ),
        weekly_signals=WordPressWeeklyIntelligence(
            schema_version=WORDPRESS_INTELLIGENCE_SCHEMA_VERSION,
            window_label=f"Past {_WINDOW_DAYS} days",
            trending_topics=trending_topics,
            emerging_themes=emerging_themes,
            top_publishers=_metrics(
                publisher_current,
                publisher_previous,
                publisher_terms,
                include_delta=False,
            ),
        ),
        strategic_themes=_metrics(
            _count_terms(entities, publisher=False),
            topic_previous,
            topic_terms,
            include_delta=True,
        ),
        publisher_authority=_metrics(
            _count_terms(entities, publisher=True),
            Counter(),
            publisher_terms,
            include_delta=False,
            limit=12,
        ),
    )
