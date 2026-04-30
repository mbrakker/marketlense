from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlsplit

from src.contracts.publisher_inventory import (
    PublisherInventoryLandingPageInspectionItem,
    PublisherInventoryLandingPageInspectionRequest,
    PublisherInventoryLandingPageInspectionResponse,
    PublisherInventoryLandingPageObservation,
    PublisherInventoryPage,
    PublisherInventoryRawCandidate,
    PublisherInventoryRouteTrace,
    PublisherInventoryScenarioSummary,
    PublisherInventoryServiceRequest,
    PublisherInventoryServiceResponse,
)
from src.contracts.http_acquisition import (
    HttpAcquisitionRequest,
    HttpAcquisitionResponsePolicy,
)
from src.contracts.run_context import RunContext
from src.services._http_acquisition import execute_http_acquisition
from src.services._publisher_inventory_service.discovery_activity import (
    _anchor_fingerprint,
    _extract_component_link_anchors,
    _extract_candidates_from_html,
    _normalize_absolute_url,
    _normalize_text,
    _resolve_next_page_url,
    _score_http_candidate_confidence,
    _with_candidate_metadata,
)
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.publisher_inventory_service")

HTTP_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/137.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
_WORDPRESS_AJAX_CONFIG_RE = re.compile(
    r"var\s+wpajax\s*=\s*(?P<payload>\{.*?\})\s*;",
    re.IGNORECASE | re.DOTALL,
)
_WORDPRESS_ACTION_RE = re.compile(
    r"action\s*:\s*['\"](?P<action>[a-z0-9_-]+)['\"]",
    re.IGNORECASE,
)
_SCRIPT_SRC_RE = re.compile(
    r"<script[^>]+src=['\"](?P<src>[^'\"]+)['\"]",
    re.IGNORECASE,
)
_HTML_TITLE_RE = re.compile(
    r"<title[^>]*>(?P<title>.*?)</title>",
    re.IGNORECASE | re.DOTALL,
)
_ASSET_TYPE_TERMS = (
    "report",
    "reports",
    "white paper",
    "whitepaper",
    "ebook",
    "study",
    "research",
    "benchmark",
    "market report",
    "industry report",
    "survey",
    "outlook",
    "playbook",
    "guide",
    "infographic",
    "snapshot",
)
_DOWNLOAD_LANGUAGE_MARKERS = (
    "download",
    "get the report",
    "get report",
    "access report",
    "read report",
    "download the report",
    "download now",
    "fill out the form",
    "request the report",
    "view the report",
)
_GATED_FORM_MARKERS = (
    "fill out the form",
    "complete the form",
    "submit the form",
    "register to download",
    "enter your details",
    "get access",
    "access the report",
)
_DOCUMENT_STRUCTURE_MARKERS = (
    "contents of the report",
    "report includes",
    "executive summary",
    "table of contents",
    "methodology",
    "key findings",
    "findings",
    "chapters",
    "pages",
)
_PRINT_LANGUAGE_MARKERS = (
    "print",
    "printable",
    "printer friendly",
    "save as pdf",
)
_PURCHASE_MARKERS = (
    "buy now",
    "buy the report",
    "buy report",
    "add to cart",
    "purchase",
    "price",
)
_EDITORIAL_URL_MARKERS = (
    "/blog/",
    "/blogs/",
    "/news/",
    "/press-release",
    "/press-releases/",
    "/article/",
    "/articles/",
    "/help/",
    "/expert-view",
    "/expert-views/",
)
_EDITORIAL_MARKERS = (
    " min read",
    "minute read",
    "share this article",
    "related articles",
    "latest articles",
    "published on",
    "posted on",
    "author",
    "expert view",
    "blog",
    "newsroom",
)
_RELATED_POST_MARKERS = (
    "related posts",
    "related articles",
    "you may also like",
    "recommended for you",
)
_NEWSLETTER_MARKERS = (
    "newsletter",
    "subscribe",
    "sign up",
    "stay updated",
)
_CONTACT_SALES_MARKERS = (
    "contact sales",
    "book a demo",
    "request a demo",
    "talk to sales",
)
_DEAD_PAGE_MARKERS = (
    "page not found",
    "404",
    "requested url was not found",
    "the page you requested could not be found",
    "this page doesn't exist",
    "this page does not exist",
)
_TRANSIENT_HTTP_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}
_PROTECTED_DOCUMENT_HTTP_STATUS_CODES = {401, 403}
_INVENTORY_HTML_MAX_BYTES = 4 * 1024 * 1024
_SCRIPT_FETCH_MAX_BYTES = 1024 * 1024
_LANDING_PAGE_HTML_MAX_BYTES = 2 * 1024 * 1024


