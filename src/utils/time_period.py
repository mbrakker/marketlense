from __future__ import annotations

import re
from typing import Optional

_MONTH_TO_INDEX = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "novemeber": 11,
    "dec": 12,
    "december": 12,
}

_INDEX_TO_MONTH_SHORT = {
    1: "Jan",
    2: "Feb",
    3: "Mar",
    4: "Apr",
    5: "May",
    6: "Jun",
    7: "Jul",
    8: "Aug",
    9: "Sep",
    10: "Oct",
    11: "Nov",
    12: "Dec",
}

_YEAR_RE = re.compile(r"^(?P<y>\d{4})$")
_YEAR_RANGE_RE = re.compile(
    r"^(?P<from>\d{4})\s*(?:-|to)\s*(?P<to>\d{4})$", re.IGNORECASE
)
_QUARTER_YEAR_RE = re.compile(r"^q(?P<q>[1-4])\s*(?P<y>\d{4})$", re.IGNORECASE)
_YEAR_QUARTER_RE = re.compile(r"^(?P<y>\d{4})\s*q(?P<q>[1-4])$", re.IGNORECASE)
_QUARTER_RANGE_SAME_YEAR_RE = re.compile(
    r"^q(?P<from_q>[1-4])\s*(?:-|to)\s*q(?P<to_q>[1-4])\s*(?P<y>\d{4})$",
    re.IGNORECASE,
)
_QUARTER_RANGE_RE = re.compile(
    r"^q(?P<from_q>[1-4])\s*(?P<from_y>\d{4})\s*(?:-|to)\s*q(?P<to_q>[1-4])\s*(?P<to_y>\d{4})$",
    re.IGNORECASE,
)
_MONTH_YEAR_RE = re.compile(r"^(?P<m>[A-Za-z.]+)\s*(?P<y>\d{4})$")
_YEAR_MONTH_RE = re.compile(r"^(?P<y>\d{4})\s*(?P<m>[A-Za-z.]+)$")
_MONTH_RANGE_SAME_YEAR_RE = re.compile(
    r"^(?P<from_m>[A-Za-z.]+)\s*(?:-|to)\s*(?P<to_m>[A-Za-z.]+)\s*(?P<y>\d{4})$",
    re.IGNORECASE,
)
_MONTH_RANGE_RE = re.compile(
    r"^(?P<from_m>[A-Za-z.]+)\s*(?P<from_y>\d{4})\s*(?:-|to)\s*(?P<to_m>[A-Za-z.]+)\s*(?P<to_y>\d{4})$",
    re.IGNORECASE,
)
_MULTI_VALUE_SPLIT_RE = re.compile(r"\s*[,;|\n]\s*")
_YEAR_TOKEN_RE = re.compile(r"\b(?:19|20)\d{2}\b")
_YEAR_LIST_RE = re.compile(
    r"^(?P<years>(?:19|20)\d{2}(?:\s*[,;/|]\s*(?:19|20)\d{2})+)$"
)
_YEAR_RANGE_TOKEN_RE = re.compile(
    r"\b(?P<from>(?:19|20)\d{2})\s*(?:-|to)\s*(?P<to>(?:19|20)\d{2})\b",
    re.IGNORECASE,
)
_DATE_RANGE_RE = re.compile(
    r"(?P<from_m>[A-Za-z.]+)\s+(?P<from_d>\d{1,2}),?\s+"
    r"(?P<from_y>(?:19|20)\d{2})\s*(?:-|to|through|until)\s*"
    r"(?P<to_m>[A-Za-z.]+)\s+(?P<to_d>\d{1,2}),?\s+"
    r"(?P<to_y>(?:19|20)\d{2})",
    re.IGNORECASE,
)
_DATE_RE = re.compile(
    r"(?P<m>[A-Za-z.]+)\s+(?P<d>\d{1,2}),?\s+(?P<y>(?:19|20)\d{2})",
    re.IGNORECASE,
)
_HALF_YEAR_RE = re.compile(
    r"^(?:(?P<h>H[12]|[12]H|first half|second half)\s*(?P<y>(?:19|20)\d{2})|"
    r"(?P<year>(?:19|20)\d{2})\s*(?P<year_h>H[12]|[12]H))$",
    re.IGNORECASE,
)
_FISCAL_YEAR_RE = re.compile(
    r"^(?:FY\s*(?P<fy>(?:19|20)\d{2})|fiscal\s+year\s*(?P<fiscal>(?:19|20)\d{2})|"
    r"(?P<year>(?:19|20)\d{2})\s+fiscal\s+year)$",
    re.IGNORECASE,
)


