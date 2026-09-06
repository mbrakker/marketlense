from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from src.utils.text_normalization import normalize_for_lookup, normalize_text

Comparator = str

_NUMBER_RE = r"[+-]?\s*(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
_COMP_RE = (
    r"(?:>=|<=|>|<|~|≈|"
    r"more than|over|above|greater than|at least|"
    r"less than|under|below|at most|about|around|approximately)"
)
_MAG_RE = r"(?:k|m|mm|mn|b|bn|t|tn|thousand|million|billion|trillion)\b"

_RANGE_RE = re.compile(
    rf"(?<!\w)(?:between\s+)?(?P<low>{_NUMBER_RE})\s*(?:-|to|and)\s*(?P<high>{_NUMBER_RE})\s*"
    r"(?P<unit>percentage points?|basis points?|%|percent|pct|pp|bps|usd|eur|gbp|jpy|"
    r"k|m|mm|mn|b|bn|tn|thousand|million|billion|trillion)?(?!\w)",
    re.IGNORECASE,
)
_RATIO_RE = re.compile(
    r"\b(?P<a>\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+"
    r"(?:(?:in)|(?:out of))\s+"
    r"(?P<b>\d+|one|two|three|four|five|six|seven|eight|nine|ten)\b",
    re.IGNORECASE,
)
_N_EQUALS_RE = re.compile(r"\bn\s*=\s*(?P<n>\d{1,3}(?:,\d{3})+|\d+)\b", re.IGNORECASE)
_MULT_RE = re.compile(rf"\b(?P<num>{_NUMBER_RE})\s*x\b", re.IGNORECASE)
_MAIN_RE = re.compile(
    rf"(?<![A-Za-z0-9])(?P<prefix>{_COMP_RE})?\s*"
    r"(?P<currency>[$€£¥])?\s*"
    rf"(?P<number>{_NUMBER_RE})"
    rf"(?:\s*(?P<magnitude>{_MAG_RE}))?"
    r"(?:\s*(?P<unit>percentage points?|basis points?|%|percent|pct|pp|bps|usd|eur|gbp|jpy|"
    r"users?|downloads?|respondents?|impressions?|installs?|visits?|sessions?|"
    r"kbps|mbps|gbps|"
    r"minutes?|hours?|days?|weeks?|months?|years?|points?|index|rank|"
    r"times?|yoy|mom|qoq|cagr|per day|per month|per year))?",
    re.IGNORECASE,
)
_TIMEFRAME_RE = re.compile(
    r"\b(?:"
    r"q[1-4]\s*20\d{2}|20\d{2}\s*q[1-4]|"
    r"fy\s*20\d{2}|20\d{2}\s*forecast|"
    r"ytd|mtd|qtd|yoy|mom|qoq|"
    r"[a-z]{3,9}\s+\d{1,2}\s*-\s*[a-z]{3,9}\s+\d{1,2},?\s*20\d{2}|"
    r"[a-z]{3,9}\s+\d{1,2},?\s*20\d{2}|"
    r"20\d{2}"
    r")\b",
    re.IGNORECASE,
)

_CURRENCY_CODES = {"usd", "eur", "gbp", "jpy"}
_CURRENCY_SYMBOL_TO_CODE = {"$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY"}
_MAG_FACTORS = {
    "k": 1_000.0,
    "thousand": 1_000.0,
    "m": 1_000_000.0,
    "mm": 1_000_000.0,
    "mn": 1_000_000.0,
    "million": 1_000_000.0,
    "b": 1_000_000_000.0,
    "bn": 1_000_000_000.0,
    "billion": 1_000_000_000.0,
    "t": 1_000_000_000_000.0,
    "tn": 1_000_000_000_000.0,
    "trillion": 1_000_000_000_000.0,
}
_WORDS_TO_NUM = {
    "one": 1.0,
    "two": 2.0,
    "three": 3.0,
    "four": 4.0,
    "five": 5.0,
    "six": 6.0,
    "seven": 7.0,
    "eight": 8.0,
    "nine": 9.0,
    "ten": 10.0,
}
_METRIC_HINTS = {
    "respondents",
    "agree",
    "increase",
    "decrease",
    "growth",
    "decline",
    "yoy",
    "mom",
    "qoq",
    "revenue",
    "spend",
    "share",
    "rank",
    "index",
    "conversion",
    "conversions",
    "users",
    "downloads",
    "impressions",
    "installs",
    "sample",
    "cagr",
    "rate",
    "margin",
}
_SOFT_FOOTNOTE_RE = re.compile(r"[\[\(]\s*\d{1,2}\s*[\]\)]")


