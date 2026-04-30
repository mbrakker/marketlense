from __future__ import annotations

import json
import logging
import threading
import warnings
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Dict, Iterator, NoReturn, Optional
from urllib.parse import urlsplit

import requests  # type: ignore[import-untyped]
import urllib3

from src.contracts.run_context import RunContext
from src.contracts.wordpress import (
    WordPressMediaUploadRequest,
    WordPressMediaUploadResponse,
    WordPressPostLookupBatchItem,
    WordPressPostLookupBatchRequest,
    WordPressPostLookupBatchResponse,
    WordPressPostCreateRequest,
    WordPressPostCreateResponse,
    WordPressPostLookupRequest,
    WordPressPostLookupResponse,
    WordPressPostUpdateRequest,
    WordPressPostUpdateResponse,
    WordPressTagEnsureRequest,
    WordPressTagEnsureResponse,
    WordPressTaxonomyEnsureRequest,
    WordPressTaxonomyEnsureResponse,
)
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


def _session_pool_key(url: str) -> str:
    parsed = urlsplit(str(url or "").strip())
    scheme = str(parsed.scheme or "").strip().casefold() or "https"
    host = str(parsed.netloc or "").strip().casefold()
    return f"{scheme}://{host}" if host else scheme


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
    pool_key = _session_pool_key(url)
    try:
        with _suppress_insecure_request_warning(ssl_verify=ssl_verify):
            direct_transport = _patched_direct_transport(normalized_method)
            if direct_transport is not None:
                response = direct_transport(url, **request_kwargs)
                return _WordPressRequestResult(
                    response=response,
                    used_pooled_session=False,
                    pool_key=pool_key,
                    pool_reused=False,
                )
            session, pool_reused = _SESSION_POOL.acquire(pool_key)
            response = session.request(normalized_method, url, **request_kwargs)
            return _WordPressRequestResult(
                response=response,
                used_pooled_session=True,
                pool_key=pool_key,
                pool_reused=pool_reused,
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
                "url": url,
                "method": normalized_method,
                "pool_key": pool_key,
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


def upload_media(
    request: WordPressMediaUploadRequest, ctx: RunContext
) -> WordPressMediaUploadResponse:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="wp_media_upload_start",
            module=logger.name,
            fields={
                "filename": request.filename,
                "mime_type": request.mime_type,
                "size": len(request.data),
                "ssl_verify": request.ssl_verify,
                "ca_bundle_path": request.ca_bundle_path or "",
            },
        )
    )
    url = f"{request.base_url.rstrip('/')}/wp-json/wp/v2/media"
    headers = {
        "Authorization": request.auth_header,
    }
    files = {
        "file": (request.filename, request.data, request.mime_type),
    }
    request_result = _execute_request(
        method="POST",
        url=url,
        headers=headers,
        files=files,
        ssl_verify=request.ssl_verify,
        ca_bundle_path=request.ca_bundle_path,
        ctx=ctx,
        request_error_event="wp_media_upload_request_error",
        request_error_code="wp_media_upload_failed",
        request_error_message="Failed to upload WordPress media",
        request_error_fields={"filename": request.filename},
    )
    resp = request_result.response

    if resp.status_code >= 500:
        _raise_http_server_error(
            ctx=ctx,
            event="wp_media_upload_http_error",
            code="wp_media_server_error",
            message_prefix="Media upload server error",
            resp=resp,
            fields={
                "url": url,
                "filename": request.filename,
                "used_pooled_session": request_result.used_pooled_session,
                "pool_key": request_result.pool_key,
                "pool_reused": request_result.pool_reused,
            },
        )
    if resp.status_code == 429:
        error_context = _http_error_context(resp)
        logger.info(
            log_event(
                ctx,
                role="service",
                event="wp_media_upload_rate_limited",
                module=logger.name,
                fields={
                    "url": url,
                    "filename": request.filename,
                    "used_pooled_session": request_result.used_pooled_session,
                    "pool_key": request_result.pool_key,
                    "pool_reused": request_result.pool_reused,
                    **error_context,
                },
            )
        )
        raise AppError(
            code="wp_media_rate_limited",
            message="Media upload rate limited: 429",
            retryable=True,
            context=error_context,
        )
    if resp.status_code >= 400:
        raise AppError(
            code="wp_media_client_error",
            message=f"Media upload client error: {resp.status_code}",
            retryable=False,
        )

    payload = _safe_json(resp.text)
    media_id = payload.get("id")
    source_url = payload.get("source_url")
    if not media_id or not source_url:
        raise AppError(
            code="wp_media_invalid_response",
            message="Media upload returned invalid response",
            retryable=False,
        )

    if request.alt_text:
        _update_media_alt_text(
            request.base_url,
            request.auth_header,
            media_id,
            request.alt_text,
            request.ssl_verify,
            request.ca_bundle_path,
            ctx,
        )

    logger.info(
        log_event(
            ctx,
            role="service",
            event="wp_media_upload_complete",
            module=logger.name,
            fields={
                "media_id": media_id,
                "source_url": source_url,
                "used_pooled_session": request_result.used_pooled_session,
                "pool_key": request_result.pool_key,
                "pool_reused": request_result.pool_reused,
            },
        )
    )
    return WordPressMediaUploadResponse(
        schema_version="1.0",
        media_id=int(media_id),
        source_url=str(source_url),
    )


