from __future__ import annotations

import json
import logging
import time
from dataclasses import FrozenInstanceError
from types import SimpleNamespace

import pytest

from src.contracts.llm import LLMClientPolicy
from src.contracts.retry_decision import RetryDecision
from src.contracts.run_budget import RunBudget
from src.orchestrators import retry_orchestrator
from src.orchestrators.retry_orchestrator import (
    RetryPolicy,
    resolve_retry_decision,
    run_with_retry,
)
from src.services import llm_service
from src.utils.errors import AppError


def _app_error(
    code: str,
    *,
    retryable: bool,
    context: dict[str, object] | None = None,
) -> AppError:
    return AppError(
        code=code,
        message=code,
        retryable=retryable,
        severity="error",
        context=context,
    )


def test_retry_decision_contract_is_complete(assert_no_defaulted_required_fields):
    decision = RetryDecision(
        schema_version="1.0",
        step_name="model_call",
        action="retry",
        attempt=1,
        max_attempts=3,
        delay_seconds=1.5,
        reason="retryable_error",
        next_action="retry_after_delay",
        error_code="openai_request_failed",
        error_retryable=True,
        error_severity="error",
    )

    assert_no_defaulted_required_fields(decision)
    assert decision.action == "retry"
    assert decision.next_action == "retry_after_delay"


def test_retry_policy_is_immutable():
    policy = RetryPolicy(retries=1)

    with pytest.raises(FrozenInstanceError):
        policy.retries = 2  # type: ignore[misc]


@pytest.mark.parametrize(
    ("step_name", "error", "attempt", "policy", "expected"),
    [
        (
            "provider_call",
            _app_error("openai_request_failed", retryable=True),
            0,
            RetryPolicy(retries=2, base_delay_seconds=1.0, backoff_step_seconds=1.0),
            {
                "action": "retry",
                "delay_seconds": 1.0,
                "reason": "retryable_error",
                "next_action": "retry_after_delay",
            },
        ),
        (
            "validation_repair",
            _app_error("validation_repair_failed", retryable=True),
            1,
            RetryPolicy(retries=2, base_delay_seconds=0.5, backoff_step_seconds=0.25),
            {
                "action": "retry",
                "delay_seconds": 0.75,
                "reason": "retryable_error",
                "next_action": "retry_after_delay",
            },
        ),
        (
            "state_write",
            _app_error("sqlite_database_locked", retryable=True),
            0,
            RetryPolicy(retries=1, base_delay_seconds=0.2, backoff_step_seconds=0.0),
            {
                "action": "retry",
                "delay_seconds": 0.2,
                "reason": "retryable_error",
                "next_action": "retry_after_delay",
            },
        ),
        (
            "drive_preflight",
            _app_error("drive_oauth_token_missing", retryable=False),
            0,
            RetryPolicy(retries=2),
            {
                "action": "user_action_required",
                "delay_seconds": 0.0,
                "reason": "missing_credential",
                "next_action": "provide_or_refresh_credentials",
            },
        ),
        (
            "provider_call",
            _app_error("openai_rate_limit", retryable=True),
            2,
            RetryPolicy(retries=2),
            {
                "action": "abort",
                "delay_seconds": 0.0,
                "reason": "retry_attempts_exhausted",
                "next_action": "surface_failure",
            },
        ),
        (
            "contract_validation",
            _app_error("contract_validation_failed", retryable=False),
            0,
            RetryPolicy(retries=2),
            {
                "action": "abort",
                "delay_seconds": 0.0,
                "reason": "non_retryable_error",
                "next_action": "surface_failure",
            },
        ),
        (
            "quota_guard",
            _app_error(
                "provider_quota_exhausted",
                retryable=True,
                context={
                    "retry_decision": "defer",
                    "retry_after_seconds": 120,
                    "next_action": "resume_after_quota_window",
                },
            ),
            0,
            RetryPolicy(retries=2),
            {
                "action": "defer",
                "delay_seconds": 120.0,
                "reason": "defer_requested",
                "next_action": "resume_after_quota_window",
            },
        ),
    ],
)
def test_resolve_retry_decision_classifies_common_failures(
    step_name: str,
    error: AppError,
    attempt: int,
    policy: RetryPolicy,
    expected: dict[str, object],
):
    decision = resolve_retry_decision(
        step_name=step_name,
        exc=error,
        attempt=attempt,
        policy=policy,
    )

    assert decision.action == expected["action"]
    assert decision.delay_seconds == expected["delay_seconds"]
    assert decision.reason == expected["reason"]
    assert decision.next_action == expected["next_action"]
    assert decision.max_attempts == int(policy.retries) + 1
    assert decision.error_code == error.code
    assert decision.error_retryable is error.retryable


