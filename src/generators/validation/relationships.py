"""Deterministic label/value relationship checks for retained evidence."""

from __future__ import annotations

import re

_TIME_VALUE = r"\d{1,3}:\d{2}"
_PERIOD = r"(?:Q[1-4]\s*(?:FY\s*)?(?:19|20)\d{2}E?|(?:19|20)\d{2}E?\s*Q[1-4]|(?:19|20)\d{2}E?)"
_PERIOD_VALUE = re.compile(
    rf"(?P<period>{_PERIOD})\s*(?:[:=,]|\s)\s*"
    rf"(?P<value>{_TIME_VALUE})(?![A-Za-z0-9])",
    re.IGNORECASE,
)
_VALUE_PERIOD = re.compile(
    rf"(?P<value>{_TIME_VALUE})(?![A-Za-z0-9])\s*"
    rf"(?:\(?\s*(?:in|for|at|during|by|of)?\s*)?"
    rf"(?P<period>{_PERIOD})\b",
    re.IGNORECASE,
)
_PERIOD_SERIES = re.compile(
    rf"(?P<periods>{_PERIOD}(?:\s+{_PERIOD}){{1,11}})", re.IGNORECASE
)


def period_time_pairs(text: str) -> set[tuple[str, str]]:
    """Return explicit and positional period/time pairs from retained text."""
    positional_pairs = _positional_period_time_pairs(text)
    return positional_pairs or _explicit_period_time_pairs(text)


def unsupported_period_time_pairs(
    claim_text: str, source_text: str
) -> set[tuple[str, str]]:
    """Return claimed period/time pairs absent from structured source evidence."""
    source_pairs = period_time_pairs(source_text)
    if len(source_pairs) < 2:
        return set()
    return period_time_pairs(claim_text) - source_pairs


def _explicit_period_time_pairs(text: str) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for pattern in (_PERIOD_VALUE, _VALUE_PERIOD):
        for match in pattern.finditer(text):
            pairs.add((_normalize_period(match.group("period")), match.group("value")))
    return pairs


def _positional_period_time_pairs(text: str) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for series in _PERIOD_SERIES.finditer(text):
        periods = [
            _normalize_period(match.group(0))
            for match in re.finditer(_PERIOD, series.group("periods"), re.IGNORECASE)
        ]
        following = text[series.end() : series.end() + 700]
        values = [match.group(0) for match in re.finditer(_TIME_VALUE, following)]
        if len(values) < len(periods):
            continue
        pairs.update(zip(periods, values[: len(periods)], strict=True))
    return pairs


def _normalize_period(value: str) -> str:
    return " ".join(value.casefold().split())
