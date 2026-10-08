from __future__ import annotations
import json
import logging
import re
import threading
import warnings
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Dict, Iterator, NoReturn, Optional
from urllib.parse import urlencode, urlsplit, urlunsplit
import requests
import urllib3
from src.contracts.run_context import RunContext
from src.contracts.wordpress import (
    WordPressPublishTargetPreflightRequest,
    WordPressPublishTargetPreflightResponse,
)
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
    provider_calls: int = 1


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
    return "posts" if token in {"", "post"} else token


def _rest_route_endpoint(route: str) -> str:
    token = str(route).strip()
    segments = token.split("/")
    if not token or any(
        not re.fullmatch(r"[A-Za-z0-9_-]+", segment) for segment in segments
    ):
        raise AppError(
            code="wordpress_rest_route_invalid",
            message="WordPress REST preflight route must be a relative wp-json path",
            retryable=False,
        )
    return "/".join(segments)


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
    timeout_seconds: float = DEFAULT_TIMEOUT,
    request_error_fields: Optional[Dict[str, Any]] = None,
    params: Optional[dict[str, Any]] = None,
    data: Any = None,
    files: Optional[dict[str, Any]] = None,
    allow_redirects: Optional[bool] = None,
) -> _WordPressRequestResult:
    normalized_method = str(method or "").strip().upper()
    request_calls = 0
    request_kwargs: dict[str, Any] = {
        "headers": dict(headers or {}),
        "timeout": min(max(float(timeout_seconds), 0.1), DEFAULT_TIMEOUT),
        "allow_redirects": False,
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
        nonlocal request_calls
        request_calls += 1
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
            if _is_wordpress_installation_redirect(result.response):
                _raise_wordpress_installation_redirect(
                    ctx=ctx,
                    resp=result.response,
                    fields={
                        **(request_error_fields or {}),
                        "provider_calls": request_calls,
                        "url": url,
                        "method": normalized_method,
                        "pool_key": result.pool_key,
                        "used_pooled_session": result.used_pooled_session,
                        "pool_reused": result.pool_reused,
                    },
                )
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
                fallback_result = _send(fallback_url)
                return _WordPressRequestResult(
                    response=fallback_result.response,
                    used_pooled_session=fallback_result.used_pooled_session,
                    pool_key=fallback_result.pool_key,
                    pool_reused=fallback_result.pool_reused,
                    provider_calls=request_calls,
                )
            return _WordPressRequestResult(
                response=result.response,
                used_pooled_session=result.used_pooled_session,
                pool_key=result.pool_key,
                pool_reused=result.pool_reused,
                provider_calls=request_calls,
            )
    except requests.RequestException as exc:
        _raise_request_exception(
            ctx=ctx,
            event=request_error_event,
            code=request_error_code,
            message=request_error_message,
            exc=exc,
            fields={
                **(request_error_fields or {}),
                "provider_calls": request_calls,
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


def _is_wordpress_installation_redirect(resp: Any) -> bool:
    status_code = int(getattr(resp, "status_code", 0) or 0)
    location = str(
        getattr(getattr(resp, "headers", {}) or {}, "get", lambda *_: "")(
            "Location", ""
        )
        or ""
    ).casefold()
    return 300 <= status_code < 400 and any(
        marker in location
        for marker in ("wp-admin/install.php", "wp-admin/setup-config.php")
    )


def _raise_wordpress_installation_redirect(
    *,
    ctx: RunContext,
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
            event="wordpress_target_installation_redirect",
            module=logger.name,
            fields=error_context,
        )
    )
    raise AppError(
        code="wordpress_target_installation_redirect",
        message="WordPress target redirected to installation or setup",
        retryable=False,
        context=error_context,
    )


def _safe_json(text: str) -> Dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}


def _execute_preflight_request(*, provider_calls: int, **kwargs: Any) -> Any:
    try:
        return _execute_request(**kwargs)
    except AppError as exc:
        request_calls = max(1, int(exc.context.get("provider_calls", 1) or 1))
        raise AppError(
            code=exc.code,
            message="WordPress capability preflight request failed",
            cause=exc,
            retryable=exc.retryable,
            context={"provider_calls": provider_calls + request_calls},
        ) from exc


def preflight_publish_target(
    request: WordPressPublishTargetPreflightRequest,
    ctx: RunContext,
) -> WordPressPublishTargetPreflightResponse:
    base = request.base_url.rstrip("/")
    targets: list[tuple[str, str, tuple[str, ...]]] = []
    if str(request.post_type or "").strip():
        targets.append(
            (
                str(request.post_type).strip(),
                _post_type_endpoint(request.post_type),
                request.required_meta_keys,
            )
        )
    for additional in request.additional_post_types:
        post_type = str(additional.post_type).strip()
        if not post_type:
            raise AppError(
                code="wordpress_post_type_invalid",
                message="WordPress preflight post type must not be empty",
                retryable=False,
            )
        targets.append(
            (
                post_type,
                _post_type_endpoint(post_type),
                additional.required_meta_keys,
            )
        )
    target_names = [target[0] for target in targets]
    if len(target_names) != len(set(target_names)):
        raise AppError(
            code="wordpress_post_type_duplicate",
            message="WordPress preflight post types must be unique",
            retryable=False,
        )
    route_targets = tuple(
        (route, _rest_route_endpoint(route)) for route in request.required_rest_routes
    )
    if not targets and not route_targets and not request.required_user_capabilities:
        raise AppError(
            code="wordpress_preflight_requirements_empty",
            message="WordPress preflight requires a post type, route, or user capability",
            retryable=False,
        )
    if (
        request.required_capabilities
        or request.required_user_capabilities
        or route_targets
    ) and not request.verify_authentication:
        raise AppError(
            code="wordpress_authentication_unverified",
            message="WordPress capability and route checks require authenticated identity verification",
            retryable=False,
        )

    first_endpoint = (
        targets[0][1] if targets else (route_targets[0][1] if route_targets else "")
    )
    authenticated = False
    user_capabilities: dict[str, object] = {}
    provider_calls = 0
    verified_post_types: list[str] = []
    verified_meta_keys: list[str] = []
    verified_capabilities: list[str] = []
    verified_user_capabilities: tuple[str, ...] = ()
    verified_rest_routes: list[str] = []
    primary_status_code = 0
    primary_pool_reused = False

    def execute(
        *,
        method: str,
        url: str,
        event: str,
        code: str,
        message: str,
        fields: dict[str, object],
        params: dict[str, str] | None = None,
    ) -> tuple[Any, bool]:
        nonlocal provider_calls
        result = _execute_preflight_request(
            provider_calls=provider_calls,
            method=method,
            url=url,
            headers={"Authorization": request.auth_header},
            params=params,
            ssl_verify=request.ssl_verify,
            ca_bundle_path=request.ca_bundle_path,
            timeout_seconds=request.timeout_seconds,
            ctx=ctx,
            request_error_event=event,
            request_error_code=code,
            request_error_message=message,
            request_error_fields=fields,
        )
        provider_calls += result.provider_calls
        response = result.response
        status_code = int(getattr(response, "status_code", 0) or 0)
        if status_code >= 500:
            _raise_http_server_error(
                ctx=ctx,
                event=event,
                code=code,
                message_prefix=message,
                resp=response,
                fields={**fields, "provider_calls": provider_calls},
            )
        if status_code >= 400:
            raise AppError(
                code=code,
                message=f"{message}: {status_code}",
                retryable=False,
                context={"status_code": status_code, "provider_calls": provider_calls},
            )
        return response, bool(result.pool_reused)

    if request.verify_authentication:
        try:
            user_response, _ = execute(
                method="GET",
                url=f"{base}/wp-json/wp/v2/users/me",
                params={"context": "edit"},
                event="wordpress_authentication_preflight_failed",
                code="wordpress_authentication_unavailable",
                message="WordPress authentication preflight failed",
                fields={
                    "post_type_count": len(targets),
                    "rest_route_count": len(route_targets),
                },
            )
        except AppError as exc:
            if exc.context.get("status_code") in {401, 403}:
                raise AppError(
                    code="wordpress_authentication_invalid",
                    message="WordPress rejected the configured publication credentials",
                    retryable=False,
                    context={
                        "status_code": exc.context.get("status_code"),
                        "provider_calls": provider_calls,
                    },
                ) from exc
            raise
        user_payload = _safe_json(getattr(user_response, "text", "") or "")
        raw_user_capabilities = (
            user_payload.get("capabilities") if isinstance(user_payload, dict) else None
        )
        if (
            not isinstance(user_payload, dict)
            or int(user_payload.get("id", 0) or 0) <= 0
            or not isinstance(raw_user_capabilities, dict)
        ):
            raise AppError(
                code="wordpress_authentication_unverified",
                message="WordPress did not return authenticated user capabilities",
                retryable=False,
                context={"provider_calls": provider_calls},
            )
        authenticated = True
        user_capabilities = raw_user_capabilities
        missing_user_capabilities = tuple(
            capability
            for capability in request.required_user_capabilities
            if user_capabilities.get(capability) is not True
        )
        if missing_user_capabilities:
            raise AppError(
                code="wordpress_user_capability_missing",
                message="Configured WordPress credentials lack a required user capability",
                retryable=False,
                context={
                    "missing_capability_count": len(missing_user_capabilities),
                    "provider_calls": provider_calls,
                },
            )
        verified_user_capabilities = tuple(request.required_user_capabilities)
        primary_status_code = int(getattr(user_response, "status_code", 0) or 0)

    logger.info(
        log_event(
            ctx,
            role="service",
            event="wordpress_publish_target_preflight_start",
            module=logger.name,
            fields={
                "base_url": base,
                "post_type_count": len(targets),
                "rest_route_count": len(route_targets),
                "endpoint": first_endpoint,
            },
        )
    )
    for index, (post_type, endpoint, required_meta_keys) in enumerate(targets):
        fields: dict[str, object] = {"post_type": post_type, "endpoint": endpoint}
        response, pool_reused = execute(
            method="GET",
            url=f"{base}/wp-json/wp/v2/types/{endpoint}",
            params={"context": "edit"} if request.verify_authentication else None,
            event="wordpress_publish_target_preflight_failed",
            code="wordpress_publish_target_unreachable",
            message="WordPress publish target preflight failed",
            fields=fields,
        )
        payload = _safe_json(getattr(response, "text", "") or "")
        if (
            not isinstance(payload, dict)
            or not str(
                payload.get("rest_base") or payload.get("slug") or endpoint
            ).strip()
        ):
            raise AppError(
                code="wordpress_publish_target_invalid_response",
                message="WordPress publish target preflight returned invalid JSON",
                retryable=False,
                context={"post_type": post_type, "provider_calls": provider_calls},
            )
        metadata_response, metadata_pool_reused = execute(
            method="OPTIONS",
            url=f"{base}/wp-json/wp/v2/{endpoint}",
            event="wordpress_publish_target_metadata_preflight_failed",
            code="wordpress_publish_target_metadata_unavailable",
            message="WordPress publish target metadata preflight failed",
            fields=fields,
        )
        metadata_payload = _safe_json(getattr(metadata_response, "text", "") or "")
        schema = (
            metadata_payload.get("schema") if isinstance(metadata_payload, dict) else {}
        )
        properties = schema.get("properties") if isinstance(schema, dict) else {}
        meta = properties.get("meta") if isinstance(properties, dict) else {}
        meta_properties = meta.get("properties") if isinstance(meta, dict) else {}
        registered_meta_keys = {
            str(key).strip() for key in (meta_properties or {}) if str(key).strip()
        }
        missing_meta_keys = tuple(
            key for key in required_meta_keys if key not in registered_meta_keys
        )
        if missing_meta_keys:
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="wordpress_publish_target_metadata_preflight_blocked",
                    module=logger.name,
                    fields={
                        "post_type": post_type,
                        "required_meta_key_count": len(required_meta_keys),
                        "missing_meta_key_count": len(missing_meta_keys),
                    },
                )
            )
            raise AppError(
                code="wordpress_publish_target_metadata_missing",
                message="WordPress publish target is missing required proof metadata",
                retryable=False,
                context={
                    "post_type": post_type,
                    "missing_meta_key_count": len(missing_meta_keys),
                    "provider_calls": provider_calls,
                },
            )
        if request.verify_authentication:
            raw_type_capabilities = payload.get("capabilities")
            if not isinstance(raw_type_capabilities, dict):
                raise AppError(
                    code="wordpress_capability_unverified",
                    message="WordPress did not expose the target post-type capabilities",
                    retryable=False,
                    context={"post_type": post_type, "provider_calls": provider_calls},
                )
            missing_capabilities = []
            for capability in request.required_capabilities:
                granted_capability = str(
                    raw_type_capabilities.get(capability) or ""
                ).strip()
                if (
                    not granted_capability
                    or user_capabilities.get(granted_capability) is not True
                ):
                    missing_capabilities.append(capability)
            if missing_capabilities:
                raise AppError(
                    code="wordpress_create_permission_missing",
                    message="Configured WordPress credentials lack required publication capabilities",
                    retryable=False,
                    context={
                        "missing_capability_count": len(missing_capabilities),
                        "provider_calls": provider_calls,
                    },
                )
            for capability in request.required_capabilities:
                if capability not in verified_capabilities:
                    verified_capabilities.append(capability)
        verified_post_types.append(post_type)
        verified_meta_keys.extend(
            key for key in required_meta_keys if key not in verified_meta_keys
        )
        if index == 0:
            primary_status_code = int(getattr(response, "status_code", 0) or 0)
            primary_pool_reused = pool_reused and metadata_pool_reused

    for route, route_path in route_targets:
        route_response, pool_reused = execute(
            method="OPTIONS",
            url=f"{base}/wp-json/{route_path}",
            event="wordpress_rest_route_preflight_failed",
            code="wordpress_rest_route_unavailable",
            message="WordPress REST route preflight failed",
            fields={"route": route},
        )
        route_payload = _safe_json(getattr(route_response, "text", "") or "")
        methods: set[str] = set()
        if isinstance(route_payload, dict):
            raw_methods = route_payload.get("methods")
            if isinstance(raw_methods, list):
                methods.update(str(method).upper() for method in raw_methods)
            endpoints = route_payload.get("endpoints")
            if isinstance(endpoints, list):
                for endpoint_payload in endpoints:
                    endpoint_methods = (
                        endpoint_payload.get("methods")
                        if isinstance(endpoint_payload, dict)
                        else None
                    )
                    if isinstance(endpoint_methods, list):
                        methods.update(
                            str(method).upper() for method in endpoint_methods
                        )
        headers = getattr(route_response, "headers", {})
        allow_header = headers.get("Allow") if isinstance(headers, dict) else None
        if isinstance(allow_header, str):
            methods.update(method.strip().upper() for method in allow_header.split(","))
        missing_methods = tuple(
            method.upper()
            for method in request.required_rest_methods
            if method.upper() not in methods
        )
        if missing_methods:
            raise AppError(
                code="wordpress_rest_route_method_missing",
                message="WordPress REST route does not expose a required method",
                retryable=False,
                context={
                    "missing_method_count": len(missing_methods),
                    "provider_calls": provider_calls,
                },
            )
        verified_rest_routes.append(route)
        if not targets and not primary_status_code:
            primary_status_code = int(getattr(route_response, "status_code", 0) or 0)
            primary_pool_reused = pool_reused

    logger.info(
        log_event(
            ctx,
            role="service",
            event="wordpress_publish_target_preflight_complete",
            module=logger.name,
            fields={
                "post_type_count": len(verified_post_types),
                "verified_meta_key_count": len(verified_meta_keys),
                "authenticated": authenticated,
                "verified_capability_count": len(verified_capabilities),
                "verified_user_capability_count": len(verified_user_capabilities),
                "verified_rest_route_count": len(verified_rest_routes),
                "pool_reused": primary_pool_reused,
                "provider_calls": provider_calls,
            },
        )
    )
    return WordPressPublishTargetPreflightResponse(
        schema_version="1.0",
        base_url=base,
        post_type=request.post_type,
        endpoint=(
            f"{base}/wp-json/wp/v2/{first_endpoint}"
            if targets
            else f"{base}/wp-json/{first_endpoint}"
        ),
        reachable=True,
        status_code=primary_status_code,
        verified_meta_keys=tuple(verified_meta_keys),
        authenticated=authenticated,
        verified_capabilities=tuple(verified_capabilities),
        verified_post_types=tuple(verified_post_types),
        verified_user_capabilities=verified_user_capabilities,
        verified_rest_routes=tuple(verified_rest_routes),
        provider_calls=provider_calls,
    )


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
    "_execute_preflight_request",
    "preflight_publish_target",
]
