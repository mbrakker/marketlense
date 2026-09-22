"""Bounded typed compatibility ranking for retained alternative evidence.

This module owns the deterministic compatibility decision used when a repair
must rebind a failed item to different retained evidence.  It reuses the
canonical protected-fact comparison and quantity utilities and never performs
external I/O.  Evidence that conflicts on any protected dimension, or that is
quarantined for this repair, can never win selection.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Sequence, Tuple

from src.contracts.protected_facts import compare_protected_fact_texts
from src.utils.coercion import string_value as _s
from src.utils.text_normalization import normalize_text

__all__ = [
    "CompatibilityQuery",
    "EvidenceCompatibility",
    "rank_compatible_alternatives",
]

# Typed dimension weights.  A compatible dimension earns its weight; an
# incompatible dimension is treated as a hard conflict instead of a small
# penalty so a lexical near-match with the wrong geography, period, cohort,
# denominator, or observation status can never outrank compatible evidence.
_DIMENSION_WEIGHTS: Tuple[Tuple[str, float], ...] = (
    ("population", 3.0),
    ("value", 2.5),
    ("geography", 2.0),
    ("timeframe", 2.0),
    ("unit_currency", 1.5),
    ("observation_status", 1.5),
    ("direction", 1.0),
    ("attribution", 1.0),
    ("comparison", 1.0),
)

_CONFLICT_PENALTY = 8.0
_SAME_PAGE_BONUS = 1.0
_NEAR_PAGE_BONUS = 0.5

_PERIOD_TOKEN_RE = re.compile(
    r"\b(?:q[1-4]\s*20\d{2}|20\d{2}\s*q[1-4]|fy\s*20\d{2}|20\d{2}e|h[12]\s*20\d{2}|"
    r"ytd|mtd|qtd)\b",
    re.IGNORECASE,
)
_FORECAST_TOKEN_RE = re.compile(
    r"\b(?:forecast|projected|projection|predicted|prediction|expected|estimate[ds]?|"
    r"outlook|20\d{2}e)\b",
    re.IGNORECASE,
)
_OBSERVED_TOKEN_RE = re.compile(
    r"\b(?:observed|measured|reported|actual|surveyed|responded)\b", re.IGNORECASE
)
_COHORT_TOKEN_RE = re.compile(
    r"\b(?:respondents?|consumers?|shoppers?|users?|marketers?|decision\s+makers?|"
    r"survey|panel|sample)\b",
    re.IGNORECASE,
)
_DENOMINATOR_TOKEN_RE = re.compile(
    r"\b(?:share\s+of|percentage\s+of|out\s+of)\b",
    re.IGNORECASE,
)

_MAX_TEXT_CHARS = 4000


@dataclass(frozen=True)
class CompatibilityQuery:
    """Typed repair context the alternatives must stay compatible with."""

    text: str = ""
    metric: Mapping[str, Any] = field(default_factory=dict)
    pages: Sequence[int] = field(default_factory=tuple)
    section: str = ""


@dataclass(frozen=True)
class EvidenceCompatibility:
    """One ranked retained alternative with its bounded typed breakdown."""

    evidence_id: str
    score: float
    compatible: bool
    breakdown: Dict[str, float]


def rank_compatible_alternatives(
    query: CompatibilityQuery,
    candidates: Sequence[Tuple[str, Mapping[str, Any]]],
    *,
    quarantined_ids: Sequence[str] = (),
    limit: int = 4,
) -> List[EvidenceCompatibility]:
    """Return at most ``limit`` retained alternatives ordered by typed fit.

    Quarantined identifiers and candidates that conflict on any protected
    dimension are never returned.  An empty result means no compatible
    retained evidence exists and the repair must rebind elsewhere or abstain.
    """

    blocked = {
        normalize_text(evidence_id)
        for evidence_id in quarantined_ids
        if normalize_text(evidence_id)
    }
    ranked: List[EvidenceCompatibility] = []
    for evidence_id, entry in candidates:
        normalized_id = normalize_text(evidence_id)
        if not normalized_id or normalized_id in blocked:
            continue
        breakdown = _score_entry(query, entry)
        if breakdown is None:
            continue
        ranked.append(
            EvidenceCompatibility(
                evidence_id=evidence_id,
                score=round(breakdown["score"], 6),
                compatible=bool(breakdown["compatible"]),
                breakdown=breakdown,
            )
        )
    ranked.sort(key=lambda item: (-item.score, item.evidence_id))
    return [item for item in ranked[: max(0, int(limit))] if item.compatible]


def _score_entry(
    query: CompatibilityQuery, entry: Mapping[str, Any]
) -> Dict[str, float] | None:
    evidence_text = _entry_text(entry)
    if not evidence_text:
        return None
    claim_text = query.text[:_MAX_TEXT_CHARS]
    comparison = (
        compare_protected_fact_texts(claim_text, evidence_text) if claim_text else None
    )
    breakdown: Dict[str, float] = {"score": 0.0, "compatible": 1.0}
    score = 0.0
    conflicting = False
    if comparison is not None:
        for dimension, weight in _DIMENSION_WEIGHTS:
            status = comparison.dimensions[dimension].status
            if status == "compatible":
                score += weight
            elif status == "incompatible":
                conflicting = True
                score -= _CONFLICT_PENALTY
        if comparison.proposition_status == "incompatible":
            conflicting = True
    score += _metric_score(query.metric, evidence_text)
    period_score, period_conflict = _period_score(claim_text, evidence_text)
    status_score, status_conflict = _observation_status_score(claim_text, evidence_text)
    cohort_score, cohort_conflict = _cohort_denominator_score(claim_text, evidence_text)
    metric_match = _metric_match(query.metric, evidence_text)
    token_relevance = _token_relevance(claim_text, evidence_text)
    score += period_score
    score += status_score
    score += cohort_score
    score += metric_match
    score += _page_score(query.pages, _entry_pages(entry))
    score += token_relevance
    conflicting = conflicting or period_conflict or status_conflict or cohort_conflict
    breakdown["score"] = score
    breakdown["metric_match"] = metric_match
    breakdown["token_relevance"] = token_relevance
    breakdown["compatible"] = 0.0 if conflicting else 1.0
    return breakdown


def _metric_score(metric: Mapping[str, Any], evidence_text: str) -> float:
    """Reward metric fields the evidence explicitly restate."""

    return _metric_match(metric, evidence_text) * 3.0


def _metric_match(metric: Mapping[str, Any], evidence_text: str) -> float:
    score = 0.0
    lowered = evidence_text.casefold()
    value = _s(metric.get("value")).strip()
    if value and value.casefold() in lowered:
        score += 1.5
    for field_name in ("timeframe", "geography", "subject", "segment"):
        field_value = _s(metric.get(field_name)).strip().casefold()
        if field_value and field_value in lowered:
            score += 0.5
    unit = _s(metric.get("unit")).strip().casefold()
    if unit and unit in lowered:
        score += 0.5
    status = _s(metric.get("observation_status")).strip().casefold()
    if status in {"forecast", "estimate"} and _FORECAST_TOKEN_RE.search(evidence_text):
        score += 0.5
    if status in {"observed", "measured"} and _OBSERVED_TOKEN_RE.search(evidence_text):
        score += 0.5
    return score


def _period_score(claim_text: str, evidence_text: str) -> Tuple[float, bool]:
    claim_periods = set(_PERIOD_TOKEN_RE.findall(claim_text))
    if not claim_periods:
        return 0.0, False
    evidence_periods = set(_PERIOD_TOKEN_RE.findall(evidence_text))
    if not evidence_periods:
        return 0.0, False
    if claim_periods & evidence_periods:
        return 1.0, False
    # An explicit quarter/fiscal-period mismatch describes a different period
    # even when the quantity matches exactly.
    return -_CONFLICT_PENALTY, True


def _observation_status_score(
    claim_text: str, evidence_text: str
) -> Tuple[float, bool]:
    claim_forecast = bool(_FORECAST_TOKEN_RE.search(claim_text))
    evidence_forecast = bool(_FORECAST_TOKEN_RE.search(evidence_text))
    if claim_forecast and evidence_forecast:
        return 1.0, False
    if claim_forecast != evidence_forecast:
        # A forecast claim and an observed datum describe different facts even
        # when every other token overlaps.
        return -_CONFLICT_PENALTY, True
    return 0.0, False


def _cohort_denominator_score(
    claim_text: str, evidence_text: str
) -> Tuple[float, bool]:
    score = 0.0
    conflicting = False
    claim_cohorts = set(_COHORT_TOKEN_RE.findall(claim_text))
    if claim_cohorts:
        evidence_cohorts = set(_COHORT_TOKEN_RE.findall(evidence_text))
        if evidence_cohorts:
            if claim_cohorts & evidence_cohorts:
                score += 1.0
            else:
                # A different surveyed population can never support the same
                # number even when all other tokens overlap.
                score -= _CONFLICT_PENALTY
                conflicting = True
    claim_denominators = set(_DENOMINATOR_TOKEN_RE.findall(claim_text))
    if claim_denominators:
        evidence_denominators = set(_DENOMINATOR_TOKEN_RE.findall(evidence_text))
        if evidence_denominators and claim_denominators == evidence_denominators:
            score += 0.5
    return score, conflicting


def _page_score(query_pages: Sequence[int], entry_pages: Sequence[int]) -> float:
    if not query_pages or not entry_pages:
        return 0.0
    if set(query_pages) & set(entry_pages):
        return _SAME_PAGE_BONUS
    if any(
        abs(query_page - page) <= 1
        for query_page in query_pages
        for page in entry_pages
    ):
        return _NEAR_PAGE_BONUS
    return 0.0


def _token_relevance(claim_text: str, evidence_text: str) -> float:
    """Small bounded lexical tiebreak strictly below every typed dimension."""

    claim_tokens = _relevance_tokens(claim_text)
    if not claim_tokens:
        return 0.0
    evidence_tokens = _relevance_tokens(evidence_text)
    if not evidence_tokens:
        return 0.0
    overlap = len(claim_tokens & evidence_tokens)
    return min(overlap / max(len(claim_tokens), 1), 1.0) * 0.5


def _relevance_tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9][a-z0-9_-]+", text.casefold())
        if len(token) >= 4
    }


def _entry_text(entry: Mapping[str, Any]) -> str:
    parts = [
        _s(entry.get(field_name))
        for field_name in (
            "text",
            "evidence",
            "summary",
            "claim",
            "title",
            "label",
            "section_title",
            "heading",
        )
    ]
    text = " ".join(part.strip() for part in parts if part.strip())
    if not text:
        # Deterministic bounded projection of structured entries without a
        # single dominant text field, excluding nested and volatile payloads.
        text = " ".join(
            _s(value).strip()
            for key, value in sorted(entry.items())
            if isinstance(value, (str, int, float)) and _s(value).strip()
        )
    return text[:_MAX_TEXT_CHARS]


def _entry_pages(entry: Mapping[str, Any]) -> List[int]:
    pages: List[int] = []
    raw_pages = entry.get("pages")
    if isinstance(raw_pages, list):
        pages.extend(value for value in raw_pages if isinstance(value, int))
    page = entry.get("page")
    if isinstance(page, int):
        pages.append(page)
    return pages
