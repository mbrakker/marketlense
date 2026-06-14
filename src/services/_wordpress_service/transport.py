from __future__ import annotations
import json
import logging
import threading
import warnings
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Dict, Iterator, NoReturn, Optional
from urllib.parse import urlencode, urlsplit, urlunsplit
import requests
import urllib3
from src.contracts.run_context import RunContext
from src.services._http_transport_common import session_pool_key as _session_pool_key
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.wordpress_service")
DEFAULT_TIMEOUT = 30
HTTP_ERROR_BODY_LIMIT = 1000
REDACTED_HEADER_KEYS = {"authorization", "cookie", "set-cookie"}
WORDPRESS_HTTP_POOL_CONNECTIONS = 8
WORDPRESS_HTTP_POOL_MAXSIZE = 8
_ORIGINAL_REQUEST_CALLS: dict[str, Any] = {
    "GET": requests.get,
    "POST": requests.post,
}


@dataclass(frozen=True)
class _WordPressRequestResult:
    response: Any
    used_pooled_session: bool
    pool_key: str
    pool_reused: bool


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


def _post_type_endpoint(post_type: str) -> str:
    token = str(post_type).strip().strip("/")
    return token or "posts"


def _requests_verify(*, ssl_verify: bool, ca_bundle_path: Optional[str]) -> bool | str:
    if not ssl_verify:
        return False
    bundle_path = str(ca_bundle_path or "").strip()
    return bundle_path or True


def _build_session() -> requests.Session:
    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(
        pool_connections=WORDPRESS_HTTP_POOL_CONNECTIONS,
        pool_maxsize=WORDPRESS_HTTP_POOL_MAXSIZE,
        max_retries=0,
    )
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def _rest_query_fallback_url(url: str) -> str | None:
    parsed = urlsplit(str(url or "").strip())
    marker = "/wp-json"
    marker_index = parsed.path.find(marker)
    if marker_index < 0:
        return None
    rest_route = parsed.path[marker_index + len(marker) :] or "/"
    base_path = parsed.path[:marker_index].rstrip("/")
    query_parts = [urlencode({"rest_route": rest_route})]
    if parsed.query:
        query_parts.append(parsed.query)
    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            f"{base_path}/index.php" if base_path else "/index.php",
            "&".join(query_parts),
            parsed.fragment,
        )
    )


def _should_retry_rest_query_mode(response: Any, url: str, files: Any) -> bool:
    if files is not None or _rest_query_fallback_url(url) is None:
        return False
    status_code = int(getattr(response, "status_code", 0) or 0)
    if status_code == 404:
        return True
    content_type = str(
        getattr(
            getattr(response, "headers", {}) or {}, "get", lambda _key, _default="": ""
        )(
            "content-type",
            "",
        )
        or ""
    ).casefold()
    body_prefix = str(getattr(response, "text", "") or "")[:300].casefold()
    return "text/html" in content_type and "<html" in body_prefix


def _patched_direct_transport(method: str) -> Any | None:
    candidate = getattr(requests, str(method or "").strip().lower(), None)
    original = _ORIGINAL_REQUEST_CALLS.get(str(method or "").strip().upper())
    if callable(candidate) and candidate is not original:
        return candidate
    return None


def _execute_request(
    *,
    method: str,
    url: str,
    headers: dict[str, str],
    ssl_verify: bool,
    ca_bundle_path: Optional[str],
    ctx: RunContext,
    request_error_event: str,
    request_error_code: str,
    request_error_message: str,
    request_error_fields: Optional[Dict[str, Any]] = None,
    params: Optional[dict[str, Any]] = None,
    data: Any = None,
    files: Optional[dict[str, Any]] = None,
    allow_redirects: Optional[bool] = None,
) -> _WordPressRequestResult:
    normalized_method = str(method or "").strip().upper()
    request_kwargs: dict[str, Any] = {
        "headers": dict(headers or {}),
        "timeout": DEFAULT_TIMEOUT,
        "verify": _requests_verify(
            ssl_verify=ssl_verify,
            ca_bundle_path=ca_bundle_path,
        ),
    }
    if params is not None:
        request_kwargs["params"] = dict(params)
    if data is not None:
        request_kwargs["data"] = data
    if files is not None:
        request_kwargs["files"] = dict(files)
    if allow_redirects is not None:
        request_kwargs["allow_redirects"] = bool(allow_redirects)

    def _send(request_url: str) -> _WordPressRequestResult:
        pool_key = _session_pool_key(request_url)
        direct_transport = _patched_direct_transport(normalized_method)
        if direct_transport is not None:
            response = direct_transport(request_url, **request_kwargs)
            return _WordPressRequestResult(
                response=response,
                used_pooled_session=False,
                pool_key=pool_key,
                pool_reused=False,
            )
        session, pool_reused = _SESSION_POOL.acquire(pool_key)
        response = session.request(normalized_method, request_url, **request_kwargs)
        return _WordPressRequestResult(
            response=response,
            used_pooled_session=True,
            pool_key=pool_key,
            pool_reused=pool_reused,
        )

    try:
        with _suppress_insecure_request_warning(ssl_verify=ssl_verify):
            result = _send(url)
            fallback_url = _rest_query_fallback_url(url)
            if (
                fallback_url
                and fallback_url != url
                and _should_retry_rest_query_mode(result.response, url, files)
            ):
                logger.info(
                    log_event(
                        ctx,
                        role="service",
                        event="wordpress_rest_query_mode_fallback",
                        module=logger.name,
                        fields={
                            "method": normalized_method,
                            "url": url,
                            "fallback_url": fallback_url,
                            "status_code": int(
                                getattr(result.response, "status_code", 0) or 0
                            ),
                        },
                    )
                )
                return _send(fallback_url)
            return result
    except requests.RequestException as exc:
        _raise_request_exception(
            ctx=ctx,
            event=request_error_event,
            code=request_error_code,
            message=request_error_message,
            exc=exc,
            fields={
                **(request_error_fields or {}),
                "url": url,
                "method": normalized_method,
                "pool_key": _session_pool_key(url),
            },
        )


