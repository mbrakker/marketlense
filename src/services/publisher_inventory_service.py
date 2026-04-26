from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
from dataclasses import dataclass
from hashlib import sha1
from importlib import import_module
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import requests  # type: ignore[import-untyped]

from src.contracts.http_acquisition import (
    HttpAcquisitionRequest,
    HttpAcquisitionResponsePolicy,
)
from src.contracts.publisher_inventory import (
    PublisherInventoryLandingPageInspectionRequest,
    PublisherInventoryLandingPageInspectionResponse,
    PublisherInventoryPage,
    PublisherInventoryRawCandidate,
    PublisherInventoryRouteTrace,
    PublisherInventoryScenarioSummary,
    PublisherInventoryServiceRequest,
    PublisherInventoryServiceResponse,
)
from src.contracts.run_context import RunContext
from src.services._http_acquisition import execute_http_acquisition
from src.services._publisher_inventory_discovery_activity import (
    _build_browser_route_summary,
    _candidate_url_signature,
    _extract_component_link_anchors,
    _extract_candidates_from_html,
    _fallback_title_from_url,
    _is_archive_surface,
    _is_exhausted_inert_load_more,
    _is_terminal_results_page,
    _needs_additional_hydration,
    _normalize_absolute_url,
    _normalize_text,
    _positive_int_or_none,
    _rendered_state_anchor_fingerprint,
    _requires_archive_surface_recovery,
    _requires_origin_host_recovery,
    _resolve_next_page_url,
    _select_anchor_title,
    _select_tab_labels_for_traversal,
    _should_apply_report_filter,
    _should_expand_archive_library,
    _should_follow_report_listing,
)
from src.services._publisher_inventory_browser_service import (
    BrowserInventoryAcquisitionDependencies,
    discover_inventory_via_browser,
)
from src.services._publisher_inventory_fetch_service import (
    HTTP_BROWSER_HEADERS,
    _InventoryHtmlParser,
    discover_inventory_via_http,
    inspect_inventory_landing_pages,
)
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.publisher_inventory_service")

_ROUTE_KINDS = {"http_parse", "browser_render"}
_PREFLIGHT_HTML_MAX_BYTES = 1024 * 1024
_HTTP_SUPPLEMENT_HTML_MAX_BYTES = 2 * 1024 * 1024


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


_DIRECT_DETAIL_URL_MARKERS = (
    "/research-library/",
    "/report/",
    "/reports/",
    "/whitepaper/",
    "/whitepapers/",
    "/ebook/",
    "/ebooks/",
    "/study/",
    "/studies/",
    "/survey/",
    "/surveys/",
)
_ARCHIVE_URL_MARKERS = (
    "/insights",
    "/insight",
    "/library",
    "/research",
    "/reports",
    "/resources",
)
_FILTER_HINT_MARKERS = ("filter", "filters", "topic", "type")
_DOWNLOAD_HINT_MARKERS = (
    "download",
    "download the report",
    "download the research brief",
    "get the report",
    "access report",
    "view report",
)
_PREFLIGHT_COLLECTION_ROOT_TOKENS = {
    "all",
    "and",
    "center",
    "centre",
    "ebook",
    "ebooks",
    "guide",
    "guides",
    "hub",
    "insight",
    "insights",
    "library",
    "publication",
    "publications",
    "report",
    "reports",
    "research",
    "resource",
    "resources",
    "study",
    "studies",
    "survey",
    "surveys",
    "whitepaper",
    "whitepapers",
}


def _build_scenario_summary(
    *,
    scenario_class: str,
    source_surface_class: str,
    confidence: float,
    direct_detail_eligible: bool,
    browser_preferred: bool,
    notes: str,
) -> PublisherInventoryScenarioSummary:
    return PublisherInventoryScenarioSummary(
        schema_version="1.0",
        scenario_class=scenario_class,
        source_surface_class=source_surface_class,
        confidence=max(0.0, min(float(confidence), 1.0)),
        direct_detail_eligible=direct_detail_eligible,
        browser_preferred=browser_preferred,
        notes=notes.strip(),
    )


def _classify_preflight_scenario(
    *,
    request: PublisherInventoryServiceRequest,
    normalized_url: str,
    ctx: RunContext,
) -> PublisherInventoryScenarioSummary:
    if normalized_url.casefold().endswith(".pdf"):
        return _build_scenario_summary(
            scenario_class="direct_pdf",
            source_surface_class="direct_detail",
            confidence=1.0,
            direct_detail_eligible=True,
            browser_preferred=False,
            notes="The source URL already points at a PDF asset.",
        )
    path_lower = urlsplit(normalized_url).path.casefold()
    if _looks_like_preflight_filter_route(normalized_url):
        return _build_scenario_summary(
            scenario_class="filtered_archive",
            source_surface_class="archive_feed",
            confidence=0.8,
            direct_detail_eligible=False,
            browser_preferred=True,
            notes="The source URL already encodes report filter state.",
        )
    if path_lower.rstrip("/") in {"/insights", "/research", "/resources", "/reports"}:
        return _build_scenario_summary(
            scenario_class="mixed_content_hub",
            source_surface_class="mixed_content_hub",
            confidence=0.55,
            direct_detail_eligible=False,
            browser_preferred=True,
            notes="The source URL looks like a broad insight or resource hub.",
        )
    try:
        response = execute_http_acquisition(
            request=HttpAcquisitionRequest(
                schema_version="1.0",
                purpose="publisher_inventory_preflight_probe",
                method="GET",
                url=normalized_url,
                headers=dict(HTTP_BROWSER_HEADERS),
                timeout_seconds=min(float(request.settings.http_timeout_seconds), 10.0),
                response_policy=HttpAcquisitionResponsePolicy(
                    schema_version="1.0",
                    require_success_status=False,
                    capture_text=True,
                    capture_content_type_markers=("html", "xml"),
                    max_body_bytes=_PREFLIGHT_HTML_MAX_BYTES,
                    truncate_body=True,
                ),
                error_code="publisher_inventory_preflight_failed",
                error_message="Preflight classification could not fetch the source page",
                allow_redirects=True,
                context_fields={"normalized_url": normalized_url},
            ),
            ctx=ctx,
            requests_module=requests,
        )
    except AppError as exc:
        marker = str(exc).casefold()
        if any(
            term in marker
            for term in (
                "captcha",
                "access denied",
                "just a moment",
                "timed out",
                "temporarily unavailable",
            )
        ):
            return _build_scenario_summary(
                scenario_class="challenge_prone",
                source_surface_class="unknown",
                confidence=0.7,
                direct_detail_eligible=False,
                browser_preferred=True,
                notes=f"Preflight fetch encountered a challenge-prone response: {str(exc).strip()}",
            )
        return _build_scenario_summary(
            scenario_class="unknown",
            source_surface_class="unknown",
            confidence=0.0,
            direct_detail_eligible=False,
            browser_preferred=bool(request.settings.force_browser),
            notes="Preflight classification could not fetch the source page.",
        )
    final_url = (
        _normalize_absolute_url(str(response.final_url or normalized_url))
        or normalized_url
    )
    content_type = str(response.content_type or "").casefold()
    html = str(response.text_body or "")
    lower_html = html.casefold()
    title_start = lower_html.find("<title")
    title_text = ""
    if title_start >= 0:
        title_close = lower_html.find("</title>", title_start)
        title_text = html[title_start:title_close] if title_close > title_start else ""
    combined = " ".join(
        part for part in (final_url, title_text, lower_html[:5000]) if part
    ).casefold()
    final_path = urlsplit(final_url).path.casefold()
    if ".pdf" in final_path or "application/pdf" in content_type:
        return _build_scenario_summary(
            scenario_class="direct_pdf",
            source_surface_class="direct_detail",
            confidence=1.0,
            direct_detail_eligible=True,
            browser_preferred=False,
            notes="Preflight fetch resolved the source URL to a PDF asset.",
        )
    detail_signal = _looks_like_preflight_direct_detail_path(final_url)
    download_signal = any(marker in combined for marker in _DOWNLOAD_HINT_MARKERS)
    archive_signal = any(marker in final_path for marker in _ARCHIVE_URL_MARKERS)
    filter_signal = _looks_like_preflight_filter_route(final_url)
    tab_signal = any(
        label in combined
        for label in ("featured", "reports", "insights", "research", "latest")
    )
    challenge_signal = any(
        marker in combined
        for marker in (
            "access denied",
            "captcha",
            "just a moment",
            "verify you are human",
        )
    )
    if challenge_signal:
        return _build_scenario_summary(
            scenario_class="challenge_prone",
            source_surface_class="unknown",
            confidence=0.8,
            direct_detail_eligible=False,
            browser_preferred=True,
            notes="Preflight fetch saw anti-bot or challenge markers in the response.",
        )
    if detail_signal and not filter_signal:
        return _build_scenario_summary(
            scenario_class="direct_detail_html",
            source_surface_class="direct_detail",
            confidence=0.9 if download_signal else 0.75,
            direct_detail_eligible=True,
            browser_preferred=False,
            notes=(
                "Preflight fetch found a direct-detail HTML route with explicit download language."
                if download_signal
                else "Preflight fetch found a deep direct-detail HTML route without archive-style filter state."
            ),
        )
    if filter_signal and archive_signal:
        return _build_scenario_summary(
            scenario_class="filtered_archive",
            source_surface_class="archive_feed",
            confidence=0.85,
            direct_detail_eligible=False,
            browser_preferred=True,
            notes="Preflight fetch found archive-style content with explicit filter state.",
        )
    if archive_signal and tab_signal:
        return _build_scenario_summary(
            scenario_class="tabbed_archive",
            source_surface_class="archive_feed",
            confidence=0.65,
            direct_detail_eligible=False,
            browser_preferred=True,
            notes="Preflight fetch suggests a tabbed report archive.",
        )
    if archive_signal:
        return _build_scenario_summary(
            scenario_class="mixed_content_hub",
            source_surface_class="mixed_content_hub",
            confidence=0.55,
            direct_detail_eligible=False,
            browser_preferred=True,
            notes="Preflight fetch suggests a broad insight hub rather than a single detail page.",
        )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="publisher_inventory_preflight_classification_defaulted",
            module=logger.name,
            fields={"normalized_url": normalized_url, "final_url": final_url},
        )
    )
    return _build_scenario_summary(
        scenario_class="unknown",
        source_surface_class="unknown",
        confidence=0.25,
        direct_detail_eligible=False,
        browser_preferred=bool(request.settings.force_browser),
        notes="Preflight fetch found no stable scenario signature.",
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
        preferred_control_labels=list(
            dict.fromkeys(initial_state.load_more_labels[:3])
        ),
        candidate_surface_guard=(
            "report_filter"
            if metrics.report_filter_applied > 0
            else ("tab_guard" if selected_tab_labels else "candidate_density")
        ),
        surface_class=surface_class,
    )


def _looks_like_preflight_filter_route(url: str) -> bool:
    normalized_url = str(url or "").strip().casefold()
    if not normalized_url:
        return False
    return (
        "filters=" in normalized_url
        or "filter=" in normalized_url
        or "types(" in normalized_url
        or "type=" in normalized_url
        or "topic=" in normalized_url
        or "/type/" in normalized_url
        or "/topic/" in normalized_url
    )


