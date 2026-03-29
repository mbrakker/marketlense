from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from dataclasses import dataclass
from hashlib import sha1
from html.parser import HTMLParser
from importlib import import_module
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urljoin, urlsplit

import requests

from src.contracts.publisher_inventory import (
    PublisherInventoryPage,
    PublisherInventoryRawCandidate,
    PublisherInventoryServiceRequest,
    PublisherInventoryServiceResponse,
)
from src.contracts.run_context import RunContext
from src.utils.errors import AppError
from src.utils.logging import log_event
from src.utils.url_utils import normalize_url

logger = logging.getLogger("market_lense.publisher_inventory_service")

_ROUTE_KINDS = {"http_parse", "browser_render"}
_REPORT_KEYWORDS = (
    "report",
    "reports",
    "insight",
    "insights",
    "study",
    "research",
    "ebook",
    "whitepaper",
    "guide",
    "survey",
    "trend",
    "playbook",
    "forecast",
    "outlook",
    "benchmark",
)
_STRONG_REPORT_KEYWORDS = (
    "report",
    "reports",
    "study",
    "research",
    "ebook",
    "whitepaper",
    "guide",
    "survey",
    "playbook",
    "forecast",
    "outlook",
    "benchmark",
)
_WEAK_REPORT_KEYWORDS = (
    "insight",
    "insights",
    "trend",
)
_PAGINATION_LABELS = {
    "next",
    "next page",
    "older",
    "older posts",
    "more",
    "load more",
    ">",
    ">>",
    "»",
}
_NEGATIVE_PATH_MARKERS = (
    "/tag/",
    "/tags/",
    "/category/",
    "/categories/",
    "/author/",
    "/search",
    "/login",
    "/privacy",
    "/contact",
    "/about",
)
_SOCIAL_HOST_MARKERS = (
    "facebook.com",
    "linkedin.com",
    "twitter.com",
    "x.com",
    "instagram.com",
    "youtube.com",
    "tiktok.com",
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
    has_report_filter: bool
    has_apply_button: bool


@dataclass(frozen=True)
class _BrowserTraversalMetrics:
    cookies_dismissed: int
    report_route_clicks: int
    report_filter_applied: int
    tab_clicks: int
    load_more_clicks: int
    next_page_visits: int


class _InventoryHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.anchors: list[dict[str, str]] = []
        self.next_link_hrefs: list[str] = []
        self._current_anchor: dict[str, str] | None = None
        self._anchor_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key.lower(): str(value or "") for key, value in attrs}
        if tag.lower() == "link":
            rel = attr_map.get("rel", "").lower()
            href = attr_map.get("href", "").strip()
            if href and "next" in rel:
                self.next_link_hrefs.append(href)
        if tag.lower() != "a":
            return
        href = attr_map.get("href", "").strip()
        if not href:
            return
        self._current_anchor = {
            "href": href,
            "rel": attr_map.get("rel", ""),
            "aria_label": attr_map.get("aria-label", ""),
            "title_attr": attr_map.get("title", ""),
        }
        self._anchor_text = []

    def handle_data(self, data: str) -> None:
        if self._current_anchor is not None:
            self._anchor_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or self._current_anchor is None:
            return
        text = _normalize_text(" ".join(self._anchor_text))
        title = text or _normalize_text(self._current_anchor.get("aria_label", "")) or _normalize_text(
            self._current_anchor.get("title_attr", "")
        )
        self.anchors.append(
            {
                "href": self._current_anchor["href"],
                "rel": self._current_anchor.get("rel", ""),
                "text": title,
            }
        )
        self._current_anchor = None
        self._anchor_text = []


def discover_publisher_inventory(
    request: PublisherInventoryServiceRequest,
    ctx: RunContext,
) -> PublisherInventoryServiceResponse:
    normalized_url = _validate_and_normalize_url(request.insights_url)
    _validate_request(request, normalized_url)
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
            },
        )
    )
    if request.settings.force_browser:
        return _discover_with_browser(request, ctx, normalized_url, use_hint=bool(request.route_hint))
    hinted_route = str(request.route_kind_hint or "").strip()
    if hinted_route:
        _validate_route_kind(hinted_route)
        if hinted_route == "http_parse":
            return _discover_with_http(request, ctx, normalized_url, use_hint=True)
        return _discover_with_browser(request, ctx, normalized_url, use_hint=True)

    try:
        return _discover_with_http(request, ctx, normalized_url, use_hint=False)
    except AppError as exc:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="publisher_inventory_http_fallback",
                module=logger.name,
                fields={"normalized_url": normalized_url, "error": exc.message, "code": exc.code},
            )
        )
    return _discover_with_browser(request, ctx, normalized_url, use_hint=False)


