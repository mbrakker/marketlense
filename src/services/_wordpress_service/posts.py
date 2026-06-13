from __future__ import annotations
import json
import logging
from typing import Any, Optional
import requests
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
    WordPressReportCardUpdateRequest,
    WordPressPostUpdateResponse,
)
from src.utils.errors import AppError
from src.utils.logging import log_event

from .transport import (
    _execute_request,
    _http_error_context,
    _post_type_endpoint,
    _raise_http_redirect_error,
    _raise_http_server_error,
    _safe_json,
)

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
                "meta_count": len(request.meta or {}),
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
    if request.meta:
        payload["meta"] = dict(request.meta)
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


def update_report_card(
    request: WordPressReportCardUpdateRequest, ctx: RunContext
) -> WordPressPostUpdateResponse:
    post_type_endpoint = _post_type_endpoint(request.post_type)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="wp_report_card_update_start",
            module=logger.name,
            fields={
                "post_id": request.post_id,
                "post_type": post_type_endpoint,
                "featured_media": request.featured_media,
                "meta_count": len(request.meta),
                "ssl_verify": request.ssl_verify,
                "ca_bundle_path": request.ca_bundle_path or "",
            },
        )
    )
    url = (
        f"{request.base_url.rstrip('/')}/wp-json/wp/v2/"
        f"{post_type_endpoint}/{request.post_id}"
    )
    headers = {
        "Authorization": request.auth_header,
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "featured_media": request.featured_media,
        "meta": dict(request.meta),
    }

    request_result = _execute_request(
        method="POST",
        url=url,
        headers=headers,
        data=json.dumps(payload),
        ssl_verify=request.ssl_verify,
        ca_bundle_path=request.ca_bundle_path,
        ctx=ctx,
        request_error_event="wp_report_card_update_request_error",
        request_error_code="wp_report_card_update_failed",
        request_error_message="Failed to update WordPress report-card metadata",
        request_error_fields={
            "post_id": request.post_id,
            "post_type": post_type_endpoint,
        },
    )
    resp = request_result.response
    if resp.status_code >= 500:
        _raise_http_server_error(
            ctx=ctx,
            event="wp_report_card_update_http_error",
            code="wp_report_card_update_server_error",
            message_prefix="Report-card update server error",
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
            code="wp_report_card_update_client_error",
            message=f"Report-card update client error: {resp.status_code}",
            retryable=False,
        )

    data = _safe_json(resp.text)
    post_id = data.get("id")
    link = data.get("link")
    if int(post_id or 0) != request.post_id or not link:
        raise AppError(
            code="wp_report_card_update_invalid_response",
            message="Report-card update returned invalid response",
            retryable=False,
        )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="wp_report_card_update_complete",
            module=logger.name,
            fields={
                "post_id": request.post_id,
                "link": link,
                "used_pooled_session": request_result.used_pooled_session,
                "pool_key": request_result.pool_key,
                "pool_reused": request_result.pool_reused,
            },
        )
    )
    return WordPressPostUpdateResponse(
        schema_version="1.0",
        post_id=request.post_id,
        link=str(link),
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


__all__ = [
    "upload_media",
    "create_post",
    "find_post_by_file_id",
    "find_posts_by_file_id_batch",
    "_update_media_alt_text",
]