def _looks_like_preflight_direct_detail_path(url: str) -> bool:
    normalized_url = str(url or "").strip().casefold()
    if not normalized_url:
        return False
    path = urlsplit(normalized_url).path
    if not any(marker in path for marker in _DIRECT_DETAIL_URL_MARKERS):
        return False
    segments = [segment for segment in path.split("/") if segment]
    if len(segments) < 2:
        return False
    leaf = segments[-1].rsplit(".", 1)[0]
    if not leaf or leaf.isdigit():
        return False
    leaf_tokens = [token for token in re.findall(r"[a-z0-9]+", leaf) if token]
    if not leaf_tokens:
        return False
    if len(leaf_tokens) == 1 and leaf_tokens[0] in _PREFLIGHT_COLLECTION_ROOT_TOKENS:
        return False
    return not all(token in _PREFLIGHT_COLLECTION_ROOT_TOKENS for token in leaf_tokens)


def discover_publisher_inventory(
    request: PublisherInventoryServiceRequest,
    ctx: RunContext,
) -> PublisherInventoryServiceResponse:
    normalized_url = _validate_and_normalize_url(request.insights_url)
    _validate_request(request, normalized_url)
    scenario_summary = (
        _classify_preflight_scenario(
            request=request, normalized_url=normalized_url, ctx=ctx
        )
        if request.settings.enable_preflight_classifier_and_direct_detail
        else None
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="publisher_inventory_discovery_start",
            module=logger.name,
            fields={
                "source_url": request.insights_url,
                "normalized_url": normalized_url,
                "route_kind_hint": request.route_kind_hint or "",
                "has_route_hint": bool(request.route_hint),
                "pagination_max_pages": request.settings.pagination_max_pages,
                "http_timeout_seconds": request.settings.http_timeout_seconds,
                "model": request.settings.model,
                "timeout_seconds": request.settings.timeout_seconds,
                "max_steps": request.settings.max_steps,
                "headed": request.settings.headed,
                "force_browser": request.settings.force_browser,
                "scenario_class": (
                    scenario_summary.scenario_class
                    if scenario_summary is not None
                    else ""
                ),
            },
        )
    )
    if normalized_url.lower().endswith(".pdf"):
        return _discover_direct_pdf_source(request, ctx, normalized_url)
    if (
        scenario_summary is not None
        and scenario_summary.direct_detail_eligible
        and scenario_summary.scenario_class == "direct_detail_html"
    ):
        return _discover_direct_detail_source(
            request,
            ctx,
            normalized_url,
            scenario_summary=scenario_summary,
        )
    if request.settings.force_browser:
        return _discover_with_browser(
            request,
            ctx,
            normalized_url,
            use_hint=bool(request.route_hint),
            scenario_summary=scenario_summary,
        )
    hinted_route = str(request.route_kind_hint or "").strip()
    if hinted_route:
        _validate_route_kind(hinted_route)
        if hinted_route == "http_parse":
            return _discover_with_http(
                request,
                ctx,
                normalized_url,
                use_hint=True,
                scenario_summary=scenario_summary,
            )
        return _discover_with_browser(
            request,
            ctx,
            normalized_url,
            use_hint=True,
            scenario_summary=scenario_summary,
        )

    try:
        return _discover_with_http(
            request,
            ctx,
            normalized_url,
            use_hint=False,
            scenario_summary=scenario_summary,
        )
    except AppError as exc:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="publisher_inventory_http_fallback",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "error": exc.message,
                    "code": exc.code,
                },
            )
        )
    return _discover_with_browser(
        request,
        ctx,
        normalized_url,
        use_hint=False,
        scenario_summary=scenario_summary,
    )


def inspect_publisher_inventory_landing_pages(
    request: PublisherInventoryLandingPageInspectionRequest,
    ctx: RunContext,
) -> PublisherInventoryLandingPageInspectionResponse:
    return inspect_inventory_landing_pages(
        request,
        ctx,
        requests_module=requests,
    )


def _discover_direct_pdf_source(
    request: PublisherInventoryServiceRequest,
    ctx: RunContext,
    normalized_url: str,
) -> PublisherInventoryServiceResponse:
    candidate = PublisherInventoryRawCandidate(
        schema_version="1.0",
        url=normalized_url,
        title=_fallback_title_from_url(normalized_url),
        source_page_url=normalized_url,
        discovered_on_page_number=1,
        pdf_url=normalized_url,
        published_at_text=None,
        provenance="direct_pdf_source",
        confidence=1.0,
    )
    response = PublisherInventoryServiceResponse(
        schema_version="1.0",
        source_url=request.insights_url,
        normalized_url=normalized_url,
        route_kind="http_parse",
        route_summary="Treated the direct PDF URL as a single-item inventory source.",
        final_page_url=normalized_url,
        used_route_hint=False,
        pages=[
            PublisherInventoryPage(
                schema_version="1.0",
                page_number=1,
                page_url=normalized_url,
            )
        ],
        candidates=[candidate],
        scenario_summary=_build_scenario_summary(
            scenario_class="direct_pdf",
            source_surface_class="direct_detail",
            confidence=1.0,
            direct_detail_eligible=True,
            browser_preferred=False,
            notes="The source URL resolved directly to a PDF document.",
        ),
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="publisher_inventory_direct_pdf_complete",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "candidate_url": candidate.url,
            },
        )
    )
    return response


def _discover_direct_detail_source(
    request: PublisherInventoryServiceRequest,
    ctx: RunContext,
    normalized_url: str,
    *,
    scenario_summary: PublisherInventoryScenarioSummary,
) -> PublisherInventoryServiceResponse:
    candidate = PublisherInventoryRawCandidate(
        schema_version="1.0",
        url=normalized_url,
        title=_fallback_title_from_url(normalized_url),
        source_page_url=normalized_url,
        discovered_on_page_number=1,
        pdf_url=None,
        published_at_text=None,
        provenance="direct_detail_source",
        confidence=max(float(scenario_summary.confidence), 0.85),
    )
    response = PublisherInventoryServiceResponse(
        schema_version="1.0",
        source_url=request.insights_url,
        normalized_url=normalized_url,
        route_kind="http_parse",
        route_summary="Short-circuited a high-confidence direct-detail report page without archive traversal.",
        final_page_url=normalized_url,
        used_route_hint=False,
        pages=[
            PublisherInventoryPage(
                schema_version="1.0",
                page_number=1,
                page_url=normalized_url,
            )
        ],
        candidates=[candidate],
        scenario_summary=scenario_summary,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="publisher_inventory_direct_detail_complete",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "scenario_class": scenario_summary.scenario_class,
            },
        )
    )
    return response


def _discover_with_http(
    request: PublisherInventoryServiceRequest,
    ctx: RunContext,
    normalized_url: str,
    *,
    use_hint: bool,
    scenario_summary: PublisherInventoryScenarioSummary | None,
) -> PublisherInventoryServiceResponse:
    return discover_inventory_via_http(
        request,
        ctx,
        normalized_url,
        use_hint=use_hint,
        scenario_summary=scenario_summary,
        requests_module=requests,
    )


def _discover_with_browser(
    request: PublisherInventoryServiceRequest,
    ctx: RunContext,
    normalized_url: str,
    *,
    use_hint: bool,
    scenario_summary: PublisherInventoryScenarioSummary | None,
) -> PublisherInventoryServiceResponse:
    return discover_inventory_via_browser(
        request,
        ctx,
        normalized_url,
        use_hint=use_hint,
        scenario_summary=scenario_summary,
        dependencies=BrowserInventoryAcquisitionDependencies(
            asyncio_module=asyncio,
            prepare_session_dir=lambda root_dir, url: _prepare_session_dir(
                root_dir=root_dir,
                normalized_url=url,
            ),
            load_browser_use_runtime=_load_browser_use_runtime,
            run_browser_traversal=lambda browser, req, run_ctx, url: (
                _run_browser_traversal_with_timeout(
                    browser=browser,
                    request=req,
                    ctx=run_ctx,
                    normalized_url=url,
                )
            ),
            extract_http_supplement=lambda req, page, url, run_ctx: (
                _extract_browser_http_supplement_candidates(
                    request=req,
                    page=page,
                    normalized_url=url,
                    ctx=run_ctx,
                )
            ),
            fallback_http_discovery=lambda req, run_ctx, url, hint: _discover_with_http(
                req,
                run_ctx,
                url,
                use_hint=hint,
                scenario_summary=None,
            ),
            kill_browser=_kill_browser,
            candidate_provenance_counts=_candidate_provenance_counts,
        ),
    )


def _seed_initial_browser_page(
    *,
    state: _RenderedInventoryState,
    page_number: int,
    candidates: list[PublisherInventoryRawCandidate],
) -> tuple[list[PublisherInventoryPage], list[PublisherInventoryRawCandidate]]:
    if not candidates:
        return [], []
    return [
        PublisherInventoryPage(
            schema_version="1.0",
            page_number=page_number,
            page_url=state.page_url,
        )
    ], list(candidates)


