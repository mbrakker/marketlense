from __future__ import annotations

from typing import Iterable


def coerce_int(value: object, default: int = 0, *, min_value: int | None = None) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    if min_value is not None and parsed < min_value:
        return min_value
    return parsed


def coerce_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def clean_string_list(values: Iterable[object], *, dedupe_casefold: bool = False) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = str(value or "").strip()
        if not item:
            continue
        key = item.casefold() if dedupe_casefold else item
        if dedupe_casefold and key in seen:
            continue
        seen.add(key)
        cleaned.append(item)
    return cleaned
