from __future__ import annotations
import logging
from typing import Any
import requests

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
)

from src.services._wordpress_service.posts import (
    upload_media,
    create_post,
    update_report_card,
    find_post_by_file_id,
    find_posts_by_file_id_batch,
    _update_media_alt_text,
)

from src.services._wordpress_service.taxonomy import (
    _ensure_terms,
    ensure_taxonomy_terms,
    ensure_tags,
    update_post_categories,
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
    "upload_media",
    "create_post",
    "update_report_card",
    "find_post_by_file_id",
    "find_posts_by_file_id_batch",
    "_update_media_alt_text",
    "_ensure_terms",
    "ensure_taxonomy_terms",
    "ensure_tags",
    "update_post_categories",
]
