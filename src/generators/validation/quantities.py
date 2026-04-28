from __future__ import annotations

from dataclasses import replace
from typing import Any, Iterable, List, Sequence, Tuple

from src.contracts.report_models import ReportPayload
from src.utils.quantity import (
    Quantity,
    extract_quantities,
    quantities_match,
    quantity_has_metric_cues,
)
from src.utils.text_normalization import normalize_text

from .shared import MAGNITUDE_FACTORS, METRIC_ATTRIBUTION_RE, ensure_dict, s


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
        quantities.extend(extract_quantities(s(insight.get("text"))))
        quantities.extend(extract_quantities(s(insight.get("evidence"))))
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
        quantities.extend(extract_quantities(s(summary.get("tldr"))))
        quantities.extend(extract_quantities(s(summary.get("executive_summary"))))
        for claim in summary.get("claim_evidence_map") or []:
            if not isinstance(claim, dict):
                continue
            quantities.extend(extract_quantities(s(claim.get("claim"))))
            quantities.extend(extract_quantities(s(claim.get("evidence"))))
    quantities.extend(
        collect_quantities_from_insights(artifacts.get("insights_final") or [])
    )
    quantities.extend(
        collect_quantities_from_insights(artifacts.get("insights_candidates") or [])
    )
    for quote in artifacts.get("quotes_final") or []:
        if isinstance(quote, dict):
            quantities.extend(extract_quantities(s(quote.get("text"))))
            quantities.extend(extract_quantities(s(quote.get("citation"))))
    return quantities


def collect_quantities_from_texts(texts: Iterable[Any]) -> List[Quantity]:
    quantities: List[Quantity] = []
    for text in texts:
        quantities.extend(extract_quantities(s(text)))
    return quantities


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
    candidate_variants = quantity_numeric_only_variants(candidate)
    evidence_variants = quantity_numeric_only_variants(evidence)
    for candidate_variant in candidate_variants:
        for evidence_variant in evidence_variants:
            approx = (
                candidate_variant.comparator == "approx"
                or evidence_variant.comparator == "approx"
            )
            reference = max(
                abs(candidate_variant.value), abs(evidence_variant.value), 1.0
            )
            tol = numeric_only_tolerance(reference=reference, approx=approx)
            if (
                candidate_variant.comparator == "range"
                or evidence_variant.comparator == "range"
            ):
                if numeric_ranges_overlap(candidate_variant, evidence_variant, tol):
                    return True
                continue
            if candidate_variant.comparator in {"eq", "approx"}:
                if numeric_value_supported_by_comparator(
                    candidate_variant.value, evidence_variant, tol
                ):
                    return True
                continue
            if evidence_variant.comparator in {"eq", "approx"}:
                if numeric_value_supported_by_comparator(
                    evidence_variant.value, candidate_variant, tol
                ):
                    return True
                continue
            if numeric_inequality_compatible(candidate_variant, evidence_variant, tol):
                return True
    return False


def quantity_numeric_only_variants(quantity: Quantity) -> List[Quantity]:
    variants: List[Quantity] = []
    factor = MAGNITUDE_FACTORS.get(s(quantity.magnitude).lower(), 1.0)
    if (
        quantity.comparator == "range"
        and quantity.low is not None
        and quantity.high is not None
    ):
        range_pairs = {(quantity.low, quantity.high)}
        if factor > 1.0:
            range_pairs.add((quantity.low / factor, quantity.high / factor))
        for low, high in range_pairs:
            variants.append(
                replace(
                    quantity,
                    value=(low + high) / 2.0,
                    low=low,
                    high=high,
                    unit_family="unknown",
                    unit="",
                    magnitude="",
                )
            )
        return variants

    numeric_values = {quantity.value}
    if quantity.unit_family in {"percent", "ratio"} or looks_percent_like(quantity):
        numeric_values.add(quantity.value / 100.0)
        numeric_values.add(quantity.value * 100.0)
    if factor > 1.0:
        numeric_values.add(quantity.value / factor)
    for value in sorted(numeric_values):
        variants.append(
            replace(
                quantity,
                value=value,
                low=None,
                high=None,
                unit_family="unknown",
                unit="",
                magnitude="",
            )
        )
    return variants


def looks_percent_like(quantity: Quantity) -> bool:
    raw_norm = normalize_text(quantity.raw)
    return "%" in raw_norm or "percent" in raw_norm or "pct" in raw_norm


def numeric_only_tolerance(*, reference: float, approx: bool) -> float:
    base = max(reference * 0.002, 0.01)
    return base * (2.0 if approx else 1.0)


def numeric_value_supported_by_comparator(
    value: float, claim: Quantity, tol: float
) -> bool:
    if claim.comparator in {"eq", "approx"}:
        return abs(value - claim.value) <= tol
    if claim.comparator == "gt":
        return value > claim.value - tol
    if claim.comparator == "gte":
        return value >= claim.value - tol
    if claim.comparator == "lt":
        return value < claim.value + tol
    if claim.comparator == "lte":
        return value <= claim.value + tol
    if claim.comparator == "range":
        if claim.low is None or claim.high is None:
            return False
        return (claim.low - tol) <= value <= (claim.high + tol)
    return False


def numeric_bounds(quantity: Quantity) -> Tuple[float, float]:
    if (
        quantity.comparator == "range"
        and quantity.low is not None
        and quantity.high is not None
    ):
        return quantity.low, quantity.high
    if quantity.comparator in {"eq", "approx"}:
        return quantity.value, quantity.value
    if quantity.comparator in {"gt", "gte"}:
        return quantity.value, float("inf")
    if quantity.comparator in {"lt", "lte"}:
        return -float("inf"), quantity.value
    return quantity.value, quantity.value


def numeric_ranges_overlap(left: Quantity, right: Quantity, tol: float) -> bool:
    left_low, left_high = numeric_bounds(left)
    right_low, right_high = numeric_bounds(right)
    return max(left_low, right_low) <= min(left_high, right_high) + tol


def numeric_inequality_compatible(
    candidate: Quantity, evidence: Quantity, tol: float
) -> bool:
    candidate_low, candidate_high = numeric_bounds(candidate)
    evidence_low, evidence_high = numeric_bounds(evidence)
    within = (
        candidate_low >= evidence_low - tol and candidate_high <= evidence_high + tol
    ) or (evidence_low >= candidate_low - tol and evidence_high <= candidate_high + tol)
    overlap = (
        max(candidate_low, evidence_low) <= min(candidate_high, evidence_high) + tol
    )
    return within or overlap


def unsupported_quantity_severity(
    *, policy: str, quantity: Quantity, sentence: str
) -> str:
    if policy == "strict":
        return "error"
    if policy == "mixed":
        if METRIC_ATTRIBUTION_RE.search(
            normalize_text(sentence)
        ) or quantity_has_metric_cues(quantity, sentence):
            return "error"
        return "warning"
    if quantity_has_metric_cues(quantity, sentence):
        return "error"
    return "warning"


def quantity_has_metric_cues_from_text(text: str) -> bool:
    quantities = extract_quantities(text)
    if not quantities:
        return False
    return any(quantity_has_metric_cues(quantity, text) for quantity in quantities)
