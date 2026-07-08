from __future__ import annotations

import json
import logging
from types import SimpleNamespace
from typing import Any, cast

import pytest

from src.contracts.llm import LLMClientPolicy, LLMProviderOperations
from src.contracts.run_context import RunContext
from src.services import llm_service
from src.utils.errors import AppError


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


def _events(caplog) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for record in caplog.records:
        if record.name != "market_lense.llm_service":
            continue
        payload = json.loads(record.message)
        if isinstance(payload, dict):
            events.append(payload)
    return events


def test_llm_service_propagates_retryable_error_without_retrying(
    caplog,
    assert_app_error,
    assert_logs_have_required_fields,
) -> None:
    caplog.set_level(logging.INFO, logger="market_lense.llm_service")
    calls = {"count": 0}
    sleeps: list[float] = []

    class _RetryableFailureClient:
        def openai_chat_json(self, req, ctx):
            calls["count"] += 1
            raise AppError(
                code="openai_chat_failed",
                message="retry at orchestrator",
                retryable=True,
            )

    client = llm_service.build_openai_client(
        base_client=_RetryableFailureClient(),
        policy=LLMClientPolicy(
            schema_version="1.0",
            scope="llm-service-single-attempt",
            retries=3,
            base_delay_seconds=1.0,
            backoff_step_seconds=1.0,
            jitter_seconds=0.0,
            circuit_breaker_failure_threshold=0,
            circuit_breaker_recovery_seconds=0.0,
        ),
        sleep_fn=lambda seconds: sleeps.append(float(seconds)),
        monotonic_fn=lambda: 100.0,
    )

    with pytest.raises(AppError) as exc_info:
        client.openai_chat_json(SimpleNamespace(model="gpt-5-mini"), _ctx())

    assert_app_error(exc_info.value, code="openai_chat_failed", retryable=True)
    assert calls["count"] == 1
    assert sleeps == []
    events = _events(caplog)
    retry_events = [event for event in events if event.get("event") == "llm_call_retry"]
    failed_events = [
        event for event in events if event.get("event") == "llm_call_failed"
    ]
    assert retry_events == []
    assert len(failed_events) == 1
    assert_logs_have_required_fields(failed_events)
    failed_fields = cast(dict[str, Any], failed_events[0]["fields"])
    assert failed_fields["operation"] == "openai_chat_json"
    assert failed_fields["attempt"] == 0
    assert failed_fields["retry_owner"] == "orchestrator"
    assert failed_fields["service_attempt_limit"] == 1
    assert failed_fields["legacy_configured_retries"] == 3


def test_llm_service_opens_circuit_after_repeated_failures(
    caplog,
    assert_app_error,
) -> None:
    caplog.set_level(logging.INFO, logger="market_lense.llm_service")
    calls = {"count": 0}
    now = {"value": 50.0}

    class _AlwaysFailClient:
        def openai_chat_json(self, req, ctx):
            calls["count"] += 1
            raise AppError(
                code="openai_chat_failed",
                message="still failing",
                retryable=True,
            )

    client = llm_service.build_openai_client(
        base_client=_AlwaysFailClient(),
        policy=LLMClientPolicy(
            schema_version="1.0",
            scope="llm-service-circuit",
            retries=0,
            base_delay_seconds=0.0,
            backoff_step_seconds=0.0,
            jitter_seconds=0.0,
            circuit_breaker_failure_threshold=2,
            circuit_breaker_recovery_seconds=30.0,
        ),
        sleep_fn=lambda _seconds: None,
        monotonic_fn=lambda: now["value"],
    )

    with pytest.raises(AppError) as first_exc:
        client.openai_chat_json(SimpleNamespace(model="gpt-5-mini"), _ctx())
    assert_app_error(first_exc.value, code="openai_chat_failed", retryable=True)

    with pytest.raises(AppError) as second_exc:
        client.openai_chat_json(SimpleNamespace(model="gpt-5-mini"), _ctx())
    assert_app_error(second_exc.value, code="openai_chat_failed", retryable=True)

    with pytest.raises(AppError) as third_exc:
        client.openai_chat_json(SimpleNamespace(model="gpt-5-mini"), _ctx())
    assert_app_error(third_exc.value, code="llm_circuit_open", retryable=True)
    assert calls["count"] == 2

    events = _events(caplog)
    opened_events = [
        event for event in events if event.get("event") == "llm_circuit_opened"
    ]
    short_circuit_events = [
        event for event in events if event.get("event") == "llm_circuit_short_circuit"
    ]
    assert len(opened_events) == 1
    assert len(short_circuit_events) == 1