class _InventoryHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.anchors: list[dict[str, str]] = []
        self.next_link_hrefs: list[str] = []
        self._current_anchor: dict[str, str] | None = None
        self._anchor_text: list[str] = []
        self._container_stack: list[dict[str, object]] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered_tag = tag.lower()
        attr_map = {key.lower(): str(value or "") for key, value in attrs}
        if lowered_tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
            return
        if lowered_tag in {"article", "section", "li", "div"}:
            self._container_stack.append({"text_parts": []})
        if lowered_tag == "link":
            rel = attr_map.get("rel", "").lower()
            href = attr_map.get("href", "").strip()
            if href and "next" in rel:
                self.next_link_hrefs.append(href)
        if lowered_tag != "a":
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
        if self._skip_depth > 0:
            return
        normalized = _normalize_text(data)
        if self._container_stack and normalized:
            text_parts = self._container_stack[-1]["text_parts"]
            assert isinstance(text_parts, list)
            if sum(len(part) for part in text_parts) < 400:
                text_parts.append(normalized)
        if self._current_anchor is not None:
            self._anchor_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        lowered_tag = tag.lower()
        if lowered_tag in {"script", "style", "noscript"}:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if lowered_tag == "a" and self._current_anchor is not None:
            text = _normalize_text(" ".join(self._anchor_text))
            context_text = ""
            if self._container_stack:
                text_parts = self._container_stack[-1]["text_parts"]
                assert isinstance(text_parts, list)
                context_text = _normalize_text(" ".join(text_parts))
            title = (
                text
                or _normalize_text(self._current_anchor.get("aria_label", ""))
                or _normalize_text(self._current_anchor.get("title_attr", ""))
            )
            self.anchors.append(
                {
                    "href": self._current_anchor["href"],
                    "rel": self._current_anchor.get("rel", ""),
                    "text": title,
                    "context_text": context_text,
                }
            )
            self._current_anchor = None
            self._anchor_text = []
            return
        if lowered_tag in {"article", "section", "li", "div"} and self._container_stack:
            self._container_stack.pop()


class _LandingPageInspectionHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.page_title = ""
        self.og_title = ""
        self.h1_title = ""
        self.form_count = 0
        self.visible_text = ""
        self.interactive_texts: list[str] = []
        self._capture_title = False
        self._capture_h1 = False
        self._skip_depth = 0
        self._title_parts: list[str] = []
        self._h1_parts: list[str] = []
        self._visible_parts: list[str] = []
        self._current_interactive_parts: list[str] | None = None
        self._current_interactive_seed = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered_tag = tag.lower()
        attr_map = {key.lower(): str(value or "") for key, value in attrs}
        if lowered_tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
            return
        if lowered_tag == "meta":
            property_name = str(attr_map.get("property", "")).strip().casefold()
            meta_name = str(attr_map.get("name", "")).strip().casefold()
            if property_name == "og:title" or meta_name == "og:title":
                content = _normalize_text(attr_map.get("content", ""))
                if content and not self.og_title:
                    self.og_title = content
            return
        if lowered_tag == "title":
            self._capture_title = True
            self._title_parts = []
            return
        if lowered_tag == "h1" and not self.h1_title:
            self._capture_h1 = True
            self._h1_parts = []
        if lowered_tag == "form":
            self.form_count += 1
        if lowered_tag == "input":
            input_type = str(attr_map.get("type", "")).strip().casefold()
            if input_type in {"submit", "button"}:
                label = _normalize_text(
                    attr_map.get("value", "")
                    or attr_map.get("aria-label", "")
                    or attr_map.get("title", "")
                )
                if label:
                    self.interactive_texts.append(label)
            return
        if lowered_tag in {"a", "button"}:
            self._current_interactive_parts = []
            self._current_interactive_seed = _normalize_text(
                attr_map.get("aria-label", "") or attr_map.get("title", "")
            )

    def handle_endtag(self, tag: str) -> None:
        lowered_tag = tag.lower()
        if lowered_tag in {"script", "style", "noscript"}:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if lowered_tag == "title":
            self.page_title = _normalize_text(" ".join(self._title_parts))
            self._capture_title = False
            self._title_parts = []
            return
        if lowered_tag == "h1" and self._capture_h1:
            self.h1_title = _normalize_text(" ".join(self._h1_parts))
            self._capture_h1 = False
            self._h1_parts = []
            return
        if (
            lowered_tag in {"a", "button"}
            and self._current_interactive_parts is not None
        ):
            label = _normalize_text(" ".join(self._current_interactive_parts))
            label = label or self._current_interactive_seed
            if label:
                self.interactive_texts.append(label)
            self._current_interactive_parts = None
            self._current_interactive_seed = ""

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return
        normalized = _normalize_text(data)
        if not normalized:
            return
        if self._capture_title:
            self._title_parts.append(normalized)
        if self._capture_h1:
            self._h1_parts.append(normalized)
        if self._current_interactive_parts is not None:
            self._current_interactive_parts.append(normalized)
        if sum(len(part) for part in self._visible_parts) < 20000:
            self._visible_parts.append(normalized)
            self.visible_text = " ".join(self._visible_parts)


