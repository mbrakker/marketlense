"""Preserve source numeric displays while deriving only validated metadata."""

from __future__ import annotations

import re
from typing import TypedDict

from src.utils.quantity import extract_quantities


class NumericDisplayMetadata(TypedDict):
    value: float
    unit_family: str
    unit: str
    magnitude: str


_INCOMPLETE_DECIMAL_DISPLAY = re.compile(
    r"(?<![A-Za-z0-9])(?P<display>[$€£¥]?\s*\d+(?:,\d{3})*\.)(?!\d)"
)
_INCOMPLETE_CURRENCY_INTEGER_DISPLAY = re.compile(
    r"(?<![A-Za-z0-9])(?P<display>[$€£¥]\s*\d{1,3}(?:,\d{3})*)(?![\d.,])"
)
_DISPLAY_MAGNITUDE_RE = r"(?:k|m|mm|mn|b|bn|t|tn|thousand|million|billion|trillion)"
_DISPLAY_UNIT_RE = (
    r"(?:%|percent|pct|pp|percentage points?|basis points?|bps|x|times|"
    r"usd|eur|gbp|jpy|users?|downloads?|respondents?|impressions?|installs?|"
    r"visits?|sessions?|minutes?|hours?|days?|weeks?|months?|years?|points?)"
)
_DISPLAY_COMPONENT_RE = (
    r"(?:[+-](?=[\d$€£¥])\s*)?(?:[$€£¥]\s*)?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
    rf"(?:\s*{_DISPLAY_MAGNITUDE_RE})?(?:\s*{_DISPLAY_UNIT_RE})?"
)
_SCALAR_DISPLAY_RE = re.compile(
    rf"(?<![A-Za-z0-9.])(?P<display>{_DISPLAY_COMPONENT_RE})(?![A-Za-z0-9])",
    re.IGNORECASE,
)
_RANGE_DISPLAY_RE = re.compile(
    rf"(?<![A-Za-z0-9.])(?P<display>{_DISPLAY_COMPONENT_RE}\s*(?:to|–|-)\s*"
    rf"{_DISPLAY_COMPONENT_RE})(?![A-Za-z0-9])",
    re.IGNORECASE,
)
_RATIO_DISPLAY_RE = re.compile(
    r"(?<![A-Za-z0-9.])(?P<display>\d+(?:\.\d+)?\s*:\s*\d+(?:\.\d+)?)(?![A-Za-z0-9.])"
)
_TEMPORAL_DISPLAY_RE = re.compile(
    r"\b(?:"
    r"(?:Q[1-4]|H[12])(?:\s+(?:FY\s*)?20\d{2}E?)?|"
    r"(?:January|February|March|April|May|June|July|August|September|"
    r"October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|"
    r"Oct|Nov|Dec)\.?(?:\s+20\d{2}E?)?|"
    r"(?:FY\s*20\d{2}E?|fiscal\s+year\s+20\d{2}E?)|"
    r"20\d{2}E"
    r")\b",
    re.IGNORECASE,
)
_PLAIN_YEAR_DISPLAY_RE = re.compile(r"\b(?P<display>20\d{2})\b")
_SCALAR_PARSE_RE = re.compile(
    rf"^(?P<sign>[+-])?\s*(?P<currency>[$€£¥])?\s*"
    r"(?P<number>(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)"
    rf"\s*(?P<magnitude>{_DISPLAY_MAGNITUDE_RE})?\s*"
    rf"(?P<unit>{_DISPLAY_UNIT_RE})?$",
    re.IGNORECASE,
)
_MONTH_YEAR_DISPLAY_RE = re.compile(
    r"^(?P<month>[A-Za-z]+)\.?\s*(?P<year>20\d{2}E?)?$",
    re.IGNORECASE,
)
_QUARTER_HALF_DISPLAY_RE = re.compile(
    r"^(?P<period>Q[1-4]|H[12])(?:\s+(?:FY\s*)?(?P<year>20\d{2}E?))?$",
    re.IGNORECASE,
)
_FISCAL_YEAR_DISPLAY_RE = re.compile(
    r"^(?:FY\s*|fiscal\s+year\s+)(?P<year>20\d{2}E?)$",
    re.IGNORECASE,
)
_MAGNITUDE_ALIASES = {
    "k": "k",
    "thousand": "k",
    "m": "m",
    "mm": "m",
    "mn": "m",
    "million": "m",
    "b": "b",
    "bn": "b",
    "billion": "b",
    "t": "t",
    "tn": "t",
    "trillion": "t",
}
_UNIT_ALIASES = {
    "percent": "%",
    "pct": "%",
    "percentage point": "pp",
    "percentage points": "pp",
    "basis point": "bps",
    "basis points": "bps",
    "times": "x",
}
_MONTH_ALIASES = {
    "jan": "january",
    "feb": "february",
    "mar": "march",
    "apr": "april",
    "jun": "june",
    "jul": "july",
    "aug": "august",
    "sep": "september",
    "sept": "september",
    "oct": "october",
    "nov": "november",
    "dec": "december",
}


