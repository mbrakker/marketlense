"""Small provider-request timing primitives shared by LLM adapters."""

from __future__ import annotations

import math
import time
from contextlib import contextmanager, suppress
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Callable, Iterator, TypeVar

_T = TypeVar("_T")


@dataclass(frozen=True)
class ProviderCallTiming:
    operation: str
    provider_elapsed_ms: float
    provider_call_status: str
    provider_request_start_monotonic_ms: float
    provider_request_finish_monotonic_ms: float
    in_flight_wait_ms: int = 0
    rate_spacing_wait_ms: int = 0
    provider_error_type: str = ""
    provider_http_status: int | None = None
    provider_request_id: str | None = None

    @property
    def limiter_wait_ms(self) -> int:
        return self.in_flight_wait_ms + self.rate_spacing_wait_ms


_limiter_wait: ContextVar[tuple[int, int]] = ContextVar(
    "llm_provider_limiter_wait", default=(0, 0)
)


@contextmanager
def limiter_wait_scope(
    *, in_flight_wait_ms: int, rate_spacing_wait_ms: int
) -> Iterator[None]:
    """Expose limiter waits to a provider timer without including them in elapsed."""

    token = _limiter_wait.set(
        (max(0, int(in_flight_wait_ms)), max(0, int(rate_spacing_wait_ms)))
    )
    try:
        yield
    finally:
        _limiter_wait.reset(token)


def _timing(
    *,
    operation: str,
    started_at: float,
    monotonic_fn: Callable[[], float],
    status: str,
    error: Exception | None = None,
) -> ProviderCallTiming:
    ended_at = monotonic_fn()
    started_ms = _bounded_monotonic_ms(started_at)
    finished_ms = _bounded_monotonic_ms(ended_at)
    in_flight_wait_ms, rate_spacing_wait_ms = _limiter_wait.get()
    status_code = None
    request_id = None
    if error is not None:
        response = getattr(error, "response", None)
        raw_status = (
            getattr(error, "status_code", None)
            or getattr(error, "code", None)
            or getattr(response, "status_code", None)
        )
        try:
            status_code = int(raw_status) if raw_status is not None else None
        except (TypeError, ValueError):
            status_code = None
        raw_request_id = getattr(error, "request_id", None)
        headers = getattr(response, "headers", None) or getattr(error, "headers", None)
        get_header = getattr(headers, "get", None)
        if not raw_request_id and callable(get_header):
            raw_request_id = get_header("x-request-id") or get_header("request-id")
        request_id = str(raw_request_id).strip()[:256] if raw_request_id else None
    return ProviderCallTiming(
        operation=operation,
        provider_elapsed_ms=max(0.0, round((ended_at - started_at) * 1_000, 3)),
        provider_call_status=status,
        provider_request_start_monotonic_ms=started_ms,
        provider_request_finish_monotonic_ms=finished_ms,
        in_flight_wait_ms=in_flight_wait_ms,
        rate_spacing_wait_ms=rate_spacing_wait_ms,
        provider_error_type=type(error).__name__ if error is not None else "",
        provider_http_status=status_code,
        provider_request_id=request_id,
    )


def _bounded_monotonic_ms(value: float) -> float:
    """Persist a finite monotonic clock reading with millisecond precision."""

    if not math.isfinite(value) or value < 0:
        return 0.0
    return round(min(value * 1_000, float(2**53 - 1)), 3)


def timed_provider_request(
    *,
    operation: str,
    call: Callable[[], _T],
    monotonic_fn: Callable[[], float] = time.monotonic,
) -> tuple[_T, ProviderCallTiming]:
    """Time only the SDK/HTTP operation, preserving the original exception."""

    started_at = monotonic_fn()
    try:
        result = call()
    except Exception as exc:
        timing = _timing(
            operation=operation,
            started_at=started_at,
            monotonic_fn=monotonic_fn,
            status="failed",
            error=exc,
        )
        with suppress(AttributeError, TypeError):
            exc._marketlense_provider_timing = timing  # type: ignore[attr-defined]
        raise
    return result, _timing(
        operation=operation,
        started_at=started_at,
        monotonic_fn=monotonic_fn,
        status="completed",
    )


def provider_timing_from_exception(exc: Exception) -> ProviderCallTiming | None:
    timing = getattr(exc, "_marketlense_provider_timing", None)
    return timing if isinstance(timing, ProviderCallTiming) else None
