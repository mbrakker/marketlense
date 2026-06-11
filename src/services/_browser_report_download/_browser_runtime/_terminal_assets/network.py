from __future__ import annotations
import json
import logging
import re
from typing import Any
from src.contracts.browser_download import (
    BrowserDownloadNetworkEvent,
)
from src.contracts.run_context import RunContext
from src.services._browser_report_download.cdp import (
    collect_terminal_network_entries_via_cdp,
)
from src.services._browser_report_download.helpers import (
    browser_helper_js,
)

logger = logging.getLogger("market_lense.browser_report_download_service")


def _collect_network_resource_urls(
    *,
    page: Any,
    final_page_html: str,
    network_events: list[BrowserDownloadNetworkEvent],
    ctx: RunContext,
    normalized_url: str,
) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()

    def add(raw_url: Any) -> None:
        token = str(raw_url or "").strip()
        if not _looks_like_documentish_url(token):
            return
        marker = token.casefold()
        if marker in seen:
            return
        seen.add(marker)
        normalized.append(token)

    if page is not None:
        for raw_url in _collect_page_resource_urls(
            page,
            ctx=ctx,
            normalized_url=normalized_url,
        ):
            add(raw_url)
        for raw_url in _collect_dom_candidate_urls(
            page,
            ctx=ctx,
            normalized_url=normalized_url,
        ):
            add(raw_url)
    for event in network_events:
        add(event.url)
    for raw_url in _extract_documentish_urls_from_html(final_page_html):
        add(raw_url)
    return normalized


def _collect_network_events(
    *,
    browser: Any,
    page: Any,
    route_family: str,
    ctx: RunContext,
    normalized_url: str,
) -> list[BrowserDownloadNetworkEvent]:
    cdp_events = _collect_network_events_via_cdp(
        browser=browser,
        route_family=route_family,
        ctx=ctx,
        normalized_url=normalized_url,
    )
    if page is None:
        return cdp_events
    js_result = browser_helper_js(
        page=page,
        expression="""
                return (() => {
                  const build = (entry, initiatorFallback = 'other') => ({
                    url: String(entry?.name || '').trim(),
                    initiator_type: String(entry?.initiatorType || initiatorFallback || 'other').trim(),
                  });
                  const navigationEntries = (globalThis.performance?.getEntriesByType?.('navigation') || [])
                    .map((entry) => build(entry, 'navigation'));
                  const resourceEntries = (globalThis.performance?.getEntriesByType?.('resource') || [])
                    .map((entry) => build(entry, 'other'));
                  return [...navigationEntries, ...resourceEntries];
                })();
                """,
        ctx=ctx,
        normalized_url=normalized_url,
    )
    if js_result.status != "ok":
        return cdp_events
    raw_events = js_result.result
    raw_events = _coerce_evaluate_list(raw_events)
    page_events = _network_events_from_raw_events(raw_events)
    if not cdp_events:
        return page_events
    return _merge_network_events(cdp_events, page_events)


def _collect_network_events_via_cdp(
    *,
    browser: Any,
    route_family: str,
    ctx: RunContext,
    normalized_url: str,
) -> list[BrowserDownloadNetworkEvent]:
    if str(route_family or "").strip() not in {
        "browser_email_form",
        "browser_pdf_click",
        "browser_tracker_redirect",
        "browser_onsite_report",
    }:
        return []
    raw_events = collect_terminal_network_entries_via_cdp(
        browser=browser,
        ctx=ctx,
        normalized_url=normalized_url,
        required=False,
    )
    return _network_events_from_raw_events(raw_events)


def _network_events_from_raw_events(
    raw_events: list[Any],
) -> list[BrowserDownloadNetworkEvent]:
    events: list[BrowserDownloadNetworkEvent] = []
    seen: set[tuple[str, str]] = set()
    for raw_event in raw_events:
        if isinstance(raw_event, dict):
            url = str(raw_event.get("url") or raw_event.get("name") or "").strip()
            initiator_type = (
                str(
                    raw_event.get("initiator_type")
                    or raw_event.get("initiatorType")
                    or "other"
                ).strip()
                or "other"
            )
        else:
            url = str(raw_event or "").strip()
            initiator_type = "other"
        if not url or not url.casefold().startswith("http"):
            continue
        key = (url.casefold(), initiator_type.casefold())
        if key in seen:
            continue
        seen.add(key)
        events.append(
            BrowserDownloadNetworkEvent(
                schema_version="1.0",
                url=url,
                initiator_type=initiator_type,
                signal_kind=_classify_network_signal_kind(
                    url=url,
                    initiator_type=initiator_type,
                ),
            )
        )
    return events[-25:]


def _merge_network_events(
    first: list[BrowserDownloadNetworkEvent],
    second: list[BrowserDownloadNetworkEvent],
) -> list[BrowserDownloadNetworkEvent]:
    merged: list[BrowserDownloadNetworkEvent] = []
    seen: set[tuple[str, str]] = set()
    for event in [*first, *second]:
        key = (event.url.casefold(), event.initiator_type.casefold())
        if key in seen:
            continue
        seen.add(key)
        merged.append(event)
    return merged[-25:]


