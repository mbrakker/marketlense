from __future__ import annotations

import time
from typing import Any, Callable, Optional, TypeVar

from src.contracts.llm import LLMClientPolicy, LLMProviderOperations
from src.contracts.run_context import RunContext
from src.services._llm_service import openai_chat, openai_responses
from src.services._llm_service.policy import _execute_with_policy, logger
from src.utils.logging import log_event

_T = TypeVar("_T")


def _default_provider_operations() -> LLMProviderOperations:
    return LLMProviderOperations(
        schema_version="1.0",
        openai_chat_json=openai_chat.openai_chat_json,
        openai_chat_json_with_images=openai_chat.openai_chat_json_with_images,
        openai_ocr_pdf=openai_responses.openai_ocr_pdf,
        openai_respond_with_vector_store=(
            openai_responses.openai_respond_with_vector_store
        ),
    )


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


def build_client(
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


def default_client_policy(*, scope: str) -> LLMClientPolicy:
    return LLMClientPolicy(schema_version="1.0", scope=scope)


def build_client_from_callables(
    *,
    policy: LLMClientPolicy,
    openai_chat_json: Optional[Callable[[Any, RunContext], Any]] = None,
    openai_chat_json_with_images: Optional[Callable[[Any, RunContext], Any]] = None,
    openai_ocr_pdf: Optional[Callable[[Any, RunContext], Any]] = None,
    openai_respond_with_vector_store: Optional[Callable[[Any, RunContext], Any]] = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    monotonic_fn: Callable[[], float] = time.monotonic,
) -> LLMServiceClient:
    return build_client(
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


def build_client_for_settings(
    settings: Any,
    *,
    scope: str,
    rate_limit_max_in_flight: Optional[int] = None,
    rate_limit_min_interval_ms: int = 0,
    base_client: Any | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    monotonic_fn: Callable[[], float] = time.monotonic,
) -> LLMServiceClient:
    return build_client(
        base_client=base_client or _default_provider_operations(),
        policy=client_policy_from_settings(
            settings,
            scope=scope,
            rate_limit_max_in_flight=rate_limit_max_in_flight,
            rate_limit_min_interval_ms=rate_limit_min_interval_ms,
        ),
        sleep_fn=sleep_fn,
        monotonic_fn=monotonic_fn,
    )


def client_policy_from_settings(
    settings: Any,
    *,
    scope: str,
    rate_limit_max_in_flight: Optional[int] = None,
    rate_limit_min_interval_ms: int = 0,
) -> LLMClientPolicy:
    return LLMClientPolicy(
        schema_version="1.0",
        scope=scope,
        retries=0,
        base_delay_seconds=0.0,
        backoff_step_seconds=0.0,
        jitter_seconds=0.0,
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


build_openai_client = build_client
default_openai_client_policy = default_client_policy
build_openai_client_from_callables = build_client_from_callables
build_openai_client_for_settings = build_client_for_settings
openai_client_policy_from_settings = client_policy_from_settings


__all__ = [
    "LLMServiceClient",
    "build_client",
    "build_client_for_settings",
    "build_client_from_callables",
    "build_openai_client",
    "build_openai_client_for_settings",
    "build_openai_client_from_callables",
    "client_policy_from_settings",
    "default_client_policy",
    "default_openai_client_policy",
    "openai_client_policy_from_settings",
]
