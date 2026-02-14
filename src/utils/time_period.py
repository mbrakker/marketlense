from __future__ import annotations

import re
from typing import Optional


_MONTHS = {
    "jan": "January",
    "january": "January",
    "feb": "February",
    "february": "February",
    "mar": "March",
    "march": "March",
    "apr": "April",
    "april": "April",
    "may": "May",
    "jun": "June",
    "june": "June",
    "jul": "July",
    "july": "July",
    "aug": "August",
    "august": "August",
    "sep": "September",
    "sept": "September",
    "september": "September",
    "oct": "October",
    "october": "October",
    "nov": "November",
    "november": "November",
    "novemeber": "November",
    "dec": "December",
    "december": "December",
}

_YEAR_RE = re.compile(r"^\d{4}$")
_YEAR_RANGE_RE = re.compile(r"^(?P<from>\d{4})\s*(?:-|to)\s*(?P<to>\d{4})$", re.IGNORECASE)
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


def normalize_time_period(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = _normalize_input(value)
    if not normalized:
        return None

    if _YEAR_RE.match(normalized):
        return normalized

    year_range = _YEAR_RANGE_RE.match(normalized)
    if year_range:
        return f"{year_range.group('from')}-{year_range.group('to')}"

    quarter_same_year = _QUARTER_RANGE_SAME_YEAR_RE.match(normalized)
    if quarter_same_year:
        return f"Q{quarter_same_year.group('from_q')}-Q{quarter_same_year.group('to_q')} {quarter_same_year.group('y')}"

    quarter_range = _QUARTER_RANGE_RE.match(normalized)
    if quarter_range:
        from_q = quarter_range.group("from_q")
        from_y = quarter_range.group("from_y")
        to_q = quarter_range.group("to_q")
        to_y = quarter_range.group("to_y")
        if from_y == to_y:
            return f"Q{from_q}-Q{to_q} {from_y}"
        return f"Q{from_q} {from_y}-Q{to_q} {to_y}"

    quarter_year = _QUARTER_YEAR_RE.match(normalized)
    if quarter_year:
        return f"Q{quarter_year.group('q')} {quarter_year.group('y')}"

    year_quarter = _YEAR_QUARTER_RE.match(normalized)
    if year_quarter:
        return f"Q{year_quarter.group('q')} {year_quarter.group('y')}"

    month_same_year = _MONTH_RANGE_SAME_YEAR_RE.match(normalized)
    if month_same_year:
        from_month = _normalize_month(month_same_year.group("from_m"))
        to_month = _normalize_month(month_same_year.group("to_m"))
        if from_month and to_month:
            return f"{from_month}-{to_month} {month_same_year.group('y')}"

    month_range = _MONTH_RANGE_RE.match(normalized)
    if month_range:
        from_month = _normalize_month(month_range.group("from_m"))
        to_month = _normalize_month(month_range.group("to_m"))
        from_year = month_range.group("from_y")
        to_year = month_range.group("to_y")
        if from_month and to_month:
            if from_year == to_year:
                return f"{from_month}-{to_month} {from_year}"
            return f"{from_month} {from_year}-{to_month} {to_year}"

    month_year = _MONTH_YEAR_RE.match(normalized)
    if month_year:
        month = _normalize_month(month_year.group("m"))
        if month:
            return f"{month} {month_year.group('y')}"

    year_month = _YEAR_MONTH_RE.match(normalized)
    if year_month:
        month = _normalize_month(year_month.group("m"))
        if month:
            return f"{month} {year_month.group('y')}"

    return normalized


def _normalize_input(value: str) -> str:
    text = str(value).strip()
    if not text:
        return ""
    text = text.replace("\u2013", "-").replace("\u2014", "-").replace("\u2212", "-")
    text = re.sub(r"\s+", " ", text)
    return text


def _normalize_month(token: str) -> Optional[str]:
    key = str(token).strip().lower().rstrip(".")
    if not key:
        return None
    return _MONTHS.get(key)
