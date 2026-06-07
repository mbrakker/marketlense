from __future__ import annotations

"""Traversal operations for publisher-inventory browser traversal."""

import asyncio
from typing import Any
from src.contracts.publisher_inventory import (
    PublisherInventoryPage,
    PublisherInventoryRawCandidate,
    PublisherInventoryRouteTrace,
    PublisherInventoryServiceRequest,
)
from src.contracts.run_context import RunContext
from src.services._publisher_inventory_service.browser_traversal_state import (
    _RenderedInventoryState,
    _build_browser_route_trace,
    _increment_browser_traversal_metrics,
    _new_browser_traversal_metrics,
)
from src.services._publisher_inventory_service.discovery_activity import (
    _build_browser_route_summary,
    _extract_candidates_from_html,
    _is_archive_surface,
    _normalize_absolute_url,
    _normalize_text,
    _select_tab_labels_for_traversal,
    _should_apply_report_filter,
    _should_expand_archive_library,
    _should_follow_report_listing,
)
from src.utils.errors import AppError
from src.services._publisher_inventory_service._browser_flow.interactions import (
    _apply_report_filter,
    _browser_wait_for_settle,
    _click_archive_expander,
    _click_tab,
    _dismiss_cookie_banner,
    _extract_rendered_inventory_state,
    _prime_browser_inventory_surface,
    _record_browser_scroll_probe_metrics,
    _wait_for_inventory_transition,
    _wait_for_tab_activation,
)
from src.services._publisher_inventory_service._browser_flow.collection import (
    _close_unexpected_blank_pages,
    _collect_browser_inventory_pages,
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