async def _run_browser_traversal(
    *,
    browser: Any,
    request: PublisherInventoryServiceRequest,
    ctx: RunContext,
    normalized_url: str,
) -> tuple[
    list[PublisherInventoryPage],
    list[PublisherInventoryRawCandidate],
    str,
    str,
    PublisherInventoryRouteTrace,
]:
    try:
        await browser.start()
        page = await browser.new_page(normalized_url)
        await _close_unexpected_blank_pages(
            browser=browser,
            active_page=page,
            ctx=ctx,
            reason="new_page",
        )
        await _browser_wait_for_settle(page=page)
        await _close_unexpected_blank_pages(
            browser=browser,
            active_page=page,
            ctx=ctx,
            reason="initial_settle",
        )
        settled_state = await _extract_rendered_inventory_state(page)
        settled_candidates = _extract_candidates_from_html(
            anchors=settled_state.anchors,
            page_url=settled_state.page_url,
            page_number=1,
            next_page_url=None,
            origin_url=normalized_url,
            page_title=settled_state.page_title,
            active_tab_label=settled_state.active_tab_label,
            archive_surface=_is_archive_surface(settled_state),
            provenance="browser_dom",
        )
        await _prime_browser_inventory_surface(page)
        pre_cookie_state = await _extract_rendered_inventory_state(page)
        pre_cookie_candidates = _extract_candidates_from_html(
            anchors=pre_cookie_state.anchors,
            page_url=pre_cookie_state.page_url,
            page_number=1,
            next_page_url=None,
            origin_url=normalized_url,
            page_title=pre_cookie_state.page_title,
            active_tab_label=pre_cookie_state.active_tab_label,
            archive_surface=_is_archive_surface(pre_cookie_state),
            provenance="browser_dom",
        )
        metrics = _BrowserTraversalMetrics(
            cookies_dismissed=0,
            report_route_clicks=0,
            report_filter_applied=0,
            tab_clicks=0,
            load_more_clicks=0,
            next_page_visits=0,
            archive_expansion_clicks=0,
        )
        dismissed = await _dismiss_cookie_banner(page)
        if dismissed:
            metrics = _BrowserTraversalMetrics(
                cookies_dismissed=metrics.cookies_dismissed + 1,
                report_route_clicks=metrics.report_route_clicks,
                report_filter_applied=metrics.report_filter_applied,
                tab_clicks=metrics.tab_clicks,
                load_more_clicks=metrics.load_more_clicks,
                next_page_visits=metrics.next_page_visits,
                archive_expansion_clicks=metrics.archive_expansion_clicks,
                button_pagination_clicks=metrics.button_pagination_clicks,
            )
            await _browser_wait_for_settle(page=page)
            await _close_unexpected_blank_pages(
                browser=browser,
                active_page=page,
                ctx=ctx,
                reason="cookie_banner",
            )
        await _prime_browser_inventory_surface(page)
        initial_state = await _extract_rendered_inventory_state(page)
        if _should_apply_report_filter(normalized_url, initial_state):
            applied = await _apply_report_filter(page)
            if applied:
                metrics = _BrowserTraversalMetrics(
                    cookies_dismissed=metrics.cookies_dismissed,
                    report_route_clicks=metrics.report_route_clicks,
                    report_filter_applied=metrics.report_filter_applied + 1,
                    tab_clicks=metrics.tab_clicks,
                    load_more_clicks=metrics.load_more_clicks,
                    next_page_visits=metrics.next_page_visits,
                    archive_expansion_clicks=metrics.archive_expansion_clicks,
                    button_pagination_clicks=metrics.button_pagination_clicks,
                )
                await _browser_wait_for_settle(page=page)
                await _close_unexpected_blank_pages(
                    browser=browser,
                    active_page=page,
                    ctx=ctx,
                    reason="report_filter",
                )
                await _prime_browser_inventory_surface(page)
                initial_state = await _extract_rendered_inventory_state(page)
        if _should_follow_report_listing(normalized_url, initial_state):
            await page.goto(initial_state.report_link_url or normalized_url)
            metrics = _BrowserTraversalMetrics(
                cookies_dismissed=metrics.cookies_dismissed,
                report_route_clicks=metrics.report_route_clicks + 1,
                report_filter_applied=metrics.report_filter_applied,
                tab_clicks=metrics.tab_clicks,
                load_more_clicks=metrics.load_more_clicks,
                next_page_visits=metrics.next_page_visits,
                archive_expansion_clicks=metrics.archive_expansion_clicks,
                button_pagination_clicks=metrics.button_pagination_clicks,
            )
            await _browser_wait_for_settle(page=page)
            await _close_unexpected_blank_pages(
                browser=browser,
                active_page=page,
                ctx=ctx,
                reason="report_route",
            )
            dismissed = await _dismiss_cookie_banner(page)
            if dismissed:
                metrics = _BrowserTraversalMetrics(
                    cookies_dismissed=metrics.cookies_dismissed + 1,
                    report_route_clicks=metrics.report_route_clicks,
                    report_filter_applied=metrics.report_filter_applied,
                    tab_clicks=metrics.tab_clicks,
                    load_more_clicks=metrics.load_more_clicks,
                    next_page_visits=metrics.next_page_visits,
                    archive_expansion_clicks=metrics.archive_expansion_clicks,
                    button_pagination_clicks=metrics.button_pagination_clicks,
                )
                await _browser_wait_for_settle(page=page)
                await _close_unexpected_blank_pages(
                    browser=browser,
                    active_page=page,
                    ctx=ctx,
                    reason="report_route_cookie_banner",
                )
            await _prime_browser_inventory_surface(page)
            initial_state = await _extract_rendered_inventory_state(page)

        pages: list[PublisherInventoryPage] = []
        candidates: list[PublisherInventoryRawCandidate] = []
        page_number = 1
        initial_candidates = _extract_candidates_from_html(
            anchors=initial_state.anchors,
            page_url=initial_state.page_url,
            page_number=page_number,
            next_page_url=None,
            origin_url=normalized_url,
            page_title=initial_state.page_title,
            active_tab_label=initial_state.active_tab_label,
            archive_surface=_is_archive_surface(initial_state),
            provenance="browser_dom",
        )
        seed_state = initial_state
        seed_candidates = initial_candidates
        for fallback_state, fallback_candidates in (
            (pre_cookie_state, pre_cookie_candidates),
            (settled_state, settled_candidates),
        ):
            if len(fallback_candidates) > len(seed_candidates):
                seed_state = fallback_state
                seed_candidates = fallback_candidates
        seeded_pages, seeded_candidates = _seed_initial_browser_page(
            state=seed_state,
            page_number=page_number,
            candidates=seed_candidates,
        )
        if _should_expand_archive_library(initial_state, initial_candidates):
            expanded = await _click_archive_expander(page)
            if expanded:
                metrics = _BrowserTraversalMetrics(
                    cookies_dismissed=metrics.cookies_dismissed,
                    report_route_clicks=metrics.report_route_clicks,
                    report_filter_applied=metrics.report_filter_applied,
                    tab_clicks=metrics.tab_clicks,
                    load_more_clicks=metrics.load_more_clicks,
                    next_page_visits=metrics.next_page_visits,
                    archive_expansion_clicks=metrics.archive_expansion_clicks + 1,
                    button_pagination_clicks=metrics.button_pagination_clicks,
                )
                await _wait_for_inventory_transition(
                    page,
                    previous_state=initial_state,
                    current_candidate_count=len(initial_candidates),
                )
                await _close_unexpected_blank_pages(
                    browser=browser,
                    active_page=page,
                    ctx=ctx,
                    reason="archive_expand",
                )
                await _prime_browser_inventory_surface(page)
                initial_state = await _extract_rendered_inventory_state(page)
                seeded_pages = []
                seeded_candidates = []
        selected_tab_labels = _select_tab_labels_for_traversal(
            normalized_url, initial_state
        )
        archive_expected = _is_archive_surface(initial_state) or bool(
            selected_tab_labels
        )
        bounded_by_pagination_limit = False
        if selected_tab_labels:
            seen_tabs: set[str] = set()
            current_state = initial_state
            active_tab_label = _normalize_text(
                current_state.active_tab_label or ""
            ).casefold()
            for tab_label in selected_tab_labels:
                normalized_label = _normalize_text(tab_label).casefold()
                if not normalized_label or normalized_label in seen_tabs:
                    continue
                if normalized_label != active_tab_label:
                    clicked = await _click_tab(page, tab_label)
                    if not clicked:
                        raise AppError(
                            code="publisher_inventory_browser_tab_click_failed",
                            message="Browser-render inventory discovery could not switch tabbed report sections",
                            retryable=True,
                            context={
                                "normalized_url": normalized_url,
                                "tab_label": tab_label,
                            },
                        )
                    await _close_unexpected_blank_pages(
                        browser=browser,
                        active_page=page,
                        ctx=ctx,
                        reason="tab_click",
                    )
                    metrics = _BrowserTraversalMetrics(
                        cookies_dismissed=metrics.cookies_dismissed,
                        report_route_clicks=metrics.report_route_clicks,
                        report_filter_applied=metrics.report_filter_applied,
                        tab_clicks=metrics.tab_clicks + 1,
                        load_more_clicks=metrics.load_more_clicks,
                        next_page_visits=metrics.next_page_visits,
                        archive_expansion_clicks=metrics.archive_expansion_clicks,
                        button_pagination_clicks=metrics.button_pagination_clicks,
                    )
                    await _wait_for_tab_activation(page, tab_label)
                    current_state = await _extract_rendered_inventory_state(page)
                    active_tab_label = _normalize_text(
                        current_state.active_tab_label or ""
                    ).casefold()
                seen_tabs.add(normalized_label)
                (
                    page_number,
                    metrics,
                    tab_bounded_by_pagination_limit,
                ) = await _collect_browser_inventory_pages(
                    browser=browser,
                    page=page,
                    current_state=current_state,
                    starting_page_number=page_number,
                    request=request,
                    normalized_url=normalized_url,
                    archive_expected=archive_expected,
                    pages=pages,
                    candidates=candidates,
                    metrics=metrics,
                    ctx=ctx,
                )
                bounded_by_pagination_limit = (
                    bounded_by_pagination_limit or tab_bounded_by_pagination_limit
                )
                current_state = await _extract_rendered_inventory_state(page)
                active_tab_label = _normalize_text(
                    current_state.active_tab_label or ""
                ).casefold()
        else:
            (
                _page_number,
                metrics,
                bounded_by_pagination_limit,
            ) = await _collect_browser_inventory_pages(
                browser=browser,
                page=page,
                current_state=initial_state,
                starting_page_number=page_number,
                request=request,
                normalized_url=normalized_url,
                archive_expected=archive_expected,
                pages=seeded_pages,
                candidates=seeded_candidates,
                metrics=metrics,
                ctx=ctx,
            )
            pages = seeded_pages
            candidates = seeded_candidates
        final_page_url = _normalize_absolute_url(await page.get_url()) or normalized_url
        route_summary = _build_browser_route_summary(
            normalized_url=normalized_url,
            pages=pages,
            metrics=metrics,
            used_tabs=bool(selected_tab_labels),
            bounded_by_pagination_limit=bounded_by_pagination_limit,
        )
        route_trace = _build_browser_route_trace(
            initial_state=initial_state,
            metrics=metrics,
            selected_tab_labels=selected_tab_labels,
        )
        return pages, candidates, final_page_url, route_summary, route_trace
    finally:
        await browser.kill()


async def _run_browser_traversal_with_timeout(
    *,
    browser: Any,
    request: PublisherInventoryServiceRequest,
    ctx: RunContext,
    normalized_url: str,
) -> tuple[
    list[PublisherInventoryPage],
    list[PublisherInventoryRawCandidate],
    str,
    str,
    PublisherInventoryRouteTrace,
]:
    return await asyncio.wait_for(
        _run_browser_traversal(
            browser=browser,
            request=request,
            ctx=ctx,
            normalized_url=normalized_url,
        ),
        timeout=max(float(request.settings.timeout_seconds), 1.0),
    )


def _page_target_id(page: Any) -> str:
    return str(getattr(page, "_target_id", "") or "").strip()


def _is_browser_placeholder_page_url(url: str) -> bool:
    normalized = str(url or "").strip().lower()
    return normalized in {
        "about:blank",
        "chrome://newtab",
        "chrome://newtab/",
        "chrome://new-tab-page",
        "chrome://new-tab-page/",
        "edge://newtab",
        "edge://newtab/",
    }


async def _close_unexpected_blank_pages(
    *,
    browser: Any,
    active_page: Any,
    ctx: RunContext,
    reason: str,
) -> None:
    get_pages = getattr(browser, "get_pages", None)
    close_page = getattr(browser, "close_page", None)
    if not callable(get_pages) or not callable(close_page):
        return
    active_target_id = _page_target_id(active_page)
    try:
        browser_pages = list(await get_pages() or [])
    except Exception as exc:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="publisher_inventory_browser_blank_page_cleanup_failed",
                module=logger.name,
                fields={
                    "reason": reason,
                    "active_target_id": active_target_id,
                    "error": str(exc),
                },
            )
        )
        return
    if not browser_pages:
        return
    closed_count = 0
    placeholder_count = 0
    for browser_page in browser_pages:
        if browser_page is active_page:
            continue
        target_id = _page_target_id(browser_page)
        if active_target_id and target_id == active_target_id:
            continue
        try:
            page_url = str(await browser_page.get_url() or "").strip()
        except Exception as exc:
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="publisher_inventory_browser_blank_page_url_failed",
                    module=logger.name,
                    fields={
                        "reason": reason,
                        "target_id": target_id,
                        "active_target_id": active_target_id,
                        "error": str(exc),
                    },
                )
            )
            continue
        if not _is_browser_placeholder_page_url(page_url):
            continue
        placeholder_count += 1
        try:
            await close_page(browser_page)
            closed_count += 1
        except Exception as exc:
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="publisher_inventory_browser_blank_page_close_failed",
                    module=logger.name,
                    fields={
                        "reason": reason,
                        "target_id": target_id,
                        "page_url": page_url,
                        "active_target_id": active_target_id,
                        "error": str(exc),
                    },
                )
            )
    if placeholder_count or len(browser_pages) > 1:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="publisher_inventory_browser_blank_page_cleanup",
                module=logger.name,
                fields={
                    "reason": reason,
                    "page_count": len(browser_pages),
                    "placeholder_count": placeholder_count,
                    "closed_count": closed_count,
                    "active_target_id": active_target_id,
                },
            )
        )