def test_llm_service_allows_half_open_probe_after_recovery(
    caplog,
    assert_logs_have_required_fields,
) -> None:
    caplog.set_level(logging.INFO, logger="market_lense.llm_service")
    calls = {"count": 0}
    now = {"value": 10.0}

    class _RecoveringClient:
        def openai_chat_json(self, req, ctx):
            calls["count"] += 1
            if calls["count"] <= 2:
                raise AppError(
                    code="openai_chat_failed",
                    message="transient",
                    retryable=True,
                )
            return SimpleNamespace(schema_version="1.0", parsed_json={"ok": True})

    client = llm_service.build_openai_client(
        base_client=_RecoveringClient(),
        policy=LLMClientPolicy(
            schema_version="1.0",
            scope="llm-service-half-open",
            retries=0,
            base_delay_seconds=0.0,
            backoff_step_seconds=0.0,
            jitter_seconds=0.0,
            circuit_breaker_failure_threshold=2,
            circuit_breaker_recovery_seconds=5.0,
        ),
        sleep_fn=lambda _seconds: None,
        monotonic_fn=lambda: now["value"],
    )

    for _ in range(2):
        with pytest.raises(AppError):
            client.openai_chat_json(SimpleNamespace(model="gpt-5-mini"), _ctx())

    now["value"] = 16.0
    response = client.openai_chat_json(SimpleNamespace(model="gpt-5-mini"), _ctx())

    assert response.parsed_json == {"ok": True}
    assert calls["count"] == 3
    events = _events(caplog)
    half_open_events = [
        event for event in events if event.get("event") == "llm_circuit_half_open"
    ]
    closed_events = [
        event for event in events if event.get("event") == "llm_circuit_closed"
    ]
    assert len(half_open_events) == 1
    assert len(closed_events) == 1
    assert_logs_have_required_fields(half_open_events + closed_events)


def test_llm_service_does_not_retry_refusal_class_errors(
    caplog,
    assert_app_error,
    assert_logs_have_required_fields,
) -> None:
    caplog.set_level(logging.INFO, logger="market_lense.llm_service")
    calls = {"count": 0}

    class _RefusalClient:
        def openai_chat_json(self, req, ctx):
            calls["count"] += 1
            raise AppError(
                code="openai_refusal",
                message="policy refusal",
                retryable=True,
            )

    client = llm_service.build_openai_client(
        base_client=_RefusalClient(),
        policy=LLMClientPolicy(
            schema_version="1.0",
            scope="llm-service-refusal",
            retries=3,
            base_delay_seconds=0.0,
            backoff_step_seconds=0.0,
            jitter_seconds=0.0,
            circuit_breaker_failure_threshold=0,
            circuit_breaker_recovery_seconds=0.0,
        ),
        sleep_fn=lambda _seconds: None,
        monotonic_fn=lambda: 100.0,
    )

    with pytest.raises(AppError) as exc_info:
        client.openai_chat_json(SimpleNamespace(model="gpt-5-mini"), _ctx())

    assert_app_error(exc_info.value, code="openai_refusal", retryable=True)
    assert calls["count"] == 1
    events = _events(caplog)
    retry_events = [event for event in events if event.get("event") == "llm_call_retry"]
    failed_events = [
        event for event in events if event.get("event") == "llm_call_failed"
    ]
    assert retry_events == []
    assert len(failed_events) == 1
    failed_fields = cast(dict[str, Any], failed_events[0]["fields"])
    assert (
        failed_fields["retry_decision_code"]
        == "non_retryable_error_code:openai_refusal"
    )
    assert_logs_have_required_fields(failed_events)