def _discover_with_http(
    request: PublisherInventoryServiceRequest,
    ctx: RunContext,
    normalized_url: str,
    *,
    use_hint: bool,
) -> PublisherInventoryServiceResponse:
    headers = {"User-Agent": "MarketLensePublisherInventory/1.0"}
    current_url = normalized_url
    visited: set[str] = set()
    pages: list[PublisherInventoryPage] = []
    candidates: list[PublisherInventoryRawCandidate] = []
    page_number = 1
    while current_url and page_number <= request.settings.pagination_max_pages:
        if current_url in visited:
            break
        visited.add(current_url)
        logger.info(
            log_event(
                ctx,
                role="service",
                event="publisher_inventory_http_request",
                module=logger.name,
                fields={"page_url": current_url, "page_number": page_number, "headers": headers},
            )
        )
        try:
            response = requests.get(
                current_url,
                timeout=request.settings.http_timeout_seconds,
                headers=headers,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise AppError(
                code="publisher_inventory_http_failed",
                message="Failed to fetch publisher inventory page via HTTP",
                cause=exc,
                retryable=True,
                context={"page_url": current_url},
            ) from exc
        final_page_url = _validate_and_normalize_url(str(response.url or current_url))
        html = response.text or ""
        logger.info(
            log_event(
                ctx,
                role="service",
                event="publisher_inventory_http_response",
                module=logger.name,
                fields={
                    "page_url": current_url,
                    "final_page_url": final_page_url,
                    "status_code": response.status_code,
                    "html_length": len(html),
                },
            )
        )
        parser = _InventoryHtmlParser()
        parser.feed(html)
        pages.append(
            PublisherInventoryPage(
                schema_version="1.0",
                page_number=page_number,
                page_url=final_page_url,
            )
        )
        next_page_url = _resolve_next_page_url(
            current_page_url=final_page_url,
            page_number=page_number,
            anchors=parser.anchors,
            rel_next_hrefs=parser.next_link_hrefs,
        )
        page_candidates = _extract_candidates_from_html(
            anchors=parser.anchors,
            page_url=final_page_url,
            page_number=page_number,
            next_page_url=next_page_url,
        )
        candidates.extend(page_candidates)
        if not next_page_url:
            break
        current_url = next_page_url
        page_number += 1

    if not candidates:
        raise AppError(
            code="publisher_inventory_http_empty",
            message="Direct HTTP parsing found no valid report inventory items",
            retryable=True,
            context={"normalized_url": normalized_url},
        )

    response = PublisherInventoryServiceResponse(
        schema_version="1.0",
        source_url=request.insights_url,
        normalized_url=normalized_url,
        route_kind="http_parse",
        route_summary=(
            f"Fetched inventory HTML directly and traversed {len(pages)} page(s) via pagination links."
        ),
        final_page_url=pages[-1].page_url,
        used_route_hint=use_hint,
        pages=pages,
        candidates=candidates,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="publisher_inventory_http_complete",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "page_count": len(response.pages),
                "candidate_count": len(response.candidates),
                "used_route_hint": response.used_route_hint,
            },
        )
    )
    return response


