from __future__ import annotations

import pytest

from src.services._llm_service.provider_timing import (
    limiter_wait_scope,
    provider_timing_from_exception,
    timed_provider_request,
)


def test_provider_request_timing_uses_monotonic_clock() -> None:
    ticks = iter((20.0, 21.375))
    response = object()

    result, timing = timed_provider_request(
        operation="chat.completions.create",
        call=lambda: response,
        monotonic_fn=lambda: next(ticks),
    )

    assert result is response
    assert timing.provider_elapsed_ms == 1375.0
    assert timing.provider_call_status == "completed"


def test_failed_provider_request_retains_elapsed_time_and_error_type() -> None:
    ticks = iter((4.0, 4.25))

    class ProviderTimeout(RuntimeError):
        status_code = 504

    with pytest.raises(ProviderTimeout) as caught:
        timed_provider_request(
            operation="responses.create",
            call=lambda: (_ for _ in ()).throw(ProviderTimeout()),
            monotonic_fn=lambda: next(ticks),
        )

    timing = provider_timing_from_exception(caught.value)
    assert timing is not None
    assert timing.provider_elapsed_ms == 250.0
    assert timing.provider_call_status == "failed"
    assert timing.provider_error_type == "ProviderTimeout"
    assert timing.provider_http_status == 504


def test_limiter_wait_is_separate_from_provider_elapsed_time() -> None:
    ticks = iter((10.0, 10.5))

    with limiter_wait_scope(in_flight_wait_ms=82, rate_spacing_wait_ms=37):
        _, timing = timed_provider_request(
            operation="embeddings.create",
            call=lambda: "response",
            monotonic_fn=lambda: next(ticks),
        )

    assert timing.provider_elapsed_ms == 500.0
    assert timing.in_flight_wait_ms == 82
    assert timing.rate_spacing_wait_ms == 37
    assert timing.limiter_wait_ms == 119
