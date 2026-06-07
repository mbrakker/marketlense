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
    _EDITORIAL_URL_MARKERS,
    _TRANSIENT_HTTP_STATUS_CODES,
    _PROTECTED_DOCUMENT_HTTP_STATUS_CODES,
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