def test_resolve_retry_decision_treats_generic_exceptions_as_non_retryable():
    decision = resolve_retry_decision(
        step_name="generic_failure",
        exc=ValueError("bad value"),
        attempt=0,
        policy=RetryPolicy(retries=1),
    )

    assert decision.action == "abort"
    assert decision.reason == "non_retryable_error"
    assert decision.error_code == "ValueError"
    assert decision.error_retryable is False


def test_retry_waits_for_open_circuit_cooldown_before_next_attempt(run_context):
    clock = [0.0]
    calls: list[float] = []

    def operation() -> str:
        calls.append(clock[0])
        if clock[0] < 22.0:
            raise _app_error(
                "llm_circuit_open",
                retryable=True,
                context={"remaining_cooldown_seconds": 22.0 - clock[0]},
            )
        return "recovered"

    def sleep(seconds: float) -> None:
        clock[0] += seconds

    result = run_with_retry(
        step_name="report_pipeline",
        operation=operation,
        ctx=run_context,
        logger=logging.getLogger("market_lense.test_retry_decision_contract.cooldown"),
        module_name="market_lense.test_retry_decision_contract",
        policy=RetryPolicy(retries=2, base_delay_seconds=1.0),
        retry_event="report_pipeline_retry",
        sleep_fn=sleep,
    )

    assert result == "recovered"
    assert calls == [0.0, 22.0]


@pytest.mark.parametrize(
    "cooldown", [None, "invalid", -1, float("inf"), float("nan"), 1e300, 10**1000]
)
def test_invalid_circuit_cooldown_keeps_bounded_policy_delay(cooldown):
    decision = resolve_retry_decision(
        step_name="report_pipeline",
        exc=_app_error(
            "llm_circuit_open",
            retryable=True,
            context={"remaining_cooldown_seconds": cooldown},
        ),
        attempt=0,
        policy=RetryPolicy(retries=1, base_delay_seconds=2.0),
    )
    assert decision.action == "retry"
    assert decision.delay_seconds == 2.0


def test_exhausted_circuit_retry_does_not_sleep():
    decision = resolve_retry_decision(
        step_name="report_pipeline",
        exc=_app_error(
            "llm_circuit_open",
            retryable=True,
            context={"remaining_cooldown_seconds": 22.0},
        ),
        attempt=1,
        policy=RetryPolicy(retries=1),
    )
    assert decision.action == "abort"
    assert decision.delay_seconds == 0.0


def test_circuit_cooldown_cannot_exceed_retry_runtime_budget(tmp_path, run_context):
    sleeps: list[float] = []
    budget = RunBudget(
        schema_version="1.0",
        run_id=run_context.run_id,
        publisher_name="",
        usage_db_path=str(tmp_path / "usage.sqlite"),
        max_runtime_seconds=10,
    )

    def operation() -> str:
        raise _app_error(
            "llm_circuit_open",
            retryable=True,
            context={"remaining_cooldown_seconds": 22.0},
        )

    with pytest.raises(AppError) as exc_info:
        run_with_retry(
            step_name="report_pipeline",
            operation=operation,
            ctx=run_context,
            logger=logging.getLogger(
                "market_lense.test_retry_decision_contract.budget"
            ),
            module_name="market_lense.test_retry_decision_contract",
            policy=RetryPolicy(retries=1, budget=budget),
            retry_event="report_pipeline_retry",
            sleep_fn=sleeps.append,
        )
    assert exc_info.value.code.startswith("retry_budget_")
    assert sleeps == []


