"""Deterministic parsing of Responses API usage and File Search output."""

from __future__ import annotations

from typing import Any

from src.contracts.openai import OpenAIFileSearchResult
from src.utils.json_recovery import parse_json_from_text


def parse_json_object_from_text(text: str) -> tuple[dict | None, str]:
    parsed, strategy = parse_json_from_text(text, accepted_types=(dict,))
    return parsed if isinstance(parsed, dict) else None, strategy


def extract_responses_usage(
    resp: Any,
) -> tuple[int | None, int | None, int, int | None]:
    usage = getattr(resp, "usage", None) or {}
    input_tokens = getattr(usage, "input_tokens", None) if usage else None
    output_tokens = getattr(usage, "output_tokens", None) if usage else None
    total_tokens = getattr(usage, "total_tokens", None) if usage else None
    tool_calls = 0
    if isinstance(usage, dict):
        input_tokens = usage.get("input_tokens")
        output_tokens = usage.get("output_tokens")
        total_tokens = usage.get("total_tokens")
        tool_calls = usage.get("total_tool_calls") or usage.get("tool_calls") or 0
    return input_tokens, output_tokens, int(tool_calls or 0), total_tokens


def extract_responses_output_text(resp: Any) -> str:
    text = getattr(resp, "output_text", None)
    if isinstance(text, str) and text:
        return text
    output = (
        getattr(resp, "output", None)
        or getattr(resp, "choices", None)
        or getattr(resp, "data", None)
    )
    if isinstance(output, list) and output:
        extracted_blocks: list[str] = []
        for item in output:
            content = getattr(item, "content", None) or (
                item.get("content") if isinstance(item, dict) else None
            )
            if not isinstance(content, list):
                continue
            for block in content:
                maybe_text = getattr(block, "text", None) or (
                    block.get("text") if isinstance(block, dict) else None
                )
                if isinstance(maybe_text, str) and maybe_text:
                    extracted_blocks.append(maybe_text)
        if extracted_blocks:
            return "\n".join(extracted_blocks)
    text = getattr(resp, "text", None)
    return text if isinstance(text, str) else ""


def extract_responses_file_search_call_count(resp: Any) -> int:
    """Count completed File Search output items returned by Responses."""

    output = getattr(resp, "output", None)
    if not isinstance(output, list):
        return 0
    return sum(
        1
        for item in output
        if (
            item.get("type") if isinstance(item, dict) else getattr(item, "type", None)
        )
        == "file_search_call"
    )


def _read_response_value(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def extract_responses_file_search_results(
    resp: Any,
) -> list[OpenAIFileSearchResult]:
    output = getattr(resp, "output", None)
    if not isinstance(output, list):
        return []
    results: list[OpenAIFileSearchResult] = []
    for output_item in output:
        if _read_response_value(output_item, "type") != "file_search_call":
            continue
        raw_queries = _read_response_value(output_item, "queries", [])
        queries = (
            [str(query) for query in raw_queries if str(query).strip()]
            if isinstance(raw_queries, list)
            else []
        )
        raw_results = _read_response_value(output_item, "results", [])
        if not isinstance(raw_results, list):
            continue
        for raw_result in raw_results:
            text_parts: list[str] = []
            direct_text = _read_response_value(raw_result, "text")
            if isinstance(direct_text, str) and direct_text.strip():
                text_parts.append(direct_text.strip())
            else:
                content = _read_response_value(raw_result, "content", [])
                if isinstance(content, list):
                    for block in content:
                        if _read_response_value(block, "type") != "text":
                            continue
                        text = _read_response_value(block, "text")
                        if isinstance(text, str) and text.strip():
                            text_parts.append(text.strip())
            try:
                score = (
                    float(_read_response_value(raw_result, "score"))
                    if _read_response_value(raw_result, "score") is not None
                    else None
                )
            except (TypeError, ValueError):
                score = None
            results.append(
                OpenAIFileSearchResult(
                    schema_version="1.0",
                    queries=queries,
                    file_id=str(_read_response_value(raw_result, "file_id") or ""),
                    filename=str(
                        _read_response_value(raw_result, "filename")
                        or _read_response_value(raw_result, "file_name")
                        or ""
                    ),
                    score=score,
                    text="\n".join(text_parts),
                )
            )
    return results
