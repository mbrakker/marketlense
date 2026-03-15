from __future__ import annotations

import json
from typing import Any


def strip_json_fence(text: str) -> str:
    stripped = (text or "").strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if len(lines) < 2 or lines[-1].strip() != "```":
        return stripped
    first_line = lines[0].strip().lower()
    if first_line not in {"```", "```json", "```jsonc", "```javascript", "```js"}:
        return stripped
    return "\n".join(lines[1:-1]).strip()


def extract_json_value(text: str) -> str:
    source = (text or "").strip()
    start = -1
    for idx, ch in enumerate(source):
        if ch in {"{", "["}:
            start = idx
            break
    if start < 0:
        return ""
    stack: list[str] = []
    in_string = False
    escaped = False
    for idx in range(start, len(source)):
        ch = source[idx]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            stack.append("}")
            continue
        if ch == "[":
            stack.append("]")
            continue
        if ch in {"}", "]"}:
            if not stack or ch != stack[-1]:
                return ""
            stack.pop()
            if not stack:
                return source[start : idx + 1]
    return ""


def parse_json_from_text(
    text: str,
    *,
    accepted_types: tuple[type[Any], ...],
) -> tuple[Any | None, str]:
    raw = (text or "").strip()
    if not raw:
        return None, "empty"
    candidates: list[tuple[str, str]] = [("direct", raw)]
    stripped = strip_json_fence(raw)
    if stripped and stripped != raw:
        candidates.append(("fence", stripped))
    for strategy, candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, accepted_types):
            return parsed, strategy
        if parsed is not None:
            return None, "json_non_object"
        extracted = extract_json_value(candidate)
        if not extracted:
            continue
        try:
            parsed_extracted = json.loads(extracted)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed_extracted, accepted_types):
            return parsed_extracted, f"{strategy}_extracted"
        return None, "json_non_object"
    return None, "invalid_json"
