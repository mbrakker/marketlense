from __future__ import annotations

import logging
import random
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional, TypeVar

from src.contracts.llm import LLMClientPolicy, LLMProviderOperations
from src.contracts.run_context import RunContext
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.llm_service")

_T = TypeVar("_T")


@dataclass
class _CircuitBreakerState:
    consecutive_failures: int = 0
    opened_until_monotonic: float = 0.0
    half_open_in_flight: bool = False


@dataclass
class _RateLimiterState:
    max_in_flight: int
    min_interval_seconds: float
    semaphore: threading.BoundedSemaphore
    gate_lock: threading.Lock
    next_allowed_monotonic: float


@dataclass(frozen=True)
class _LLMRetryDecision:
    retryable: bool
    reason_code: str


NON_RETRYABLE_LLM_ERROR_CODES = {
    "openai_authentication_failed",
    "openai_bad_request",
    "openai_content_filter",
    "openai_invalid_request",
    "openai_policy_violation",
    "openai_refusal",
    "openai_response_refusal",
}
_CIRCUIT_BREAKERS_LOCK = threading.Lock()
_CIRCUIT_BREAKERS: dict[str, _CircuitBreakerState] = {}
_RATE_LIMITERS_LOCK = threading.Lock()
_RATE_LIMITERS: dict[str, _RateLimiterState] = {}


def _openai_boundary() -> Any:
    from src.services import openai_service

    return openai_service


def _llm_retry_decision(exc: Exception) -> _LLMRetryDecision:
    if not isinstance(exc, AppError):
        return _LLMRetryDecision(False, "non_app_error")
    if exc.code == "llm_circuit_open":
        return _LLMRetryDecision(False, "circuit_open")
    if exc.code in NON_RETRYABLE_LLM_ERROR_CODES:
        return _LLMRetryDecision(False, f"non_retryable_error_code:{exc.code}")
    if not bool(exc.retryable):
        return _LLMRetryDecision(False, "app_error_non_retryable")
    return _LLMRetryDecision(True, f"retryable_error_code:{exc.code}")


def _is_retryable_llm_error(exc: Exception) -> bool:
    return _llm_retry_decision(exc).retryable


def _retry_delay_seconds(policy: LLMClientPolicy, attempt_index: int) -> float:
    delay = float(policy.base_delay_seconds) + (
        float(policy.backoff_step_seconds) * float(attempt_index)
    )
    if policy.jitter_seconds > 0:
        delay += random.uniform(0.0, float(policy.jitter_seconds))
    return max(0.0, delay)


def _policy_scope(policy: LLMClientPolicy, operation_name: str) -> str:
    base_scope = str(policy.scope or "").strip() or "default"
    return f"{base_scope}:{operation_name}"


def _circuit_breaker_enabled(policy: LLMClientPolicy) -> bool:
    return (
        int(policy.circuit_breaker_failure_threshold) > 0
        and float(policy.circuit_breaker_recovery_seconds) > 0.0
    )


def _get_circuit_breaker_state(
    policy: LLMClientPolicy, operation_name: str
) -> _CircuitBreakerState:
    scope = _policy_scope(policy, operation_name)
    with _CIRCUIT_BREAKERS_LOCK:
        state = _CIRCUIT_BREAKERS.get(scope)
        if state is None:
            state = _CircuitBreakerState()
            _CIRCUIT_BREAKERS[scope] = state
        return state


def _get_rate_limiter_state(
    policy: LLMClientPolicy, operation_name: str
) -> _RateLimiterState | None:
    max_in_flight = policy.rate_limit_max_in_flight
    if max_in_flight is None or int(max_in_flight) <= 0:
        return None
    scope = _policy_scope(policy, operation_name)
    min_interval_seconds = max(0.0, float(policy.rate_limit_min_interval_ms) / 1000.0)
    with _RATE_LIMITERS_LOCK:
        limiter = _RATE_LIMITERS.get(scope)
        if (
            limiter is None
            or limiter.max_in_flight != int(max_in_flight)
            or abs(limiter.min_interval_seconds - min_interval_seconds) > 1e-9
        ):
            limiter = _RateLimiterState(
                max_in_flight=int(max_in_flight),
                min_interval_seconds=min_interval_seconds,
                semaphore=threading.BoundedSemaphore(int(max_in_flight)),
                gate_lock=threading.Lock(),
                next_allowed_monotonic=0.0,
            )
            _RATE_LIMITERS[scope] = limiter
        return limiter


