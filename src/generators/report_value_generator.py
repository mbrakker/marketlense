from __future__ import annotations

import logging
import re
from statistics import pstdev
from urllib.parse import urlsplit

from src.contracts.report_store import (
    PublisherResourceRankingItem,
    PublisherResourceRankingRequest,
    PublisherResourceRankingResponse,
    ReportSourceQualityHistoryItem,
    ReportValueScoreComponent,
    ReportValueScoreRequest,
    ReportValueScoreResponse,
)
from src.contracts.run_context import RunContext
from src.utils.logging import log_event
from src.utils.url_utils import normalize_url

logger = logging.getLogger("market_lense.report_value_generator")

_REPORT_MARKERS = (
    "report",
    "research",
    "study",
    "survey",
    "benchmark",
    "outlook",
    "forecast",
    "trend",
    "trends",
    "whitepaper",
    "white paper",
    "guide",
    "playbook",
    "index",
)
_INSIGHT_MARKERS = (
    "market",
    "industry",
    "consumer",
    "customer",
    "commerce",
    "retail",
    "growth",
    "forecast",
    "outlook",
    "driver",
    "risk",
    "strategy",
    "implication",
)
_EVIDENCE_MARKERS = (
    "data",
    "benchmark",
    "survey",
    "methodology",
    "sample",
    "respondents",
    "statistics",
    "figures",
    "index",
)
_DECISION_MARKERS = (
    "strategy",
    "playbook",
    "guide",
    "priorities",
    "recommendations",
    "forecast",
    "outlook",
    "benchmark",
    "predictions",
)
_AUTHORITY_MARKERS = (
    "proprietary",
    "primary research",
    "survey",
    "benchmark",
    "index",
    "methodology",
    "annual",
    "global",
)
_LOW_VALUE_MARKERS = (
    "case study",
    "customer story",
    "webinar",
    "podcast",
    "press release",
    "blog",
    "demo",
    "pricing",
    "contact sales",
)
_YEAR_RX = re.compile(r"\b(20[1-3][0-9])\b")
_NUMBER_RX = re.compile(r"\b(?:\d+(?:\.\d+)?%?|\d+\s*(?:bn|m|k|million|billion))\b")


def score_report_value(
    request: ReportValueScoreRequest, ctx: RunContext
) -> ReportValueScoreResponse:
    title = request.report_name.strip()
    landing_url = request.landing_page_url.strip()
    source_url = request.source_page_url.strip()
    text = " ".join(
        [
            title,
            landing_url.replace("-", " ").replace("_", " "),
            source_url.replace("-", " ").replace("_", " "),
            request.source_domain,
            request.publisher_name,
        ]
    ).casefold()
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="report_value_score_start",
            module=logger.name,
            fields={
                "publisher_name": request.publisher_name,
                "source_domain": request.source_domain,
                "report_name": request.report_name,
                "landing_page_url": request.landing_page_url,
                "source_status": request.source_status,
                "evaluation_year": request.evaluation_year,
            },
        )
    )
    components = [
        _component(
            "market_insight_depth",
            _score_market_insight_depth(text, title),
            _matched_reason(text, _INSIGHT_MARKERS, "market insight markers"),
        ),
        _component(
            "evidence_specificity",
            _score_evidence_specificity(text),
            _matched_reason(
                text, _EVIDENCE_MARKERS, "evidence and methodology markers"
            ),
        ),
        _component(
            "decision_relevance",
            _score_decision_relevance(text),
            _matched_reason(text, _DECISION_MARKERS, "decision-use markers"),
        ),
        _component(
            "recency_timeliness",
            _score_recency_timeliness(text, request.evaluation_year),
            _recency_reason(text, request.evaluation_year),
        ),
        _component(
            "source_authority_originality",
            _score_source_authority_originality(text, request.source_domain),
            _matched_reason(text, _AUTHORITY_MARKERS, "authority/originality markers"),
        ),
    ]
    raw_overall = sum(component.score for component in components) / len(components)
    low_value_penalty = (
        14.0 if any(marker in text for marker in _LOW_VALUE_MARKERS) else 0.0
    )
    downloaded_bonus = (
        3.0 if request.source_status == "downloaded" and request.md5 else 0.0
    )
    overall = _clamp_score(raw_overall - low_value_penalty + downloaded_bonus)
    response = ReportValueScoreResponse(
        schema_version="1.0",
        overall_score=round(overall, 3),
        value_band=_value_band(overall),
        components=components,
        rationale=_overall_rationale(overall, components, low_value_penalty),
    )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="report_value_score_complete",
            module=logger.name,
            fields={
                "publisher_name": request.publisher_name,
                "landing_page_url": request.landing_page_url,
                "overall_score": response.overall_score,
                "value_band": response.value_band,
                "component_scores": {
                    component.dimension: component.score
                    for component in response.components
                },
                "rationale": response.rationale,
            },
        )
    )
    return response


