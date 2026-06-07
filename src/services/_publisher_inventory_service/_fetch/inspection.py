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
    _ASSET_TYPE_TERMS,
    _DOWNLOAD_LANGUAGE_MARKERS,
    _GATED_FORM_MARKERS,
    _DOCUMENT_STRUCTURE_MARKERS,
    _PRINT_LANGUAGE_MARKERS,
    _PURCHASE_MARKERS,
    _EDITORIAL_MARKERS,
    _RELATED_POST_MARKERS,
    _NEWSLETTER_MARKERS,
    _CONTACT_SALES_MARKERS,
    _DEAD_PAGE_MARKERS,
    _LANDING_PAGE_HTML_MAX_BYTES,
    _LandingPageInspectionHtmlParser,
)

from .classification import (
    _contains_any_marker,
    _has_editorial_url_pattern,
    _contains_price_signal,
    _classify_source_surface,
    _classify_verification,
)


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