def _log_rate_limit_wait(
    *,
    ctx: RunContext,
    operation_name: str,
    policy: LLMClientPolicy,
    in_flight_wait_ms: int,
    rate_wait_ms: int,
) -> None:
    if in_flight_wait_ms <= 0 and rate_wait_ms <= 0:
        return
    logger.info(
        log_event(
            ctx,
            role="service",
            event="llm_rate_limiter_wait",
            module=logger.name,
            fields={
                "operation": operation_name,
                "scope": policy.scope,
                "in_flight_wait_ms": in_flight_wait_ms,
                "rate_wait_ms": rate_wait_ms,
                "global_max_in_flight": policy.rate_limit_max_in_flight,
                "global_min_interval_ms": policy.rate_limit_min_interval_ms,
            },
        )
    )


def _with_rate_limit(
    *,
    ctx: RunContext,
    operation_name: str,
    policy: LLMClientPolicy,
    sleep_fn: Callable[[float], None],
    monotonic_fn: Callable[[], float],
    call: Callable[[], _T],
) -> _T:
    limiter = _get_rate_limiter_state(policy, operation_name)
    if limiter is None:
        return call()

    wait_started = monotonic_fn()
    limiter.semaphore.acquire()
    acquired_at = monotonic_fn()
    in_flight_wait_ms = int((acquired_at - wait_started) * 1000)
    rate_wait_ms = 0
    try:
        if limiter.min_interval_seconds > 0:
            with limiter.gate_lock:
                now = monotonic_fn()
                scheduled = max(now, limiter.next_allowed_monotonic)
                limiter.next_allowed_monotonic = (
                    scheduled + limiter.min_interval_seconds
                )
            sleep_for = max(0.0, scheduled - monotonic_fn())
            if sleep_for > 0:
                sleep_fn(sleep_for)
            rate_wait_ms = int((monotonic_fn() - acquired_at) * 1000)
        _log_rate_limit_wait(
            ctx=ctx,
            operation_name=operation_name,
            policy=policy,
            in_flight_wait_ms=in_flight_wait_ms,
            rate_wait_ms=rate_wait_ms,
        )
        return call()
    finally:
        limiter.semaphore.release()


def _before_circuit_call(
    *,
    ctx: RunContext,
    operation_name: str,
    policy: LLMClientPolicy,
    monotonic_fn: Callable[[], float],
) -> tuple[_CircuitBreakerState | None, bool]:
    if not _circuit_breaker_enabled(policy):
        return None, False
    state = _get_circuit_breaker_state(policy, operation_name)
    now = monotonic_fn()
    with _CIRCUIT_BREAKERS_LOCK:
        if state.opened_until_monotonic > now:
            remaining_seconds = max(0.0, state.opened_until_monotonic - now)
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="llm_circuit_short_circuit",
                    module=logger.name,
                    fields={
                        "operation": operation_name,
                        "scope": policy.scope,
                        "remaining_cooldown_seconds": round(remaining_seconds, 3),
                        "failure_threshold": policy.circuit_breaker_failure_threshold,
                    },
                )
            )
            raise AppError(
                code="llm_circuit_open",
                message="LLM circuit breaker is open",
                retryable=True,
                context={
                    "operation": operation_name,
                    "scope": policy.scope,
                    "remaining_cooldown_seconds": remaining_seconds,
                },
            )
        half_open_probe = False
        if state.opened_until_monotonic > 0.0 and state.opened_until_monotonic <= now:
            if state.half_open_in_flight:
                raise AppError(
                    code="llm_circuit_open",
                    message="LLM circuit breaker half-open probe already in progress",
                    retryable=True,
                    context={
                        "operation": operation_name,
                        "scope": policy.scope,
                    },
                )
            state.half_open_in_flight = True
            half_open_probe = True
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="llm_circuit_half_open",
                    module=logger.name,
                    fields={
                        "operation": operation_name,
                        "scope": policy.scope,
                        "failure_threshold": policy.circuit_breaker_failure_threshold,
                    },
                )
            )
        return state, half_open_probe