async def _extract_rendered_html_supplement_candidates(
    *,
    page: Any,
    state: _RenderedInventoryState,
    page_number: int,
    normalized_url: str,
    ctx: RunContext,
) -> list[PublisherInventoryRawCandidate]:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="publisher_inventory_browser_rendered_html_supplement_request",
            module=logger.name,
            fields={
                "page_url": state.page_url,
                "page_number": page_number,
            },
        )
    )
    try:
        html = str(await page.evaluate(_browser_rendered_html_script()) or "")
    except Exception as exc:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="publisher_inventory_browser_rendered_html_supplement_failed",
                module=logger.name,
                fields={
                    "page_url": state.page_url,
                    "page_number": page_number,
                    "error": str(exc),
                },
            )
        )
        return []
    logger.info(
        log_event(
            ctx,
            role="service",
            event="publisher_inventory_browser_rendered_html_supplement_response",
            module=logger.name,
            fields={
                "page_url": state.page_url,
                "page_number": page_number,
                "html_length": len(html),
            },
        )
    )
    parser = _InventoryHtmlParser()
    try:
        parser.feed(html)
    except Exception as exc:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="publisher_inventory_browser_rendered_html_supplement_invalid_html",
                module=logger.name,
                fields={
                    "page_url": state.page_url,
                    "page_number": page_number,
                    "error": str(exc),
                },
            )
        )
        return []
    anchors = list(parser.anchors)
    if not anchors:
        anchors = _extract_component_link_anchors(
            html_text=html,
            page_url=state.page_url,
        )
    candidates = _extract_candidates_from_html(
        anchors=anchors,
        page_url=state.page_url,
        page_number=page_number,
        next_page_url=None,
        origin_url=normalized_url,
        page_title=state.page_title,
        active_tab_label=state.active_tab_label,
        archive_surface=_is_archive_surface(state),
        provenance="browser_rendered_html_supplement",
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="publisher_inventory_browser_rendered_html_supplement_extracted",
            module=logger.name,
            fields={
                "page_url": state.page_url,
                "page_number": page_number,
                "candidate_count": len(candidates),
            },
        )
    )
    return candidates


async def _collect_browser_inventory_pages(
    *,
    browser: Any,
    page: Any,
    current_state: _RenderedInventoryState,
    starting_page_number: int,
    request: PublisherInventoryServiceRequest,
    normalized_url: str,
    archive_expected: bool,
    pages: list[PublisherInventoryPage],
    candidates: list[PublisherInventoryRawCandidate],
    metrics: _BrowserTraversalMetrics,
    ctx: RunContext,
) -> tuple[int, _BrowserTraversalMetrics, bool]:
    page_number = starting_page_number
    visited_navigation_urls: set[str] = set()
    empty_results_reset_urls: set[str] = set()
    origin_host_recovery_urls: set[str] = set()
    archive_surface_recovery_urls: set[str] = set()
    cumulative_candidate_urls: set[str] = {candidate.url for candidate in candidates}
    last_recorded_page_candidate_signature = _candidate_url_signature(
        [
            candidate
            for candidate in candidates
            if pages
            and candidate.discovered_on_page_number == pages[-1].page_number
            and candidate.source_page_url == pages[-1].page_url
        ]
    )
    seen_inventory_signatures: set[tuple[str, tuple[str, ...]]] = set()
    seen_candidate_signatures: set[tuple[str, ...]] = set()
    consecutive_zero_growth_pages = 0
    bounded_by_pagination_limit = False
    if pages and last_recorded_page_candidate_signature:
        seen_inventory_signatures.add(
            (
                _normalize_absolute_url(pages[-1].page_url) or pages[-1].page_url,
                last_recorded_page_candidate_signature,
            )
        )
        seen_candidate_signatures.add(last_recorded_page_candidate_signature)
    state = current_state
    while True:
        await _close_unexpected_blank_pages(
            browser=browser,
            active_page=page,
            ctx=ctx,
            reason="collect_loop",
        )
        await _prime_browser_inventory_surface(page)
        state = await _extract_rendered_inventory_state(page)
        if (
            state.empty_results_visible
            and state.reset_filter_labels
            and state.page_url not in empty_results_reset_urls
        ):
            reset_clicked = await _reset_empty_results_filters(
                page,
                labels=state.reset_filter_labels,
            )
            if reset_clicked:
                empty_results_reset_urls.add(state.page_url)
                await _wait_for_inventory_transition(
                    page,
                    previous_state=state,
                    current_candidate_count=0,
                )
                state = await _extract_rendered_inventory_state(page)
                continue
        next_page_url = _resolve_next_page_url(
            current_page_url=state.page_url,
            page_number=page_number,
            anchors=state.anchors,
            rel_next_hrefs=[],
        )
        page_candidates = _extract_candidates_from_html(
            anchors=state.anchors,
            page_url=state.page_url,
            page_number=page_number,
            next_page_url=next_page_url,
            origin_url=normalized_url,
            page_title=state.page_title,
            active_tab_label=state.active_tab_label,
            archive_surface=_is_archive_surface(state),
            provenance="browser_dom",
        )
        if archive_expected and _requires_archive_surface_recovery(
            state=state,
            page_candidates=page_candidates,
            normalized_url=normalized_url,
        ):
            if state.page_url not in archive_surface_recovery_urls:
                archive_surface_recovery_urls.add(state.page_url)
                await page.goto(normalized_url)
                await _browser_wait_for_settle(page=page)
                await _close_unexpected_blank_pages(
                    browser=browser,
                    active_page=page,
                    ctx=ctx,
                    reason="archive_surface_recovery",
                )
                state = await _extract_rendered_inventory_state(page)
                continue
            raise AppError(
                code="publisher_inventory_archive_drift",
                message="Browser-render inventory discovery drifted away from the archive surface",
                retryable=True,
                context={
                    "normalized_url": normalized_url,
                    "page_url": state.page_url,
                },
            )
        hydration_attempts = 0
        while hydration_attempts < 3 and _needs_additional_hydration(
            state,
            page_candidates=page_candidates,
            next_page_url=next_page_url,
        ):
            hydration_attempts += 1
            await _browser_wait_for_settle(
                page=page, delay_seconds=1.0, timeout_seconds=10.0
            )
            await _prime_browser_inventory_surface(page)
            state = await _extract_rendered_inventory_state(page)
            next_page_url = _resolve_next_page_url(
                current_page_url=state.page_url,
                page_number=page_number,
                anchors=state.anchors,
                rel_next_hrefs=[],
            )
            page_candidates = _extract_candidates_from_html(
                anchors=state.anchors,
                page_url=state.page_url,
                page_number=page_number,
                next_page_url=next_page_url,
                origin_url=normalized_url,
                page_title=state.page_title,
                active_tab_label=state.active_tab_label,
                archive_surface=_is_archive_surface(state),
                provenance="browser_dom",
            )
        if not page_candidates:
            page_candidates = await _extract_rendered_html_supplement_candidates(
                page=page,
                state=state,
                page_number=page_number,
                normalized_url=normalized_url,
                ctx=ctx,
            )
        if (
            not page_candidates
            and _requires_origin_host_recovery(
                page_url=state.page_url,
                normalized_url=normalized_url,
            )
            and state.page_url not in origin_host_recovery_urls
        ):
            origin_host_recovery_urls.add(state.page_url)
            await page.goto(normalized_url)
            await _browser_wait_for_settle(page=page)
            await _close_unexpected_blank_pages(
                browser=browser,
                active_page=page,
                ctx=ctx,
                reason="origin_host_recovery",
            )
            state = await _extract_rendered_inventory_state(page)
            continue
        new_candidate_urls = {
            candidate.url
            for candidate in page_candidates
            if candidate.url not in cumulative_candidate_urls
        }
        previous_page_url = pages[-1].page_url if pages else ""
        if (
            pages
            and state.page_url == previous_page_url
            and not new_candidate_urls
            and not (
                state.load_more_labels or next_page_url or state.has_pagination_next
            )
        ):
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="publisher_inventory_browser_inert_state_ignored",
                    module=logger.name,
                    fields={
                        "normalized_url": normalized_url,
                        "page_number": page_number,
                        "page_url": state.page_url,
                        "candidate_count": len(page_candidates),
                    },
                )
            )
            break
        same_page_entry = bool(
            pages
            and pages[-1].page_url == state.page_url
            and pages[-1].page_number == page_number
        )
        current_page_candidate_signature = _candidate_url_signature(page_candidates)
        current_inventory_signature = (
            _normalize_absolute_url(state.page_url) or state.page_url,
            current_page_candidate_signature,
        )
        if (
            current_page_candidate_signature
            and current_inventory_signature in seen_inventory_signatures
            and not same_page_entry
            and not new_candidate_urls
        ):
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="publisher_inventory_browser_cycle_detected",
                    module=logger.name,
                    fields={
                        "normalized_url": normalized_url,
                        "page_number": page_number,
                        "page_url": state.page_url,
                        "candidate_count": len(page_candidates),
                    },
                )
            )
            break
        if (
            current_page_candidate_signature
            and current_page_candidate_signature in seen_candidate_signatures
            and not same_page_entry
            and not new_candidate_urls
        ):
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="publisher_inventory_browser_cycle_detected",
                    module=logger.name,
                    fields={
                        "normalized_url": normalized_url,
                        "page_number": page_number,
                        "page_url": state.page_url,
                        "candidate_count": len(page_candidates),
                        "scope": "candidate_signature",
                    },
                )
            )
            break
        if not new_candidate_urls and page_number > 1:
            consecutive_zero_growth_pages += 1
        else:
            consecutive_zero_growth_pages = 0
        if consecutive_zero_growth_pages >= 2:
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="publisher_inventory_browser_cycle_detected",
                    module=logger.name,
                    fields={
                        "normalized_url": normalized_url,
                        "page_number": page_number,
                        "page_url": state.page_url,
                        "candidate_count": len(page_candidates),
                        "scope": "zero_growth_streak",
                    },
                )
            )
            break
        duplicate_page_inventory_state = bool(
            pages
            and pages[-1].page_url == state.page_url
            and last_recorded_page_candidate_signature
            == current_page_candidate_signature
        )
        if not same_page_entry and not duplicate_page_inventory_state:
            pages.append(
                PublisherInventoryPage(
                    schema_version="1.0",
                    page_number=page_number,
                    page_url=state.page_url,
                )
            )
            last_recorded_page_candidate_signature = current_page_candidate_signature
        if current_page_candidate_signature:
            seen_inventory_signatures.add(current_inventory_signature)
            seen_candidate_signatures.add(current_page_candidate_signature)
        page_candidates_to_add = [
            candidate
            for candidate in page_candidates
            if candidate.url not in cumulative_candidate_urls
        ]
        if not same_page_entry and not duplicate_page_inventory_state:
            page_candidates_to_add = page_candidates
        candidates.extend(page_candidates_to_add)
        cumulative_candidate_urls.update(
            candidate.url for candidate in page_candidates_to_add
        )
        logger.info(
            log_event(
                ctx,
                role="service",
                event="publisher_inventory_browser_page_extracted",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "page_number": page_number,
                    "page_url": state.page_url,
                    "candidate_count": len(page_candidates),
                    "has_load_more": bool(state.load_more_labels),
                    "has_pagination_next": state.has_pagination_next,
                    "result_range_end": state.result_range_end or 0,
                    "result_range_total": state.result_range_total or 0,
                    "page_index_hint": state.page_index_hint or 0,
                    "page_total_hint": state.page_total_hint or 0,
                    "next_page_url": next_page_url or "",
                    "active_tab_label": state.active_tab_label or "",
                },
            )
        )
        if _is_terminal_results_page(state):
            break
        if page_number >= request.settings.pagination_max_pages:
            if state.load_more_labels or next_page_url or state.has_pagination_next:
                if page_number > 1 and cumulative_candidate_urls:
                    bounded_by_pagination_limit = True
                    break
                raise AppError(
                    code="publisher_inventory_browser_pagination_limit",
                    message="Browser-render inventory discovery reached the pagination limit before exhausting the inventory",
                    retryable=False,
                    context={
                        "normalized_url": normalized_url,
                        "page_number": page_number,
                        "page_url": state.page_url,
                    },
                )
            break
        if next_page_url and next_page_url not in visited_navigation_urls:
            visited_navigation_urls.add(next_page_url)
            await page.goto(next_page_url)
            metrics = _BrowserTraversalMetrics(
                cookies_dismissed=metrics.cookies_dismissed,
                report_route_clicks=metrics.report_route_clicks,
                report_filter_applied=metrics.report_filter_applied,
                tab_clicks=metrics.tab_clicks,
                load_more_clicks=metrics.load_more_clicks,
                next_page_visits=metrics.next_page_visits + 1,
                archive_expansion_clicks=metrics.archive_expansion_clicks,
                button_pagination_clicks=metrics.button_pagination_clicks,
            )
            await _browser_wait_for_settle()
            await _close_unexpected_blank_pages(
                browser=browser,
                active_page=page,
                ctx=ctx,
                reason="next_page_navigation",
            )
            page_number += 1
            state = await _extract_rendered_inventory_state(page)
            continue
        if state.has_pagination_next:
            clicked = await _click_pagination_next(page)
            if not clicked:
                raise AppError(
                    code="publisher_inventory_browser_pagination_click_failed",
                    message="Browser-render inventory discovery could not activate the next pagination button",
                    retryable=True,
                    context={
                        "normalized_url": normalized_url,
                        "page_number": page_number,
                        "page_url": state.page_url,
                    },
                )
            await _close_unexpected_blank_pages(
                browser=browser,
                active_page=page,
                ctx=ctx,
                reason="pagination_click",
            )
            metrics = _BrowserTraversalMetrics(
                cookies_dismissed=metrics.cookies_dismissed,
                report_route_clicks=metrics.report_route_clicks,
                report_filter_applied=metrics.report_filter_applied,
                tab_clicks=metrics.tab_clicks,
                load_more_clicks=metrics.load_more_clicks,
                next_page_visits=metrics.next_page_visits,
                archive_expansion_clicks=metrics.archive_expansion_clicks,
                button_pagination_clicks=metrics.button_pagination_clicks + 1,
            )
            await _wait_for_inventory_transition(
                page,
                previous_state=state,
                current_candidate_count=len(page_candidates),
            )
            page_number += 1
            state = await _extract_rendered_inventory_state(page)
            continue
        if state.load_more_labels:
            load_more_result = await _click_load_more(
                page,
                state.load_more_labels,
                page_candidates=page_candidates,
                require_candidate_surface_match=True,
            )
            if load_more_result == "not_relevant":
                break
            if load_more_result != "clicked":
                raise AppError(
                    code="publisher_inventory_browser_load_more_failed",
                    message="Browser-render inventory discovery could not activate the next load-more step",
                    retryable=True,
                    context={
                        "normalized_url": normalized_url,
                        "page_number": page_number,
                        "page_url": state.page_url,
                    },
                )
            await _close_unexpected_blank_pages(
                browser=browser,
                active_page=page,
                ctx=ctx,
                reason="load_more_click",
            )
            growth_observed = await _wait_for_inventory_growth_probe(
                page,
                previous_state=state,
            )
            if not growth_observed:
                try:
                    await _wait_for_inventory_growth(
                        page,
                        previous_state=state,
                        current_candidate_count=len(page_candidates),
                    )
                except AppError as exc:
                    if exc.code == "publisher_inventory_browser_growth_timeout":
                        stalled_state = await _extract_rendered_inventory_state(page)
                        if _is_exhausted_inert_load_more(
                            previous_state=state,
                            stalled_state=stalled_state,
                        ):
                            break
                    raise
            metrics = _BrowserTraversalMetrics(
                cookies_dismissed=metrics.cookies_dismissed,
                report_route_clicks=metrics.report_route_clicks,
                report_filter_applied=metrics.report_filter_applied,
                tab_clicks=metrics.tab_clicks,
                load_more_clicks=metrics.load_more_clicks + 1,
                next_page_visits=metrics.next_page_visits,
                archive_expansion_clicks=metrics.archive_expansion_clicks,
                button_pagination_clicks=metrics.button_pagination_clicks,
            )
            page_number += 1
            state = await _extract_rendered_inventory_state(page)
            continue
        break
    return page_number + 1, metrics, bounded_by_pagination_limit


