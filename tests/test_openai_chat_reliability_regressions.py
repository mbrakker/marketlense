from __future__ import annotations

import json
import time
from dataclasses import replace
from types import SimpleNamespace

import pytest

from src.contracts.openai import OpenAIJSONPromptRequest
from src.contracts.run_context import RunContext
from src.services import llm_service as svc
from src.services._llm_service import openai_shared
from src.utils.errors import AppError


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


def _chat_request(tmp_path) -> OpenAIJSONPromptRequest:
    return OpenAIJSONPromptRequest(
        schema_version="1.0",
        system_prompt="system",
        user_prompt="user",
        model="gpt-4.1-mini",
        temperature=0.1,
        api_key="key",
        seed=7,
        timeout_seconds=5.0,
        cost_ledger_path=str(tmp_path / "ledger.jsonl"),
        cost_daily_path=str(tmp_path / "daily.json"),
        usage_db_path=str(tmp_path / "usage.sqlite"),
        model_pricing={},
    )


def test_invalid_semantic_cache_payload_is_not_reused(tmp_path) -> None:
    request = replace(
        _chat_request(tmp_path),
        response_cache_enabled=True,
        response_cache_dir=str(tmp_path / "cache"),
        response_cache_ttl_seconds=60.0,
    )
    spec = openai_shared._semantic_response_cache_spec(
        request,
        operation="openai_chat_json",
        params={"model": request.model},
    )
    assert spec is not None
    spec.path.parent.mkdir(parents=True)
    spec.path.write_text(
        json.dumps(
            {
                "_cache": {"key": spec.key, "cached_at_epoch": time.time()},
                "response": {"parsed_json": None, "provider_status": "completed"},
            }
        ),
        encoding="utf-8",
    )
    assert openai_shared._read_semantic_response_cache(spec, _ctx()) is None


@pytest.mark.parametrize(
    "response_payload",
    [
        {},
        {"parsed_json": None},
        {"parsed_json": {"ok": True}, "finish_reason": "length"},
        {"parsed_json": {"ok": True}, "refusal": "blocked"},
        {"parsed_json": {"ok": True}, "incomplete_reason": "provider_timeout"},
    ],
)
def test_semantic_cache_rejects_missing_or_unusable_structured_payload(
    response_payload,
) -> None:
    assert (
        openai_shared._semantic_response_payload_is_cacheable(response_payload) is False
    )


def test_semantic_cache_accepts_complete_legacy_structured_payload() -> None:
    assert (
        openai_shared._semantic_response_payload_is_cacheable(
            {"parsed_json": {"ok": True}, "provider_status": "completed"}
        )
        is True
    )


def test_semantic_cache_does_not_write_unparsed_response(tmp_path) -> None:
    request = replace(
        _chat_request(tmp_path),
        response_cache_enabled=True,
        response_cache_dir=str(tmp_path / "cache"),
        response_cache_ttl_seconds=60.0,
    )
    spec = openai_shared._semantic_response_cache_spec(
        request,
        operation="openai_chat_json",
        params={"model": request.model},
    )
    assert spec is not None

    openai_shared._write_semantic_response_cache(
        spec,
        _ctx(),
        response_payload={"provider_status": "completed"},
    )

    assert not spec.path.exists()


def test_openai_chat_json_preserves_completion_state_and_does_not_cache_incomplete(
    external_boundary_mocks_only, tmp_path
) -> None:
    calls: list[dict] = []

    class _Chat:
        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                id=f"chat_{len(calls)}",
                choices=[
                    SimpleNamespace(
                        finish_reason="length",
                        message=SimpleNamespace(
                            content='{"ok":true}',
                            refusal=None,
                        ),
                    )
                ],
                usage=SimpleNamespace(
                    prompt_tokens=12, completion_tokens=5, total_tokens=17
                ),
            )

    class _Client:
        def __init__(self, **_kwargs):
            self.chat = SimpleNamespace(completions=_Chat())

    external_boundary_mocks_only.setattr(svc.openai_legacy, "OpenAI", _Client)
    request = replace(
        _chat_request(tmp_path),
        response_cache_enabled=True,
        response_cache_dir=str(tmp_path / "cache"),
    )

    first = svc.openai_chat_json(request, _ctx())
    second = svc.openai_chat_json(request, _ctx())

    assert first.parsed_json is None
    assert first.finish_reason == "length"
    assert first.provider_status == "incomplete"
    assert first.incomplete_reason == "length"
    assert second.request_id == "chat_2"
    assert len(calls) == 2


def test_legacy_chat_adapter_preserves_completion_state(
    external_boundary_mocks_only, tmp_path
) -> None:
    class _LegacyChatCompletion:
        @staticmethod
        def create(**_kwargs):
            return {
                "id": "legacy_truncated",
                "choices": [
                    {
                        "finish_reason": "length",
                        "message": {"content": '{"ok":true}'},
                    }
                ],
                "usage": {
                    "prompt_tokens": 8,
                    "completion_tokens": 4,
                    "total_tokens": 12,
                },
            }

    external_boundary_mocks_only.setattr(svc.openai_legacy, "OpenAI", None)
    external_boundary_mocks_only.setattr(
        svc.openai_legacy, "ChatCompletion", _LegacyChatCompletion
    )

    result = svc.openai_chat_json(_chat_request(tmp_path), _ctx())

    assert result.parsed_json is None
    assert result.finish_reason == "length"
    assert result.provider_status == "incomplete"
    assert result.incomplete_reason == "length"