def _record_circuit_success(
    *,
    ctx: RunContext,
    operation_name: str,
    policy: LLMClientPolicy,
    state: _CircuitBreakerState | None,
    half_open_probe: bool,
) -> None:
    if state is None:
        return
    with _CIRCUIT_BREAKERS_LOCK:
        state.consecutive_failures = 0
        state.opened_until_monotonic = 0.0
        state.half_open_in_flight = False
    if half_open_probe:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="llm_circuit_closed",
                module=logger.name,
                fields={
                    "operation": operation_name,
                    "scope": policy.scope,
                    "reason": "half_open_success",
                },
            )
        )


def _record_circuit_failure(
    *,
    ctx: RunContext,
    operation_name: str,
    policy: LLMClientPolicy,
    state: _CircuitBreakerState | None,
    half_open_probe: bool,
    monotonic_fn: Callable[[], float],
    exc: Exception,
) -> None:
    if state is None or not _is_retryable_llm_error(exc):
        if state is not None and half_open_probe:
            with _CIRCUIT_BREAKERS_LOCK:
                state.half_open_in_flight = False
        return

    with _CIRCUIT_BREAKERS_LOCK:
        if half_open_probe:
            state.consecutive_failures = int(policy.circuit_breaker_failure_threshold)
        else:
            state.consecutive_failures += 1
        state.half_open_in_flight = False
        if state.consecutive_failures >= int(policy.circuit_breaker_failure_threshold):
            state.opened_until_monotonic = monotonic_fn() + float(
                policy.circuit_breaker_recovery_seconds
            )
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="llm_circuit_opened",
                    module=logger.name,
                    fields={
                        "operation": operation_name,
                        "scope": policy.scope,
                        "consecutive_failures": state.consecutive_failures,
                        "failure_threshold": policy.circuit_breaker_failure_threshold,
                        "recovery_seconds": policy.circuit_breaker_recovery_seconds,
                        "code": exc.code if isinstance(exc, AppError) else "",
                    },
                )
            )


def _execute_with_policy(
    *,
    ctx: RunContext,
    operation_name: str,
    policy: LLMClientPolicy,
    sleep_fn: Callable[[float], None],
    monotonic_fn: Callable[[], float],
    call: Callable[[], _T],
) -> _T:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="llm_call_start",
            module=logger.name,
            fields={
                "operation": operation_name,
                "scope": policy.scope,
                "retries": policy.retries,
                "base_delay_seconds": policy.base_delay_seconds,
                "backoff_step_seconds": policy.backoff_step_seconds,
                "jitter_seconds": policy.jitter_seconds,
                "rate_limit_max_in_flight": policy.rate_limit_max_in_flight,
                "rate_limit_min_interval_ms": policy.rate_limit_min_interval_ms,
                "circuit_breaker_failure_threshold": policy.circuit_breaker_failure_threshold,
                "circuit_breaker_recovery_seconds": policy.circuit_breaker_recovery_seconds,
            },
        )
    )
    retries = max(0, int(policy.retries))
    attempt = 0
    while True:
        state, half_open_probe = _before_circuit_call(
            ctx=ctx,
            operation_name=operation_name,
            policy=policy,
            monotonic_fn=monotonic_fn,
        )
        try:
            result = _with_rate_limit(
                ctx=ctx,
                operation_name=operation_name,
                policy=policy,
                sleep_fn=sleep_fn,
                monotonic_fn=monotonic_fn,
                call=call,
            )
        except Exception as exc:
            _record_circuit_failure(
                ctx=ctx,
                operation_name=operation_name,
                policy=policy,
                state=state,
                half_open_probe=half_open_probe,
                monotonic_fn=monotonic_fn,
                exc=exc,
            )
            retry_decision = _llm_retry_decision(exc)
            retryable = retry_decision.retryable
            if not retryable or attempt >= retries:
                logger.info(
                    log_event(
                        ctx,
                        role="service",
                        event="llm_call_failed",
                        module=logger.name,
                        fields={
                            "operation": operation_name,
                            "scope": policy.scope,
                            "attempt": attempt,
                            "retryable": retryable,
                            "retry_decision_code": retry_decision.reason_code,
                            "code": exc.code if isinstance(exc, AppError) else "",
                            "error": exc.message
                            if isinstance(exc, AppError)
                            else str(exc),
                        },
                    )
                )
                raise
            retry_delay = _retry_delay_seconds(policy, attempt)
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="llm_call_retry",
                    module=logger.name,
                    fields={
                        "operation": operation_name,
                        "scope": policy.scope,
                        "attempt": attempt + 1,
                        "delay_seconds": retry_delay,
                        "retry_decision_code": retry_decision.reason_code,
                        "code": exc.code if isinstance(exc, AppError) else "",
                        "error": exc.message if isinstance(exc, AppError) else str(exc),
                    },
                )
            )
            sleep_fn(retry_delay)
            attempt += 1
            continue
        _record_circuit_success(
            ctx=ctx,
            operation_name=operation_name,
            policy=policy,
            state=state,
            half_open_probe=half_open_probe,
        )
        logger.info(
            log_event(
                ctx,
                role="service",
                event="llm_call_complete",
                module=logger.name,
                fields={
                    "operation": operation_name,
                    "scope": policy.scope,
                    "attempt": attempt,
                },
            )
        )
        return result


