"""Deterministic validation for one public-facing metric display."""

from __future__ import annotations

import re


_NUMBER = r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
_MAGNITUDE = r"(?:k|m|mm|mn|b|bn|t|tn|thousand|million|billion|trillion)"
_DISPLAY_NUMBER_RE = re.compile(
    rf"[$€£¥]?\s*{_NUMBER}(?:\s*(?:%|percent|pct|pp|bps|{_MAGNITUDE}))?"
    r"(?=\s|$|[;,.)])",
    re.IGNORECASE,
)
_COHERENT_COMPARISON_RE = re.compile(
    r"\s*(?:to|through|[-–—]|vs\.?|versus|and)\s*", re.IGNORECASE
)
_CURRENCY_MAGNITUDE_UNIT_RE = re.compile(
    rf"(?P<currency>[$€£¥])\s*(?P<magnitude>{_MAGNITUDE})", re.IGNORECASE
)
_TRAILING_CURRENCY_MAGNITUDE_VALUE_RE = re.compile(
    rf"^(?P<number>{_NUMBER})\s*(?P<currency>[$€£¥])\s*"
    rf"(?P<magnitude>{_MAGNITUDE})$",
    re.IGNORECASE,
)
_CURRENCY_TOKEN_RE = re.compile(r"[$€£¥]|\b(?:usd|eur|gbp|jpy)\b", re.IGNORECASE)
_MAGNITUDE_TOKEN_RE = re.compile(rf"(?<![A-Za-z]){_MAGNITUDE}\b", re.IGNORECASE)
_PERCENT_UNIT_VALUES = {"%", "percent", "percentage", "pct"}


def normalize_public_metric_display(*, value: str, unit: str) -> tuple[str, str]:
    """Return one natural metric display or blank fields when it is composite.

    This is deliberately display-focused. It never rewrites insight text or
    evidence, and it only repairs the unambiguous ``258.6`` plus ``$ billion``
    representation into the conventional currency value plus magnitude unit.
    """

    display_value = _compact(value)
    display_unit = _compact(unit)
    if not display_value or ";" in display_value or ";" in display_unit:
        return "", ""

    numbers = list(_DISPLAY_NUMBER_RE.finditer(display_value))
    if not numbers or not _has_one_metric_or_coherent_comparison(
        display_value, numbers
    ):
        return "", ""

    currency_magnitude = _CURRENCY_MAGNITUDE_UNIT_RE.fullmatch(display_unit)
    if currency_magnitude:
        if len(numbers) != 1:
            return "", ""
        currency = currency_magnitude.group("currency")
        magnitude = currency_magnitude.group("magnitude")
        reversed_currency_value = _TRAILING_CURRENCY_MAGNITUDE_VALUE_RE.fullmatch(
            display_value
        )
        if reversed_currency_value:
            display_value = (
                f"{reversed_currency_value.group('currency')}"
                f"{reversed_currency_value.group('number')} "
                f"{reversed_currency_value.group('magnitude')}"
            )
        elif not _contains_currency(display_value):
            display_value = f"{currency}{display_value}"
        display_unit = "" if _contains_magnitude(display_value) else magnitude
    elif _CURRENCY_TOKEN_RE.search(display_unit):
        if not _contains_currency(display_value):
            return "", ""
        display_unit = _compact(_CURRENCY_TOKEN_RE.sub("", display_unit))

    if _DISPLAY_NUMBER_RE.search(display_unit):
        return "", ""
    if (
        _contains_percent(display_value)
        and display_unit.casefold() in _PERCENT_UNIT_VALUES
    ):
        display_unit = ""
    if _contains_magnitude(display_value) and display_unit.casefold() in {
        "k",
        "m",
        "mm",
        "mn",
        "b",
        "bn",
        "t",
        "tn",
        "thousand",
        "million",
        "billion",
        "trillion",
    }:
        display_unit = ""

    return display_value, display_unit


def _has_one_metric_or_coherent_comparison(
    value: str, numbers: list[re.Match[str]]
) -> bool:
    if len(numbers) == 1:
        return True
    if len(numbers) != 2:
        return False
    return bool(
        _COHERENT_COMPARISON_RE.fullmatch(value[numbers[0].end() : numbers[1].start()])
    )


def _compact(value: str) -> str:
    return " ".join(str(value or "").split())


def _contains_currency(value: str) -> bool:
    return bool(re.search(r"[$€£¥]", value))


def _contains_magnitude(value: str) -> bool:
    return bool(_MAGNITUDE_TOKEN_RE.search(value))


def _contains_percent(value: str) -> bool:
    return bool(re.search(r"%|\b(?:percent|percentage|pct)\b", value, re.IGNORECASE))