def discover_inventory_via_http(
    request: PublisherInventoryServiceRequest,
    ctx: RunContext,
    normalized_url: str,
    *,
    use_hint: bool,
    scenario_summary: PublisherInventoryScenarioSummary | None,
    requests_module: Any,
) -> PublisherInventoryServiceResponse:
    headers = dict(HTTP_BROWSER_HEADERS)
    current_url = normalized_url
    visited: set[str] = set()
    seen_page_fingerprints: set[tuple[tuple[str, str, str], ...]] = set()
    pages: list[PublisherInventoryPage] = []
    candidates: list[PublisherInventoryRawCandidate] = []
    rejected_low_confidence_count = 0
    page_number = 1
    wordpress_ajax_action = ""
    while current_url and page_number <= request.settings.pagination_max_pages:
        if current_url in visited:
            break
        visited.add(current_url)
        request_urls = _http_request_url_candidates(current_url)
        logger.info(
            log_event(
                ctx,
                role="service",
                event="publisher_inventory_http_request",
                module=logger.name,
                fields={
                    "page_url": current_url,
                    "page_number": page_number,
                    "request_urls": request_urls,
                    "headers": headers,
                },
            )
        )
        response = None
        last_request_error: AppError | None = None
        for request_url in request_urls:
            try:
                response = execute_http_acquisition(
                    request=HttpAcquisitionRequest(
                        schema_version="1.0",
                        purpose="publisher_inventory_http_page_fetch",
                        method="GET",
                        url=request_url,
                        headers=headers,
                        timeout_seconds=request.settings.http_timeout_seconds,
                        response_policy=HttpAcquisitionResponsePolicy(
                            schema_version="1.0",
                            require_success_status=True,
                            capture_text=True,
                            capture_content_type_markers=("html", "xml"),
                            max_body_bytes=_INVENTORY_HTML_MAX_BYTES,
                            truncate_body=True,
                        ),
                        error_code="publisher_inventory_http_failed",
                        error_message="Failed to fetch publisher inventory page via HTTP",
                        context_fields={
                            "page_url": current_url,
                            "request_url": request_url,
                        },
                    ),
                    ctx=ctx,
                    requests_module=requests_module,
                )
                break
            except AppError as exc:
                last_request_error = exc
                response = None
                continue
        if response is None:
            raise last_request_error or AppError(
                code="publisher_inventory_http_failed",
                message="Failed to fetch publisher inventory page via HTTP",
                retryable=True,
                context={"page_url": current_url},
            )
        final_page_url = _normalize_absolute_url(str(response.final_url or current_url))
        html = str(response.text_body or "")
        page_title = _extract_html_page_title(html)
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
                    "body_truncated": response.body_truncated,
                },
            )
        )
        parser = _InventoryHtmlParser()
        try:
            parser.feed(html)
        except Exception as exc:
            raise AppError(
                code="publisher_inventory_http_invalid_html",
                message="Direct HTTP parsing received invalid publisher inventory HTML",
                cause=exc,
                retryable=True,
                context={"page_url": final_page_url},
            ) from exc
        anchors = list(parser.anchors)
        if not anchors:
            anchors = _extract_component_link_anchors(
                html_text=html,
                page_url=final_page_url,
            )
        next_page_url = _resolve_next_page_url(
            current_page_url=final_page_url,
            page_number=page_number,
            anchors=anchors,
            rel_next_hrefs=parser.next_link_hrefs,
        )
        page_candidates = _extract_candidates_from_html(
            anchors=anchors,
            page_url=final_page_url,
            page_number=page_number,
            next_page_url=next_page_url,
            provenance="http_parse",
        )
        page_fingerprint = _anchor_fingerprint(parser.anchors)
        if page_fingerprint and page_fingerprint in seen_page_fingerprints:
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="publisher_inventory_http_duplicate_page_fingerprint",
                    module=logger.name,
                    fields={
                        "page_url": final_page_url,
                        "page_number": page_number,
                        "candidate_count": len(page_candidates),
                    },
                )
            )
            break
        if page_fingerprint:
            seen_page_fingerprints.add(page_fingerprint)
        confidence_by_url = {
            candidate.url: _score_http_candidate_confidence(
                candidate,
                page_url=final_page_url,
            )
            for candidate in page_candidates
        }
        qualified_page_candidates = _with_candidate_metadata(
            [
                candidate
                for candidate in page_candidates
                if confidence_by_url.get(candidate.url, 0.0) >= 0.60
            ],
            provenance="http_parse",
            confidence_by_url=confidence_by_url,
        )
        rejected_low_confidence_count += max(
            0,
            len(page_candidates) - len(qualified_page_candidates),
        )
        pages.append(
            PublisherInventoryPage(
                schema_version="1.0",
                page_number=page_number,
                page_url=final_page_url,
            )
        )
        candidates.extend(qualified_page_candidates)
        if not next_page_url:
            break
        current_url = next_page_url
        page_number += 1

    if _should_try_wordpress_ajax_supplement(
        normalized_url=normalized_url,
        candidates=candidates,
    ):
        ajax_pages, ajax_candidates, ajax_action = (
            _discover_inventory_via_wordpress_ajax(
                request=request,
                ctx=ctx,
                normalized_url=normalized_url,
                page_url=pages[-1].page_url if pages else normalized_url,
                page_title=page_title if "page_title" in locals() else "",
                html=html if "html" in locals() else "",
                headers=headers,
                requests_module=requests_module,
            )
        )
        if ajax_candidates:
            existing_urls = {candidate.url for candidate in candidates}
            candidates.extend(
                [
                    candidate
                    for candidate in ajax_candidates
                    if candidate.url not in existing_urls
                ]
            )
            if len(ajax_pages) > len(pages):
                pages = ajax_pages
            wordpress_ajax_action = ajax_action
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="publisher_inventory_http_wordpress_ajax_complete",
                    module=logger.name,
                    fields={
                        "normalized_url": normalized_url,
                        "ajax_action": ajax_action,
                        "page_count": len(pages),
                        "candidate_count": len(candidates),
                    },
                )
            )
    if not candidates:
        raise AppError(
            code="publisher_inventory_http_empty",
            message="Direct HTTP parsing found no valid report inventory items",
            retryable=False,
            context={"normalized_url": normalized_url},
        )

    service_response = PublisherInventoryServiceResponse(
        schema_version="1.0",
        source_url=request.insights_url,
        normalized_url=normalized_url,
        route_kind="http_parse",
        route_summary=(
            f"Fetched inventory HTML directly and traversed {len(pages)} page(s) via pagination links."
            if not wordpress_ajax_action
            else (
                "Fetched inventory HTML directly and recovered report cards via "
                f"WordPress AJAX action `{wordpress_ajax_action}` across {len(pages)} page(s)."
            )
        ),
        final_page_url=pages[-1].page_url,
        used_route_hint=use_hint,
        pages=pages,
        candidates=candidates,
        route_trace=PublisherInventoryRouteTrace(
            schema_version="1.0",
            followed_report_listing=False,
            applied_report_filter=False,
            selected_filters=[],
            selected_tab_labels=[],
            pagination_mode="next_link" if len(pages) > 1 else "none",
            preferred_control_labels=[],
            candidate_surface_guard="none",
            surface_class=(
                "archive_feed"
                if len(pages) > 1 or "filters=" in normalized_url
                else "direct_detail"
            ),
        ),
        scenario_summary=scenario_summary,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="publisher_inventory_http_complete",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "page_count": len(service_response.pages),
                "candidate_count": len(service_response.candidates),
                "rejected_low_confidence_count": rejected_low_confidence_count,
                "average_confidence": round(
                    sum(
                        candidate.confidence or 0.0
                        for candidate in service_response.candidates
                    )
                    / len(service_response.candidates),
                    4,
                ),
                "candidate_provenance_counts": _candidate_provenance_counts(
                    service_response.candidates
                ),
                "used_route_hint": service_response.used_route_hint,
            },
        )
    )
    return service_response


