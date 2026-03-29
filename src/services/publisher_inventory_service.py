from __future__ import annotations

import asyncio
import logging
import os
import sys
from dataclasses import asdict
from hashlib import sha1
from html.parser import HTMLParser
from importlib import import_module
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urljoin, urlsplit

import requests
from pydantic import BaseModel, Field, ValidationError

from src.contracts.prompts import PromptLoadRequest, PromptRenderRequest
from src.contracts.publisher_inventory import (
    PublisherInventoryPage,
    PublisherInventoryRawCandidate,
    PublisherInventoryServiceRequest,
    PublisherInventoryServiceResponse,
)
from src.contracts.run_context import RunContext
from src.services.prompt_service import load_prompt_set, render_prompt
from src.utils.errors import AppError
from src.utils.logging import child_context, log_event
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


class _BrowserInventoryPageModel(BaseModel):
    page_number: int = Field(description="One-based inventory page number.")
    page_url: str = Field(description="Absolute visited inventory page URL.")


class _BrowserInventoryCandidateModel(BaseModel):
    url: str = Field(description="Absolute report detail or PDF URL.")
    title: str = Field(description="Human-readable report title.")
    source_page_url: str = Field(description="Absolute visited inventory page URL where this item was found.")
    discovered_on_page_number: int = Field(description="One-based inventory page number where this item was found.")
    pdf_url: str | None = Field(
        default=None,
        description="Absolute PDF URL when known.",
    )
    published_at_text: str | None = Field(
        default=None,
        description="Visible published-date text when available.",
    )


