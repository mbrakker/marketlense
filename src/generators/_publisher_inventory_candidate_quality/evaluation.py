from __future__ import annotations

from src.contracts.publisher_inventory import (
    PublisherInventoryLandingPageObservation,
    PublisherInventoryRecoveryRecipe,
)


def _qualify_observation(
    observation: PublisherInventoryLandingPageObservation,
    *,
    source_page_url: str,
) -> tuple[bool, str]:
    """Return the technical result after the screening model's decision.

    Landing-page titles, URL patterns and report-like signals are semantic
    qualification inputs. The candidate-screening LLM owns that decision;
    this stage keeps only source identity and fetch integrity contracts.
    """
    del source_page_url
    resolved_url = str(observation.final_url or observation.canonical_url or "").strip()
    if not resolved_url:
        return False, "landing_page_url_missing"
    if (
        observation.fetch_error
        or observation.has_dead_page_marker
        or int(observation.http_status_code or 0) >= 400
    ):
        return False, "landing_page_unreachable"
    return True, "candidate_screening_model_authoritative"


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
            f"candidate after {verification_class} verification failure on "
            f"{resolved_title}."
        ),
    )
