from __future__ import annotations
import json
import logging
from typing import Any, Dict, NoReturn, Optional
import requests
from src.contracts.run_context import RunContext
from src.contracts.wordpress import (
    WordPressPostUpdateRequest,
    WordPressPostUpdateResponse,
    WordPressTagEnsureRequest,
    WordPressTagEnsureResponse,
    WordPressTaxonomyEnsureRequest,
    WordPressTaxonomyEnsureResponse,
    WordPressTaxonomyTerm,
)
from src.utils.errors import AppError
from src.utils.logging import log_event
from .budget import (
    assert_wordpress_write_authority,
    finalize_wordpress_write_authority,
)

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
TOPIC_DEFINITION_META = "ml_topic_definition"
TOPIC_INCLUDE_WHEN_META = "ml_topic_include_when"
TOPIC_EXCLUDE_WHEN_META = "ml_topic_exclude_when"
TOPIC_SCHEMA_VERSION_META = "ml_topic_schema_version"
_ORIGINAL_REQUEST_CALLS: dict[str, Any] = {
    "GET": requests.get,
    "POST": requests.post,
}


def _ensure_terms(
    *,
    ctx: RunContext,
    base_url: str,
    auth_header: str,
    terms: list[WordPressTaxonomyTerm],
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
    for term in terms:
        slug = term.slug
        name = term.name or term.slug
        term_payload = _term_payload(term)
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
                data=json.dumps(term_payload),
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
            if term_id and _term_semantics_payload(term):
                _validate_term_semantics_readback(
                    ctx=ctx,
                    base_url=base_url,
                    term=term,
                    term_id=int(term_id),
                    auth_header=auth_header,
                    ssl_verify=ssl_verify,
                    ca_bundle_path=ca_bundle_path,
                    lookup_failed_code=lookup_failed_code,
                    lookup_failed_message=lookup_failed_message,
                    lookup_server_code=lookup_server_code,
                    lookup_server_prefix=lookup_server_prefix,
                    lookup_client_code=lookup_client_code,
                    lookup_client_prefix=lookup_client_prefix,
                )
        elif _term_semantics_payload(term):
            _update_term_semantics(
                ctx=ctx,
                base_url=base_url,
                term_id=int(term_id),
                auth_header=auth_header,
                payload=term_payload,
                ssl_verify=ssl_verify,
                ca_bundle_path=ca_bundle_path,
                update_failed_code=create_failed_code,
                update_failed_message=create_failed_message,
                update_server_code=create_server_code,
                update_server_prefix=create_server_prefix,
                update_client_code=create_client_code,
                update_client_prefix=create_client_prefix,
            )
            _validate_term_semantics_readback(
                ctx=ctx,
                base_url=base_url,
                term=term,
                term_id=int(term_id),
                auth_header=auth_header,
                ssl_verify=ssl_verify,
                ca_bundle_path=ca_bundle_path,
                lookup_failed_code=lookup_failed_code,
                lookup_failed_message=lookup_failed_message,
                lookup_server_code=lookup_server_code,
                lookup_server_prefix=lookup_server_prefix,
                lookup_client_code=lookup_client_code,
                lookup_client_prefix=lookup_client_prefix,
            )

        if not term_id:
            raise AppError(
                code=invalid_code,
                message=invalid_message,
                retryable=False,
            )
        slug_to_id[slug] = int(term_id)
    return slug_to_id


def _term_semantics_payload(term: WordPressTaxonomyTerm) -> dict[str, object]:
    meta: dict[str, object] = {}
    if term.definition.strip():
        meta[TOPIC_DEFINITION_META] = term.definition.strip()
    include_when = [value.strip() for value in term.include_when if value.strip()]
    if include_when:
        meta[TOPIC_INCLUDE_WHEN_META] = include_when
    exclude_when = [value.strip() for value in term.exclude_when if value.strip()]
    if exclude_when:
        meta[TOPIC_EXCLUDE_WHEN_META] = exclude_when
    if term.semantics_version.strip():
        meta[TOPIC_SCHEMA_VERSION_META] = term.semantics_version.strip()
    return meta


def _term_payload(term: WordPressTaxonomyTerm) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": term.name or term.slug,
        "slug": term.slug,
    }
    if term.description.strip():
        payload["description"] = term.description.strip()
    meta = _term_semantics_payload(term)
    if meta:
        payload["meta"] = meta
    return payload


