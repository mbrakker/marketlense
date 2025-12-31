from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

import requests

from src.contracts.run_context import RunContext
from src.contracts.wordpress import (
    WordPressMediaUploadRequest,
    WordPressMediaUploadResponse,
    WordPressPostCreateRequest,
    WordPressPostCreateResponse,
    WordPressPostLookupRequest,
    WordPressPostLookupResponse,
)
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.wordpress_service")

DEFAULT_TIMEOUT = 30


def upload_media(request: WordPressMediaUploadRequest, ctx: RunContext) -> WordPressMediaUploadResponse:
    logger.info(log_event(
        ctx,
        role="service",
        event="wp_media_upload_start",
        module=logger.name,
        fields={
            "filename": request.filename,
            "mime_type": request.mime_type,
            "size": len(request.data),
        },
    ))
    url = f"{request.base_url.rstrip('/')}/wp-json/wp/v2/media"
    headers = {
        "Authorization": request.auth_header,
    }
    files = {
        "file": (request.filename, request.data, request.mime_type),
    }
    try:
        resp = requests.post(url, headers=headers, files=files, timeout=DEFAULT_TIMEOUT)
    except requests.RequestException as exc:
        raise AppError(
            code="wp_media_upload_failed",
            message="Failed to upload WordPress media",
            cause=exc,
            retryable=True,
        ) from exc

    if resp.status_code >= 500:
        raise AppError(
            code="wp_media_server_error",
            message=f"Media upload server error: {resp.status_code}",
            retryable=True,
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
        _update_media_alt_text(request.base_url, request.auth_header, media_id, request.alt_text, ctx)

    logger.info(log_event(
        ctx,
        role="service",
        event="wp_media_upload_complete",
        module=logger.name,
        fields={"media_id": media_id, "source_url": source_url},
    ))
    return WordPressMediaUploadResponse(
        schema_version="1.0",
        media_id=int(media_id),
        source_url=str(source_url),
    )


def create_post(request: WordPressPostCreateRequest, ctx: RunContext) -> WordPressPostCreateResponse:
    logger.info(log_event(
        ctx,
        role="service",
        event="wp_post_create_start",
        module=logger.name,
        fields={"title": request.title, "status": request.status, "slug": request.slug},
    ))
    url = f"{request.base_url.rstrip('/')}/wp-json/wp/v2/posts"
    headers = {
        "Authorization": request.auth_header,
        "Content-Type": "application/json",
    }
    payload = {
        "title": request.title,
        "content": request.content_html,
        "status": request.status,
    }
    if request.slug:
        payload["slug"] = request.slug
    if request.featured_media:
        payload["featured_media"] = request.featured_media

    try:
        resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=DEFAULT_TIMEOUT)
    except requests.RequestException as exc:
        raise AppError(
            code="wp_post_create_failed",
            message="Failed to create WordPress post",
            cause=exc,
            retryable=True,
        ) from exc

    if resp.status_code >= 500:
        raise AppError(
            code="wp_post_server_error",
            message=f"Post create server error: {resp.status_code}",
            retryable=True,
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

    logger.info(log_event(
        ctx,
        role="service",
        event="wp_post_create_complete",
        module=logger.name,
        fields={"post_id": post_id, "link": link, "status": status},
    ))
    return WordPressPostCreateResponse(
        schema_version="1.0",
        post_id=int(post_id),
        link=str(link),
        status=str(status or request.status),
    )


def find_post_by_file_id(request: WordPressPostLookupRequest, ctx: RunContext) -> WordPressPostLookupResponse:
    logger.info(log_event(
        ctx,
        role="service",
        event="wp_post_lookup_start",
        module=logger.name,
        fields={"file_id": request.file_id},
    ))
    url = f"{request.base_url.rstrip('/')}/wp-json/wp/v2/posts"
    params = {
        "search": f"Drive fileId: {request.file_id}",
        "per_page": request.per_page,
    }
    headers = {"Authorization": request.auth_header}
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=DEFAULT_TIMEOUT)
    except requests.RequestException as exc:
        raise AppError(
            code="wp_post_lookup_failed",
            message="Failed to lookup WordPress post",
            cause=exc,
            retryable=True,
        ) from exc

    if resp.status_code >= 500:
        raise AppError(
            code="wp_post_lookup_server_error",
            message=f"Post lookup server error: {resp.status_code}",
            retryable=True,
        )
    if resp.status_code >= 400:
        raise AppError(
            code="wp_post_lookup_client_error",
            message=f"Post lookup client error: {resp.status_code}",
            retryable=False,
        )

    try:
        payload = json.loads(resp.text)
    except Exception:
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
    logger.info(log_event(
        ctx,
        role="service",
        event="wp_post_lookup_complete",
        module=logger.name,
        fields={"file_id": request.file_id, "found": found},
    ))
    return WordPressPostLookupResponse(
        schema_version="1.0",
        found=found,
        post_id=int(post_id) if post_id else None,
        link=str(link) if link else None,
    )


def _update_media_alt_text(
    base_url: str,
    auth_header: str,
    media_id: int,
    alt_text: str,
    ctx: RunContext,
) -> None:
    url = f"{base_url.rstrip('/')}/wp-json/wp/v2/media/{media_id}"
    headers = {
        "Authorization": auth_header,
        "Content-Type": "application/json",
    }
    payload = {"alt_text": alt_text}
    try:
        resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=DEFAULT_TIMEOUT)
    except requests.RequestException:
        logger.info(log_event(
            ctx,
            role="service",
            event="wp_media_alt_text_failed",
            module=logger.name,
            fields={"media_id": media_id},
        ))
        return

    if resp.status_code >= 400:
        logger.info(log_event(
            ctx,
            role="service",
            event="wp_media_alt_text_failed",
            module=logger.name,
            fields={"media_id": media_id, "status": resp.status_code},
        ))


def _safe_json(text: str) -> Dict[str, Any]:
    try:
        return json.loads(text)
    except Exception:
        return {}
