from __future__ import annotations

from typing import Any, Iterable, cast


DEFAULT_TRUE_TOKENS = frozenset({"1", "true", "yes", "on"})
DEFAULT_FALSE_TOKENS = frozenset({"0", "false", "no", "off"})
EXTENDED_TRUE_TOKENS = frozenset({"1", "true", "yes", "y", "on", "t"})
EXTENDED_FALSE_TOKENS = frozenset({"0", "false", "no", "n", "off", "f"})


def string_value(value: object) -> str:
    if value is None:
        return ""
    return value if isinstance(value, str) else str(value)


def stripped_string_value(value: object) -> str:
    return str(value or "").strip()


def ordered_unique_strings(values: Iterable[object]) -> list[str]:
    return clean_string_list(values, dedupe_casefold=True)


def coerce_int(value: object, default: int = 0, *, min_value: int | None = None) -> int:
    try:
        parsed = int(cast(Any, value))
    except (TypeError, ValueError):
        parsed = default
    if min_value is not None and parsed < min_value:
        return min_value
    return parsed


def coerce_float(value: object, default: float = 0.0) -> float:
    try:
        return float(cast(Any, value))
    except (TypeError, ValueError):
        return default


def coerce_bool(
    value: object,
    default: bool = False,
    *,
    true_tokens: Iterable[str] = DEFAULT_TRUE_TOKENS,
    false_tokens: Iterable[str] = DEFAULT_FALSE_TOKENS,
) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    token = str(value).strip().lower()
    if not token:
        return default
    if token in {str(item).strip().lower() for item in true_tokens}:
        return True
    if token in {str(item).strip().lower() for item in false_tokens}:
        return False
    return default


def coerce_extended_bool(value: object, default: bool = False) -> bool:
    return coerce_bool(
        value,
        default,
        true_tokens=EXTENDED_TRUE_TOKENS,
        false_tokens=EXTENDED_FALSE_TOKENS,
    )


STRICT_TRUE_TOKENS = frozenset({"1", "true", "yes"})
STRICT_FALSE_TOKENS = frozenset({"0", "false", "no"})


def normalize_optional_bool_signal(value: object) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        if value == 1:
            return True
        if value == 0:
            return False
        return None
    if isinstance(value, float):
        if value == 1.0:
            return True
        if value == 0.0:
            return False
        return None
    token = str(value).strip().lower()
    if not token:
        return None
    if token in STRICT_TRUE_TOKENS:
        return True
    if token in STRICT_FALSE_TOKENS:
        return False
    return None


def is_ambiguous_optional_bool_signal(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    return normalize_optional_bool_signal(value) is None


def clean_string_list(
    values: Iterable[object], *, dedupe_casefold: bool = False
) -> list[str]:
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