def test_callable_builder_uses_explicit_provider_operations_contract() -> None:
    operations = LLMProviderOperations(
        schema_version="1.0",
        openai_chat_json=lambda req, ctx: SimpleNamespace(parsed_json={"ok": True}),
    )

    client = llm_service.build_openai_client(
        base_client=operations,
        policy=LLMClientPolicy(schema_version="1.0", scope="operations-contract"),
    )

    result = client.openai_chat_json(SimpleNamespace(model="gpt-5-mini"), _ctx())

    assert result.parsed_json == {"ok": True}


def test_generic_builder_names_preserve_provider_operations_contract() -> None:
    operations = LLMProviderOperations(
        schema_version="1.0",
        openai_chat_json=lambda req, ctx: SimpleNamespace(parsed_json={"ok": True}),
    )

    client = llm_service.build_client(
        base_client=operations,
        policy=LLMClientPolicy(schema_version="1.0", scope="generic-builder"),
    )

    result = client.openai_chat_json(SimpleNamespace(model="gpt-5-mini"), _ctx())

    assert result.parsed_json == {"ok": True}
    assert llm_service.build_openai_client is llm_service.build_client
    assert (
        llm_service.build_openai_client_from_callables
        is llm_service.build_client_from_callables
    )
    assert (
        llm_service.build_openai_client_for_settings
        is llm_service.build_client_for_settings
    )
    assert (
        llm_service.openai_client_policy_from_settings
        is llm_service.client_policy_from_settings
    )


def test_llm_client_logs_replayable_model_call_audit_record(
    caplog,
    assert_logs_have_required_fields,
) -> None:
    caplog.set_level(logging.INFO, logger="market_lense.llm_service")

    class _SuccessfulClient:
        def openai_chat_json(self, req, ctx):
            return SimpleNamespace(
                schema_version="1.0",
                parsed_json={"ok": True},
                input_tokens=12,
                output_tokens=5,
                total_tokens=17,
                request_id="resp_123",
                model=req.model,
            )

    client = llm_service.build_openai_client(
        base_client=_SuccessfulClient(),
        policy=LLMClientPolicy(schema_version="1.0", scope="audit-scope"),
    )

    result = client.openai_chat_json(
        SimpleNamespace(
            model="gpt-5-mini",
            temperature=0.2,
            seed=42,
            system_prompt="system prompt",
            user_prompt="user prompt",
            prompt_namespace="report_vs/doc_map",
            prompt_hash="prompt-hash",
            schema_name="doc_map",
            schema_version="1.0",
            response_cache_enabled=True,
            response_cache_dir="cache",
            response_cache_ttl_seconds=60.0,
            validation_result="pass",
            timeout_seconds=30.0,
        ),
        _ctx(),
    )

    assert result.parsed_json == {"ok": True}
    events = _events(caplog)
    audits = [event for event in events if event.get("event") == "llm_model_call_audit"]
    assert len(audits) == 1
    assert_logs_have_required_fields(audits)
    fields = cast(dict[str, Any], audits[0]["fields"])
    assert fields["prompt_namespace"] == "report_vs/doc_map"
    assert fields["prompt_hash"] == "prompt-hash"
    assert fields["rendered_prompt_redaction_hash"]
    assert fields["model"] == "gpt-5-mini"
    assert fields["seed_supported"] is True
    assert fields["schema_name"] == "doc_map"
    assert fields["response_id"] == "resp_123"
    assert fields["total_tokens"] == 17
    assert fields["cache_decision"] == "enabled"
    assert fields["provider_decision"] == "openai_primary"
    assert "system prompt" not in json.dumps(audits)
    assert "user prompt" not in json.dumps(audits)


def test_llm_replay_bundle_reconstructs_context_without_provider_call() -> None:
    record = llm_service.build_model_call_audit_record(
        operation="openai_chat_json",
        scope="audit-scope",
        request=SimpleNamespace(
            model="gpt-5-mini",
            temperature=0.0,
            seed=None,
            system_prompt="system",
            user_prompt="user",
            prompt_namespace="report_vs/doc_map",
            prompt_hash="hash",
            schema_name="doc_map",
            schema_version="1.0",
            response_cache_enabled=False,
        ),
        response=SimpleNamespace(
            request_id=None,
            input_tokens=None,
            output_tokens=None,
            total_tokens=None,
            model="gpt-5-mini",
        ),
    )

    bundle = llm_service.build_model_call_replay_bundle(record)

    assert bundle.live_provider_call_allowed is False
    assert bundle.audit_record.operation == "openai_chat_json"
    assert bundle.replay_inputs["prompt_namespace"] == "report_vs/doc_map"
    assert bundle.replay_inputs["model"] == "gpt-5-mini"