@dataclass(frozen=True)
class Quantity:
    value: float
    comparator: Comparator
    unit_family: str
    unit: str
    magnitude: str
    start: int
    end: int
    sentence: str
    timeframe: str
    confidence: float
    raw: str = ""
    low: Optional[float] = None
    high: Optional[float] = None


@dataclass(frozen=True)
class CanonicalQuantity:
    """Universal, display-independent primitives for one explicit quantity."""

    value: float
    sign: int
    scale: float
    comparator: Comparator
    unit_family: str
    unit: str
    currency: str
    low: Optional[float]
    high: Optional[float]
    timeframe: str


def extract_quantities(text: str) -> List[Quantity]:
    normalized = normalize_for_lookup(text)
    if not normalized:
        return []
    quantities: List[Quantity] = []
    quantities.extend(_extract_ranges(normalized))
    quantities.extend(_extract_ratios(normalized))
    quantities.extend(_extract_n_equals(normalized))
    quantities.extend(_extract_main(normalized))
    quantities.extend(_extract_multipliers(normalized))
    return _dedupe_quantities(quantities)


def quantities_match(candidate: Quantity, evidence: Quantity) -> bool:
    if not _unit_families_compatible(candidate, evidence):
        return False

    cand_values = _canonical_values(candidate)
    ev_values = _canonical_values(evidence)
    if not cand_values or not ev_values:
        return False

    family = _resolved_family(candidate, evidence)
    approx = candidate.comparator == "approx" or evidence.comparator == "approx"
    tol = _tolerance(
        family,
        reference=max(abs(cand_values[0]), abs(ev_values[0]), 1.0),
        approx=approx,
    )

    if candidate.comparator == "range" or evidence.comparator == "range":
        return _ranges_overlap(candidate, evidence, tol)

    # Candidate exact/approx should be contained by evidence claim.
    if candidate.comparator in {"eq", "approx"}:
        return any(
            _value_supported_by_comparator(v, evidence, tol) for v in cand_values
        )

    # Candidate inequalities should be compatible with evidence.
    if evidence.comparator in {"eq", "approx"}:
        return any(_value_supported_by_comparator(v, candidate, tol) for v in ev_values)

    return _inequality_compatible(candidate, evidence, tol)


def canonicalize_quantity(quantity: Quantity) -> CanonicalQuantity:
    """Return the explicit universal primitives of a parsed quantity.

    This retains unit, currency, range, and timeframe identity. It is not a
    metric or subject-equivalence mechanism.
    """
    scale = _MAG_FACTORS.get(_clean_unit(quantity.magnitude), 1.0)
    raw_value = quantity.value / scale
    raw_low = quantity.low / scale if quantity.low is not None else None
    raw_high = quantity.high / scale if quantity.high is not None else None
    return CanonicalQuantity(
        value=abs(_round_canonical(raw_value)),
        sign=_sign(raw_value),
        scale=scale,
        comparator="eq" if quantity.comparator == "approx" else quantity.comparator,
        unit_family=quantity.unit_family,
        unit=quantity.unit,
        currency=quantity.unit if quantity.unit_family == "currency" else "",
        low=_round_canonical(raw_low) if raw_low is not None else None,
        high=_round_canonical(raw_high) if raw_high is not None else None,
        timeframe=normalize_for_lookup(quantity.timeframe),
    )


def quantities_canonically_equivalent(left: Quantity, right: Quantity) -> bool:
    """Compare only explicit universal quantity primitives."""
    return canonicalize_quantity(left) == canonicalize_quantity(right)


def should_ground_quantity(
    quantity: Quantity,
    sentence: str,
    *,
    section_policy: str,
    strict_section: bool = False,
) -> bool:
    sentence_norm = normalize_text(sentence)
    explicit_unit = quantity.unit_family != "unknown" or bool(quantity.unit)
    metric_context = _has_metric_context(sentence_norm)
    if strict_section or section_policy == "strict":
        if (
            _looks_like_non_metric_token(quantity, sentence_norm)
            and not metric_context
            and not explicit_unit
        ):
            return False
        return True
    if quantity.unit_family == "time" and not metric_context:
        return False
    if explicit_unit:
        return not _looks_like_non_metric_token(quantity, sentence_norm)
    if metric_context:
        return not _looks_like_non_metric_token(quantity, sentence_norm)
    return False