async def _extract_rendered_inventory_state(page: Any) -> _RenderedInventoryState:
    payload = json.loads(await page.evaluate(_browser_inventory_state_script()))
    page_url = _normalize_absolute_url(
        str(payload.get("page_url") or "")
    ) or _normalize_absolute_url(await page.get_url())
    anchors = [
        {
            "href": _normalize_text(item.get("href", "")),
            "text": _select_anchor_title(item),
            "rel": _normalize_text(item.get("rel", "")),
        }
        for item in payload.get("anchors", [])
        if isinstance(item, dict) and _normalize_text(item.get("href", ""))
    ]
    tab_labels = [
        _normalize_text(label)
        for label in payload.get("tab_labels", [])
        if _normalize_text(str(label or ""))
    ]
    active_tab_label = (
        _normalize_text(str(payload.get("active_tab_label") or "")) or None
    )
    report_link_url = (
        _normalize_absolute_url(str(payload.get("report_link_url") or "")) or None
    )
    return _RenderedInventoryState(
        page_url=page_url,
        page_title=_normalize_text(str(payload.get("page_title") or "")),
        anchors=anchors,
        load_more_labels=[
            _normalize_text(label)
            for label in payload.get("load_more_labels", [])
            if _normalize_text(str(label or ""))
        ],
        tab_labels=tab_labels,
        active_tab_label=active_tab_label,
        report_link_url=report_link_url,
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


async def _dismiss_cookie_banner(page: Any) -> bool:
    clicked = await page.evaluate(_browser_click_cookie_banner_script())
    return str(clicked).strip().lower() == "true"


async def _reset_empty_results_filters(page: Any, labels: list[str]) -> bool:
    clicked = await page.evaluate(_browser_click_named_control_script(), labels)
    return str(clicked).strip().lower() == "true"


async def _click_tab(page: Any, tab_label: str) -> bool:
    clicked = await page.evaluate(_browser_click_tab_script(), tab_label)
    return str(clicked).strip().lower() == "true"


async def _click_load_more(
    page: Any,
    labels: list[str],
    *,
    page_candidates: list[PublisherInventoryRawCandidate],
    require_candidate_surface_match: bool,
) -> str:
    result = (
        str(
            await page.evaluate(
                _browser_click_named_control_script(),
                {
                    "labels": labels,
                    "candidate_urls": [
                        candidate.url for candidate in page_candidates if candidate.url
                    ],
                    "require_candidate_surface": require_candidate_surface_match,
                },
            )
        )
        .strip()
        .lower()
    )
    if result == "not_relevant":
        return "not_relevant"
    return "clicked" if result == "true" else "missing"


async def _click_pagination_next(page: Any) -> bool:
    clicked = await page.evaluate(_browser_click_pagination_next_script())
    return str(clicked).strip().lower() == "true"


async def _click_archive_expander(page: Any) -> bool:
    clicked = await page.evaluate(_browser_click_archive_expander_script())
    return str(clicked).strip().lower() == "true"


async def _apply_report_filter(page: Any) -> bool:
    clicked = await page.evaluate(_browser_apply_report_filter_script())
    return str(clicked).strip().lower() == "true"


async def _wait_for_tab_activation(page: Any, tab_label: str) -> None:
    expected = _normalize_text(tab_label).casefold()
    for _ in range(20):
        await _browser_wait_for_settle(page=page, delay_seconds=0.35)
        state = await _extract_rendered_inventory_state(page)
        if str(state.active_tab_label or "").casefold() == expected:
            return
    raise AppError(
        code="publisher_inventory_browser_tab_activation_timeout",
        message="Browser-render inventory discovery did not observe the requested tab become active",
        retryable=True,
        context={"tab_label": tab_label},
    )


async def _wait_for_inventory_growth(
    page: Any,
    *,
    previous_state: _RenderedInventoryState,
    current_candidate_count: int,
) -> None:
    previous_candidate_urls = {
        candidate.url
        for candidate in _extract_candidates_from_html(
            anchors=previous_state.anchors,
            page_url=previous_state.page_url,
            page_number=1,
            next_page_url=None,
        )
    }
    previous_anchor_fingerprint = _rendered_state_anchor_fingerprint(previous_state)
    for _ in range(20):
        await _browser_wait_for_settle(page=page, delay_seconds=0.35)
        state = await _extract_rendered_inventory_state(page)
        if state.page_url != previous_state.page_url:
            return
        if (
            state.result_range_end is not None
            and previous_state.result_range_end is not None
            and (
                state.result_range_end != previous_state.result_range_end
                or state.result_range_total != previous_state.result_range_total
            )
        ):
            return
        next_page_url = _resolve_next_page_url(
            current_page_url=state.page_url,
            page_number=1,
            anchors=state.anchors,
            rel_next_hrefs=[],
        )
        current_candidates = _extract_candidates_from_html(
            anchors=state.anchors,
            page_url=state.page_url,
            page_number=1,
            next_page_url=next_page_url,
        )
        current_candidate_urls = {candidate.url for candidate in current_candidates}
        if (
            len(current_candidates) > current_candidate_count
            or current_candidate_urls != previous_candidate_urls
        ):
            return
        if _rendered_state_anchor_fingerprint(state) != previous_anchor_fingerprint:
            return
    raise AppError(
        code="publisher_inventory_browser_growth_timeout",
        message="Browser-render inventory discovery did not observe new inventory items after interaction",
        retryable=True,
    )


async def _wait_for_inventory_growth_probe(
    page: Any,
    *,
    previous_state: _RenderedInventoryState,
    delay_seconds: float = 0.2,
    timeout_seconds: float = 4.0,
) -> bool:
    previous_url = (
        _normalize_absolute_url(previous_state.page_url) or previous_state.page_url
    )
    previous_anchor_count = len(previous_state.anchors)
    max_attempts = max(1, int(timeout_seconds / delay_seconds))
    for _ in range(max_attempts):
        await asyncio.sleep(delay_seconds)
        try:
            payload = json.loads(
                await page.evaluate(
                    """() => JSON.stringify({
                        pageUrl: window.location.href || '',
                        anchorCount: document.querySelectorAll('a[href]').length || 0,
                    })"""
                )
            )
        except Exception:
            continue
        current_url = _normalize_absolute_url(str(payload.get("pageUrl") or "")) or ""
        if current_url and current_url != previous_url:
            return True
        if int(payload.get("anchorCount") or 0) > previous_anchor_count:
            return True
    return False


async def _wait_for_inventory_transition(
    page: Any,
    *,
    previous_state: _RenderedInventoryState,
    current_candidate_count: int,
) -> None:
    previous_urls = {
        candidate.url
        for candidate in _extract_candidates_from_html(
            anchors=previous_state.anchors,
            page_url=previous_state.page_url,
            page_number=1,
            next_page_url=None,
        )
    }
    for _ in range(20):
        await _browser_wait_for_settle(page=page, delay_seconds=0.35)
        state = await _extract_rendered_inventory_state(page)
        if state.page_url != previous_state.page_url:
            return
        if (
            state.result_range_end is not None
            and previous_state.result_range_end is not None
            and (
                state.result_range_end != previous_state.result_range_end
                or state.result_range_total != previous_state.result_range_total
            )
        ):
            return
        next_page_url = _resolve_next_page_url(
            current_page_url=state.page_url,
            page_number=1,
            anchors=state.anchors,
            rel_next_hrefs=[],
        )
        current_candidates = _extract_candidates_from_html(
            anchors=state.anchors,
            page_url=state.page_url,
            page_number=1,
            next_page_url=next_page_url,
        )
        current_urls = {candidate.url for candidate in current_candidates}
        if previous_state.result_range_end is None and (
            len(current_candidates) > current_candidate_count
            or current_urls != previous_urls
        ):
            return
    raise AppError(
        code="publisher_inventory_browser_transition_timeout",
        message="Browser-render inventory discovery did not observe a page transition after pagination click",
        retryable=True,
    )


async def _prime_browser_inventory_surface(page: Any) -> None:
    for ratio in (0.0, 0.35, 0.7, 0.95):
        await page.evaluate(_browser_scroll_to_ratio_script(), ratio)
        await _browser_wait_for_settle(page=page, delay_seconds=0.35)


async def _browser_wait_for_settle(
    *,
    page: Any | None = None,
    delay_seconds: float = 1.0,
    timeout_seconds: float = 15.0,
) -> None:
    if page is None:
        await asyncio.sleep(delay_seconds)
        return
    max_attempts = max(1, int(timeout_seconds / delay_seconds))
    for _ in range(max_attempts):
        await asyncio.sleep(delay_seconds)
        try:
            payload = json.loads(
                await page.evaluate(
                    """() => JSON.stringify({
                        readyState: document.readyState || '',
                        title: document.title || '',
                        anchorCount: document.querySelectorAll('a[href]').length || 0,
                    })"""
                )
            )
        except Exception:
            continue
        ready_state = str(payload.get("readyState") or "").strip().lower()
        title = str(payload.get("title") or "").strip()
        anchor_count = int(payload.get("anchorCount") or 0)
        if ready_state == "complete" and (title or anchor_count > 0):
            return


def _browser_named_control_selector() -> str:
    return (
        "button, "
        '[role="button"], '
        'a[role="button"], '
        "a.button, "
        "a.btn, "
        "a.wp-block-button__link, "
        "a.cursor-pointer, "
        'a[class*="btn"], '
        'input[type="button"], '
        'input[type="submit"], '
        ".load-more"
    )


def _browser_scroll_to_ratio_script() -> str:
    return """(ratio) => {
        const value = Number(ratio || 0);
        const maxY = Math.max(
            0,
            Math.max(
                document.body ? document.body.scrollHeight : 0,
                document.documentElement ? document.documentElement.scrollHeight : 0
            ) - window.innerHeight
        );
        const clamped = Math.max(0, Math.min(1, value));
        window.scrollTo(0, Math.round(maxY * clamped));
        return true;
    }"""


def _browser_inventory_state_script() -> str:
    named_control_selector = json.dumps(_browser_named_control_selector())
    script = """() => {
        const namedControlSelector = __NAMED_CONTROL_SELECTOR__;
        const normalize = (value) => String(value ?? '').replace(/\\s+/g, ' ').trim();
        const isVisible = (element) => {
            if (!element) return false;
            const style = window.getComputedStyle(element);
            const rect = element.getBoundingClientRect();
            return style && style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0;
        };
        const isEnabled = (element) => {
            if (!element) return false;
            const ariaDisabled = normalize(element.getAttribute('aria-disabled')).toLowerCase();
            const className = normalize(element.className || '').toLowerCase();
            return !element.disabled && ariaDisabled !== 'true' && !/\\bdisabled\\b/.test(className);
        };
        const anchors = Array.from(document.querySelectorAll('a[href]')).map((anchor) => {
            const image = anchor.querySelector('img');
            const card = anchor.closest('article, li, section, div');
            const heading = card ? card.querySelector('h1, h2, h3, h4, h5, h6') : null;
            return {
                href: normalize(anchor.href || anchor.getAttribute('href') || ''),
                text: normalize(anchor.textContent),
                rel: normalize(anchor.getAttribute('rel')),
                aria_label: normalize(anchor.getAttribute('aria-label')),
                title_attr: normalize(anchor.getAttribute('title')),
                img_alt: normalize(image ? image.getAttribute('alt') : ''),
                heading_text: normalize(heading ? heading.textContent : ''),
                context_text: normalize(card ? card.textContent : ''),
                visible: isVisible(anchor),
            };
        }).filter((item) => item.href && item.visible);
        const collectLabels = (elements) => elements
            .filter((element) => isVisible(element) && isEnabled(element))
            .map((element) => normalize(element.textContent || element.getAttribute('aria-label') || element.value || ''))
            .filter((label) => label);
        const controlEntries = Array.from(document.querySelectorAll(namedControlSelector))
            .filter((element) => isVisible(element) && isEnabled(element))
            .map((element) => ({
                element,
                label: normalize(element.textContent || element.getAttribute('aria-label') || element.value || ''),
            }))
            .filter((entry) => entry.label);
        const paginationContainerSelector = '[aria-label*="pagination" i], [class*="pagination" i], [data-testid*="pagination" i], nav, ul, ol';
        const isPaginationNextLabel = (label) => /^(next|next page|>|>>|»)$/i.test(label);
        const pageCountText = Array.from(document.querySelectorAll('body *'))
            .filter((element) => isVisible(element))
            .map((element) => normalize(element.textContent || ''))
            .filter((text) => /^page\\s+\\d+\\s+of\\s+\\d+$/i.test(text))
            .pop() || '';
        const pageCountMatch = pageCountText.match(/^page\\s+(\\d+)\\s+of\\s+(\\d+)$/i);
        const visibleContainerLabels = (container) => Array.from(container.querySelectorAll(namedControlSelector))
            .filter((element) => isVisible(element) && isEnabled(element))
            .map((element) => normalize(element.textContent || element.getAttribute('aria-label') || element.value || ''))
            .filter((label) => label);
        const paginationContainers = Array.from(new Set(
            controlEntries
                .map((entry) => entry.element.closest(paginationContainerSelector))
                .filter((container) => container)
        ));
        const hasPaginationNext = paginationContainers.some((container) => {
            const labels = visibleContainerLabels(container);
            return labels.some((label) => /^\\d+$/.test(label)) && labels.some((label) => isPaginationNextLabel(label));
        }) || (
            controlEntries.some((entry) => /^\\d+$/.test(entry.label)) &&
            controlEntries.some((entry) => isPaginationNextLabel(entry.label))
        ) || (
            Boolean(pageCountMatch) &&
            controlEntries.some((entry) => isPaginationNextLabel(entry.label))
        );
        const loadMoreLabels = collectLabels(
            Array.from(document.querySelectorAll(namedControlSelector))
                .filter((element) => /(^|\\b)(load|show|view|see)\\b.*\\b(more|all|next)\\b|^more$/i.test(normalize(element.textContent || element.getAttribute('aria-label') || element.value || '')))
        );
        const tabs = Array.from(document.querySelectorAll('[role="tab"]'));
        const tabLabels = tabs
            .filter((tab) => isVisible(tab))
            .map((tab) => normalize(tab.textContent || tab.getAttribute('aria-label') || ''))
            .filter((label) => label);
        const activeTab = tabs.find((tab) => (tab.getAttribute('aria-selected') || '').toLowerCase() === 'true');
        const reportLink = Array.from(document.querySelectorAll('a[href]'))
            .find((anchor) => {
                const href = normalize(anchor.href || anchor.getAttribute('href') || '');
                const label = normalize(anchor.textContent || anchor.getAttribute('aria-label') || '');
                if (!href || !label) return false;
                if (href.replace(/\\/$/, '') === window.location.href.replace(/\\/$/, '')) return false;
                return (
                    (href.includes('/insights/report/') && /report/i.test(label || href)) ||
                    (
                        /(explore|view|see|browse|open|discover)( all)?/i.test(label) &&
                        /(report|reports|research|resource|resources|library|white paper|whitepaper|ebook)/i.test(label)
                    ) ||
                    (
                        /(report|reports|research|resource library|resource center|white paper|whitepaper|ebook)/i.test(label) &&
                        /\\/(reports?|resources?|resource-library|knowledge-hub|library)\\//i.test(href)
                    )
                );
            });
        const reportFilter = Array.from(document.querySelectorAll('label, button, div, span')).some((element) => {
            const label = normalize(element.textContent || element.getAttribute('aria-label') || '');
            return label === 'Report' || label === 'Reports';
        });
        const applyButton = Array.from(document.querySelectorAll('button, input[type="submit"], input[type="button"]'))
            .some((element) => /^apply$/i.test(normalize(element.textContent || element.value || element.getAttribute('aria-label') || '')) && isVisible(element));
        const emptyResultsVisible = Array.from(document.querySelectorAll('body *'))
            .filter((element) => isVisible(element))
            .map((element) => normalize(element.textContent || ''))
            .some((text) => /couldn't find any matches|no matches|no results|no resources found|try adjusting your filters|clear(?:ing)? your filters/i.test(text));
        const resetFilterLabels = collectLabels(
            Array.from(document.querySelectorAll(namedControlSelector))
                .filter((element) => /^(reset|clear)( all)? filters?$|^reset all$|^clear all$/i.test(normalize(element.textContent || element.getAttribute('aria-label') || element.value || '')))
        );
        const resultRangeText = Array.from(document.querySelectorAll('body *'))
            .filter((element) => isVisible(element))
            .map((element) => normalize(element.textContent || ''))
            .filter((text) => /\\d+\\s*-\\s*\\d+\\s+of\\s+\\d+\\s+results/i.test(text))
            .pop() || '';
        const resultRangeMatch = resultRangeText.match(/(\\d+)\\s*-\\s*(\\d+)\\s+of\\s+(\\d+)\\s+results/i);
        return {
            page_url: window.location.href,
            page_title: document.title,
            anchors,
            load_more_labels: loadMoreLabels,
            tab_labels: tabLabels,
            active_tab_label: normalize(activeTab ? activeTab.textContent || activeTab.getAttribute('aria-label') || '' : ''),
            report_link_url: reportLink ? normalize(reportLink.href || reportLink.getAttribute('href') || '') : '',
            empty_results_visible: emptyResultsVisible,
            reset_filter_labels: resetFilterLabels,
            has_report_filter: reportFilter,
            has_apply_button: applyButton,
            has_pagination_next: hasPaginationNext,
            result_range_end: resultRangeMatch ? Number(resultRangeMatch[2]) : 0,
            result_range_total: resultRangeMatch ? Number(resultRangeMatch[3]) : 0,
            page_index_hint: pageCountMatch ? Number(pageCountMatch[1]) : 0,
            page_total_hint: pageCountMatch ? Number(pageCountMatch[2]) : 0,
        };
    }"""
    return script.replace("__NAMED_CONTROL_SELECTOR__", named_control_selector)


def _browser_rendered_html_script() -> str:
    return (
        """() => document.documentElement ? document.documentElement.outerHTML : ''"""
    )


def _browser_click_named_control_script() -> str:
    named_control_selector = json.dumps(_browser_named_control_selector())
    script = """(payloadOrLabels) => {
        const namedControlSelector = __NAMED_CONTROL_SELECTOR__;
        const normalize = (value) => String(value ?? '').replace(/\\s+/g, ' ').trim().toLowerCase();
        const payload = Array.isArray(payloadOrLabels)
            ? { labels: payloadOrLabels, candidate_urls: [] }
            : (payloadOrLabels || {});
        const wanted = Array.isArray(payload.labels) ? payload.labels.map((item) => normalize(item)).filter((item) => item) : [];
        const requireCandidateSurface = payload.require_candidate_surface === true;
        const normalizeHref = (value) => {
            const raw = String(value ?? '').trim();
            if (!raw) return '';
            try {
                const parsed = new URL(raw, window.location.href);
                parsed.hash = '';
                return parsed.href.replace(/\\/$/, '');
            } catch (_error) {
                return normalize(raw);
            }
        };
        const candidateUrls = new Set(
            (Array.isArray(payload.candidate_urls) ? payload.candidate_urls : [])
                .map((item) => normalizeHref(String(item || '')))
                .filter((item) => item)
        );
        const isVisible = (element) => {
            if (!element) return false;
            const style = window.getComputedStyle(element);
            const rect = element.getBoundingClientRect();
            return style && style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0;
        };
        const isEnabled = (element) => {
            if (!element) return false;
            const ariaDisabled = normalize(element.getAttribute('aria-disabled')).toLowerCase();
            const className = normalize(element.className || '').toLowerCase();
            return !element.disabled && ariaDisabled !== 'true' && !/\\bdisabled\\b/.test(className);
        };
        const collectVisibleAnchorHrefs = (container) => {
            if (!container || typeof container.querySelectorAll !== 'function') return [];
            return Array.from(container.querySelectorAll('a[href]'))
                .filter((anchor) => isVisible(anchor))
                .map((anchor) => normalizeHref(anchor.href || anchor.getAttribute('href') || ''))
                .filter((href) => href);
        };
        const scoreElement = (element, index) => {
            let bestExactHits = 0;
            let bestAnchorCount = Number.MAX_SAFE_INTEGER;
            let node = element;
            let depth = 0;
            while (node && depth < 8) {
                if (node instanceof Element) {
                    const hrefs = collectVisibleAnchorHrefs(node);
                    const exactHits = hrefs.filter((href) => candidateUrls.has(href)).length;
                    if (exactHits > bestExactHits) {
                        bestExactHits = exactHits;
                        bestAnchorCount = hrefs.length || Number.MAX_SAFE_INTEGER;
                    } else if (exactHits > 0 && exactHits === bestExactHits) {
                        bestAnchorCount = Math.min(bestAnchorCount, hrefs.length || Number.MAX_SAFE_INTEGER);
                    }
                }
                node = node.parentElement;
                depth += 1;
            }
            return {
                element,
                index,
                exactHits: bestExactHits,
                anchorCount: bestAnchorCount,
                top: Math.round(element.getBoundingClientRect().top || 0),
            };
        };
        const elements = Array.from(document.querySelectorAll(namedControlSelector));
        const matches = [];
        for (const [index, element] of elements.entries()) {
            const label = normalize(element.textContent || element.getAttribute('aria-label') || element.value || '');
            if (!label || !isVisible(element) || !isEnabled(element)) continue;
            if (wanted.some((candidate) => label === candidate || label.includes(candidate))) {
                matches.push({ label, ...scoreElement(element, index) });
            }
        }
        matches.sort((left, right) => {
            if (right.exactHits !== left.exactHits) return right.exactHits - left.exactHits;
            if (left.exactHits > 0 && left.anchorCount !== right.anchorCount) {
                return left.anchorCount - right.anchorCount;
            }
            if (right.top !== left.top) return right.top - left.top;
            return right.index - left.index;
        });
        const target = matches[0];
        if (!target) return false;
        const minRelevantHits = candidateUrls.size > 0
            ? (candidateUrls.size > 4 ? Math.min(3, Math.ceil(candidateUrls.size / 4)) : 1)
            : 0;
        if (requireCandidateSurface && candidateUrls.size > 0 && target.exactHits < minRelevantHits) {
            return 'not_relevant';
        }
        if (typeof target.element.scrollIntoView === 'function') {
            target.element.scrollIntoView({ block: 'center', inline: 'center' });
        }
        target.element.click();
        return true;
    }"""
    return script.replace("__NAMED_CONTROL_SELECTOR__", named_control_selector)


def _browser_click_cookie_banner_script() -> str:
    named_control_selector = json.dumps(_browser_named_control_selector())
    script = """() => {
        const namedControlSelector = __NAMED_CONTROL_SELECTOR__;
        const normalize = (value) => String(value ?? '').replace(/\\s+/g, ' ').trim().toLowerCase();
        const isVisible = (element) => {
            if (!element) return false;
            const style = window.getComputedStyle(element);
            const rect = element.getBoundingClientRect();
            return style && style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0;
        };
        const isEnabled = (element) => {
            if (!element) return false;
            const ariaDisabled = normalize(element.getAttribute('aria-disabled')).toLowerCase();
            const className = normalize(element.className || '').toLowerCase();
            return !element.disabled && ariaDisabled !== 'true' && !/\\bdisabled\\b/.test(className);
        };
        const wanted = [
            'accept all cookies',
            'accept all',
            'accept',
            'agree',
            'ok',
            'close',
            'continue',
        ];
        const bannerSelector = [
            '[id*="cookie" i]',
            '[class*="cookie" i]',
            '[id*="consent" i]',
            '[class*="consent" i]',
            '[id*="onetrust" i]',
            '[class*="onetrust" i]',
            '[aria-label*="cookie" i]',
            '[aria-label*="consent" i]',
            '[role="dialog"]',
            '[role="region"]'
        ].join(', ');
        const containers = Array.from(document.querySelectorAll(bannerSelector))
            .filter((element) => isVisible(element))
            .filter((element) => {
                const descriptor = normalize([
                    element.id || '',
                    element.className || '',
                    element.getAttribute('aria-label') || '',
                    element.textContent || '',
                ].join(' '));
                return /(cookie|consent|privacy|onetrust)/i.test(descriptor);
            });
        for (const container of containers) {
            const controls = Array.from(container.querySelectorAll(namedControlSelector))
                .filter((element) => isVisible(element) && isEnabled(element))
                .map((element) => ({
                    element,
                    label: normalize(element.textContent || element.getAttribute('aria-label') || element.value || ''),
                }))
                .filter((entry) => entry.label);
            const target = controls.find((entry) => wanted.some((label) => entry.label === label || entry.label.includes(label)));
            if (!target) continue;
            if (typeof target.element.scrollIntoView === 'function') {
                target.element.scrollIntoView({ block: 'center', inline: 'center' });
            }
            target.element.click();
            return true;
        }
        return false;
    }"""
    return script.replace("__NAMED_CONTROL_SELECTOR__", named_control_selector)


def _browser_click_pagination_next_script() -> str:
    named_control_selector = json.dumps(_browser_named_control_selector())
    script = """() => {
        const namedControlSelector = __NAMED_CONTROL_SELECTOR__;
        const normalize = (value) => String(value ?? '').replace(/\\s+/g, ' ').trim().toLowerCase();
        const isVisible = (element) => {
            if (!element) return false;
            const style = window.getComputedStyle(element);
            const rect = element.getBoundingClientRect();
            return style && style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0;
        };
        const isEnabled = (element) => {
            if (!element) return false;
            const ariaDisabled = normalize(element.getAttribute('aria-disabled')).toLowerCase();
            const className = normalize(element.className || '').toLowerCase();
            return !element.disabled && ariaDisabled !== 'true' && !/\\bdisabled\\b/.test(className);
        };
        const paginationContainerSelector = '[aria-label*="pagination" i], [class*="pagination" i], [data-testid*="pagination" i], nav, ul, ol';
        const isPaginationNextLabel = (label) => /^(next|next page|>|>>|»)$/i.test(label);
        const pageCountText = Array.from(document.querySelectorAll('body *'))
            .filter((element) => isVisible(element))
            .map((element) => normalize(element.textContent || ''))
            .filter((text) => /^page\\s+\\d+\\s+of\\s+\\d+$/i.test(text))
            .pop() || '';
        const pageCountMatch = pageCountText.match(/^page\\s+(\\d+)\\s+of\\s+(\\d+)$/i);
        const controlEntries = Array.from(document.querySelectorAll(namedControlSelector))
            .filter((element) => isVisible(element) && isEnabled(element))
            .map((element) => ({
                element,
                label: normalize(element.textContent || element.getAttribute('aria-label') || element.value || ''),
            }))
            .filter((entry) => entry.label);
        const visibleContainerEntries = (container) => Array.from(container.querySelectorAll(namedControlSelector))
            .filter((element) => isVisible(element) && isEnabled(element))
            .map((element) => ({
                element,
                label: normalize(element.textContent || element.getAttribute('aria-label') || element.value || ''),
            }))
            .filter((entry) => entry.label);
        const paginationContainers = Array.from(new Set(
            controlEntries
                .map((entry) => entry.element.closest(paginationContainerSelector))
                .filter((container) => container)
        ));
        for (const container of paginationContainers) {
            const entries = visibleContainerEntries(container);
            if (!entries.some((entry) => /^\\d+$/.test(entry.label))) continue;
            const nextEntry = entries.find((entry) => isPaginationNextLabel(entry.label));
            if (!nextEntry) continue;
            if (typeof nextEntry.element.scrollIntoView === 'function') {
                nextEntry.element.scrollIntoView({ block: 'center', inline: 'center' });
            }
            nextEntry.element.click();
            return true;
        }
        if (pageCountMatch) {
            const nextEntry = controlEntries.find((entry) => isPaginationNextLabel(entry.label));
            if (nextEntry) {
                if (typeof nextEntry.element.scrollIntoView === 'function') {
                    nextEntry.element.scrollIntoView({ block: 'center', inline: 'center' });
                }
                nextEntry.element.click();
                return true;
            }
        }
        if (controlEntries.some((entry) => /^\\d+$/.test(entry.label))) {
            const nextEntry = controlEntries.find((entry) => isPaginationNextLabel(entry.label));
            if (nextEntry) {
                if (typeof nextEntry.element.scrollIntoView === 'function') {
                    nextEntry.element.scrollIntoView({ block: 'center', inline: 'center' });
                }
                nextEntry.element.click();
                return true;
            }
        }
        return false;
    }"""
    return script.replace("__NAMED_CONTROL_SELECTOR__", named_control_selector)


def _browser_click_archive_expander_script() -> str:
    return """() => {
        const normalize = (value) => String(value ?? '').replace(/\\s+/g, ' ').trim().toLowerCase();
        const isVisible = (element) => {
            if (!element) return false;
            const style = window.getComputedStyle(element);
            const rect = element.getBoundingClientRect();
            return style && style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0;
        };
        const controls = Array.from(document.querySelectorAll('button, [role="button"], a[role="button"], a.button, a.btn, a.wp-block-button__link, a.cursor-pointer, a[class*="btn"], a[href], input[type="button"], input[type="submit"]'))
            .filter((element) => isVisible(element))
            .map((element) => {
                const label = normalize(element.textContent || element.value || element.getAttribute('aria-label') || '');
                const href = normalize(element.getAttribute('href') || '');
                let score = 0;
                if (/(view|explore|see|show|browse|open)( all)?/.test(label)) score += 3;
                if (/(library|archive|entries|items|reports?|resources?|research|collection)/.test(label)) score += 4;
                if (/\\d+\\+?/.test(label)) score += 2;
                if (/#\\/(feed|library|archive)/.test(href)) score += 4;
                if (/\\/(reports?|resources?|resource-library|knowledge-hub|library|archive)\\b/.test(href)) score += 3;
                if (!href || href === '#') score += 1;
                return { element, score };
            })
            .filter((entry) => entry.score >= 7)
            .sort((left, right) => right.score - left.score);
        if (!controls.length) return false;
        if (typeof controls[0].element.scrollIntoView === 'function') {
            controls[0].element.scrollIntoView({ block: 'center', inline: 'center' });
        }
        controls[0].element.click();
        return true;
    }"""


def _browser_click_tab_script() -> str:
    return """(tabLabel) => {
        const normalize = (value) => String(value ?? '').replace(/\\s+/g, ' ').trim().toLowerCase();
        const target = normalize(tabLabel);
        const isVisible = (element) => {
            if (!element) return false;
            const style = window.getComputedStyle(element);
            const rect = element.getBoundingClientRect();
            return style && style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0;
        };
        const tabs = Array.from(document.querySelectorAll('[role="tab"]'));
        for (const tab of tabs) {
            const label = normalize(tab.textContent || tab.getAttribute('aria-label') || '');
            if (!label || !isVisible(tab) || label !== target) continue;
            tab.click();
            return true;
        }
        return false;
    }"""


def _browser_apply_report_filter_script() -> str:
    return """() => {
        const normalize = (value) => String(value ?? '').replace(/\\s+/g, ' ').trim().toLowerCase();
        const isVisible = (element) => {
            if (!element) return false;
            const style = window.getComputedStyle(element);
            const rect = element.getBoundingClientRect();
            return style && style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0;
        };
        const candidates = Array.from(document.querySelectorAll('input[type="checkbox"], input[type="radio"], [role="checkbox"]'));
        const preferredOptionLabels = [
            'report',
            'reports',
            'whitepaper',
            'whitepapers',
            'white paper',
            'ebook',
            'ebooks',
            'insight guide',
            'insight guides',
            'study',
            'studies',
            'research report',
            'research reports',
            'benchmark',
            'benchmarks',
            'playbook',
            'playbooks',
        ];
        const isPreferredOptionLabel = (label) => preferredOptionLabels.some((candidate) => (
            label === candidate ||
            label.startsWith(candidate + ' ') ||
            label.startsWith(candidate + '(') ||
            label.includes(' ' + candidate + ' ')
        ));
        const applyButtons = Array.from(document.querySelectorAll('button, input[type="submit"], input[type="button"]'));
        const clickApplyIfPresent = () => {
            for (const button of applyButtons) {
                const label = normalize(button.textContent || button.value || button.getAttribute('aria-label') || '');
                if (label === 'apply' && isVisible(button)) {
                    button.click();
                    return true;
                }
            }
            return false;
        };
        let toggled = false;
        for (const element of candidates) {
            const labelledBy = element.id ? document.querySelector(`label[for="${element.id}"]`) : null;
            const container = element.closest('label, div, li');
            const label = normalize(
                (labelledBy ? labelledBy.textContent : '') ||
                (container ? container.textContent : '') ||
                element.getAttribute('aria-label') ||
                ''
            );
            if ((label === 'report' || label === 'reports') && isVisible(element)) {
                const checked = element.checked === true || element.getAttribute('aria-checked') === 'true';
                if (!checked) {
                    element.click();
                }
                toggled = true;
                break;
            }
        }
        if (toggled) {
            if (clickApplyIfPresent()) {
                return true;
            }
            return true;
        }
        const selects = Array.from(document.querySelectorAll('select'))
            .filter((element) => isVisible(element) && !element.disabled);
        for (const select of selects) {
            const options = Array.from(select.options || [])
                .map((option) => ({
                    value: option.value,
                    label: normalize(option.textContent || option.label || ''),
                    selected: option.selected === true,
                }))
                .filter((entry) => entry.label);
            if (!options.length) continue;
            const preferred = options.find((entry) => isPreferredOptionLabel(entry.label));
            if (!preferred || preferred.selected) continue;
            select.value = preferred.value;
            select.dispatchEvent(new Event('input', { bubbles: true }));
            select.dispatchEvent(new Event('change', { bubbles: true }));
            if (clickApplyIfPresent()) {
                return true;
            }
            return true;
        }
        return false;
    }"""


def _extract_browser_http_supplement_candidates(
    *,
    request: PublisherInventoryServiceRequest,
    page: PublisherInventoryPage,
    normalized_url: str,
    ctx: RunContext,
) -> list[PublisherInventoryRawCandidate]:
    headers = dict(HTTP_BROWSER_HEADERS)
    request_urls: list[str] = []
    for candidate_url in (page.page_url, normalized_url):
        normalized_candidate = _normalize_absolute_url(candidate_url)
        if normalized_candidate and normalized_candidate not in request_urls:
            request_urls.append(normalized_candidate)

    response = None
    for request_url in request_urls:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="publisher_inventory_browser_http_supplement_request",
                module=logger.name,
                fields={
                    "page_url": page.page_url,
                    "page_number": page.page_number,
                    "request_url": request_url,
                    "headers": headers,
                },
            )
        )
        try:
            response = execute_http_acquisition(
                request=HttpAcquisitionRequest(
                    schema_version="1.0",
                    purpose="publisher_inventory_browser_http_supplement",
                    method="GET",
                    url=request_url,
                    headers=headers,
                    timeout_seconds=request.settings.http_timeout_seconds,
                    response_policy=HttpAcquisitionResponsePolicy(
                        schema_version="1.0",
                        require_success_status=True,
                        capture_text=True,
                        capture_content_type_markers=("html", "xml"),
                        max_body_bytes=_HTTP_SUPPLEMENT_HTML_MAX_BYTES,
                        truncate_body=True,
                    ),
                    error_code="publisher_inventory_http_failed",
                    error_message="Failed to fetch publisher inventory page via HTTP",
                    context_fields={
                        "page_url": page.page_url,
                        "page_number": str(page.page_number),
                        "request_url": request_url,
                    },
                ),
                ctx=ctx,
                requests_module=requests,
            )
            break
        except AppError as exc:
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="publisher_inventory_browser_http_supplement_failed",
                    module=logger.name,
                    fields={
                        "page_url": page.page_url,
                        "page_number": page.page_number,
                        "request_url": request_url,
                        "error": exc.message,
                    },
                )
            )
            response = None
    if response is None:
        return []

    final_page_url = _validate_and_normalize_url(
        str(response.final_url or page.page_url)
    )
    html = str(response.text_body or "")
    logger.info(
        log_event(
            ctx,
            role="service",
            event="publisher_inventory_browser_http_supplement_response",
            module=logger.name,
            fields={
                "page_url": page.page_url,
                "page_number": page.page_number,
                "final_page_url": final_page_url,
                "status_code": response.status_code,
                "html_length": len(html),
                "body_truncated": response.body_truncated,
            },
        )
    )
    parser = _InventoryHtmlParser()
    try:
        parser.feed(html)
    except Exception as exc:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="publisher_inventory_browser_http_supplement_invalid_html",
                module=logger.name,
                fields={
                    "page_url": page.page_url,
                    "page_number": page.page_number,
                    "request_url": final_page_url,
                    "error": str(exc),
                },
            )
        )
        return []
    anchors = list(parser.anchors)
    if not anchors:
        anchors = _extract_component_link_anchors(
            html_text=html,
            page_url=final_page_url,
        )
    candidates = _extract_candidates_from_html(
        anchors=anchors,
        page_url=final_page_url,
        page_number=page.page_number,
        next_page_url=None,
        origin_url=normalized_url,
        provenance="http_supplement",
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="publisher_inventory_browser_http_supplement_extracted",
            module=logger.name,
            fields={
                "page_url": page.page_url,
                "page_number": page.page_number,
                "candidate_count": len(candidates),
            },
        )
    )
    return candidates