def create_post(
    request: WordPressPostCreateRequest, ctx: RunContext
) -> WordPressPostCreateResponse:
    post_type_endpoint = _post_type_endpoint(request.post_type)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="wp_post_create_start",
            module=logger.name,
            fields={
                "title": request.title,
                "status": request.status,
                "slug": request.slug,
                "post_type": post_type_endpoint,
                "categories_count": len(request.categories or []),
                "tags_count": len(request.tags or []),
                "taxonomy_count": len(request.taxonomy_terms or {}),
                "ssl_verify": request.ssl_verify,
                "ca_bundle_path": request.ca_bundle_path or "",
            },
        )
    )
    url = f"{request.base_url.rstrip('/')}/wp-json/wp/v2/{post_type_endpoint}"
    headers = {
        "Authorization": request.auth_header,
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "title": request.title,
        "content": request.content_html,
        "status": request.status,
    }
    if request.slug:
        payload["slug"] = request.slug
    if request.featured_media:
        payload["featured_media"] = request.featured_media
    if request.categories:
        payload["categories"] = request.categories
    if request.tags:
        payload["tags"] = request.tags
    if request.taxonomy_terms:
        for taxonomy_rest_base, term_ids in request.taxonomy_terms.items():
            key = str(taxonomy_rest_base).strip()
            normalized_ids = [int(term_id) for term_id in term_ids if int(term_id) > 0]
            if key and normalized_ids:
                payload[key] = normalized_ids

    request_result = _execute_request(
        method="POST",
        url=url,
        headers=headers,
        data=json.dumps(payload),
        ssl_verify=request.ssl_verify,
        ca_bundle_path=request.ca_bundle_path,
        ctx=ctx,
        request_error_event="wp_post_create_request_error",
        request_error_code="wp_post_create_failed",
        request_error_message="Failed to create WordPress post",
        request_error_fields={"post_type": post_type_endpoint},
    )
    resp = request_result.response

    if resp.status_code >= 500:
        _raise_http_server_error(
            ctx=ctx,
            event="wp_post_create_http_error",
            code="wp_post_server_error",
            message_prefix="Post create server error",
            resp=resp,
            fields={
                "url": url,
                "post_type": post_type_endpoint,
                "used_pooled_session": request_result.used_pooled_session,
                "pool_key": request_result.pool_key,
                "pool_reused": request_result.pool_reused,
            },
        )
    if resp.status_code >= 400:
        raise AppError(
            code="wp_post_client_error",
            message=f"Post create client error: {resp.status_code}",
            retryable=False,
        )

    data = _safe_json(resp.text)
    post_id = data.get("id")
    link = data.get("link")
    status = data.get("status")
    if not post_id or not link:
        raise AppError(
            code="wp_post_invalid_response",
            message="Post create returned invalid response",
            retryable=False,
        )

    logger.info(
        log_event(
            ctx,
            role="service",
            event="wp_post_create_complete",
            module=logger.name,
            fields={
                "post_id": post_id,
                "link": link,
                "status": status,
                "used_pooled_session": request_result.used_pooled_session,
                "pool_key": request_result.pool_key,
                "pool_reused": request_result.pool_reused,
            },
        )
    )
    return WordPressPostCreateResponse(
        schema_version="1.0",
        post_id=int(post_id),
        link=str(link),
        status=str(status or request.status),
    )


