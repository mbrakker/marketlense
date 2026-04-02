from __future__ import annotations

from src.contracts.publisher_inventory import (
    PublisherInventoryCoverageValidationRequest,
    PublisherInventoryRoutePlanRequest,
    PublisherInventoryRunQualityEvaluationRequest,
    PublisherInventoryRunQualitySummary,
)
from src.generators.publisher_inventory_coverage_generator import (
    validate_publisher_inventory_coverage,
)
from src.generators.publisher_inventory_run_quality_generator import (
    evaluate_publisher_inventory_run_quality,
)
from src.orchestrators._publisher_inventory_route_planner import (
    plan_publisher_inventory_routes,
)


def test_route_planner_prefers_browser_when_previous_quality_requires_review(
    run_context,
) -> None:
    response = plan_publisher_inventory_routes(
        PublisherInventoryRoutePlanRequest(
            schema_version="1.0",
            normalized_url="https://example.com/insights",
            force_browser=False,
            remembered_route_kind=None,
            remembered_route_summary=None,
            previous_run_quality_summary=PublisherInventoryRunQualitySummary(
                schema_version="1.0",
                outcome="undercoverage_regression",
                status="failed:publisher_inventory_browser_incomplete",
                quality_band="low",
                route_kind="http_parse",
                recommended_route_kind="browser_render",
                used_memory_route=False,
                page_count=1,
                raw_candidate_count=2,
                current_report_count=2,
                previous_report_count=10,
                raw_new_report_count=0,
                screened_new_report_count=0,
                qualified_new_report_count=0,
                snapshot_changed=False,
                requires_review=True,
                recommended_route_reason="Prefer browser after undercoverage.",
                summary="low quality via http_parse",
                candidate_provenance_counts={"http_parse": 2},
            ),
        ),
        run_context,
    )

    assert [step.route_kind_hint for step in response.steps] == [
        "browser_render",
        "http_parse",
    ]


def test_coverage_validation_rejects_raw_only_delta_with_previous_snapshot(
    run_context,
) -> None:
    response = validate_publisher_inventory_coverage(
        PublisherInventoryCoverageValidationRequest(
            schema_version="1.0",
            publisher_name="Example",
            normalized_url="https://example.com/insights",
            previous_snapshot_available=True,
            previous_page_count=4,
            previous_report_count=20,
            current_page_count=4,
            current_report_count=21,
            raw_new_report_count=3,
            screened_new_report_count=0,
            qualified_new_report_count=0,
            candidate_snapshot_changed=True,
            quality_rejection_reasons=[],
        ),
        run_context,
    )

    assert response.verdict == "raw_only_delta_rejected"
    assert response.snapshot_allowed is False
    assert response.should_raise_error is False


def test_run_quality_evaluation_marks_rejected_delta_for_review(run_context) -> None:
    coverage = validate_publisher_inventory_coverage(
        PublisherInventoryCoverageValidationRequest(
            schema_version="1.0",
            publisher_name="Example",
            normalized_url="https://example.com/insights",
            previous_snapshot_available=True,
            previous_page_count=3,
            previous_report_count=12,
            current_page_count=3,
            current_report_count=12,
            raw_new_report_count=2,
            screened_new_report_count=0,
            qualified_new_report_count=0,
            candidate_snapshot_changed=True,
            quality_rejection_reasons=[],
        ),
        run_context,
    )

    summary = evaluate_publisher_inventory_run_quality(
        PublisherInventoryRunQualityEvaluationRequest(
            schema_version="1.0",
            publisher_name="Example",
            normalized_url="https://example.com/insights",
            route_kind="http_parse",
            used_memory_route=False,
            page_count=3,
            raw_candidate_count=12,
            current_report_count=12,
            previous_report_count=12,
            raw_new_report_count=2,
            screened_new_report_count=0,
            qualified_new_report_count=0,
            snapshot_changed=False,
            coverage_validation=coverage,
            candidate_provenance_counts={"http_parse": 12},
        ),
        run_context,
    )

    assert summary.quality_band == "medium"
    assert summary.requires_review is True
    assert summary.recommended_route_kind == "browser_render"
