from __future__ import annotations

# ruff: noqa: F401

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