def find_post_by_file_id(
    request: WordPressPostLookupRequest, ctx: RunContext
) -> WordPressPostLookupResponse:
    post_type_endpoint = _post_type_endpoint(request.post_type)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="wp_post_lookup_start",
            module=logger.name,
            fields={
                "file_id": request.file_id,
                "post_type": post_type_endpoint,
                "ssl_verify": request.ssl_verify,
                "ca_bundle_path": request.ca_bundle_path or "",
            },
        )
    )
    url = f"{request.base_url.rstrip('/')}/wp-json/wp/v2/{post_type_endpoint}"
    params = {
        "search": f"Drive fileId: {request.file_id}",
        "per_page": request.per_page,
    }
    headers = {"Authorization": request.auth_header}
    request_result = _execute_request(
        method="GET",
        url=url,
        headers=headers,
        params=params,
        allow_redirects=False,
        ssl_verify=request.ssl_verify,
        ca_bundle_path=request.ca_bundle_path,
        ctx=ctx,
        request_error_event="wp_post_lookup_request_error",
        request_error_code="wp_post_lookup_failed",
        request_error_message="Failed to lookup WordPress post",
        request_error_fields={"file_id": request.file_id},
    )
    resp = request_result.response

    if 300 <= resp.status_code < 400:
        _raise_http_redirect_error(
            ctx=ctx,
            event="wp_post_lookup_http_redirect",
            code="wp_post_lookup_redirected",
            message_prefix="Post lookup redirected unexpectedly",
            resp=resp,
            fields={
                "url": url,
                "file_id": request.file_id,
                "used_pooled_session": request_result.used_pooled_session,
                "pool_key": request_result.pool_key,
                "pool_reused": request_result.pool_reused,
            },
        )
    if resp.status_code >= 500:
        _raise_http_server_error(
            ctx=ctx,
            event="wp_post_lookup_http_error",
            code="wp_post_lookup_server_error",
            message_prefix="Post lookup server error",
            resp=resp,
            fields={
                "url": url,
                "file_id": request.file_id,
                "used_pooled_session": request_result.used_pooled_session,
                "pool_key": request_result.pool_key,
                "pool_reused": request_result.pool_reused,
            },
        )
    if resp.status_code >= 400:
        raise AppError(
            code="wp_post_lookup_client_error",
            message=f"Post lookup client error: {resp.status_code}",
            retryable=False,
        )

    try:
        payload = json.loads(resp.text)
    except json.JSONDecodeError:
        payload = []

    post_id = None
    link = None
    if isinstance(payload, list):
        for post in payload:
            content = (post or {}).get("content", {}).get("rendered", "")
            if request.file_id and request.file_id in content:
                post_id = post.get("id")
                link = post.get("link")
                break

    found = bool(post_id and link)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="wp_post_lookup_complete",
            module=logger.name,
            fields={
                "file_id": request.file_id,
                "found": found,
                "used_pooled_session": request_result.used_pooled_session,
                "pool_key": request_result.pool_key,
                "pool_reused": request_result.pool_reused,
            },
        )
    )
    return WordPressPostLookupResponse(
        schema_version="1.0",
        found=found,
        post_id=int(post_id) if post_id else None,
        link=str(link) if link else None,
    )


