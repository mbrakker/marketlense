from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, TypeVar

from src.contracts.retry_decision import RetryDecision, RetryDecisionAction
from src.contracts.run_context import RunContext
from src.utils.errors import AppError
from src.utils.logging import log_event

T = TypeVar("T")

RetryablePredicate = Callable[[Exception], bool]
RetryFieldsBuilder = Callable[[Exception, int], dict[str, Any]]
FailureFieldsBuilder = Callable[[Exception, int, bool], dict[str, Any]]
SleepFn = Callable[[float], None]


@dataclass(frozen=True)
class RetryPolicy:
    retries: int = field(
        default=0, metadata={"doc": "Maximum retry count after the initial attempt."}
    )
    base_delay_seconds: float = field(
        default=1.0, metadata={"doc": "Base delay before the first retry."}
    )
    backoff_step_seconds: float = field(
        default=1.0, metadata={"doc": "Additional delay added per retry attempt."}
    )
    jitter_seconds: float = field(
        default=0.0,
        metadata={"doc": "Optional random jitter added to each retry delay."},
    )
    delay_schedule_seconds: tuple[float, ...] = field(
        default_factory=tuple,
        metadata={
            "doc": "Optional explicit retry delays by zero-based failed attempt."
        },
    )


def is_retryable_app_error(exc: Exception) -> bool:
    return isinstance(exc, AppError) and bool(exc.retryable)


def _default_retry_fields(
    step_name: str, exc: Exception, attempt: int
) -> dict[str, Any]:
    fields: dict[str, Any] = {"step": step_name, "attempt": attempt + 1}
    if isinstance(exc, AppError):
        fields["code"] = exc.code
    else:
        fields["error"] = str(exc)
    return fields


def _default_failure_fields(
    step_name: str, exc: Exception, attempt: int, retryable: bool
) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "step": step_name,
        "attempt": attempt,
        "retryable": retryable,
    }
    if isinstance(exc, AppError):
        fields["code"] = exc.code
        fields["error"] = exc.message
    else:
        fields["error"] = str(exc)
    return fields


def _retry_delay_seconds(policy: RetryPolicy, attempt: int) -> float:
    if policy.delay_schedule_seconds:
        schedule = tuple(float(item) for item in policy.delay_schedule_seconds)
        index = min(max(0, int(attempt)), len(schedule) - 1)
        return max(0.0, schedule[index])
    base = float(policy.base_delay_seconds) + float(
        policy.backoff_step_seconds
    ) * float(attempt)
    if policy.jitter_seconds > 0:
        base += random.uniform(0.0, float(policy.jitter_seconds))
    return max(0.0, base)


def _error_code(exc: Exception) -> str:
    if isinstance(exc, AppError):
        return str(exc.code)
    return exc.__class__.__name__


def _error_retryable(exc: Exception, retryable: bool | None = None) -> bool:
    if retryable is not None:
        return bool(retryable)
    return bool(getattr(exc, "retryable", False))


def _error_severity(exc: Exception) -> str:
    if isinstance(exc, AppError):
        return str(exc.severity or "error")
    return "error"


def _context_value(exc: Exception, key: str) -> Any:
    if not isinstance(exc, AppError):
        return None
    return exc.context.get(key)


def _is_missing_credential_error(exc: Exception) -> bool:
    code = _error_code(exc).lower()
    credential_tokens = (
        "credential",
        "credentials",
        "oauth_token_missing",
        "token_missing",
        "api_key_missing",
        "app_password_missing",
        "scope_insufficient",
        "no_write_access",
    )
    return any(token in code for token in credential_tokens)


def _defer_delay_seconds(exc: Exception, policy: RetryPolicy, attempt: int) -> float:
    raw_delay = _context_value(exc, "retry_after_seconds")
    if raw_delay is None:
        raw_delay = _context_value(exc, "defer_seconds")
    try:
        if raw_delay is not None:
            return max(0.0, float(raw_delay))
    except (TypeError, ValueError):
        return _retry_delay_seconds(policy, attempt)
    return _retry_delay_seconds(policy, attempt)


