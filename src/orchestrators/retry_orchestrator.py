from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, TypeVar

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
    retries: int = field(default=0, metadata={"doc": "Maximum retry count after the initial attempt."})
    base_delay_seconds: float = field(default=1.0, metadata={"doc": "Base delay before the first retry."})
    backoff_step_seconds: float = field(default=1.0, metadata={"doc": "Additional delay added per retry attempt."})
    jitter_seconds: float = field(default=0.0, metadata={"doc": "Optional random jitter added to each retry delay."})


def is_retryable_app_error(exc: Exception) -> bool:
    return isinstance(exc, AppError) and bool(exc.retryable)


def _default_retry_fields(step_name: str, exc: Exception, attempt: int) -> dict[str, Any]:
    fields: dict[str, Any] = {"step": step_name, "attempt": attempt + 1}
    if isinstance(exc, AppError):
        fields["code"] = exc.code
    else:
        fields["error"] = str(exc)
    return fields


def _default_failure_fields(step_name: str, exc: Exception, attempt: int, retryable: bool) -> dict[str, Any]:
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
    base = float(policy.base_delay_seconds) + float(policy.backoff_step_seconds) * float(attempt)
    if policy.jitter_seconds > 0:
        base += random.uniform(0.0, float(policy.jitter_seconds))
    return max(0.0, base)


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
    retries = max(0, int(policy.retries))
    attempt = 0
    while True:
        try:
            return operation()
        except Exception as exc:
            retryable = bool(is_retryable(exc))
            if not retryable or attempt >= retries:
                if failure_event:
                    fields = (
                        failure_fields_builder(exc, attempt, retryable)
                        if failure_fields_builder
                        else _default_failure_fields(step_name, exc, attempt, retryable)
                    )
                    logger.info(log_event(
                        ctx,
                        role="orchestrator",
                        event=failure_event,
                        module=module_name,
                        fields=fields,
                    ))
                raise
            fields = (
                retry_fields_builder(exc, attempt)
                if retry_fields_builder
                else _default_retry_fields(step_name, exc, attempt)
            )
            logger.info(log_event(
                ctx,
                role="orchestrator",
                event=retry_event,
                module=module_name,
                fields=fields,
            ))
            sleep_fn(_retry_delay_seconds(policy, attempt))
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
        policy=RetryPolicy(retries=retries, base_delay_seconds=1.0, backoff_step_seconds=1.0, jitter_seconds=0.25),
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