def normalize_time_period(value: Optional[str]) -> Optional[str]:
    """Project untrusted period metadata into a concise public temporal label.

    This is intentionally a public projection: callers retaining source metadata
    must store their raw value and only use this result at a display boundary.
    """
    if value is None:
        return None

    normalized = _normalize_input(value)
    if not normalized:
        return None

    candidates = (normalized, _strip_annotations(normalized))
    for candidate in candidates:
        parsed = _parse_public_period(candidate)
        if parsed:
            return parsed
    for candidate in candidates:
        embedded = _find_embedded_public_period(candidate)
        if embedded:
            return embedded

    # Surrounding prose is not public metadata. A lone year is nevertheless
    # safe to recover when it is the only temporal value in the raw metadata.
    years = _dedupe_preserve_order(_YEAR_TOKEN_RE.findall(normalized))
    return years[0] if len(years) == 1 else None


def _find_embedded_public_period(value: str) -> Optional[str]:
    candidates: list[str] = []
    for match in _DATE_RANGE_RE.finditer(value):
        if period := _format_date_range(match):
            candidates.append(period)
    for match in _YEAR_RANGE_TOKEN_RE.finditer(value):
        candidates.append(f"{match.group('from')}–{match.group('to')}")
    unique = _dedupe_preserve_order(candidates)
    return unique[0] if len(unique) == 1 else None


def _parse_public_period(value: str) -> Optional[str]:
    date_range = _DATE_RANGE_RE.fullmatch(value)
    if date_range:
        return _format_date_range(date_range)

    date = _DATE_RE.fullmatch(value)
    if date:
        return _format_date(date.group("m"), date.group("d"), date.group("y"))

    year_range = _YEAR_RANGE_RE.fullmatch(value)
    if year_range:
        return f"{year_range.group('from')}–{year_range.group('to')}"

    year_list = _YEAR_LIST_RE.fullmatch(value)
    if year_list:
        return ", ".join(_YEAR_TOKEN_RE.findall(year_list.group("years")))

    quarter = _parse_public_quarter(value)
    if quarter:
        return quarter

    half_year = _HALF_YEAR_RE.fullmatch(value)
    if half_year:
        half = half_year.group("h") or half_year.group("year_h") or ""
        year = half_year.group("y") or half_year.group("year") or ""
        return f"H{half[-1]} {year}"

    fiscal_year = _FISCAL_YEAR_RE.fullmatch(value)
    if fiscal_year:
        year = (
            fiscal_year.group("fy")
            or fiscal_year.group("fiscal")
            or fiscal_year.group("year")
        )
        return f"FY{year}"

    month = _parse_public_month(value)
    if month:
        return month

    if _YEAR_RE.fullmatch(value):
        return value
    return None


def _parse_public_quarter(value: str) -> Optional[str]:
    compact = re.sub(r"\s+", " ", value).strip()
    match = _QUARTER_YEAR_RE.fullmatch(compact)
    if match:
        return f"Q{match.group('q')} {match.group('y')}"
    match = _YEAR_QUARTER_RE.fullmatch(compact)
    if match:
        return f"Q{match.group('q')} {match.group('y')}"
    match = _QUARTER_RANGE_SAME_YEAR_RE.fullmatch(compact)
    if match:
        return f"Q{match.group('from_q')}–Q{match.group('to_q')} {match.group('y')}"
    match = _QUARTER_RANGE_RE.fullmatch(compact)
    if match:
        return (
            f"Q{match.group('from_q')} {match.group('from_y')}–"
            f"Q{match.group('to_q')} {match.group('to_y')}"
        )
    return None


def _parse_public_month(value: str) -> Optional[str]:
    match = _MONTH_YEAR_RE.fullmatch(value)
    if match:
        month = _month_to_full(match.group("m"))
        return f"{month} {match.group('y')}" if month else None
    match = _YEAR_MONTH_RE.fullmatch(value)
    if match:
        month = _month_to_full(match.group("m"))
        return f"{month} {match.group('y')}" if month else None
    match = _MONTH_RANGE_SAME_YEAR_RE.fullmatch(value)
    if match:
        first = _month_to_full(match.group("from_m"))
        last = _month_to_full(match.group("to_m"))
        return f"{first}–{last} {match.group('y')}" if first and last else None
    match = _MONTH_RANGE_RE.fullmatch(value)
    if match:
        first = _month_to_full(match.group("from_m"))
        last = _month_to_full(match.group("to_m"))
        if first and last:
            return f"{first} {match.group('from_y')}–{last} {match.group('to_y')}"
    return None


def _format_date_range(match: re.Match[str]) -> Optional[str]:
    start = _format_date(
        match.group("from_m"), match.group("from_d"), match.group("from_y")
    )
    end = _format_date(match.group("to_m"), match.group("to_d"), match.group("to_y"))
    return f"{start} to {end}" if start and end else None


def _format_date(month_token: str, day: str, year: str) -> Optional[str]:
    month = _month_to_full(month_token)
    if month is None:
        return None
    day_number = int(day)
    if not 1 <= day_number <= 31:
        return None
    return f"{month} {day_number}, {year}"