def _discover_inventory_via_wordpress_ajax(
    *,
    request: PublisherInventoryServiceRequest,
    ctx: RunContext,
    normalized_url: str,
    page_url: str,
    page_title: str,
    html: str,
    headers: dict[str, str],
    requests_module: Any,
) -> tuple[list[PublisherInventoryPage], list[PublisherInventoryRawCandidate], str]:
    ajax_config = _extract_wordpress_ajax_config(html=html, page_url=page_url)
    if ajax_config is None:
        return [], [], ""
    action_names = _discover_wordpress_ajax_actions(
        ctx=ctx,
        html=html,
        page_url=page_url,
        page_title=page_title,
        headers=headers,
        requests_module=requests_module,
        timeout_seconds=request.settings.http_timeout_seconds,
    )
    if not action_names:
        return [], [], ""
    logger.info(
        log_event(
            ctx,
            role="service",
            event="publisher_inventory_http_wordpress_ajax_start",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "page_url": page_url,
                "ajax_url": ajax_config["url"],
                "action_names": action_names,
            },
        )
    )
    for action_name in action_names:
        pages: list[PublisherInventoryPage] = []
        candidates: list[PublisherInventoryRawCandidate] = []
        seen_urls: set[str] = set()
        max_pages = request.settings.pagination_max_pages
        for page_number in range(1, request.settings.pagination_max_pages + 1):
            payload = {
                "action": action_name,
                "nonce": ajax_config["nonce"],
                "not_in": "0",
                "paged": str(page_number),
            }
            try:
                response = execute_http_acquisition(
                    request=HttpAcquisitionRequest(
                        schema_version="1.0",
                        purpose="publisher_inventory_wordpress_ajax_fetch",
                        method="POST",
                        url=ajax_config["url"],
                        headers={
                            **headers,
                            "X-Requested-With": "XMLHttpRequest",
                        },
                        timeout_seconds=request.settings.http_timeout_seconds,
                        response_policy=HttpAcquisitionResponsePolicy(
                            schema_version="1.0",
                            require_success_status=True,
                            capture_text=True,
                            capture_content_type_markers=("json", "javascript", "text"),
                            max_body_bytes=_INVENTORY_HTML_MAX_BYTES,
                            truncate_body=True,
                        ),
                        error_code="publisher_inventory_http_failed",
                        error_message="Failed to fetch publisher inventory page via HTTP",
                        data=payload,
                        context_fields={
                            "page_url": page_url,
                            "action": action_name,
                            "paged": str(page_number),
                        },
                    ),
                    ctx=ctx,
                    requests_module=requests_module,
                )
            except AppError:
                break
            try:
                response_payload = json.loads(response.text_body or "{}")
            except json.JSONDecodeError:
                break
            posts_html = str(response_payload.get("posts") or "").strip()
            if not posts_html:
                break
            try:
                parsed_max_pages = int(response_payload.get("max_num_pages") or 0)
            except (TypeError, ValueError):
                parsed_max_pages = 0
            if parsed_max_pages > 0:
                max_pages = min(request.settings.pagination_max_pages, parsed_max_pages)
            parser = _InventoryHtmlParser()
            try:
                parser.feed(posts_html)
            except Exception:
                break
            anchors = list(parser.anchors)
            if not anchors:
                anchors = _extract_component_link_anchors(
                    html_text=posts_html,
                    page_url=page_url,
                )
            page_candidates = _extract_candidates_from_html(
                anchors=anchors,
                page_url=page_url,
                page_number=page_number,
                next_page_url=None,
                origin_url=normalized_url,
                page_title=page_title,
                provenance="http_parse_wordpress_ajax",
            )
            confidence_by_url = {
                candidate.url: _score_http_candidate_confidence(
                    candidate,
                    page_url=page_url,
                )
                for candidate in page_candidates
            }
            qualified_page_candidates = _with_candidate_metadata(
                [
                    candidate
                    for candidate in page_candidates
                    if confidence_by_url.get(candidate.url, 0.0) >= 0.60
                    and candidate.url not in seen_urls
                ],
                provenance="http_parse_wordpress_ajax",
                confidence_by_url=confidence_by_url,
            )
            if qualified_page_candidates:
                pages.append(
                    PublisherInventoryPage(
                        schema_version="1.0",
                        page_number=page_number,
                        page_url=page_url,
                    )
                )
                candidates.extend(qualified_page_candidates)
                seen_urls.update(
                    candidate.url for candidate in qualified_page_candidates
                )
            if page_number >= max_pages:
                break
        if candidates:
            return pages, candidates, action_name
    return [], [], ""


def _extract_html_page_title(html: str) -> str:
    match = _HTML_TITLE_RE.search(str(html or ""))
    if match is None:
        return ""
    return _normalize_text(str(match.group("title") or ""))