def test_strict_schema_does_not_fall_back_by_dropping_response_format(
    external_boundary_mocks_only, tmp_path
) -> None:
    class _Chat:
        def create(self, **_kwargs):
            raise TypeError("unexpected keyword argument 'response_format'")

    class _Client:
        def __init__(self, **_kwargs):
            self.chat = SimpleNamespace(completions=_Chat())

    class _LegacyChatCompletion:
        @staticmethod
        def create(**_kwargs):
            raise AssertionError(
                "strict schema fallback must not remove response_format"
            )

    external_boundary_mocks_only.setattr(svc.openai_legacy, "OpenAI", _Client)
    external_boundary_mocks_only.setattr(
        svc.openai_legacy, "ChatCompletion", _LegacyChatCompletion
    )
    request = replace(
        _chat_request(tmp_path),
        structured_output_schema={
            "type": "object",
            "properties": {"ok": {"type": "boolean"}},
            "required": ["ok"],
            "additionalProperties": False,
        },
        structured_output_schema_identity="strict_test",
    )

    with pytest.raises(AppError) as exc_info:
        svc.openai_chat_json(request, _ctx())

    assert exc_info.value.code == "openai_structured_output_unsupported"
    assert exc_info.value.retryable is False


def test_json_object_legacy_compatibility_may_drop_unsupported_response_format(
    external_boundary_mocks_only, tmp_path
) -> None:
    calls: list[dict] = []

    class _LegacyChatCompletion:
        @staticmethod
        def create(**kwargs):
            calls.append(dict(kwargs))
            if "response_format" in kwargs:
                raise TypeError("unexpected keyword argument 'response_format'")
            return {
                "id": "legacy_json_object",
                "choices": [{"message": {"content": '{"ok":true}'}}],
                "usage": {
                    "prompt_tokens": 4,
                    "completion_tokens": 2,
                    "total_tokens": 6,
                },
            }

    external_boundary_mocks_only.setattr(svc.openai_legacy, "OpenAI", None)
    external_boundary_mocks_only.setattr(
        svc.openai_legacy, "ChatCompletion", _LegacyChatCompletion
    )

    result = svc.openai_chat_json(_chat_request(tmp_path), _ctx())

    assert result.parsed_json == {"ok": True}
    assert len(calls) == 2
    assert calls[0]["response_format"] == {"type": "json_object"}
    assert "response_format" not in calls[1]


def test_openai_chat_json_preserves_provider_refusal_without_caching(
    external_boundary_mocks_only, tmp_path
) -> None:
    calls = 0

    class _Chat:
        def create(self, **_kwargs):
            nonlocal calls
            calls += 1
            return SimpleNamespace(
                id=f"refusal_{calls}",
                choices=[
                    SimpleNamespace(
                        finish_reason="content_filter",
                        message=SimpleNamespace(content=None, refusal="blocked"),
                    )
                ],
                usage=SimpleNamespace(
                    prompt_tokens=3, completion_tokens=1, total_tokens=4
                ),
            )

    class _Client:
        def __init__(self, **_kwargs):
            self.chat = SimpleNamespace(completions=_Chat())

    external_boundary_mocks_only.setattr(svc.openai_legacy, "OpenAI", _Client)
    request = replace(
        _chat_request(tmp_path),
        response_cache_enabled=True,
        response_cache_dir=str(tmp_path / "cache"),
    )

    result = svc.openai_chat_json(request, _ctx())
    again = svc.openai_chat_json(request, _ctx())

    assert result.parsed_json is None
    assert result.refusal == "blocked"
    assert result.provider_status == "refused"
    assert result.incomplete_reason == "refusal"
    assert again.request_id == "refusal_2"
    assert calls == 2


def test_openai_chat_json_keeps_complete_strict_schema_contract(
    external_boundary_mocks_only, tmp_path
) -> None:
    payloads: list[dict] = []

    class _Chat:
        def create(self, **kwargs):
            payloads.append(dict(kwargs))
            return SimpleNamespace(
                id="strict_ok",
                choices=[
                    SimpleNamespace(
                        finish_reason="stop",
                        message=SimpleNamespace(content='{"ok":true}', refusal=None),
                    )
                ],
                usage=SimpleNamespace(
                    prompt_tokens=3, completion_tokens=2, total_tokens=5
                ),
            )

    class _Client:
        def __init__(self, **_kwargs):
            self.chat = SimpleNamespace(completions=_Chat())

    external_boundary_mocks_only.setattr(svc.openai_legacy, "OpenAI", _Client)
    request = replace(
        _chat_request(tmp_path),
        structured_output_schema={
            "type": "object",
            "properties": {"ok": {"type": "boolean"}},
            "required": ["ok"],
            "additionalProperties": False,
        },
        structured_output_schema_identity="strict_test",
    )

    result = svc.openai_chat_json(request, _ctx())

    assert result.parsed_json == {"ok": True}
    assert result.finish_reason == "stop"
    assert result.provider_status == "completed"
    assert payloads[0]["response_format"] == {
        "type": "json_schema",
        "json_schema": {
            "name": "strict_test",
            "strict": True,
            "schema": request.structured_output_schema,
        },
    }
