from __future__ import annotations

"""Preflight scenario classification for publisher-inventory discovery.

This module owns deterministic URL and source-surface interpretation that runs
before the workflow coordinator chooses direct-detail, HTTP, or browser routes.
It performs no workflow orchestration and exposes helpers through workflow.py for
internal compatibility.
"""

import logging
import re
from urllib.parse import urlsplit

import requests

from src.contracts.http_acquisition import (
    HttpAcquisitionRequest,
    HttpAcquisitionResponsePolicy,
)
from src.contracts.publisher_inventory import (
    PublisherInventoryScenarioSummary,
    PublisherInventoryServiceRequest,
)
from src.contracts.run_context import RunContext
from src.services._http_acquisition import execute_http_acquisition
from src.services._publisher_inventory_service.discovery_activity import (
    _normalize_absolute_url,
)
from src.services._publisher_inventory_service.fetch_service import HTTP_BROWSER_HEADERS
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.publisher_inventory_service")


_PREFLIGHT_HTML_MAX_BYTES = 1024 * 1024

_DIRECT_DETAIL_URL_MARKERS = (
    "/research-library/",
    "/report/",
    "/reports/",
    "/whitepaper/",
    "/whitepapers/",
    "/ebook/",
    "/ebooks/",
    "/study/",
    "/studies/",
    "/survey/",
    "/surveys/",
)

_ARCHIVE_URL_MARKERS = (
    "/insights",
    "/insight",
    "/library",
    "/research",
    "/reports",
    "/resources",
)

_FILTER_HINT_MARKERS = ("filter", "filters", "topic", "type")

_DOWNLOAD_HINT_MARKERS = (
    "download",
    "download the report",
    "download the research brief",
    "get the report",
    "access report",
    "view report",
)

_PREFLIGHT_COLLECTION_ROOT_TOKENS = {
    "all",
    "and",
    "center",
    "centre",
    "ebook",
    "ebooks",
    "guide",
    "guides",
    "hub",
    "insight",
    "insights",
    "library",
    "publication",
    "publications",
    "report",
    "reports",
    "research",
    "resource",
    "resources",
    "study",
    "studies",
    "survey",
    "surveys",
    "whitepaper",
    "whitepapers",
}


def _build_scenario_summary(
    *,
    scenario_class: str,
    source_surface_class: str,
    confidence: float,
    direct_detail_eligible: bool,
    browser_preferred: bool,
    notes: str,
) -> PublisherInventoryScenarioSummary:
    return PublisherInventoryScenarioSummary(
        schema_version="1.0",
        scenario_class=scenario_class,
        source_surface_class=source_surface_class,
        confidence=max(0.0, min(float(confidence), 1.0)),
        direct_detail_eligible=direct_detail_eligible,
        browser_preferred=browser_preferred,
        notes=notes.strip(),
    )