def _http_request_url_candidates(url: str) -> list[str]:
    normalized_url = _normalize_absolute_url(url) or str(url or "").strip()
    if not normalized_url:
        return []
    candidates = [normalized_url]
    parsed = urlsplit(normalized_url)
    path = str(parsed.path or "")
    if (
        path
        and not path.endswith("/")
        and "." not in path.rsplit("/", 1)[-1]
        and not parsed.query
    ):
        slash_url = f"{normalized_url}/"
        if slash_url not in candidates:
            candidates.append(slash_url)
    return candidates


def _should_try_wordpress_ajax_supplement(
    *,
    normalized_url: str,
    candidates: list[PublisherInventoryRawCandidate],
) -> bool:
    if not candidates:
        return True
    return len(candidates) <= 3


def _extract_wordpress_ajax_config(
    *,
    html: str,
    page_url: str,
) -> dict[str, str] | None:
    match = _WORDPRESS_AJAX_CONFIG_RE.search(str(html or ""))
    if match is None:
        return None
    try:
        payload = json.loads(str(match.group("payload") or ""))
    except json.JSONDecodeError:
        return None
    ajax_url = _normalize_absolute_url(urljoin(page_url, str(payload.get("url") or "")))
    nonce = str(payload.get("nonce") or "").strip()
    if not ajax_url or not nonce:
        return None
    return {"url": ajax_url, "nonce": nonce}


def _discover_wordpress_ajax_actions(
    *,
    ctx: RunContext,
    html: str,
    page_url: str,
    page_title: str,
    headers: dict[str, str],
    requests_module: Any,
    timeout_seconds: float,
) -> list[str]:
    action_names = {
        str(match.group("action") or "").strip()
        for match in _WORDPRESS_ACTION_RE.finditer(str(html or ""))
        if str(match.group("action") or "").strip()
    }
    for script_url in _same_host_script_urls(html=html, page_url=page_url):
        try:
            response = execute_http_acquisition(
                request=HttpAcquisitionRequest(
                    schema_version="1.0",
                    purpose="publisher_inventory_wordpress_script_fetch",
                    method="GET",
                    url=script_url,
                    headers=headers,
                    timeout_seconds=timeout_seconds,
                    response_policy=HttpAcquisitionResponsePolicy(
                        schema_version="1.0",
                        require_success_status=True,
                        capture_text=True,
                        capture_content_type_markers=("javascript", "json", "text"),
                        max_body_bytes=_SCRIPT_FETCH_MAX_BYTES,
                        truncate_body=True,
                    ),
                    error_code="publisher_inventory_http_failed",
                    error_message="Failed to fetch publisher inventory page via HTTP",
                    context_fields={"script_url": script_url, "page_url": page_url},
                ),
                ctx=ctx,
                requests_module=requests_module,
            )
        except AppError:
            continue
        action_names.update(
            str(match.group("action") or "").strip()
            for match in _WORDPRESS_ACTION_RE.finditer(response.text_body or "")
            if str(match.group("action") or "").strip()
        )
        if action_names:
            break
    preferred_tokens = {
        token
        for token in re.findall(
            r"[a-z0-9]+",
            " ".join(
                part
                for part in (
                    str(urlsplit(page_url).path or ""),
                    str(page_title or ""),
                )
                if part
            ).casefold(),
        )
        if token
    }
    scored_actions = sorted(
        action_names,
        key=lambda action: (
            _score_wordpress_ajax_action(action, preferred_tokens),
            len(action),
        ),
        reverse=True,
    )
    preferred_actions = [
        action
        for action in scored_actions
        if _score_wordpress_ajax_action(action, preferred_tokens) > 0
    ][:2]
    if preferred_actions:
        return preferred_actions
    fallback_actions: list[str] = []
    for token in sorted(preferred_tokens):
        if len(token) < 4:
            continue
        for action_name in (token, f"{token}_filter"):
            if action_name not in fallback_actions:
                fallback_actions.append(action_name)
    return fallback_actions[:4]


def _same_host_script_urls(
    *,
    html: str,
    page_url: str,
) -> list[str]:
    page_host = str(urlsplit(page_url).hostname or "").strip().casefold()
    script_urls: list[str] = []
    for match in _SCRIPT_SRC_RE.finditer(str(html or "")):
        script_url = _normalize_absolute_url(
            urljoin(page_url, str(match.group("src") or ""))
        )
        script_host = str(urlsplit(script_url).hostname or "").strip().casefold()
        if not script_url or script_host != page_host or script_url in script_urls:
            continue
        script_urls.append(script_url)
    return script_urls[:4]


def _score_wordpress_ajax_action(
    action_name: str,
    preferred_tokens: set[str],
) -> int:
    normalized_action = str(action_name or "").strip().casefold()
    if not normalized_action:
        return 0
    action_tokens = {
        token for token in re.findall(r"[a-z0-9]+", normalized_action) if token
    }
    score = len(action_tokens & preferred_tokens)
    if normalized_action.endswith("_filter"):
        score += 1
    return score