def quantity_has_metric_cues(quantity: Quantity, sentence: str) -> bool:
    return quantity.unit_family != "unknown" or _has_metric_context(
        normalize_text(sentence)
    )


def infer_timeframe(text: str) -> str:
    normalized = normalize_for_lookup(text)
    if not normalized:
        return ""
    matches = [m.group(0) for m in _TIMEFRAME_RE.finditer(normalized)]
    if not matches:
        return ""
    return ", ".join(dict.fromkeys(matches))


def _extract_ranges(text: str) -> List[Quantity]:
    output: List[Quantity] = []
    for match in _RANGE_RE.finditer(text):
        low = _to_float(match.group("low"))
        high = _to_float(match.group("high"))
        if low is None or high is None:
            continue
        unit = _clean_unit(match.group("unit"))
        if unit in {"%", "percent", "pct", "pp", "percentage point", "percentage points"} and re.fullmatch(
            r"20\d{2}", match.group("low").strip()
        ):
            # "from 16.3% in 2024 to 17.8%" is a time comparison, not a
            # 2024-to-17.8 percent range.
            continue
        family, canonical_unit, magnitude = _resolve_unit_family(
            unit=unit,
            currency="",
            magnitude=unit if unit in _MAG_FACTORS else "",
            sentence=text,
            span=(match.start(), match.end()),
        )
        factor = _MAG_FACTORS.get(magnitude, 1.0)
        low_v = low * factor
        high_v = high * factor
        if high_v < low_v:
            low_v, high_v = high_v, low_v
        output.append(
            Quantity(
                value=(low_v + high_v) / 2.0,
                comparator="range",
                unit_family=family,
                unit=canonical_unit,
                magnitude=magnitude,
                start=match.start(),
                end=match.end(),
                sentence=text,
                timeframe=infer_timeframe(text),
                confidence=0.9 if canonical_unit else 0.65,
                raw=match.group(0),
                low=low_v,
                high=high_v,
            )
        )
    return output


def _extract_ratios(text: str) -> List[Quantity]:
    output: List[Quantity] = []
    for match in _RATIO_RE.finditer(text):
        a = _word_or_number(match.group("a"))
        b = _word_or_number(match.group("b"))
        if a is None or b is None or b == 0:
            continue
        value = a / b
        output.append(
            Quantity(
                value=value,
                comparator="eq",
                unit_family="ratio",
                unit="ratio",
                magnitude="",
                start=match.start(),
                end=match.end(),
                sentence=text,
                timeframe=infer_timeframe(text),
                confidence=0.9,
                raw=match.group(0),
            )
        )
    return output


def _extract_n_equals(text: str) -> List[Quantity]:
    output: List[Quantity] = []
    for match in _N_EQUALS_RE.finditer(text):
        n = _to_float(match.group("n"))
        if n is None:
            continue
        output.append(
            Quantity(
                value=n,
                comparator="eq",
                unit_family="count",
                unit="respondents",
                magnitude="",
                start=match.start(),
                end=match.end(),
                sentence=text,
                timeframe=infer_timeframe(text),
                confidence=0.95,
                raw=match.group(0),
            )
        )
    return output


def _extract_multipliers(text: str) -> List[Quantity]:
    output: List[Quantity] = []
    for match in _MULT_RE.finditer(text):
        value = _to_float(match.group("num"))
        if value is None:
            continue
        output.append(
            Quantity(
                value=value,
                comparator="eq",
                unit_family="ratio",
                unit="x",
                magnitude="",
                start=match.start(),
                end=match.end(),
                sentence=text,
                timeframe=infer_timeframe(text),
                confidence=0.92,
                raw=match.group(0),
            )
        )
    return output


