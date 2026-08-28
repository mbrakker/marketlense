from __future__ import annotations

import json
import re
import unicodedata
from typing import Any


def normalize_json_text(text: str) -> str:
    """Normalize provider JSON transport quirks without changing JSON semantics."""

    normalized = unicodedata.normalize("NFC", str(text or ""))
    return normalized.lstrip("\ufeff").replace("\u00a0", " ").strip()


def strip_json_fence(text: str) -> str:
    stripped = normalize_json_text(text)
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
    source = normalize_json_text(text)
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
    raw = normalize_json_text(text)
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


def repair_json_once(text: str) -> tuple[str, str]:
    """Apply one deliberately small, deterministic JSON repair attempt.

    This runs only after regular parsing/extraction.  It corrects the two
    transport defects observed in retained model responses (curly delimiters
    and trailing commas) and never attempts to infer missing values or close
    incomplete structures.
    """

    candidate = strip_json_fence(text)
    extracted = extract_json_value(candidate)
    if extracted:
        candidate = extracted
    repaired = _escape_literal_newlines_in_strings(candidate)
    repaired = (
        repaired.replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2018", "'")
        .replace("\u2019", "'")
    )
    repaired = re.sub(r",\s*([}\]])", r"\1", repaired)
    return repaired, "deterministic_json_repair"


def _escape_literal_newlines_in_strings(text: str) -> str:
    """Escape literal newlines only while inside an already-quoted JSON string."""

    result: list[str] = []
    in_string = False
    escaped = False
    for char in text:
        if in_string and not escaped and char == "\n":
            result.append("\\n")
            continue
        result.append(char)
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
    return "".join(result)
