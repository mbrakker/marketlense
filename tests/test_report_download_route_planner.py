from __future__ import annotations

from src.contracts.browser_download import (
    PublisherDownloadRouteMemory,
    ReportDownloadRoutePlanRequest,
)
from src.contracts.publisher_inventory import PublisherInventoryCandidateTrace
from src.orchestrators._report_download_route_planner import plan_report_download_routes


def test_plan_report_download_routes_prefers_email_form_for_tracker_redirect(
    run_context,
) -> None:
    response = plan_report_download_routes(
        ReportDownloadRoutePlanRequest(
            schema_version="1.0",
            normalized_url=(
                "https://trk.example.com/click?redirect="
                "https%3A%2F%2Fwww.algolia.com%2Fresources%2Fasset%2Fwhy-agentic-ai-is-your-next-priority"
            ),
            remembered_route=None,
            candidate_trace=PublisherInventoryCandidateTrace(
                schema_version="1.0",
                canonical_url="https://trk.example.com/click?id=123",
                title="Algolia asset",
                discovered_on_page_number=1,
                source_page_urls=["https://www.algolia.com/resources"],
                discovery_provenances=["browser_dom"],
                pdf_url=None,
                published_at_text=None,
                max_confidence=0.81,
            ),
            publisher_discovery_route_kind="browser_render",
            publisher_recommended_discovery_route_kind="browser_render",
        ),
        run_context,
    )

    assert response.steps[0].route_family == "browser_email_form"
    assert response.steps[0].attempt_url == (
        "https://www.algolia.com/resources/asset/why-agentic-ai-is-your-next-priority"
    )


def test_plan_report_download_routes_does_not_reuse_weak_salvaged_memory(
    run_context,
) -> None:
    response = plan_report_download_routes(
        ReportDownloadRoutePlanRequest(
            schema_version="1.0",
            normalized_url="https://example.com/report",
            remembered_route=PublisherDownloadRouteMemory(
                schema_version="1.0",
                route_kind="pdf_download",
                route_summary="Open the report page and click download.",
                outcome="downloaded",
                route_family="browser_pdf_click",
                route_status="verified",
                resolved_target_url="https://example.com/report",
                attempts=1,
                verified_successes=1,
                last_n_outcomes=["downloaded"],
                confidence_score=0.5,
                browser_had_structured_result=False,
                onsite_completeness_status=None,
            ),
            candidate_trace=None,
            publisher_discovery_route_kind=None,
            publisher_recommended_discovery_route_kind=None,
        ),
        run_context,
    )

    assert response.steps[0].step_name != "report_download_with_memory_route"


def test_plan_report_download_routes_does_not_reuse_incomplete_onsite_memory(
    run_context,
) -> None:
    response = plan_report_download_routes(
        ReportDownloadRoutePlanRequest(
            schema_version="1.0",
            normalized_url="https://example.com/research/longread",
            remembered_route=PublisherDownloadRouteMemory(
                schema_version="1.0",
                route_kind="onsite_report",
                route_summary="Open the longread and capture it.",
                outcome="captured",
                route_family="browser_onsite_report",
                route_status="verified",
                resolved_target_url="https://example.com/research/longread",
                attempts=3,
                verified_successes=2,
                last_n_outcomes=["captured", "captured"],
                confidence_score=0.9,
                browser_had_structured_result=True,
                onsite_completeness_status="partial",
            ),
            candidate_trace=None,
            publisher_discovery_route_kind=None,
            publisher_recommended_discovery_route_kind=None,
        ),
        run_context,
    )

    assert response.steps[0].step_name != "report_download_with_memory_route"


def test_plan_report_download_routes_prefers_pdf_click_for_resource_report_pages(
    run_context,
) -> None:
    response = plan_report_download_routes(
        ReportDownloadRoutePlanRequest(
            schema_version="1.0",
            normalized_url="https://www.bigcommerce.com/resources/reports/global-b2b-buyer-report-cdl-report",
            remembered_route=None,
            candidate_trace=None,
            publisher_discovery_route_kind=None,
            publisher_recommended_discovery_route_kind=None,
        ),
        run_context,
    )

    assert response.steps[-1].route_family == "browser_pdf_click"


def test_plan_report_download_routes_keeps_onsite_for_insights_longread(
    run_context,
) -> None:
    response = plan_report_download_routes(
        ReportDownloadRoutePlanRequest(
            schema_version="1.0",
            normalized_url="https://brandfinance.com/insights/global-soft-power-index-which-nations-lead-global-perceptions-of-innovation-in-2026",
            remembered_route=None,
            candidate_trace=None,
            publisher_discovery_route_kind=None,
            publisher_recommended_discovery_route_kind=None,
        ),
        run_context,
    )

    assert response.steps[-1].route_family == "browser_onsite_report"


def test_plan_report_download_routes_canonicalizes_email_memory_route_family(
    run_context,
) -> None:
    response = plan_report_download_routes(
        ReportDownloadRoutePlanRequest(
            schema_version="1.0",
            normalized_url="https://www.bigcommerce.com/resources/reports/global-b2b-buyer-report-cdl-report",
            remembered_route=PublisherDownloadRouteMemory(
                schema_version="1.0",
                route_kind="email_delivery",
                route_summary="Open the report page, fill the form, and submit it.",
                outcome="email_requested",
                route_family="browser_pdf_click",
                route_status="verified",
                resolved_target_url="https://www.bigcommerce.com/resources/reports/global-b2b-buyer-report-cdl-report",
                attempts=3,
                verified_successes=1,
                last_n_outcomes=["email_requested"],
                confidence_score=0.46,
                browser_had_structured_result=True,
                onsite_completeness_status=None,
            ),
            candidate_trace=None,
            publisher_discovery_route_kind=None,
            publisher_recommended_discovery_route_kind=None,
        ),
        run_context,
    )

    assert response.steps[0].step_name == "report_download_with_memory_route"
    assert response.steps[0].route_family == "browser_email_form"


def test_plan_report_download_routes_uses_email_form_browser_fallback_from_memory(
    run_context,
) -> None:
    response = plan_report_download_routes(
        ReportDownloadRoutePlanRequest(
            schema_version="1.0",
            normalized_url="https://www.bigcommerce.com/resources/reports/global-b2b-buyer-report-cdl-report",
            remembered_route=PublisherDownloadRouteMemory(
                schema_version="1.0",
                route_kind="email_delivery",
                route_summary="Open the report page, fill the form, and submit it.",
                outcome="email_requested",
                route_family="browser_pdf_click",
                route_status="verified",
                resolved_target_url="https://www.bigcommerce.com/resources/reports/global-b2b-buyer-report-cdl-report",
                attempts=3,
                verified_successes=1,
                last_n_outcomes=["email_requested"],
                confidence_score=0.2,
                browser_had_structured_result=True,
                onsite_completeness_status=None,
            ),
            candidate_trace=None,
            publisher_discovery_route_kind=None,
            publisher_recommended_discovery_route_kind=None,
        ),
        run_context,
    )

    assert response.steps[0].step_name == "report_download_http_probe"
    assert response.steps[1].step_name == "report_download_browser_email_form"
    assert response.steps[1].route_family == "browser_email_form"