def _discover_with_browser(
    request: PublisherInventoryServiceRequest,
    ctx: RunContext,
    normalized_url: str,
    *,
    use_hint: bool,
) -> PublisherInventoryServiceResponse:
    session_dir = _prepare_session_dir(
        root_dir=request.settings.output_dir,
        normalized_url=normalized_url,
    )
    browser_use = _load_browser_use_runtime(normalized_url)
    browser = browser_use.Browser(
        downloads_path=str(session_dir),
        headless=not request.settings.headed,
        auto_download_pdfs=False,
    )
    pages: list[PublisherInventoryPage] = []
    candidates: list[PublisherInventoryRawCandidate] = []
    final_page_url = normalized_url
    route_summary = ""
    try:
        pages, candidates, final_page_url, route_summary = asyncio.run(
            _run_browser_traversal(
                browser=browser,
                request=request,
                ctx=ctx,
                normalized_url=normalized_url,
            )
        )
    except Exception as exc:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="publisher_inventory_browser_failed",
                module=logger.name,
                fields={"normalized_url": normalized_url, "error": str(exc)},
            )
        )
        if isinstance(exc, AppError):
            raise
        raise AppError(
            code="publisher_inventory_browser_failed",
            message="Browser-render inventory discovery failed",
            cause=exc,
            retryable=True,
            context={"normalized_url": normalized_url},
        ) from exc
    logger.info(
        log_event(
            ctx,
            role="service",
            event="publisher_inventory_browser_response",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "browser_final_url": final_page_url,
                "page_count": len(pages),
                "candidate_count": len(candidates),
                "route_summary": route_summary,
            },
        )
    )
    if not pages or not candidates:
        raise AppError(
            code="publisher_inventory_browser_incomplete",
            message="Browser-render inventory discovery returned no usable pages or candidates",
            retryable=True,
            context={"normalized_url": normalized_url},
        )
    response = PublisherInventoryServiceResponse(
        schema_version="1.0",
        source_url=request.insights_url,
        normalized_url=normalized_url,
        route_kind="browser_render",
        route_summary=route_summary,
        final_page_url=str(final_page_url or normalized_url).strip(),
        used_route_hint=use_hint,
        pages=pages,
        candidates=candidates,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="publisher_inventory_browser_complete",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "page_count": len(response.pages),
                "candidate_count": len(response.candidates),
                "used_route_hint": response.used_route_hint,
                "route_kind": response.route_kind,
            },
        )
    )
    return response


async def _run_browser_traversal(
    *,
    browser: Any,
    request: PublisherInventoryServiceRequest,
    ctx: RunContext,
    normalized_url: str,
) -> tuple[list[PublisherInventoryPage], list[PublisherInventoryRawCandidate], str, str]:
    try:
        await browser.start()
        page = await browser.new_page(normalized_url)
        await _browser_wait_for_settle(page=page)
        metrics = _BrowserTraversalMetrics(
            cookies_dismissed=0,
            report_route_clicks=0,
            report_filter_applied=0,
            tab_clicks=0,
            load_more_clicks=0,
            next_page_visits=0,
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
            )
            await _browser_wait_for_settle(page=page)
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
                )
                await _browser_wait_for_settle(page=page)
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
            )
            await _browser_wait_for_settle(page=page)
            dismissed = await _dismiss_cookie_banner(page)
            if dismissed:
                metrics = _BrowserTraversalMetrics(
                    cookies_dismissed=metrics.cookies_dismissed + 1,
                    report_route_clicks=metrics.report_route_clicks,
                    report_filter_applied=metrics.report_filter_applied,
                    tab_clicks=metrics.tab_clicks,
                    load_more_clicks=metrics.load_more_clicks,
                    next_page_visits=metrics.next_page_visits,
                )
                await _browser_wait_for_settle(page=page)
            initial_state = await _extract_rendered_inventory_state(page)

        pages: list[PublisherInventoryPage] = []
        candidates: list[PublisherInventoryRawCandidate] = []
        page_number = 1
        if _should_traverse_tabs(normalized_url, initial_state):
            seen_tabs: set[str] = set()
            tab_labels = [label for label in initial_state.tab_labels if label]
            current_state = initial_state
            for tab_index, tab_label in enumerate(tab_labels):
                normalized_label = _normalize_text(tab_label).casefold()
                if normalized_label in seen_tabs:
                    continue
                if tab_index > 0:
                    clicked = await _click_tab(page, tab_label)
                    if not clicked:
                        raise AppError(
                            code="publisher_inventory_browser_tab_click_failed",
                            message="Browser-render inventory discovery could not switch tabbed report sections",
                            retryable=True,
                            context={"normalized_url": normalized_url, "tab_label": tab_label},
                        )
                    metrics = _BrowserTraversalMetrics(
                        cookies_dismissed=metrics.cookies_dismissed,
                        report_route_clicks=metrics.report_route_clicks,
                        report_filter_applied=metrics.report_filter_applied,
                        tab_clicks=metrics.tab_clicks + 1,
                        load_more_clicks=metrics.load_more_clicks,
                        next_page_visits=metrics.next_page_visits,
                    )
                    await _wait_for_tab_activation(page, tab_label)
                    current_state = await _extract_rendered_inventory_state(page)
                seen_tabs.add(normalized_label)
                page_number, metrics = await _collect_browser_inventory_pages(
                    page=page,
                    current_state=current_state,
                    starting_page_number=page_number,
                    request=request,
                    normalized_url=normalized_url,
                    pages=pages,
                    candidates=candidates,
                    metrics=metrics,
                    ctx=ctx,
                )
                current_state = await _extract_rendered_inventory_state(page)
        else:
            _page_number, metrics = await _collect_browser_inventory_pages(
                page=page,
                current_state=initial_state,
                starting_page_number=page_number,
                request=request,
                normalized_url=normalized_url,
                pages=pages,
                candidates=candidates,
                metrics=metrics,
                ctx=ctx,
            )
        final_page_url = _normalize_absolute_url(await page.get_url()) or normalized_url
        route_summary = _build_browser_route_summary(
            normalized_url=normalized_url,
            pages=pages,
            metrics=metrics,
            used_tabs=_should_traverse_tabs(normalized_url, initial_state),
        )
        return pages, candidates, final_page_url, route_summary
    finally:
        await browser.kill()


