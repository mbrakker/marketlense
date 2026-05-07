"""Typed traversal-state helpers for publisher inventory browser discovery.

The canonical service still owns orchestration, but repeated browser state and
metrics mutations live here so the browser path uses one explicit state model.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Mapping

from src.contracts.publisher_inventory import PublisherInventoryRouteTrace
from src.services._publisher_inventory_service.discovery_activity import (
    _is_archive_surface,
    _normalize_absolute_url,
    _normalize_text,
    _positive_int_or_none,
    _select_anchor_title,
)


@dataclass(frozen=True)
class _RenderedInventoryState:
    page_url: str
    page_title: str
    anchors: list[dict[str, str]]
    load_more_labels: list[str]
    tab_labels: list[str]
    active_tab_label: str | None
    report_link_url: str | None
    empty_results_visible: bool
    reset_filter_labels: list[str]
    has_report_filter: bool
    has_apply_button: bool
    has_pagination_next: bool = False
    result_range_end: int | None = None
    result_range_total: int | None = None
    page_index_hint: int | None = None
    page_total_hint: int | None = None


@dataclass(frozen=True)
class _BrowserTraversalMetrics:
    cookies_dismissed: int
    report_route_clicks: int
    report_filter_applied: int
    tab_clicks: int
    load_more_clicks: int
    next_page_visits: int
    archive_expansion_clicks: int = 0
    button_pagination_clicks: int = 0
    nested_scroll_probes: int = 0
    nested_scroll_candidate_growth: int = 0
    virtualized_list_detected: int = 0
    scroll_surface: str = "document"


@dataclass(frozen=True)
class _BrowserScrollProbeResult:
    schema_version: str
    scroll_surface: str
    best_surface_label: str
    probed_surface_count: int
    consumed_surface_count: int
    candidate_growth: bool
    virtualized_list_detected: bool
    anchor_count_before: int
    anchor_count_after: int


def _new_browser_traversal_metrics() -> _BrowserTraversalMetrics:
    return _BrowserTraversalMetrics(
        cookies_dismissed=0,
        report_route_clicks=0,
        report_filter_applied=0,
        tab_clicks=0,
        load_more_clicks=0,
        next_page_visits=0,
        archive_expansion_clicks=0,
        button_pagination_clicks=0,
        nested_scroll_probes=0,
        nested_scroll_candidate_growth=0,
        virtualized_list_detected=0,
        scroll_surface="document",
    )


def _increment_browser_traversal_metrics(
    metrics: _BrowserTraversalMetrics,
    *,
    cookies_dismissed: int = 0,
    report_route_clicks: int = 0,
    report_filter_applied: int = 0,
    tab_clicks: int = 0,
    load_more_clicks: int = 0,
    next_page_visits: int = 0,
    archive_expansion_clicks: int = 0,
    button_pagination_clicks: int = 0,
    nested_scroll_probes: int = 0,
    nested_scroll_candidate_growth: int = 0,
    virtualized_list_detected: int = 0,
    scroll_surface: str | None = None,
) -> _BrowserTraversalMetrics:
    normalized_surface = _normalize_text(scroll_surface or metrics.scroll_surface)
    if normalized_surface not in {"document", "nested_container", "virtualized_list"}:
        normalized_surface = metrics.scroll_surface
    if metrics.scroll_surface in {"nested_container", "virtualized_list"} and normalized_surface == "document":
        normalized_surface = metrics.scroll_surface
    if metrics.scroll_surface == "virtualized_list":
        normalized_surface = "virtualized_list"
    return replace(
        metrics,
        cookies_dismissed=metrics.cookies_dismissed + int(cookies_dismissed),
        report_route_clicks=metrics.report_route_clicks + int(report_route_clicks),
        report_filter_applied=metrics.report_filter_applied
        + int(report_filter_applied),
        tab_clicks=metrics.tab_clicks + int(tab_clicks),
        load_more_clicks=metrics.load_more_clicks + int(load_more_clicks),
        next_page_visits=metrics.next_page_visits + int(next_page_visits),
        archive_expansion_clicks=metrics.archive_expansion_clicks
        + int(archive_expansion_clicks),
        button_pagination_clicks=metrics.button_pagination_clicks
        + int(button_pagination_clicks),
        nested_scroll_probes=metrics.nested_scroll_probes
        + int(nested_scroll_probes),
        nested_scroll_candidate_growth=metrics.nested_scroll_candidate_growth
        + int(nested_scroll_candidate_growth),
        virtualized_list_detected=metrics.virtualized_list_detected
        + int(virtualized_list_detected),
        scroll_surface=normalized_surface,
    )


def _rendered_inventory_state_from_payload(
    payload: Mapping[str, Any],
    *,
    page_url_fallback: str,
) -> _RenderedInventoryState:
    page_url = _normalize_absolute_url(str(payload.get("page_url") or "")) or (
        _normalize_absolute_url(page_url_fallback) or page_url_fallback
    )
    anchors = [
        {
            "href": _normalize_text(item.get("href", "")),
            "text": _select_anchor_title(item),
            "rel": _normalize_text(item.get("rel", "")),
        }
        for item in payload.get("anchors", [])
        if isinstance(item, dict) and _normalize_text(item.get("href", ""))
    ]
    return _RenderedInventoryState(
        page_url=page_url,
        page_title=_normalize_text(str(payload.get("page_title") or "")),
        anchors=anchors,
        load_more_labels=[
            _normalize_text(label)
            for label in payload.get("load_more_labels", [])
            if _normalize_text(str(label or ""))
        ],
        tab_labels=[
            _normalize_text(label)
            for label in payload.get("tab_labels", [])
            if _normalize_text(str(label or ""))
        ],
        active_tab_label=(
            _normalize_text(str(payload.get("active_tab_label") or "")) or None
        ),
        report_link_url=(
            _normalize_absolute_url(str(payload.get("report_link_url") or "")) or None
        ),
        empty_results_visible=bool(payload.get("empty_results_visible")),
        reset_filter_labels=[
            _normalize_text(label)
            for label in payload.get("reset_filter_labels", [])
            if _normalize_text(str(label or ""))
        ],
        has_report_filter=bool(payload.get("has_report_filter")),
        has_apply_button=bool(payload.get("has_apply_button")),
        has_pagination_next=bool(payload.get("has_pagination_next")),
        result_range_end=_positive_int_or_none(payload.get("result_range_end")),
        result_range_total=_positive_int_or_none(payload.get("result_range_total")),
        page_index_hint=_positive_int_or_none(payload.get("page_index_hint")),
        page_total_hint=_positive_int_or_none(payload.get("page_total_hint")),
    )


def _build_browser_route_trace(
    *,
    initial_state: _RenderedInventoryState,
    metrics: _BrowserTraversalMetrics,
    selected_tab_labels: list[str],
) -> PublisherInventoryRouteTrace:
    pagination_mode = "none"
    if metrics.load_more_clicks > 0:
        pagination_mode = "load_more"
    elif metrics.button_pagination_clicks > 0:
        pagination_mode = "button_next"
    elif metrics.next_page_visits > 0:
        pagination_mode = "next_link"
    if selected_tab_labels:
        pagination_mode = "tabbed" if pagination_mode == "none" else "mixed"
    surface_class = (
        "archive_feed"
        if _is_archive_surface(initial_state) or selected_tab_labels
        else "mixed_content_hub"
    )
    return PublisherInventoryRouteTrace(
        schema_version="1.0",
        followed_report_listing=metrics.report_route_clicks > 0,
        applied_report_filter=metrics.report_filter_applied > 0,
        selected_filters=(["report"] if metrics.report_filter_applied > 0 else []),
        selected_tab_labels=[
            label for label in selected_tab_labels if str(label).strip()
        ],
        pagination_mode=pagination_mode,
        preferred_control_labels=list(dict.fromkeys(initial_state.load_more_labels[:3])),
        candidate_surface_guard=(
            "report_filter"
            if metrics.report_filter_applied > 0
            else ("tab_guard" if selected_tab_labels else "candidate_density")
        ),
        surface_class=surface_class,
        scroll_surface=metrics.scroll_surface,
        scroll_surface_candidate_growth=metrics.nested_scroll_candidate_growth > 0,
        virtualized_list_detected=metrics.virtualized_list_detected > 0,
    )


def _browser_scroll_probe_result_from_payload(
    payload: Mapping[str, Any],
) -> _BrowserScrollProbeResult:
    surface = _normalize_text(str(payload.get("scrollSurface") or "document"))
    if surface not in {"document", "nested_container", "virtualized_list"}:
        surface = "document"
    return _BrowserScrollProbeResult(
        schema_version="1.0",
        scroll_surface=surface,
        best_surface_label=_normalize_text(
            str(payload.get("bestSurfaceLabel") or surface)
        )
        or surface,
        probed_surface_count=int(payload.get("probedSurfaceCount") or 0),
        consumed_surface_count=int(payload.get("consumedSurfaceCount") or 0),
        candidate_growth=bool(payload.get("candidateGrowth")),
        virtualized_list_detected=bool(payload.get("virtualizedListDetected")),
        anchor_count_before=int(payload.get("anchorCountBefore") or 0),
        anchor_count_after=int(payload.get("anchorCountAfter") or 0),
    )
