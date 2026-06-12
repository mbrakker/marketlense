from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from src.contracts.publisher_inventory import PublisherInventoryRawCandidate
from src.services._publisher_inventory_service._discovery_activity.candidates import (
    _extract_candidates_from_html,
    _has_report_focused_surface_context,
)
from src.services._publisher_inventory_service._discovery_activity.constants import (
    _REPORT_FOCUSED_TAB_MARKERS,
)
from src.services._publisher_inventory_service._discovery_activity.titles import (
    _looks_like_human_report_title,
    _normalize_text,
)
from src.services._publisher_inventory_service._discovery_activity.urls import (
    _looks_like_report_listing_route_url,
    _normalize_absolute_url,
)
from src.utils.url_utils import host_matches_domain

def _should_follow_report_listing(
    normalized_url: str,
    state: Any,
) -> bool:
    host = str(urlsplit(normalized_url).hostname or "").casefold()
    if "gfk-media-measurement.com" not in host:
        if not state.report_link_url:
            return False
        if _normalize_absolute_url(state.report_link_url) == _normalize_absolute_url(
            state.page_url
        ):
            return False
        if not _looks_like_report_listing_route_url(state.report_link_url):
            return False
        return not _is_archive_surface(state)
    path = str(urlsplit(normalized_url).path or "").casefold()
    if "/insights/report/" in path:
        return False
    if state.has_report_filter and state.has_apply_button:
        return False
    return bool(state.report_link_url)

def _should_expand_archive_library(
    state: Any,
    page_candidates: list[PublisherInventoryRawCandidate],
) -> bool:
    if state.load_more_labels or state.has_pagination_next:
        return False
    if state.page_total_hint and state.page_total_hint > 1:
        return False
    if state.result_range_total and state.result_range_total > max(
        len(page_candidates), 0
    ):
        return False
    if len(page_candidates) > 3:
        return False
    if _looks_like_report_listing_route_url(state.page_url):
        return False
    if not (
        _is_archive_surface(state)
        or _has_report_focused_surface_context(
            page_url=state.page_url,
            origin_url=state.page_url,
            page_title=state.page_title,
            active_tab_label=state.active_tab_label,
        )
    ):
        return False
    return True

def _should_apply_report_filter(
    normalized_url: str,
    state: Any,
) -> bool:
    _ = normalized_url
    return state.has_report_filter

def _should_traverse_tabs(
    normalized_url: str,
    state: Any,
) -> bool:
    return (
        host_matches_domain(normalized_url, "salesforce.com")
        and len(state.tab_labels) > 1
    )

def _select_tab_labels_for_traversal(
    normalized_url: str,
    state: Any,
) -> list[str]:
    labels = [
        _normalize_text(label) for label in state.tab_labels if _normalize_text(label)
    ]
    if not labels:
        return []
    unique_labels: list[str] = []
    seen_labels: set[str] = set()
    for label in labels:
        normalized_label = label.casefold()
        if normalized_label in seen_labels:
            continue
        seen_labels.add(normalized_label)
        unique_labels.append(label)
    preferred_labels = [
        label
        for label in unique_labels
        if any(marker in label.casefold() for marker in _REPORT_FOCUSED_TAB_MARKERS)
    ]
    if preferred_labels:
        return preferred_labels
    if _should_traverse_tabs(normalized_url, state):
        return unique_labels
    return []

def _is_archive_surface(state: Any) -> bool:
    substantive_anchor_count = sum(
        1
        for anchor in state.anchors
        if len(_normalize_text(anchor.get("text", ""))) >= 18
        and _looks_like_human_report_title(_normalize_text(anchor.get("text", "")))
    )
    return bool(
        state.load_more_labels
        or state.has_pagination_next
        or (state.page_total_hint and state.page_total_hint > 1)
        or (state.result_range_total and state.result_range_total > 0)
        or len(state.tab_labels) > 1
        or len(state.anchors) >= 12
        or substantive_anchor_count >= 3
    )

def _requires_archive_surface_recovery(
    *,
    state: Any,
    page_candidates: list[PublisherInventoryRawCandidate],
    normalized_url: str,
) -> bool:
    current_url = _normalize_absolute_url(state.page_url)
    origin_url = _normalize_absolute_url(normalized_url)
    if not current_url or not origin_url or current_url == origin_url:
        return False
    if _is_archive_surface(state):
        return False
    return len(page_candidates) < 3

