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
