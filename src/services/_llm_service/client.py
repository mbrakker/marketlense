from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Any, Callable, Optional, TypeVar

from src.contracts.llm import (
    BrowserUseLLMClients,
    LLMClientPolicy,
    LLMProviderOperations,
)
from src.contracts.run_context import RunContext
from src.services._llm_service import openai_chat, openai_responses, openrouter
from src.services._llm_service.audit import (
    audit_record_fields,
    build_model_call_audit_record,
    build_model_call_replay_bundle,
)
from src.services._llm_service.policy import _execute_with_policy, logger
from src.utils.errors import AppError
from src.utils.logging import log_event

_T = TypeVar("_T")
_BROWSER_USE_OPENAI_MODEL_DEFAULT = "gpt-5.6-luna"


def _default_provider_operations() -> LLMProviderOperations:
    return LLMProviderOperations(
        schema_version="1.0",
        openai_chat_json=openai_chat.openai_chat_json,
        openrouter_chat_json=openrouter.openrouter_chat_json,
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
                        "same_provider_fallback": bool(
                            getattr(request, "same_provider_fallback", False)
                        ),
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
        response = _execute_with_policy(
            ctx=ctx,
            operation_name=operation_name,
            policy=self._policy,
            sleep_fn=self._sleep_fn,
            monotonic_fn=self._monotonic_fn,
            call=call,
        )
        if request is not None:
            try:
                audit_record = build_model_call_audit_record(
                    operation=operation_name,
                    scope=self._policy.scope,
                    request=request,
                    response=response,
                )
                logger.info(
                    log_event(
                        ctx,
                        role="service",
                        event="llm_model_call_audit",
                        module=logger.name,
                        fields=audit_record_fields(audit_record),
                    )
                )
            except Exception as exc:
                logger.info(
                    log_event(
                        ctx,
                        role="service",
                        event="llm_model_call_audit_failed",
                        module=logger.name,
                        fields={
                            "operation": operation_name,
                            "scope": self._policy.scope,
                            "error_type": type(exc).__name__,
                            "error": str(exc),
                        },
                    )
                )
        return response

    def openai_chat_json(self, req: Any, ctx: RunContext) -> Any:
        try:
            return self._run(
                "openai_chat_json",
                ctx,
                lambda: self._base_client.openai_chat_json(req, ctx),
                request=req,
            )
        except AppError as exc:
            fallback = getattr(self._base_client, "openrouter_chat_json", None)
            if (
                bool(getattr(req, "same_provider_fallback", False))
                or fallback is None
                or not callable(fallback)
                or not exc.retryable
            ):
                raise
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="llm_provider_failover_start",
                    module=logger.name,
                    fields={
                        "operation": "openai_chat_json",
                        "scope": self._policy.scope,
                        "primary_provider": "openai",
                        "fallback_provider": "openrouter",
                        "primary_error_code": exc.code,
                        "primary_retryable": exc.retryable,
                    },
                )
            )
            response = self._run(
                "openai_chat_json",
                ctx,
                lambda: fallback(req, ctx),
                request=_request_with_provider_decision(req, "openrouter_fallback"),
            )
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="llm_provider_failover_complete",
                    module=logger.name,
                    fields={
                        "operation": "openai_chat_json",
                        "scope": self._policy.scope,
                        "primary_provider": "openai",
                        "fallback_provider": "openrouter",
                        "primary_error_code": exc.code,
                        "fallback_model": str(getattr(response, "model", "") or ""),
                        "fallback_request_id": str(
                            getattr(response, "request_id", "") or ""
                        ),
                    },
                )
            )
            return _response_with_provider_decision(
                response,
                "openrouter_fallback",
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
    openrouter_chat_json: Optional[Callable[[Any, RunContext], Any]] = None,
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
            openrouter_chat_json=openrouter_chat_json,
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


def build_openai_browser_use_client(
    *,
    settings: Any,
    ctx: RunContext,
    client_factory: Callable[..., Any],
) -> Any:
    api_key = str(getattr(settings, "openai_api_key", "") or "").strip()
    model = _openai_browser_use_model(getattr(settings, "model", ""))
    if not api_key:
        raise AppError(
            code="openai_missing_api_key",
            message="OPENAI_API_KEY is required for browser-use OpenAI primary",
            retryable=False,
            context={"model": model},
        )
    max_tokens = getattr(settings, "max_tokens", None)
    effective_max_tokens = openrouter._resolve_effective_max_tokens(max_tokens)
    fields = {
        "provider": "openai",
        "model": model,
        "temperature": getattr(settings, "temperature", None),
        "timeout_seconds": getattr(settings, "timeout_seconds", None),
        "configured_max_tokens": max_tokens,
        "effective_max_tokens": effective_max_tokens,
        "max_retries": 0,
    }
    logger.info(
        log_event(
            ctx,
            role="service",
            event="llm_browser_use_openai_client_start",
            module=logger.name,
            fields=fields,
        )
    )
    try:
        client = client_factory(
            model=model,
            api_key=api_key,
            temperature=getattr(settings, "temperature", None),
            timeout=getattr(settings, "timeout_seconds", None),
            max_retries=0,
            max_completion_tokens=effective_max_tokens,
        )
    except (RuntimeError, OSError, TypeError, ValueError) as exc:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="llm_browser_use_openai_client_failed",
                module=logger.name,
                fields={**fields, "error_type": type(exc).__name__},
            )
        )
        raise AppError(
            code="openai_browser_use_client_init_failed",
            message="Failed to initialize browser-use OpenAI client",
            cause=exc,
            retryable=True,
            context={"model": model, "provider_error_type": type(exc).__name__},
        ) from exc
    logger.info(
        log_event(
            ctx,
            role="service",
            event="llm_browser_use_openai_client_complete",
            module=logger.name,
            fields=fields,
        )
    )
    return client