def inspect_inventory_landing_pages(
    request: PublisherInventoryLandingPageInspectionRequest,
    ctx: RunContext,
    *,
    requests_module: Any,
) -> PublisherInventoryLandingPageInspectionResponse:
    if request.timeout_seconds <= 0:
        raise AppError(
            code="publisher_inventory_quality_timeout_invalid",
            message="Landing-page quality-check timeout must be greater than zero",
            retryable=False,
        )
    if request.max_workers <= 0:
        raise AppError(
            code="publisher_inventory_quality_workers_invalid",
            message="Landing-page quality-check max_workers must be at least one",
            retryable=False,
        )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="publisher_inventory_landing_page_inspection_start",
            module=logger.name,
            fields={
                "publisher_name": request.publisher_name,
                "item_count": len(request.items),
                "timeout_seconds": request.timeout_seconds,
                "max_workers": request.max_workers,
            },
        )
    )
    if not request.items:
        return PublisherInventoryLandingPageInspectionResponse(
            schema_version="1.0",
            observations=[],
        )
    observations_by_url: dict[str, PublisherInventoryLandingPageObservation] = {}
    worker_count = min(max(1, request.max_workers), len(request.items))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        future_map = {
            executor.submit(
                _inspect_landing_page_item,
                item=item,
                timeout_seconds=request.timeout_seconds,
                requests_module=requests_module,
                ctx=ctx,
            ): item
            for item in request.items
        }
        for future in as_completed(future_map):
            item = future_map[future]
            try:
                observation = future.result()
            except Exception as exc:  # pragma: no cover - defensive guard
                observation = PublisherInventoryLandingPageObservation(
                    schema_version="1.0",
                    canonical_url=item.canonical_url,
                    source_title=item.title,
                    final_url=item.canonical_url,
                    final_title="",
                    h1_title="",
                    og_title="",
                    http_status_code=None,
                    content_type="",
                    fetch_error=str(exc),
                    is_pdf=False,
                    has_asset_type_term=False,
                    has_download_language=False,
                    has_gated_form=False,
                    has_document_structure=False,
                    has_price_or_purchase=False,
                    has_print_language=False,
                    has_editorial_url_pattern=_has_editorial_url_pattern(
                        item.canonical_url
                    ),
                    has_editorial_markers=False,
                    has_related_posts=False,
                    has_newsletter_cta=False,
                    has_contact_sales_cta=False,
                    has_dead_page_marker=True,
                    verification_class="dead",
                    recovery_eligible=False,
                    source_surface_class=_classify_source_surface(
                        canonical_url=item.canonical_url,
                        source_page_url=item.source_page_url,
                        source_title=item.title,
                    ),
                )
            observations_by_url[item.canonical_url] = observation
    observations = [observations_by_url[item.canonical_url] for item in request.items]
    response = PublisherInventoryLandingPageInspectionResponse(
        schema_version="1.0",
        observations=observations,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="publisher_inventory_landing_page_inspection_complete",
            module=logger.name,
            fields={
                "publisher_name": request.publisher_name,
                "item_count": len(request.items),
                "observed_count": len(response.observations),
                "dead_page_count": sum(
                    1 for item in response.observations if item.has_dead_page_marker
                ),
                "pdf_count": sum(1 for item in response.observations if item.is_pdf),
            },
        )
    )
    return response


