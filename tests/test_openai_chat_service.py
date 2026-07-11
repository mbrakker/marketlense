from __future__ import annotations

import json
import logging
from dataclasses import replace
from types import SimpleNamespace

import pytest

from src.contracts.llm import LLMContextCompactionPolicy
from src.contracts.openai import (
    OpenAIAnalyzeRequest,
    OpenAIJSONPromptRequest,
    OpenAIUsageAccountingResponse,
)
from src.contracts.run_context import RunContext
from src.services import llm_service as svc
from src.services import openai_accounting_service
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

    monkeypatch.setattr(svc.openai_legacy, "OpenAI", _FakeClient)

    result = svc.openai_chat_json(_chat_request(tmp_path), _ctx())

    assert result.parsed_json == {"ok": True}
    assert result.request_id == "chat_1"
    assert result.input_tokens == 12
    assert result.output_tokens == 5
    assert result.tool_calls == 0
    assert result.total_tokens == 17
    assert captured_client_kwargs == [
        {"api_key": "key", "max_retries": 0, "timeout": 5.0}
    ]
    assert captured_payloads[0]["response_format"] == {"type": "json_object"}
    assert captured_payloads[0]["seed"] == 7


def test_openai_chat_json_delegates_usage_accounting(
    external_boundary_mocks_only, tmp_path
) -> None:
    captured_accounting = []

    class _FakeChatCompletions:
        def create(self, **kwargs):
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
            self.chat = SimpleNamespace(completions=_FakeChatCompletions())

    def _record_usage(request, ctx):
        captured_accounting.append((request, ctx))
        return OpenAIUsageAccountingResponse(
            schema_version="1.0",
            recorded=True,
            estimated_cost_usd=0.0,
            ledger_path=request.cost_ledger_path,
            daily_path=request.cost_daily_path,
        )

    external_boundary_mocks_only.setattr(svc.openai_legacy, "OpenAI", _FakeClient)
    external_boundary_mocks_only.setattr(
        openai_accounting_service, "record_usage", _record_usage
    )

    result = svc.openai_chat_json(_chat_request(tmp_path), _ctx())

    assert result.parsed_json == {"ok": True}
    assert len(captured_accounting) == 1
    accounting_request, accounting_ctx = captured_accounting[0]
    assert accounting_ctx == _ctx()
    assert accounting_request.step_name == "openai_chat_json"
    assert accounting_request.model == "gpt-4.1-mini"
    assert accounting_request.input_tokens == 12
    assert accounting_request.output_tokens == 5
    assert accounting_request.tool_calls == 0
    assert accounting_request.request_id == "chat_1"
    assert accounting_request.cost_ledger_path == str(tmp_path / "ledger.jsonl")
    assert not (tmp_path / "ledger.jsonl").exists()


def test_openai_chat_json_records_semantic_artifact_action(
    external_boundary_mocks_only, tmp_path
) -> None:
    captured_accounting = []

    class _FakeChatCompletions:
        def create(self, **kwargs):
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
            self.chat = SimpleNamespace(completions=_FakeChatCompletions())

    def _record_usage(request, ctx):
        captured_accounting.append((request, ctx))
        return OpenAIUsageAccountingResponse(
            schema_version="1.0",
            recorded=True,
            estimated_cost_usd=0.0,
            ledger_path=request.cost_ledger_path,
            daily_path=request.cost_daily_path,
        )

    external_boundary_mocks_only.setattr(svc.openai_legacy, "OpenAI", _FakeClient)
    external_boundary_mocks_only.setattr(
        openai_accounting_service, "record_usage", _record_usage
    )

    svc.openai_chat_json(
        replace(
            _chat_request(tmp_path),
            prompt_namespace="report_vs/artifacts/insights_final",
        ),
        _ctx(),
    )

    assert captured_accounting[0][0].action == "artifacts:insights_final"


def test_openai_chat_json_emits_redacted_model_call_audit(
    external_boundary_mocks_only,
    tmp_path,
    caplog,
    assert_logs_have_required_fields,
) -> None:
    caplog.set_level(logging.INFO, logger="market_lense.llm_service.openai")

    class _FakeChatCompletions:
        def create(self, **kwargs):
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
            self.chat = SimpleNamespace(completions=_FakeChatCompletions())

    external_boundary_mocks_only.setattr(svc.openai_legacy, "OpenAI", _FakeClient)

    result = svc.openai_chat_json(_chat_request(tmp_path), _ctx())

    assert result.parsed_json == {"ok": True}
    events = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == "market_lense.llm_service.openai"
    ]
    audits = [event for event in events if event.get("event") == "llm_model_call_audit"]
    assert len(audits) == 1
    assert_logs_have_required_fields(audits)
    fields = audits[0]["fields"]
    assert fields["operation"] == "openai_chat_json"
    assert fields["scope"] == "direct-openai-chat-json"
    assert fields["rendered_prompt_redaction_hash"]
    assert fields["model"] == "gpt-4.1-mini"
    assert fields["response_id"] == "chat_1"
    assert fields["input_tokens"] == 12
    assert fields["output_tokens"] == 5
    assert fields["total_tokens"] == 17
    assert "system" not in json.dumps(audits)
    assert "user" not in json.dumps(audits)


