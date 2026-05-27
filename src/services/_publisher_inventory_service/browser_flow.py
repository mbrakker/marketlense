from __future__ import annotations

"""Browser traversal helpers for publisher-inventory discovery.

This module owns deterministic browser-page traversal, rendered-state parsing,
interaction waits, and HTTP supplement recovery used by the workflow coordinator.
It does not select discovery routes or define the public service boundary.
"""

import asyncio
import json
import logging
from typing import Any

import requests

from src.contracts.http_acquisition import (
    HttpAcquisitionRequest,
    HttpAcquisitionResponsePolicy,
)
from src.contracts.publisher_inventory import (
    PublisherInventoryPage,
    PublisherInventoryRawCandidate,
    PublisherInventoryRouteTrace,
    PublisherInventoryServiceRequest,
)
from src.contracts.run_context import RunContext
from src.services._http_acquisition import execute_http_acquisition
from src.services._publisher_inventory_service.browser_scripts import (
    _browser_apply_report_filter_script,
    _browser_click_archive_expander_script,
    _browser_click_cookie_banner_script,
    _browser_click_named_control_script,
    _browser_click_pagination_next_script,
    _browser_click_tab_script,
    _browser_inventory_growth_probe_script,
    _browser_inventory_settle_probe_script,
    _browser_inventory_state_script,
    _browser_named_control_selector,
    _browser_nested_scroll_probe_script,
    _browser_rendered_html_script,
    _browser_scroll_to_ratio_script,
)
from src.services._publisher_inventory_service.browser_traversal_state import (
    _BrowserScrollProbeResult,
    _BrowserTraversalMetrics,
    _RenderedInventoryState,
    _build_browser_route_trace,
    _browser_scroll_probe_result_from_payload,
    _increment_browser_traversal_metrics,
    _new_browser_traversal_metrics,
    _rendered_inventory_state_from_payload,
)
from src.services._publisher_inventory_service.discovery_activity import (
    _build_browser_route_summary,
    _candidate_url_signature,
    _extract_component_link_anchors,
    _extract_candidates_from_html,
    _is_archive_surface,
    _is_exhausted_inert_load_more,
    _is_terminal_results_page,
    _needs_additional_hydration,
    _normalize_absolute_url,
    _normalize_absolute_url as _validate_and_normalize_url,
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
from src.services._publisher_inventory_service.fetch_service import (
    HTTP_BROWSER_HEADERS,
    _InventoryHtmlParser,
)
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.publisher_inventory_service")


_HTTP_SUPPLEMENT_HTML_MAX_BYTES = 2 * 1024 * 1024


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
        metrics = _new_browser_traversal_metrics()
        scroll_probe = await _prime_browser_inventory_surface(
            page, ctx=ctx, normalized_url=normalized_url
        )
        metrics = _record_browser_scroll_probe_metrics(metrics, scroll_probe)
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
        dismissed = await _dismiss_cookie_banner(page)
        if dismissed:
            metrics = _increment_browser_traversal_metrics(
                metrics,
                cookies_dismissed=1,
            )
            await _browser_wait_for_settle(page=page)
            await _close_unexpected_blank_pages(
                browser=browser,
                active_page=page,
                ctx=ctx,
                reason="cookie_banner",
            )
        scroll_probe = await _prime_browser_inventory_surface(
            page, ctx=ctx, normalized_url=normalized_url
        )
        metrics = _record_browser_scroll_probe_metrics(metrics, scroll_probe)
        initial_state = await _extract_rendered_inventory_state(page)
        if _should_apply_report_filter(normalized_url, initial_state):
            applied = await _apply_report_filter(page)
            if applied:
                metrics = _increment_browser_traversal_metrics(
                    metrics,
                    report_filter_applied=1,
                )
                await _browser_wait_for_settle(page=page)
                await _close_unexpected_blank_pages(
                    browser=browser,
                    active_page=page,
                    ctx=ctx,
                    reason="report_filter",
                )
                scroll_probe = await _prime_browser_inventory_surface(
                    page, ctx=ctx, normalized_url=normalized_url
                )
                metrics = _record_browser_scroll_probe_metrics(metrics, scroll_probe)
                initial_state = await _extract_rendered_inventory_state(page)
        if _should_follow_report_listing(normalized_url, initial_state):
            await page.goto(initial_state.report_link_url or normalized_url)
            metrics = _increment_browser_traversal_metrics(
                metrics,
                report_route_clicks=1,
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
                metrics = _increment_browser_traversal_metrics(
                    metrics,
                    cookies_dismissed=1,
                )
                await _browser_wait_for_settle(page=page)
                await _close_unexpected_blank_pages(
                    browser=browser,
                    active_page=page,
                    ctx=ctx,
                    reason="report_route_cookie_banner",
                )
            scroll_probe = await _prime_browser_inventory_surface(
                page, ctx=ctx, normalized_url=normalized_url
            )
            metrics = _record_browser_scroll_probe_metrics(metrics, scroll_probe)
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
                metrics = _increment_browser_traversal_metrics(
                    metrics,
                    archive_expansion_clicks=1,
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
                scroll_probe = await _prime_browser_inventory_surface(
                    page, ctx=ctx, normalized_url=normalized_url
                )
                metrics = _record_browser_scroll_probe_metrics(metrics, scroll_probe)
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
                    metrics = _increment_browser_traversal_metrics(
                        metrics,
                        tab_clicks=1,
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
        scroll_probe = await _prime_browser_inventory_surface(
            page, ctx=ctx, normalized_url=normalized_url
        )
        metrics = _record_browser_scroll_probe_metrics(metrics, scroll_probe)
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
            scroll_probe = await _prime_browser_inventory_surface(
                page, ctx=ctx, normalized_url=normalized_url
            )
            metrics = _record_browser_scroll_probe_metrics(metrics, scroll_probe)
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
            metrics = _increment_browser_traversal_metrics(
                metrics,
                next_page_visits=1,
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
            metrics = _increment_browser_traversal_metrics(
                metrics,
                button_pagination_clicks=1,
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
            metrics = _increment_browser_traversal_metrics(
                metrics,
                load_more_clicks=1,
            )
            page_number += 1
            state = await _extract_rendered_inventory_state(page)
            continue
        break
    return page_number + 1, metrics, bounded_by_pagination_limit


async def _extract_rendered_inventory_state(page: Any) -> _RenderedInventoryState:
    payload = json.loads(await page.evaluate(_browser_inventory_state_script()))
    return _rendered_inventory_state_from_payload(
        payload,
        page_url_fallback=str(await page.get_url() or ""),
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
                await page.evaluate(_browser_inventory_growth_probe_script())
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


async def _prime_browser_inventory_surface(
    page: Any,
    *,
    ctx: RunContext | None = None,
    normalized_url: str = "",
) -> _BrowserScrollProbeResult:
    for ratio in (0.0, 0.35, 0.7, 0.95):
        await page.evaluate(_browser_scroll_to_ratio_script(), ratio)
        await _browser_wait_for_settle(page=page, delay_seconds=0.35)
    try:
        payload = json.loads(await page.evaluate(_browser_nested_scroll_probe_script()))
    except Exception as exc:
        if ctx is not None:
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="publisher_inventory_browser_scroll_probe_failed",
                    module=logger.name,
                    fields={
                        "normalized_url": normalized_url,
                        "error": str(exc),
                    },
                )
            )
        return _BrowserScrollProbeResult(
            schema_version="1.0",
            scroll_surface="document",
            best_surface_label="document",
            probed_surface_count=0,
            consumed_surface_count=0,
            candidate_growth=False,
            virtualized_list_detected=False,
            anchor_count_before=0,
            anchor_count_after=0,
        )
    result = _browser_scroll_probe_result_from_payload(payload)
    if result.consumed_surface_count > 0:
        await _browser_wait_for_settle(page=page, delay_seconds=0.35)
    if ctx is not None and (
        result.probed_surface_count > 0
        or result.consumed_surface_count > 0
        or result.virtualized_list_detected
    ):
        logger.info(
            log_event(
                ctx,
                role="service",
                event="publisher_inventory_browser_scroll_probe",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "scroll_surface": result.scroll_surface,
                    "best_surface_label": result.best_surface_label,
                    "probed_surface_count": result.probed_surface_count,
                    "consumed_surface_count": result.consumed_surface_count,
                    "candidate_growth": result.candidate_growth,
                    "virtualized_list_detected": result.virtualized_list_detected,
                    "anchor_count_before": result.anchor_count_before,
                    "anchor_count_after": result.anchor_count_after,
                },
            )
        )
    return result


def _record_browser_scroll_probe_metrics(
    metrics: _BrowserTraversalMetrics,
    result: _BrowserScrollProbeResult,
) -> _BrowserTraversalMetrics:
    if (
        result.scroll_surface == "document"
        and not result.candidate_growth
        and not result.virtualized_list_detected
    ):
        return metrics
    return _increment_browser_traversal_metrics(
        metrics,
        nested_scroll_probes=1 if result.consumed_surface_count > 0 else 0,
        nested_scroll_candidate_growth=1 if result.candidate_growth else 0,
        virtualized_list_detected=1 if result.virtualized_list_detected else 0,
        scroll_surface=result.scroll_surface,
    )


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
                await page.evaluate(_browser_inventory_settle_probe_script())
            )
        except Exception:
            continue
        ready_state = str(payload.get("readyState") or "").strip().lower()
        title = str(payload.get("title") or "").strip()
        anchor_count = int(payload.get("anchorCount") or 0)
        if ready_state == "complete" and (title or anchor_count > 0):
            return


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


__all__ = [name for name in globals() if not name.startswith("__")]