def _parse_period_expression(value: str) -> list[str]:
    year_range = _YEAR_RANGE_RE.match(value)
    if year_range:
        start = int(year_range.group("from"))
        end = int(year_range.group("to"))
        return _expand_years(start, end)

    quarter_same_year = _QUARTER_RANGE_SAME_YEAR_RE.match(value)
    if quarter_same_year:
        from_q = int(quarter_same_year.group("from_q"))
        to_q = int(quarter_same_year.group("to_q"))
        year = int(quarter_same_year.group("y"))
        return _expand_quarters(from_q, year, to_q, year)

    quarter_range = _QUARTER_RANGE_RE.match(value)
    if quarter_range:
        from_q = int(quarter_range.group("from_q"))
        from_y = int(quarter_range.group("from_y"))
        to_q = int(quarter_range.group("to_q"))
        to_y = int(quarter_range.group("to_y"))
        return _expand_quarters(from_q, from_y, to_q, to_y)

    month_same_year = _MONTH_RANGE_SAME_YEAR_RE.match(value)
    if month_same_year:
        from_month = _month_to_index(month_same_year.group("from_m"))
        to_month = _month_to_index(month_same_year.group("to_m"))
        year = int(month_same_year.group("y"))
        if from_month is not None and to_month is not None:
            return _expand_months(from_month, year, to_month, year)

    month_range = _MONTH_RANGE_RE.match(value)
    if month_range:
        from_month = _month_to_index(month_range.group("from_m"))
        to_month = _month_to_index(month_range.group("to_m"))
        from_year = int(month_range.group("from_y"))
        to_year = int(month_range.group("to_y"))
        if from_month is not None and to_month is not None:
            return _expand_months(from_month, from_year, to_month, to_year)

    single = _parse_single_period(value)
    if single:
        return [single]

    return []


def _parse_single_period(value: str) -> Optional[str]:
    year_match = _YEAR_RE.match(value)
    if year_match:
        return year_match.group("y")

    quarter_year = _QUARTER_YEAR_RE.match(value)
    if quarter_year:
        return f"Q{quarter_year.group('q')} {quarter_year.group('y')}"

    year_quarter = _YEAR_QUARTER_RE.match(value)
    if year_quarter:
        return f"Q{year_quarter.group('q')} {year_quarter.group('y')}"

    month_year = _MONTH_YEAR_RE.match(value)
    if month_year:
        month = _month_to_short(month_year.group("m"))
        if month:
            return f"{month} {month_year.group('y')}"

    year_month = _YEAR_MONTH_RE.match(value)
    if year_month:
        month = _month_to_short(year_month.group("m"))
        if month:
            return f"{month} {year_month.group('y')}"

    return None


def _expand_years(start: int, end: int) -> list[str]:
    if start > end:
        start, end = end, start
    return [str(year) for year in range(start, end + 1)]


def _expand_quarters(
    start_q: int, start_year: int, end_q: int, end_year: int
) -> list[str]:
    start_idx = start_year * 4 + (start_q - 1)
    end_idx = end_year * 4 + (end_q - 1)
    if start_idx > end_idx:
        start_idx, end_idx = end_idx, start_idx
    values: list[str] = []
    for idx in range(start_idx, end_idx + 1):
        year = idx // 4
        quarter = (idx % 4) + 1
        values.append(f"Q{quarter} {year}")
    return values


def _expand_months(
    start_month: int, start_year: int, end_month: int, end_year: int
) -> list[str]:
    start_idx = start_year * 12 + (start_month - 1)
    end_idx = end_year * 12 + (end_month - 1)
    if start_idx > end_idx:
        start_idx, end_idx = end_idx, start_idx
    values: list[str] = []
    for idx in range(start_idx, end_idx + 1):
        year = idx // 12
        month_index = (idx % 12) + 1
        month_short = _INDEX_TO_MONTH_SHORT[month_index]
        values.append(f"{month_short} {year}")
    return values


def _normalize_input(value: str) -> str:
    text = str(value).strip()
    if not text:
        return ""
    text = text.replace("\u2013", "-").replace("\u2014", "-").replace("\u2212", "-")
    text = re.sub(r"\s+", " ", text)
    return text


def _strip_annotations(value: str) -> str:
    text = str(value)
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"\[[^\]]*\]", " ", text)
    return _normalize_input(text)


def _split_parts(value: str) -> list[str]:
    return [part for part in _MULTI_VALUE_SPLIT_RE.split(value) if part]


def _month_to_index(token: str) -> Optional[int]:
    key = str(token).strip().lower().rstrip(".")
    if not key:
        return None
    return _MONTH_TO_INDEX.get(key)


def _month_to_short(token: str) -> Optional[str]:
    index = _month_to_index(token)
    if index is None:
        return None
    return _INDEX_TO_MONTH_SHORT[index]


def _month_to_full(token: str) -> Optional[str]:
    index = _month_to_index(token)
    if index is None:
        return None
    return [
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ][index - 1]


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(value)
    return deduped
