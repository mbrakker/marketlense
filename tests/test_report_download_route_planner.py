from __future__ import annotations

from src.contracts.browser_download import (
    BrowserDownloadRouteStep,
    PublisherDownloadRouteMemory,
    PublisherDownloadRoutePolicySignal,
    ReportDownloadRoutePlanRequest,
)
from src.contracts.publisher_inventory import PublisherInventoryCandidateTrace
from src.orchestrators._report_download_orchestrator.route_planner import plan_report_download_routes


def test_plan_report_download_routes_prefers_email_form_for_tracker_redirect(
    run_context,
) -> None:
    response = plan_report_download_routes(
        ReportDownloadRoutePlanRequest(
            schema_version="1.0",
            normalized_url=(
                "https://trk.example.com/click?redirect="
                "https%3A%2F%2Fexample.com%2Fresources%2Fasset%2Fwhy-agentic-ai-is-your-next-priority"
            ),
            remembered_route=None,
            candidate_trace=PublisherInventoryCandidateTrace(
                schema_version="1.0",
                canonical_url="https://trk.example.com/click?id=123",
                title="Report asset",
                discovered_on_page_number=1,
                source_page_urls=["https://example.com/resources"],
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
        "https://example.com/resources/asset/why-agentic-ai-is-your-next-priority"
    )


def test_plan_report_download_routes_uses_learned_policy_to_rank_browser_email_first(
    run_context,
) -> None:
    response = plan_report_download_routes(
        ReportDownloadRoutePlanRequest(
            schema_version="1.0",
            normalized_url="https://example.com/brand-study",
            remembered_route=PublisherDownloadRouteMemory(
                schema_version="1.0",
                route_kind="pdf_download",
                route_summary="Static click route was inconclusive.",
                outcome="email_required",
                route_family="browser_pdf_click",
                route_status="inferred",
                resolved_target_url="https://example.com/brand-study",
                attempts=4,
                verified_successes=2,
                last_n_outcomes=["email_requested", "downloaded", "email_required"],
                confidence_score=0.3,
                browser_had_structured_result=True,
                onsite_completeness_status=None,
                route_policy=[
                    PublisherDownloadRoutePolicySignal(
                        schema_version="1.0",
                        route_family="browser_email_form",
                        route_kind="email_delivery",
                        attempts=3,
                        verified_successes=2,
                        blocked_attempts=0,
                        success_rate=0.667,
                        confidence_score=0.817,
                        rank_score=0.803,
                        last_outcome="email_requested",
                        last_route_status="verified",
                        last_blocked_reason=None,
                        recent_outcomes=["email_requested", "email_requested"],
                    ),
                    PublisherDownloadRoutePolicySignal(
                        schema_version="1.0",
                        route_family="http_pdf_probe",
                        route_kind="pdf_download",
                        attempts=2,
                        verified_successes=0,
                        blocked_attempts=1,
                        success_rate=0.0,
                        confidence_score=0.0,
                        rank_score=0.0,
                        last_outcome="email_required",
                        last_route_status="inferred",
                        last_blocked_reason="blocked_missing_identity_field",
                        recent_outcomes=["email_required"],
                    ),
                ],
            ),
            candidate_trace=None,
            publisher_discovery_route_kind=None,
            publisher_recommended_discovery_route_kind=None,
        ),
        run_context,
    )

    assert response.steps[0].step_name == "report_download_policy_browser_email_form"
    assert response.steps[0].route_family == "browser_email_form"
    assert response.steps[0].route_kind_hint == "email_delivery"
    assert response.steps[0].uses_memory_route is False
    assert (
        "Publisher route-policy history prefers browser_email_form"
        in response.planning_reason
    )


def test_plan_report_download_routes_uses_learned_policy_to_override_browser_first_hint(
    run_context,
) -> None:
    response = plan_report_download_routes(
        ReportDownloadRoutePlanRequest(
            schema_version="1.0",
            normalized_url="https://example.com/reports/latest-study",
            remembered_route=PublisherDownloadRouteMemory(
                schema_version="1.0",
                route_kind="pdf_download",
                route_summary="HTTP probe has historically found embedded PDFs.",
                outcome="downloaded",
                route_family="http_pdf_probe",
                route_status="inferred",
                resolved_target_url="https://example.com/reports/latest-study",
                attempts=4,
                verified_successes=2,
                last_n_outcomes=["downloaded", "downloaded", "email_required"],
                confidence_score=0.3,
                browser_had_structured_result=False,
                onsite_completeness_status=None,
                route_policy=[
                    PublisherDownloadRoutePolicySignal(
                        schema_version="1.0",
                        route_family="http_pdf_probe",
                        route_kind="pdf_download",
                        attempts=3,
                        verified_successes=2,
                        blocked_attempts=0,
                        success_rate=0.667,
                        confidence_score=0.967,
                        rank_score=0.893,
                        last_outcome="downloaded",
                        last_route_status="verified",
                        last_blocked_reason=None,
                        recent_outcomes=["downloaded", "downloaded"],
                    )
                ],
            ),
            candidate_trace=PublisherInventoryCandidateTrace(
                schema_version="1.0",
                canonical_url="https://example.com/reports/latest-study",
                title="Latest study",
                discovered_on_page_number=1,
                source_page_urls=["https://example.com/reports"],
                discovery_provenances=["browser_dom"],
                pdf_url=None,
                published_at_text=None,
                max_confidence=0.8,
            ),
            publisher_discovery_route_kind="browser_render",
            publisher_recommended_discovery_route_kind="browser_render",
        ),
        run_context,
    )

    assert response.steps[0].route_family == "http_pdf_probe"
    assert response.steps[1].route_family.startswith("browser_")
    assert (
        "Publisher route-policy history prefers http_pdf_probe"
        in response.planning_reason
    )


def test_plan_report_download_routes_uses_publisher_policy_for_new_report_url(
    run_context,
) -> None:
    response = plan_report_download_routes(
        ReportDownloadRoutePlanRequest(
            schema_version="1.0",
            normalized_url="https://example.com/research/industry-outlook",
            remembered_route=PublisherDownloadRouteMemory(
                schema_version="1.0",
                route_kind="",
                route_summary=(
                    "No exact URL route memory is available; publisher-scope route "
                    "policy is available."
                ),
                outcome="policy_only",
                route_family="",
                route_status="inferred",
                resolved_target_url="https://example.com/research/industry-outlook",
                attempts=0,
                verified_successes=0,
                last_n_outcomes=[],
                confidence_score=0.0,
                exact_route_found=False,
                browser_had_structured_result=False,
                onsite_completeness_status=None,
                route_policy=[],
                publisher_route_policy=[
                    PublisherDownloadRoutePolicySignal(
                        schema_version="1.0",
                        route_family="browser_onsite_report",
                        route_kind="onsite_report",
                        attempts=4,
                        verified_successes=4,
                        blocked_attempts=0,
                        success_rate=1.0,
                        confidence_score=1.0,
                        rank_score=1.0,
                        last_outcome="captured",
                        last_route_status="verified",
                        last_blocked_reason=None,
                        recent_outcomes=["captured", "captured", "captured"],
                    )
                ],
            ),
            candidate_trace=PublisherInventoryCandidateTrace(
                schema_version="1.0",
                canonical_url="https://example.com/research/industry-outlook",
                title="Industry outlook",
                discovered_on_page_number=1,
                source_page_urls=["https://example.com/research"],
                discovery_provenances=[],
                pdf_url=None,
                published_at_text=None,
                max_confidence=0.8,
            ),
            publisher_discovery_route_kind=None,
            publisher_recommended_discovery_route_kind=None,
        ),
        run_context,
    )

    assert response.steps[0].step_name == "report_download_policy_browser_onsite_report"
    assert response.steps[0].route_family == "browser_onsite_report"
    assert response.steps[0].route_kind_hint == "onsite_report"
    assert "Publisher-domain route-policy history prefers" in response.planning_reason


def test_plan_report_download_routes_sends_report_id_detail_to_email_form(
    run_context,
) -> None:
    response = plan_report_download_routes(
        ReportDownloadRoutePlanRequest(
            schema_version="1.0",
            normalized_url="https://yougov.com/reports/51871-european-retail-landscape-report-en-2025",
            remembered_route=None,
            candidate_trace=PublisherInventoryCandidateTrace(
                schema_version="1.0",
                canonical_url="https://yougov.com/reports/51871-european-retail-landscape-report-en-2025",
                title="European Retail Landscape Report 2025",
                discovered_on_page_number=3,
                source_page_urls=["https://yougov.com/reports"],
                discovery_provenances=[],
                pdf_url=None,
                published_at_text=None,
                max_confidence=0.8,
            ),
            publisher_discovery_route_kind=None,
            publisher_recommended_discovery_route_kind=None,
        ),
        run_context,
    )

    assert response.steps[-1].route_family == "browser_email_form"
    assert response.steps[-1].route_kind_hint == "email_delivery"
    assert response.steps[-1].attempt_url == (
        "https://yougov.com/reports/51871-european-retail-landscape-report-en-2025"
    )


def test_plan_report_download_routes_sends_generic_whitepaper_to_email_form(
    run_context,
) -> None:
    response = plan_report_download_routes(
        ReportDownloadRoutePlanRequest(
            schema_version="1.0",
            normalized_url=(
                "https://example.com/whitepapers/"
                "the-right-aisle-strategy-for-retail-success/"
            ),
            remembered_route=None,
            candidate_trace=PublisherInventoryCandidateTrace(
                schema_version="1.0",
                canonical_url=(
                    "https://example.com/whitepapers/"
                    "the-right-aisle-strategy-for-retail-success/"
                ),
                title="The Right Aisle Strategy for Retail Success",
                discovered_on_page_number=1,
                source_page_urls=["https://example.com/whitepapers/"],
                discovery_provenances=[],
                pdf_url=None,
                published_at_text=None,
                max_confidence=0.8,
            ),
            publisher_discovery_route_kind=None,
            publisher_recommended_discovery_route_kind=None,
        ),
        run_context,
    )

    assert response.steps[-1].step_name == "report_download_browser_email_form"
    assert response.steps[-1].route_family == "browser_email_form"
    assert response.steps[-1].route_kind_hint == "email_delivery"


def test_plan_report_download_routes_keeps_algorithm_research_url_on_onsite_route(
    run_context,
) -> None:
    response = plan_report_download_routes(
        ReportDownloadRoutePlanRequest(
            schema_version="1.0",
            normalized_url=(
                "https://www.brightlocal.com/research/"
                "november-2025-local-consumer-review-survey/"
            ),
            remembered_route=None,
            candidate_trace=PublisherInventoryCandidateTrace(
                schema_version="1.0",
                canonical_url=(
                    "https://www.brightlocal.com/research/"
                    "november-2025-local-consumer-review-survey/"
                ),
                title="November 2025 Local Consumer Review Survey",
                discovered_on_page_number=4,
                source_page_urls=[
                    "https://www.brightlocal.com/research/page/4/",
                ],
                discovery_provenances=[],
                pdf_url=None,
                published_at_text=None,
                max_confidence=0.78,
            ),
            publisher_discovery_route_kind=None,
            publisher_recommended_discovery_route_kind=None,
        ),
        run_context,
    )

    assert response.steps[-1].route_family == "browser_onsite_report"
    assert response.steps[-1].attempt_url == (
        "https://www.brightlocal.com/research/"
        "november-2025-local-consumer-review-survey/"
    )


def test_plan_report_download_routes_ignores_weak_email_memory_for_onsite_research_url(
    run_context,
) -> None:
    response = plan_report_download_routes(
        ReportDownloadRoutePlanRequest(
            schema_version="1.0",
            normalized_url=(
                "https://www.brightlocal.com/research/"
                "november-2019-local-algorithm-fluctuation"
            ),
            remembered_route=PublisherDownloadRouteMemory(
                schema_version="1.0",
                route_kind="email_delivery",
                route_summary="Navigated to the report URL and captured the on-site content.",
                outcome="email_required",
                route_family="browser_email_form",
                route_status="inferred",
                resolved_target_url=(
                    "https://www.brightlocal.com/research/"
                    "november-2019-local-algorithm-fluctuation"
                ),
                attempts=1,
                verified_successes=0,
                last_n_outcomes=["email_required"],
                confidence_score=0.25,
                browser_had_structured_result=True,
                onsite_completeness_status="partial",
            ),
            candidate_trace=PublisherInventoryCandidateTrace(
                schema_version="1.0",
                canonical_url=(
                    "https://www.brightlocal.com/research/"
                    "november-2019-local-algorithm-fluctuation"
                ),
                title="Are We Experiencing a Local Algorithm Update?",
                discovered_on_page_number=4,
                source_page_urls=["https://www.brightlocal.com/research/page/4"],
                discovery_provenances=[],
                pdf_url=None,
                published_at_text=None,
                max_confidence=0.8,
            ),
            publisher_discovery_route_kind=None,
            publisher_recommended_discovery_route_kind=None,
        ),
        run_context,
    )

    assert response.steps[-1].route_family == "browser_onsite_report"
    assert response.steps[-1].uses_memory_route is False


def test_plan_report_download_routes_treats_reports_slug_as_detail_page(
    run_context,
) -> None:
    response = plan_report_download_routes(
        ReportDownloadRoutePlanRequest(
            schema_version="1.0",
            normalized_url="https://www.gwi.com/reports/south-africa-consumers",
            remembered_route=None,
            candidate_trace=PublisherInventoryCandidateTrace(
                schema_version="1.0",
                canonical_url="https://www.gwi.com/reports/south-africa-consumers",
                title="Understanding consumers in South Africa",
                discovered_on_page_number=8,
                source_page_urls=["https://www.gwi.com/reports?page_num=8"],
                discovery_provenances=[],
                pdf_url=None,
                published_at_text=None,
                max_confidence=0.8,
            ),
            publisher_discovery_route_kind=None,
            publisher_recommended_discovery_route_kind=None,
        ),
        run_context,
    )

    assert response.steps[-1].route_family == "browser_pdf_click"
    assert (
        response.steps[-1].attempt_url
        == "https://www.gwi.com/reports/south-africa-consumers"
    )


def test_plan_report_download_routes_treats_guide_article_as_onsite_report(
    run_context,
) -> None:
    response = plan_report_download_routes(
        ReportDownloadRoutePlanRequest(
            schema_version="1.0",
            normalized_url=(
                "https://impact.com/commerce-content/"
                "guide-to-building-a-high-performance-content-operation"
            ),
            remembered_route=None,
            candidate_trace=PublisherInventoryCandidateTrace(
                schema_version="1.0",
                canonical_url=(
                    "https://impact.com/commerce-content/"
                    "guide-to-building-a-high-performance-content-operation"
                ),
                title="The B2B Guide to Building a High-Performance Content Operations Workflow",
                discovered_on_page_number=18,
                source_page_urls=["https://impact.com/search?ft%5B0%5D=report&pg=18"],
                discovery_provenances=[],
                pdf_url=None,
                published_at_text=None,
                max_confidence=0.8,
            ),
            publisher_discovery_route_kind=None,
            publisher_recommended_discovery_route_kind=None,
        ),
        run_context,
    )

    assert response.steps[-1].route_family == "browser_onsite_report"
    assert response.steps[-1].route_kind_hint == "onsite_report"


def test_plan_report_download_routes_treats_singular_insight_detail_as_onsite_report(
    run_context,
) -> None:
    response = plan_report_download_routes(
        ReportDownloadRoutePlanRequest(
            schema_version="1.0",
            normalized_url="https://www.vml.com/insight/new-trend-report-the-single-age",
            remembered_route=None,
            candidate_trace=PublisherInventoryCandidateTrace(
                schema_version="1.0",
                canonical_url="https://www.vml.com/insight/new-trend-report-the-single-age",
                title="New trend report: The Single Age",
                discovered_on_page_number=2,
                source_page_urls=[
                    "https://www.vml.com/expertise/intelligence/trend-reports"
                ],
                discovery_provenances=[],
                pdf_url=None,
                published_at_text=None,
                max_confidence=0.8,
            ),
            publisher_discovery_route_kind=None,
            publisher_recommended_discovery_route_kind=None,
        ),
        run_context,
    )

    assert response.steps[-1].route_family == "browser_onsite_report"
    assert response.steps[-1].route_kind_hint == "onsite_report"
    assert response.steps[-1].attempt_url == (
        "https://www.vml.com/insight/new-trend-report-the-single-age"
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


def test_plan_report_download_routes_sends_resource_report_pages_to_email_form(
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

    assert response.steps[-1].route_family == "browser_email_form"
    assert response.steps[-1].route_kind_hint == "email_delivery"


def test_plan_report_download_routes_sends_nested_report_title_page_to_email_form(
    run_context,
) -> None:
    response = plan_report_download_routes(
        ReportDownloadRoutePlanRequest(
            schema_version="1.0",
            normalized_url=(
                "https://www.nielsen.com/insights/2024/"
                "maximizing-roi-in-a-fragmented-world-nielsen-annual-marketing-report"
            ),
            remembered_route=None,
            candidate_trace=PublisherInventoryCandidateTrace(
                schema_version="1.0",
                canonical_url=(
                    "https://www.nielsen.com/insights/2024/"
                    "maximizing-roi-in-a-fragmented-world-nielsen-annual-marketing-report"
                ),
                title="2024 Annual Marketing Report",
                discovered_on_page_number=3,
                source_page_urls=["https://www.nielsen.com/insights/type/report"],
                discovery_provenances=[],
                pdf_url=None,
                published_at_text=None,
                max_confidence=0.8,
            ),
            publisher_discovery_route_kind=None,
            publisher_recommended_discovery_route_kind=None,
        ),
        run_context,
    )

    assert response.steps[-1].route_family == "browser_email_form"
    assert response.steps[-1].route_kind_hint == "email_delivery"


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


def test_plan_report_download_routes_treats_year_in_review_as_onsite_longread(
    run_context,
) -> None:
    response = plan_report_download_routes(
        ReportDownloadRoutePlanRequest(
            schema_version="1.0",
            normalized_url="https://example.com/year-in-review-2022",
            remembered_route=None,
            candidate_trace=PublisherInventoryCandidateTrace(
                schema_version="1.0",
                canonical_url="https://example.com/year-in-review-2022",
                title="Year in Review 2022",
                discovered_on_page_number=2,
                source_page_urls=["https://example.com/reports"],
                discovery_provenances=[],
                pdf_url=None,
                published_at_text=None,
                max_confidence=0.8,
            ),
            publisher_discovery_route_kind=None,
            publisher_recommended_discovery_route_kind=None,
        ),
        run_context,
    )

    assert response.steps[-1].route_family == "browser_onsite_report"
    assert response.steps[-1].route_kind_hint == "onsite_report"


def test_plan_report_download_routes_uses_direct_detail_url_instead_of_source_listing(
    run_context,
) -> None:
    response = plan_report_download_routes(
        ReportDownloadRoutePlanRequest(
            schema_version="1.0",
            normalized_url=(
                "https://example.com/our-insights/"
                "bs-commercial-industrial-services-m-and-a-trends-q1-2026"
            ),
            remembered_route=None,
            candidate_trace=PublisherInventoryCandidateTrace(
                schema_version="1.0",
                canonical_url=(
                    "https://example.com/our-insights/"
                    "bs-commercial-industrial-services-m-and-a-trends-q1-2026"
                ),
                title="Commercial & Industrial Services",
                discovered_on_page_number=1,
                source_page_urls=["https://example.com/our-insights"],
                discovery_provenances=[],
                pdf_url=None,
                published_at_text=None,
                max_confidence=0.8,
            ),
            publisher_discovery_route_kind=None,
            publisher_recommended_discovery_route_kind=None,
        ),
        run_context,
    )

    assert response.steps[-1].route_family == "browser_pdf_click"
    assert response.steps[-1].attempt_url == (
        "https://example.com/our-insights/"
        "bs-commercial-industrial-services-m-and-a-trends-q1-2026"
    )


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
                route_steps=[
                    BrowserDownloadRouteStep(
                        schema_version="1.0",
                        index=0,
                        action="click",
                        target_text="Download report",
                        target_role="button",
                        target_url="https://www.bigcommerce.com/resources/reports/global-b2b-buyer-report-cdl-report",
                        result="opened form",
                    )
                ],
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

    assert response.steps[0].step_name == "report_download_browser_email_form"
    assert response.steps[0].route_family == "browser_email_form"
    assert response.steps[0].route_hint == (
        "Open the report page, fill the form, and submit it."
    )
    assert response.steps[0].route_step_hints[0].target_text == "Download report"


def test_plan_report_download_routes_prefers_email_form_for_direct_detail_with_email_memory(
    run_context,
) -> None:
    response = plan_report_download_routes(
        ReportDownloadRoutePlanRequest(
            schema_version="1.0",
            normalized_url=(
                "https://www.mintel.com/insights/food-and-drink/"
                "global-food-and-drink-trends"
            ),
            remembered_route=PublisherDownloadRouteMemory(
                schema_version="1.0",
                route_kind="email_delivery",
                route_summary="Open the page, fill the form, and submit it.",
                outcome="email_required",
                route_family="browser_email_form",
                route_status="inferred",
                resolved_target_url=(
                    "https://www.mintel.com/insights/food-and-drink/"
                    "global-food-and-drink-trends"
                ),
                route_steps=[
                    BrowserDownloadRouteStep(
                        schema_version="1.0",
                        index=0,
                        action="click",
                        target_text="Download insights",
                        target_role="button",
                        target_url=(
                            "https://www.mintel.com/insights/food-and-drink/"
                            "global-food-and-drink-trends"
                        ),
                        result="opened form",
                    )
                ],
                attempts=1,
                verified_successes=0,
                last_n_outcomes=["email_required"],
                confidence_score=0.4,
                browser_had_structured_result=True,
                onsite_completeness_status=None,
            ),
            candidate_trace=PublisherInventoryCandidateTrace(
                schema_version="1.0",
                canonical_url=(
                    "https://www.mintel.com/insights/food-and-drink/"
                    "global-food-and-drink-trends"
                ),
                title="2026 Global Food & Drink Predictions",
                discovered_on_page_number=1,
                source_page_urls=["https://www.mintel.com/insights/consumer-research"],
                discovery_provenances=[],
                pdf_url=None,
                published_at_text=None,
                max_confidence=0.8,
            ),
            publisher_discovery_route_kind=None,
            publisher_recommended_discovery_route_kind=None,
        ),
        run_context,
    )

    assert response.steps[0].step_name == "report_download_browser_email_form"
    assert response.steps[0].route_family == "browser_email_form"
    assert response.steps[0].attempt_url == (
        "https://www.mintel.com/insights/food-and-drink/global-food-and-drink-trends"
    )
    assert (
        response.steps[0].route_hint == "Open the page, fill the form, and submit it."
    )
    assert response.steps[0].route_step_hints == []