def _classify_preflight_scenario(
    *,
    request: PublisherInventoryServiceRequest,
    normalized_url: str,
    ctx: RunContext,
) -> PublisherInventoryScenarioSummary:
    if normalized_url.casefold().endswith(".pdf"):
        return _build_scenario_summary(
            scenario_class="direct_pdf",
            source_surface_class="direct_detail",
            confidence=1.0,
            direct_detail_eligible=True,
            browser_preferred=False,
            notes="The source URL already points at a PDF asset.",
        )
    path_lower = urlsplit(normalized_url).path.casefold()
    if _looks_like_preflight_filter_route(normalized_url):
        return _build_scenario_summary(
            scenario_class="filtered_archive",
            source_surface_class="archive_feed",
            confidence=0.8,
            direct_detail_eligible=False,
            browser_preferred=True,
            notes="The source URL already encodes report filter state.",
        )
    if path_lower.rstrip("/") in {"/insights", "/research", "/resources", "/reports"}:
        return _build_scenario_summary(
            scenario_class="mixed_content_hub",
            source_surface_class="mixed_content_hub",
            confidence=0.55,
            direct_detail_eligible=False,
            browser_preferred=True,
            notes="The source URL looks like a broad insight or resource hub.",
        )
    try:
        response = execute_http_acquisition(
            request=HttpAcquisitionRequest(
                schema_version="1.0",
                purpose="publisher_inventory_preflight_probe",
                method="GET",
                url=normalized_url,
                headers=dict(HTTP_BROWSER_HEADERS),
                timeout_seconds=min(float(request.settings.http_timeout_seconds), 10.0),
                response_policy=HttpAcquisitionResponsePolicy(
                    schema_version="1.0",
                    require_success_status=False,
                    capture_text=True,
                    capture_content_type_markers=("html", "xml"),
                    max_body_bytes=_PREFLIGHT_HTML_MAX_BYTES,
                    truncate_body=True,
                ),
                error_code="publisher_inventory_preflight_failed",
                error_message="Preflight classification could not fetch the source page",
                allow_redirects=True,
                context_fields={"normalized_url": normalized_url},
            ),
            ctx=ctx,
            requests_module=requests,
        )
    except AppError as exc:
        marker = str(exc).casefold()
        if any(
            term in marker
            for term in (
                "captcha",
                "access denied",
                "just a moment",
                "timed out",
                "temporarily unavailable",
            )
        ):
            return _build_scenario_summary(
                scenario_class="challenge_prone",
                source_surface_class="unknown",
                confidence=0.7,
                direct_detail_eligible=False,
                browser_preferred=True,
                notes=f"Preflight fetch encountered a challenge-prone response: {str(exc).strip()}",
            )
        return _build_scenario_summary(
            scenario_class="unknown",
            source_surface_class="unknown",
            confidence=0.0,
            direct_detail_eligible=False,
            browser_preferred=bool(request.settings.force_browser),
            notes="Preflight classification could not fetch the source page.",
        )
    final_url = (
        _normalize_absolute_url(str(response.final_url or normalized_url))
        or normalized_url
    )
    content_type = str(response.content_type or "").casefold()
    html = str(response.text_body or "")
    lower_html = html.casefold()
    title_start = lower_html.find("<title")
    title_text = ""
    if title_start >= 0:
        title_close = lower_html.find("</title>", title_start)
        title_text = html[title_start:title_close] if title_close > title_start else ""
    combined = " ".join(
        part for part in (final_url, title_text, lower_html[:5000]) if part
    ).casefold()
    final_path = urlsplit(final_url).path.casefold()
    if ".pdf" in final_path or "application/pdf" in content_type:
        return _build_scenario_summary(
            scenario_class="direct_pdf",
            source_surface_class="direct_detail",
            confidence=1.0,
            direct_detail_eligible=True,
            browser_preferred=False,
            notes="Preflight fetch resolved the source URL to a PDF asset.",
        )
    detail_signal = _looks_like_preflight_direct_detail_path(final_url)
    download_signal = any(marker in combined for marker in _DOWNLOAD_HINT_MARKERS)
    archive_signal = any(marker in final_path for marker in _ARCHIVE_URL_MARKERS)
    filter_signal = _looks_like_preflight_filter_route(final_url)
    tab_signal = any(
        label in combined
        for label in ("featured", "reports", "insights", "research", "latest")
    )
    challenge_signal = any(
        marker in combined
        for marker in (
            "access denied",
            "captcha",
            "just a moment",
            "verify you are human",
        )
    )
    if challenge_signal:
        return _build_scenario_summary(
            scenario_class="challenge_prone",
            source_surface_class="unknown",
            confidence=0.8,
            direct_detail_eligible=False,
            browser_preferred=True,
            notes="Preflight fetch saw anti-bot or challenge markers in the response.",
        )
    if detail_signal and not filter_signal:
        return _build_scenario_summary(
            scenario_class="direct_detail_html",
            source_surface_class="direct_detail",
            confidence=0.9 if download_signal else 0.75,
            direct_detail_eligible=True,
            browser_preferred=False,
            notes=(
                "Preflight fetch found a direct-detail HTML route with explicit download language."
                if download_signal
                else "Preflight fetch found a deep direct-detail HTML route without archive-style filter state."
            ),
        )
    if filter_signal and archive_signal:
        return _build_scenario_summary(
            scenario_class="filtered_archive",
            source_surface_class="archive_feed",
            confidence=0.85,
            direct_detail_eligible=False,
            browser_preferred=True,
            notes="Preflight fetch found archive-style content with explicit filter state.",
        )
    if archive_signal and tab_signal:
        return _build_scenario_summary(
            scenario_class="tabbed_archive",
            source_surface_class="archive_feed",
            confidence=0.65,
            direct_detail_eligible=False,
            browser_preferred=True,
            notes="Preflight fetch suggests a tabbed report archive.",
        )
    if archive_signal:
        return _build_scenario_summary(
            scenario_class="mixed_content_hub",
            source_surface_class="mixed_content_hub",
            confidence=0.55,
            direct_detail_eligible=False,
            browser_preferred=True,
            notes="Preflight fetch suggests a broad insight hub rather than a single detail page.",
        )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="publisher_inventory_preflight_classification_defaulted",
            module=logger.name,
            fields={"normalized_url": normalized_url, "final_url": final_url},
        )
    )
    return _build_scenario_summary(
        scenario_class="unknown",
        source_surface_class="unknown",
        confidence=0.25,
        direct_detail_eligible=False,
        browser_preferred=bool(request.settings.force_browser),
        notes="Preflight fetch found no stable scenario signature.",
    )


def _looks_like_preflight_filter_route(url: str) -> bool:
    normalized_url = str(url or "").strip().casefold()
    if not normalized_url:
        return False
    return (
        "filters=" in normalized_url
        or "filter=" in normalized_url
        or "types(" in normalized_url
        or "type=" in normalized_url
        or "topic=" in normalized_url
        or "/type/" in normalized_url
        or "/topic/" in normalized_url
    )


def _looks_like_preflight_direct_detail_path(url: str) -> bool:
    normalized_url = str(url or "").strip().casefold()
    if not normalized_url:
        return False
    path = urlsplit(normalized_url).path
    if not any(marker in path for marker in _DIRECT_DETAIL_URL_MARKERS):
        return False
    segments = [segment for segment in path.split("/") if segment]
    if len(segments) < 2:
        return False
    leaf = segments[-1].rsplit(".", 1)[0]
    if not leaf or leaf.isdigit():
        return False
    leaf_tokens = [token for token in re.findall(r"[a-z0-9]+", leaf) if token]
    if not leaf_tokens:
        return False
    if len(leaf_tokens) == 1 and leaf_tokens[0] in _PREFLIGHT_COLLECTION_ROOT_TOKENS:
        return False
    return not all(token in _PREFLIGHT_COLLECTION_ROOT_TOKENS for token in leaf_tokens)


__all__ = [name for name in globals() if not name.startswith("__")]