class LLMServiceClient:
    def __init__(
        self,
        *,
        base_client: Any,
        policy: LLMClientPolicy,
        sleep_fn: Callable[[float], None] = time.sleep,
        monotonic_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        self._base_client = base_client
        self._policy = policy
        self._sleep_fn = sleep_fn
        self._monotonic_fn = monotonic_fn

    def _run(
        self,
        operation_name: str,
        ctx: RunContext,
        call: Callable[[], _T],
        *,
        request: Any | None = None,
    ) -> _T:
        if request is not None:
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="llm_policy_context",
                    module=logger.name,
                    fields={
                        "operation": operation_name,
                        "scope": self._policy.scope,
                        "provider_decision": "openai_primary",
                        "provider": "openai",
                        "model": str(getattr(request, "model", "") or ""),
                        "timeout_seconds": getattr(request, "timeout_seconds", None),
                        "semantic_cache_decision": (
                            "enabled"
                            if bool(getattr(request, "response_cache_enabled", False))
                            else "disabled"
                        ),
                        "semantic_cache_enabled": bool(
                            getattr(request, "response_cache_enabled", False)
                        ),
                        "semantic_cache_ttl_seconds": getattr(
                            request, "response_cache_ttl_seconds", None
                        ),
                        "budget_decision": "not_configured",
                        "budget_enforced": False,
                        "vector_store_id_present": bool(
                            str(getattr(request, "vector_store_id", "") or "").strip()
                        ),
                    },
                )
            )
        return _execute_with_policy(
            ctx=ctx,
            operation_name=operation_name,
            policy=self._policy,
            sleep_fn=self._sleep_fn,
            monotonic_fn=self._monotonic_fn,
            call=call,
        )

    def openai_chat_json(self, req: Any, ctx: RunContext) -> Any:
        return self._run(
            "openai_chat_json",
            ctx,
            lambda: self._base_client.openai_chat_json(req, ctx),
            request=req,
        )

    def openai_chat_json_with_images(self, req: Any, ctx: RunContext) -> Any:
        return self._run(
            "openai_chat_json_with_images",
            ctx,
            lambda: self._base_client.openai_chat_json_with_images(req, ctx),
            request=req,
        )

    def openai_ocr_pdf(self, req: Any, ctx: RunContext) -> Any:
        return self._run(
            "openai_ocr_pdf",
            ctx,
            lambda: self._base_client.openai_ocr_pdf(req, ctx),
            request=req,
        )

    def openai_respond_with_vector_store(self, req: Any, ctx: RunContext) -> Any:
        return self._run(
            "openai_respond_with_vector_store",
            ctx,
            lambda: self._base_client.openai_respond_with_vector_store(req, ctx),
            request=req,
        )


def build_openai_client(
    *,
    base_client: Any,
    policy: LLMClientPolicy,
    sleep_fn: Callable[[float], None] = time.sleep,
    monotonic_fn: Callable[[], float] = time.monotonic,
) -> LLMServiceClient:
    return LLMServiceClient(
        base_client=base_client,
        policy=policy,
        sleep_fn=sleep_fn,
        monotonic_fn=monotonic_fn,
    )


def default_openai_client_policy(
    *,
    scope: str,
) -> LLMClientPolicy:
    return LLMClientPolicy(schema_version="1.0", scope=scope)


