from __future__ import annotations

"""Supplement operations for publisher-inventory browser traversal."""

import logging

import requests
from src.contracts.http_acquisition import (
    HttpAcquisitionRequest,
    HttpAcquisitionResponsePolicy,
)
from src.contracts.publisher_inventory import (
    PublisherInventoryPage,
    PublisherInventoryRawCandidate,
    PublisherInventoryServiceRequest,
)
from src.contracts.run_context import RunContext
from src.services._http_acquisition import execute_http_acquisition
from src.services._publisher_inventory_service.discovery_activity import (
    _extract_component_link_anchors,
    _extract_candidates_from_html,
    _normalize_absolute_url,
    _normalize_absolute_url as _validate_and_normalize_url,
)
from src.services._publisher_inventory_service.fetch_service import (
    HTTP_BROWSER_HEADERS,
    _InventoryHtmlParser,
)
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.publisher_inventory_service")

_HTTP_SUPPLEMENT_HTML_MAX_BYTES = 2 * 1024 * 1024


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