def _extract_main(text: str) -> List[Quantity]:
    output: List[Quantity] = []
    for match in _MAIN_RE.finditer(text):
        number = _to_float(match.group("number"))
        if number is None:
            continue
        magnitude_raw = _clean_unit(match.group("magnitude"))
        unit_raw = _clean_unit(match.group("unit"))
        currency = _s(match.group("currency"))
        raw_number = match.group("number").strip()
        if re.fullmatch(r"-\s*20\d{2}", raw_number):
            # Normalization spaces an en dash, which otherwise makes the
            # second endpoint in 2020E–2024E look like a negative number.
            continue
        if (
            number.is_integer()
            and 1900 <= number <= 2100
            and not magnitude_raw
            and not unit_raw
            and not currency
        ):
            # Bare year labels are temporal context, not independently
            # groundable quantities. This also prevents an en dash in a date
            # span (for example, 2020E–2024E) from becoming a negative value.
            continue
        family, unit, magnitude = _resolve_unit_family(
            unit=unit_raw,
            currency=currency,
            magnitude=magnitude_raw,
            sentence=text,
            span=(match.start(), match.end()),
        )
        factor = _MAG_FACTORS.get(magnitude, 1.0)
        value = number * factor
        comparator = _normalize_comparator(match.group("prefix"))
        confidence = 0.95 if family != "unknown" else 0.55
        output.append(
            Quantity(
                value=value,
                comparator=comparator,
                unit_family=family,
                unit=unit,
                magnitude=magnitude,
                start=match.start(),
                end=match.end(),
                sentence=text,
                timeframe=infer_timeframe(text),
                confidence=confidence,
                raw=match.group(0),
            )
        )
    return output