def _inspect_landing_page_item(
    *,
    item: PublisherInventoryLandingPageInspectionItem,
    timeout_seconds: float,
    requests_module: Any,
    ctx: RunContext,
) -> PublisherInventoryLandingPageObservation:
    normalized_url = _normalize_absolute_url(item.canonical_url)
    if not normalized_url:
        return _dead_observation(
            item=item,
            final_url=item.canonical_url,
            fetch_error="invalid_candidate_url",
        )
    headers = dict(HTTP_BROWSER_HEADERS)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="publisher_inventory_landing_page_request",
            module=logger.name,
            fields={
                "candidate_url": normalized_url,
                "timeout_seconds": timeout_seconds,
            },
        )
    )
    try:
        response = execute_http_acquisition(
            request=HttpAcquisitionRequest(
                schema_version="1.0",
                purpose="publisher_inventory_landing_page_fetch",
                method="GET",
                url=normalized_url,
                headers=headers,
                timeout_seconds=timeout_seconds,
                response_policy=HttpAcquisitionResponsePolicy(
                    schema_version="1.0",
                    require_success_status=False,
                    capture_text=True,
                    capture_content_type_markers=("html", "xml"),
                    max_body_bytes=_LANDING_PAGE_HTML_MAX_BYTES,
                    truncate_body=True,
                ),
                error_code="publisher_inventory_quality_fetch_failed",
                error_message="Failed to fetch landing page during publisher inventory quality inspection",
                allow_redirects=True,
                context_fields={"candidate_url": normalized_url},
            ),
            ctx=ctx,
            requests_module=requests_module,
        )
    except AppError as exc:
        return _dead_observation(
            item=item,
            final_url=normalized_url,
            fetch_error=exc.message,
        )
    final_url = (
        _normalize_absolute_url(str(response.final_url or normalized_url))
        or normalized_url
    )
    content_type = str(response.content_type or "").strip()
    status_code = int(response.status_code)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="publisher_inventory_landing_page_response",
            module=logger.name,
            fields={
                "candidate_url": normalized_url,
                "final_url": final_url,
                "status_code": status_code,
                "content_type": content_type,
                "body_truncated": response.body_truncated,
            },
        )
    )
    lowered_content_type = content_type.casefold()
    if (
        final_url.casefold().endswith(".pdf")
        or "application/pdf" in lowered_content_type
    ):
        verification_class, recovery_eligible = _classify_verification(
            final_url=final_url,
            final_title="",
            h1_title="",
            og_title="",
            fetch_error="",
            http_status_code=status_code,
            is_pdf=status_code < 400,
            has_asset_type_term=True,
            has_download_language=True,
            has_document_structure=False,
            has_dead_page_marker=status_code >= 400,
        )
        return PublisherInventoryLandingPageObservation(
            schema_version="1.0",
            canonical_url=item.canonical_url,
            source_title=item.title,
            final_url=final_url,
            final_title="",
            h1_title="",
            og_title="",
            http_status_code=status_code,
            content_type=content_type,
            fetch_error="",
            is_pdf=status_code < 400,
            has_asset_type_term=True,
            has_download_language=True,
            has_gated_form=False,
            has_document_structure=False,
            has_price_or_purchase=False,
            has_print_language=False,
            has_editorial_url_pattern=_has_editorial_url_pattern(final_url),
            has_editorial_markers=False,
            has_related_posts=False,
            has_newsletter_cta=False,
            has_contact_sales_cta=False,
            has_dead_page_marker=status_code >= 400,
            verification_class=verification_class,
            recovery_eligible=recovery_eligible,
            source_surface_class=_classify_source_surface(
                canonical_url=item.canonical_url,
                source_page_url=item.source_page_url,
                source_title=item.title,
            ),
        )
    html = str(response.text_body or "")
    parser = _LandingPageInspectionHtmlParser()
    try:
        parser.feed(html)
    except Exception:
        parser = _LandingPageInspectionHtmlParser()
    interactive_text = _normalize_text(" ".join(parser.interactive_texts))
    combined_text = " ".join(
        part
        for part in (
            item.title,
            parser.page_title,
            parser.h1_title,
            parser.og_title,
            parser.visible_text,
            interactive_text,
            final_url,
        )
        if part
    )
    combined_lower = combined_text.casefold()
    interactive_lower = interactive_text.casefold()
    dead_page_marker = status_code >= 400 or _contains_any_marker(
        combined_lower, _DEAD_PAGE_MARKERS
    )
    verification_class, recovery_eligible = _classify_verification(
        final_url=final_url,
        final_title=parser.page_title,
        h1_title=parser.h1_title,
        og_title=parser.og_title,
        fetch_error="",
        http_status_code=status_code,
        is_pdf=False,
        has_asset_type_term=_contains_any_marker(combined_lower, _ASSET_TYPE_TERMS),
        has_download_language=(
            ".pdf" in combined_lower
            or _contains_any_marker(combined_lower, _DOWNLOAD_LANGUAGE_MARKERS)
        ),
        has_document_structure=_contains_any_marker(
            combined_lower, _DOCUMENT_STRUCTURE_MARKERS
        ),
        has_dead_page_marker=dead_page_marker,
    )
    observation = PublisherInventoryLandingPageObservation(
        schema_version="1.0",
        canonical_url=item.canonical_url,
        source_title=item.title,
        final_url=final_url,
        final_title=parser.page_title,
        h1_title=parser.h1_title,
        og_title=parser.og_title,
        http_status_code=status_code,
        content_type=content_type,
        fetch_error="",
        is_pdf=False,
        has_asset_type_term=_contains_any_marker(combined_lower, _ASSET_TYPE_TERMS),
        has_download_language=(
            ".pdf" in combined_lower
            or _contains_any_marker(combined_lower, _DOWNLOAD_LANGUAGE_MARKERS)
        ),
        has_gated_form=parser.form_count > 0
        and (
            _contains_any_marker(combined_lower, _GATED_FORM_MARKERS)
            or (
                _contains_any_marker(combined_lower, _DOWNLOAD_LANGUAGE_MARKERS)
                and _contains_any_marker(combined_lower, _ASSET_TYPE_TERMS)
            )
        ),
        has_document_structure=_contains_any_marker(
            combined_lower, _DOCUMENT_STRUCTURE_MARKERS
        ),
        has_price_or_purchase=(
            _contains_any_marker(interactive_lower, _PURCHASE_MARKERS)
            or _contains_price_signal(combined_text)
        ),
        has_print_language=_contains_any_marker(
            combined_lower, _PRINT_LANGUAGE_MARKERS
        ),
        has_editorial_url_pattern=_has_editorial_url_pattern(final_url),
        has_editorial_markers=_contains_any_marker(combined_lower, _EDITORIAL_MARKERS),
        has_related_posts=_contains_any_marker(combined_lower, _RELATED_POST_MARKERS),
        has_newsletter_cta=_contains_any_marker(combined_lower, _NEWSLETTER_MARKERS),
        has_contact_sales_cta=_contains_any_marker(
            combined_lower, _CONTACT_SALES_MARKERS
        ),
        has_dead_page_marker=dead_page_marker,
        verification_class=verification_class,
        recovery_eligible=recovery_eligible,
        source_surface_class=_classify_source_surface(
            canonical_url=item.canonical_url,
            source_page_url=item.source_page_url,
            source_title=item.title,
        ),
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="publisher_inventory_landing_page_observation",
            module=logger.name,
            fields={
                "candidate_url": normalized_url,
                "final_url": observation.final_url,
                "status_code": observation.http_status_code,
                "is_pdf": observation.is_pdf,
                "has_asset_type_term": observation.has_asset_type_term,
                "has_download_language": observation.has_download_language,
                "has_gated_form": observation.has_gated_form,
                "has_document_structure": observation.has_document_structure,
                "has_price_or_purchase": observation.has_price_or_purchase,
                "has_print_language": observation.has_print_language,
                "has_editorial_url_pattern": observation.has_editorial_url_pattern,
                "has_editorial_markers": observation.has_editorial_markers,
                "has_related_posts": observation.has_related_posts,
                "has_newsletter_cta": observation.has_newsletter_cta,
                "has_contact_sales_cta": observation.has_contact_sales_cta,
                "has_dead_page_marker": observation.has_dead_page_marker,
                "verification_class": observation.verification_class,
                "recovery_eligible": observation.recovery_eligible,
                "source_surface_class": observation.source_surface_class,
            },
        )
    )
    return observation


