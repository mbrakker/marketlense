from __future__ import annotations

import logging

from src.contracts.publisher_inventory import (
    PublisherInventoryCoverageValidationResponse,
    PublisherInventoryRunQualityEvaluationRequest,
    PublisherInventoryRunQualitySummary,
)
from src.contracts.run_context import RunContext
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.publisher_inventory_run_quality_generator")


def evaluate_publisher_inventory_run_quality(
    request: PublisherInventoryRunQualityEvaluationRequest,
    ctx: RunContext,
) -> PublisherInventoryRunQualitySummary:
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="publisher_inventory_run_quality_start",
            module=logger.name,
            fields={
                "publisher_name": request.publisher_name,
                "normalized_url": request.normalized_url,
                "route_kind": request.route_kind,
                "used_memory_route": request.used_memory_route,
                "page_count": request.page_count,
                "current_report_count": request.current_report_count,
                "previous_report_count": request.previous_report_count,
                "raw_new_report_count": request.raw_new_report_count,
                "screened_new_report_count": request.screened_new_report_count,
                "qualified_new_report_count": request.qualified_new_report_count,
                "coverage_verdict": request.coverage_validation.verdict,
                "snapshot_changed": request.snapshot_changed,
            },
        )
    )
    summary = _evaluate(request)
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="publisher_inventory_run_quality_complete",
            module=logger.name,
            fields={
                "publisher_name": request.publisher_name,
                "normalized_url": request.normalized_url,
                "outcome": summary.outcome,
                "status": summary.status,
                "quality_band": summary.quality_band,
                "recommended_route_kind": summary.recommended_route_kind,
                "requires_review": summary.requires_review,
            },
        )
    )
    return summary


def _evaluate(
    request: PublisherInventoryRunQualityEvaluationRequest,
) -> PublisherInventoryRunQualitySummary:
    coverage = request.coverage_validation
    status = _status_for_coverage(coverage)
    quality_band = _quality_band_for_coverage(coverage)
    recommended_route_kind, recommended_route_reason = _recommended_route(
        request, coverage
    )
    requires_review = coverage.verdict in {
        "undercoverage_regression",
        "unreachable_delta_failure",
        "unreachable_delta_tolerated",
        "raw_only_delta_rejected",
    }
    return PublisherInventoryRunQualitySummary(
        schema_version="1.0",
        outcome=coverage.verdict,
        status=status,
        quality_band=quality_band,
        route_kind=request.route_kind,
        recommended_route_kind=recommended_route_kind,
        used_memory_route=request.used_memory_route,
        page_count=request.page_count,
        raw_candidate_count=request.raw_candidate_count,
        current_report_count=request.current_report_count,
        previous_report_count=request.previous_report_count,
        raw_new_report_count=request.raw_new_report_count,
        screened_new_report_count=request.screened_new_report_count,
        qualified_new_report_count=request.qualified_new_report_count,
        snapshot_changed=request.snapshot_changed,
        requires_review=requires_review,
        recommended_route_reason=recommended_route_reason,
        summary=_summary_text(request, coverage, quality_band),
        candidate_provenance_counts=dict(
            sorted(request.candidate_provenance_counts.items())
        ),
    )


def _status_for_coverage(
    coverage: PublisherInventoryCoverageValidationResponse,
) -> str:
    if coverage.should_raise_error and coverage.error_code:
        return f"failed:{coverage.error_code}"
    if coverage.no_report_assets_detected:
        return "passed:no_report_assets"
    return "passed"


def _quality_band_for_coverage(
    coverage: PublisherInventoryCoverageValidationResponse,
) -> str:
    if coverage.verdict == "accepted":
        return "high"
    if coverage.verdict in {
        "no_report_assets",
        "raw_only_delta_rejected",
        "unreachable_delta_tolerated",
    }:
        return "medium"
    return "low"


def _recommended_route(
    request: PublisherInventoryRunQualityEvaluationRequest,
    coverage: PublisherInventoryCoverageValidationResponse,
) -> tuple[str, str]:
    if coverage.verdict in {
        "undercoverage_regression",
        "unreachable_delta_failure",
        "unreachable_delta_tolerated",
        "raw_only_delta_rejected",
    }:
        return (
            "browser_render",
            "Recent drift or incomplete deltas favor the stronger browser-render route on the next run.",
        )
    if (
        request.route_kind == "http_parse"
        and request.page_count <= 1
        and (request.current_report_count <= 2 or request.raw_new_report_count == 0)
    ):
        return (
            "browser_render",
            "The last HTTP run was shallow, so the next run should prefer browser traversal if deeper coverage is needed.",
        )
    return (
        request.route_kind,
        "The latest run quality supports reusing the same primary route kind.",
    )


def _summary_text(
    request: PublisherInventoryRunQualityEvaluationRequest,
    coverage: PublisherInventoryCoverageValidationResponse,
    quality_band: str,
) -> str:
    return (
        f"{quality_band} quality via {request.route_kind}: "
        f"{request.current_report_count} current items, "
        f"{request.raw_new_report_count} raw deltas, "
        f"{request.qualified_new_report_count} qualified deltas, "
        f"coverage verdict {coverage.verdict}."
    )