def find_posts_by_file_id_batch(
    request: WordPressPostLookupBatchRequest, ctx: RunContext
) -> WordPressPostLookupBatchResponse:
    normalized_file_ids: list[str] = []
    seen: set[str] = set()
    for raw_file_id in request.file_ids:
        file_id = str(raw_file_id or "").strip()
        if not file_id or file_id in seen:
            continue
        seen.add(file_id)
        normalized_file_ids.append(file_id)

    logger.info(
        log_event(
            ctx,
            role="service",
            event="wp_post_lookup_batch_start",
            module=logger.name,
            fields={
                "count": len(normalized_file_ids),
                "post_type": _post_type_endpoint(request.post_type),
                "ssl_verify": request.ssl_verify,
                "ca_bundle_path": request.ca_bundle_path or "",
            },
        )
    )

    items: list[WordPressPostLookupBatchItem] = []
    error_count = 0
    found_count = 0
    for file_id in normalized_file_ids:
        try:
            response = find_post_by_file_id(
                WordPressPostLookupRequest(
                    schema_version="1.0",
                    base_url=request.base_url,
                    auth_header=request.auth_header,
                    file_id=file_id,
                    ssl_verify=request.ssl_verify,
                    ca_bundle_path=request.ca_bundle_path,
                    per_page=request.per_page,
                    post_type=request.post_type,
                ),
                ctx,
            )
            if response.found:
                found_count += 1
            items.append(
                WordPressPostLookupBatchItem(
                    schema_version="1.0",
                    file_id=file_id,
                    found=response.found,
                    post_id=response.post_id,
                    link=response.link,
                )
            )
        except AppError as exc:
            error_count += 1
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="wp_post_lookup_batch_item_error",
                    module=logger.name,
                    fields={
                        "file_id": file_id,
                        "code": exc.code,
                        "retryable": exc.retryable,
                        "error": exc.message,
                    },
                )
            )
            items.append(
                WordPressPostLookupBatchItem(
                    schema_version="1.0",
                    file_id=file_id,
                    found=False,
                    error_code=exc.code,
                    error_message=exc.message,
                    retryable=exc.retryable,
                )
            )
        except Exception as exc:
            error_count += 1
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="wp_post_lookup_batch_item_error",
                    module=logger.name,
                    fields={
                        "file_id": file_id,
                        "error": str(exc),
                        "retryable": False,
                    },
                )
            )
            items.append(
                WordPressPostLookupBatchItem(
                    schema_version="1.0",
                    file_id=file_id,
                    found=False,
                    error_code="wp_post_lookup_unexpected_error",
                    error_message=str(exc),
                    retryable=False,
                )
            )

    logger.info(
        log_event(
            ctx,
            role="service",
            event="wp_post_lookup_batch_complete",
            module=logger.name,
            fields={
                "count": len(items),
                "found_count": found_count,
                "error_count": error_count,
            },
        )
    )
    return WordPressPostLookupBatchResponse(schema_version="1.0", items=items)


def _ensure_terms(
    *,
    ctx: RunContext,
    base_url: str,
    auth_header: str,
    terms: list[tuple[str, str]],
    ssl_verify: bool,
    ca_bundle_path: Optional[str],
    lookup_failed_code: str,
    lookup_failed_message: str,
    lookup_server_code: str,
    lookup_server_prefix: str,
    lookup_client_code: str,
    lookup_client_prefix: str,
    create_failed_code: str,
    create_failed_message: str,
    create_server_code: str,
    create_server_prefix: str,
    create_client_code: str,
    create_client_prefix: str,
    invalid_code: str,
    invalid_message: str,
) -> Dict[str, int]:
    slug_to_id: Dict[str, int] = {}
    headers = {
        "Authorization": auth_header,
        "Content-Type": "application/json",
    }
    for slug, name in terms:
        lookup_result = _execute_request(
            method="GET",
            url=base_url,
            headers={"Authorization": auth_header},
            params={"slug": slug},
            ssl_verify=ssl_verify,
            ca_bundle_path=ca_bundle_path,
            ctx=ctx,
            request_error_event="wp_taxonomy_lookup_request_error",
            request_error_code=lookup_failed_code,
            request_error_message=lookup_failed_message,
            request_error_fields={"base_url": base_url, "slug": slug},
        )
        resp = lookup_result.response

        if resp.status_code >= 500:
            _raise_http_server_error(
                ctx=ctx,
                event="wp_taxonomy_lookup_http_error",
                code=lookup_server_code,
                message_prefix=lookup_server_prefix,
                resp=resp,
                fields={
                    "base_url": base_url,
                    "slug": slug,
                    "used_pooled_session": lookup_result.used_pooled_session,
                    "pool_key": lookup_result.pool_key,
                    "pool_reused": lookup_result.pool_reused,
                },
            )
        if resp.status_code >= 400:
            raise AppError(
                code=lookup_client_code,
                message=f"{lookup_client_prefix}: {resp.status_code}",
                retryable=False,
            )

        term_id: Optional[int] = None
        try:
            payload = json.loads(resp.text)
        except json.JSONDecodeError:
            payload = []
        if isinstance(payload, list) and payload:
            term_id = payload[0].get("id")

        if not term_id:
            create_result = _execute_request(
                method="POST",
                url=base_url,
                headers=headers,
                data=json.dumps({"name": name, "slug": slug}),
                ssl_verify=ssl_verify,
                ca_bundle_path=ca_bundle_path,
                ctx=ctx,
                request_error_event="wp_taxonomy_create_request_error",
                request_error_code=create_failed_code,
                request_error_message=create_failed_message,
                request_error_fields={
                    "base_url": base_url,
                    "slug": slug,
                    "name": name,
                },
            )
            create_resp = create_result.response

            if create_resp.status_code >= 500:
                _raise_http_server_error(
                    ctx=ctx,
                    event="wp_taxonomy_create_http_error",
                    code=create_server_code,
                    message_prefix=create_server_prefix,
                    resp=create_resp,
                    fields={
                        "base_url": base_url,
                        "slug": slug,
                        "name": name,
                        "used_pooled_session": create_result.used_pooled_session,
                        "pool_key": create_result.pool_key,
                        "pool_reused": create_result.pool_reused,
                    },
                )
            if create_resp.status_code >= 400:
                raise AppError(
                    code=create_client_code,
                    message=f"{create_client_prefix}: {create_resp.status_code}",
                    retryable=False,
                )
            data = _safe_json(create_resp.text)
            term_id = data.get("id")

        if not term_id:
            raise AppError(
                code=invalid_code,
                message=invalid_message,
                retryable=False,
            )
        slug_to_id[slug] = int(term_id)
    return slug_to_id