def _dedupe_quantities(values: Sequence[Quantity]) -> List[Quantity]:
    ordered = sorted(values, key=lambda q: (q.start, q.end))
    ranges = [quantity for quantity in ordered if quantity.comparator == "range"]
    deduped: List[Quantity] = []
    seen: set[Tuple[str, str, int, int, int]] = set()
    for quantity in ordered:
        if quantity.comparator != "range" and any(
            span.start <= quantity.start and quantity.end <= span.end for span in ranges
        ):
            continue
        key = (
            quantity.unit_family,
            quantity.comparator,
            int(round(quantity.value * 10_000)),
            int(round((quantity.low or -1.0) * 1_000)),
            int(round((quantity.high or -1.0) * 1_000)),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(quantity)
    return deduped


def _resolve_unit_family(
    *,
    unit: str,
    currency: str,
    magnitude: str,
    sentence: str,
    span: Tuple[int, int],
) -> Tuple[str, str, str]:
    unit_norm = _clean_unit(unit)
    magnitude_norm = _clean_unit(magnitude)
    sentence_norm = normalize_text(sentence)
    around = sentence_norm[max(0, span[0] - 32) : min(len(sentence_norm), span[1] + 32)]
    near = sentence_norm[max(0, span[0] - 10) : min(len(sentence_norm), span[1] + 10)]
    following = sentence_norm[span[1] : min(len(sentence_norm), span[1] + 24)]

    if not magnitude_norm:
        currency_scale_context = re.match(
            r"\s*(?:in\s+)?(?:annual\s+)?(?:usd|eur|gbp|jpy)\s+(?:k|m|mm|mn|b|bn|t|tn|"
            r"thousands?|millions?|billions?|trillions?)\b",
            following,
        )
        magnitude_text = following if currency_scale_context else near
        if "trillion" in magnitude_text or re.search(r"\btn\b", magnitude_text):
            magnitude_norm = "tn"
        elif "billion" in magnitude_text or re.search(r"\bbn\b", magnitude_text):
            magnitude_norm = "b"
        elif "million" in magnitude_text or re.search(r"\bmn\b|\bmm\b", magnitude_text):
            magnitude_norm = "m"
        elif "thousand" in magnitude_text or re.search(r"\bk\b", magnitude_text):
            magnitude_norm = "k"

    if currency in _CURRENCY_SYMBOL_TO_CODE:
        code = _CURRENCY_SYMBOL_TO_CODE[currency]
        return "currency", code, magnitude_norm
    if unit_norm in _CURRENCY_CODES:
        return "currency", unit_norm.upper(), magnitude_norm

    if unit_norm in {"%", "percent", "pct"}:
        return "percent", "percent", magnitude_norm
    if unit_norm in {
        "pp",
        "percentage point",
        "percentage points",
        "basis point",
        "basis points",
        "bps",
    }:
        return (
            "points",
            "pp"
            if unit_norm in {"pp", "percentage point", "percentage points"}
            else "bps",
            magnitude_norm,
        )

    if unit_norm in {"time", "times"}:
        return "ratio", "x", magnitude_norm

    if unit_norm in {"yoy", "mom", "qoq", "cagr"} or "per " in unit_norm:
        return "rate", unit_norm or "rate", magnitude_norm

    if unit_norm in {"kbps", "mbps", "gbps"}:
        return "data_rate", unit_norm, magnitude_norm

    if unit_norm in {
        "user",
        "users",
        "download",
        "downloads",
        "respondent",
        "respondents",
        "impression",
        "impressions",
        "install",
        "installs",
        "visit",
        "visits",
        "session",
        "sessions",
    }:
        return "count", unit_norm.removesuffix("s"), magnitude_norm

    if magnitude_norm:
        following_count_unit = re.search(
            r"\b(user|users|download|downloads|respondent|respondents|"
            r"impression|impressions|install|installs|visit|visits|"
            r"session|sessions)\b",
            following,
        )
        if following_count_unit:
            return (
                "count",
                following_count_unit.group(1).removesuffix("s"),
                magnitude_norm,
            )

    if unit_norm in {
        "minute",
        "minutes",
        "hour",
        "hours",
        "day",
        "days",
        "week",
        "weeks",
        "month",
        "months",
        "year",
        "years",
    }:
        return "time", unit_norm, magnitude_norm

    if unit_norm in {"point", "points"}:
        return "points", "points", magnitude_norm
    if unit_norm in {"index", "rank"}:
        return unit_norm, unit_norm, magnitude_norm

    if ("usd" in around or "eur" in around or "gbp" in around or "jpy" in around) and (
        magnitude_norm
        or any(
            token in around
            for token in ("revenue", "spend", "market size", "valuation")
        )
    ):
        if "eur" in around:
            return "currency", "EUR", magnitude_norm
        if "gbp" in around:
            return "currency", "GBP", magnitude_norm
        if "jpy" in around:
            return "currency", "JPY", magnitude_norm
        return "currency", "USD", magnitude_norm

    if magnitude_norm and (
        "usd" in around
        or "eur" in around
        or "gbp" in around
        or "jpy" in around
        or "revenue" in around
        or "spend" in around
    ):
        code = "USD" if "usd" in around or "$" in around else ""
        return "currency", code or "USD", magnitude_norm
    if magnitude_norm:
        return "count", "count", magnitude_norm

    if _has_metric_context(sentence_norm):
        if any(
            t in around for t in {"%", "percent", "pct", "share", "conversion", "rate"}
        ):
            return "percent", "percent", magnitude_norm
        return "count", "count", magnitude_norm

    return "unknown", "", magnitude_norm


def _canonical_values(quantity: Quantity) -> List[float]:
    if quantity.unit_family == "percent":
        raw = normalize_text(quantity.raw)
        values = {quantity.value}
        if "%" in raw or "percent" in raw or "pct" in raw:
            values.add(quantity.value / 100.0)
        elif quantity.value <= 1.0:
            values.add(quantity.value * 100.0)
        else:
            values.add(quantity.value / 100.0)
        return sorted(values)
    if quantity.unit_family == "ratio":
        values = {quantity.value}
        if quantity.value <= 1.0:
            values.add(quantity.value * 100.0)
        else:
            values.add(quantity.value / 100.0)
        return sorted(values)
    return [quantity.value]


def _tolerance(family: str, *, reference: float, approx: bool) -> float:
    if family == "percent":
        base = 0.1
        return base * (2.0 if approx else 1.0)
    if family == "currency":
        base = max(reference * 0.005, 1.0)
        return base * (2.0 if approx else 1.0)
    if family in {"count", "ratio", "points", "rate"}:
        base = max(reference * 0.0025, 0.5)
        return base * (2.0 if approx else 1.0)
    return max(reference * 0.001, 0.1) * (2.0 if approx else 1.0)


def _resolved_family(left: Quantity, right: Quantity) -> str:
    if left.unit_family != "unknown":
        return left.unit_family
    return right.unit_family


def _unit_families_compatible(left: Quantity, right: Quantity) -> bool:
    if left.unit_family == right.unit_family:
        return True
    compat = {left.unit_family, right.unit_family}
    if compat == {"ratio", "percent"}:
        return True
    if compat == {"points", "percent"}:
        combined = normalize_text(left.sentence + " " + right.sentence)
        return any(
            token in combined
            for token in ("change", "delta", "increase", "decrease", "up", "down")
        )
    if "unknown" in compat:
        known = left if left.unit_family != "unknown" else right
        unknown = right if left.unit_family != "unknown" else left
        return abs(known.value - unknown.value) <= _tolerance(
            known.unit_family, reference=max(abs(known.value), 1.0), approx=True
        )
    return False


def _value_supported_by_comparator(value: float, claim: Quantity, tol: float) -> bool:
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


def _ranges_overlap(left: Quantity, right: Quantity, tol: float) -> bool:
    l_low, l_high = _bounds(left)
    r_low, r_high = _bounds(right)
    return max(l_low, r_low) <= min(l_high, r_high) + tol


def _inequality_compatible(candidate: Quantity, evidence: Quantity, tol: float) -> bool:
    c_low, c_high = _bounds(candidate)
    e_low, e_high = _bounds(evidence)
    # "candidate within evidence range or vice versa" for robust equivalence.
    within = (c_low >= e_low - tol and c_high <= e_high + tol) or (
        e_low >= c_low - tol and e_high <= c_high + tol
    )
    overlap = max(c_low, e_low) <= min(c_high, e_high) + tol
    return within or overlap


def _bounds(quantity: Quantity) -> Tuple[float, float]:
    if (
        quantity.comparator == "range"
        and quantity.low is not None
        and quantity.high is not None
    ):
        return quantity.low, quantity.high
    if quantity.comparator in {"eq", "approx"}:
        return quantity.value, quantity.value
    if quantity.comparator in {"gt", "gte"}:
        return quantity.value, math.inf
    if quantity.comparator in {"lt", "lte"}:
        return -math.inf, quantity.value
    return quantity.value, quantity.value


def _has_metric_context(sentence: str) -> bool:
    tokens = set(re.findall(r"[a-z]+", sentence))
    return bool(tokens & _METRIC_HINTS)


def _looks_like_non_metric_token(quantity: Quantity, sentence: str) -> bool:
    if quantity.unit_family != "unknown":
        return False
    if quantity.value.is_integer() and 1 <= int(quantity.value) <= 50:
        if _SOFT_FOOTNOTE_RE.search(sentence):
            return True
        around = sentence[
            max(0, quantity.start - 6) : min(len(sentence), quantity.end + 6)
        ]
        if re.fullmatch(r"[\s\[\(]*\d{1,2}[\]\)\s]*", around):
            return True
    # Year labels are often metadata unless there are explicit metric cues.
    if (
        quantity.value.is_integer()
        and 1900 <= int(quantity.value) <= 2100
        and not _has_metric_context(sentence)
    ):
        return True
    if any(token in sentence for token in ("page ", "p.", "pp.")):
        return True
    return False


def _normalize_comparator(raw: str) -> Comparator:
    value = normalize_text(raw)
    if not value:
        return "eq"
    if value in {">", "more than", "over", "above", "greater than"}:
        return "gt"
    if value in {">=", "at least"}:
        return "gte"
    if value in {"<", "less than", "under", "below"}:
        return "lt"
    if value in {"<=", "at most"}:
        return "lte"
    if value in {"~", "≈", "about", "around", "approximately"}:
        return "approx"
    return "eq"


def _word_or_number(value: str) -> Optional[float]:
    number = _to_float(value)
    if number is not None:
        return number
    return _WORDS_TO_NUM.get(normalize_text(value))


def _to_float(value: str) -> Optional[float]:
    text = _s(value).strip()
    if not text:
        return None
    try:
        return float(re.sub(r"^([+-])\s+", r"\1", text).replace(",", ""))
    except ValueError:
        return None


def _round_canonical(value: float) -> float:
    return round(value, 12)


def _sign(value: float) -> int:
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def _clean_unit(value: str) -> str:
    unit = normalize_text(value).strip()
    if unit.endswith("."):
        unit = unit[:-1]
    if unit in {"billions", "billion"}:
        return "billion"
    if unit in {"millions", "million"}:
        return "million"
    if unit in {"trillions", "trillion"}:
        return "trillion"
    if unit in {"thousands", "thousand"}:
        return "thousand"
    if unit in {"percentage point", "percentage points"}:
        return "pp"
    if unit in {"basis point", "basis points"}:
        return "bps"
    if unit in {"per day", "per month", "per year"}:
        return unit
    return unit


def _s(value: object) -> str:
    if value is None:
        return ""
    return value if isinstance(value, str) else str(value)