def rank_publisher_resources(
    request: PublisherResourceRankingRequest, ctx: RunContext
) -> PublisherResourceRankingResponse:
    policy = request.policy
    candidate_urls = [_resource_key(url) for url in request.candidate_source_page_urls]
    candidate_urls = [
        url
        for index, url in enumerate(candidate_urls)
        if url and url not in candidate_urls[:index]
    ]
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="publisher_resource_ranking_start",
            module=logger.name,
            fields={
                "publisher_name": request.publisher_name,
                "candidate_resource_count": len(candidate_urls),
                "history_count": len(request.history_items),
                "score_window_size": policy.score_window_size,
                "min_sample_size": policy.min_sample_size,
                "consistency_weight": policy.consistency_weight,
                "average_score_weight": policy.average_score_weight,
                "confidence_weight": policy.confidence_weight,
            },
        )
    )
    history_by_resource: dict[str, list[ReportSourceQualityHistoryItem]] = {}
    for item in request.history_items:
        key = _resource_key(item.source_page_url) or _resource_key(
            item.landing_page_url
        )
        if not key:
            continue
        history_by_resource.setdefault(key, []).append(item)
    ranked = [
        _rank_resource(resource_url, history_by_resource.get(resource_url, []), policy)
        for resource_url in candidate_urls
    ]
    ranked.sort(
        key=lambda item: (-item.rank_score, item.demotion_reason, item.resource_url)
    )
    response = PublisherResourceRankingResponse(
        schema_version="1.0",
        publisher_name=request.publisher_name,
        items=ranked,
    )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="publisher_resource_ranking_complete",
            module=logger.name,
            fields={
                "publisher_name": response.publisher_name,
                "ranked_resource_count": len(response.items),
                "top_rank_score": response.items[0].rank_score
                if response.items
                else 0.0,
            },
        )
    )
    return response


def _component(
    dimension: str, score: float, rationale: str
) -> ReportValueScoreComponent:
    return ReportValueScoreComponent(
        schema_version="1.0",
        dimension=dimension,
        score=round(_clamp_score(score), 3),
        rationale=rationale,
    )


def _score_market_insight_depth(text: str, title: str) -> float:
    score = 28.0
    score += _marker_score(text, _REPORT_MARKERS, 24.0)
    score += _marker_score(text, _INSIGHT_MARKERS, 34.0)
    if len(title.split()) >= 5:
        score += 8.0
    return _penalize_low_value(text, score)


def _score_evidence_specificity(text: str) -> float:
    score = 24.0 + _marker_score(text, _EVIDENCE_MARKERS, 34.0)
    if _NUMBER_RX.search(text):
        score += 16.0
    if _YEAR_RX.search(text):
        score += 10.0
    return _penalize_low_value(text, score)


def _score_decision_relevance(text: str) -> float:
    score = 26.0 + _marker_score(text, _REPORT_MARKERS, 20.0)
    score += _marker_score(text, _DECISION_MARKERS, 38.0)
    return _penalize_low_value(text, score)


def _score_recency_timeliness(text: str, evaluation_year: int) -> float:
    years = [int(match.group(1)) for match in _YEAR_RX.finditer(text)]
    if not years:
        return 58.0
    newest = max(years)
    if newest >= evaluation_year:
        return 94.0
    age = max(0, evaluation_year - newest)
    return max(22.0, 90.0 - age * 16.0)


