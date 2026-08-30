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


def incomplete_source_numeric_displays(text: str, source_text: str) -> list[str]:
    """Return decimal-ending displays only when linked source text continues them."""

    if not text or not source_text:
        return []
    incomplete: list[str] = []
    for match in _INCOMPLETE_DECIMAL_DISPLAY.finditer(text):
        display = match.group("display")
        if re.search(re.escape(display) + r"\d", source_text, re.IGNORECASE):
            incomplete.append(display)
    return list(dict.fromkeys(incomplete))


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