def test_repeated_circuit_waits_accumulate_runtime_budget(tmp_path, run_context):
    sleeps: list[float] = []
    budget = RunBudget(
        schema_version="1.0",
        run_id=run_context.run_id,
        publisher_name="",
        usage_db_path=str(tmp_path / "usage.sqlite"),
        max_runtime_seconds=3,
    )

    def operation() -> str:
        raise _app_error(
            "llm_circuit_open",
            retryable=True,
            context={"remaining_cooldown_seconds": 1.05},
        )

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        time.sleep(seconds)

    with pytest.raises(AppError) as exc_info:
        run_with_retry(
            step_name="report_pipeline",
            operation=operation,
            ctx=run_context,
            logger=logging.getLogger("market_lense.test_retry_decision_contract.total"),
            module_name="market_lense.test_retry_decision_contract",
            policy=RetryPolicy(retries=2, base_delay_seconds=0.0, budget=budget),
            retry_event="report_pipeline_retry",
            sleep_fn=sleep,
        )
    assert exc_info.value.code.startswith("retry_budget_")
    assert sleeps == [1.05]


def test_interrupted_wait_preserves_error_and_accounts_elapsed_budget(
    tmp_path, run_context
):
    budget = RunBudget(
        schema_version="1.0",
        run_id=run_context.run_id,
        publisher_name="",
        usage_db_path=str(tmp_path / "usage.sqlite"),
        max_runtime_seconds=2,
    )

    def open_circuit(cooldown: float) -> str:
        raise _app_error(
            "llm_circuit_open",
            retryable=True,
            context={"remaining_cooldown_seconds": cooldown},
        )

    def interrupted_sleep(_: float) -> None:
        time.sleep(0.02)
        raise RuntimeError("interrupted wait")

    common = {
        "ctx": run_context,
        "logger": logging.getLogger(
            "market_lense.test_retry_decision_contract.interrupted"
        ),
        "module_name": "market_lense.test_retry_decision_contract",
        "policy": RetryPolicy(retries=1, base_delay_seconds=0.0, budget=budget),
        "retry_event": "report_pipeline_retry",
    }
    with pytest.raises(RuntimeError, match="interrupted wait"):
        run_with_retry(
            step_name="first",
            operation=lambda: open_circuit(0.01),
            sleep_fn=interrupted_sleep,
            **common,
        )
    sleeps: list[float] = []
    with pytest.raises(AppError) as exc_info:
        run_with_retry(
            step_name="second",
            operation=lambda: open_circuit(1.05),
            sleep_fn=sleeps.append,
            **common,
        )
    assert exc_info.value.code.startswith("retry_budget_")
    assert sleeps == []


def test_retry_wait_cannot_outlive_its_budget_reservation(tmp_path, run_context):
    budget = RunBudget(
        schema_version="1.0",
        run_id=run_context.run_id,
        publisher_name="",
        usage_db_path=str(tmp_path / "usage.sqlite"),
        reservation_ttl_seconds=30,
    )
    sleeps: list[float] = []
    with pytest.raises(AppError) as exc_info:
        run_with_retry(
            step_name="report_pipeline",
            operation=lambda: (_ for _ in ()).throw(
                _app_error(
                    "llm_circuit_open",
                    retryable=True,
                    context={"remaining_cooldown_seconds": 31.0},
                )
            ),
            ctx=run_context,
            logger=logging.getLogger(__name__),
            module_name=__name__,
            policy=RetryPolicy(retries=1, budget=budget),
            retry_event="report_pipeline_retry",
            sleep_fn=sleeps.append,
        )
    assert exc_info.value.code == "retry_wait_reservation_window_exceeded"
    assert sleeps == []