def resolve_retry_decision(
    *,
    step_name: str,
    exc: Exception,
    attempt: int,
    policy: RetryPolicy,
    retryable: bool | None = None,
) -> RetryDecision:
    retries = max(0, int(policy.retries))
    max_attempts = retries + 1
    attempt_number = max(1, int(attempt) + 1)
    error_retryable = _error_retryable(exc, retryable)
    requested_decision = (
        str(_context_value(exc, "retry_decision") or "").strip().lower()
    )

    action: RetryDecisionAction
    if _is_missing_credential_error(exc):
        action = "user_action_required"
        reason = "missing_credential"
        next_action = "provide_or_refresh_credentials"
        delay_seconds = 0.0
    elif requested_decision == "defer":
        action = "defer"
        reason = "defer_requested"
        next_action = str(
            _context_value(exc, "next_action") or "retry_after_defer_window"
        )
        delay_seconds = _defer_delay_seconds(exc, policy, attempt)
    elif not error_retryable:
        action = "abort"
        reason = "non_retryable_error"
        next_action = "surface_failure"
        delay_seconds = 0.0
    elif attempt >= retries:
        action = "abort"
        reason = "retry_attempts_exhausted"
        next_action = "surface_failure"
        delay_seconds = 0.0
    else:
        action = "retry"
        reason = "retryable_error"
        next_action = "retry_after_delay"
        delay_seconds = _retry_delay_seconds(policy, attempt)

    return RetryDecision(
        schema_version="1.0",
        step_name=step_name,
        action=action,
        attempt=attempt_number,
        max_attempts=max_attempts,
        delay_seconds=delay_seconds,
        reason=reason,
        next_action=next_action,
        error_code=_error_code(exc),
        error_retryable=error_retryable,
        error_severity=_error_severity(exc),
    )


def _decision_fields(decision: RetryDecision) -> dict[str, Any]:
    return {
        "step": decision.step_name,
        "decision_attempt": decision.attempt,
        "max_attempts": decision.max_attempts,
        "delay_seconds": decision.delay_seconds,
        "decision": decision.action,
        "reason": decision.reason,
        "next_action": decision.next_action,
        "error_code": decision.error_code,
        "error_retryable": decision.error_retryable,
        "error_severity": decision.error_severity,
    }


def run_with_retry(
    *,
    step_name: str,
    operation: Callable[[], T],
    ctx: RunContext,
    logger: logging.Logger,
    module_name: str,
    policy: RetryPolicy,
    retry_event: str,
    retry_fields_builder: Optional[RetryFieldsBuilder] = None,
    failure_event: Optional[str] = None,
    failure_fields_builder: Optional[FailureFieldsBuilder] = None,
    is_retryable: RetryablePredicate = is_retryable_app_error,
    sleep_fn: SleepFn = time.sleep,
) -> T:
    attempt = 0
    while True:
        try:
            return operation()
        except Exception as exc:
            retryable = bool(is_retryable(exc))
            decision = resolve_retry_decision(
                step_name=step_name,
                exc=exc,
                attempt=attempt,
                policy=policy,
                retryable=retryable,
            )
            if decision.action != "retry":
                if failure_event:
                    base_fields = (
                        failure_fields_builder(exc, attempt, retryable)
                        if failure_fields_builder
                        else _default_failure_fields(step_name, exc, attempt, retryable)
                    )
                    fields = {**base_fields, **_decision_fields(decision)}
                    logger.info(
                        log_event(
                            ctx,
                            role="orchestrator",
                            event=failure_event,
                            module=module_name,
                            fields=fields,
                        )
                    )
                raise
            base_fields = (
                retry_fields_builder(exc, attempt)
                if retry_fields_builder
                else _default_retry_fields(step_name, exc, attempt)
            )
            fields = {**base_fields, **_decision_fields(decision)}
            logger.info(
                log_event(
                    ctx,
                    role="orchestrator",
                    event=retry_event,
                    module=module_name,
                    fields=fields,
                )
            )
            sleep_fn(decision.delay_seconds)
            attempt += 1


def run_step_with_default_policy(
    *,
    step_name: str,
    operation: Callable[[], T],
    ctx: RunContext,
    logger: logging.Logger,
    module_name: str,
    retries: int,
    include_error_text: bool = False,
    sleep_fn: SleepFn = time.sleep,
) -> T:
    return run_with_retry(
        step_name=step_name,
        operation=operation,
        ctx=ctx,
        logger=logger,
        module_name=module_name,
        policy=RetryPolicy(
            retries=retries,
            base_delay_seconds=1.0,
            backoff_step_seconds=1.0,
            jitter_seconds=0.25,
        ),
        retry_event="step_retry",
        retry_fields_builder=lambda exc, attempt: {
            "step": step_name,
            "attempt": attempt + 1,
            "code": exc.code if isinstance(exc, AppError) else "",
            **({"error": str(exc)} if include_error_text else {}),
        },
        is_retryable=lambda exc: isinstance(exc, AppError) and exc.retryable,
        sleep_fn=sleep_fn,
    )