class _BrowserInventoryAgentResult(BaseModel):
    route_kind: str = Field(description="Must be `browser_render`.")
    route_summary: str = Field(description="Short summary of the successful browser route, including pagination.")
    final_page_url: str = Field(description="Final browser URL after the run.")
    pages: list[_BrowserInventoryPageModel] = Field(
        description="Visited inventory pages in traversal order."
    )
    candidates: list[_BrowserInventoryCandidateModel] = Field(
        description="Discovered report items across all visited inventory pages."
    )


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
    prompt_ctx = child_context(ctx, task_id=ctx.task_id)
    prompt_set = load_prompt_set(
        PromptLoadRequest(
            schema_version="1.0",
            namespace=request.settings.prompt_namespace,
            reload_if_changed=True,
            force_reload=False,
        ),
        prompt_ctx,
    )
    system_prompt = render_prompt(
        PromptRenderRequest(
            schema_version="1.0",
            template=prompt_set.system,
            variables={
                "insights_url": normalized_url,
                "pagination_max_pages": request.settings.pagination_max_pages,
                "route_hint": request.route_hint or "",
                "route_kind_hint": request.route_kind_hint or "",
            },
        ),
        prompt_ctx,
    )
    user_prompt = render_prompt(
        PromptRenderRequest(
            schema_version="1.0",
            template=prompt_set.user,
            variables={
                "insights_url": normalized_url,
                "pagination_max_pages": request.settings.pagination_max_pages,
                "route_hint": request.route_hint or "",
                "route_kind_hint": request.route_kind_hint or "",
            },
        ),
        prompt_ctx,
    )
    combined_prompt = (
        "SYSTEM PROMPT\n"
        f"{system_prompt.text}\n\n"
        "USER PROMPT\n"
        f"{user_prompt.text}\n"
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="publisher_inventory_browser_prompt",
            module=logger.name,
            fields={
                "prompt_namespace": request.settings.prompt_namespace,
                "system_prompt_path": prompt_set.system.path,
                "system_prompt_sha256": prompt_set.system.sha256,
                "user_prompt_path": prompt_set.user.path,
                "user_prompt_sha256": prompt_set.user.sha256,
                "rendered_system_prompt": system_prompt.text,
                "rendered_user_prompt": user_prompt.text,
                "task_prompt": combined_prompt,
                "model": request.settings.model,
                "temperature": request.settings.temperature,
                "timeout_seconds": request.settings.timeout_seconds,
                "max_steps": request.settings.max_steps,
            },
        )
    )
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
    llm = browser_use.ChatOpenRouter(
        model=request.settings.model,
        api_key=request.settings.openrouter_api_key,
        http_referer=request.settings.openrouter_http_referer,
        temperature=request.settings.temperature,
        timeout=request.settings.timeout_seconds,
    )
    agent = browser_use.Agent(
        task=combined_prompt,
        llm=llm,
        browser=browser,
        output_model_schema=_BrowserInventoryAgentResult,
    )
    raw_model_response = ""
    final_page_url = ""
    try:
        history = agent.run_sync(max_steps=request.settings.max_steps)
        raw_model_response = str(history.final_result() or "").strip()
        final_page_url = str(getattr(browser, "url", "") or "").strip()
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
        raise AppError(
            code="publisher_inventory_browser_failed",
            message="Browser-render inventory discovery failed",
            cause=exc,
            retryable=True,
            context={"normalized_url": normalized_url},
        ) from exc
    finally:
        _kill_browser(browser, ctx)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="publisher_inventory_browser_response",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "browser_final_url": final_page_url,
                "raw_model_response": raw_model_response,
            },
        )
    )
    if not raw_model_response:
        raise AppError(
            code="publisher_inventory_browser_empty",
            message="Browser-render inventory discovery returned no structured result",
            retryable=True,
            context={"normalized_url": normalized_url},
        )
    try:
        agent_result = _BrowserInventoryAgentResult.model_validate_json(raw_model_response)
    except ValidationError as exc:
        raise AppError(
            code="publisher_inventory_browser_invalid",
            message="Browser-render inventory discovery returned an invalid structured result",
            cause=exc,
            retryable=True,
            context={"normalized_url": normalized_url, "raw_model_response": raw_model_response},
        ) from exc
    _validate_route_kind(agent_result.route_kind)
    pages = [
        PublisherInventoryPage(
            schema_version="1.0",
            page_number=int(page.page_number),
            page_url=str(page.page_url).strip(),
        )
        for page in agent_result.pages
        if int(page.page_number) > 0 and str(page.page_url).strip()
    ]
    candidates = [
        PublisherInventoryRawCandidate(
            schema_version="1.0",
            url=str(candidate.url).strip(),
            title=str(candidate.title).strip(),
            source_page_url=str(candidate.source_page_url).strip(),
            discovered_on_page_number=int(candidate.discovered_on_page_number),
            pdf_url=(
                str(candidate.pdf_url).strip()
                if candidate.pdf_url and str(candidate.pdf_url).strip()
                else None
            ),
            published_at_text=(
                str(candidate.published_at_text).strip()
                if candidate.published_at_text
                and str(candidate.published_at_text).strip()
                else None
            ),
        )
        for candidate in agent_result.candidates
        if str(candidate.url).strip()
        and str(candidate.title).strip()
        and str(candidate.source_page_url).strip()
        and int(candidate.discovered_on_page_number) > 0
    ]
    candidates = _supplement_browser_candidates_with_http(
        request=request,
        ctx=ctx,
        pages=pages,
        browser_candidates=candidates,
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
        route_summary=str(agent_result.route_summary).strip(),
        final_page_url=str(final_page_url or agent_result.final_page_url or normalized_url).strip(),
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


def _supplement_browser_candidates_with_http(
    *,
    request: PublisherInventoryServiceRequest,
    ctx: RunContext,
    pages: list[PublisherInventoryPage],
    browser_candidates: list[PublisherInventoryRawCandidate],
) -> list[PublisherInventoryRawCandidate]:
    browser_candidates_by_page: dict[str, list[PublisherInventoryRawCandidate]] = {}
    for candidate in browser_candidates:
        browser_candidates_by_page.setdefault(candidate.source_page_url, []).append(candidate)

    supplemented_candidates: list[PublisherInventoryRawCandidate] = []
    for page in pages:
        page_candidates = browser_candidates_by_page.pop(page.page_url, [])
        http_candidates = _fetch_page_candidates_for_browser_page(
            request=request,
            ctx=ctx,
            page=page,
        )
        if http_candidates:
            supplemented_candidates.extend(http_candidates)
            continue
        supplemented_candidates.extend(page_candidates)

    for leftover_candidates in browser_candidates_by_page.values():
        supplemented_candidates.extend(leftover_candidates)

    logger.info(
        log_event(
            ctx,
            role="service",
            event="publisher_inventory_browser_http_supplement_complete",
            module=logger.name,
            fields={
                "page_count": len(pages),
                "browser_candidate_count": len(browser_candidates),
                "supplemented_candidate_count": len(supplemented_candidates),
            },
        )
    )
    return supplemented_candidates


def _fetch_page_candidates_for_browser_page(
    *,
    request: PublisherInventoryServiceRequest,
    ctx: RunContext,
    page: PublisherInventoryPage,
) -> list[PublisherInventoryRawCandidate]:
    headers = {"User-Agent": "MarketLensePublisherInventory/1.0"}
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
    if any(marker in lowered_url for marker in _NEGATIVE_PATH_MARKERS):
        return False
    lowered_title = title.casefold()
    if lowered_title in _PAGINATION_LABELS:
        return False
    if absolute_url.lower().endswith(".pdf"):
        return True
    if any(keyword in lowered_url for keyword in _REPORT_KEYWORDS):
        return True
    if any(keyword in lowered_title for keyword in _REPORT_KEYWORDS):
        return True
    if title and len(title) >= 16 and any(char.isdigit() for char in title):
        return True
    return False


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
