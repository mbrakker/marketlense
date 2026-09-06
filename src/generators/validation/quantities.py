from __future__ import annotations

import re
from typing import Any, Iterable, List, Sequence

from src.contracts.report_models import ReportPayload
from src.utils.quantity import (
    Quantity,
    canonicalize_quantity,
    extract_quantities,
    quantities_canonically_equivalent,
    quantities_match,
    quantity_has_metric_cues,
)
from .shared import ensure_dict, s


def collect_allowed_quantities(
    insights: Sequence[dict],
    report: ReportPayload,
    artifacts: dict,
    evidence_texts: Sequence[str],
) -> List[Quantity]:
    quantities: List[Quantity] = []
    quantities.extend(collect_quantities_from_insights(insights))
    quantities.extend(collect_quantities_from_report(report))
    quantities.extend(collect_quantities_from_artifacts(artifacts))
    quantities.extend(collect_quantities_from_texts(evidence_texts))
    return quantities


def collect_quantities_from_insights(insights: Sequence[dict]) -> List[Quantity]:
    quantities: List[Quantity] = []
    for insight in insights:
        if not isinstance(insight, dict):
            continue
        metric = ensure_dict(insight.get("metric"))
        for field in ("value", "unit", "timeframe", "sample_size"):
            value = s(metric.get(field))
            if value:
                quantities.extend(extract_quantities(value))
        quantities.extend(_extract_sentence_quantities(s(insight.get("text"))))
        quantities.extend(_extract_sentence_quantities(s(insight.get("evidence"))))
    return quantities


def collect_quantities_from_report(report: ReportPayload) -> List[Quantity]:
    if not isinstance(report, ReportPayload):
        return []
    texts: List[str] = [
        report.tldr,
        report.title,
        report.commentary,
        report.quote.text if getattr(report, "quote", None) else "",
        report.figure.evidence if getattr(report, "figure", None) else "",
        report.time_period,
        report.region,
        report.source,
    ]
    texts.extend(report.insights or [])
    texts.extend(report.taxonomy or [])
    texts.extend(report.categories or [])
    return collect_quantities_from_texts(texts)


def collect_quantities_from_artifacts(artifacts: dict) -> List[Quantity]:
    if not isinstance(artifacts, dict):
        return []
    quantities: List[Quantity] = []
    summary = ensure_dict(artifacts.get("summary"))
    if summary:
        quantities.extend(_extract_sentence_quantities(s(summary.get("tldr"))))
        quantities.extend(
            _extract_sentence_quantities(s(summary.get("executive_summary")))
        )
        for claim in summary.get("claim_evidence_map") or []:
            if not isinstance(claim, dict):
                continue
            quantities.extend(_extract_sentence_quantities(s(claim.get("claim"))))
            quantities.extend(_extract_sentence_quantities(s(claim.get("evidence"))))
    quantities.extend(
        collect_quantities_from_insights(artifacts.get("insights_final") or [])
    )
    quantities.extend(
        collect_quantities_from_insights(artifacts.get("insights_candidates") or [])
    )
    for quote in artifacts.get("quotes_final") or []:
        if isinstance(quote, dict):
            quantities.extend(_extract_sentence_quantities(s(quote.get("text"))))
            quantities.extend(_extract_sentence_quantities(s(quote.get("citation"))))
    return quantities


def collect_quantities_from_texts(texts: Iterable[Any]) -> List[Quantity]:
    quantities: List[Quantity] = []
    for text in texts:
        quantities.extend(_extract_sentence_quantities(s(text)))
    return quantities


def _extract_sentence_quantities(text: str) -> List[Quantity]:
    """Keep a quantity's inferred timeframe local to its source sentence."""

    return [
        quantity
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", text)
        if sentence.strip()
        for quantity in extract_quantities(sentence.strip())
    ]


def quantity_supported(
    candidate: Quantity,
    allowed: Iterable[Quantity],
    *,
    numeric_only: bool = False,
) -> bool:
    if numeric_only:
        return any(
            quantities_match_numeric_only(candidate, evidence) for evidence in allowed
        )
    return any(quantities_match(candidate, evidence) for evidence in allowed)


def all_quantities_supported(
    candidates: Sequence[Quantity],
    allowed: Sequence[Quantity],
    *,
    numeric_only: bool = False,
) -> bool:
    if not candidates:
        return False
    for candidate in candidates:
        if not quantity_supported(candidate, allowed, numeric_only=numeric_only):
            return False
    return True


def quantities_match_numeric_only(candidate: Quantity, evidence: Quantity) -> bool:
    if quantities_canonically_equivalent(candidate, evidence):
        return True
    canonical_candidate = canonicalize_quantity(candidate)
    canonical_evidence = canonicalize_quantity(evidence)
    # A standalone key-figure display intentionally omits the date retained
    # by its linked label and explanatory prose. An explicit conflicting
    # timeframe still fails; only absence may inherit the source context.
    if canonical_candidate.timeframe and canonical_evidence.timeframe:
        return False
    return (
        canonical_candidate.value,
        canonical_candidate.sign,
        canonical_candidate.scale,
        canonical_candidate.comparator,
        canonical_candidate.unit_family,
        canonical_candidate.unit,
        canonical_candidate.currency,
        canonical_candidate.low,
        canonical_candidate.high,
    ) == (
        canonical_evidence.value,
        canonical_evidence.sign,
        canonical_evidence.scale,
        canonical_evidence.comparator,
        canonical_evidence.unit_family,
        canonical_evidence.unit,
        canonical_evidence.currency,
        canonical_evidence.low,
        canonical_evidence.high,
    )


def unsupported_quantity_severity(
    *, policy: str, quantity: Quantity, sentence: str
) -> str:
    del policy, quantity, sentence
    return "error"


def quantity_has_metric_cues_from_text(text: str) -> bool:
    quantities = extract_quantities(text)
    if not quantities:
        return False
    return any(quantity_has_metric_cues(quantity, text) for quantity in quantities)