def test_openrouter_client_construction_is_owned_by_llm_service(
    caplog,
    assert_logs_have_required_fields,
) -> None:
    caplog.set_level(logging.INFO, logger="market_lense.llm_service")
    captured: list[dict[str, object]] = []

    def _factory(**kwargs: object) -> object:
        captured.append(dict(kwargs))
        return SimpleNamespace(provider="openrouter")

    settings = SimpleNamespace(
        openrouter_api_key="secret-key",
        model="openai/gpt-5-mini",
        openrouter_http_referer="https://marketlense.local",
        temperature=0.0,
        timeout_seconds=30.0,
        max_tokens=16000,
    )

    result = llm_service.build_openrouter_client(
        settings=settings,
        ctx=_ctx(),
        client_factory=_factory,
    )

    assert result.provider == "openrouter"
    assert captured == [
        {
            "model": "openai/gpt-5-mini",
            "api_key": "secret-key",
            "http_referer": "https://marketlense.local",
            "temperature": 0.0,
            "timeout": 30.0,
            "extra_body": {"max_tokens": 12000},
            "max_retries": 0,
        }
    ]
    events = _events(caplog)
    relevant = [
        event
        for event in events
        if event.get("event")
        in {"llm_openrouter_client_start", "llm_openrouter_client_complete"}
    ]
    assert len(relevant) == 2
    assert "secret-key" not in json.dumps(relevant)
    assert_logs_have_required_fields(relevant)


def test_openrouter_client_uses_installed_browser_use_openrouter_signature() -> None:
    import inspect

    from browser_use import ChatOpenRouter

    captured: list[dict[str, object]] = []

    def _factory(**kwargs: object) -> object:
        unexpected = set(kwargs).difference(
            set(inspect.signature(ChatOpenRouter).parameters)
        )
        assert unexpected == set()
        captured.append(dict(kwargs))
        return SimpleNamespace(provider="openrouter")

    settings = SimpleNamespace(
        openrouter_api_key="secret-key",
        model="openai/gpt-5-mini",
        openrouter_http_referer="https://marketlense.local",
        temperature=0.0,
        timeout_seconds=30.0,
        max_tokens=16000,
    )

    llm_service.build_openrouter_client(
        settings=settings,
        ctx=_ctx(),
        client_factory=_factory,
    )

    assert captured[0]["extra_body"] == {"max_tokens": 12000}
    assert "max_tokens" not in captured[0]


def test_openrouter_client_missing_key_raises_typed_error(
    assert_app_error,
) -> None:
    settings = SimpleNamespace(
        openrouter_api_key="",
        model="openai/gpt-5-mini",
        openrouter_http_referer=None,
        temperature=0.0,
        timeout_seconds=30.0,
    )

    with pytest.raises(AppError) as exc_info:
        llm_service.build_openrouter_client(
            settings=settings,
            ctx=_ctx(),
            client_factory=lambda **kwargs: object(),
        )

    assert_app_error(
        exc_info.value,
        code="openrouter_missing_api_key",
        retryable=False,
    )


def test_openrouter_client_provider_failure_is_typed(
    assert_app_error,
) -> None:
    settings = SimpleNamespace(
        openrouter_api_key="secret-key",
        model="openai/gpt-5-mini",
        openrouter_http_referer=None,
        temperature=0.0,
        timeout_seconds=30.0,
    )

    def _factory(**kwargs: object) -> object:
        raise RuntimeError("provider init failed")

    with pytest.raises(AppError) as exc_info:
        llm_service.build_openrouter_client(
            settings=settings,
            ctx=_ctx(),
            client_factory=_factory,
        )

    assert_app_error(
        exc_info.value,
        code="openrouter_client_init_failed",
        retryable=True,
    )
