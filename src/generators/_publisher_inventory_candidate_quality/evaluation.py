from __future__ import annotations

from src.contracts.publisher_inventory import (
    PublisherInventoryLandingPageObservation,
    PublisherInventoryRecoveryRecipe,
)

from .classification import (
    _LEGAL_URL_MARKERS,
    _LEGAL_TITLE_MARKERS,
    _REGULATORY_TITLE_MARKERS,
    _CORPORATE_POLICY_TITLE_MARKERS,
    _CASE_STUDY_URL_MARKERS,
    _CASE_STUDY_TITLE_MARKERS,
    _ANNOUNCEMENT_TITLE_MARKERS,
    _METHODOLOGY_TITLE_MARKERS,
    _looks_like_dated_editorial_url,
    _looks_like_editorial_section_url,
    _normalize_title,
    _looks_like_informational_article_title,
    _looks_like_article_label_title,
    _contains_report_style_title_marker,
    _looks_like_bot_challenge_page,
    _looks_like_transient_fetch_failure,
    _looks_like_transient_http_status,
    _looks_like_protected_document_status,
    _looks_like_document_url,
    _has_report_style_url_slug,
    _has_strong_report_style_url_slug,
    _contains_specific_report_style_title_marker,
    _looks_like_self_service_page_url,
    _looks_like_consumer_self_service_report_product,
    _looks_like_report_section_url,
    _has_report_style_url_path,
    _looks_like_publication_detail_url,
    _looks_like_report_collection_bucket_url,
    _looks_like_audio_editorial_page,
    _looks_like_service_or_membership_page,
    _looks_like_news_analysis_title,
    _contains_strong_editorial_report_title_marker,
    _looks_like_hard_non_asset_route,
    _looks_like_research_hub_page,
    _looks_like_report_collection_root_url,
    _looks_like_strict_collection_root_url,
    _looks_like_newsletter_source_url,
    _looks_like_report_section_title,
    _looks_like_survey_platform_page,
)


