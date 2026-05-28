from __future__ import annotations

"""Candidate post-processing helpers for publisher-inventory orchestration.

This module owns resource-quality ordering, deferred recovery-cache recording,
provenance summarization, and rollout guardrail logging after discovery.
"""

import logging
from urllib.parse import urlsplit

from src.contracts.publisher_inventory import (
    PublisherInventoryCandidateQualityResponse,
    PublisherInventoryCoverageValidationResponse,
    PublisherInventoryDiscoveryRequest,
    PublisherInventoryRecoveryRecord,
    PublisherInventoryServiceResponse,
)
from src.contracts.report_store import (
    PublisherInventoryRecoveryCacheGetRequest,
    PublisherInventoryRecoveryCacheRecordRequest,
    PublisherResourceRankingPolicy,
    PublisherResourceRankingRequest,
    ReportSourceQualityHistoryRequest,
)
from src.contracts.run_context import RunContext
from src.orchestrators._publisher_inventory_orchestrator.dependencies import (
    PublisherInventoryDependencies,
)
from src.orchestrators._publisher_inventory_orchestrator.idempotency import (
    _record_recovery_cache_if_needed,
)
from src.orchestrators._publisher_inventory_orchestrator.runtime import _utc_now_iso
from src.utils.logging import log_event
from src.utils.url_utils import normalize_url

logger = logging.getLogger("market_lense.publisher_inventory_orchestrator")


def _rank_qualified_items_by_resource_quality(
    *,
    qualified_items,
    publisher_name: str,
    reports_db: str,
    page_url_by_number: dict[int, str],
    fallback_source_url: str,
    settings,
    ctx: RunContext,
    dependencies: PublisherInventoryDependencies,
):
    if not qualified_items or not settings.resource_quality_ranking_enabled:
        return qualified_items
    source_urls = [
        page_url_by_number.get(item.discovered_on_page_number, fallback_source_url)
        for item in qualified_items
    ]
    history = dependencies.list_report_source_quality_history(
        ReportSourceQualityHistoryRequest(
            schema_version="1.0",
            db_path=reports_db,
            publisher_name=publisher_name,
            limit=max(
                settings.resource_quality_score_window_size
                * max(1, len(set(source_urls))),
                settings.resource_quality_score_window_size,
            ),
        ),
        ctx,
    )
    ranking = dependencies.rank_publisher_resources(
        PublisherResourceRankingRequest(
            schema_version="1.0",
            publisher_name=publisher_name,
            candidate_source_page_urls=source_urls,
            history_items=history.items,
            policy=PublisherResourceRankingPolicy(
                schema_version="1.0",
                score_window_size=settings.resource_quality_score_window_size,
                min_sample_size=settings.resource_quality_min_sample_size,
                consistency_weight=settings.resource_quality_consistency_weight,
                average_score_weight=settings.resource_quality_average_weight,
                confidence_weight=settings.resource_quality_confidence_weight,
                low_score_demotion_threshold=(
                    settings.resource_quality_low_score_demotion_threshold
                ),
            ),
        ),
        ctx,
    )
    rank_by_url = {item.resource_url: index for index, item in enumerate(ranking.items)}
    score_by_url = {item.resource_url: item for item in ranking.items}

    def source_url_for_item(item) -> str:
        source_url = page_url_by_number.get(
            item.discovered_on_page_number, fallback_source_url
        )
        return normalize_url(source_url) or source_url

    def sort_key(item) -> tuple[int, int, str]:
        normalized_source_url = source_url_for_item(item)
        return (
            rank_by_url.get(normalized_source_url, len(rank_by_url)),
            item.discovered_on_page_number,
            item.canonical_url,
        )

    ranked_items = sorted(qualified_items, key=sort_key)
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="publisher_inventory_resource_quality_ranking_applied",
            module=logger.name,
            fields={
                "publisher_name": publisher_name,
                "history_sample_count": len(history.items),
                "score_window_size": settings.resource_quality_score_window_size,
                "min_sample_size": settings.resource_quality_min_sample_size,
                "ranked_resource_count": len(ranking.items),
                "resource_rankings": [
                    {
                        "resource_url": item.resource_url,
                        "sample_size": item.sample_size,
                        "confidence": item.confidence,
                        "rank_score": item.rank_score,
                        "demotion_reason": item.demotion_reason,
                    }
                    for item in ranking.items
                ],
                "ordered_candidate_urls": [item.canonical_url for item in ranked_items],
                "candidate_resource_scores": {
                    item.canonical_url: score_by_url[
                        source_url_for_item(item)
                    ].rank_score
                    if source_url_for_item(item) in score_by_url
                    else 0.0
                    for item in ranked_items
                },
            },
        )
    )
    return ranked_items


