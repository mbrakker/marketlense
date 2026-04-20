from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from src.contracts.openai import OpenAIAnalyzeRequest, OpenAIJSONPromptRequest
from src.contracts.run_context import RunContext
from src.services import openai_service as svc
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
        model_pricing={},
    )


def _analyze_request(tmp_path) -> OpenAIAnalyzeRequest:
    return OpenAIAnalyzeRequest(
        schema_version="1.0",
        system_prompt="system",
        user_prompt="user",
        prompt_system_sha256="system-sha",
        prompt_user_sha256="user-sha",
        model="gpt-4.1-mini",
        temperature=0.1,
        api_key="key",
        seed=11,
        timeout_seconds=5.0,
        cost_ledger_path=str(tmp_path / "ledger.jsonl"),
        cost_daily_path=str(tmp_path / "daily.json"),
        model_pricing={},
    )


def test_openai_chat_json_uses_modern_chat_completion(monkeypatch, tmp_path) -> None:
    captured_client_kwargs = []
    captured_payloads = []

    class _FakeChatCompletions:
        def create(self, **kwargs):
            captured_payloads.append(dict(kwargs))
            usage = SimpleNamespace(
                prompt_tokens=12,
                completion_tokens=5,
                total_tokens=17,
            )
            message = SimpleNamespace(content=json.dumps({"ok": True}))
            choice = SimpleNamespace(message=message)
            return SimpleNamespace(id="chat_1", choices=[choice], usage=usage)

    class _FakeClient:
        def __init__(self, **kwargs):
            captured_client_kwargs.append(dict(kwargs))
            self.chat = SimpleNamespace(completions=_FakeChatCompletions())

    monkeypatch.setattr(svc, "OpenAI", _FakeClient)

    result = svc.openai_chat_json(_chat_request(tmp_path), _ctx())

    assert result.parsed_json == {"ok": True}
    assert result.request_id == "chat_1"
    assert result.input_tokens == 12
    assert result.output_tokens == 5
    assert result.tool_calls == 0
    assert result.total_tokens == 17
    assert captured_client_kwargs == [{"api_key": "key", "timeout": 5.0}]
    assert captured_payloads[0]["response_format"] == {"type": "json_object"}
    assert captured_payloads[0]["seed"] == 7


def test_analyze_report_falls_back_to_legacy_chat_completion(
    monkeypatch, tmp_path
) -> None:
    payload = {
        "tldr": "TLDR",
        "title": "Title",
        "insights": ["1", "2", "3", "4", "5"],
        "quote": {"text": "Quote", "author": "Author"},
        "figure": {"title": "Figure", "evidence": "Evidence"},
        "commentary": "Commentary",
        "source": "Source",
        "publisher": "Publisher",
        "taxonomy": ["Retail"],
        "region": "EU",
        "time_period": "2025",
    }
    legacy_calls = []

    class _FakeLegacyChatCompletion:
        @staticmethod
        def create(**kwargs):
            legacy_calls.append(dict(kwargs))
            return {
                "id": "legacy_1",
                "choices": [{"message": {"content": json.dumps(payload)}}],
                "usage": {
                    "prompt_tokens": 9,
                    "completion_tokens": 4,
                    "total_tokens": 13,
                },
            }

    monkeypatch.setattr(svc, "OpenAI", None)
    monkeypatch.setattr(
        svc.openai_legacy, "ChatCompletion", _FakeLegacyChatCompletion
    )

    result = svc.analyze_report(_analyze_request(tmp_path), _ctx())

    assert result.request_id == "legacy_1"
    assert result.prompt_tokens == 9
    assert result.completion_tokens == 4
    assert result.total_tokens == 13
    assert result.payload.title == "Title"
    assert result.payload.insights == ["1", "2", "3", "4", "5"]
    assert legacy_calls[0]["response_format"] == {"type": "json_object"}


def test_openai_chat_json_maps_provider_failure_to_typed_app_error(
    monkeypatch, tmp_path, assert_app_error
) -> None:
    class _FailingChatCompletions:
        def create(self, **kwargs):
            raise RuntimeError("provider boom")

    class _FailingClient:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=_FailingChatCompletions())

    monkeypatch.setattr(svc, "OpenAI", _FailingClient)

    with pytest.raises(AppError) as exc_info:
        svc.openai_chat_json(_chat_request(tmp_path), _ctx())

    assert_app_error(exc_info.value, code="openai_chat_failed", retryable=True)


def test_legacy_chat_completion_timeout_does_not_leak_between_requests(
    external_boundary_mocks_only, tmp_path
) -> None:
    observed_timeouts: list[float | None] = []

    class _FakeLegacyChatCompletion:
        @staticmethod
        def create(**kwargs):
            observed_timeouts.append(getattr(svc.openai_legacy, "timeout", None))
            return {
                "id": "legacy_chat_1",
                "choices": [{"message": {"content": json.dumps({"ok": True})}}],
                "usage": {
                    "prompt_tokens": 5,
                    "completion_tokens": 2,
                    "total_tokens": 7,
                },
            }

    def _request(timeout_seconds: float | None) -> OpenAIJSONPromptRequest:
        return OpenAIJSONPromptRequest(
            schema_version="1.0",
            system_prompt="system",
            user_prompt="user",
            model="gpt-4.1-mini",
            temperature=0.1,
            api_key="key",
            seed=7,
            timeout_seconds=timeout_seconds,
            cost_ledger_path=str(tmp_path / "ledger.jsonl"),
            cost_daily_path=str(tmp_path / "daily.json"),
            model_pricing={},
        )

    external_boundary_mocks_only.setattr(svc, "OpenAI", None)
    external_boundary_mocks_only.setattr(
        svc.openai_legacy, "ChatCompletion", _FakeLegacyChatCompletion
    )

    had_timeout = hasattr(svc.openai_legacy, "timeout")
    original_timeout = getattr(svc.openai_legacy, "timeout", None)
    try:
        if had_timeout:
            delattr(svc.openai_legacy, "timeout")

        svc.openai_chat_json(_request(1.5), _ctx())
        assert hasattr(svc.openai_legacy, "timeout") is False

        svc.openai_chat_json(_request(None), _ctx())

        assert observed_timeouts == [1.5, None]
        assert hasattr(svc.openai_legacy, "timeout") is False
    finally:
        if had_timeout:
            svc.openai_legacy.timeout = original_timeout
        elif hasattr(svc.openai_legacy, "timeout"):
            delattr(svc.openai_legacy, "timeout")