def _extract_candidates_from_html(
    *,
    anchors: list[dict[str, str]],
    page_url: str,
    page_number: int,
    next_page_url: str | None,
) -> list[PublisherInventoryRawCandidate]:
    candidates: list[PublisherInventoryRawCandidate] = []
    seen_urls: set[str] = set()
    for anchor in anchors:
        href = str(anchor.get("href", "")).strip()
        if not href:
            continue
        absolute_url = _normalize_absolute_url(urljoin(page_url, href))
        if not absolute_url or absolute_url in seen_urls:
            continue
        title = _normalize_text(anchor.get("text", ""))
        if not _looks_like_report_candidate(
            absolute_url=absolute_url,
            title=title,
            page_url=page_url,
            next_page_url=next_page_url,
        ):
            continue
        seen_urls.add(absolute_url)
        pdf_url = absolute_url if absolute_url.lower().endswith(".pdf") else None
        candidates.append(
            PublisherInventoryRawCandidate(
                schema_version="1.0",
                url=absolute_url,
                title=title or _fallback_title_from_url(absolute_url),
                source_page_url=page_url,
                discovered_on_page_number=page_number,
                pdf_url=pdf_url,
                published_at_text=None,
            )
    )
    return candidates


async def _collect_browser_inventory_pages(
    *,
    page: Any,
    current_state: _RenderedInventoryState,
    starting_page_number: int,
    request: PublisherInventoryServiceRequest,
    normalized_url: str,
    pages: list[PublisherInventoryPage],
    candidates: list[PublisherInventoryRawCandidate],
    metrics: _BrowserTraversalMetrics,
    ctx: RunContext,
) -> tuple[int, _BrowserTraversalMetrics]:
    page_number = starting_page_number
    visited_navigation_urls: set[str] = set()
    state = current_state
    while True:
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
        )
        pages.append(
            PublisherInventoryPage(
                schema_version="1.0",
                page_number=page_number,
                page_url=state.page_url,
            )
        )
        candidates.extend(page_candidates)
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
                    "next_page_url": next_page_url or "",
                    "active_tab_label": state.active_tab_label or "",
                },
            )
        )
        if page_number >= request.settings.pagination_max_pages:
            if state.load_more_labels or next_page_url:
                raise AppError(
                    code="publisher_inventory_browser_pagination_limit",
                    message="Browser-render inventory discovery reached the pagination limit before exhausting the inventory",
                    retryable=True,
                    context={
                        "normalized_url": normalized_url,
                        "page_number": page_number,
                        "page_url": state.page_url,
                    },
                )
            break
        if state.load_more_labels:
            clicked = await _click_load_more(page, state.load_more_labels)
            if not clicked:
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
            metrics = _BrowserTraversalMetrics(
                cookies_dismissed=metrics.cookies_dismissed,
                report_route_clicks=metrics.report_route_clicks,
                report_filter_applied=metrics.report_filter_applied,
                tab_clicks=metrics.tab_clicks,
                load_more_clicks=metrics.load_more_clicks + 1,
                next_page_visits=metrics.next_page_visits,
            )
            await _wait_for_inventory_growth(page, current_candidate_count=len(page_candidates))
            page_number += 1
            state = await _extract_rendered_inventory_state(page)
            continue
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
            )
            await _browser_wait_for_settle()
            page_number += 1
            state = await _extract_rendered_inventory_state(page)
            continue
        break
    return page_number + 1, metrics