def build_openai_client_from_callables(
    *,
    policy: LLMClientPolicy,
    openai_chat_json: Optional[Callable[[Any, RunContext], Any]] = None,
    openai_chat_json_with_images: Optional[Callable[[Any, RunContext], Any]] = None,
    openai_ocr_pdf: Optional[Callable[[Any, RunContext], Any]] = None,
    openai_respond_with_vector_store: Optional[Callable[[Any, RunContext], Any]] = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    monotonic_fn: Callable[[], float] = time.monotonic,
) -> LLMServiceClient:
    return build_openai_client(
        base_client=LLMProviderOperations(
            schema_version="1.0",
            openai_chat_json=openai_chat_json,
            openai_chat_json_with_images=openai_chat_json_with_images,
            openai_ocr_pdf=openai_ocr_pdf,
            openai_respond_with_vector_store=openai_respond_with_vector_store,
        ),
        policy=policy,
        sleep_fn=sleep_fn,
        monotonic_fn=monotonic_fn,
    )


def build_openai_client_for_settings(
    settings: Any,
    *,
    scope: str,
    rate_limit_max_in_flight: Optional[int] = None,
    rate_limit_min_interval_ms: int = 0,
    base_client: Any | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    monotonic_fn: Callable[[], float] = time.monotonic,
) -> LLMServiceClient:
    return build_openai_client(
        base_client=base_client or _openai_boundary(),
        policy=openai_client_policy_from_settings(
            settings,
            scope=scope,
            rate_limit_max_in_flight=rate_limit_max_in_flight,
            rate_limit_min_interval_ms=rate_limit_min_interval_ms,
        ),
        sleep_fn=sleep_fn,
        monotonic_fn=monotonic_fn,
    )


def openai_client_policy_from_settings(
    settings: Any,
    *,
    scope: str,
    rate_limit_max_in_flight: Optional[int] = None,
    rate_limit_min_interval_ms: int = 0,
) -> LLMClientPolicy:
    return LLMClientPolicy(
        schema_version="1.0",
        scope=scope,
        retries=max(0, int(getattr(settings, "llm_retry_retries", 1))),
        base_delay_seconds=max(
            0.0, float(getattr(settings, "llm_retry_base_delay_seconds", 1.0))
        ),
        backoff_step_seconds=max(
            0.0, float(getattr(settings, "llm_retry_backoff_step_seconds", 1.0))
        ),
        jitter_seconds=max(
            0.0, float(getattr(settings, "llm_retry_jitter_seconds", 0.25))
        ),
        rate_limit_max_in_flight=rate_limit_max_in_flight,
        rate_limit_min_interval_ms=max(0, int(rate_limit_min_interval_ms)),
        circuit_breaker_failure_threshold=max(
            0, int(getattr(settings, "llm_circuit_breaker_failure_threshold", 3))
        ),
        circuit_breaker_recovery_seconds=max(
            0.0,
            float(getattr(settings, "llm_circuit_breaker_recovery_seconds", 30.0)),
        ),
    )


def openai_chat_json(req: Any, ctx: RunContext) -> Any:
    return _openai_boundary().openai_chat_json(req, ctx)


def openai_chat_json_with_images(req: Any, ctx: RunContext) -> Any:
    return _openai_boundary().openai_chat_json_with_images(req, ctx)


def openai_ocr_pdf(req: Any, ctx: RunContext) -> Any:
    return _openai_boundary().openai_ocr_pdf(req, ctx)


def openai_respond_with_vector_store(req: Any, ctx: RunContext) -> Any:
    return _openai_boundary().openai_respond_with_vector_store(req, ctx)


def openai_vector_store_create(req: Any, ctx: RunContext) -> Any:
    return _openai_boundary().openai_vector_store_create(req, ctx)


def openai_vector_store_upload_file(req: Any, ctx: RunContext) -> Any:
    return _openai_boundary().openai_vector_store_upload_file(req, ctx)


def openai_vector_store_attach_file(req: Any, ctx: RunContext) -> Any:
    return _openai_boundary().openai_vector_store_attach_file(req, ctx)


def openai_vector_store_status(req: Any, ctx: RunContext) -> Any:
    return _openai_boundary().openai_vector_store_status(req, ctx)


def openai_vector_store_delete(req: Any, ctx: RunContext) -> Any:
    return _openai_boundary().openai_vector_store_delete(req, ctx)


def openai_vector_store_update_metadata(req: Any, ctx: RunContext) -> Any:
    return _openai_boundary().openai_vector_store_update_metadata(req, ctx)