def _update_term_semantics(
    *,
    ctx: RunContext,
    base_url: str,
    term_id: int,
    auth_header: str,
    payload: dict[str, object],
    ssl_verify: bool,
    ca_bundle_path: Optional[str],
    update_failed_code: str,
    update_failed_message: str,
    update_server_code: str,
    update_server_prefix: str,
    update_client_code: str,
    update_client_prefix: str,
) -> None:
    update_result = _execute_request(
        method="POST",
        url=f"{base_url.rstrip('/')}/{term_id}",
        headers={
            "Authorization": auth_header,
            "Content-Type": "application/json",
        },
        data=json.dumps(payload),
        ssl_verify=ssl_verify,
        ca_bundle_path=ca_bundle_path,
        ctx=ctx,
        request_error_event="wp_taxonomy_update_request_error",
        request_error_code=update_failed_code,
        request_error_message=update_failed_message,
        request_error_fields={"base_url": base_url, "term_id": term_id},
    )
    resp = update_result.response
    if resp.status_code >= 500:
        _raise_http_server_error(
            ctx=ctx,
            event="wp_taxonomy_update_http_error",
            code=update_server_code,
            message_prefix=update_server_prefix,
            resp=resp,
            fields={
                "base_url": base_url,
                "term_id": term_id,
                "used_pooled_session": update_result.used_pooled_session,
                "pool_key": update_result.pool_key,
                "pool_reused": update_result.pool_reused,
            },
        )
    if resp.status_code >= 400:
        raise AppError(
            code=update_client_code,
            message=f"{update_client_prefix}: {resp.status_code}",
            retryable=False,
        )


def _validate_term_semantics_readback(
    *,
    ctx: RunContext,
    base_url: str,
    term: WordPressTaxonomyTerm,
    term_id: int,
    auth_header: str,
    ssl_verify: bool,
    ca_bundle_path: Optional[str],
    lookup_failed_code: str,
    lookup_failed_message: str,
    lookup_server_code: str,
    lookup_server_prefix: str,
    lookup_client_code: str,
    lookup_client_prefix: str,
) -> None:
    expected_meta = _term_semantics_payload(term)
    readback_result = _execute_request(
        method="GET",
        url=base_url,
        headers={"Authorization": auth_header},
        params={"slug": term.slug, "context": "edit"},
        ssl_verify=ssl_verify,
        ca_bundle_path=ca_bundle_path,
        ctx=ctx,
        request_error_event="wp_taxonomy_semantics_readback_request_error",
        request_error_code=lookup_failed_code,
        request_error_message=lookup_failed_message,
        request_error_fields={"base_url": base_url, "slug": term.slug},
    )
    resp = readback_result.response
    if resp.status_code >= 500:
        _raise_http_server_error(
            ctx=ctx,
            event="wp_taxonomy_semantics_readback_http_error",
            code=lookup_server_code,
            message_prefix=lookup_server_prefix,
            resp=resp,
            fields={
                "base_url": base_url,
                "slug": term.slug,
                "used_pooled_session": readback_result.used_pooled_session,
                "pool_key": readback_result.pool_key,
                "pool_reused": readback_result.pool_reused,
            },
        )
    if resp.status_code >= 400:
        raise AppError(
            code=lookup_client_code,
            message=f"{lookup_client_prefix}: {resp.status_code}",
            retryable=False,
        )

    payload = _safe_json(resp.text)
    if not isinstance(payload, list):
        _raise_term_semantics_readback_mismatch(
            term=term,
            term_id=term_id,
            reason="readback_payload_not_list",
            expected_meta=expected_meta,
        )
    readback_term = next(
        (
            item
            for item in payload
            if isinstance(item, dict) and int(item.get("id") or 0) == term_id
        ),
        None,
    )
    if not isinstance(readback_term, dict):
        _raise_term_semantics_readback_mismatch(
            term=term,
            term_id=term_id,
            reason="readback_term_missing",
            expected_meta=expected_meta,
        )

    if (
        term.description.strip()
        and readback_term.get("description") != term.description.strip()
    ):
        _raise_term_semantics_readback_mismatch(
            term=term,
            term_id=term_id,
            reason="description_mismatch",
            expected_meta=expected_meta,
        )

    readback_meta = readback_term.get("meta")
    if not isinstance(readback_meta, dict):
        _raise_term_semantics_readback_mismatch(
            term=term,
            term_id=term_id,
            reason="meta_missing",
            expected_meta=expected_meta,
        )
    for key, expected_value in expected_meta.items():
        if readback_meta.get(key) != expected_value:
            _raise_term_semantics_readback_mismatch(
                term=term,
                term_id=term_id,
                reason=f"meta_mismatch:{key}",
                expected_meta=expected_meta,
            )


