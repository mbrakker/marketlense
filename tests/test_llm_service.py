from __future__ import annotations

import json
import logging
from types import SimpleNamespace

import pytest

from src.contracts.llm import LLMClientPolicy
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


def test_llm_service_retries_with_backoff(
    caplog,
    assert_logs_have_required_fields,
) -> None:
    caplog.set_level(logging.INFO, logger="market_lense.llm_service")
    calls = {"count": 0}
    sleeps: list[float] = []

    class _FailThenSucceedClient:
        def openai_chat_json(self, req, ctx):
            calls["count"] += 1
            if calls["count"] == 1:
                raise AppError(
                    code="openai_chat_failed",
                    message="retry me",
                    retryable=True,
                )
            return SimpleNamespace(schema_version="1.0", parsed_json={"ok": True})

    client = llm_service.build_openai_client(
        base_client=_FailThenSucceedClient(),
        policy=LLMClientPolicy(
            schema_version="1.0",
            scope="llm-service-retry",
            retries=1,
            base_delay_seconds=1.0,
            backoff_step_seconds=1.0,
            jitter_seconds=0.0,
            circuit_breaker_failure_threshold=0,
            circuit_breaker_recovery_seconds=0.0,
        ),
        sleep_fn=lambda seconds: sleeps.append(float(seconds)),
        monotonic_fn=lambda: 100.0,
    )

    response = client.openai_chat_json(SimpleNamespace(model="gpt-5-mini"), _ctx())

    assert response.parsed_json == {"ok": True}
    assert calls["count"] == 2
    assert sleeps == [1.0]
    events = _events(caplog)
    retry_events = [event for event in events if event.get("event") == "llm_call_retry"]
    complete_events = [event for event in events if event.get("event") == "llm_call_complete"]
    assert len(retry_events) == 1
    assert len(complete_events) == 1
    assert_logs_have_required_fields(retry_events + complete_events)
    retry_fields = retry_events[0]["fields"]
    assert retry_fields["operation"] == "openai_chat_json"
    assert retry_fields["attempt"] == 1
    assert retry_fields["delay_seconds"] == 1.0
    assert retry_fields["code"] == "openai_chat_failed"


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
    opened_events = [event for event in events if event.get("event") == "llm_circuit_opened"]
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
    half_open_events = [event for event in events if event.get("event") == "llm_circuit_half_open"]
    closed_events = [event for event in events if event.get("event") == "llm_circuit_closed"]
    assert len(half_open_events) == 1
    assert len(closed_events) == 1
    assert_logs_have_required_fields(half_open_events + closed_events)