def build_browser_use_llm_clients(
    *,
    settings: Any,
    ctx: RunContext,
    openai_client_factory: Callable[..., Any] | None,
    openrouter_client_factory: Callable[..., Any] | None,
) -> BrowserUseLLMClients:
    primary_llm: Any = None
    primary_provider = ""
    primary_model = ""
    fallback_llm: Any = None
    fallback_provider: str | None = None
    fallback_model: str | None = None
    primary_error: AppError | None = None

    if (
        openai_client_factory is not None
        and str(getattr(settings, "openai_api_key", "") or "").strip()
    ):
        try:
            primary_llm = build_openai_browser_use_client(
                settings=settings,
                ctx=ctx,
                client_factory=openai_client_factory,
            )
            primary_provider = "openai"
            primary_model = _openai_browser_use_model(getattr(settings, "model", ""))
        except AppError as exc:
            primary_error = exc

    if (
        openrouter_client_factory is not None
        and str(getattr(settings, "openrouter_api_key", "") or "").strip()
    ):
        openrouter_settings = _browser_use_openrouter_settings(settings)
        try:
            openrouter_llm = openrouter.build_openrouter_client(
                settings=openrouter_settings,
                ctx=ctx,
                client_factory=openrouter_client_factory,
            )
        except AppError as exc:
            if primary_llm is None:
                raise
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="llm_browser_use_fallback_unavailable",
                    module=logger.name,
                    fields={
                        "primary_provider": primary_provider,
                        "fallback_provider": "openrouter",
                        "fallback_model": str(
                            getattr(openrouter_settings, "model", "") or ""
                        ),
                        "error_code": exc.code,
                        "retryable": exc.retryable,
                    },
                )
            )
        else:
            if primary_llm is None:
                primary_llm = openrouter_llm
                primary_provider = "openrouter"
                primary_model = str(getattr(openrouter_settings, "model", "") or "")
            else:
                fallback_llm = openrouter_llm
                fallback_provider = "openrouter"
                fallback_model = str(getattr(openrouter_settings, "model", "") or "")

    if primary_llm is None:
        if (
            primary_error is not None
            and not str(getattr(settings, "openrouter_api_key", "") or "").strip()
        ):
            raise primary_error
        raise AppError(
            code="browser_use_llm_provider_missing",
            message="OPENAI_API_KEY or OPENROUTER_API_KEY is required for browser-use",
            retryable=False,
            context={
                "openai_key_present": bool(
                    str(getattr(settings, "openai_api_key", "") or "").strip()
                ),
                "openrouter_key_present": bool(
                    str(getattr(settings, "openrouter_api_key", "") or "").strip()
                ),
            },
        )

    logger.info(
        log_event(
            ctx,
            role="service",
            event="llm_browser_use_clients_resolved",
            module=logger.name,
            fields={
                "primary_provider": primary_provider,
                "primary_model": primary_model,
                "fallback_provider": fallback_provider or "",
                "fallback_model": fallback_model or "",
                "openai_key_present": bool(
                    str(getattr(settings, "openai_api_key", "") or "").strip()
                ),
                "openrouter_key_present": bool(
                    str(getattr(settings, "openrouter_api_key", "") or "").strip()
                ),
            },
        )
    )
    return BrowserUseLLMClients(
        schema_version="1.0",
        primary_provider=primary_provider,
        primary_model=primary_model,
        primary_llm=primary_llm,
        fallback_provider=fallback_provider,
        fallback_model=fallback_model,
        fallback_llm=fallback_llm,
    )


