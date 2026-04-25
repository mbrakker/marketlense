"""Shared bounded HTTP acquisition executor for repeated website fetch flows.

This module centralizes session pooling, response-size policy, and transport
adaptation for acquisition-oriented services without introducing a second
public service boundary.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

import requests

from src.contracts.http_acquisition import (
    HttpAcquisitionRequest,
    HttpAcquisitionResponse,
    HttpAcquisitionResponsePolicy,
)
from src.contracts.run_context import RunContext
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.http_acquisition_service")

_ORIGINAL_REQUEST_CALLS: dict[str, Callable[..., Any]] = {
    "GET": requests.get,
    "POST": requests.post,
    "HEAD": requests.head,
}
_HTTP_POOL_CONNECTIONS = 8
_HTTP_POOL_MAXSIZE = 8


class _SessionPool:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: dict[str, requests.Session] = {}

    def acquire(self, pool_key: str) -> tuple[requests.Session, bool]:
        with self._lock:
            existing = self._sessions.get(pool_key)
            if existing is not None:
                return existing, True
            session = _build_session()
            self._sessions[pool_key] = session
            return session, False


_SESSION_POOL = _SessionPool()


def _build_session() -> requests.Session:
    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(
        pool_connections=_HTTP_POOL_CONNECTIONS,
        pool_maxsize=_HTTP_POOL_MAXSIZE,
        max_retries=0,
    )
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def execute_http_acquisition(
    *,
    request: HttpAcquisitionRequest,
    ctx: RunContext,
    requests_module: Any = requests,
) -> HttpAcquisitionResponse:
    method = str(request.method or "").strip().upper()
    if method not in {"GET", "POST", "HEAD"}:
        raise AppError(
            code="http_acquisition_method_invalid",
            message="HTTP acquisition only supports GET, POST, or HEAD requests",
            retryable=False,
            context={"method": request.method, "purpose": request.purpose},
        )
    url = str(request.url or "").strip()
    if not url:
        raise AppError(
            code="http_acquisition_url_invalid",
            message="HTTP acquisition requires a non-empty absolute URL",
            retryable=False,
            context={"purpose": request.purpose},
        )
    headers = {str(key): str(value) for key, value in dict(request.headers).items()}
    if request.range_header and "Range" not in headers:
        headers["Range"] = str(request.range_header)
    policy = request.response_policy
    pool_key = _session_pool_key(url)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="http_acquisition_request",
            module=logger.name,
            fields={
                "purpose": request.purpose,
                "method": method,
                "url": url,
                "pool_key": pool_key,
                "allow_redirects": request.allow_redirects,
                "timeout_seconds": request.timeout_seconds,
                "response_policy": {
                    "require_success_status": policy.require_success_status,
                    "capture_text": policy.capture_text,
                    "capture_binary": policy.capture_binary,
                    "capture_content_type_markers": list(
                        policy.capture_content_type_markers
                    ),
                    "max_body_bytes": policy.max_body_bytes,
                    "truncate_body": policy.truncate_body,
                    "stream_to_path": policy.stream_to_path,
                    "max_stream_bytes": policy.max_stream_bytes,
                    "chunk_size_bytes": policy.chunk_size_bytes,
                },
                "context_fields": dict(request.context_fields),
            },
        )
    )
    response_obj = None
    used_pooled_session = False
    pool_reused = False
    try:
        direct_transport = _patched_direct_transport(
            requests_module=requests_module,
            method=method,
        )
        request_kwargs = _request_kwargs(request=request)
        if direct_transport is not None:
            response_obj = direct_transport(url, **request_kwargs)
        else:
            session, pool_reused = _SESSION_POOL.acquire(pool_key)
            used_pooled_session = True
            response_obj = session.request(method, url, **request_kwargs)
        response = _adapt_response(
            response_obj=response_obj,
            request=request,
            policy=policy,
            method=method,
            url=url,
            pool_key=pool_key,
            used_pooled_session=used_pooled_session,
        )
        if policy.require_success_status and int(response.status_code) >= 400:
            raise AppError(
                code=request.error_code,
                message=request.error_message,
                retryable=True,
                context={
                    **dict(request.context_fields),
                    "purpose": request.purpose,
                    "method": method,
                    "url": url,
                    "status_code": response.status_code,
                    "content_type": response.content_type,
                },
            )
        logger.info(
            log_event(
                ctx,
                role="service",
                event="http_acquisition_response",
                module=logger.name,
                fields={
                    "purpose": request.purpose,
                    "method": method,
                    "url": url,
                    "final_url": response.final_url,
                    "status_code": response.status_code,
                    "content_type": response.content_type,
                    "content_length_bytes": response.content_length_bytes,
                    "body_truncated": response.body_truncated,
                    "streamed_bytes": response.streamed_bytes,
                    "used_pooled_session": response.used_pooled_session,
                    "pool_key": pool_key,
                    "pool_reused": pool_reused,
                },
            )
        )
        return response
    except AppError as exc:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="http_acquisition_failed",
                module=logger.name,
                fields={
                    "purpose": request.purpose,
                    "method": method,
                    "url": url,
                    "pool_key": pool_key,
                    "used_pooled_session": used_pooled_session,
                    "pool_reused": pool_reused,
                    "error_code": exc.code,
                    "error_message": exc.message,
                    "context_fields": dict(request.context_fields),
                },
            )
        )
        raise
    except _request_exception_type(requests_module) as exc:
        app_error = AppError(
            code=request.error_code,
            message=request.error_message,
            cause=exc,
            retryable=True,
            context={
                **dict(request.context_fields),
                "purpose": request.purpose,
                "method": method,
                "url": url,
            },
        )
        logger.info(
            log_event(
                ctx,
                role="service",
                event="http_acquisition_failed",
                module=logger.name,
                fields={
                    "purpose": request.purpose,
                    "method": method,
                    "url": url,
                    "pool_key": pool_key,
                    "used_pooled_session": used_pooled_session,
                    "pool_reused": pool_reused,
                    "error_code": app_error.code,
                    "error_message": app_error.message,
                    "context_fields": dict(request.context_fields),
                },
            )
        )
        raise app_error from exc
    finally:
        if response_obj is not None and hasattr(response_obj, "close"):
            try:
                response_obj.close()
            except Exception:  # pragma: no cover - defensive cleanup
                pass


def _request_kwargs(request: HttpAcquisitionRequest) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "headers": {str(key): str(value) for key, value in dict(request.headers).items()},
        "timeout": request.timeout_seconds,
    }
    if request.allow_redirects is not None:
        kwargs["allow_redirects"] = bool(request.allow_redirects)
    if request.data is not None:
        kwargs["data"] = dict(request.data)
    if request.response_policy.stream_to_path is not None:
        kwargs["stream"] = True
    return kwargs


def _patched_direct_transport(
    *,
    requests_module: Any,
    method: str,
) -> Callable[..., Any] | None:
    candidate = getattr(requests_module, method.lower(), None)
    original = _ORIGINAL_REQUEST_CALLS.get(method)
    if callable(candidate) and candidate is not original:
        return candidate
    return None


def _request_exception_type(requests_module: Any) -> type[Exception]:
    candidate = getattr(requests_module, "RequestException", None)
    if isinstance(candidate, type) and issubclass(candidate, Exception):
        return candidate
    return requests.RequestException


def _adapt_response(
    *,
    response_obj: Any,
    request: HttpAcquisitionRequest,
    policy: HttpAcquisitionResponsePolicy,
    method: str,
    url: str,
    pool_key: str,
    used_pooled_session: bool,
) -> HttpAcquisitionResponse:
    headers = {
        str(key): str(value)
        for key, value in dict(getattr(response_obj, "headers", {})).items()
    }
    content_type = str(
        headers.get("Content-Type", "") or headers.get("content-type", "")
    ).strip()
    content_length_bytes = _content_length_from_headers(headers)
    text_body: str | None = None
    body_bytes: bytes | None = None
    body_truncated = False
    streamed_bytes: int | None = None
    streamed_to_path: str | None = None
    if policy.stream_to_path:
        streamed_to_path, streamed_bytes = _stream_response_to_path(
            response_obj=response_obj,
            request=request,
            policy=policy,
            method=method,
            url=url,
        )
    elif _should_capture_body(policy=policy, content_type=content_type):
        captured_bytes, body_truncated = _read_response_body(
            response_obj=response_obj,
            request=request,
            policy=policy,
            method=method,
            url=url,
        )
        if policy.capture_binary:
            body_bytes = captured_bytes
        if policy.capture_text:
            text_body = _decode_response_bytes(
                captured_bytes=captured_bytes,
                response_obj=response_obj,
            )
    return HttpAcquisitionResponse(
        schema_version="1.0",
        purpose=request.purpose,
        method=method,
        request_url=url,
        final_url=str(getattr(response_obj, "url", "") or url).strip() or url,
        status_code=int(getattr(response_obj, "status_code", 0) or 0),
        headers=headers,
        content_type=content_type,
        content_length_bytes=content_length_bytes,
        text_body=text_body,
        body_bytes=body_bytes,
        body_truncated=body_truncated,
        streamed_to_path=streamed_to_path,
        streamed_bytes=streamed_bytes,
        used_pooled_session=used_pooled_session,
        pool_key=pool_key,
    )


def _content_length_from_headers(headers: dict[str, str]) -> int | None:
    raw_value = str(
        headers.get("Content-Length", "") or headers.get("content-length", "")
    ).strip()
    if not raw_value:
        return None
    try:
        parsed = int(raw_value)
    except ValueError:
        return None
    return parsed if parsed >= 0 else None


def _should_capture_body(
    *,
    policy: HttpAcquisitionResponsePolicy,
    content_type: str,
) -> bool:
    if not policy.capture_text and not policy.capture_binary:
        return False
    markers = tuple(
        str(marker).strip().casefold()
        for marker in policy.capture_content_type_markers
        if str(marker).strip()
    )
    if not markers:
        return True
    lowered = str(content_type or "").casefold()
    return any(marker in lowered for marker in markers)


def _read_response_body(
    *,
    response_obj: Any,
    request: HttpAcquisitionRequest,
    policy: HttpAcquisitionResponsePolicy,
    method: str,
    url: str,
) -> tuple[bytes, bool]:
    if hasattr(response_obj, "iter_content"):
        buffer = bytearray()
        for chunk in response_obj.iter_content(chunk_size=policy.chunk_size_bytes):
            if not chunk:
                continue
            next_size = len(buffer) + len(chunk)
            if policy.max_body_bytes is not None and next_size > policy.max_body_bytes:
                if not policy.truncate_body:
                    raise _body_too_large_error(
                        request=request,
                        method=method,
                        url=url,
                    )
                remaining = max(0, int(policy.max_body_bytes) - len(buffer))
                if remaining > 0:
                    buffer.extend(chunk[:remaining])
                return bytes(buffer), True
            buffer.extend(chunk)
        return bytes(buffer), False
    text_value = str(getattr(response_obj, "text", "") or "")
    encoded = text_value.encode("utf-8", errors="ignore")
    if policy.max_body_bytes is not None and len(encoded) > policy.max_body_bytes:
        if not policy.truncate_body:
            raise _body_too_large_error(
                request=request,
                method=method,
                url=url,
            )
        return bytes(encoded[: int(policy.max_body_bytes)]), True
    return encoded, False


def _decode_response_bytes(*, captured_bytes: bytes, response_obj: Any) -> str:
    encoding = str(getattr(response_obj, "encoding", "") or "").strip() or "utf-8"
    try:
        return captured_bytes.decode(encoding, errors="ignore")
    except LookupError:
        return captured_bytes.decode("utf-8", errors="ignore")


def _stream_response_to_path(
    *,
    response_obj: Any,
    request: HttpAcquisitionRequest,
    policy: HttpAcquisitionResponsePolicy,
    method: str,
    url: str,
) -> tuple[str, int]:
    destination_path = Path(str(policy.stream_to_path))
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    total_bytes = 0
    try:
        with destination_path.open("wb") as handle:
            if hasattr(response_obj, "iter_content"):
                chunks = response_obj.iter_content(chunk_size=policy.chunk_size_bytes)
            else:
                raw_bytes = getattr(response_obj, "content", None)
                if raw_bytes is None:
                    raw_bytes = str(getattr(response_obj, "text", "") or "").encode(
                        "utf-8",
                        errors="ignore",
                    )
                chunks = [raw_bytes]
            for chunk in chunks:
                if not chunk:
                    continue
                total_bytes += len(chunk)
                if (
                    policy.max_stream_bytes is not None
                    and total_bytes > policy.max_stream_bytes
                ):
                    raise _body_too_large_error(
                        request=request,
                        method=method,
                        url=url,
                    )
                handle.write(chunk)
    except AppError:
        destination_path.unlink(missing_ok=True)
        raise
    except OSError as exc:
        destination_path.unlink(missing_ok=True)
        raise AppError(
            code=request.write_error_code or request.error_code,
            message=request.write_error_message or request.error_message,
            cause=exc,
            retryable=True,
            context={
                **dict(request.context_fields),
                "purpose": request.purpose,
                "method": method,
                "url": url,
                "destination_path": str(destination_path),
            },
        ) from exc
    return str(destination_path), total_bytes


def _body_too_large_error(
    *,
    request: HttpAcquisitionRequest,
    method: str,
    url: str,
) -> AppError:
    return AppError(
        code=request.body_too_large_code or request.error_code,
        message=request.body_too_large_message or request.error_message,
        retryable=True,
        context={
            **dict(request.context_fields),
            "purpose": request.purpose,
            "method": method,
            "url": url,
        },
    )


def _session_pool_key(url: str) -> str:
    parsed = urlsplit(str(url or "").strip())
    scheme = str(parsed.scheme or "").strip().casefold() or "https"
    host = str(parsed.netloc or "").strip().casefold()
    return f"{scheme}://{host}" if host else scheme