def _candidate_provenance_counts(
    candidates: list[PublisherInventoryRawCandidate],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for candidate in candidates:
        provenance = str(candidate.provenance or "unknown").strip() or "unknown"
        counts[provenance] = counts.get(provenance, 0) + 1
    return counts


def _validate_request(
    request: PublisherInventoryServiceRequest,
    normalized_url: str,
) -> None:
    if not normalized_url:
        raise AppError(
            code="publisher_inventory_url_invalid",
            message="A valid absolute insights URL is required for publisher inventory discovery",
            retryable=False,
        )
    if not request.settings.openrouter_api_key.strip():
        raise AppError(
            code="publisher_inventory_api_key_missing",
            message="OPENROUTER_API_KEY is required for publisher inventory discovery",
            retryable=False,
        )
    if not request.settings.model.strip():
        raise AppError(
            code="publisher_inventory_model_missing",
            message="A publisher inventory discovery model must be configured",
            retryable=False,
        )
    if request.settings.pagination_max_pages <= 0:
        raise AppError(
            code="publisher_inventory_pagination_limit_invalid",
            message="pagination_max_pages must be at least 1",
            retryable=False,
        )


def _validate_route_kind(route_kind: str) -> None:
    if str(route_kind or "").strip() not in _ROUTE_KINDS:
        raise AppError(
            code="publisher_inventory_route_kind_invalid",
            message="publisher inventory discovery returned an unsupported route kind",
            retryable=True,
            context={"route_kind": route_kind},
        )


def _validate_and_normalize_url(url: str) -> str:
    normalized = _normalize_absolute_url(url)
    return normalized


def _prepare_session_dir(*, root_dir: str, normalized_url: str) -> Path:
    root = Path(root_dir).expanduser().resolve()
    host = urlsplit(normalized_url).netloc.replace(":", "_") or "unknown_host"
    url_hash = sha1(normalized_url.encode("utf-8")).hexdigest()[:12]
    path = (root / host / url_hash).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _load_browser_use_runtime(normalized_url: str) -> Any:
    os.environ.setdefault("BROWSER_USE_SETUP_LOGGING", "false")
    vendored_root = (
        Path(__file__).resolve().parents[2] / "tools" / "browser-use"
    ).resolve()
    load_errors: list[tuple[str, Exception]] = []
    for import_mode, extra_path in (
        ("direct", None),
        ("vendored", vendored_root),
    ):
        if extra_path is not None:
            extra_path_str = str(extra_path)
            if extra_path_str not in sys.path:
                sys.path.insert(0, extra_path_str)
        try:
            return import_module("browser_use")
        except Exception as exc:
            load_errors.append((import_mode, exc))

    final_mode, final_error = load_errors[-1]
    missing_dependency = (
        final_error.name if isinstance(final_error, ModuleNotFoundError) else ""
    )
    raise AppError(
        code="browser_use_unavailable",
        message=(
            "The local browser_use runtime is not available in the active Python interpreter. "
            "Run publisher discovery from the project virtualenv or install the vendored browser-use dependencies."
        ),
        cause=final_error,
        retryable=False,
        context={
            "normalized_url": normalized_url,
            "current_python": sys.executable,
            "vendored_root": str(vendored_root),
            "attempted_import_modes": [mode for mode, _ in load_errors],
            "final_import_mode": final_mode,
            "missing_dependency": missing_dependency,
        },
    ) from final_error


def _kill_browser(browser: Any, ctx: RunContext) -> None:
    try:
        asyncio.run(browser.kill())
    except Exception:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="publisher_inventory_browser_kill_failed",
                module=logger.name,
                fields={},
            )
        )