async def _extract_rendered_inventory_state(page: Any) -> _RenderedInventoryState:
    payload = json.loads(await page.evaluate(_browser_inventory_state_script()))
    page_url = _normalize_absolute_url(str(payload.get("page_url") or "")) or _normalize_absolute_url(
        await page.get_url()
    )
    anchors = [
        {
            "href": _normalize_text(item.get("href", "")),
            "text": _normalize_text(
                item.get("text", "")
                or item.get("img_alt", "")
                or item.get("aria_label", "")
                or item.get("title_attr", "")
            ),
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
    active_tab_label = _normalize_text(str(payload.get("active_tab_label") or "")) or None
    report_link_url = _normalize_absolute_url(str(payload.get("report_link_url") or "")) or None
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
        has_report_filter=bool(payload.get("has_report_filter")),
        has_apply_button=bool(payload.get("has_apply_button")),
    )


async def _dismiss_cookie_banner(page: Any) -> bool:
    clicked = await page.evaluate(_browser_click_named_control_script(), [
        "accept all cookies",
        "accept all",
        "accept",
        "agree",
        "ok",
        "close",
        "continue",
    ])
    return str(clicked).strip().lower() == "true"


async def _click_tab(page: Any, tab_label: str) -> bool:
    clicked = await page.evaluate(_browser_click_tab_script(), tab_label)
    return str(clicked).strip().lower() == "true"


async def _click_load_more(page: Any, labels: list[str]) -> bool:
    clicked = await page.evaluate(_browser_click_named_control_script(), labels)
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


async def _wait_for_inventory_growth(page: Any, *, current_candidate_count: int) -> None:
    for _ in range(20):
        await _browser_wait_for_settle(page=page, delay_seconds=0.35)
        state = await _extract_rendered_inventory_state(page)
        next_page_url = _resolve_next_page_url(
            current_page_url=state.page_url,
            page_number=1,
            anchors=state.anchors,
            rel_next_hrefs=[],
        )
        if len(_extract_candidates_from_html(
            anchors=state.anchors,
            page_url=state.page_url,
            page_number=1,
            next_page_url=next_page_url,
        )) > current_candidate_count:
            return
    raise AppError(
        code="publisher_inventory_browser_growth_timeout",
        message="Browser-render inventory discovery did not observe new inventory items after interaction",
        retryable=True,
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


def _should_follow_report_listing(normalized_url: str, state: _RenderedInventoryState) -> bool:
    host = str(urlsplit(normalized_url).hostname or "").casefold()
    if "gfk-media-measurement.com" not in host:
        return False
    path = str(urlsplit(normalized_url).path or "").casefold()
    if "/insights/report/" in path:
        return False
    if state.has_report_filter and state.has_apply_button:
        return False
    return bool(state.report_link_url)


def _should_apply_report_filter(normalized_url: str, state: _RenderedInventoryState) -> bool:
    host = str(urlsplit(normalized_url).hostname or "").casefold()
    return "gfk-media-measurement.com" in host and state.has_report_filter and state.has_apply_button


def _should_traverse_tabs(normalized_url: str, state: _RenderedInventoryState) -> bool:
    host = str(urlsplit(normalized_url).hostname or "").casefold()
    return "salesforce.com" in host and len(state.tab_labels) > 1


def _build_browser_route_summary(
    *,
    normalized_url: str,
    pages: list[PublisherInventoryPage],
    metrics: _BrowserTraversalMetrics,
    used_tabs: bool,
) -> str:
    host = str(urlsplit(normalized_url).hostname or "").strip().lower()
    steps = [f"Rendered {host} in browser and extracted {len(pages)} inventory state(s)."]
    if metrics.cookies_dismissed:
        steps.append(f"Dismissed cookie banners {metrics.cookies_dismissed} time(s).")
    if metrics.report_route_clicks:
        steps.append("Followed the report listing route before extraction.")
    if metrics.report_filter_applied:
        steps.append("Applied the report format filter.")
    if used_tabs and metrics.tab_clicks:
        steps.append(f"Traversed {metrics.tab_clicks + 1} tabbed publisher section(s).")
    if metrics.load_more_clicks:
        steps.append(f"Expanded load-more pagination {metrics.load_more_clicks} time(s).")
    if metrics.next_page_visits:
        steps.append(f"Visited {metrics.next_page_visits} additional pagination URL(s).")
    return " ".join(steps)


def _browser_inventory_state_script() -> str:
    return """() => {
        const normalize = (value) => (value || '').replace(/\\s+/g, ' ').trim();
        const isVisible = (element) => {
            if (!element) return false;
            const style = window.getComputedStyle(element);
            const rect = element.getBoundingClientRect();
            return style && style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0;
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
                visible: isVisible(anchor),
            };
        }).filter((item) => item.href && item.visible);
        const collectLabels = (elements) => elements
            .filter((element) => isVisible(element))
            .map((element) => normalize(element.textContent || element.getAttribute('aria-label') || element.value || ''))
            .filter((label) => label);
        const loadMoreLabels = collectLabels(
            Array.from(document.querySelectorAll('button, a[role="button"], a.button, input[type="button"], input[type="submit"]'))
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
                return href.includes('/insights/report/') && /report/i.test(label || href);
            });
        const reportFilter = Array.from(document.querySelectorAll('label, button, div, span')).some((element) => {
            const label = normalize(element.textContent || element.getAttribute('aria-label') || '');
            return label === 'Report' || label === 'Reports';
        });
        const applyButton = Array.from(document.querySelectorAll('button, input[type="submit"], input[type="button"]'))
            .some((element) => /^apply$/i.test(normalize(element.textContent || element.value || element.getAttribute('aria-label') || '')) && isVisible(element));
        return {
            page_url: window.location.href,
            page_title: document.title,
            anchors,
            load_more_labels: loadMoreLabels,
            tab_labels: tabLabels,
            active_tab_label: normalize(activeTab ? activeTab.textContent || activeTab.getAttribute('aria-label') || '' : ''),
            report_link_url: reportLink ? normalize(reportLink.href || reportLink.getAttribute('href') || '') : '',
            has_report_filter: reportFilter,
            has_apply_button: applyButton,
        };
    }"""


def _browser_click_named_control_script() -> str:
    return """(labels) => {
        const normalize = (value) => (value || '').replace(/\\s+/g, ' ').trim().toLowerCase();
        const wanted = Array.isArray(labels) ? labels.map((item) => normalize(item)) : [];
        const isVisible = (element) => {
            if (!element) return false;
            const style = window.getComputedStyle(element);
            const rect = element.getBoundingClientRect();
            return style && style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0;
        };
        const elements = Array.from(document.querySelectorAll('button, a[role="button"], a.button, input[type="button"], input[type="submit"]'));
        for (const element of elements) {
            const label = normalize(element.textContent || element.getAttribute('aria-label') || element.value || '');
            if (!label || !isVisible(element)) continue;
            if (wanted.some((candidate) => label === candidate || label.includes(candidate))) {
                element.click();
                return true;
            }
        }
        return false;
    }"""


def _browser_click_tab_script() -> str:
    return """(tabLabel) => {
        const normalize = (value) => (value || '').replace(/\\s+/g, ' ').trim().toLowerCase();
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
        const normalize = (value) => (value || '').replace(/\\s+/g, ' ').trim().toLowerCase();
        const isVisible = (element) => {
            if (!element) return false;
            const style = window.getComputedStyle(element);
            const rect = element.getBoundingClientRect();
            return style && style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0;
        };
        const candidates = Array.from(document.querySelectorAll('input[type="checkbox"], input[type="radio"], [role="checkbox"]'));
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
        if (!toggled) return false;
        const applyButtons = Array.from(document.querySelectorAll('button, input[type="submit"], input[type="button"]'));
        for (const button of applyButtons) {
            const label = normalize(button.textContent || button.value || button.getAttribute('aria-label') || '');
            if (label === 'apply' && isVisible(button)) {
                button.click();
                return true;
            }
        }
        return false;
    }"""
    logger.info(
        log_event(
            ctx,
            role="service",
            event="publisher_inventory_browser_http_supplement_request",
            module=logger.name,
            fields={
                "page_url": page.page_url,
                "page_number": page.page_number,
                "headers": headers,
            },
        )
    )
    try:
        response = requests.get(
            page.page_url,
            timeout=request.settings.http_timeout_seconds,
            headers=headers,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="publisher_inventory_browser_http_supplement_failed",
                module=logger.name,
                fields={
                    "page_url": page.page_url,
                    "page_number": page.page_number,
                    "error": str(exc),
                },
            )
        )
        return []

    final_page_url = _validate_and_normalize_url(str(response.url or page.page_url))
    html = response.text or ""
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
            },
        )
    )
    parser = _InventoryHtmlParser()
    parser.feed(html)
    candidates = _extract_candidates_from_html(
        anchors=parser.anchors,
        page_url=final_page_url,
        page_number=page.page_number,
        next_page_url=None,
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


def _resolve_next_page_url(
    *,
    current_page_url: str,
    page_number: int,
    anchors: list[dict[str, str]],
    rel_next_hrefs: list[str],
) -> str | None:
    for href in rel_next_hrefs:
        normalized = _normalize_absolute_url(urljoin(current_page_url, href))
        if normalized and normalized != current_page_url:
            return normalized
    numeric_candidates: list[tuple[int, str]] = []
    for anchor in anchors:
        href = str(anchor.get("href", "")).strip()
        title = _normalize_text(anchor.get("text", ""))
        rel = str(anchor.get("rel", "")).lower()
        normalized = _normalize_absolute_url(urljoin(current_page_url, href))
        if not normalized or normalized == current_page_url:
            continue
        if "next" in rel or title.casefold() in _PAGINATION_LABELS:
            return normalized
        page_value = _page_query_value(normalized)
        if page_value is not None and page_value > page_number:
            numeric_candidates.append((page_value, normalized))
    if not numeric_candidates:
        return None
    numeric_candidates.sort(key=lambda item: item[0])
    return numeric_candidates[0][1]


def _looks_like_report_candidate(
    *,
    absolute_url: str,
    title: str,
    page_url: str,
    next_page_url: str | None,
) -> bool:
    if absolute_url == page_url or absolute_url == next_page_url:
        return False
    if absolute_url.startswith(("mailto:", "tel:", "javascript:")):
        return False
    lowered_url = absolute_url.casefold()
    candidate_host = str(urlsplit(absolute_url).hostname or "").strip().casefold()
    page_host = str(urlsplit(page_url).hostname or "").strip().casefold()
    if any(marker in candidate_host for marker in _SOCIAL_HOST_MARKERS):
        return False
    if any(marker in lowered_url for marker in _NEGATIVE_PATH_MARKERS):
        return False
    lowered_title = title.casefold()
    if lowered_title in _PAGINATION_LABELS:
        return False
    if lowered_title in {"report", "reports"}:
        return False
    if lowered_title.startswith("view all "):
        return False
    if _is_generic_icon_label(lowered_title):
        return False
    if _is_section_landing_page(absolute_url):
        return False
    if _is_reports_hub_path(absolute_url):
        return False
    if _is_inventory_type_archive_path(absolute_url):
        return False
    if _is_inventory_topic_hub_path(absolute_url):
        return False
    if _is_root_or_locale_home(absolute_url):
        return False
    if absolute_url.lower().endswith(".pdf"):
        return True
    if not _is_same_inventory_domain(candidate_host, page_host):
        return False
    if _is_generic_insights_hub_title(lowered_title):
        return False
    if any(keyword in lowered_url for keyword in _STRONG_REPORT_KEYWORDS):
        return True
    if any(keyword in lowered_title for keyword in _STRONG_REPORT_KEYWORDS):
        return True
    if _is_inventory_article_path(absolute_url):
        return True
    if any(keyword in lowered_url for keyword in _WEAK_REPORT_KEYWORDS) and _is_inventory_article_path(absolute_url):
        return True
    if any(keyword in lowered_title for keyword in _WEAK_REPORT_KEYWORDS) and _is_inventory_article_path(absolute_url):
        return True
    if (
        title
        and len(title) >= 16
        and any(char.isdigit() for char in title)
        and _looks_like_human_report_title(title)
    ):
        return True
    return False


def _is_same_inventory_domain(candidate_host: str, page_host: str) -> bool:
    if not candidate_host or not page_host:
        return False
    candidate_apex = _apex_domain(candidate_host)
    page_apex = _apex_domain(page_host)
    return bool(candidate_apex and page_apex and candidate_apex == page_apex)


def _apex_domain(host: str) -> str:
    parts = [part for part in str(host or "").strip().casefold().split(".") if part]
    if len(parts) < 2:
        return ""
    return ".".join(parts[-2:])


def _is_section_landing_page(url: str) -> bool:
    path = str(urlsplit(url).path or "").strip().casefold().rstrip("/")
    if not path:
        return False
    segments = [segment for segment in path.split("/") if segment]
    if segments == ["insights"]:
        return True
    if len(segments) == 2 and segments[1] == "insights":
        return True
    return False


def _is_inventory_article_path(url: str) -> bool:
    path = str(urlsplit(url).path or "").strip().casefold().rstrip("/")
    if not path.startswith("/insights/"):
        return False
    return not _is_section_landing_page(url)


def _is_inventory_type_archive_path(url: str) -> bool:
    segments = [
        segment for segment in str(urlsplit(url).path or "").strip().casefold().rstrip("/").split("/") if segment
    ]
    if len(segments) >= 3 and segments[0] == "insights" and segments[1] == "type":
        return True
    if len(segments) >= 4 and segments[1] == "insights" and segments[2] == "type":
        return True
    return False


def _is_inventory_topic_hub_path(url: str) -> bool:
    path = str(urlsplit(url).path or "").strip().casefold().rstrip("/")
    return "/insights/topic/" in path


def _is_reports_hub_path(url: str) -> bool:
    segments = [
        segment for segment in str(urlsplit(url).path or "").strip().casefold().rstrip("/").split("/") if segment
    ]
    return len(segments) >= 2 and "insights" in segments and segments[-1] == "reports"


def _is_root_or_locale_home(url: str) -> bool:
    segments = [
        segment for segment in str(urlsplit(url).path or "").strip().casefold().rstrip("/").split("/") if segment
    ]
    if not segments:
        return True
    return (
        len(segments) <= 2
        and "insights" not in segments
        and "report" not in segments
        and "reports" not in segments
    )


def _is_generic_icon_label(lowered_title: str) -> bool:
    token = str(lowered_title or "").strip()
    return (
        token.startswith("02_elements/")
        or token.startswith(".st")
        or token in {"close", "arrowright", "arrowleft"}
    )


def _looks_like_human_report_title(title: str) -> bool:
    token = str(title or "").strip()
    if not token:
        return False
    if any(char in token for char in {"{", "}", "<", ">", "\\", "/", "_"}):
        return False
    alpha_count = sum(1 for char in token if char.isalpha())
    return alpha_count >= 3


def _is_generic_insights_hub_title(lowered_title: str) -> bool:
    if not lowered_title or not lowered_title.endswith(" insights"):
        return False
    stem = lowered_title[: -len(" insights")].strip()
    if not stem:
        return False
    return all(char.isalpha() or char in {" ", "&", "-"} for char in stem)


def _page_query_value(url: str) -> int | None:
    query = parse_qs(urlsplit(url).query)
    for key in ("page", "paged", "p"):
        values = query.get(key)
        if not values:
            continue
        try:
            return int(str(values[0]).strip())
        except (TypeError, ValueError):
            return None
    return None


def _normalize_text(value: str) -> str:
    return " ".join(str(value or "").split()).strip()


def _fallback_title_from_url(url: str) -> str:
    path = urlsplit(url).path.rsplit("/", 1)[-1]
    token = path.rsplit(".", 1)[0].replace("-", " ").replace("_", " ").strip()
    return _normalize_text(token) or url


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


def _normalize_absolute_url(url: str) -> str:
    normalized_url = normalize_url(url)
    parts = urlsplit(normalized_url)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        return ""
    return normalized_url


def _prepare_session_dir(*, root_dir: str, normalized_url: str) -> Path:
    root = Path(root_dir).expanduser().resolve()
    host = urlsplit(normalized_url).netloc.replace(":", "_") or "unknown_host"
    url_hash = sha1(normalized_url.encode("utf-8")).hexdigest()[:12]
    path = (root / host / url_hash).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _load_browser_use_runtime(normalized_url: str) -> Any:
    os.environ.setdefault("BROWSER_USE_SETUP_LOGGING", "false")
    vendored_root = (Path(__file__).resolve().parents[2] / "tools" / "browser-use").resolve()
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
        final_error.name
        if isinstance(final_error, ModuleNotFoundError)
        else ""
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