def _dead_observation(
    *,
    item: PublisherInventoryLandingPageInspectionItem,
    final_url: str,
    fetch_error: str,
) -> PublisherInventoryLandingPageObservation:
    source_surface_class = _classify_source_surface(
        canonical_url=item.canonical_url,
        source_page_url=item.source_page_url,
        source_title=item.title,
    )
    verification_class, recovery_eligible = _classify_verification(
        final_url=final_url,
        final_title="",
        h1_title="",
        og_title="",
        fetch_error=fetch_error,
        http_status_code=None,
        is_pdf=False,
        has_asset_type_term=False,
        has_download_language=False,
        has_document_structure=False,
        has_dead_page_marker=True,
    )
    return PublisherInventoryLandingPageObservation(
        schema_version="1.0",
        canonical_url=item.canonical_url,
        source_title=item.title,
        final_url=final_url,
        final_title="",
        h1_title="",
        og_title="",
        http_status_code=None,
        content_type="",
        fetch_error=fetch_error,
        is_pdf=False,
        has_asset_type_term=False,
        has_download_language=False,
        has_gated_form=False,
        has_document_structure=False,
        has_price_or_purchase=False,
        has_print_language=False,
        has_editorial_url_pattern=_has_editorial_url_pattern(final_url),
        has_editorial_markers=False,
        has_related_posts=False,
        has_newsletter_cta=False,
        has_contact_sales_cta=False,
        has_dead_page_marker=True,
        verification_class=verification_class,
        recovery_eligible=recovery_eligible,
        source_surface_class=source_surface_class,
    )


def _contains_any_marker(value: str, markers: tuple[str, ...]) -> bool:
    lowered_value = str(value or "").casefold()
    return any(marker in lowered_value for marker in markers)


def _has_editorial_url_pattern(url: str) -> bool:
    lowered_url = str(url or "").strip().casefold()
    if any(marker in lowered_url for marker in _EDITORIAL_URL_MARKERS):
        return True
    segments = [segment for segment in urlsplit(lowered_url).path.split("/") if segment]
    if (
        len(segments) >= 3
        and len(segments[0]) == 4
        and segments[0].isdigit()
        and len(segments[1]) in {1, 2}
        and segments[1].isdigit()
        and len(segments[2]) in {1, 2}
        and segments[2].isdigit()
    ):
        return True
    return False


def _contains_price_signal(value: str) -> bool:
    normalized = _normalize_text(value)
    if not normalized:
        return False
    return bool(
        re.search(
            r"(?<!\w)(?:\$|€|£)\s?\d|\b(?:usd|eur|gbp)\s?\d",
            normalized,
            flags=re.IGNORECASE,
        )
    )


def _classify_source_surface(
    *,
    canonical_url: str,
    source_page_url: str,
    source_title: str,
) -> str:
    candidate_url = str(canonical_url or "").strip().casefold()
    source_url = str(source_page_url or "").strip().casefold()
    source_title_lower = str(source_title or "").strip().casefold()
    if any(
        marker in candidate_url or marker in source_url
        for marker in ("/service/", "/services/", "/membership", "/subscription")
    ):
        return "service_membership"
    if source_url and source_url.rstrip("/") != candidate_url.rstrip("/"):
        if any(
            marker in source_url
            for marker in ("/reports", "/research", "/resources", "/insights")
        ):
            return "archive_feed"
        return "mixed_content_hub"
    if any(
        marker in candidate_url
        for marker in (
            "/report/",
            "/reports/",
            "/research-library/",
            "/study/",
            "/survey/",
        )
    ):
        return "direct_detail"
    if any(
        marker in candidate_url for marker in ("/research", "/insights", "/resources")
    ):
        return "research_hub"
    if any(
        marker in source_title_lower
        for marker in ("report", "study", "survey", "benchmark", "playbook")
    ):
        return "direct_detail"
    return "unknown"


def _classify_verification(
    *,
    final_url: str,
    final_title: str,
    h1_title: str,
    og_title: str,
    fetch_error: str,
    http_status_code: int | None,
    is_pdf: bool,
    has_asset_type_term: bool,
    has_download_language: bool,
    has_document_structure: bool,
    has_dead_page_marker: bool,
) -> tuple[str, bool]:
    combined = " ".join(
        part
        for part in (final_url, final_title, h1_title, og_title, fetch_error)
        if part
    ).casefold()
    if any(
        marker in combined
        for marker in (
            "access denied",
            "captcha",
            "just a moment",
            "verify you are human",
            "attention required",
        )
    ):
        return "challenge", True
    if fetch_error and any(
        marker in fetch_error.casefold()
        for marker in (
            "connection aborted",
            "connection reset",
            "read timed out",
            "remote end closed connection",
            "temporarily unavailable",
            "timed out",
        )
    ):
        return "transient_fetch_failure", True
    if int(http_status_code or 0) in _TRANSIENT_HTTP_STATUS_CODES:
        return "transient_fetch_failure", True
    if int(http_status_code or 0) in _PROTECTED_DOCUMENT_HTTP_STATUS_CODES and (
        is_pdf or has_asset_type_term or has_download_language or has_document_structure
    ):
        return "protected_document", True
    if fetch_error or has_dead_page_marker:
        return "dead", False
    if not (
        is_pdf or has_asset_type_term or has_download_language or has_document_structure
    ):
        return "weak_signal_html", False
    return "verified", False


def _candidate_provenance_counts(
    candidates: list[PublisherInventoryRawCandidate],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for candidate in candidates:
        provenance = str(candidate.provenance or "unknown").strip() or "unknown"
        counts[provenance] = counts.get(provenance, 0) + 1
    return counts
