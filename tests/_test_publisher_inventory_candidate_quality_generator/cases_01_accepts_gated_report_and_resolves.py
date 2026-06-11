# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403

def test_qualify_publisher_inventory_candidates_accepts_gated_report_and_resolves_title(
    caplog,
    assert_logs_have_required_fields,
    assert_no_defaulted_required_fields,
) -> None:
    candidate = _candidate(
        "https://convertgroup.com/reports_posts/greek-egrocery-s1-2024/",
        "Download report",
    )
    caplog.set_level(
        logging.INFO,
        logger="market_lense.publisher_inventory_candidate_quality_generator",
    )

    response = qualify_publisher_inventory_candidates(
        PublisherInventoryCandidateQualityRequest(
            schema_version="1.0",
            publisher_name="Convert Group",
            insights_url="https://convertgroup.com/reports",
            candidates=[candidate],
            settings=_settings(),
        ),
        _ctx(),
        inspection_client=lambda request, ctx: (
            PublisherInventoryLandingPageInspectionResponse(
                schema_version="1.0",
                observations=[
                    _observation(
                        canonical_url=candidate.canonical_url,
                        source_title=candidate.title,
                        final_url=candidate.canonical_url,
                        h1_title="Greek eGrocery S1 2024",
                        final_title="Greek eGrocery S1 2024 | Convert Group",
                        has_asset_type_term=True,
                        has_download_language=True,
                        has_gated_form=True,
                        has_document_structure=True,
                    )
                ],
            )
        ),
    )

    assert [item.canonical_url for item in response.approved_items] == [
        candidate.canonical_url
    ]
    assert response.approved_items[0].title == "Greek eGrocery S1 2024"
    assert response.rejected_items == []
    assert response.decisions[0].reason in {
        "gated_report_asset",
        "report_like_document_page",
    }
    assert_no_defaulted_required_fields(response.approved_items[0])
    assert_no_defaulted_required_fields(response.decisions[0])
    records = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == "market_lense.publisher_inventory_candidate_quality_generator"
    ]
    assert_logs_have_required_fields(records)

def test_qualify_publisher_inventory_candidates_accepts_printable_report_page() -> None:
    candidate = _candidate(
        "https://example.com/research/2026-outlook",
        "2026 Outlook",
    )

    response = qualify_publisher_inventory_candidates(
        PublisherInventoryCandidateQualityRequest(
            schema_version="1.0",
            publisher_name="Example Publisher",
            insights_url="https://example.com/insights",
            candidates=[candidate],
            settings=_settings(),
        ),
        _ctx(),
        inspection_client=lambda request, ctx: (
            PublisherInventoryLandingPageInspectionResponse(
                schema_version="1.0",
                observations=[
                    _observation(
                        canonical_url=candidate.canonical_url,
                        source_title=candidate.title,
                        final_url=candidate.canonical_url,
                        h1_title="2026 Global Outlook",
                        has_asset_type_term=True,
                        has_document_structure=True,
                        has_print_language=True,
                    )
                ],
            )
        ),
    )

    assert [item.title for item in response.approved_items] == ["2026 Global Outlook"]
    assert response.decisions[0].reason == "printable_report_page"

def test_qualify_publisher_inventory_candidates_accepts_structured_infographic_report_page() -> (
    None
):
    candidate = _candidate(
        "https://pubmatic.com/reports/quarterly-global-advertising-spend-trends-q4-2025/",
        "Quarterly Global Advertising Spend Trends: Q4 2025",
    )

    response = qualify_publisher_inventory_candidates(
        PublisherInventoryCandidateQualityRequest(
            schema_version="1.0",
            publisher_name="Pubmatic",
            insights_url="https://pubmatic.com/reports/",
            candidates=[candidate],
            settings=_settings(),
        ),
        _ctx(),
        inspection_client=lambda request, ctx: (
            PublisherInventoryLandingPageInspectionResponse(
                schema_version="1.0",
                observations=[
                    _observation(
                        canonical_url=candidate.canonical_url,
                        source_title=candidate.title,
                        final_url=candidate.canonical_url,
                        final_title="Q4 2025 Global Advertiser Ad Spend Trends | PubMatic Ad Spend Report",
                        h1_title="Quarterly Global Advertising Spend Trends: Q4 2025",
                        has_asset_type_term=True,
                        has_document_structure=True,
                        has_editorial_markers=True,
                    )
                ],
            )
        ),
    )

    assert [item.title for item in response.approved_items] == [
        "Quarterly Global Advertising Spend Trends: Q4 2025"
    ]
    assert response.decisions[0].reason == "printable_report_page"