def _raise_term_semantics_readback_mismatch(
    *,
    term: WordPressTaxonomyTerm,
    term_id: int,
    reason: str,
    expected_meta: dict[str, object],
) -> NoReturn:
    raise AppError(
        code="wp_taxonomy_semantics_readback_mismatch",
        message="WordPress taxonomy term semantics failed REST readback validation",
        retryable=False,
        severity="error",
        context={
            "term_id": term_id,
            "slug": term.slug,
            "reason": reason,
            "expected_meta_keys": sorted(expected_meta),
        },
    )


def ensure_taxonomy_terms(
    request: WordPressTaxonomyEnsureRequest, ctx: RunContext
) -> WordPressTaxonomyEnsureResponse:
    authority_budget, authority_decision = assert_wordpress_write_authority(
        request,
        ctx,
        operation="taxonomy_ensure",
        estimated_writes=max(1, len(request.terms)),
    )
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
        terms=list(request.terms),
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
    response = WordPressTaxonomyEnsureResponse(
        schema_version="1.0",
        slug_to_id=slug_to_id,
    )
    finalize_wordpress_write_authority(
        budget=authority_budget,
        decision=authority_decision,
        ctx=ctx,
        outcome="completed",
        actual_writes=len(request.terms),
    )
    return response


def ensure_tags(
    request: WordPressTagEnsureRequest, ctx: RunContext
) -> WordPressTagEnsureResponse:
    authority_budget, authority_decision = assert_wordpress_write_authority(
        request,
        ctx,
        operation="tag_ensure",
        estimated_writes=max(1, len(request.tags)),
    )
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
        terms=[
            WordPressTaxonomyTerm(schema_version="1.0", slug=slug, name=slug)
            for slug in request.tags
        ],
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
    response = WordPressTagEnsureResponse(
        schema_version="1.0", slug_to_id=slug_to_id
    )
    finalize_wordpress_write_authority(
        budget=authority_budget,
        decision=authority_decision,
        ctx=ctx,
        outcome="completed",
        actual_writes=len(request.tags),
    )
    return response


def update_post_categories(
    request: WordPressPostUpdateRequest, ctx: RunContext
) -> WordPressPostUpdateResponse:
    authority_budget, authority_decision = assert_wordpress_write_authority(
        request, ctx, operation="post_update"
    )
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
    response = WordPressPostUpdateResponse(
        schema_version="1.0", post_id=request.post_id, link=str(link) if link else None
    )
    finalize_wordpress_write_authority(
        budget=authority_budget,
        decision=authority_decision,
        ctx=ctx,
        outcome="completed",
        actual_writes=1,
    )
    return response


__all__ = [
    "_ensure_terms",
    "_term_payload",
    "_term_semantics_payload",
    "ensure_taxonomy_terms",
    "ensure_tags",
    "update_post_categories",
]
