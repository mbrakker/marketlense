from __future__ import annotations

import logging

from src.contracts.publisher_inventory import (
    PublisherInventoryCandidateQualityDecision,
    PublisherInventoryCandidateQualityRequest,
    PublisherInventoryCandidateQualityResponse,
    PublisherInventoryLandingPageInspectionItem,
    PublisherInventoryLandingPageInspectionRequest,
    PublisherInventoryQualifiedCandidateItem,
)
from src.services.publisher_inventory_service import (
    inspect_publisher_inventory_landing_pages,
)
from src.utils.errors import AppError
from src.utils.logging import log_event

from .classification import _resolve_candidate_title
from .evaluation import _build_recovery_recipe, _qualify_observation

logger = logging.getLogger(
    "market_lense.publisher_inventory_candidate_quality_generator"
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
        passthrough_items = [
            PublisherInventoryQualifiedCandidateItem(
                schema_version="1.0",
                canonical_url=item.canonical_url,
                title=item.title,
                discovered_on_page_number=item.discovered_on_page_number,
                source_page_url=item.source_page_url,
            )
            for item in candidates
        ]
        passthrough_decisions = [
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
            approved_items=passthrough_items,
            rejected_items=[],
            decisions=passthrough_decisions,
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
        recovery_recipe = _build_recovery_recipe(
            observation=observation,
            accepted=accepted,
            reason=reason,
            resolved_title=resolved_title,
        )
        decisions.append(
            PublisherInventoryCandidateQualityDecision(
                schema_version="1.0",
                canonical_url=item.canonical_url,
                accepted=accepted,
                reason=reason,
                resolved_title=resolved_title,
                source_surface_class=observation.source_surface_class,
                recovery_recipe=recovery_recipe,
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