def _is_terminal_results_page(state: Any) -> bool:
    if (
        state.page_index_hint is not None
        and state.page_total_hint is not None
        and state.page_total_hint > 0
        and state.page_index_hint >= state.page_total_hint
    ):
        return True
    if state.result_range_end is None or state.result_range_total is None:
        return False
    return (
        state.result_range_total > 0
        and state.result_range_end >= state.result_range_total
    )

def _needs_additional_hydration(
    state: Any,
    *,
    page_candidates: list[PublisherInventoryRawCandidate],
    next_page_url: str | None,
) -> bool:
    return (
        not state.load_more_labels
        and not state.has_pagination_next
        and not next_page_url
        and len(page_candidates) < 5
    )

def _rendered_state_anchor_fingerprint(state: Any) -> tuple[tuple[str, str, str], ...]:
    return tuple(
        (
            _normalize_text(anchor.get("href", "")),
            _normalize_text(anchor.get("text", "")),
            _normalize_text(anchor.get("rel", "")),
        )
        for anchor in state.anchors
        if _normalize_text(anchor.get("href", ""))
    )

def _is_exhausted_inert_load_more(
    *,
    previous_state: Any,
    stalled_state: Any,
) -> bool:
    if stalled_state.page_url != previous_state.page_url:
        return False
    if _rendered_state_anchor_fingerprint(
        stalled_state
    ) != _rendered_state_anchor_fingerprint(previous_state):
        return False
    if (
        stalled_state.result_range_end != previous_state.result_range_end
        or stalled_state.result_range_total != previous_state.result_range_total
    ):
        return False
    if stalled_state.has_pagination_next:
        return False
    previous_candidates = {
        candidate.url
        for candidate in _extract_candidates_from_html(
            anchors=previous_state.anchors,
            page_url=previous_state.page_url,
            page_number=1,
            next_page_url=None,
        )
    }
    stalled_candidates = {
        candidate.url
        for candidate in _extract_candidates_from_html(
            anchors=stalled_state.anchors,
            page_url=stalled_state.page_url,
            page_number=1,
            next_page_url=None,
        )
    }
    return stalled_candidates == previous_candidates

def _build_browser_route_summary(
    *,
    normalized_url: str,
    pages: list[Any],
    metrics: Any,
    used_tabs: bool,
    bounded_by_pagination_limit: bool = False,
) -> str:
    host = str(urlsplit(normalized_url).hostname or "").strip().lower()
    steps = [
        f"Rendered {host} in browser and extracted {len(pages)} inventory state(s)."
    ]
    if metrics.cookies_dismissed:
        steps.append(f"Dismissed cookie banners {metrics.cookies_dismissed} time(s).")
    if metrics.report_route_clicks:
        steps.append("Followed the report listing route before extraction.")
    if metrics.archive_expansion_clicks:
        steps.append(
            f"Expanded archive surfaces {metrics.archive_expansion_clicks} time(s)."
        )
    if metrics.report_filter_applied:
        steps.append("Applied the report format filter.")
    if used_tabs and metrics.tab_clicks:
        steps.append(f"Traversed {metrics.tab_clicks + 1} tabbed publisher section(s).")
    if metrics.load_more_clicks:
        steps.append(
            f"Expanded load-more pagination {metrics.load_more_clicks} time(s)."
        )
    if metrics.button_pagination_clicks:
        steps.append(
            f"Clicked button pagination {metrics.button_pagination_clicks} time(s)."
        )
    if metrics.next_page_visits:
        steps.append(
            f"Visited {metrics.next_page_visits} additional pagination URL(s)."
        )
    if getattr(metrics, "nested_scroll_probes", 0):
        surface = str(getattr(metrics, "scroll_surface", "nested_container")).strip()
        probe_count = int(getattr(metrics, "nested_scroll_probes", 0))
        steps.append(
            f"Probed {surface.replace('_', ' ')} scroll surfaces {probe_count} time(s)."
        )
    if bounded_by_pagination_limit:
        steps.append(
            "Stopped at the configured pagination limit after collecting a bounded "
            "candidate set."
        )
    return " ".join(steps)
