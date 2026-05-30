"""Inspectable browser helper compatibility facade for report downloads.

This module remains the stable private import surface for browser report
download helpers. Focused implementation lives in `_helpers.state`,
`_helpers.inspection`, and `_helpers.interaction`; callers continue importing
from `src.services._browser_report_download.helpers`.
"""

from __future__ import annotations

from src.services._browser_report_download._helpers.inspection import (
    _JS_SNIPPET_CHARS,
    _JavaScriptEvaluationError,
    browser_helper_js,
    browser_helper_js_async,
    _js_failure,
    _adapt_js_result_value,
    _coerce_json_envelope,
    _wrap_js_expression,
    _looks_like_js_function,
    _looks_like_statement_script,
    _is_js_error_envelope,
    _unwrap_js_success_envelope,
    _is_json_serializable,
    _coerce_optional_int,
    _extract_error_location,
    _snippet,
)
from src.services._browser_report_download._helpers.interaction import (
    browser_helper_capture_screenshot,
    browser_helper_form_autocomplete,
    _autocomplete_result,
    _screenshot_result,
    _try_screenshot_call,
)
from src.services._browser_report_download._helpers.state import (
    _HELPER_SCHEMA_VERSION,
    _HTML_EXCERPT_CHARS,
    _HELPER_AWAIT_TIMEOUT_SECONDS,
    _INTERNAL_TARGET_URL_PREFIXES,
    browser_helper_page_info,
    _first_non_empty,
    _looks_like_browser_use_session,
    _read_browser_url,
    _read_browser_title,
    _read_browser_html,
    _read_browser_current_page_url,
    _read_browser_current_page_title,
    _read_page_url,
    _read_page_title,
    _read_page_html,
    _is_real_tab_url,
    _maybe_await,
    _await_async,
    _excerpt,
)

__all__ = (
    "get_browser_helper_surface",
    "_HELPER_SCHEMA_VERSION",
    "_HTML_EXCERPT_CHARS",
    "_HELPER_AWAIT_TIMEOUT_SECONDS",
    "_INTERNAL_TARGET_URL_PREFIXES",
    "browser_helper_page_info",
    "_first_non_empty",
    "_looks_like_browser_use_session",
    "_read_browser_url",
    "_read_browser_title",
    "_read_browser_html",
    "_read_browser_current_page_url",
    "_read_browser_current_page_title",
    "_read_page_url",
    "_read_page_title",
    "_read_page_html",
    "_is_real_tab_url",
    "_maybe_await",
    "_await_async",
    "_excerpt",
    "_JS_SNIPPET_CHARS",
    "_JavaScriptEvaluationError",
    "browser_helper_js",
    "browser_helper_js_async",
    "_js_failure",
    "_adapt_js_result_value",
    "_coerce_json_envelope",
    "_wrap_js_expression",
    "_looks_like_js_function",
    "_looks_like_statement_script",
    "_is_js_error_envelope",
    "_unwrap_js_success_envelope",
    "_is_json_serializable",
    "_coerce_optional_int",
    "_extract_error_location",
    "_snippet",
    "browser_helper_capture_screenshot",
    "browser_helper_form_autocomplete",
    "_autocomplete_result",
    "_screenshot_result",
    "_try_screenshot_call",
)


def get_browser_helper_surface() -> dict[str, str]:
    return {
        "page_info": "Read bounded URL/title/HTML metadata from the active page.",
        "capture_screenshot": "Persist a screenshot through browser, page, or CDP hooks.",
        "js": "Run bounded JavaScript inspection and return structured values.",
        "form_autocomplete": "Recover required form autocompletes with keyboard-style input and verified selection.",
    }
