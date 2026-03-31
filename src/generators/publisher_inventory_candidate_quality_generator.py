"""Deterministic landing-page qualification for already screened inventory candidates."""

from __future__ import annotations

import logging
import re

from src.contracts.publisher_inventory import (
    PublisherInventoryCandidateQualityDecision,
    PublisherInventoryCandidateQualityRequest,
    PublisherInventoryCandidateQualityResponse,
    PublisherInventoryLandingPageInspectionItem,
    PublisherInventoryLandingPageInspectionRequest,
    PublisherInventoryLandingPageInspectionResponse,
    PublisherInventoryLandingPageObservation,
    PublisherInventoryQualifiedCandidateItem,
)
from src.services.publisher_inventory_service import (
    inspect_publisher_inventory_landing_pages,
)
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger(
    "market_lense.publisher_inventory_candidate_quality_generator"
)

_GENERIC_TITLE_TOKENS = {
    "",
    "read now",
    "download now",
    "learn more",
    "read report",
    "download report",
    "view report",
    "report",
    "reports",
    "whitepaper",
    "white paper",
    "ebook",
    "page not found",
}
_LEGAL_URL_MARKERS = (
    "/legal/",
    "/privacy",
    "/terms",
    "/cookie",
    "/compliance",
    "/gdpr",
)
_LEGAL_TITLE_MARKERS = (
    "transparency report",
    "privacy policy",
    "cookie policy",
    "terms of service",
    "terms and conditions",
    "acceptable use policy",
)
_REGULATORY_TITLE_MARKERS = (
    "pillar 3",
    "disclosure",
    "disclosures",
    "proxy statement",
    "prospectus",
    "financial statements",
)
_CASE_STUDY_URL_MARKERS = (
    "/case-study",
    "/case-studies/",
    "/customer-story",
    "/customer-stories/",
    "/success-story",
    "/success-stories/",
)
_CASE_STUDY_TITLE_MARKERS = (
    "case study",
    "customer story",
    "success story",
)
_ANNOUNCEMENT_TITLE_MARKERS = (
    "according to new research",
    "finds new research",
    "launches new research",
    "new research from",
    "research finds",
    "study finds",
)
_SECTION_TITLE_MARKERS = {
    "about the report",
    "conclusion",
    "contents",
    "executive summary",
    "foreword",
    "introduction",
    "methodology",
    "table of contents",
}
_INFORMATIONAL_ARTICLE_PREFIXES = (
    "how to ",
    "what is ",
    "why ",
    "how can ",
    "how do ",
    "how does ",
    "what can ",
)
_REPORT_STYLE_TITLE_MARKERS = (
    "report",
    "benchmark",
    "study",
    "research",
    "survey",
    "outlook",
    "playbook",
    "blueprint",
    "whitepaper",
    "white paper",
    "ebook",
    "infographic",
    "snapshot",
)


