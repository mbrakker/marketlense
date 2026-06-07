from __future__ import annotations

# ruff: noqa: F401

from ._fetch.parsing import (
    HTTP_BROWSER_HEADERS,
    _WORDPRESS_AJAX_CONFIG_RE,
    _WORDPRESS_ACTION_RE,
    _SCRIPT_SRC_RE,
    _HTML_TITLE_RE,
    _ASSET_TYPE_TERMS,
    _DOWNLOAD_LANGUAGE_MARKERS,
    _GATED_FORM_MARKERS,
    _DOCUMENT_STRUCTURE_MARKERS,
    _PRINT_LANGUAGE_MARKERS,
    _PURCHASE_MARKERS,
    _EDITORIAL_URL_MARKERS,
    _EDITORIAL_MARKERS,
    _RELATED_POST_MARKERS,
    _NEWSLETTER_MARKERS,
    _CONTACT_SALES_MARKERS,
    _DEAD_PAGE_MARKERS,
    _TRANSIENT_HTTP_STATUS_CODES,
    _PROTECTED_DOCUMENT_HTTP_STATUS_CODES,
    _INVENTORY_HTML_MAX_BYTES,
    _SCRIPT_FETCH_MAX_BYTES,
    _LANDING_PAGE_HTML_MAX_BYTES,
    _InventoryHtmlParser,
    _LandingPageInspectionHtmlParser,
)
from ._fetch.discovery import (
    logger,
    discover_inventory_via_http,
    _discover_inventory_via_wordpress_ajax,
    _extract_html_page_title,
    _http_request_url_candidates,
    _should_try_wordpress_ajax_supplement,
    _extract_wordpress_ajax_config,
    _discover_wordpress_ajax_actions,
    _same_host_script_urls,
    _score_wordpress_ajax_action,
)
from ._fetch.classification import (
    _contains_any_marker,
    _has_editorial_url_pattern,
    _contains_price_signal,
    _classify_source_surface,
    _classify_verification,
    _candidate_provenance_counts,
)
from ._fetch.inspection import (
    inspect_inventory_landing_pages,
    _inspect_landing_page_item,
    _dead_observation,
)