def incomplete_source_numeric_displays(text: str, source_text: str) -> list[str]:
    """Return displays whose linked retained source proves a missing decimal digit."""

    if not text or not source_text:
        return []
    incomplete: list[str] = []
    for match in _INCOMPLETE_DECIMAL_DISPLAY.finditer(text):
        display = match.group("display")
        if re.search(re.escape(display) + r"\d", source_text, re.IGNORECASE):
            incomplete.append(display)
    for match in _INCOMPLETE_CURRENCY_INTEGER_DISPLAY.finditer(text):
        display = match.group("display")
        if re.search(re.escape(display) + r"\.\d", source_text, re.IGNORECASE):
            incomplete.append(display)
    return list(dict.fromkeys(incomplete))


def preserve_unique_source_displays(text: str, source_text: str) -> str:
    """Restore a public factual display only when linked evidence is unique.

    The source display remains authoritative for precision, signs, units,
    comparison ranges, and temporal or forecast notation.  Ordinary prose is
    left untouched; a replacement occurs only when a public display has the
    same normalized factual identity as exactly one retained source display.
    """

    replacements = _source_display_replacements(text, source_text)
    repaired = text
    for start, end, source_display in reversed(replacements):
        repaired = repaired[:start] + source_display + repaired[end:]
    return repaired


def _source_display_replacements(
    text: str, source_text: str
) -> list[tuple[int, int, str]]:
    if not text or not source_text:
        return []
    source_by_key = _source_displays_by_key(source_text)

    replacements: list[tuple[int, int, str]] = []
    for start, end, display, keys in _fact_display_matches(text):
        for key in keys:
            candidates = source_by_key.get(key, set())
            if not candidates:
                continue
            if len(candidates) != 1:
                break
            source_display = next(iter(candidates))
            if source_display != display:
                replacements.append((start, end, source_display))
            break
    return replacements


def _source_displays_by_key(source_text: str) -> dict[str, set[str]]:
    source_by_key: dict[str, set[str]] = {}
    for _, _, display, keys in _fact_display_matches(source_text):
        for key in keys:
            source_by_key.setdefault(key, set()).add(display)
    return source_by_key


def _fact_display_matches(text: str) -> list[tuple[int, int, str, tuple[str, ...]]]:
    matches: list[tuple[int, int, str, tuple[str, ...]]] = []
    occupied: list[tuple[int, int]] = []
    for pattern, key_builder in (
        (_RANGE_DISPLAY_RE, _range_display_keys),
        (_RATIO_DISPLAY_RE, _ratio_display_keys),
        (_TEMPORAL_DISPLAY_RE, _temporal_display_keys),
        (_PLAIN_YEAR_DISPLAY_RE, _plain_forecast_year_keys),
        (_SCALAR_DISPLAY_RE, _scalar_display_keys),
    ):
        for match in pattern.finditer(text):
            start, end = (
                match.span("display")
                if "display" in match.re.groupindex
                else match.span()
            )
            if any(
                start < prior_end and end > prior_start
                for prior_start, prior_end in occupied
            ):
                continue
            display = (
                match.group("display")
                if "display" in match.re.groupindex
                else match.group()
            )
            keys = key_builder(display)
            if not keys:
                continue
            matches.append((start, end, display, keys))
            occupied.append((start, end))
    return sorted(matches, key=lambda item: item[0])


