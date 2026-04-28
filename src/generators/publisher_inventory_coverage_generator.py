from __future__ import annotations

import logging

from src.contracts.publisher_inventory import (
    PublisherInventoryCoverageValidationRequest,
    PublisherInventoryCoverageValidationResponse,
)
from src.contracts.run_context import RunContext
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.publisher_inventory_coverage_generator")


def validate_publisher_inventory_coverage(
    request: PublisherInventoryCoverageValidationRequest,
    ctx: RunContext,
) -> PublisherInventoryCoverageValidationResponse:
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="publisher_inventory_coverage_validation_start",
            module=logger.name,
            fields={
                "publisher_name": request.publisher_name,
                "normalized_url": request.normalized_url,
                "previous_snapshot_available": request.previous_snapshot_available,
                "previous_page_count": request.previous_page_count,
                "previous_report_count": request.previous_report_count,
                "current_page_count": request.current_page_count,
                "current_report_count": request.current_report_count,
                "raw_new_report_count": request.raw_new_report_count,
                "screened_new_report_count": request.screened_new_report_count,
                "qualified_new_report_count": request.qualified_new_report_count,
                "candidate_snapshot_changed": request.candidate_snapshot_changed,
            },
        )
    )
    response = _evaluate_coverage(request)
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="publisher_inventory_coverage_validation_complete",
            module=logger.name,
            fields={
                "publisher_name": request.publisher_name,
                "normalized_url": request.normalized_url,
                "verdict": response.verdict,
                "snapshot_allowed": response.snapshot_allowed,
                "no_report_assets_detected": response.no_report_assets_detected,
                "should_raise_error": response.should_raise_error,
                "error_code": response.error_code or "",
            },
        )
    )
    return response


def _evaluate_coverage(
    request: PublisherInventoryCoverageValidationRequest,
) -> PublisherInventoryCoverageValidationResponse:
    if _is_systematic_unreachable_delta(request):
        if request.previous_snapshot_available:
            return PublisherInventoryCoverageValidationResponse(
                schema_version="1.0",
                verdict="unreachable_delta_tolerated",
                reason=(
                    "All screened delta candidates were unreachable, so the previous canonical snapshot remains authoritative."
                ),
                snapshot_allowed=False,
                no_report_assets_detected=False,
                should_raise_error=False,
            )
        return PublisherInventoryCoverageValidationResponse(
            schema_version="1.0",
            verdict="unreachable_delta_failure",
            reason=(
                "All screened candidates were rejected as unreachable and no earlier canonical snapshot exists."
            ),
            snapshot_allowed=False,
            no_report_assets_detected=False,
            should_raise_error=True,
            error_code="publisher_inventory_candidate_quality_unreachable_archive",
            error_message=(
                "Landing-page quality verification rejected all screened candidates as unreachable"
            ),
        )

    if _is_no_report_assets_archive(request):
        return PublisherInventoryCoverageValidationResponse(
            schema_version="1.0",
            verdict="no_report_assets",
            reason=(
                "The first-run archive exposed raw candidates but no qualifying report assets after screening and landing-page checks."
            ),
            snapshot_allowed=False,
            no_report_assets_detected=True,
            should_raise_error=False,
        )

    if _is_undercoverage_regression(request):
        return PublisherInventoryCoverageValidationResponse(
            schema_version="1.0",
            verdict="undercoverage_regression",
            reason=(
                "Discovery returned a materially smaller inventory without any new qualified report assets."
            ),
            snapshot_allowed=False,
            no_report_assets_detected=False,
            should_raise_error=True,
            error_code="publisher_inventory_browser_incomplete",
            error_message=(
                "Discovery returned a materially smaller inventory without any new qualified report assets"
            ),
        )

    if (
        request.candidate_snapshot_changed
        and request.previous_snapshot_available
        and request.raw_new_report_count > 0
        and request.qualified_new_report_count == 0
    ):
        return PublisherInventoryCoverageValidationResponse(
            schema_version="1.0",
            verdict="raw_only_delta_rejected",
            reason=(
                "Only raw snapshot deltas changed, and every new candidate was rejected before qualification, so the previous canonical snapshot is preserved."
            ),
            snapshot_allowed=False,
            no_report_assets_detected=False,
            should_raise_error=False,
        )

    return PublisherInventoryCoverageValidationResponse(
        schema_version="1.0",
        verdict="accepted",
        reason="Coverage and delta validation accepted the candidate snapshot.",
        snapshot_allowed=True,
        no_report_assets_detected=False,
        should_raise_error=False,
    )


def _is_systematic_unreachable_delta(
    request: PublisherInventoryCoverageValidationRequest,
) -> bool:
    if request.screened_new_report_count <= 0:
        return False
    if request.qualified_new_report_count > 0:
        return False
    if len(request.quality_rejection_reasons) != request.screened_new_report_count:
        return False
    return all(
        str(reason or "").strip() == "dead_or_unreachable_landing_page"
        for reason in request.quality_rejection_reasons
    )


def _is_no_report_assets_archive(
    request: PublisherInventoryCoverageValidationRequest,
) -> bool:
    if request.previous_snapshot_available:
        return False
    if request.current_report_count <= 0:
        return False
    if request.qualified_new_report_count != 0:
        return False
    return request.screened_new_report_count == 0 or bool(
        request.quality_rejection_reasons
    )


def _is_undercoverage_regression(
    request: PublisherInventoryCoverageValidationRequest,
) -> bool:
    if not request.previous_snapshot_available:
        return False
    if request.current_page_count <= 1 and request.previous_page_count <= 1:
        return False
    if request.previous_report_count <= 0:
        return False
    if request.current_report_count >= request.previous_report_count:
        return False
    if request.raw_new_report_count > 0 or request.qualified_new_report_count > 0:
        return False
    dropped_report_count = request.previous_report_count - request.current_report_count
    if dropped_report_count < 5:
        return False
    return request.current_report_count / request.previous_report_count <= 0.8