def _openai_browser_use_model(value: object) -> str:
    model = str(value or "").strip() or _BROWSER_USE_OPENAI_MODEL_DEFAULT
    if model.startswith("openai/"):
        model = model.split("/", 1)[1].strip()
    return model or _BROWSER_USE_OPENAI_MODEL_DEFAULT


def _browser_use_openrouter_settings(settings: Any) -> Any:
    model = str(getattr(settings, "openrouter_model", "") or "").strip()
    if not model:
        model = str(getattr(settings, "model", "") or "").strip()
    if model and "/" not in model:
        model = f"openai/{model}"
    if not model:
        model = f"openai/{_BROWSER_USE_OPENAI_MODEL_DEFAULT}"
    return SimpleNamespace(
        **{
            name: getattr(settings, name)
            for name in dir(settings)
            if not name.startswith("_")
            and not callable(getattr(settings, name, None))
            and name != "model"
        },
        model=model,
    )


def _request_with_provider_decision(request: Any, provider_decision: str) -> Any:
    try:
        return type(
            "LLMProviderDecisionRequest",
            (),
            {
                **{
                    name: getattr(request, name)
                    for name in dir(request)
                    if not name.startswith("_")
                    and not callable(getattr(request, name, None))
                },
                "provider_decision": provider_decision,
            },
        )()
    except Exception:
        request.provider_decision = provider_decision
        return request


def _response_with_provider_decision(response: Any, provider_decision: str) -> Any:
    if hasattr(response, "provider_decision"):
        return response
    try:
        response.provider_decision = provider_decision
        return response
    except Exception:
        return SimpleNamespace(
            **{
                name: getattr(response, name)
                for name in dir(response)
                if not name.startswith("_")
                and not callable(getattr(response, name, None))
            },
            provider_decision=provider_decision,
        )


__all__ = [
    "LLMServiceClient",
    "build_client",
    "build_client_for_settings",
    "build_client_from_callables",
    "build_model_call_audit_record",
    "build_model_call_replay_bundle",
    "build_browser_use_llm_clients",
    "build_openai_browser_use_client",
    "build_openai_client",
    "build_openai_client_for_settings",
    "build_openai_client_from_callables",
    "client_policy_from_settings",
    "default_client_policy",
    "default_openai_client_policy",
    "openai_client_policy_from_settings",
]