def _range_display_keys(display: str) -> tuple[str, ...]:
    components = [
        _scalar_display_identity(match.group("display"))
        for match in _SCALAR_DISPLAY_RE.finditer(display)
    ]
    if len(components) != 2 or not all(components):
        return ()
    return (f"range:{components[0]}:{components[1]}",)


def _ratio_display_keys(display: str) -> tuple[str, ...]:
    values = [
        _normalized_number_display(value)
        for value in re.findall(r"\d+(?:\.\d+)?", display)
    ]
    return (f"ratio:{':'.join(values)}",) if len(values) == 2 else ()


def _scalar_display_keys(display: str) -> tuple[str, ...]:
    exact = _scalar_display_identity(display)
    if not exact:
        return ()
    parsed = _SCALAR_PARSE_RE.fullmatch(display.strip())
    if not parsed:
        return ()
    raw_number = parsed.group("number")
    _, number, magnitude, unit = exact.split(":", 3)
    truncated = (
        f"scalar-truncated:{raw_number.replace(',', '').split('.')[0]}:"
        f"{magnitude}:{unit}"
    )
    return (truncated, exact) if "." not in raw_number else (exact, truncated)


def _scalar_display_identity(display: str) -> str:
    parsed = _SCALAR_PARSE_RE.fullmatch(display.strip())
    if not parsed:
        return ""
    sign = parsed.group("sign") or ""
    currency = parsed.group("currency") or ""
    magnitude = _MAGNITUDE_ALIASES.get(
        (parsed.group("magnitude") or "").casefold(), ""
    )
    unit = (parsed.group("unit") or "").casefold()
    unit = _UNIT_ALIASES.get(unit, unit)
    raw_number = parsed.group("number")
    if not any((sign, currency, magnitude, unit)) and "." not in raw_number:
        return ""
    number = _normalized_number_display(raw_number)
    return f"scalar:{number}:{magnitude}:{unit}"


def _temporal_display_keys(display: str) -> tuple[str, ...]:
    if display.strip() == "may":
        return ()
    normalized = re.sub(r"\s+", " ", display).strip().casefold()
    month = _MONTH_YEAR_DISPLAY_RE.fullmatch(normalized)
    if month:
        month_name = _MONTH_ALIASES.get(
            month.group("month").rstrip("."), month.group("month").rstrip(".")
        )
        year = month.group("year") or ""
        return (
            (f"temporal:month:{month_name}:{year}", f"temporal:month:{month_name}")
            if year
            else (f"temporal:month:{month_name}",)
        )
    quarter_half = _QUARTER_HALF_DISPLAY_RE.fullmatch(normalized)
    if quarter_half:
        period = quarter_half.group("period").casefold()
        year = (quarter_half.group("year") or "").removesuffix("e")
        return (
            (f"temporal:period:{period}:{year}", f"temporal:period:{period}")
            if year
            else (f"temporal:period:{period}",)
        )
    fiscal_year = _FISCAL_YEAR_DISPLAY_RE.fullmatch(normalized)
    if fiscal_year:
        year = fiscal_year.group("year").removesuffix("e")
        return (f"temporal:fiscal:{year}",)
    if re.fullmatch(r"20\d{2}e", normalized):
        return (f"temporal:forecast:{normalized[:4]}",)
    return ()


def _plain_forecast_year_keys(display: str) -> tuple[str, ...]:
    return (f"temporal:forecast:{display}",)


def _normalized_number_display(value: str) -> str:
    whole, dot, fractional = value.replace(",", "").partition(".")
    whole = whole.lstrip("0") or "0"
    fractional = fractional.rstrip("0")
    return whole if not dot or not fractional else f"{whole}.{fractional}"


def numeric_metadata_for_complete_display(
    display: str,
) -> NumericDisplayMetadata | None:
    """Derive metadata only from one complete, exact source display."""

    source_display = str(display or "").strip()
    if not source_display or _INCOMPLETE_DECIMAL_DISPLAY.search(source_display):
        return None
    for quantity in extract_quantities(source_display):
        if quantity.raw.casefold() != source_display.casefold():
            continue
        if quantity.unit_family == "unknown":
            continue
        return {
            "value": quantity.value,
            "unit_family": quantity.unit_family,
            "unit": quantity.unit,
            "magnitude": quantity.magnitude,
        }
    return None