def _qualify_observation(
    observation: PublisherInventoryLandingPageObservation,
    *,
    source_page_url: str,
) -> tuple[bool, str]:
    resolved_title_lower = _normalize_title(
        observation.h1_title
        or observation.og_title
        or observation.final_title
        or observation.source_title
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
    editorial_section_signal = _looks_like_editorial_section_url(
        final_url_lower
    ) or _looks_like_editorial_section_url(observation.canonical_url)
    editorial_surface_signal = (
        observation.has_editorial_url_pattern
        or observation.has_related_posts
        or editorial_section_signal
    )
    editorial_context_signal = (
        editorial_surface_signal or observation.has_editorial_markers
    )
    hard_editorial_signal = (
        editorial_section_signal or observation.has_contact_sales_cta
    )
    report_archive_path_signal = _has_report_style_url_path(final_url_lower)
    report_slug_signal = _has_report_style_url_slug(final_url_lower)
    report_title_signal = _contains_report_style_title_marker(resolved_title_lower)
    specific_report_title_signal = _contains_specific_report_style_title_marker(
        resolved_title_lower
    )
    strong_editorial_report_title_signal = (
        _contains_strong_editorial_report_title_marker(resolved_title_lower)
    )
    strong_report_slug_signal = _has_strong_report_style_url_slug(final_url_lower)
    editorial_report_rescue_signal = (
        report_archive_path_signal
        or strong_report_slug_signal
        or strong_editorial_report_title_signal
    )
    source_title_report_signal = _contains_report_style_title_marker(source_title_lower)
    source_report_signal = (
        source_title_report_signal
        or _has_report_style_url_path(observation.canonical_url)
        or _has_report_style_url_slug(observation.canonical_url)
        or _has_report_style_url_path(source_page_url)
        or _has_report_style_url_slug(source_page_url)
        or _looks_like_publication_detail_url(observation.canonical_url)
        or _looks_like_publication_detail_url(source_page_url)
    )
    bot_protected_report_signal = (
        report_title_signal
        or source_title_report_signal
        or _has_report_style_url_path(observation.canonical_url)
        or _has_report_style_url_slug(observation.canonical_url)
    )
    case_study_signal = (
        any(marker in final_url_lower for marker in _CASE_STUDY_URL_MARKERS)
        or any(
            marker in observation.canonical_url.casefold()
            for marker in _CASE_STUDY_URL_MARKERS
        )
        or any(marker in resolved_title_lower for marker in _CASE_STUDY_TITLE_MARKERS)
        or any(marker in source_title_lower for marker in _CASE_STUDY_TITLE_MARKERS)
    )
    collection_hub_signal = (
        _looks_like_strict_collection_root_url(final_url_lower)
        or _looks_like_strict_collection_root_url(observation.canonical_url)
        or _looks_like_report_collection_root_url(final_url_lower)
        or _looks_like_report_collection_root_url(observation.canonical_url)
        or _looks_like_report_collection_bucket_url(final_url_lower)
        or _looks_like_report_collection_bucket_url(observation.canonical_url)
    )
    hard_non_asset_signal = _looks_like_hard_non_asset_route(
        final_url_lower
    ) or _looks_like_hard_non_asset_route(observation.canonical_url)
    service_or_membership_signal = _looks_like_service_or_membership_page(
        final_url_lower=final_url_lower or observation.canonical_url,
        resolved_title_lower=resolved_title_lower,
    ) or _looks_like_service_or_membership_page(
        final_url_lower=observation.canonical_url,
        resolved_title_lower=resolved_title_lower,
    )
    newsletter_source_signal = _looks_like_newsletter_source_url(source_page_url)
    if (
        _looks_like_bot_challenge_page(observation)
        and observation.has_dead_page_marker
        and _looks_like_article_label_title(source_title_lower)
    ):
        return False, "bot_protected_editorial_page"
    if case_study_signal:
        return False, "case_study_or_customer_story_page"
    if (
        _looks_like_bot_challenge_page(observation)
        and source_report_signal
        and not collection_hub_signal
        and not hard_non_asset_signal
        and not service_or_membership_signal
    ):
        if (
            _looks_like_article_label_title(source_title_lower)
            and not report_title_signal
        ):
            return False, "bot_protected_editorial_page"
        if bot_protected_report_signal:
            return True, "bot_protected_report_asset"
        if _looks_like_publication_detail_url(observation.canonical_url):
            return True, "bot_protected_report_asset"
        return False, "bot_protected_editorial_page"
    if (
        (
            _looks_like_transient_fetch_failure(observation.fetch_error)
            or _looks_like_transient_http_status(observation.http_status_code)
        )
        and source_report_signal
        and not collection_hub_signal
        and not hard_non_asset_signal
        and not service_or_membership_signal
    ):
        return True, "transient_fetch_report_asset"
    if (
        _looks_like_protected_document_status(observation.http_status_code)
        and source_report_signal
        and not collection_hub_signal
        and not hard_non_asset_signal
        and not service_or_membership_signal
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
    if (
        source_report_signal
        and not collection_hub_signal
        and not hard_non_asset_signal
        and not service_or_membership_signal
        and (
            report_archive_path_signal
            or report_slug_signal
            or specific_report_title_signal
            or _looks_like_publication_detail_url(observation.canonical_url)
        )
        and (observation.fetch_error or observation.has_dead_page_marker)
        and (
            not editorial_context_signal
            or structured_document_signal
            or observation.has_print_language
        )
    ):
        return True, "unreachable_report_asset"
    if observation.fetch_error or observation.has_dead_page_marker:
        return False, "dead_or_unreachable_landing_page"
    if (
        _looks_like_audio_editorial_page(
            final_url_lower=final_url_lower,
            resolved_title_lower=resolved_title_lower,
            source_title_lower=source_title_lower,
        )
        and not observation.is_pdf
    ):
        return False, "audio_editorial_page"
    if _looks_like_self_service_page_url(final_url_lower) and not (
        observation.is_pdf
        or observation.has_download_language
        or observation.has_gated_form
        or observation.has_document_structure
    ):
        return False, "self_service_or_signup_page"
    if _looks_like_consumer_self_service_report_product(
        final_url_lower=final_url_lower,
        resolved_title_lower=resolved_title_lower,
        observation=observation,
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
    if (
        any(marker in resolved_title_lower for marker in _METHODOLOGY_TITLE_MARKERS)
        and not (
            specific_report_title_signal
            or _looks_like_publication_detail_url(observation.canonical_url)
            or _looks_like_publication_detail_url(source_page_url)
        )
        and not strong_distribution_signal
        and not structured_document_signal
    ):
        return False, "editorial_article_page"
    if (
        _looks_like_service_or_membership_page(
            final_url_lower=final_url_lower,
            resolved_title_lower=resolved_title_lower,
        )
        and not specific_report_title_signal
    ):
        return False, "service_or_membership_page"
    if any(
        marker in resolved_title_lower for marker in _ANNOUNCEMENT_TITLE_MARKERS
    ) and not (observation.has_gated_form or observation.has_price_or_purchase):
        return False, "research_announcement_page"
    if any(marker in resolved_title_lower for marker in _REGULATORY_TITLE_MARKERS):
        return False, "regulatory_or_disclosure_document"
    if any(
        marker in resolved_title_lower for marker in _CORPORATE_POLICY_TITLE_MARKERS
    ):
        return False, "corporate_policy_document"
    if _looks_like_survey_platform_page(observation.final_url) and not (
        observation.has_download_language or observation.has_document_structure
    ):
        return False, "survey_or_questionnaire_page"
    if (
        (report_archive_path_signal or report_slug_signal)
        and specific_report_title_signal
        and source_report_signal
        and not strong_distribution_signal
        and not structured_document_signal
        and not hard_editorial_signal
        and not _looks_like_dated_editorial_url(final_url_lower)
    ):
        return True, "report_detail_landing_page"
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
            or strong_report_slug_signal
            or strong_editorial_report_title_signal
            or (observation.is_pdf and (report_title_signal or source_report_signal))
        )
        and not _looks_like_dated_editorial_url(final_url_lower)
    ):
        if hard_editorial_signal and not report_archive_path_signal:
            return False, "editorial_article_page"
        if editorial_context_signal and not editorial_report_rescue_signal:
            return False, "editorial_article_page"
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
    if (
        _looks_like_informational_article_title(resolved_title_lower)
        and not (observation.has_gated_form or observation.has_price_or_purchase)
        and not (
            source_report_signal
            and (
                report_slug_signal
                or specific_report_title_signal
                or report_archive_path_signal
            )
        )
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
        _looks_like_news_analysis_title(resolved_title_lower)
        and editorial_context_signal
        and not strong_distribution_signal
        and not structured_document_signal
        and not specific_report_title_signal
        and not report_archive_path_signal
        and not report_slug_signal
    ):
        return False, "editorial_article_page"
    if (
        (report_archive_path_signal or report_slug_signal or report_title_signal)
        and (structured_document_signal or observation.has_asset_type_term)
        and not observation.has_dead_page_marker
        and not (editorial_context_signal and not editorial_report_rescue_signal)
    ):
        if hard_editorial_signal and not report_archive_path_signal:
            return False, "editorial_article_page"
        return True, "printable_report_page"
    if (
        observation.has_price_or_purchase
        and observation.has_asset_type_term
        and not editorial_context_signal
    ):
        return True, "paid_or_publication_report_page"
    if (
        observation.has_gated_form
        and (observation.has_asset_type_term or observation.has_document_structure)
        and (
            report_title_signal
            or specific_report_title_signal
            or report_archive_path_signal
            or report_slug_signal
            or source_report_signal
        )
    ):
        if hard_editorial_signal and not report_archive_path_signal:
            return False, "editorial_article_page"
        if editorial_context_signal and not editorial_report_rescue_signal:
            return False, "editorial_article_page"
        return True, "gated_report_asset"
    if (
        observation.has_download_language
        and (observation.has_asset_type_term or observation.has_document_structure)
        and (
            report_title_signal
            or specific_report_title_signal
            or report_archive_path_signal
            or report_slug_signal
            or source_report_signal
        )
    ):
        if hard_editorial_signal and not report_archive_path_signal:
            return False, "editorial_article_page"
        if editorial_context_signal and not editorial_report_rescue_signal:
            return False, "editorial_article_page"
        return True, "downloadable_report_asset"
    if (
        observation.has_print_language
        and (observation.has_asset_type_term or observation.has_document_structure)
        and not editorial_surface_signal
        and (
            report_title_signal
            or specific_report_title_signal
            or report_archive_path_signal
            or report_slug_signal
            or source_report_signal
        )
    ):
        return True, "printable_report_page"
    if (
        (report_slug_signal or specific_report_title_signal)
        and source_report_signal
        and not editorial_context_signal
        and not _looks_like_report_collection_bucket_url(final_url_lower)
    ):
        return True, "report_detail_landing_page"
    if structured_document_signal and (
        observation.has_asset_type_term
        or report_title_signal
        or report_archive_path_signal
        or report_slug_signal
    ):
        if hard_editorial_signal and not report_archive_path_signal:
            return False, "editorial_article_page"
        if editorial_context_signal and not editorial_report_rescue_signal:
            return False, "editorial_article_page"
        return True, "report_like_document_page"
    if editorial_context_signal and not strong_distribution_signal:
        return False, "editorial_article_page"
    if (observation.has_newsletter_cta or observation.has_contact_sales_cta) and not (
        strong_distribution_signal or structured_document_signal
    ):
        return False, "marketing_cta_without_report_asset"
    return False, "insufficient_report_signals"


def _build_recovery_recipe(
    *,
    observation: PublisherInventoryLandingPageObservation,
    accepted: bool,
    reason: str,
    resolved_title: str,
) -> PublisherInventoryRecoveryRecipe | None:
    if accepted:
        return None
    if observation.source_surface_class not in {"archive_feed", "direct_detail"}:
        return None
    verification_class = str(observation.verification_class or "").strip()
    if verification_class not in {
        "challenge",
        "transient_fetch_failure",
        "protected_document",
    }:
        return None
    if reason in {
        "editorial_article_page",
        "case_study_or_customer_story_page",
        "service_or_membership_page",
        "newsletter_article_page",
        "research_announcement_page",
        "informational_article_page",
        "audio_editorial_page",
        "generic_asset_hub_page",
        "report_section_page",
    }:
        return None
    action = {
        "challenge": "browser_retry",
        "transient_fetch_failure": "http_recheck",
        "protected_document": "protected_document_probe",
    }.get(verification_class, "")
    if not action:
        return None
    return PublisherInventoryRecoveryRecipe(
        schema_version="1.0",
        verification_class=verification_class,
        source_surface_class=observation.source_surface_class,
        recovery_action=action,
        reason=(
            f"Deferred recovery allowed for strong {observation.source_surface_class} "
            f"candidate after {verification_class} verification failure on {resolved_title}."
        ),
    )