def ensure_taxonomy_terms(
    request: WordPressTaxonomyEnsureRequest, ctx: RunContext
) -> WordPressTaxonomyEnsureResponse:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="wp_taxonomy_ensure_start",
            module=logger.name,
            fields={
                "taxonomy_rest_base": request.taxonomy_rest_base,
                "count": len(request.terms),
                "ssl_verify": request.ssl_verify,
                "ca_bundle_path": request.ca_bundle_path or "",
            },
        )
    )
    taxonomy_rest_base = request.taxonomy_rest_base.strip().strip("/")
    if taxonomy_rest_base == "":
        raise AppError(
            code="wp_taxonomy_invalid_rest_base",
            message="WordPress taxonomy REST base is required",
            retryable=False,
        )
    base_url = f"{request.base_url.rstrip('/')}/wp-json/wp/v2/{taxonomy_rest_base}"
    slug_to_id = _ensure_terms(
        ctx=ctx,
        base_url=base_url,
        auth_header=request.auth_header,
        terms=[(term.slug, term.name or term.slug) for term in request.terms],
        ssl_verify=request.ssl_verify,
        ca_bundle_path=request.ca_bundle_path,
        lookup_failed_code="wp_taxonomy_lookup_failed",
        lookup_failed_message="Failed to lookup WordPress taxonomy term",
        lookup_server_code="wp_taxonomy_lookup_server_error",
        lookup_server_prefix="Taxonomy lookup server error",
        lookup_client_code="wp_taxonomy_lookup_client_error",
        lookup_client_prefix="Taxonomy lookup client error",
        create_failed_code="wp_taxonomy_create_failed",
        create_failed_message="Failed to create WordPress taxonomy term",
        create_server_code="wp_taxonomy_create_server_error",
        create_server_prefix="Taxonomy create server error",
        create_client_code="wp_taxonomy_create_client_error",
        create_client_prefix="Taxonomy create client error",
        invalid_code="wp_taxonomy_invalid_response",
        invalid_message="Taxonomy ensure returned invalid response",
    )

    logger.info(
        log_event(
            ctx,
            role="service",
            event="wp_taxonomy_ensure_complete",
            module=logger.name,
            fields={
                "taxonomy_rest_base": taxonomy_rest_base,
                "count": len(slug_to_id),
            },
        )
    )
    return WordPressTaxonomyEnsureResponse(
        schema_version="1.0",
        slug_to_id=slug_to_id,
    )


def ensure_tags(
    request: WordPressTagEnsureRequest, ctx: RunContext
) -> WordPressTagEnsureResponse:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="wp_tag_ensure_start",
            module=logger.name,
            fields={
                "count": len(request.tags),
                "ssl_verify": request.ssl_verify,
                "ca_bundle_path": request.ca_bundle_path or "",
            },
        )
    )
    base_url = f"{request.base_url.rstrip('/')}/wp-json/wp/v2/tags"
    slug_to_id = _ensure_terms(
        ctx=ctx,
        base_url=base_url,
        auth_header=request.auth_header,
        terms=[(slug, slug) for slug in request.tags],
        ssl_verify=request.ssl_verify,
        ca_bundle_path=request.ca_bundle_path,
        lookup_failed_code="wp_tag_lookup_failed",
        lookup_failed_message="Failed to lookup WordPress tag",
        lookup_server_code="wp_tag_lookup_server_error",
        lookup_server_prefix="Tag lookup server error",
        lookup_client_code="wp_tag_lookup_client_error",
        lookup_client_prefix="Tag lookup client error",
        create_failed_code="wp_tag_create_failed",
        create_failed_message="Failed to create WordPress tag",
        create_server_code="wp_tag_create_server_error",
        create_server_prefix="Tag create server error",
        create_client_code="wp_tag_create_client_error",
        create_client_prefix="Tag create client error",
        invalid_code="wp_tag_invalid_response",
        invalid_message="Tag ensure returned invalid response",
    )

    logger.info(
        log_event(
            ctx,
            role="service",
            event="wp_tag_ensure_complete",
            module=logger.name,
            fields={"count": len(slug_to_id)},
        )
    )
    return WordPressTagEnsureResponse(schema_version="1.0", slug_to_id=slug_to_id)