def qualify_publisher_inventory_candidates(
    request: PublisherInventoryCandidateQualityRequest,
    ctx,
    *,
    inspection_client=inspect_publisher_inventory_landing_pages,
) -> PublisherInventoryCandidateQualityResponse:
    candidates = list(request.candidates)
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="publisher_inventory_candidate_quality_start",
            module=logger.name,
            fields={
                "publisher_name": request.publisher_name,
                "insights_url": request.insights_url,
                "candidate_count": len(candidates),
                "candidate_quality_check_enabled": request.settings.candidate_quality_check_enabled,
                "candidate_quality_check_timeout_seconds": request.settings.candidate_quality_check_timeout_seconds,
                "candidate_quality_check_max_workers": request.settings.candidate_quality_check_max_workers,
            },
        )
    )
    if not candidates:
        return PublisherInventoryCandidateQualityResponse(
            schema_version="1.0",
            approved_items=[],
            rejected_items=[],
            decisions=[],
        )
    if not request.settings.candidate_quality_check_enabled:
        approved_items = [
            PublisherInventoryQualifiedCandidateItem(
                schema_version="1.0",
                canonical_url=item.canonical_url,
                title=item.title,
                discovered_on_page_number=item.discovered_on_page_number,
                source_page_url=item.source_page_url,
            )
            for item in candidates
        ]
        decisions = [
            PublisherInventoryCandidateQualityDecision(
                schema_version="1.0",
                canonical_url=item.canonical_url,
                accepted=True,
                reason="candidate_quality_check_disabled",
                resolved_title=item.title,
            )
            for item in candidates
        ]
        response = PublisherInventoryCandidateQualityResponse(
            schema_version="1.0",
            approved_items=approved_items,
            rejected_items=[],
            decisions=decisions,
        )
        logger.info(
            log_event(
                ctx,
                role="generator",
                event="publisher_inventory_candidate_quality_complete",
                module=logger.name,
                fields={
                    "publisher_name": request.publisher_name,
                    "candidate_count": len(candidates),
                    "approved_count": len(response.approved_items),
                    "rejected_count": len(response.rejected_items),
                    "quality_check_skipped": True,
                },
            )
        )
        return response

    inspection_response = inspection_client(
        PublisherInventoryLandingPageInspectionRequest(
            schema_version="1.0",
            publisher_name=request.publisher_name,
            items=[
                PublisherInventoryLandingPageInspectionItem(
                    schema_version="1.0",
                    canonical_url=item.canonical_url,
                    title=item.title,
                    discovered_on_page_number=item.discovered_on_page_number,
                    source_page_url=item.source_page_url,
                )
                for item in candidates
            ],
            timeout_seconds=request.settings.candidate_quality_check_timeout_seconds,
            max_workers=request.settings.candidate_quality_check_max_workers,
        ),
        ctx,
    )
    observation_by_url = {
        observation.canonical_url: observation
        for observation in inspection_response.observations
    }
    missing_urls = [
        item.canonical_url
        for item in candidates
        if item.canonical_url not in observation_by_url
    ]
    if missing_urls:
        raise AppError(
            code="publisher_inventory_candidate_quality_incomplete",
            message="Landing-page quality checks did not return an observation for every candidate",
            retryable=False,
            severity="error",
            context={"missing_urls": missing_urls},
        )
    approved_items: list[PublisherInventoryQualifiedCandidateItem] = []
    rejected_items: list[PublisherInventoryQualifiedCandidateItem] = []
    decisions: list[PublisherInventoryCandidateQualityDecision] = []
    for item in candidates:
        observation = observation_by_url[item.canonical_url]
        resolved_title = _resolve_candidate_title(item.title, observation)
        accepted, reason = _qualify_observation(observation)
        qualified_item = PublisherInventoryQualifiedCandidateItem(
            schema_version="1.0",
            canonical_url=item.canonical_url,
            title=resolved_title,
            discovered_on_page_number=item.discovered_on_page_number,
            source_page_url=item.source_page_url,
        )
        decisions.append(
            PublisherInventoryCandidateQualityDecision(
                schema_version="1.0",
                canonical_url=item.canonical_url,
                accepted=accepted,
                reason=reason,
                resolved_title=resolved_title,
            )
        )
        if accepted:
            approved_items.append(qualified_item)
        else:
            rejected_items.append(qualified_item)
    response = PublisherInventoryCandidateQualityResponse(
        schema_version="1.0",
        approved_items=approved_items,
        rejected_items=rejected_items,
        decisions=decisions,
    )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="publisher_inventory_candidate_quality_complete",
            module=logger.name,
            fields={
                "publisher_name": request.publisher_name,
                "candidate_count": len(candidates),
                "approved_count": len(response.approved_items),
                "rejected_count": len(response.rejected_items),
                "decisions": [
                    {
                        "canonical_url": decision.canonical_url,
                        "accepted": decision.accepted,
                        "reason": decision.reason,
                        "resolved_title": decision.resolved_title,
                    }
                    for decision in response.decisions
                ],
            },
        )
    )
    return response


