from __future__ import annotations

from src.contracts.browser_download import (
    PublisherDownloadRouteMemory,
    ReportDownloadRoutePlanRequest,
)
from src.orchestrators._report_download_orchestrator.route_planner import (
    plan_report_download_routes,
)


def test_plan_report_download_routes_blocks_browser_memory_for_direct_pdf_url(
    run_context,
) -> None:
    response = plan_report_download_routes(
        ReportDownloadRoutePlanRequest(
            schema_version="1.0",
            normalized_url="https://www.w3.org/reports/sample.pdf",
            remembered_route=PublisherDownloadRouteMemory(
                schema_version="1.0",
                route_kind="pdf_download",
                route_summary="Clicked a PDF CTA in browser.",
                outcome="downloaded",
                route_family="browser_pdf_click",
                route_status="verified",
                resolved_target_url="https://www.w3.org/reports/sample.pdf",
                attempts=5,
                verified_successes=5,
                last_n_outcomes=["downloaded"],
                confidence_score=0.95,
                browser_had_structured_result=True,
                onsite_completeness_status=None,
            ),
            candidate_trace=None,
            publisher_discovery_route_kind=None,
            publisher_recommended_discovery_route_kind=None,
        ),
        run_context,
    )

    assert response.steps[0].step_name == "report_download_direct_pdf_probe"
    assert response.steps[0].route_family == "direct_pdf_probe"
    assert [step.route_family for step in response.steps] == [
        "direct_pdf_probe",
        "http_pdf_probe",
    ]
    assert (
        "browser_pdf_click:blocked:direct_pdf_request"
        in response.blocked_recovery_classes
    )