def test_disabled_retry_budget_does_not_impose_reservation_window(
    tmp_path, run_context
):
    budget = RunBudget(
        schema_version="1.0",
        run_id=run_context.run_id,
        publisher_name="",
        usage_db_path=str(tmp_path / "usage.sqlite"),
        reservation_ttl_seconds=1,
        enabled_effect_kinds=("llm_provider",),
    )
    calls = [0]
    sleeps: list[float] = []

    def operation() -> str:
        calls[0] += 1
        if calls[0] == 1:
            raise _app_error(
                "llm_circuit_open",
                retryable=True,
                context={"remaining_cooldown_seconds": 31.0},
            )
        return "ok"

    result = run_with_retry(
        step_name="report_pipeline",
        operation=operation,
        ctx=run_context,
        logger=logging.getLogger(__name__),
        module_name=__name__,
        policy=RetryPolicy(retries=1, budget=budget),
        retry_event="report_pipeline_retry",
        sleep_fn=sleeps.append,
    )
    assert result == "ok"
    assert sleeps == [31.0]


def test_reused_retry_reservation_cannot_silently_repeat_wait(tmp_path, run_context):
    budget = RunBudget(
        schema_version="1.0",
        run_id=run_context.run_id,
        publisher_name="",
        usage_db_path=str(tmp_path / "usage.sqlite"),
    )
    sleeps: list[float] = []

    def execute():
        calls = [0]

        def operation():
            calls[0] += 1
            if calls[0] == 1:
                raise _app_error(
                    "llm_circuit_open",
                    retryable=True,
                    context={"remaining_cooldown_seconds": 1.0},
                )
            return "ok"

        return run_with_retry(
            step_name="report_pipeline",
            operation=operation,
            ctx=run_context,
            logger=logging.getLogger(__name__),
            module_name=__name__,
            policy=RetryPolicy(retries=1, budget=budget),
            retry_event="report_pipeline_retry",
            sleep_fn=sleeps.append,
        )

    assert execute() == "ok"
    with pytest.raises(AppError) as exc_info:
        execute()
    assert exc_info.value.code == "retry_wait_reservation_conflict"
    assert sleeps == [1.0]


def test_retry_allows_real_circuit_to_half_open(run_context):
    now = [50.0]
    provider_calls: list[float] = []

    class RecoveringProvider:
        def openai_chat_json(self, request, ctx):
            provider_calls.append(now[0])
            if len(provider_calls) == 1:
                raise _app_error("openai_response_failed", retryable=True)
            return "recovered"

    client = llm_service.build_openai_client(
        base_client=RecoveringProvider(),
        policy=LLMClientPolicy(
            schema_version="1.0",
            scope="test-retry-cooldown-integration",
            retries=0,
            base_delay_seconds=0.0,
            backoff_step_seconds=0.0,
            jitter_seconds=0.0,
            circuit_breaker_failure_threshold=1,
            circuit_breaker_recovery_seconds=30.0,
        ),
        monotonic_fn=lambda: now[0],
        sleep_fn=lambda _: None,
    )
    request = SimpleNamespace(model="gpt-6-luna")
    with pytest.raises(AppError, match="openai_response_failed"):
        client.openai_chat_json(request, run_context)

    def sleep(seconds: float) -> None:
        now[0] += seconds

    result = run_with_retry(
        step_name="report_pipeline",
        operation=lambda: client.openai_chat_json(request, run_context),
        ctx=run_context,
        logger=logging.getLogger("market_lense.test_retry_decision_contract.circuit"),
        module_name="market_lense.test_retry_decision_contract",
        policy=RetryPolicy(retries=1, base_delay_seconds=1.0),
        retry_event="report_pipeline_retry",
        sleep_fn=sleep,
    )
    assert result == "recovered"
    assert provider_calls == [50.0, 80.0]


