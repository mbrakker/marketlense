from __future__ import annotations
import json
import logging
from typing import Any, Dict, Optional
import requests
from src.contracts.run_context import RunContext
from src.contracts.wordpress import (
    WordPressPostUpdateRequest,
    WordPressPostUpdateResponse,
    WordPressTagEnsureRequest,
    WordPressTagEnsureResponse,
    WordPressTaxonomyEnsureRequest,
    WordPressTaxonomyEnsureResponse,
)
from src.utils.errors import AppError
from src.utils.logging import log_event

from .transport import (
    _execute_request,
    _post_type_endpoint,
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
        request_error_fields={
            "post_id": request.post_id,
            "post_type": post_type_endpoint,
        },
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


__all__ = [
    "_ensure_terms",
    "ensure_taxonomy_terms",
    "ensure_tags",
    "update_post_categories",
]