@contextmanager
def _suppress_insecure_request_warning(*, ssl_verify: bool) -> Iterator[None]:
    if ssl_verify:
        yield
        return
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", urllib3.exceptions.InsecureRequestWarning)
        yield


def _truncate_text(value: str, limit: int = HTTP_ERROR_BODY_LIMIT) -> str:
    normalized = str(value).replace("\r", "\\r").replace("\n", "\\n")
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[:limit]}...(truncated)"


def _sanitize_response_headers(headers: Any) -> Dict[str, str]:
    sanitized: Dict[str, str] = {}
    try:
        items = list(getattr(headers, "items", lambda: [])())
    except (AttributeError, TypeError):
        return sanitized
    for raw_key, raw_value in items:
        key = str(raw_key)
        if key.strip().lower() in REDACTED_HEADER_KEYS:
            continue
        sanitized[key] = str(raw_value)
    return sanitized


def _http_error_context(resp: Any) -> Dict[str, Any]:
    return {
        "status_code": int(getattr(resp, "status_code", 0) or 0),
        "reason": str(getattr(resp, "reason", "") or ""),
        "response_headers": _sanitize_response_headers(
            getattr(resp, "headers", {}) or {}
        ),
        "response_body_excerpt": _truncate_text(getattr(resp, "text", "") or ""),
    }


def _raise_request_exception(
    *,
    ctx: RunContext,
    event: str,
    code: str,
    message: str,
    exc: requests.RequestException,
    fields: Optional[Dict[str, Any]] = None,
) -> NoReturn:
    extra_fields = dict(fields or {})
    error_context = {
        **extra_fields,
        "exception_type": type(exc).__name__,
        "exception_message": str(exc),
    }
    response = getattr(exc, "response", None)
    if response is not None:
        error_context.update(_http_error_context(response))
    logger.info(
        log_event(
            ctx,
            role="service",
            event=event,
            module=logger.name,
            fields=error_context,
        )
    )
    raise AppError(
        code=code,
        message=message,
        cause=exc,
        retryable=True,
        context=error_context,
    ) from exc


def _raise_http_server_error(
    *,
    ctx: RunContext,
    event: str,
    code: str,
    message_prefix: str,
    resp: Any,
    fields: Optional[Dict[str, Any]] = None,
) -> NoReturn:
    error_context = {
        **dict(fields or {}),
        **_http_error_context(resp),
    }
    logger.info(
        log_event(
            ctx,
            role="service",
            event=event,
            module=logger.name,
            fields=error_context,
        )
    )
    raise AppError(
        code=code,
        message=f"{message_prefix}: {resp.status_code}",
        retryable=True,
        context=error_context,
    )


def _raise_http_redirect_error(
    *,
    ctx: RunContext,
    event: str,
    code: str,
    message_prefix: str,
    resp: Any,
    fields: Optional[Dict[str, Any]] = None,
) -> NoReturn:
    error_context = {
        **dict(fields or {}),
        **_http_error_context(resp),
    }
    logger.info(
        log_event(
            ctx,
            role="service",
            event=event,
            module=logger.name,
            fields=error_context,
        )
    )
    raise AppError(
        code=code,
        message=f"{message_prefix}: {resp.status_code}",
        retryable=True,
        context=error_context,
    )


def _safe_json(text: str) -> Dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}


__all__ = [
    "_WordPressRequestResult",
    "_SessionPool",
    "_SESSION_POOL",
    "_post_type_endpoint",
    "_requests_verify",
    "_build_session",
    "_session_pool_key",
    "_rest_query_fallback_url",
    "_should_retry_rest_query_mode",
    "_patched_direct_transport",
    "_execute_request",
    "_suppress_insecure_request_warning",
    "_truncate_text",
    "_sanitize_response_headers",
    "_http_error_context",
    "_raise_request_exception",
    "_raise_http_server_error",
    "_raise_http_redirect_error",
    "_safe_json",
]
