from __future__ import annotations

"""Collection operations for publisher-inventory browser traversal."""

import logging
from typing import Any

from src.contracts.publisher_inventory import (
    PublisherInventoryPage,
    PublisherInventoryRawCandidate,
    PublisherInventoryServiceRequest,
)
from src.contracts.run_context import RunContext
from src.services._publisher_inventory_service._browser_flow.interactions import (
    _browser_wait_for_settle,
    _click_load_more,
    _click_pagination_next,
    _extract_rendered_inventory_state,
    _prime_browser_inventory_surface,
    _record_browser_scroll_probe_metrics,
    _reset_empty_results_filters,
    _wait_for_inventory_growth,
    _wait_for_inventory_growth_probe,
    _wait_for_inventory_transition,
)
from src.services._publisher_inventory_service.browser_scripts import (
    _browser_rendered_html_script,
)
from src.services._publisher_inventory_service.browser_traversal_state import (
    _BrowserTraversalMetrics,
    _increment_browser_traversal_metrics,
    _RenderedInventoryState,
)
from src.services._publisher_inventory_service.discovery_activity import (
    _candidate_url_signature,
    _extract_candidates_from_html,
    _extract_component_link_anchors,
    _is_archive_surface,
    _is_exhausted_inert_load_more,
    _is_terminal_results_page,
    _needs_additional_hydration,
    _normalize_absolute_url,
    _requires_archive_surface_recovery,
    _requires_origin_host_recovery,
    _resolve_next_page_url,
)
from src.services._publisher_inventory_service.fetch_service import (
    _InventoryHtmlParser,
)
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.publisher_inventory_service")


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
            await _browser_wait_for_settle(page=page)
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