def test_qualify_publisher_inventory_candidates_rejects_editorial_blog_post() -> None:
    candidate = _candidate(
        "https://example.com/blog/what-is-agentic-commerce",
        "What is agentic commerce? A guide for businesses",
    )

    response = qualify_publisher_inventory_candidates(
        PublisherInventoryCandidateQualityRequest(
            schema_version="1.0",
            publisher_name="Example Publisher",
            insights_url="https://example.com/insights",
            candidates=[candidate],
            settings=_settings(),
        ),
        _ctx(),
        inspection_client=lambda request, ctx: (
            PublisherInventoryLandingPageInspectionResponse(
                schema_version="1.0",
                observations=[
                    _observation(
                        canonical_url=candidate.canonical_url,
                        source_title=candidate.title,
                        final_url=candidate.canonical_url,
                        h1_title="What is agentic commerce?",
                        has_asset_type_term=True,
                        has_editorial_url_pattern=True,
                        has_editorial_markers=True,
                        has_related_posts=True,
                    )
                ],
            )
        ),
    )

    assert response.approved_items == []
    assert [item.canonical_url for item in response.rejected_items] == [
        candidate.canonical_url
    ]
    assert response.decisions[0].reason == "editorial_article_page"

def test_qualify_publisher_inventory_candidates_rejects_editorial_finance_insight_routes() -> (
    None
):
    candidate = _candidate(
        "https://www.example.com/insights/company-insights/from-boutique-to-benchmark",
        "From boutique to benchmark",
    )

    response = qualify_publisher_inventory_candidates(
        PublisherInventoryCandidateQualityRequest(
            schema_version="1.0",
            publisher_name="Example Publisher",
            insights_url="https://www.example.com/insights",
            candidates=[candidate],
            settings=_settings(),
        ),
        _ctx(),
        inspection_client=lambda request, ctx: (
            PublisherInventoryLandingPageInspectionResponse(
                schema_version="1.0",
                observations=[
                    _observation(
                        canonical_url=candidate.canonical_url,
                        source_title=candidate.title,
                        final_url=candidate.canonical_url,
                        h1_title="From boutique to benchmark",
                        has_asset_type_term=True,
                        has_price_or_purchase=True,
                    )
                ],
            )
        ),
    )

    assert response.approved_items == []
    assert [item.canonical_url for item in response.rejected_items] == [
        candidate.canonical_url
    ]
    assert response.decisions[0].reason == "editorial_article_page"