def _classify_network_signal_kind(*, url: str, initiator_type: str) -> str:
    lowered_url = str(url or "").strip().casefold()
    lowered_initiator = str(initiator_type or "").strip().casefold()
    if not lowered_url:
        return "other"
    if lowered_url.endswith(".pdf") or ".pdf?" in lowered_url:
        return "document_request"
    if any(
        marker in lowered_url
        for marker in ("thank", "success", "confirm", "complete", "done")
    ):
        return "confirmation_request"
    if any(
        marker in lowered_url
        for marker in (
            "download",
            "document",
            "whitepaper",
            "research",
            "study",
            "ebook",
            "report",
        )
    ):
        return "document_request"
    if lowered_initiator in {"fetch", "xmlhttprequest", "beacon"} and any(
        marker in lowered_url
        for marker in (
            "form",
            "submit",
            "lead",
            "register",
            "request",
            "contact",
            "marketo",
            "pardot",
            "hubspot",
            "eloqua",
        )
    ):
        return "submission_request"
    if lowered_initiator == "navigation":
        return "navigation_request"
    return "other"


def _collect_page_resource_urls(
    page: Any,
    *,
    ctx: RunContext,
    normalized_url: str,
) -> list[str]:
    js_result = browser_helper_js(
        page=page,
        expression="""
                return (() => {
                  const entries = globalThis.performance?.getEntriesByType?.('resource') || [];
                  return entries
                    .map((entry) => String(entry?.name || '').trim())
                    .filter(Boolean)
                    .filter((url) => {
                      const lowered = url.toLowerCase();
                      return lowered.endsWith('.pdf')
                        || lowered.includes('.pdf?')
                        || lowered.includes('download')
                        || lowered.includes('document')
                        || lowered.includes('report');
                    });
                })();
                """,
        ctx=ctx,
        normalized_url=normalized_url,
    )
    if js_result.status != "ok":
        return []
    resource_urls = _coerce_evaluate_list(js_result.result)
    return [
        str(raw_url or "").strip()
        for raw_url in resource_urls
        if str(raw_url or "").strip()
    ]


def _collect_dom_candidate_urls(
    page: Any,
    *,
    ctx: RunContext,
    normalized_url: str,
) -> list[str]:
    js_result = browser_helper_js(
        page=page,
        expression="""
                return (() => {
                  const selectors = [
                    'a[href]',
                    'iframe[src]',
                    'embed[src]',
                    'object[data]',
                    'source[src]',
                    'link[href]',
                    'meta[content]',
                  ];
                  const values = [];
                  for (const selector of selectors) {
                    for (const node of document.querySelectorAll(selector)) {
                      const value =
                        node.getAttribute('href')
                        || node.getAttribute('src')
                        || node.getAttribute('data')
                        || node.getAttribute('content')
                        || '';
                      if (value) {
                        values.push(String(value).trim());
                      }
                    }
                  }
                  return values;
                })();
                """,
        ctx=ctx,
        normalized_url=normalized_url,
    )
    if js_result.status != "ok":
        return []
    candidate_urls = _coerce_evaluate_list(js_result.result)
    return [
        str(raw_url or "").strip()
        for raw_url in candidate_urls
        if str(raw_url or "").strip()
    ]


def _coerce_evaluate_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    token = str(value or "").strip()
    if not token:
        return []
    try:
        parsed = json.loads(token)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def _extract_documentish_urls_from_html(html: str) -> list[str]:
    token = str(html or "")
    if not token.strip():
        return []
    urls: list[str] = []
    for match in re.finditer(
        r"""(?is)(?:href|src|data|content)\s*=\s*['"]([^'"]+)['"]""",
        token,
    ):
        candidate = str(match.group(1) or "").strip()
        if candidate:
            urls.append(candidate)
    return urls


def _looks_like_documentish_url(raw_url: str) -> bool:
    token = str(raw_url or "").strip()
    if not token:
        return False
    lowered = token.casefold()
    if lowered.startswith(("/", "./", "../")) and (
        lowered.endswith(".pdf") or ".pdf?" in lowered
    ):
        return True
    if not lowered.startswith("http"):
        return False
    if lowered.endswith(".pdf") or ".pdf?" in lowered:
        return True
    return any(
        marker in lowered
        for marker in (
            "download",
            "document",
            "report",
            "whitepaper",
            "research",
            "study",
            "ebook",
            "insight",
        )
    )


__all__ = [
    "_collect_network_resource_urls",
    "_collect_network_events",
    "_collect_network_events_via_cdp",
    "_network_events_from_raw_events",
    "_merge_network_events",
    "_classify_network_signal_kind",
    "_collect_page_resource_urls",
    "_collect_dom_candidate_urls",
    "_coerce_evaluate_list",
    "_extract_documentish_urls_from_html",
    "_looks_like_documentish_url",
]
