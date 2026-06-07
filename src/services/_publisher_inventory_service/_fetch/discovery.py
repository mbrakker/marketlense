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

from .parsing import (
    HTTP_BROWSER_HEADERS,
    _WORDPRESS_AJAX_CONFIG_RE,
    _WORDPRESS_ACTION_RE,
    _SCRIPT_SRC_RE,
    _HTML_TITLE_RE,
    _INVENTORY_HTML_MAX_BYTES,
    _SCRIPT_FETCH_MAX_BYTES,
    _InventoryHtmlParser,
)

from .classification import (
    _candidate_provenance_counts,
)


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