def _candidate_provenance_counts(
    candidates,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for candidate in candidates:
        provenance = str(getattr(candidate, "provenance", "") or "unknown").strip()
        key = provenance or "unknown"
        counts[key] = counts.get(key, 0) + 1
    return counts


def _record_deferred_candidate_recovery_cache(
    *,
    request: PublisherInventoryDiscoveryRequest,
    normalized_url: str,
    publisher_name: str,
    quality_response: PublisherInventoryCandidateQualityResponse,
    ctx: RunContext,
    dependencies: PublisherInventoryDependencies,
) -> int:
    scheduled_count = 0
    for decision in quality_response.decisions:
        recipe = decision.recovery_recipe
        if recipe is None:
            continue
        existing = dependencies.get_publisher_inventory_recovery_cache_record(
            PublisherInventoryRecoveryCacheGetRequest(
                schema_version="1.0",
                db_path=request.reports_db,
                normalized_url=normalized_url,
                canonical_url=decision.canonical_url,
            ),
            ctx,
        )
        if (
            existing is not None
            and existing.verification_class == recipe.verification_class
            and existing.recovery_action == recipe.recovery_action
            and existing.last_outcome in {"scheduled", "recovered"}
        ):
            logger.info(
                log_event(
                    ctx,
                    role="orchestrator",
                    event="publisher_inventory_candidate_recovery_cache_reused",
                    module=logger.name,
                    fields={
                        "publisher_name": publisher_name,
                        "normalized_url": normalized_url,
                        "canonical_url": decision.canonical_url,
                        "verification_class": existing.verification_class,
                        "last_outcome": existing.last_outcome,
                    },
                )
            )
            continue
        last_outcome = (
            "scheduled"
            if request.settings.enable_deferred_candidate_recovery
            else "skipped"
        )
        if last_outcome == "scheduled":
            scheduled_count += 1
        _record_recovery_cache_if_needed(
            request=PublisherInventoryRecoveryCacheRecordRequest(
                schema_version="1.0",
                db_path=request.reports_db,
                record=PublisherInventoryRecoveryRecord(
                    schema_version="1.0",
                    normalized_url=normalized_url,
                    canonical_url=decision.canonical_url,
                    source_surface_class=decision.source_surface_class,
                    verification_class=recipe.verification_class,
                    recovery_action=recipe.recovery_action,
                    last_outcome=last_outcome,
                    last_http_status=None,
                    last_error_marker=decision.reason,
                    updated_at_utc=_utc_now_iso(),
                ),
            ),
            ctx=ctx,
            dependencies=dependencies,
        )
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="publisher_inventory_candidate_recovery_cache_recorded",
                module=logger.name,
                fields={
                    "publisher_name": publisher_name,
                    "normalized_url": normalized_url,
                    "canonical_url": decision.canonical_url,
                    "verification_class": recipe.verification_class,
                    "recovery_action": recipe.recovery_action,
                    "last_outcome": last_outcome,
                },
            )
        )
    return scheduled_count


def _log_rollout_guardrails(
    *,
    request: PublisherInventoryDiscoveryRequest,
    normalized_url: str,
    publisher_name: str,
    discovery_result: PublisherInventoryServiceResponse,
    run_quality_summary,
    coverage_response: PublisherInventoryCoverageValidationResponse,
    raw_new_report_count: int,
    screened_new_report_count: int,
    qualified_new_report_count: int,
    quality_rejected_new_report_count: int,
    deferred_recovery_scheduled_count: int,
    ctx: RunContext,
) -> None:
    precision_guardrail_passed = (
        0
        <= qualified_new_report_count
        <= screened_new_report_count
        <= raw_new_report_count
    )
    coverage_guardrail_passed = coverage_response.verdict not in {
        "undercoverage_regression",
        "unreachable_delta_failure",
    }
    kpi_guardrail_status = (
        "pass"
        if precision_guardrail_passed
        and coverage_guardrail_passed
        and not run_quality_summary.requires_review
        else "review_required"
    )
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="publisher_inventory_rollout_guardrails_evaluated",
            module=logger.name,
            fields={
                "publisher_name": publisher_name,
                "normalized_url": normalized_url,
                "rollout_flags": {
                    "enable_deferred_candidate_recovery": (
                        request.settings.enable_deferred_candidate_recovery
                    ),
                    "enable_structured_route_reuse": (
                        request.settings.enable_structured_route_reuse
                    ),
                    "enable_preflight_classifier_and_direct_detail": (
                        request.settings.enable_preflight_classifier_and_direct_detail
                    ),
                },
                "canary_kpi_set": {
                    "coverage_verdict": coverage_response.verdict,
                    "run_quality_band": run_quality_summary.quality_band,
                    "raw_new_report_count": raw_new_report_count,
                    "screened_new_report_count": screened_new_report_count,
                    "qualified_new_report_count": qualified_new_report_count,
                    "quality_rejected_new_report_count": quality_rejected_new_report_count,
                    "candidate_provenance_counts": (
                        run_quality_summary.candidate_provenance_counts
                    ),
                },
                "scenario_class": (
                    discovery_result.scenario_summary.scenario_class
                    if discovery_result.scenario_summary is not None
                    else ""
                ),
                "used_memory_route": discovery_result.used_route_hint,
                "deferred_recovery_scheduled_count": deferred_recovery_scheduled_count,
                "precision_guardrail_passed": precision_guardrail_passed,
                "coverage_guardrail_passed": coverage_guardrail_passed,
                "run_quality_requires_review": run_quality_summary.requires_review,
                "kpi_guardrail_status": kpi_guardrail_status,
                "rollback_condition": (
                    "disable rollout flags or force browser review when status is review_required"
                ),
            },
        )
    )


def _source_domain_for_url(url: str) -> str:
    return str(urlsplit(str(url).strip()).hostname or "").strip().lower()


__all__ = [name for name in globals() if not name.startswith("__")]
