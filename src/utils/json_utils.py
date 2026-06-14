from __future__ import annotations

import json
from typing import Any


def safe_json_dumps(
    data: Any,
    *,
    ensure_ascii: bool = False,
    fallback: str = "",
) -> str:
    try:
        return json.dumps(data, ensure_ascii=ensure_ascii)
    except Exception:
        return fallback


def dump_json_text(data: Any) -> str:
    return safe_json_dumps(data, ensure_ascii=False, fallback="")


def dump_json_object(data: Any) -> str:
    return safe_json_dumps(data, ensure_ascii=False, fallback="{}")
