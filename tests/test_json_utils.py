from __future__ import annotations

from src.utils.json_utils import safe_json_dumps


def test_safe_json_dumps_serializes_json_payload() -> None:
    assert safe_json_dumps({"alpha": 1}, ensure_ascii=False) == '{"alpha": 1}'


def test_safe_json_dumps_returns_requested_fallback_for_non_serializable_payload() -> None:
    assert safe_json_dumps({"bad": {1, 2}}, fallback="{}") == "{}"
