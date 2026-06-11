from __future__ import annotations
import logging
import re

from src.orchestrators._report_download_orchestrator._route_planner.planning import (
    plan_report_download_routes,
    _build_plan,
    _build_browser_step,
    _planning_reason,
)

from src.orchestrators._report_download_orchestrator._route_planner.policy import (
    _preferred_policy_signal,
    _preferred_publisher_policy_signal,
    _publisher_policy_signal_matches_context,
    _apply_policy_route_family,
    _policy_step_name,
    _route_kind_hint_for_policy_family,
    _default_route_family_for_kind,
    _should_reuse_memory_route,
    _has_actionable_email_memory_hint,
    _canonical_memory_route_family,
)

from src.orchestrators._report_download_orchestrator._route_planner.recovery import (
    _browser_to_http_recovery_decision,
    _has_http_probe_signal,
    _annotate_recovery_steps,
    _dedupe_steps,
)

from src.orchestrators._report_download_orchestrator._route_planner.url_rules import (
    _clean_string_list,
    _looks_like_pdf,
    _looks_like_listing_url,
    _looks_like_tracker_url,
    _tracker_path_query_tokens,
    _extract_tracker_target_url,
    _classify_redirect_target,
    _looks_like_editorial_report_url,
    _looks_like_onsite_longread_url,
    _looks_like_email_form_url,
    _looks_like_direct_onsite_report_url,
    _path_has_direct_onsite_report_phrase,
    _onsite_capture_route_steps,
    _path_has_email_gate_marker,
    _looks_like_probable_gated_report_detail_url,
)

logger = logging.getLogger("market_lense.report_download_route_planner")
_BROWSER_DISCOVERY_PROVENANCES = {
    "browser_dom",
    "browser_rendered_html_supplement",
}
_PDF_FIRST_DISCOVERY_PROVENANCES = {
    "direct_pdf_source",
}
_TRACKER_HOST_MARKERS = {
    "lnk",
    "trk",
    "click",
    "go",
    "email",
    "hubspot",
    "pardot",
    "marketo",
}
_TRACKER_SHORT_PATH_MARKERS = {
    "go",
    "lnk",
    "trk",
}
_LISTING_PATH_MARKERS = {
    "insights",
    "reports",
    "research",
    "resources",
    "publications",
    "library",
}
_EDITORIAL_NON_REPORT_MARKERS = {
    "blog",
    "news",
    "press",
    "case-study",
    "case_study",
    "webinar",
}
_EDITORIAL_REPORT_MARKERS = {
    "report",
    "reports",
    "guide",
    "guides",
    "insight",
    "insights",
    "playbook",
    "research",
    "analysis",
    "study",
    "survey",
    "trend",
    "trends",
    "whitepaper",
    "whitepapers",
}
_BROWSER_TO_HTTP_RECOVERY_CLASS = "browser_to_http_pdf_probe"
_DIRECT_PDF_RECOVERY_CLASS = "direct_pdf_probe"
_HTTP_PDF_RECOVERY_CLASS = "http_pdf_probe"
_REPORT_DETAIL_SIGNAL_MARKERS = {
    "benchmark",
    "download",
    "ebook",
    "e-book",
    "guide",
    "market",
    "outlook",
    "playbook",
    "predictions",
    "report",
    "research",
    "study",
    "survey",
    "trend",
    "trends",
    "whitepaper",
    "white paper",
}
_EMAIL_GATE_PATH_MARKERS = {
    "gated-content-form",
    "download",
    "downloads",
    "ebook",
    "ebooks",
    "whitepaper",
    "whitepapers",
    "asset",
    "assets",
    "register",
    "form",
}
_EMAIL_GATE_PARENT_SEGMENTS = {
    "report",
    "reports",
    "resources",
}
_EMAIL_GATE_DETAIL_TITLE_MARKERS = {
    "benchmark",
    "ebook",
    "e-book",
    "guide",
    "outlook",
    "predictions",
    "report",
    "research",
    "study",
    "trends",
    "whitepaper",
    "white paper",
}
_ONSITE_LONGREAD_SEGMENTS = {
    "insight",
    "insights",
    "research",
    "analysis",
    "survey",
    "outlook",
}
_DIRECT_ONSITE_REPORT_SEGMENTS = {
    "guide",
    "guides",
    "insight",
    "playbook",
    "playbooks",
    "research",
    "analysis",
    "survey",
    "outlook",
}
_DIRECT_ONSITE_REPORT_PATH_PHRASES = {
    "year-in-review",
}
_DIRECT_ONSITE_DIGITAL_YEAR_SEGMENT_RX = re.compile(
    r"^(?:digital|global-digital)-20\d{2}(?:-|$)"
)
_ONSITE_EXCLUDED_SEGMENTS = {
    "resources",
    "reports",
    "report",
    "download",
    "downloads",
    "ebook",
    "whitepaper",
    "whitepapers",
    "asset",
    "assets",
    "form",
    "register",
}
_TRACKER_QUERY_KEYS = (
    "url",
    "target",
    "dest",
    "destination",
    "redirect",
    "redirect_url",
    "redirect_uri",
    "u",
    "r",
)

__all__ = [
    "plan_report_download_routes",
    "_build_plan",
    "_build_browser_step",
    "_planning_reason",
    "_preferred_policy_signal",
    "_preferred_publisher_policy_signal",
    "_publisher_policy_signal_matches_context",
    "_apply_policy_route_family",
    "_policy_step_name",
    "_route_kind_hint_for_policy_family",
    "_default_route_family_for_kind",
    "_should_reuse_memory_route",
    "_has_actionable_email_memory_hint",
    "_canonical_memory_route_family",
    "_browser_to_http_recovery_decision",
    "_has_http_probe_signal",
    "_annotate_recovery_steps",
    "_dedupe_steps",
    "_clean_string_list",
    "_looks_like_pdf",
    "_looks_like_listing_url",
    "_looks_like_tracker_url",
    "_tracker_path_query_tokens",
    "_extract_tracker_target_url",
    "_classify_redirect_target",
    "_looks_like_editorial_report_url",
    "_looks_like_onsite_longread_url",
    "_looks_like_email_form_url",
    "_looks_like_direct_onsite_report_url",
    "_path_has_direct_onsite_report_phrase",
    "_onsite_capture_route_steps",
    "_path_has_email_gate_marker",
    "_looks_like_probable_gated_report_detail_url",
]