def update_post_categories(
    request: WordPressPostUpdateRequest, ctx: RunContext
) -> WordPressPostUpdateResponse:
    post_type_endpoint = _post_type_endpoint(request.post_type)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="wp_post_update_start",
            module=logger.name,
            fields={
                "post_id": request.post_id,
                "categories": request.categories,
                "post_type": post_type_endpoint,
                "ssl_verify": request.ssl_verify,
                "ca_bundle_path": request.ca_bundle_path or "",
            },
        )
    )
    url = f"{request.base_url.rstrip('/')}/wp-json/wp/v2/{post_type_endpoint}/{request.post_id}"
    headers = {
        "Authorization": request.auth_header,
        "Content-Type": "application/json",
    }
    payload = {"categories": request.categories}
    request_result = _execute_request(
        method="POST",
        url=url,
        headers=headers,
        data=json.dumps(payload),
        ssl_verify=request.ssl_verify,
        ca_bundle_path=request.ca_bundle_path,
        ctx=ctx,
        request_error_event="wp_post_update_request_error",
        request_error_code="wp_post_update_failed",
        request_error_message="Failed to update WordPress post",
        request_error_fields={"post_id": request.post_id, "post_type": post_type_endpoint},
    )
    resp = request_result.response

    if resp.status_code >= 500:
        _raise_http_server_error(
            ctx=ctx,
            event="wp_post_update_http_error",
            code="wp_post_update_server_error",
            message_prefix="Post update server error",
            resp=resp,
            fields={
                "url": url,
                "post_id": request.post_id,
                "used_pooled_session": request_result.used_pooled_session,
                "pool_key": request_result.pool_key,
                "pool_reused": request_result.pool_reused,
            },
        )
    if resp.status_code >= 400:
        raise AppError(
            code="wp_post_update_client_error",
            message=f"Post update client error: {resp.status_code}",
            retryable=False,
        )
    data = _safe_json(resp.text)
    link = data.get("link")
    logger.info(
        log_event(
            ctx,
            role="service",
            event="wp_post_update_complete",
            module=logger.name,
            fields={
                "post_id": request.post_id,
                "used_pooled_session": request_result.used_pooled_session,
                "pool_key": request_result.pool_key,
                "pool_reused": request_result.pool_reused,
            },
        )
    )
    return WordPressPostUpdateResponse(
        schema_version="1.0", post_id=request.post_id, link=str(link) if link else None
    )


def _update_media_alt_text(
    base_url: str,
    auth_header: str,
    media_id: int,
    alt_text: str,
    ssl_verify: bool,
    ca_bundle_path: Optional[str],
    ctx: RunContext,
) -> None:
    url = f"{base_url.rstrip('/')}/wp-json/wp/v2/media/{media_id}"
    headers = {
        "Authorization": auth_header,
        "Content-Type": "application/json",
    }
    payload = {"alt_text": alt_text}
    try:
        request_result = _execute_request(
            method="POST",
            url=url,
            headers=headers,
            data=json.dumps(payload),
            ssl_verify=ssl_verify,
            ca_bundle_path=ca_bundle_path,
            ctx=ctx,
            request_error_event="wp_media_alt_text_request_error",
            request_error_code="wp_media_alt_text_failed",
            request_error_message="Failed to update WordPress media alt text",
            request_error_fields={"media_id": media_id},
        )
        resp = request_result.response
    except AppError:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="wp_media_alt_text_failed",
                module=logger.name,
                fields={"media_id": media_id},
            )
        )
        return

    if resp.status_code >= 400:
        logger.info(
        log_event(
            ctx,
            role="service",
            event="wp_media_alt_text_failed",
            module=logger.name,
            fields={
                "media_id": media_id,
                "status": resp.status_code,
                "used_pooled_session": request_result.used_pooled_session,
                "pool_key": request_result.pool_key,
                "pool_reused": request_result.pool_reused,
            },
        )
        )


def _safe_json(text: str) -> Dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}
