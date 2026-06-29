from __future__ import annotations
import logging
from typing import Any
import requests

from src.contracts.publish import PublishSettings
from src.contracts.run_context import RunContext
from src.contracts.wordpress import (
    WordPressAuthSettings,
    WordPressPublishTargetPreflightRequest,
    WordPressPublishTargetPreflightResponse,
)
from src.services._wordpress_service.transport import (
    _WordPressRequestResult,
    _SessionPool,
    _SESSION_POOL,
    _post_type_endpoint,
    _requests_verify,
    _build_session,
    _session_pool_key,
    _rest_query_fallback_url,
    _should_retry_rest_query_mode,
    _patched_direct_transport,
    _execute_request,
    _suppress_insecure_request_warning,
    _truncate_text,
    _sanitize_response_headers,
    _http_error_context,
    _raise_request_exception,
    _raise_http_server_error,
    _raise_http_redirect_error,
    _safe_json,
    preflight_publish_target as _preflight_publish_target_request,
)

from src.services._wordpress_service.posts import (
    upload_media,
    create_post,
    update_card,
    find_post_by_file_id,
    find_posts_by_file_id_batch,
    _update_media_alt_text,
)

from src.services._wordpress_service.media import prepare_media_upload

from src.services._wordpress_service.taxonomy import (
    _ensure_terms,
    ensure_taxonomy_terms,
    ensure_tags,
    update_post_categories,
)
from src.utils.wp_auth import build_auth_header

# Preserve the report-only entrypoint while card updates become entity-agnostic.
update_report_card = update_card

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


def preflight_publish_target(
    settings: PublishSettings | WordPressAuthSettings, ctx: RunContext
) -> WordPressPublishTargetPreflightResponse:
    wp = settings.wp if hasattr(settings, "wp") else settings
    auth_header = build_auth_header(
        username=getattr(wp, "username", None),
        app_password=getattr(wp, "app_password", None),
        bearer_token=getattr(wp, "bearer_token", None),
    )
    return _preflight_publish_target_request(
        WordPressPublishTargetPreflightRequest(
            schema_version="1.0",
            base_url=wp.site_url,
            auth_header=auth_header,
            post_type=wp.post_type,
            ssl_verify=wp.ssl_verify,
            ca_bundle_path=wp.ca_bundle_path,
        ),
        ctx,
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
    "preflight_publish_target",
    "upload_media",
    "prepare_media_upload",
    "create_post",
    "update_card",
    "update_report_card",
    "find_post_by_file_id",
    "find_posts_by_file_id_batch",
    "_update_media_alt_text",
    "_ensure_terms",
    "ensure_taxonomy_terms",
    "ensure_tags",
    "update_post_categories",
]