def test_openai_chat_json_semantic_response_cache_skips_repeated_provider_call(
    monkeypatch,
    tmp_path,
    caplog,
    assert_logs_have_required_fields,
) -> None:
    caplog.set_level(logging.INFO, logger="market_lense.llm_service.openai")
    call_count = {"value": 0}

    class _FakeChatCompletions:
        def create(self, **kwargs):
            call_count["value"] += 1
            usage = SimpleNamespace(
                prompt_tokens=12,
                completion_tokens=5,
                total_tokens=17,
            )
            message = SimpleNamespace(content=json.dumps({"ok": True}))
            choice = SimpleNamespace(message=message)
            return SimpleNamespace(
                id=f"chat_{call_count['value']}", choices=[choice], usage=usage
            )

    class _FakeClient:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=_FakeChatCompletions())

    monkeypatch.setattr(svc.openai_legacy, "OpenAI", _FakeClient)
    request = OpenAIJSONPromptRequest(
        **{
            **_chat_request(tmp_path).__dict__,
            "response_cache_enabled": True,
            "response_cache_dir": str(tmp_path / "cache"),
            "response_cache_ttl_seconds": 3600.0,
        }
    )

    first = svc.openai_chat_json(request, _ctx())
    second = svc.openai_chat_json(request, _ctx())

    assert first.parsed_json == {"ok": True}
    assert second.parsed_json == {"ok": True}
    assert first.request_id == "chat_1"
    assert second.request_id == "chat_1"
    assert call_count["value"] == 1
    events = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == "market_lense.llm_service.openai"
    ]
    cache_events = [
        event
        for event in events
        if event.get("event")
        in {
            "openai_semantic_cache_miss",
            "openai_semantic_cache_write",
            "openai_semantic_cache_hit",
        }
    ]
    assert [event["event"] for event in cache_events] == [
        "openai_semantic_cache_miss",
        "openai_semantic_cache_write",
        "openai_semantic_cache_hit",
    ]
    assert cache_events[0]["fields"]["reason"] == "missing"
    assert_logs_have_required_fields(cache_events)