def test_qualify_publisher_inventory_candidates_rejects_dead_pages() -> None:
    candidate = _candidate(
        "https://example.com/resources/the-ce-scorecard",
        "The CE Scorecard",
    )

    response = qualify_publisher_inventory_candidates(
        PublisherInventoryCandidateQualityRequest(
            schema_version="1.0",
            publisher_name="Example Publisher",
            insights_url="https://example.com/insights",
            candidates=[candidate],
            settings=_settings(),
        ),
        _ctx(),
        inspection_client=lambda request, ctx: (
            PublisherInventoryLandingPageInspectionResponse(
                schema_version="1.0",
                observations=[
                    _observation(
                        canonical_url=candidate.canonical_url,
                        source_title=candidate.title,
                        final_url=candidate.canonical_url,
                        final_title="Page not found | Example",
                        fetch_error="404 Client Error",
                        has_dead_page_marker=True,
                    )
                ],
            )
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason == "dead_or_unreachable_landing_page"

def test_qualify_publisher_inventory_candidates_attaches_recovery_recipe_for_challenge() -> (
    None
):
    candidate = _candidate(
        "https://example.com/protected/asset-123",
        "Download now",
    )

    response = qualify_publisher_inventory_candidates(
        PublisherInventoryCandidateQualityRequest(
            schema_version="1.0",
            publisher_name="Example Publisher",
            insights_url="https://example.com/reports",
            candidates=[candidate],
            settings=_settings(),
        ),
        _ctx(),
        inspection_client=lambda request, ctx: (
            PublisherInventoryLandingPageInspectionResponse(
                schema_version="1.0",
                observations=[
                    _observation(
                        canonical_url=candidate.canonical_url,
                        source_title=candidate.title,
                        final_url=candidate.canonical_url,
                        final_title="Attention required",
                        fetch_error="Access denied",
                        has_dead_page_marker=True,
                        verification_class="challenge",
                        recovery_eligible=True,
                        source_surface_class="direct_detail",
                    )
                ],
            )
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].accepted is False
    assert response.decisions[0].source_surface_class == "direct_detail"
    assert response.decisions[0].recovery_recipe is not None
    assert response.decisions[0].recovery_recipe.recovery_action == "browser_retry"

def test_qualify_publisher_inventory_candidates_accepts_bot_protected_report_asset() -> (
    None
):
    candidate = _candidate(
        "https://www.adjust.com/resources/ebooks/mobile-app-trends-2026",
        "Mobile app trends 2026 edition",
    )

    response = qualify_publisher_inventory_candidates(
        PublisherInventoryCandidateQualityRequest(
            schema_version="1.0",
            publisher_name="Adjust",
            insights_url="https://www.adjust.com/resources/ebooks/",
            candidates=[candidate],
            settings=_settings(),
        ),
        _ctx(),
        inspection_client=lambda request, ctx: (
            PublisherInventoryLandingPageInspectionResponse(
                schema_version="1.0",
                observations=[
                    _observation(
                        canonical_url=candidate.canonical_url,
                        source_title=candidate.title,
                        final_url=candidate.canonical_url,
                        final_title="Vercel Security Checkpoint",
                        http_status_code=429,
                        has_dead_page_marker=True,
                    )
                ],
            )
        ),
    )

    assert [item.canonical_url for item in response.approved_items] == [
        candidate.canonical_url
    ]
    assert response.approved_items[0].title == "Mobile app trends 2026 edition"
    assert response.decisions[0].reason == "bot_protected_report_asset"

def test_qualify_publisher_inventory_candidates_rejects_editorial_detail_page_despite_report_archive_source() -> (
    None
):
    candidate = _candidate(
        "https://www.mastercardservices.com/en/advisors/economic-consulting/insights/keeping-times-how-anticipate-new-market-trends-and-adapt",
        "How to anticipate new market trends and adapt with confidence",
    )

    response = qualify_publisher_inventory_candidates(
        PublisherInventoryCandidateQualityRequest(
            schema_version="1.0",
            publisher_name="Mastercard services",
            insights_url="https://www.mastercardservices.com/en/resources/reports",
            candidates=[candidate],
            settings=_settings(),
        ),
        _ctx(),
        inspection_client=lambda request, ctx: (
            PublisherInventoryLandingPageInspectionResponse(
                schema_version="1.0",
                observations=[
                    _observation(
                        canonical_url=candidate.canonical_url,
                        source_title=candidate.title,
                        final_url=candidate.canonical_url,
                        final_title="Keeping up with the times: How to anticipate new market trends and adapt with confidence | Mastercard Services",
                        h1_title="How to anticipate new market trends and adapt with confidence",
                        has_asset_type_term=True,
                        has_editorial_markers=True,
                        has_contact_sales_cta=True,
                    )
                ],
            )
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason in {
        "editorial_article_page",
        "insufficient_report_signals",
    }

def test_qualify_publisher_inventory_candidates_rejects_bot_protected_editorial_article() -> (
    None
):
    candidate = _candidate(
        "https://www.bcg.com/publications/2026/ai-is-already-moving-the-logistics-industry-forward",
        "Article March 27, 2026 AI Is Already Moving the Logistics Industry Forward",
    )

    response = qualify_publisher_inventory_candidates(
        PublisherInventoryCandidateQualityRequest(
            schema_version="1.0",
            publisher_name="Boston Consulting Group (BCG)",
            insights_url="https://www.bcg.com/search?q=Reports&s=1",
            candidates=[candidate],
            settings=_settings(),
        ),
        _ctx(),
        inspection_client=lambda request, ctx: (
            PublisherInventoryLandingPageInspectionResponse(
                schema_version="1.0",
                observations=[
                    _observation(
                        canonical_url=candidate.canonical_url,
                        source_title=candidate.title,
                        final_url=candidate.canonical_url,
                        final_title="Access Denied",
                        http_status_code=403,
                        has_dead_page_marker=True,
                    )
                ],
            )
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason == "bot_protected_editorial_page"

def test_qualify_publisher_inventory_candidates_accepts_transient_fetch_timeout_for_report_asset() -> (
    None
):
    candidate = _candidate(
        "https://business.adobe.com/resources/digital-trends-report.html",
        "Adobe 2026 AI and Digital Trends",
    )

    response = qualify_publisher_inventory_candidates(
        PublisherInventoryCandidateQualityRequest(
            schema_version="1.0",
            publisher_name="Adobe",
            insights_url="https://business.adobe.com/resources/reports.html",
            candidates=[candidate],
            settings=_settings(),
        ),
        _ctx(),
        inspection_client=lambda request, ctx: (
            PublisherInventoryLandingPageInspectionResponse(
                schema_version="1.0",
                observations=[
                    _observation(
                        canonical_url=candidate.canonical_url,
                        source_title=candidate.title,
                        final_url=candidate.canonical_url,
                        fetch_error="HTTPSConnectionPool(host='business.adobe.com', port=443): Read timed out. (read timeout=20)",
                        has_dead_page_marker=True,
                    )
                ],
            )
        ),
    )

    assert [item.canonical_url for item in response.approved_items] == [
        candidate.canonical_url
    ]
    assert response.approved_items[0].title == "Adobe 2026 AI and Digital Trends"
    assert response.decisions[0].reason == "transient_fetch_report_asset"

def test_qualify_publisher_inventory_candidates_accepts_transient_http_status_for_report_asset() -> (
    None
):
    candidate = _candidate(
        "https://cube.asia/report_pages/citi-report",
        "Download the report",
    )

    response = qualify_publisher_inventory_candidates(
        PublisherInventoryCandidateQualityRequest(
            schema_version="1.0",
            publisher_name="Cube Asia",
            insights_url="https://cube.asia/insights",
            candidates=[candidate],
            settings=_settings(),
        ),
        _ctx(),
        inspection_client=lambda request, ctx: (
            PublisherInventoryLandingPageInspectionResponse(
                schema_version="1.0",
                observations=[
                    _observation(
                        canonical_url=candidate.canonical_url,
                        source_title=candidate.title,
                        final_url=candidate.canonical_url,
                        http_status_code=429,
                        fetch_error="429 Client Error: Too Many Requests",
                        has_dead_page_marker=True,
                    )
                ],
            )
        ),
    )

    assert [item.canonical_url for item in response.approved_items] == [
        candidate.canonical_url
    ]
    assert response.decisions[0].reason == "transient_fetch_report_asset"

def test_qualify_publisher_inventory_candidates_rejects_transient_case_study_asset() -> (
    None
):
    candidate = _candidate(
        "https://example.com/resources/customer-success-case-study",
        "Customer Success Case Study",
    )

    response = qualify_publisher_inventory_candidates(
        PublisherInventoryCandidateQualityRequest(
            schema_version="1.0",
            publisher_name="Example Publisher",
            insights_url="https://example.com/resources",
            candidates=[candidate],
            settings=_settings(),
        ),
        _ctx(),
        inspection_client=lambda request, ctx: (
            PublisherInventoryLandingPageInspectionResponse(
                schema_version="1.0",
                observations=[
                    _observation(
                        canonical_url=candidate.canonical_url,
                        source_title=candidate.title,
                        final_url=candidate.canonical_url,
                        fetch_error="HTTPSConnectionPool(host='example.com', port=443): Read timed out. (read timeout=20)",
                        has_dead_page_marker=True,
                    )
                ],
            )
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason == "case_study_or_customer_story_page"

def test_qualify_publisher_inventory_candidates_rejects_transient_case_study_slug_with_generic_title() -> (
    None
):
    candidate = _candidate(
        "https://example.com/resources/customer-success-case-study",
        "Learn more",
    )

    response = qualify_publisher_inventory_candidates(
        PublisherInventoryCandidateQualityRequest(
            schema_version="1.0",
            publisher_name="Example Publisher",
            insights_url="https://example.com/resources",
            candidates=[candidate],
            settings=_settings(),
        ),
        _ctx(),
        inspection_client=lambda request, ctx: (
            PublisherInventoryLandingPageInspectionResponse(
                schema_version="1.0",
                observations=[
                    _observation(
                        canonical_url=candidate.canonical_url,
                        source_title=candidate.title,
                        final_url=candidate.canonical_url,
                        fetch_error="HTTPSConnectionPool(host='example.com', port=443): Read timed out. (read timeout=20)",
                        has_dead_page_marker=True,
                    )
                ],
            )
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason == "case_study_or_customer_story_page"

def test_qualify_publisher_inventory_candidates_rejects_transient_fetch_on_collection_root() -> (
    None
):
    candidate = _candidate(
        "https://example.com/resources",
        "Guides + ebooks Retail strategy, reports and industry trends.",
    )

    response = qualify_publisher_inventory_candidates(
        PublisherInventoryCandidateQualityRequest(
            schema_version="1.0",
            publisher_name="Example Publisher",
            insights_url="https://example.com/resources",
            candidates=[candidate],
            settings=_settings(),
        ),
        _ctx(),
        inspection_client=lambda request, ctx: (
            PublisherInventoryLandingPageInspectionResponse(
                schema_version="1.0",
                observations=[
                    _observation(
                        canonical_url=candidate.canonical_url,
                        source_title=candidate.title,
                        final_url=candidate.canonical_url,
                        fetch_error="HTTPSConnectionPool(host='example.com', port=443): Read timed out. (read timeout=20)",
                        has_dead_page_marker=True,
                    )
                ],
            )
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason == "dead_or_unreachable_landing_page"

def test_qualify_publisher_inventory_candidates_accepts_protected_pdf_asset() -> None:
    candidate = _candidate(
        "https://www.example.com/files/agency-guide-report.pdf",
        "Learn more",
    )

    response = qualify_publisher_inventory_candidates(
        PublisherInventoryCandidateQualityRequest(
            schema_version="1.0",
            publisher_name="Example Publisher",
            insights_url="https://example.com/resources/reports",
            candidates=[candidate],
            settings=_settings(),
        ),
        _ctx(),
        inspection_client=lambda request, ctx: (
            PublisherInventoryLandingPageInspectionResponse(
                schema_version="1.0",
                observations=[
                    _observation(
                        canonical_url=candidate.canonical_url,
                        source_title=candidate.title,
                        final_url=candidate.canonical_url,
                        http_status_code=403,
                        fetch_error="403 Client Error: Forbidden",
                        has_dead_page_marker=True,
                    )
                ],
            )
        ),
    )

    assert [item.canonical_url for item in response.approved_items] == [
        candidate.canonical_url
    ]
    assert response.decisions[0].reason == "protected_document_asset"

def test_qualify_publisher_inventory_candidates_accepts_protected_report_page() -> None:
    candidate = _candidate(
        "https://www.example.com/resources/data-report/rewriting-the-rules-of-engagement",
        "Rewriting the Rules of Engagement",
    )

    response = qualify_publisher_inventory_candidates(
        PublisherInventoryCandidateQualityRequest(
            schema_version="1.0",
            publisher_name="Example Publisher",
            insights_url="https://example.com/resources/reports",
            candidates=[candidate],
            settings=_settings(),
        ),
        _ctx(),
        inspection_client=lambda request, ctx: (
            PublisherInventoryLandingPageInspectionResponse(
                schema_version="1.0",
                observations=[
                    _observation(
                        canonical_url=candidate.canonical_url,
                        source_title=candidate.title,
                        final_url=candidate.canonical_url,
                        http_status_code=403,
                        final_title="403 Forbidden",
                        h1_title="Error 403 Forbidden",
                        has_dead_page_marker=True,
                        has_asset_type_term=True,
                    )
                ],
            )
        ),
    )

    assert [item.canonical_url for item in response.approved_items] == [
        candidate.canonical_url
    ]
    assert response.decisions[0].reason == "protected_report_asset"

__all__ = [
    "test_qualify_publisher_inventory_candidates_accepts_gated_report_and_resolves_title",
    "test_qualify_publisher_inventory_candidates_accepts_printable_report_page",
    "test_qualify_publisher_inventory_candidates_accepts_structured_infographic_report_page",
    "test_qualify_publisher_inventory_candidates_rejects_editorial_blog_post",
    "test_qualify_publisher_inventory_candidates_rejects_editorial_finance_insight_routes",
    "test_qualify_publisher_inventory_candidates_rejects_dead_pages",
    "test_qualify_publisher_inventory_candidates_attaches_recovery_recipe_for_challenge",
    "test_qualify_publisher_inventory_candidates_accepts_bot_protected_report_asset",
    "test_qualify_publisher_inventory_candidates_rejects_editorial_detail_page_despite_report_archive_source",
    "test_qualify_publisher_inventory_candidates_rejects_bot_protected_editorial_article",
    "test_qualify_publisher_inventory_candidates_accepts_transient_fetch_timeout_for_report_asset",
    "test_qualify_publisher_inventory_candidates_accepts_transient_http_status_for_report_asset",
    "test_qualify_publisher_inventory_candidates_rejects_transient_case_study_asset",
    "test_qualify_publisher_inventory_candidates_rejects_transient_case_study_slug_with_generic_title",
    "test_qualify_publisher_inventory_candidates_rejects_transient_fetch_on_collection_root",
    "test_qualify_publisher_inventory_candidates_accepts_protected_pdf_asset",
    "test_qualify_publisher_inventory_candidates_accepts_protected_report_page",
]
