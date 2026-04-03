"""Deterministic landing-page qualification for already screened inventory candidates."""

from __future__ import annotations

import logging
import re
from urllib.parse import urlsplit

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
    "key takeaways",
    "takeaways",
    "here",
    "online here",
    "white papers",
    "whitepapers",
    "research",
    "studies",
    "guides",
    "playbooks",
    "benchmarks",
    "surveys",
    "outlooks",
    "forecasts",
    "resources",
}
_LEGAL_URL_MARKERS = (
    "/legal/",
    "/laws-and-regulations/",
    "/privacy",
    "/practice-areas/",
    "/terms",
    "/cookie",
    "/compliance",
    "/gdpr",
)
_SELF_SERVICE_URL_MARKERS = (
    "/help/",
    "/registration/",
    "/sign-in",
    "/signin",
    "/sign-up",
    "/signup",
    "/get-started",
)
_LEGAL_TITLE_MARKERS = (
    "privacy policy",
    "cookie policy",
    "terms of service",
    "terms and conditions",
    "acceptable use policy",
    "binding corporate rules",
    "bcr summary",
)
_REGULATORY_TITLE_MARKERS = (
    "pillar 3",
    "disclosure",
    "disclosures",
    "proxy statement",
    "prospectus",
    "financial statements",
)
_CORPORATE_POLICY_TITLE_MARKERS = (
    "modern slavery statement",
    "slavery statement",
    "tax strategy",
    "gender pay gap report",
    "gender pay report",
    "gender equality index",
    "equality index",
    "index de l egalite",
    "index de l égalité",
    "egalite femmes hommes",
    "égalité femmes-hommes",
    "supplier code of conduct",
    "supplier code",
    "accessibility statement",
    "whistleblowing policy",
)
_SURVEY_PLATFORM_HOST_MARKERS = (
    "surveymonkey.com",
    "qualtrics.com",
    "surveygizmo.com",
    "alchemer.com",
    "typeform.com",
    "jotform.com",
)
_CASE_STUDY_URL_MARKERS = (
    "/case-study",
    "/case-studies/",
    "/case-studies",
    "/customer-story",
    "/customer-stories/",
    "/customer-stories",
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
_SECTION_URL_SLUG_MARKERS = (
    "about",
    "conclusion",
    "contents",
    "executive-summary",
    "foreword",
    "innovation",
    "introduction",
    "methodology",
    "path-to-market",
    "strategic-implications",
    "table-of-contents",
)
_INFORMATIONAL_ARTICLE_PREFIXES = (
    "how long ",
    "how to ",
    "what is ",
    "what to ",
    "why ",
    "how can ",
    "how do ",
    "how does ",
    "what can ",
)
_EDITORIAL_SECTION_URL_MARKERS = (
    "/behind-the-scenes/",
    "/company-insights/",
    "/market-insights/",
    "/market-outlook/",
    "/markets-explained/",
)
_BOT_CHALLENGE_MARKERS = (
    "access denied",
    "attention required",
    "captcha",
    "checking your browser",
    "just a moment",
    "security checkpoint",
    "verify you are human",
)
_TRANSIENT_FETCH_ERROR_MARKERS = (
    "connection aborted",
    "connection reset",
    "read timed out",
    "remote end closed connection",
    "temporarily unavailable",
    "timed out",
)
_REPORT_STYLE_TITLE_MARKERS = (
    "barometer",
    "report",
    "reports",
    "benchmark",
    "benchmarks",
    "study",
    "studies",
    "research",
    "survey",
    "surveys",
    "outlook",
    "outlooks",
    "playbook",
    "playbooks",
    "blueprint",
    "whitepaper",
    "white paper",
    "guide",
    "guides",
    "ebook",
    "ebooks",
    "fact sheet",
    "fact sheets",
    "forecast",
    "forecasts",
    "atlas",
    "buyers guide",
    "buyer's guide",
    "infographic",
    "snapshot",
    "trend",
    "trends",
)
_SPECIFIC_REPORT_STYLE_TITLE_MARKERS = (
    "annual report",
    "barometer",
    "benchmark",
    "benchmarks",
    "buyers guide",
    "buyer's guide",
    "ebook",
    "ebooks",
    "forecast",
    "forecasts",
    "guide",
    "guides",
    "index",
    "outlook",
    "outlooks",
    "playbook",
    "playbooks",
    "snapshot",
    "study",
    "studies",
    "survey",
    "surveys",
    "trend",
    "trends",
    "fact sheet",
    "fact sheets",
    "atlas",
    "transparency report",
    "whitepaper",
    "white paper",
)
_REPORT_URL_PATH_MARKERS = (
    "/barometer",
    "/buyers-guide",
    "/buyers-guides/",
    "/data-report",
    "/data-reports/",
    "/fact-sheet",
    "/fact-sheets/",
    "/guide",
    "/guides/",
    "/industry-report",
    "/industry-reports/",
    "/lp/product-fact-sheet/",
    "/lp/report/",
    "/report/",
    "/reports/",
    "/report_pages/",
    "/report-hub/",
    "/special-reports/",
    "/whitepaper",
    "/whitepapers/",
    "/white-paper",
    "/ebook",
    "/ebooks/",
    "/forecast",
    "/forecasts/",
    "/study",
    "/studies/",
    "/survey",
    "/surveys/",
    "/trend",
    "/trends/",
    "/research/",
)
_REPORT_COLLECTION_URL_SEGMENTS = {
    "benchmark",
    "benchmarks",
    "ebook",
    "ebooks",
    "fact-sheet",
    "fact-sheets",
    "guide",
    "guides",
    "playbook",
    "playbooks",
    "report",
    "reports",
    "research",
    "study",
    "studies",
    "survey",
    "surveys",
    "trend",
    "trends",
    "whitepaper",
    "whitepapers",
    "white-paper",
}
_SERVICE_OR_MEMBERSHIP_LEAF_MARKERS = {
    "access",
    "council",
    "membership",
    "planned",
    "reprints",
    "subscription",
    "system",
}
_SERVICE_OR_MEMBERSHIP_PATH_MARKERS = (
    "/become-a-client",
    "/capabilities/",
    "/events/",
    "/research-center",
    "/research-centers/",
)
_SERVICE_OR_MEMBERSHIP_TITLE_MARKERS = (
    "analyst relations council",
    "membership",
    "planned research",
    "quarterly trends hub",
    "request a call back",
    "reprints",
    "research center",
    "resource center",
    "subscription",
    "thought leadership",
)
_HARD_NON_ASSET_PATH_MARKERS = (
    "/become-a-client",
    "/capabilities/",
    "/events/",
    "/research-center",
    "/research-centers/",
)
_REPORT_COLLECTION_ROOT_WORDS = {
    "all",
    "and",
    "asset",
    "assets",
    "benchmark",
    "benchmarks",
    "center",
    "centre",
    "ebook",
    "ebooks",
    "guide",
    "guides",
    "hub",
    "index",
    "library",
    "paper",
    "papers",
    "playbook",
    "playbooks",
    "quarterly",
    "report",
    "reports",
    "research",
    "resource",
    "resources",
    "study",
    "studies",
    "survey",
    "surveys",
    "thought",
    "trend",
    "trends",
    "white",
    "whitepaper",
    "whitepapers",
}
_TRANSIENT_HTTP_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}
_PROTECTED_DOCUMENT_HTTP_STATUS_CODES = {401, 403}
_DOCUMENT_URL_SUFFIXES = (".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx")
_DATED_EDITORIAL_URL_RE = re.compile(r"/20\d{2}/\d{1,2}/\d{1,2}/")
_LEAD_CAPTURE_PATH_RE = re.compile(r"^/l/\d+/")


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
        accepted, reason = _qualify_observation(
            observation,
            source_page_url=item.source_page_url,
        )
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
    *,
    source_page_url: str,
) -> tuple[bool, str]:
    resolved_title_lower = _normalize_title(
        observation.h1_title or observation.og_title or observation.final_title or observation.source_title
    ).casefold()
    final_url_lower = str(observation.final_url or "").strip().casefold()
    source_title_lower = _normalize_title(observation.source_title).casefold()
    strong_distribution_signal = (
        observation.is_pdf
        or observation.has_download_language
        or observation.has_gated_form
    )
    structured_document_signal = (
        observation.has_document_structure or observation.has_print_language
    )
    editorial_section_signal = _looks_like_editorial_section_url(final_url_lower) or _looks_like_editorial_section_url(
        observation.canonical_url
    )
    editorial_surface_signal = (
        observation.has_editorial_url_pattern
        or observation.has_related_posts
        or editorial_section_signal
    )
    editorial_context_signal = editorial_surface_signal or observation.has_editorial_markers
    report_archive_path_signal = _has_report_style_url_path(final_url_lower)
    report_slug_signal = _has_report_style_url_slug(final_url_lower)
    report_title_signal = _contains_report_style_title_marker(resolved_title_lower)
    specific_report_title_signal = _contains_specific_report_style_title_marker(
        resolved_title_lower
    )
    source_title_report_signal = _contains_report_style_title_marker(source_title_lower)
    source_report_signal = (
        source_title_report_signal
        or _has_report_style_url_path(observation.canonical_url)
        or _has_report_style_url_slug(observation.canonical_url)
        or _has_report_style_url_path(source_page_url)
        or _has_report_style_url_slug(source_page_url)
    )
    bot_protected_report_signal = (
        report_title_signal
        or source_title_report_signal
        or _has_report_style_url_path(observation.canonical_url)
        or _has_report_style_url_slug(observation.canonical_url)
    )
    newsletter_source_signal = _looks_like_newsletter_source_url(source_page_url)
    if (
        _looks_like_bot_challenge_page(observation)
        and observation.has_dead_page_marker
        and _looks_like_article_label_title(source_title_lower)
    ):
        return False, "bot_protected_editorial_page"
    if _looks_like_bot_challenge_page(observation) and source_report_signal:
        if _looks_like_article_label_title(source_title_lower) and not report_title_signal:
            return False, "bot_protected_editorial_page"
        if bot_protected_report_signal:
            return True, "bot_protected_report_asset"
        return False, "bot_protected_editorial_page"
    if (
        _looks_like_transient_fetch_failure(observation.fetch_error)
        or _looks_like_transient_http_status(observation.http_status_code)
    ) and source_report_signal:
        return True, "transient_fetch_report_asset"
    if (
        _looks_like_protected_document_status(observation.http_status_code)
        and source_report_signal
    ):
        if observation.has_editorial_url_pattern and not (
            report_archive_path_signal or specific_report_title_signal
        ):
            return False, "protected_editorial_page"
        if _looks_like_document_url(observation.final_url or observation.canonical_url):
            return True, "protected_document_asset"
        if (
            observation.has_asset_type_term
            or report_archive_path_signal
            or report_slug_signal
            or specific_report_title_signal
        ):
            return True, "protected_report_asset"
    if (
        _looks_like_document_url(observation.final_url or observation.canonical_url)
        and source_report_signal
        and (observation.fetch_error or observation.has_dead_page_marker)
    ):
        return True, "unreachable_document_asset"
    if observation.fetch_error or observation.has_dead_page_marker:
        return False, "dead_or_unreachable_landing_page"
    if _looks_like_self_service_page_url(final_url_lower) and not (
        observation.is_pdf
        or observation.has_download_language
        or observation.has_gated_form
        or observation.has_document_structure
    ):
        return False, "self_service_or_signup_page"
    if any(marker in final_url_lower for marker in _LEGAL_URL_MARKERS) or any(
        marker in resolved_title_lower for marker in _LEGAL_TITLE_MARKERS
    ):
        return False, "legal_or_compliance_page"
    if _looks_like_report_section_url(final_url_lower):
        return False, "report_section_page"
    if _looks_like_hard_non_asset_route(final_url_lower):
        return False, "service_or_membership_page"
    if _looks_like_research_hub_page(
        final_url_lower=final_url_lower,
        resolved_title_lower=resolved_title_lower,
    ):
        return False, "service_or_membership_page"
    if (
        _looks_like_strict_collection_root_url(final_url_lower)
        or _looks_like_strict_collection_root_url(observation.canonical_url)
        or (
            _looks_like_report_collection_root_url(final_url_lower)
            or _looks_like_report_collection_root_url(observation.canonical_url)
        )
        or (
            not resolved_title_lower
            and report_archive_path_signal
            and not report_slug_signal
        )
    ):
        if (
            _looks_like_strict_collection_root_url(final_url_lower)
            or _looks_like_strict_collection_root_url(observation.canonical_url)
            or (not specific_report_title_signal and not observation.is_pdf)
        ):
            return False, "generic_asset_hub_page"
    if (
        (
            _looks_like_report_collection_bucket_url(final_url_lower)
            or _looks_like_report_collection_bucket_url(observation.canonical_url)
        )
        and not specific_report_title_signal
        and not observation.is_pdf
    ):
        return False, "generic_asset_hub_page"
    if _looks_like_service_or_membership_page(
        final_url_lower=final_url_lower,
        resolved_title_lower=resolved_title_lower,
    ) and not specific_report_title_signal:
        return False, "service_or_membership_page"
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
    if any(marker in resolved_title_lower for marker in _CORPORATE_POLICY_TITLE_MARKERS):
        return False, "corporate_policy_document"
    if _looks_like_survey_platform_page(observation.final_url) and not (
        observation.has_download_language or observation.has_document_structure
    ):
        return False, "survey_or_questionnaire_page"
    if observation.is_pdf:
        return True, "direct_document_asset"
    if _looks_like_report_section_title(resolved_title_lower):
        return False, "report_section_page"
    if newsletter_source_signal and not (
        report_title_signal
        or report_archive_path_signal
        or observation.is_pdf
        or observation.has_gated_form
        or observation.has_document_structure
    ):
        return False, "newsletter_article_page"
    if (
        editorial_surface_signal
        and strong_distribution_signal
        and structured_document_signal
        and (
            report_archive_path_signal
            or specific_report_title_signal
            or (
                observation.is_pdf
                and (report_title_signal or source_report_signal)
            )
        )
        and not _looks_like_dated_editorial_url(final_url_lower)
    ):
        if observation.has_gated_form:
            return True, "gated_report_asset"
        if observation.has_download_language:
            return True, "downloadable_report_asset"
        if observation.has_print_language:
            return True, "printable_report_page"
    if observation.has_editorial_url_pattern and (
        _looks_like_dated_editorial_url(final_url_lower)
        or not (report_archive_path_signal or specific_report_title_signal)
    ):
        return False, "editorial_article_page"
    if _looks_like_informational_article_title(resolved_title_lower) and not (
        observation.has_gated_form or observation.has_price_or_purchase
    ) and not (
        source_report_signal
        and (report_slug_signal or specific_report_title_signal or report_archive_path_signal)
    ):
        return False, "informational_article_page"
    if (
        editorial_context_signal
        and not strong_distribution_signal
        and not report_title_signal
        and not report_archive_path_signal
    ):
        return False, "editorial_article_page"
    if (
        (report_archive_path_signal or report_slug_signal or report_title_signal)
        and (structured_document_signal or observation.has_asset_type_term)
        and not observation.has_dead_page_marker
        and not (
            editorial_context_signal
            and not structured_document_signal
            and not strong_distribution_signal
        )
    ):
        return True, "printable_report_page"
    if (
        observation.has_price_or_purchase
        and observation.has_asset_type_term
        and not editorial_context_signal
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
        (report_slug_signal or specific_report_title_signal)
        and source_report_signal
        and not editorial_context_signal
        and not _looks_like_report_collection_bucket_url(final_url_lower)
    ):
        return True, "report_detail_landing_page"
    if (
        structured_document_signal
        and (
            observation.has_asset_type_term
            or report_title_signal
            or report_archive_path_signal
            or report_slug_signal
        )
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


def _looks_like_dated_editorial_url(url: str) -> bool:
    return bool(_DATED_EDITORIAL_URL_RE.search(str(url or "").strip().casefold()))


def _looks_like_editorial_section_url(url: str) -> bool:
    lowered = str(url or "").strip().casefold()
    return any(marker in lowered for marker in _EDITORIAL_SECTION_URL_MARKERS)


def _resolve_candidate_title(
    source_title: str,
    observation: PublisherInventoryLandingPageObservation,
) -> str:
    fallback_title = observation.final_url.rsplit("/", 1)[-1].rsplit(".", 1)[0].replace("-", " ")
    for candidate_title in (
        observation.h1_title,
        observation.og_title,
        observation.final_title,
        source_title,
        fallback_title,
    ):
        if _looks_like_bot_challenge_text(candidate_title):
            continue
        normalized = _normalize_title(candidate_title)
        if normalized:
            return normalized
    return _normalize_title(fallback_title) or observation.canonical_url


def _normalize_title(value: str) -> str:
    normalized = " ".join(str(value or "").split()).strip()
    lowered = normalized.casefold()
    if not normalized or lowered in _GENERIC_TITLE_TOKENS:
        return ""
    if lowered.startswith(("read now ", "learn more ", "download report ", "download now ")):
        normalized = normalized.split(" ", 2)[-1].strip()
        lowered = normalized.casefold()
    normalized = re.sub(
        r"\s*(?:pdf|docx?|xlsx?|pptx?)\s*\d+(?:\.\d+)?\s*(?:kb|mb|gb)\s*$",
        "",
        normalized,
        flags=re.IGNORECASE,
    ).rstrip()
    lowered = normalized.casefold()
    normalized = normalized.rstrip(". ")
    if normalized.endswith("..."):
        normalized = normalized[:-3].rstrip()
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


def _looks_like_article_label_title(lowered_title: str) -> bool:
    title = str(lowered_title or "").strip().casefold()
    if not title:
        return False
    return title.startswith("article ")


def _contains_report_style_title_marker(title: str) -> bool:
    normalized_title = str(title or "").strip().casefold()
    if not normalized_title:
        return False
    words = {
        _normalize_title_word(token)
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
        if _normalize_title_word(normalized_marker) in words:
            return True
    return False


def _looks_like_bot_challenge_page(
    observation: PublisherInventoryLandingPageObservation,
) -> bool:
    return any(
        _looks_like_bot_challenge_text(value)
        for value in (
            observation.final_title,
            observation.h1_title,
            observation.og_title,
            observation.fetch_error,
            observation.final_url,
        )
    )


def _looks_like_bot_challenge_text(value: str) -> bool:
    normalized_value = str(value or "").strip().casefold()
    if not normalized_value:
        return False
    return any(marker in normalized_value for marker in _BOT_CHALLENGE_MARKERS)


def _looks_like_transient_fetch_failure(value: str) -> bool:
    normalized_value = str(value or "").strip().casefold()
    if not normalized_value:
        return False
    return any(marker in normalized_value for marker in _TRANSIENT_FETCH_ERROR_MARKERS)


def _looks_like_transient_http_status(status_code: int | None) -> bool:
    return int(status_code or 0) in _TRANSIENT_HTTP_STATUS_CODES


def _looks_like_protected_document_status(status_code: int | None) -> bool:
    return int(status_code or 0) in _PROTECTED_DOCUMENT_HTTP_STATUS_CODES


def _looks_like_document_url(url: str) -> bool:
    normalized_url = str(url or "").strip().casefold()
    if not normalized_url:
        return False
    return any(normalized_url.endswith(suffix) for suffix in _DOCUMENT_URL_SUFFIXES)


def _has_report_style_url_slug(url: str) -> bool:
    path = urlsplit(str(url or "").strip().casefold()).path
    if not path:
        return False
    slug = path.rsplit("/", 1)[-1].rsplit(".", 1)[0].replace("-", " ")
    return _contains_report_style_title_marker(slug)


def _contains_specific_report_style_title_marker(title: str) -> bool:
    normalized_title = str(title or "").strip().casefold()
    if not normalized_title:
        return False
    return any(
        str(marker or "").strip().casefold() in normalized_title
        for marker in _SPECIFIC_REPORT_STYLE_TITLE_MARKERS
    )


def _normalize_title_word(token: str) -> str:
    normalized_token = str(token or "").strip().casefold()
    if len(normalized_token) <= 4:
        return normalized_token
    if normalized_token.endswith("ies"):
        return normalized_token[:-3] + "y"
    if normalized_token.endswith("s") and not normalized_token.endswith("ss"):
        return normalized_token[:-1]
    return normalized_token


def _looks_like_self_service_page_url(url: str) -> bool:
    normalized = str(url or "").strip().casefold()
    if not normalized:
        return False
    return any(marker in normalized for marker in _SELF_SERVICE_URL_MARKERS)


def _looks_like_report_section_url(url: str) -> bool:
    path = urlsplit(str(url or "").strip().casefold()).path
    segments = [segment for segment in path.split("/") if segment]
    if len(segments) < 2:
        return False
    parent_slug = segments[-2].replace("-", " ")
    child_slug = segments[-1].rsplit(".", 1)[0]
    if child_slug not in _SECTION_URL_SLUG_MARKERS:
        return False
    return _contains_report_style_title_marker(parent_slug)


def _has_report_style_url_path(final_url_lower: str) -> bool:
    normalized = str(final_url_lower or "").strip().casefold()
    if not normalized:
        return False
    return any(marker in normalized for marker in _REPORT_URL_PATH_MARKERS)


def _looks_like_report_collection_bucket_url(url: str) -> bool:
    path = urlsplit(str(url or "").strip().casefold()).path
    if not path:
        return False
    segments = [segment for segment in path.split("/") if segment]
    if not segments:
        return False
    leaf = segments[-1].rsplit(".", 1)[0]
    return leaf in _REPORT_COLLECTION_URL_SEGMENTS


def _looks_like_service_or_membership_page(
    *,
    final_url_lower: str,
    resolved_title_lower: str,
) -> bool:
    normalized_url = str(final_url_lower or "").strip().casefold()
    if not normalized_url:
        return False
    path = urlsplit(normalized_url).path
    segments = [segment for segment in path.split("/") if segment]
    if not segments:
        return False
    if any(marker in normalized_url for marker in _SERVICE_OR_MEMBERSHIP_PATH_MARKERS):
        return True
    if _LEAD_CAPTURE_PATH_RE.match(path):
        return True
    leaf = segments[-1].rsplit(".", 1)[0]
    if leaf in _SERVICE_OR_MEMBERSHIP_LEAF_MARKERS:
        return True
    if any(
        leaf.endswith(f"-{marker}") or leaf.startswith(f"{marker}-")
        for marker in _SERVICE_OR_MEMBERSHIP_LEAF_MARKERS
    ):
        return True
    if leaf.endswith("-system"):
        return True
    return any(
        marker in str(resolved_title_lower or "").strip().casefold()
        for marker in _SERVICE_OR_MEMBERSHIP_TITLE_MARKERS
    )


def _looks_like_hard_non_asset_route(url: str) -> bool:
    normalized_url = str(url or "").strip().casefold()
    if not normalized_url:
        return False
    path = urlsplit(normalized_url).path
    if any(marker in normalized_url for marker in _HARD_NON_ASSET_PATH_MARKERS):
        return True
    return bool(_LEAD_CAPTURE_PATH_RE.match(path))


def _looks_like_research_hub_page(
    *,
    final_url_lower: str,
    resolved_title_lower: str,
) -> bool:
    normalized_url = str(final_url_lower or "").strip().casefold()
    normalized_title = str(resolved_title_lower or "").strip().casefold()
    if not normalized_url:
        return False
    path = urlsplit(normalized_url).path
    segments = [segment for segment in path.split("/") if segment]
    if not segments:
        return False
    leaf = segments[-1].rsplit(".", 1)[0]
    if leaf.endswith("-research-center") or leaf.endswith("-research"):
        return normalized_title.endswith("research center") or normalized_title.endswith("research")
    return normalized_title.endswith("research center") or normalized_title.endswith("research")


def _looks_like_report_collection_root_url(url: str) -> bool:
    path = urlsplit(str(url or "").strip().casefold()).path
    if not path:
        return False
    segments = [segment for segment in path.split("/") if segment]
    if not segments:
        return False
    leaf = segments[-1].rsplit(".", 1)[0]
    if leaf in _REPORT_COLLECTION_URL_SEGMENTS:
        return True
    words = [token for token in re.findall(r"[a-z0-9]+", leaf) if token]
    if not words:
        return False
    if not any(
        token in _REPORT_COLLECTION_URL_SEGMENTS
        or token in {"hub", "library", "center", "centre", "research", "reports", "report"}
        for token in words
    ):
        return False
    return all(token in _REPORT_COLLECTION_ROOT_WORDS for token in words)


def _looks_like_strict_collection_root_url(url: str) -> bool:
    path = urlsplit(str(url or "").strip().casefold()).path
    if not path:
        return False
    segments = [segment for segment in path.split("/") if segment]
    if not segments:
        return False
    leaf = segments[-1].rsplit(".", 1)[0]
    if leaf in _REPORT_COLLECTION_URL_SEGMENTS:
        return True
    words = [token for token in re.findall(r"[a-z0-9]+", leaf) if token]
    if not words:
        return False
    return any(token in {"hub", "library", "center", "centre"} for token in words) and all(
        token in _REPORT_COLLECTION_ROOT_WORDS for token in words
    )


def _looks_like_newsletter_source_url(source_page_url: str) -> bool:
    normalized = str(source_page_url or "").strip().casefold()
    if not normalized:
        return False
    return "newsletter" in normalized or "/newsletters/" in normalized


def _looks_like_report_section_title(title: str) -> bool:
    normalized_title = str(title or "").strip().casefold()
    if not normalized_title:
        return False
    if normalized_title in _SECTION_TITLE_MARKERS:
        return True
    return bool(re.fullmatch(r"(chapter|part|section)\s+\d+[a-z]?", normalized_title))


def _looks_like_survey_platform_page(url: str) -> bool:
    normalized = str(url or "").strip().casefold()
    if not normalized:
        return False
    return any(marker in normalized for marker in _SURVEY_PLATFORM_HOST_MARKERS)