def test_run_with_retry_ignores_negative_jitter(
    run_context,
    external_boundary_mocks_only,
):
    attempts = {"count": 0}
    sleeps: list[float] = []

    external_boundary_mocks_only.setattr(
        retry_orchestrator.random,
        "uniform",
        lambda _a, _b: 9.0,
    )

    def operation() -> str:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise _app_error("sqlite_database_locked", retryable=True)
        return "ok"

    result = run_with_retry(
        step_name="state_write",
        operation=operation,
        ctx=run_context,
        logger=logging.getLogger("market_lense.test_retry_decision_contract.jitter"),
        module_name="market_lense.test_retry_decision_contract",
        policy=RetryPolicy(
            retries=1,
            base_delay_seconds=1.0,
            backoff_step_seconds=0.0,
            jitter_seconds=-1.0,
        ),
        retry_event="state_write_retry",
        sleep_fn=sleeps.append,
    )

    assert result == "ok"
    assert sleeps == [1.0]


def test_run_with_retry_logs_typed_decision_fields_and_preserves_attempts(
    run_context,
    caplog,
    assert_logs_have_required_fields,
):
    attempts = {"count": 0}
    sleeps: list[float] = []
    error = _app_error("openai_request_failed", retryable=True)

    def operation() -> str:
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise error
        return "ok"

    logger = logging.getLogger("market_lense.test_retry_decision_contract")
    caplog.set_level(logging.INFO, logger=logger.name)

    result = run_with_retry(
        step_name="provider_call",
        operation=operation,
        ctx=run_context,
        logger=logger,
        module_name="market_lense.test_retry_decision_contract",
        policy=RetryPolicy(
            retries=2,
            base_delay_seconds=1.0,
            backoff_step_seconds=1.0,
            jitter_seconds=0.0,
        ),
        retry_event="provider_retry",
        sleep_fn=sleeps.append,
    )

    assert result == "ok"
    assert attempts["count"] == 3
    assert sleeps == [1.0, 2.0]
    assert_logs_have_required_fields(caplog.records)
    events = [json.loads(record.message) for record in caplog.records]
    retry_fields = [event["fields"] for event in events]
    assert [fields["decision"] for fields in retry_fields] == ["retry", "retry"]
    assert [fields["reason"] for fields in retry_fields] == [
        "retryable_error",
        "retryable_error",
    ]
    assert [fields["delay_seconds"] for fields in retry_fields] == [1.0, 2.0]
    assert [fields["attempt"] for fields in retry_fields] == [1, 2]
    assert [fields["decision_attempt"] for fields in retry_fields] == [1, 2]
    assert [fields["max_attempts"] for fields in retry_fields] == [3, 3]
    assert [fields["error_code"] for fields in retry_fields] == [
        "openai_request_failed",
        "openai_request_failed",
    ]


def test_run_with_retry_logs_non_retryable_contract_failure_decision(
    run_context,
    caplog,
    assert_logs_have_required_fields,
):
    error = _app_error("contract_validation_failed", retryable=False)

    logger = logging.getLogger("market_lense.test_retry_decision_contract.failure")
    caplog.set_level(logging.INFO, logger=logger.name)

    with pytest.raises(AppError):
        run_with_retry(
            step_name="contract_validation",
            operation=lambda: (_ for _ in ()).throw(error),
            ctx=run_context,
            logger=logger,
            module_name="market_lense.test_retry_decision_contract",
            policy=RetryPolicy(retries=2),
            retry_event="unused_retry",
            failure_event="contract_step_failed",
            sleep_fn=lambda _seconds: None,
        )

    assert_logs_have_required_fields(caplog.records)
    events = [json.loads(record.message) for record in caplog.records]
    assert len(events) == 1
    fields = events[0]["fields"]
    assert fields["decision"] == "abort"
    assert fields["reason"] == "non_retryable_error"
    assert fields["next_action"] == "surface_failure"
    assert fields["attempt"] == 0
    assert fields["decision_attempt"] == 1
    assert fields["max_attempts"] == 3
    assert fields["error_code"] == "contract_validation_failed"
    assert fields["error_retryable"] is False
