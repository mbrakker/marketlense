from __future__ import annotations

import asyncio
import inspect
import logging
from concurrent.futures import Future, TimeoutError as FutureTimeoutError
from threading import Thread
from typing import Any, Coroutine, cast

from src.contracts.run_context import RunContext
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.browser_report_download_service.cdp")

from .models import (
    _CDP_OPERATION_TIMEOUT_SECONDS,
    _CDP_PRINT_TO_PDF_TIMEOUT_SECONDS,
)


def _send_raw_cdp(
    *,
    client: Any,
    method: str,
    params: dict[str, Any],
    session_id: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    send_raw = getattr(client, "send_raw", None)
    if callable(send_raw):
        result = _await_cdp_client_operation(
            client=client,
            value=send_raw(method, params, session_id=session_id or None),
            timeout_seconds=timeout_seconds,
        )
        return result if isinstance(result, dict) else {}
    send = getattr(client, "send", None)
    domain, command = method.split(".", 1)
    domain_sender = getattr(send, domain, None) if send is not None else None
    command_sender = (
        getattr(domain_sender, command, None) if domain_sender is not None else None
    )
    if not callable(command_sender):
        raise RuntimeError(f"CDP client cannot send {method}")
    kwargs: dict[str, Any] = {"params": params}
    if session_id:
        kwargs["session_id"] = session_id
    result = _await_cdp_client_operation(
        client=client,
        value=command_sender(**kwargs),
        timeout_seconds=timeout_seconds,
    )
    return result if isinstance(result, dict) else {}


def _extract_runtime_value(
    *,
    result: dict[str, Any],
    ctx: RunContext,
    normalized_url: str,
    required: bool,
) -> Any:
    if result.get("exceptionDetails"):
        description = str(result.get("exceptionDetails") or "").strip()
        if required:
            raise AppError(
                code="browser_download_cdp_runtime_exception",
                message="CDP Runtime.evaluate reported a JavaScript exception",
                retryable=False,
                severity="error",
                context={"normalized_url": normalized_url, "exception": description},
            )
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_cdp_runtime_exception",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "result_status": "failed",
                    "error": description,
                },
            )
        )
        return None
    value_payload = result.get("result")
    if isinstance(value_payload, dict) and "value" in value_payload:
        return value_payload.get("value")
    if "value" in result:
        return result.get("value")
    return None


def _await_with_timeout(
    value: Any,
    *,
    timeout_seconds: float = _CDP_OPERATION_TIMEOUT_SECONDS,
) -> Any:
    if not inspect.isawaitable(value):
        return value
    payload: dict[str, Any] = {}
    errors: list[BaseException] = []

    async def awaitable() -> Any:
        return await value

    def runner() -> None:
        try:
            payload["result"] = asyncio.run(awaitable())
        except BaseException as exc:  # pragma: no cover - defensive thread bridge
            errors.append(exc)

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(asyncio.wait_for(awaitable(), timeout=timeout_seconds))

    thread = Thread(target=runner, daemon=True)
    thread.start()
    thread.join(timeout_seconds)
    if thread.is_alive():
        raise TimeoutError("CDP operation timed out")
    if errors:
        raise errors[0]
    return payload.get("result")


def _await_cdp_client_operation(
    *,
    client: Any,
    value: Any,
    timeout_seconds: float = _CDP_OPERATION_TIMEOUT_SECONDS,
) -> Any:
    if not inspect.isawaitable(value):
        return value
    handler_task = getattr(client, "_message_handler_task", None)
    client_loop = None
    if handler_task is not None:
        try:
            client_loop = handler_task.get_loop()
        except Exception:
            client_loop = None
    if client_loop is not None and client_loop.is_running():
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None
        if running_loop is not client_loop:
            future: Future[Any] = asyncio.run_coroutine_threadsafe(
                cast(Coroutine[Any, Any, Any], value),
                client_loop,
            )
            try:
                return future.result(timeout=timeout_seconds)
            except FutureTimeoutError as exc:
                future.cancel()
                raise TimeoutError("CDP operation timed out") from exc
    return _await_with_timeout(value, timeout_seconds=timeout_seconds)


def _cdp_timeout_seconds(method: str) -> float:
    if method == "Page.printToPDF":
        return _CDP_PRINT_TO_PDF_TIMEOUT_SECONDS
    return _CDP_OPERATION_TIMEOUT_SECONDS