def _score_source_authority_originality(text: str, source_domain: str) -> float:
    score = 38.0 + _marker_score(text, _AUTHORITY_MARKERS, 36.0)
    host = str(urlsplit(f"https://{source_domain.strip()}").hostname or source_domain)
    if host and not any(
        host.endswith(suffix) for suffix in (".wordpress.com", ".medium.com")
    ):
        score += 10.0
    return _penalize_low_value(text, score)


def _marker_score(text: str, markers: tuple[str, ...], max_score: float) -> float:
    hits = sum(1 for marker in markers if marker in text)
    return min(max_score, hits * (max_score / 3.0))


def _penalize_low_value(text: str, score: float) -> float:
    if any(marker in text for marker in _LOW_VALUE_MARKERS):
        return score - 24.0
    return score


def _clamp_score(value: float) -> float:
    return max(0.0, min(100.0, float(value)))


def _value_band(score: float) -> str:
    if score >= 78.0:
        return "high"
    if score >= 60.0:
        return "medium"
    if score >= 42.0:
        return "low"
    return "weak"


def _matched_reason(text: str, markers: tuple[str, ...], label: str) -> str:
    hits = [marker for marker in markers if marker in text][:4]
    return f"{label}: {', '.join(hits)}" if hits else f"no strong {label}"


def _recency_reason(text: str, evaluation_year: int) -> str:
    years = [int(match.group(1)) for match in _YEAR_RX.finditer(text)]
    if not years:
        return "no explicit publication or coverage year"
    newest = max(years)
    return f"newest explicit year {newest} against evaluation year {evaluation_year}"


def _overall_rationale(
    overall: float,
    components: list[ReportValueScoreComponent],
    low_value_penalty: float,
) -> str:
    strongest = max(components, key=lambda component: component.score)
    weakest = min(components, key=lambda component: component.score)
    penalty = " with low-value marker penalty" if low_value_penalty else ""
    return (
        f"{_value_band(overall)} value; strongest={strongest.dimension}, "
        f"weakest={weakest.dimension}{penalty}"
    )


def _resource_key(url: str) -> str:
    token = str(url or "").strip()
    if not token:
        return ""
    normalized = normalize_url(token)
    return normalized or token


def _rank_resource(
    resource_url: str,
    history: list[ReportSourceQualityHistoryItem],
    policy,
) -> PublisherResourceRankingItem:
    ordered = sorted(
        history,
        key=lambda item: (
            item.scored_at_utc or item.downloaded_at_utc or item.discovered_at_utc,
            item.landing_page_url,
        ),
        reverse=True,
    )[: max(1, policy.score_window_size)]
    scores = [float(item.overall_score) for item in ordered]
    sample_size = len(scores)
    if not scores:
        return PublisherResourceRankingItem(
            schema_version="1.0",
            resource_url=resource_url,
            sample_size=0,
            score_window_size=policy.score_window_size,
            average_value_score=0.0,
            latest_value_score=0.0,
            consistency_score=0.0,
            confidence=0.0,
            rank_score=0.0,
            demotion_reason="insufficient_history",
        )
    average = sum(scores) / sample_size
    spread = pstdev(scores) if sample_size > 1 else 0.0
    consistency = max(0.0, 1.0 - min(1.0, spread / 30.0))
    confidence = min(1.0, sample_size / max(1, policy.min_sample_size))
    rank_score = (
        (average / 100.0) * policy.average_score_weight
        + consistency * policy.consistency_weight
        + confidence * policy.confidence_weight
    )
    demotion_reason = ""
    if sample_size < policy.min_sample_size:
        demotion_reason = "insufficient_history"
        rank_score *= 0.72
    elif average < policy.low_score_demotion_threshold:
        demotion_reason = "low_average_value"
        rank_score *= 0.55
    return PublisherResourceRankingItem(
        schema_version="1.0",
        resource_url=resource_url,
        sample_size=sample_size,
        score_window_size=policy.score_window_size,
        average_value_score=round(average, 3),
        latest_value_score=round(scores[0], 3),
        consistency_score=round(consistency, 3),
        confidence=round(confidence, 3),
        rank_score=round(rank_score, 3),
        demotion_reason=demotion_reason,
    )