def test_openai_chat_json_compacts_over_budget_prompt_before_provider_call(
    external_boundary_mocks_only,
    tmp_path,
    caplog,
    assert_logs_have_required_fields,
) -> None:
    caplog.set_level(logging.INFO, logger="market_lense.llm_service.openai")
    captured_payloads: list[dict] = []
    noise = "\n".join(f"background filler row {index}" for index in range(120))
    user_prompt = "\n".join(
        [
            "METRIC: 87% of leaders named digital video a 2026 priority.",
            'QUOTE: "Trust controls determine whether AI commerce scales."',
            "CLAIM: Retail media investment is shifting toward measured attention.",
            "CITATION: IAS-2026-page-12",
            noise,
            "VALIDATION_ANCHOR: source-table-4",
        ]
    )

    class _FakeChatCompletions:
        def create(self, **kwargs):
            captured_payloads.append(dict(kwargs))
            usage = SimpleNamespace(
                prompt_tokens=48,
                completion_tokens=5,
                total_tokens=53,
            )
            message = SimpleNamespace(content=json.dumps({"ok": True}))
            choice = SimpleNamespace(message=message)
            return SimpleNamespace(id="chat_compacted", choices=[choice], usage=usage)

    class _FakeClient:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=_FakeChatCompletions())

    external_boundary_mocks_only.setattr(svc.openai_legacy, "OpenAI", _FakeClient)
    request = OpenAIJSONPromptRequest(
        **{
            **_chat_request(tmp_path).__dict__,
            "user_prompt": user_prompt,
            "model_pricing": {
                "gpt-4.1-mini": {
                    "input_tokens_per_1k_usd": 0.1,
                    "output_tokens_per_1k_usd": 0.2,
                }
            },
            "context_compaction_policy": LLMContextCompactionPolicy(
                schema_version="1.0",
                enabled=True,
                max_input_tokens=90,
                max_estimated_input_cost_usd=0.009,
                expected_output_tokens=16,
                strategy="anchor_preserving_head_tail",
            ),
        }
    )

    result = svc.openai_chat_json(request, _ctx())

    assert result.parsed_json == {"ok": True}
    sent_user_prompt = captured_payloads[0]["messages"][1]["content"]
    assert len(sent_user_prompt) < len(user_prompt)
    assert "METRIC: 87%" in sent_user_prompt
    assert "QUOTE:" in sent_user_prompt
    assert "CLAIM:" in sent_user_prompt
    assert "CITATION:" in sent_user_prompt
    assert "VALIDATION_ANCHOR:" in sent_user_prompt
    assert "background filler row 119" in sent_user_prompt
    assert "background filler row 60" not in sent_user_prompt
    events = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == "market_lense.llm_service.openai"
    ]
    compaction_events = [
        event
        for event in events
        if event.get("event") == "llm_context_compaction_applied"
    ]
    assert len(compaction_events) == 1
    assert_logs_have_required_fields(compaction_events)
    fields = compaction_events[0]["fields"]
    assert fields["operation"] == "openai_chat_json"
    assert fields["strategy"] == "anchor_preserving_head_tail"
    assert fields["original_input_tokens_est"] > fields["compacted_input_tokens_est"]
    assert fields["avoided_input_tokens_est"] > 0
    assert fields["estimated_avoided_cost_usd"] > 0


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

    monkeypatch.setattr(svc.openai_legacy, "OpenAI", None)
    monkeypatch.setattr(svc.openai_legacy, "ChatCompletion", _FakeLegacyChatCompletion)

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

    monkeypatch.setattr(svc.openai_legacy, "OpenAI", _FailingClient)

    with pytest.raises(AppError) as exc_info:
        svc.openai_chat_json(_chat_request(tmp_path), _ctx())

    assert_app_error(exc_info.value, code="openai_chat_failed", retryable=True)


def test_openai_chat_json_maps_content_filter_to_non_retryable_refusal(
    monkeypatch, tmp_path, assert_app_error
) -> None:
    class _RefusingChatCompletions:
        def create(self, **kwargs):
            raise RuntimeError("content_filter blocked by safety policy")

    class _RefusingClient:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=_RefusingChatCompletions())

    monkeypatch.setattr(svc.openai_legacy, "OpenAI", _RefusingClient)

    with pytest.raises(AppError) as exc_info:
        svc.openai_chat_json(_chat_request(tmp_path), _ctx())

    assert_app_error(exc_info.value, code="openai_refusal", retryable=False)
    assert exc_info.value.context["provider_error_type"] == "RuntimeError"


def test_legacy_chat_completion_policy_does_not_leak_between_requests(
    external_boundary_mocks_only, tmp_path
) -> None:
    observed_timeouts: list[float | None] = []
    observed_max_retries: list[int | None] = []

    class _FakeLegacyChatCompletion:
        @staticmethod
        def create(**kwargs):
            observed_timeouts.append(getattr(svc.openai_legacy, "timeout", None))
            observed_max_retries.append(getattr(svc.openai_legacy, "max_retries", None))
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

    external_boundary_mocks_only.setattr(svc.openai_legacy, "OpenAI", None)
    external_boundary_mocks_only.setattr(
        svc.openai_legacy, "ChatCompletion", _FakeLegacyChatCompletion
    )

    had_timeout = hasattr(svc.openai_legacy, "timeout")
    original_timeout = getattr(svc.openai_legacy, "timeout", None)
    had_max_retries = hasattr(svc.openai_legacy, "max_retries")
    original_max_retries = getattr(svc.openai_legacy, "max_retries", None)
    try:
        if had_timeout:
            delattr(svc.openai_legacy, "timeout")

        svc.openai_chat_json(_request(1.5), _ctx())
        assert hasattr(svc.openai_legacy, "timeout") is False

        svc.openai_chat_json(_request(None), _ctx())

        assert observed_timeouts == [1.5, None]
        assert observed_max_retries == [0, 0]
        assert hasattr(svc.openai_legacy, "timeout") is False
        assert getattr(svc.openai_legacy, "max_retries", None) == original_max_retries
    finally:
        if had_timeout:
            svc.openai_legacy.timeout = original_timeout
        elif hasattr(svc.openai_legacy, "timeout"):
            delattr(svc.openai_legacy, "timeout")
        if had_max_retries:
            svc.openai_legacy.max_retries = original_max_retries
        elif hasattr(svc.openai_legacy, "max_retries"):
            delattr(svc.openai_legacy, "max_retries")