def _qualify_observation(
    observation: PublisherInventoryLandingPageObservation,
) -> tuple[bool, str]:
    resolved_title_lower = _normalize_title(
        observation.h1_title or observation.og_title or observation.final_title or observation.source_title
    ).casefold()
    final_url_lower = str(observation.final_url or "").strip().casefold()
    strong_distribution_signal = (
        observation.is_pdf
        or observation.has_download_language
        or observation.has_gated_form
        or observation.has_price_or_purchase
    )
    structured_document_signal = (
        observation.has_document_structure or observation.has_print_language
    )
    editorial_surface_signal = (
        observation.has_editorial_url_pattern or observation.has_related_posts
    )
    editorial_context_signal = editorial_surface_signal or observation.has_editorial_markers
    report_archive_path_signal = "/reports/" in final_url_lower or "/report/" in final_url_lower
    report_title_signal = _contains_report_style_title_marker(resolved_title_lower)
    if observation.fetch_error or observation.has_dead_page_marker:
        return False, "dead_or_unreachable_landing_page"
    if any(marker in final_url_lower for marker in _LEGAL_URL_MARKERS) or any(
        marker in resolved_title_lower for marker in _LEGAL_TITLE_MARKERS
    ):
        return False, "legal_or_compliance_page"
    if any(marker in final_url_lower for marker in _CASE_STUDY_URL_MARKERS) or any(
        marker in resolved_title_lower for marker in _CASE_STUDY_TITLE_MARKERS
    ):
        return False, "case_study_or_customer_story_page"
    if any(marker in resolved_title_lower for marker in _ANNOUNCEMENT_TITLE_MARKERS) and not (
        observation.has_gated_form or observation.has_price_or_purchase
    ):
        return False, "research_announcement_page"
    if any(marker in resolved_title_lower for marker in _REGULATORY_TITLE_MARKERS):
        return False, "regulatory_or_disclosure_document"
    if observation.is_pdf:
        return True, "direct_document_asset"
    if _looks_like_report_section_title(resolved_title_lower):
        return False, "report_section_page"
    if editorial_surface_signal and not report_archive_path_signal:
        return False, "editorial_article_page"
    if _looks_like_informational_article_title(resolved_title_lower) and not (
        observation.has_gated_form or observation.has_price_or_purchase
    ):
        return False, "informational_article_page"
    if (
        (report_archive_path_signal or report_title_signal)
        and (structured_document_signal or observation.has_asset_type_term)
        and not observation.has_dead_page_marker
    ):
        return True, "printable_report_page"
    if (
        observation.has_price_or_purchase
        and observation.has_asset_type_term
        and not observation.has_editorial_url_pattern
    ):
        return True, "paid_or_publication_report_page"
    if observation.has_gated_form and (
        observation.has_asset_type_term or observation.has_document_structure
    ):
        return True, "gated_report_asset"
    if observation.has_download_language and (
        observation.has_asset_type_term or observation.has_document_structure
    ):
        return True, "downloadable_report_asset"
    if observation.has_print_language and (
        observation.has_asset_type_term or observation.has_document_structure
    ) and not editorial_surface_signal:
        return True, "printable_report_page"
    if (
        structured_document_signal
        and (observation.has_asset_type_term or report_title_signal or report_archive_path_signal)
        and not editorial_surface_signal
    ):
        return True, "report_like_document_page"
    if editorial_context_signal and not strong_distribution_signal:
        return False, "editorial_article_page"
    if (
        observation.has_newsletter_cta or observation.has_contact_sales_cta
    ) and not (strong_distribution_signal or structured_document_signal):
        return False, "marketing_cta_without_report_asset"
    return False, "insufficient_report_signals"


def _resolve_candidate_title(
    source_title: str,
    observation: PublisherInventoryLandingPageObservation,
) -> str:
    for candidate_title in (
        observation.h1_title,
        observation.og_title,
        observation.final_title,
        source_title,
        observation.final_url.rsplit("/", 1)[-1].rsplit(".", 1)[0].replace("-", " "),
    ):
        normalized = _normalize_title(candidate_title)
        if normalized:
            return normalized
    return source_title.strip() or observation.canonical_url


def _normalize_title(value: str) -> str:
    normalized = " ".join(str(value or "").split()).strip()
    lowered = normalized.casefold()
    if not normalized or lowered in _GENERIC_TITLE_TOKENS:
        return ""
    if lowered.startswith(("read now ", "learn more ", "download report ", "download now ")):
        normalized = normalized.split(" ", 2)[-1].strip()
        lowered = normalized.casefold()
    if lowered in _GENERIC_TITLE_TOKENS:
        return ""
    return normalized


def _looks_like_informational_article_title(lowered_title: str) -> bool:
    title = str(lowered_title or "").strip().casefold()
    if not title:
        return False
    if not title.startswith(_INFORMATIONAL_ARTICLE_PREFIXES):
        return False
    return not _contains_report_style_title_marker(title)


def _contains_report_style_title_marker(title: str) -> bool:
    normalized_title = str(title or "").strip().casefold()
    if not normalized_title:
        return False
    words = {
        token
        for token in re.findall(r"[a-z0-9]+", normalized_title)
        if token
    }
    for marker in _REPORT_STYLE_TITLE_MARKERS:
        normalized_marker = str(marker or "").strip().casefold()
        if not normalized_marker:
            continue
        if " " in normalized_marker:
            if normalized_marker in normalized_title:
                return True
            continue
        if normalized_marker in words:
            return True
    return False


def _looks_like_report_section_title(title: str) -> bool:
    normalized_title = str(title or "").strip().casefold()
    if not normalized_title:
        return False
    if normalized_title in _SECTION_TITLE_MARKERS:
        return True
    return bool(re.fullmatch(r"(chapter|part|section)\s+\d+[a-z]?", normalized_title))
