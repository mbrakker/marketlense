from __future__ import annotations

import json
import logging

from src.contracts.publisher_inventory import (
    PublisherInventoryCandidateQualityRequest,
    PublisherInventoryCandidateScreeningItem,
    PublisherInventoryLandingPageInspectionResponse,
    PublisherInventoryLandingPageObservation,
    PublisherInventorySettings,
)
from src.contracts.run_context import RunContext
from src.generators.publisher_inventory_candidate_quality_generator import (
    qualify_publisher_inventory_candidates,
)


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


def _settings() -> PublisherInventorySettings:
    return PublisherInventorySettings(
        schema_version="1.0",
        openrouter_api_key="openrouter-key",
        model="google/gemini-2.5-flash-lite",
        temperature=0.0,
        timeout_seconds=30.0,
        max_steps=10,
        output_dir="./out/publisher_inventory_discovery",
        reports_db="./state/reports.sqlite",
        google_sa_path="./sa.json",
        prompt_namespace="publisher_inventory/discovery",
        pagination_max_pages=10,
        http_timeout_seconds=30.0,
        openrouter_http_referer=None,
        headed=False,
        force_browser=True,
        retry_retries=1,
        retry_base_delay_seconds=0.0,
        retry_backoff_step_seconds=0.0,
        retry_jitter_seconds=0.0,
        openai_api_key="openai-key",
        openai_models={},
        openai_seed=123,
        candidate_screening_enabled=True,
        candidate_screening_model="gpt-5-nano",
        candidate_screening_temperature=1.0,
        candidate_screening_timeout_seconds=45.0,
        candidate_screening_batch_size=20,
        candidate_screening_prompt_namespace="publisher_inventory/meaningful_candidate_screen",
        candidate_quality_check_enabled=True,
        candidate_quality_check_timeout_seconds=10.0,
        candidate_quality_check_max_workers=4,
    )


def _candidate(url: str, title: str) -> PublisherInventoryCandidateScreeningItem:
    return PublisherInventoryCandidateScreeningItem(
        schema_version="1.0",
        canonical_url=url,
        title=title,
        discovered_on_page_number=1,
        source_page_url="https://example.com/insights",
    )


def _observation(
    *,
    canonical_url: str,
    source_title: str,
    final_url: str,
    final_title: str = "",
    h1_title: str = "",
    og_title: str = "",
    http_status_code: int | None = 200,
    content_type: str = "text/html",
    fetch_error: str = "",
    is_pdf: bool = False,
    has_asset_type_term: bool = False,
    has_download_language: bool = False,
    has_gated_form: bool = False,
    has_document_structure: bool = False,
    has_price_or_purchase: bool = False,
    has_print_language: bool = False,
    has_editorial_url_pattern: bool = False,
    has_editorial_markers: bool = False,
    has_related_posts: bool = False,
    has_newsletter_cta: bool = False,
    has_contact_sales_cta: bool = False,
    has_dead_page_marker: bool = False,
) -> PublisherInventoryLandingPageObservation:
    return PublisherInventoryLandingPageObservation(
        schema_version="1.0",
        canonical_url=canonical_url,
        source_title=source_title,
        final_url=final_url,
        final_title=final_title,
        h1_title=h1_title,
        og_title=og_title,
        http_status_code=http_status_code,
        content_type=content_type,
        fetch_error=fetch_error,
        is_pdf=is_pdf,
        has_asset_type_term=has_asset_type_term,
        has_download_language=has_download_language,
        has_gated_form=has_gated_form,
        has_document_structure=has_document_structure,
        has_price_or_purchase=has_price_or_purchase,
        has_print_language=has_print_language,
        has_editorial_url_pattern=has_editorial_url_pattern,
        has_editorial_markers=has_editorial_markers,
        has_related_posts=has_related_posts,
        has_newsletter_cta=has_newsletter_cta,
        has_contact_sales_cta=has_contact_sales_cta,
        has_dead_page_marker=has_dead_page_marker,
    )


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
        inspection_client=lambda request, ctx: PublisherInventoryLandingPageInspectionResponse(
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
        inspection_client=lambda request, ctx: PublisherInventoryLandingPageInspectionResponse(
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
        ),
    )

    assert [item.title for item in response.approved_items] == ["2026 Global Outlook"]
    assert response.decisions[0].reason == "printable_report_page"


def test_qualify_publisher_inventory_candidates_accepts_structured_infographic_report_page() -> None:
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
        inspection_client=lambda request, ctx: PublisherInventoryLandingPageInspectionResponse(
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
        inspection_client=lambda request, ctx: PublisherInventoryLandingPageInspectionResponse(
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
        ),
    )

    assert response.approved_items == []
    assert [item.canonical_url for item in response.rejected_items] == [
        candidate.canonical_url
    ]
    assert response.decisions[0].reason == "editorial_article_page"


def test_qualify_publisher_inventory_candidates_rejects_editorial_finance_insight_routes() -> None:
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
        inspection_client=lambda request, ctx: PublisherInventoryLandingPageInspectionResponse(
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
        inspection_client=lambda request, ctx: PublisherInventoryLandingPageInspectionResponse(
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
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason == "dead_or_unreachable_landing_page"


def test_qualify_publisher_inventory_candidates_accepts_bot_protected_report_asset() -> None:
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
        inspection_client=lambda request, ctx: PublisherInventoryLandingPageInspectionResponse(
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
        ),
    )

    assert [item.canonical_url for item in response.approved_items] == [
        candidate.canonical_url
    ]
    assert response.approved_items[0].title == "Mobile app trends 2026 edition"
    assert response.decisions[0].reason == "bot_protected_report_asset"


def test_qualify_publisher_inventory_candidates_rejects_editorial_detail_page_despite_report_archive_source() -> None:
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
        inspection_client=lambda request, ctx: PublisherInventoryLandingPageInspectionResponse(
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
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason in {
        "editorial_article_page",
        "insufficient_report_signals",
    }


def test_qualify_publisher_inventory_candidates_rejects_bot_protected_editorial_article() -> None:
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
        inspection_client=lambda request, ctx: PublisherInventoryLandingPageInspectionResponse(
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
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason == "bot_protected_editorial_page"


def test_qualify_publisher_inventory_candidates_accepts_transient_fetch_timeout_for_report_asset() -> None:
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
        inspection_client=lambda request, ctx: PublisherInventoryLandingPageInspectionResponse(
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
        ),
    )

    assert [item.canonical_url for item in response.approved_items] == [
        candidate.canonical_url
    ]
    assert response.approved_items[0].title == "Adobe 2026 AI and Digital Trends"
    assert response.decisions[0].reason == "transient_fetch_report_asset"


def test_qualify_publisher_inventory_candidates_accepts_transient_http_status_for_report_asset() -> None:
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
        inspection_client=lambda request, ctx: PublisherInventoryLandingPageInspectionResponse(
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
        ),
    )

    assert [item.canonical_url for item in response.approved_items] == [
        candidate.canonical_url
    ]
    assert response.decisions[0].reason == "transient_fetch_report_asset"


def test_qualify_publisher_inventory_candidates_rejects_transient_case_study_asset() -> None:
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
        inspection_client=lambda request, ctx: PublisherInventoryLandingPageInspectionResponse(
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
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason == "case_study_or_customer_story_page"


def test_qualify_publisher_inventory_candidates_rejects_transient_case_study_slug_with_generic_title() -> None:
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
        inspection_client=lambda request, ctx: PublisherInventoryLandingPageInspectionResponse(
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
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason == "case_study_or_customer_story_page"


def test_qualify_publisher_inventory_candidates_rejects_transient_fetch_on_collection_root() -> None:
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
        inspection_client=lambda request, ctx: PublisherInventoryLandingPageInspectionResponse(
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
        inspection_client=lambda request, ctx: PublisherInventoryLandingPageInspectionResponse(
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
        inspection_client=lambda request, ctx: PublisherInventoryLandingPageInspectionResponse(
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
        ),
    )

    assert [item.canonical_url for item in response.approved_items] == [
        candidate.canonical_url
    ]
    assert response.decisions[0].reason == "protected_report_asset"


def test_qualify_publisher_inventory_candidates_rejects_legal_pages() -> None:
    candidate = _candidate(
        "https://example.com/legal/transparency-report",
        "Transparency Report",
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
        inspection_client=lambda request, ctx: PublisherInventoryLandingPageInspectionResponse(
            schema_version="1.0",
            observations=[
                _observation(
                    canonical_url=candidate.canonical_url,
                    source_title=candidate.title,
                    final_url=candidate.canonical_url,
                    h1_title="Transparency Report",
                    has_asset_type_term=True,
                    has_document_structure=True,
                )
            ],
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason == "legal_or_compliance_page"


def test_qualify_publisher_inventory_candidates_rejects_case_studies() -> None:
    candidate = _candidate(
        "https://example.com/case-studies/state-of-snacking-report",
        "State of Snacking Report",
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
        inspection_client=lambda request, ctx: PublisherInventoryLandingPageInspectionResponse(
            schema_version="1.0",
            observations=[
                _observation(
                    canonical_url=candidate.canonical_url,
                    source_title=candidate.title,
                    final_url=candidate.canonical_url,
                    h1_title="State of Snacking Report",
                    has_asset_type_term=True,
                    has_download_language=True,
                    has_editorial_markers=True,
                    has_newsletter_cta=True,
                )
            ],
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason == "case_study_or_customer_story_page"


def test_qualify_publisher_inventory_candidates_rejects_report_section_pages() -> None:
    candidate = _candidate(
        "https://example.com/global-culture-report/2025-conclusion",
        "Conclusion",
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
        inspection_client=lambda request, ctx: PublisherInventoryLandingPageInspectionResponse(
            schema_version="1.0",
            observations=[
                _observation(
                    canonical_url=candidate.canonical_url,
                    source_title=candidate.title,
                    final_url=candidate.canonical_url,
                    h1_title="Conclusion",
                    final_title="Conclusion | 2025 Global Culture Report",
                    has_asset_type_term=True,
                    has_download_language=True,
                    has_document_structure=True,
                    has_editorial_markers=True,
                )
            ],
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason == "report_section_page"


def test_qualify_publisher_inventory_candidates_rejects_nested_report_section_urls() -> None:
    candidate = _candidate(
        "https://example.com/enterprise-software-technology-predictions-report-2026/innovation",
        "2026 Enterprise software technology predictions report",
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
        inspection_client=lambda request, ctx: PublisherInventoryLandingPageInspectionResponse(
            schema_version="1.0",
            observations=[
                _observation(
                    canonical_url=candidate.canonical_url,
                    source_title=candidate.title,
                    final_url=candidate.canonical_url,
                    h1_title="2026 Enterprise software technology predictions report",
                    has_asset_type_term=True,
                    has_document_structure=True,
                )
            ],
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason == "report_section_page"


def test_qualify_publisher_inventory_candidates_rejects_legal_practice_area_guides() -> None:
    candidate = _candidate(
        "https://iclg.com/practice-areas/sanctions/germany",
        "Sanctions Germany 2026",
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
        inspection_client=lambda request, ctx: PublisherInventoryLandingPageInspectionResponse(
            schema_version="1.0",
            observations=[
                _observation(
                    canonical_url=candidate.canonical_url,
                    source_title=candidate.title,
                    final_url=candidate.canonical_url,
                    h1_title="Sanctions Germany 2026",
                    has_price_or_purchase=True,
                    has_asset_type_term=True,
                )
            ],
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason == "legal_or_compliance_page"


def test_qualify_publisher_inventory_candidates_rejects_research_announcements_without_asset_flow() -> None:
    candidate = _candidate(
        "https://example.com/insights/despite-gains-finds-new-research",
        "Despite Gains, CMOs Still Struggle to Prove Value to CFOs, Finds New Research from Example and Partner",
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
        inspection_client=lambda request, ctx: PublisherInventoryLandingPageInspectionResponse(
            schema_version="1.0",
            observations=[
                _observation(
                    canonical_url=candidate.canonical_url,
                    source_title=candidate.title,
                    final_url=candidate.canonical_url,
                    h1_title="Despite Gains, CMOs Still Struggle to Prove Value to CFOs, Finds New Research from Example and Partner",
                    has_asset_type_term=True,
                    has_download_language=True,
                    has_document_structure=True,
                    has_editorial_markers=True,
                    has_newsletter_cta=True,
                )
            ],
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason == "research_announcement_page"


def test_qualify_publisher_inventory_candidates_rejects_informational_how_to_pages() -> None:
    candidate = _candidate(
        "https://example.com/resources/how-to-use-x",
        "How to use X",
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
        inspection_client=lambda request, ctx: PublisherInventoryLandingPageInspectionResponse(
            schema_version="1.0",
            observations=[
                _observation(
                    canonical_url=candidate.canonical_url,
                    source_title=candidate.title,
                    final_url=candidate.canonical_url,
                    h1_title="How to use Reddit for social listening",
                    has_asset_type_term=True,
                    has_document_structure=True,
                    has_editorial_markers=True,
                )
            ],
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason == "informational_article_page"


def test_qualify_publisher_inventory_candidates_rejects_how_to_reporting_pages() -> None:
    candidate = _candidate(
        "https://example.com/insights/reporting-and-data-analytics-with-ai",
        "How to maximise international reporting and data analytics with AI",
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
        inspection_client=lambda request, ctx: PublisherInventoryLandingPageInspectionResponse(
            schema_version="1.0",
            observations=[
                _observation(
                    canonical_url=candidate.canonical_url,
                    source_title=candidate.title,
                    final_url=candidate.canonical_url,
                    h1_title="How to maximise international reporting and data analytics with AI",
                    has_asset_type_term=True,
                    has_print_language=True,
                    has_editorial_markers=True,
                )
            ],
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason == "informational_article_page"


def test_qualify_publisher_inventory_candidates_rejects_regulatory_disclosure_documents() -> None:
    candidate = _candidate(
        "https://example.com/docs/disclosure-notes.pdf",
        "Pillar 3 Disclosures",
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
        inspection_client=lambda request, ctx: PublisherInventoryLandingPageInspectionResponse(
            schema_version="1.0",
            observations=[
                _observation(
                    canonical_url=candidate.canonical_url,
                    source_title=candidate.title,
                    final_url=candidate.canonical_url,
                    is_pdf=True,
                    content_type="application/pdf",
                )
            ],
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason == "regulatory_or_disclosure_document"


def test_qualify_publisher_inventory_candidates_rejects_corporate_policy_pdfs() -> None:
    candidate = _candidate(
        "https://example.com/docs/modern-slavery-statement.pdf",
        "Modern Slavery Statement",
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
        inspection_client=lambda request, ctx: PublisherInventoryLandingPageInspectionResponse(
            schema_version="1.0",
            observations=[
                _observation(
                    canonical_url=candidate.canonical_url,
                    source_title=candidate.title,
                    final_url=candidate.canonical_url,
                    is_pdf=True,
                    content_type="application/pdf",
                )
            ],
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason == "corporate_policy_document"


def test_qualify_publisher_inventory_candidates_rejects_gender_equality_index_pdfs() -> None:
    candidate = _candidate(
        "https://example.com/docs/index-de-l-egalite-femmes-hommes.pdf",
        "Index de l’égalité femmes-hommes",
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
        inspection_client=lambda request, ctx: PublisherInventoryLandingPageInspectionResponse(
            schema_version="1.0",
            observations=[
                _observation(
                    canonical_url=candidate.canonical_url,
                    source_title=candidate.title,
                    final_url=candidate.canonical_url,
                    final_title="Index de l’égalité femmes-hommes",
                    h1_title="Index de l’égalité femmes-hommes",
                    content_type="application/pdf",
                    is_pdf=True,
                    has_download_language=False,
                    has_document_structure=False,
                )
            ],
        ),
    )

    assert response.approved_items == []
    assert [item.canonical_url for item in response.rejected_items] == [
        candidate.canonical_url
    ]
    assert response.decisions[0].reason == "corporate_policy_document"


def test_qualify_publisher_inventory_candidates_rejects_binding_corporate_rules_documents() -> None:
    candidate = _candidate(
        "https://example.com/docs/company-bcr-summary.pdf",
        "UK BCR Summarypdf 159.3 KB",
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
        inspection_client=lambda request, ctx: PublisherInventoryLandingPageInspectionResponse(
            schema_version="1.0",
            observations=[
                _observation(
                    canonical_url=candidate.canonical_url,
                    source_title=candidate.title,
                    final_url=candidate.canonical_url,
                    final_title="UK BCR Summarypdf 159.3 KB",
                    h1_title="UK BCR Summarypdf 159.3 KB",
                    content_type="application/pdf",
                    is_pdf=True,
                )
            ],
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason in {
        "legal_or_compliance_page",
        "legal_or_policy_document",
        "regulatory_or_disclosure_document",
    }


def test_qualify_publisher_inventory_candidates_rejects_survey_platform_pages_without_report_signals() -> None:
    candidate = _candidate(
        "https://www.surveymonkey.com/r/SFSA_BTB_Sep25",
        "SurveyMonkey logo with text in primary",
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
        inspection_client=lambda request, ctx: PublisherInventoryLandingPageInspectionResponse(
            schema_version="1.0",
            observations=[
                _observation(
                    canonical_url=candidate.canonical_url,
                    source_title=candidate.title,
                    final_url="https://www.surveymonkey.com/survey-closed",
                    final_title="SurveyMonkey logo with text in primary",
                    has_gated_form=True,
                    has_newsletter_cta=True,
                    has_contact_sales_cta=True,
                    has_editorial_markers=True,
                )
            ],
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason == "survey_or_questionnaire_page"


def test_qualify_publisher_inventory_candidates_rejects_survey_platform_pages_even_with_report_like_title() -> None:
    candidate = _candidate(
        "https://www.surveymonkey.com/r/SFSA_BTB_Feb26",
        "SFSA Business Trend Survey - February 2026",
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
        inspection_client=lambda request, ctx: PublisherInventoryLandingPageInspectionResponse(
            schema_version="1.0",
            observations=[
                _observation(
                    canonical_url=candidate.canonical_url,
                    source_title=candidate.title,
                    final_url="https://www.surveymonkey.com/r/SFSA_BTB_Feb26",
                    final_title="SFSA Business Trend Survey - February 2026",
                    has_gated_form=True,
                )
            ],
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason == "survey_or_questionnaire_page"


def test_qualify_publisher_inventory_candidates_uses_pdf_filename_when_source_title_is_generic() -> None:
    candidate = _candidate(
        "https://cdn.example.com/files/2026-market-forecast.pdf",
        "here",
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
        inspection_client=lambda request, ctx: PublisherInventoryLandingPageInspectionResponse(
            schema_version="1.0",
            observations=[
                _observation(
                    canonical_url=candidate.canonical_url,
                    source_title=candidate.title,
                    final_url=candidate.canonical_url,
                    is_pdf=True,
                    content_type="application/pdf",
                )
            ],
        ),
    )

    assert response.approved_items[0].title == "2026 market forecast"
    assert response.decisions[0].resolved_title == "2026 market forecast"


def test_qualify_publisher_inventory_candidates_rejects_plural_asset_bucket_titles_without_distribution_signals() -> None:
    candidate = _candidate(
        "https://example.com/subject-areas/education/whitepapers",
        "White papers",
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
        inspection_client=lambda request, ctx: PublisherInventoryLandingPageInspectionResponse(
            schema_version="1.0",
            observations=[
                _observation(
                    canonical_url=candidate.canonical_url,
                    source_title=candidate.title,
                    final_url=candidate.canonical_url,
                    final_title="White papers",
                    h1_title="White papers",
                    has_asset_type_term=True,
                )
            ],
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason == "generic_asset_hub_page"
    assert response.decisions[0].resolved_title == candidate.canonical_url


def test_qualify_publisher_inventory_candidates_rejects_report_root_hub_even_with_document_structure() -> None:
    candidate = _candidate(
        "https://example.com/reports",
        "Reports - Resources, Marketing Infographics & Guides",
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
        inspection_client=lambda request, ctx: PublisherInventoryLandingPageInspectionResponse(
            schema_version="1.0",
            observations=[
                _observation(
                    canonical_url=candidate.canonical_url,
                    source_title=candidate.title,
                    final_url=candidate.canonical_url,
                    final_title="Reports - Resources, Marketing Infographics & Guides",
                    h1_title="Reports",
                    has_document_structure=True,
                    has_asset_type_term=True,
                )
            ],
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason == "generic_asset_hub_page"


def test_qualify_publisher_inventory_candidates_rejects_service_membership_pages() -> None:
    candidate = _candidate(
        "https://example.com/research/ai-access",
        "AI Access",
    )

    response = qualify_publisher_inventory_candidates(
        PublisherInventoryCandidateQualityRequest(
            schema_version="1.0",
            publisher_name="Example Publisher",
            insights_url="https://example.com/research",
            candidates=[candidate],
            settings=_settings(),
        ),
        _ctx(),
        inspection_client=lambda request, ctx: PublisherInventoryLandingPageInspectionResponse(
            schema_version="1.0",
            observations=[
                _observation(
                    canonical_url=candidate.canonical_url,
                    source_title=candidate.title,
                    final_url=candidate.canonical_url,
                    final_title="AI Access",
                    h1_title="AI Access",
                    has_document_structure=True,
                )
            ],
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason == "service_or_membership_page"


def test_qualify_publisher_inventory_candidates_rejects_research_center_hubs() -> None:
    candidate = _candidate(
        "https://example.com/research-centers/artificial-intelligence-research-center",
        "Artificial Intelligence Research Center",
    )

    response = qualify_publisher_inventory_candidates(
        PublisherInventoryCandidateQualityRequest(
            schema_version="1.0",
            publisher_name="Example Publisher",
            insights_url="https://example.com/research",
            candidates=[candidate],
            settings=_settings(),
        ),
        _ctx(),
        inspection_client=lambda request, ctx: PublisherInventoryLandingPageInspectionResponse(
            schema_version="1.0",
            observations=[
                _observation(
                    canonical_url=candidate.canonical_url,
                    source_title=candidate.title,
                    final_url=candidate.canonical_url,
                    final_title="Artificial Intelligence Research Center",
                    h1_title="Artificial Intelligence Research Center",
                    has_document_structure=True,
                    has_print_language=True,
                )
            ],
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason == "service_or_membership_page"


def test_qualify_publisher_inventory_candidates_rejects_research_center_hubs_even_with_gated_signals() -> None:
    candidate = _candidate(
        "https://example.com/research-centers/tech-trends-priorities-research-center",
        "Tech Trends & Priorities Research Center",
    )

    response = qualify_publisher_inventory_candidates(
        PublisherInventoryCandidateQualityRequest(
            schema_version="1.0",
            publisher_name="Example Publisher",
            insights_url="https://example.com/research",
            candidates=[candidate],
            settings=_settings(),
        ),
        _ctx(),
        inspection_client=lambda request, ctx: PublisherInventoryLandingPageInspectionResponse(
            schema_version="1.0",
            observations=[
                _observation(
                    canonical_url=candidate.canonical_url,
                    source_title=candidate.title,
                    final_url=candidate.canonical_url,
                    final_title="Tech Trends & Priorities Research Center",
                    h1_title="Tech Trends & Priorities Research Center",
                    has_download_language=True,
                    has_gated_form=True,
                    has_document_structure=True,
                    has_print_language=True,
                )
            ],
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason == "service_or_membership_page"


def test_qualify_publisher_inventory_candidates_rejects_capability_pages_even_with_report_words_in_title() -> None:
    candidate = _candidate(
        "https://example.com/capabilities/survey-creation",
        "Survey creation",
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
        inspection_client=lambda request, ctx: PublisherInventoryLandingPageInspectionResponse(
            schema_version="1.0",
            observations=[
                _observation(
                    canonical_url=candidate.canonical_url,
                    source_title=candidate.title,
                    final_url=candidate.canonical_url,
                    final_title="From research objectives to ready-to-launch survey — in a day",
                    h1_title="From research objectives to ready-to-launch survey — in a day",
                    has_document_structure=True,
                    has_print_language=True,
                )
            ],
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason == "service_or_membership_page"


def test_qualify_publisher_inventory_candidates_rejects_collection_root_hubs() -> None:
    candidate = _candidate(
        "https://example.com/reports-and-whitepapers",
        "Reports and Whitepapers",
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
        inspection_client=lambda request, ctx: PublisherInventoryLandingPageInspectionResponse(
            schema_version="1.0",
            observations=[
                _observation(
                    canonical_url=candidate.canonical_url,
                    source_title=candidate.title,
                    final_url=candidate.canonical_url,
                    final_title="Thought Leadership",
                    h1_title="Thought Leadership",
                    has_document_structure=True,
                    has_print_language=True,
                )
            ],
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason == "generic_asset_hub_page"


def test_qualify_publisher_inventory_candidates_rejects_trends_hub_roots() -> None:
    candidate = _candidate(
        "https://example.com/quarterly-trends-hub",
        "Quarterly Trends Hub",
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
        inspection_client=lambda request, ctx: PublisherInventoryLandingPageInspectionResponse(
            schema_version="1.0",
            observations=[
                _observation(
                    canonical_url=candidate.canonical_url,
                    source_title=candidate.title,
                    final_url=candidate.canonical_url,
                    final_title="Quarterly Trends Hub",
                    h1_title="Quarterly Trends Hub",
                    has_document_structure=True,
                    has_print_language=True,
                )
            ],
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason == "generic_asset_hub_page"


def test_qualify_publisher_inventory_candidates_rejects_generic_research_hubs() -> None:
    candidate = _candidate(
        "https://example.com/insights/research/index-research",
        "Example Global Index Research",
    )

    response = qualify_publisher_inventory_candidates(
        PublisherInventoryCandidateQualityRequest(
            schema_version="1.0",
            publisher_name="Example Publisher",
            insights_url="https://example.com/insights/research",
            candidates=[candidate],
            settings=_settings(),
        ),
        _ctx(),
        inspection_client=lambda request, ctx: PublisherInventoryLandingPageInspectionResponse(
            schema_version="1.0",
            observations=[
                _observation(
                    canonical_url=candidate.canonical_url,
                    source_title=candidate.title,
                    final_url=candidate.canonical_url,
                    final_title="Example Global Index Research",
                    h1_title="Example Global Index Research",
                    has_document_structure=True,
                    has_print_language=True,
                )
            ],
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason == "service_or_membership_page"


def test_qualify_publisher_inventory_candidates_accepts_unreachable_report_documents() -> None:
    candidate = _candidate(
        "https://cdn.example.com/annual-report-2025.pdf",
        "Download Annual Report",
    )

    response = qualify_publisher_inventory_candidates(
        PublisherInventoryCandidateQualityRequest(
            schema_version="1.0",
            publisher_name="Example Publisher",
            insights_url="https://example.com/annual-report",
            candidates=[candidate],
            settings=_settings(),
        ),
        _ctx(),
        inspection_client=lambda request, ctx: PublisherInventoryLandingPageInspectionResponse(
            schema_version="1.0",
            observations=[
                _observation(
                    canonical_url=candidate.canonical_url,
                    source_title=candidate.title,
                    final_url=candidate.canonical_url,
                    fetch_error="403 Client Error",
                    has_dead_page_marker=True,
                )
            ],
        ),
    )

    assert [item.canonical_url for item in response.approved_items] == [
        candidate.canonical_url
    ]
    assert response.decisions[0].reason == "unreachable_document_asset"


def test_qualify_publisher_inventory_candidates_rejects_self_service_help_pages() -> None:
    candidate = _candidate(
        "https://example.com/help/annual-credit-report",
        "How to get your free annual credit reports",
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
        inspection_client=lambda request, ctx: PublisherInventoryLandingPageInspectionResponse(
            schema_version="1.0",
            observations=[
                _observation(
                    canonical_url=candidate.canonical_url,
                    source_title=candidate.title,
                    final_url=candidate.canonical_url,
                    h1_title="How to get your free annual credit reports",
                )
            ],
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason == "self_service_or_signup_page"


def test_qualify_publisher_inventory_candidates_rejects_consumer_self_service_report_products() -> None:
    candidate = _candidate(
        "https://example.com/credit/three-bureau-credit-report-and-score",
        "3-bureau credit report and FICO Scores",
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
        inspection_client=lambda request, ctx: PublisherInventoryLandingPageInspectionResponse(
            schema_version="1.0",
            observations=[
                _observation(
                    canonical_url=candidate.canonical_url,
                    source_title=candidate.title,
                    final_url=candidate.canonical_url,
                    final_title="3 Bureau Credit Reports and Scores",
                    h1_title="3-bureau credit report and FICO Scores",
                    has_asset_type_term=True,
                    has_download_language=True,
                    has_gated_form=True,
                    has_price_or_purchase=True,
                )
            ],
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason == "self_service_or_signup_page"


def test_qualify_publisher_inventory_candidates_rejects_audio_editorial_pages() -> None:
    candidate = _candidate(
        "https://example.com/podcast/retail-playbook",
        "Retail Playbook Podcast",
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
        inspection_client=lambda request, ctx: PublisherInventoryLandingPageInspectionResponse(
            schema_version="1.0",
            observations=[
                _observation(
                    canonical_url=candidate.canonical_url,
                    source_title=candidate.title,
                    final_url=candidate.canonical_url,
                    final_title="Retail Playbook Podcast",
                    h1_title="Retail Playbook Podcast",
                    has_asset_type_term=True,
                    has_editorial_markers=True,
                    has_newsletter_cta=True,
                )
            ],
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason == "audio_editorial_page"


def test_qualify_publisher_inventory_candidates_accepts_buyer_guide_report_detail_pages_without_document_markup() -> None:
    candidate = _candidate(
        "https://example.com/resources/buyers-guide-enterprise-marketing-governance-platforms",
        "How to Evaluate Enterprise Marketing Governance Platforms",
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
        inspection_client=lambda request, ctx: PublisherInventoryLandingPageInspectionResponse(
            schema_version="1.0",
            observations=[
                _observation(
                    canonical_url=candidate.canonical_url,
                    source_title=candidate.title,
                    final_url=candidate.canonical_url,
                    final_title="How to Evaluate Enterprise Marketing Governance Platforms",
                    h1_title="How to Evaluate Enterprise Marketing Governance Platforms",
                )
            ],
        ),
    )

    assert [item.canonical_url for item in response.approved_items] == [
        candidate.canonical_url
    ]
    assert response.decisions[0].reason == "report_detail_landing_page"


def test_qualify_publisher_inventory_candidates_accepts_report_detail_pages_with_generic_editorial_chrome() -> None:
    candidate = _candidate(
        "https://example.com/next-normal-guide-to-the-digital-shelf",
        "'Next Normal' Guide to the Digital Shelf",
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
        inspection_client=lambda request, ctx: PublisherInventoryLandingPageInspectionResponse(
            schema_version="1.0",
            observations=[
                _observation(
                    canonical_url=candidate.canonical_url,
                    source_title=candidate.title,
                    final_url=candidate.canonical_url,
                    final_title="The Next Normal",
                    h1_title="'Next Normal' Guide to the Digital Shelf",
                    has_asset_type_term=True,
                    has_editorial_markers=True,
                )
            ],
        ),
    )

    assert [item.canonical_url for item in response.approved_items] == [
        candidate.canonical_url
    ]
    assert response.decisions[0].reason == "report_detail_landing_page"


def test_qualify_publisher_inventory_candidates_accepts_trend_detail_pages_with_generic_titles() -> None:
    candidate = _candidate(
        "https://example.com/our-insights/commerce-m-and-a-trends-q1-2026",
        "Commerce",
    )

    response = qualify_publisher_inventory_candidates(
        PublisherInventoryCandidateQualityRequest(
            schema_version="1.0",
            publisher_name="Example Publisher",
            insights_url="https://example.com/our-insights",
            candidates=[candidate],
            settings=_settings(),
        ),
        _ctx(),
        inspection_client=lambda request, ctx: PublisherInventoryLandingPageInspectionResponse(
            schema_version="1.0",
            observations=[
                _observation(
                    canonical_url=candidate.canonical_url,
                    source_title=candidate.title,
                    final_url=candidate.canonical_url,
                    final_title="Commerce M&A Trends Q1 2026",
                    h1_title="Commerce",
                )
            ],
        ),
    )

    assert [item.canonical_url for item in response.approved_items] == [
        candidate.canonical_url
    ]
    assert response.decisions[0].reason == "report_detail_landing_page"


def test_qualify_publisher_inventory_candidates_rejects_dated_editorial_pages_even_with_generic_form_signals() -> None:
    candidate = _candidate(
        "https://example.com/2026/02/11/survey-enterprises-ai-agents",
        "Survey: Enterprises move AI agents from pilots to production",
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
        inspection_client=lambda request, ctx: PublisherInventoryLandingPageInspectionResponse(
            schema_version="1.0",
            observations=[
                _observation(
                    canonical_url=candidate.canonical_url,
                    source_title=candidate.title,
                    final_url=candidate.canonical_url,
                    h1_title="Survey: Enterprises move AI agents from pilots to production",
                    has_asset_type_term=True,
                    has_gated_form=True,
                    has_document_structure=True,
                    has_editorial_url_pattern=True,
                    has_editorial_markers=True,
                )
            ],
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason in {
        "editorial_article_page",
        "insufficient_report_signals",
    }


def test_qualify_publisher_inventory_candidates_rejects_gated_editorial_blog_post_with_generic_report_title() -> None:
    candidate = _candidate(
        "https://www.cardlytics.com/blog/loyalty-movement-report-apparel",
        "Loyalty Movement Report: Apparel",
    )

    response = qualify_publisher_inventory_candidates(
        PublisherInventoryCandidateQualityRequest(
            schema_version="1.0",
            publisher_name="Cardlytics",
            insights_url="https://www.cardlytics.com/research-and-insights",
            candidates=[candidate],
            settings=_settings(),
        ),
        _ctx(),
        inspection_client=lambda request, ctx: PublisherInventoryLandingPageInspectionResponse(
            schema_version="1.0",
            observations=[
                _observation(
                    canonical_url=candidate.canonical_url,
                    source_title=candidate.title,
                    final_url=candidate.canonical_url,
                    h1_title="Loyalty Movement Report: Apparel",
                    has_asset_type_term=True,
                    has_download_language=True,
                    has_gated_form=True,
                    has_document_structure=True,
                    has_editorial_url_pattern=True,
                    has_editorial_markers=True,
                )
            ],
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason in {
        "editorial_article_page",
        "insufficient_report_signals",
    }


def test_qualify_publisher_inventory_candidates_accepts_editorial_path_when_title_has_specific_report_signal() -> None:
    candidate = _candidate(
        "https://www.example.com/blog/global-consumer-outlook-2026",
        "Global Consumer Outlook 2026",
    )

    response = qualify_publisher_inventory_candidates(
        PublisherInventoryCandidateQualityRequest(
            schema_version="1.0",
            publisher_name="Example Publisher",
            insights_url="https://www.example.com/research",
            candidates=[candidate],
            settings=_settings(),
        ),
        _ctx(),
        inspection_client=lambda request, ctx: PublisherInventoryLandingPageInspectionResponse(
            schema_version="1.0",
            observations=[
                _observation(
                    canonical_url=candidate.canonical_url,
                    source_title=candidate.title,
                    final_url=candidate.canonical_url,
                    h1_title="Global Consumer Outlook 2026",
                    has_asset_type_term=True,
                    has_download_language=True,
                    has_gated_form=True,
                    has_document_structure=True,
                    has_editorial_url_pattern=True,
                    has_editorial_markers=True,
                )
            ],
        ),
    )

    assert [item.canonical_url for item in response.approved_items] == [
        candidate.canonical_url
    ]
    assert response.decisions[0].reason == "gated_report_asset"


def test_qualify_publisher_inventory_candidates_accepts_related_post_guide_when_document_signals_are_strong() -> None:
    candidate = _candidate(
        "https://www.example.com/insights/the-guide-framework",
        "The guide framework",
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
        inspection_client=lambda request, ctx: PublisherInventoryLandingPageInspectionResponse(
            schema_version="1.0",
            observations=[
                _observation(
                    canonical_url=candidate.canonical_url,
                    source_title=candidate.title,
                    final_url=candidate.canonical_url,
                    h1_title="The Guide Framework",
                    has_asset_type_term=True,
                    has_document_structure=True,
                    has_related_posts=True,
                )
            ],
        ),
    )

    assert [item.canonical_url for item in response.approved_items] == [
        candidate.canonical_url
    ]
    assert response.decisions[0].reason == "printable_report_page"


def test_qualify_publisher_inventory_candidates_accepts_transparency_reports() -> None:
    candidate = _candidate(
        "https://example.com/reports/tax-transparency-report-2025",
        "Tax Transparency Report 2025",
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
        inspection_client=lambda request, ctx: PublisherInventoryLandingPageInspectionResponse(
            schema_version="1.0",
            observations=[
                _observation(
                    canonical_url=candidate.canonical_url,
                    source_title=candidate.title,
                    final_url=candidate.canonical_url,
                    h1_title="Tax Transparency Report 2025",
                    has_asset_type_term=True,
                    has_download_language=True,
                    has_gated_form=True,
                )
            ],
        ),
    )

    assert [item.canonical_url for item in response.approved_items] == [
        candidate.canonical_url
    ]
    assert response.decisions[0].reason == "printable_report_page"


def test_qualify_publisher_inventory_candidates_accepts_slug_signaled_ebook_page() -> None:
    candidate = _candidate(
        "https://go.example.com/en/analysis-paralysis-ebook",
        "Breaking Free From Analysis Paralysis",
    )

    response = qualify_publisher_inventory_candidates(
        PublisherInventoryCandidateQualityRequest(
            schema_version="1.0",
            publisher_name="Example Publisher",
            insights_url="https://example.com/ebooks-reports",
            candidates=[candidate],
            settings=_settings(),
        ),
        _ctx(),
        inspection_client=lambda request, ctx: PublisherInventoryLandingPageInspectionResponse(
            schema_version="1.0",
            observations=[
                _observation(
                    canonical_url=candidate.canonical_url,
                    source_title=candidate.title,
                    final_url=candidate.canonical_url,
                    h1_title="Breaking Free From Analysis Paralysis",
                    has_asset_type_term=True,
                )
            ],
        ),
    )

    assert [item.canonical_url for item in response.approved_items] == [
        candidate.canonical_url
    ]
    assert response.decisions[0].reason == "printable_report_page"


def test_qualify_publisher_inventory_candidates_rejects_thought_leadership_article_with_generic_section_heading() -> None:
    candidate = _candidate(
        "https://www.publiciscommerce.com/insights/creating-relevance-through-the-convergence-of-content-creators-and-commerce",
        "KEY TAKEAWAYS",
    )

    response = qualify_publisher_inventory_candidates(
        PublisherInventoryCandidateQualityRequest(
            schema_version="1.0",
            publisher_name="Publicis Commerce",
            insights_url="https://www.publiciscommerce.com/insights",
            candidates=[candidate],
            settings=_settings(),
        ),
        _ctx(),
        inspection_client=lambda request, ctx: PublisherInventoryLandingPageInspectionResponse(
            schema_version="1.0",
            observations=[
                _observation(
                    canonical_url=candidate.canonical_url,
                    source_title=candidate.title,
                    final_url=candidate.canonical_url,
                    final_title="Creating Relevance Through the Convergence of Content, Creators & Commerce",
                    h1_title="KEY TAKEAWAYS",
                    has_asset_type_term=True,
                    has_document_structure=True,
                    has_editorial_markers=True,
                    has_newsletter_cta=True,
                )
            ],
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason in {
        "editorial_article_page",
        "insufficient_report_signals",
    }
    assert response.decisions[0].resolved_title == "Creating Relevance Through the Convergence of Content, Creators & Commerce"


def test_qualify_publisher_inventory_candidates_accepts_report_hub_pages_with_download_and_related_links() -> None:
    candidate = _candidate(
        "https://internetretailing.net/report-hub/amazon-sellers-summit-report-2025",
        "Amazon Sellers Summit Report 2025",
    )

    response = qualify_publisher_inventory_candidates(
        PublisherInventoryCandidateQualityRequest(
            schema_version="1.0",
            publisher_name="Retail X",
            insights_url="https://internetretailing.net/browse-all-reports/#",
            candidates=[candidate],
            settings=_settings(),
        ),
        _ctx(),
        inspection_client=lambda request, ctx: PublisherInventoryLandingPageInspectionResponse(
            schema_version="1.0",
            observations=[
                _observation(
                    canonical_url=candidate.canonical_url,
                    source_title=candidate.title,
                    final_url=candidate.canonical_url,
                    final_title="Amazon Sellers Summit Report 2025 - InternetRetailing",
                    h1_title="Amazon Sellers Summit Report 2025",
                    has_asset_type_term=True,
                    has_download_language=True,
                    has_related_posts=True,
                )
            ],
        ),
    )

    assert response.approved_items != []
    assert response.decisions[0].reason in {
        "downloadable_report_asset",
        "printable_report_page",
    }


def test_qualify_publisher_inventory_candidates_rejects_newsletter_articles_without_real_report_signals() -> None:
    candidate = PublisherInventoryCandidateScreeningItem(
        schema_version="1.0",
        canonical_url="https://www.robeco.com/en-int/insights/2026/03/why-the-future-of-chips-depends-on-water",
        title="Why the future of chips depends on water",
        discovered_on_page_number=1,
        source_page_url="https://www.robeco.com/en-int/insights/monthly-newsletter",
    )

    response = qualify_publisher_inventory_candidates(
        PublisherInventoryCandidateQualityRequest(
            schema_version="1.0",
            publisher_name="Robeco",
            insights_url="https://www.robeco.com/en-int/insights/monthly-newsletter",
            candidates=[candidate],
            settings=_settings(),
        ),
        _ctx(),
        inspection_client=lambda request, ctx: PublisherInventoryLandingPageInspectionResponse(
            schema_version="1.0",
            observations=[
                _observation(
                    canonical_url=candidate.canonical_url,
                    source_title=candidate.title,
                    final_url=candidate.canonical_url,
                    h1_title="Why the future of chips depends on water",
                    has_asset_type_term=True,
                    has_print_language=True,
                    has_price_or_purchase=True,
                    has_editorial_markers=True,
                    has_newsletter_cta=True,
                )
            ],
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason == "newsletter_article_page"


def test_qualify_publisher_inventory_candidates_rejects_software_pages_with_report_like_titles() -> None:
    candidate = _candidate(
        "https://www.paycom.com/software/paycom-surveys",
        "Paycom Surveys",
    )

    response = qualify_publisher_inventory_candidates(
        PublisherInventoryCandidateQualityRequest(
            schema_version="1.0",
            publisher_name="Paycom",
            insights_url="https://www.paycom.com/resources/nucleus-research-beti-bolsters-payroll-success",
            candidates=[candidate],
            settings=_settings(),
        ),
        _ctx(),
        inspection_client=lambda request, ctx: PublisherInventoryLandingPageInspectionResponse(
            schema_version="1.0",
            observations=[
                _observation(
                    canonical_url=candidate.canonical_url,
                    source_title=candidate.title,
                    final_url=candidate.canonical_url,
                    h1_title="Paycom Surveys",
                    has_asset_type_term=True,
                    has_editorial_markers=True,
                    has_newsletter_cta=True,
                )
            ],
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason == "service_or_membership_page"


def test_qualify_publisher_inventory_candidates_rejects_gated_career_pages() -> None:
    candidate = _candidate(
        "https://mediacharge.com/career",
        "Join our Team",
    )

    response = qualify_publisher_inventory_candidates(
        PublisherInventoryCandidateQualityRequest(
            schema_version="1.0",
            publisher_name="Mediacharge",
            insights_url="https://mediacharge.com/publications/example",
            candidates=[candidate],
            settings=_settings(),
        ),
        _ctx(),
        inspection_client=lambda request, ctx: PublisherInventoryLandingPageInspectionResponse(
            schema_version="1.0",
            observations=[
                _observation(
                    canonical_url=candidate.canonical_url,
                    source_title=candidate.title,
                    final_url=candidate.canonical_url,
                    h1_title="Join our Team",
                    has_asset_type_term=True,
                    has_gated_form=True,
                )
            ],
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason == "service_or_membership_page"


def test_qualify_publisher_inventory_candidates_rejects_gated_editorial_page_without_report_signals() -> None:
    candidate = _candidate(
        "https://mediacharge.com/publications/escaping-the-click-cost-trap-how-top-brands-win-with-full-funnel-mastery",
        "Escaping the Click-Cost Trap: How Top Brands Win with Full-Funnel Mastery",
    )

    response = qualify_publisher_inventory_candidates(
        PublisherInventoryCandidateQualityRequest(
            schema_version="1.0",
            publisher_name="Mediacharge",
            insights_url="https://mediacharge.com/publications/example",
            candidates=[candidate],
            settings=_settings(),
        ),
        _ctx(),
        inspection_client=lambda request, ctx: PublisherInventoryLandingPageInspectionResponse(
            schema_version="1.0",
            observations=[
                _observation(
                    canonical_url=candidate.canonical_url,
                    source_title=candidate.title,
                    final_url=candidate.canonical_url,
                    h1_title="Heading 1",
                    has_asset_type_term=True,
                    has_gated_form=True,
                    has_editorial_markers=True,
                )
            ],
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason in {
        "editorial_article_page",
        "marketing_cta_without_report_asset",
        "insufficient_report_signals",
    }


def test_qualify_publisher_inventory_candidates_rejects_gated_editorial_article_even_from_report_archive_source() -> None:
    candidate = PublisherInventoryCandidateScreeningItem(
        schema_version="1.0",
        canonical_url="https://www.mintel.com/insights/consumer-research/unilever-acquires-dr-squatch-cpg-brand-strategy-analysis",
        title="Unilever Acquires Dr. Squatch: What This $1.5B Deal Reveals About Modern CPG Brand Strategy",
        discovered_on_page_number=1,
        source_page_url="https://www.mintel.com/insights/downloads/",
    )

    response = qualify_publisher_inventory_candidates(
        PublisherInventoryCandidateQualityRequest(
            schema_version="1.0",
            publisher_name="Mintel",
            insights_url="https://www.mintel.com/insights/downloads/",
            candidates=[candidate],
            settings=_settings(),
        ),
        _ctx(),
        inspection_client=lambda request, ctx: PublisherInventoryLandingPageInspectionResponse(
            schema_version="1.0",
            observations=[
                _observation(
                    canonical_url=candidate.canonical_url,
                    source_title=candidate.title,
                    final_url=candidate.canonical_url,
                    final_title="Unilever Acquires Dr. Squatch for $1.5B: Brand Strategy Analysis",
                    h1_title="Unilever Acquires Dr. Squatch: What This $1.5B Deal Reveals About Modern CPG Brand Strategy",
                    has_asset_type_term=True,
                    has_gated_form=True,
                    has_document_structure=True,
                    has_price_or_purchase=True,
                    has_editorial_markers=True,
                    has_related_posts=True,
                )
            ],
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason in {
        "editorial_article_page",
        "insufficient_report_signals",
    }


def test_qualify_publisher_inventory_candidates_rejects_printable_editorial_trends_article() -> None:
    candidate = PublisherInventoryCandidateScreeningItem(
        schema_version="1.0",
        canonical_url="https://www.mintel.com/insights/retail/gen-z-online-shopping-behaviour-and-trends-what-brands-need-to-know",
        title="Gen Z Online Shopping Behaviour & Trends: What Brands Need to Know",
        discovered_on_page_number=1,
        source_page_url="https://www.mintel.com/insights/downloads/",
    )

    response = qualify_publisher_inventory_candidates(
        PublisherInventoryCandidateQualityRequest(
            schema_version="1.0",
            publisher_name="Mintel",
            insights_url="https://www.mintel.com/insights/downloads/",
            candidates=[candidate],
            settings=_settings(),
        ),
        _ctx(),
        inspection_client=lambda request, ctx: PublisherInventoryLandingPageInspectionResponse(
            schema_version="1.0",
            observations=[
                _observation(
                    canonical_url=candidate.canonical_url,
                    source_title=candidate.title,
                    final_url=candidate.canonical_url,
                    final_title="Gen Z Online Shopping Behaviour & Trends: What Brands Need to Know | Mintel",
                    h1_title="Gen Z Online Shopping Behaviour & Trends: What Brands Need to Know",
                    has_asset_type_term=True,
                    has_document_structure=True,
                    has_print_language=True,
                    has_gated_form=True,
                    has_editorial_markers=True,
                )
            ],
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason in {
        "editorial_article_page",
        "insufficient_report_signals",
    }


def test_qualify_publisher_inventory_candidates_rejects_methodology_pages_without_report_context() -> None:
    candidate = PublisherInventoryCandidateScreeningItem(
        schema_version="1.0",
        canonical_url="https://www.morningstar.com/research/signature",
        title="Our Signature Methodologies",
        discovered_on_page_number=1,
        source_page_url="https://www.morningstar.com/podcasts/investing-insights",
    )

    response = qualify_publisher_inventory_candidates(
        PublisherInventoryCandidateQualityRequest(
            schema_version="1.0",
            publisher_name="Morningstar",
            insights_url="https://www.morningstar.com/podcasts/investing-insights",
            candidates=[candidate],
            settings=_settings(),
        ),
        _ctx(),
        inspection_client=lambda request, ctx: PublisherInventoryLandingPageInspectionResponse(
            schema_version="1.0",
            observations=[
                _observation(
                    canonical_url=candidate.canonical_url,
                    source_title=candidate.title,
                    final_url=candidate.canonical_url,
                    h1_title="Our Signature Methodologies",
                    has_asset_type_term=True,
                )
            ],
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason in {
        "editorial_article_page",
        "insufficient_report_signals",
    }


def test_qualify_publisher_inventory_candidates_rejects_structured_editorial_publication_pages() -> None:
    candidate = PublisherInventoryCandidateScreeningItem(
        schema_version="1.0",
        canonical_url="https://mediacharge.com/publications/escaping-the-click-cost-trap-how-top-brands-win-with-full-funnel-mastery",
        title="Escaping the Click-Cost Trap: How Top Brands Win with Full-Funnel Mastery",
        discovered_on_page_number=1,
        source_page_url="https://mediacharge.com/publications/why-more-industry-leading-brands-use-gdn-for-brand-building-while-others-pour-budgets-into-social-channels",
    )

    response = qualify_publisher_inventory_candidates(
        PublisherInventoryCandidateQualityRequest(
            schema_version="1.0",
            publisher_name="Mediacharge",
            insights_url="https://mediacharge.com/publications/example",
            candidates=[candidate],
            settings=_settings(),
        ),
        _ctx(),
        inspection_client=lambda request, ctx: PublisherInventoryLandingPageInspectionResponse(
            schema_version="1.0",
            observations=[
                _observation(
                    canonical_url=candidate.canonical_url,
                    source_title=candidate.title,
                    final_url=candidate.canonical_url,
                    final_title="Escaping the Click-Cost Trap: How Top Brands Win with Full-Funnel Mastery",
                    h1_title="Heading 1",
                    has_asset_type_term=True,
                    has_download_language=True,
                    has_gated_form=True,
                    has_document_structure=True,
                    has_print_language=True,
                    has_price_or_purchase=True,
                    has_editorial_markers=True,
                    has_contact_sales_cta=True,
                )
            ],
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason in {
        "editorial_article_page",
        "insufficient_report_signals",
    }


def test_qualify_publisher_inventory_candidates_accepts_unreachable_publication_detail_pages() -> None:
    candidate = PublisherInventoryCandidateScreeningItem(
        schema_version="1.0",
        canonical_url="https://www.oecd.org/en/publications/methodology-for-the-oecd-index-of-digital-trade-integration-and-openness-indigo_b6d01a7b-en.html",
        title="Methodology for the OECD Index of Digital Trade Integration and Openness (INDIGO)",
        discovered_on_page_number=1,
        source_page_url="https://www.oecd.org/en/publications/reports.html",
    )

    response = qualify_publisher_inventory_candidates(
        PublisherInventoryCandidateQualityRequest(
            schema_version="1.0",
            publisher_name="OECD",
            insights_url="https://www.oecd.org/en/publications/reports.html",
            candidates=[candidate],
            settings=_settings(),
        ),
        _ctx(),
        inspection_client=lambda request, ctx: PublisherInventoryLandingPageInspectionResponse(
            schema_version="1.0",
            observations=[
                _observation(
                    canonical_url=candidate.canonical_url,
                    source_title=candidate.title,
                    final_url=candidate.canonical_url,
                    http_status_code=403,
                    fetch_error="Access denied",
                    has_dead_page_marker=True,
                )
            ],
        ),
    )

    assert [item.canonical_url for item in response.approved_items] == [
        candidate.canonical_url
    ]
    assert response.decisions[0].reason == "bot_protected_report_asset"


def test_qualify_publisher_inventory_candidates_accepts_dead_report_detail_page_from_report_archive_context() -> None:
    candidate = PublisherInventoryCandidateScreeningItem(
        schema_version="1.0",
        canonical_url="https://nielseniq.com/global/en/insights/report/2026/the-new-rules-of-relevance-eight-predictions-that-will-redefine-cpg-growth-in-a-rapidly-shifting-marketplace",
        title="The New Rules of Relevance: Eight Predictions That Will Redefine CPG Growth in a Rapidly Shifting Marketplace",
        discovered_on_page_number=1,
        source_page_url="https://nielseniq.com/global/en/insights/report",
    )

    response = qualify_publisher_inventory_candidates(
        PublisherInventoryCandidateQualityRequest(
            schema_version="1.0",
            publisher_name="NIQ",
            insights_url="https://nielseniq.com/global/en/insights",
            candidates=[candidate],
            settings=_settings(),
        ),
        _ctx(),
        inspection_client=lambda request, ctx: PublisherInventoryLandingPageInspectionResponse(
            schema_version="1.0",
            observations=[
                _observation(
                    canonical_url=candidate.canonical_url,
                    source_title=candidate.title,
                    final_url=candidate.canonical_url,
                    http_status_code=404,
                    fetch_error="Page not found",
                    has_dead_page_marker=True,
                )
            ],
        ),
    )

    assert [item.canonical_url for item in response.approved_items] == [
        candidate.canonical_url
    ]
    assert response.decisions[0].reason == "unreachable_report_asset"


def test_qualify_publisher_inventory_candidates_accepts_dead_editorial_context_report_when_report_signals_are_strong() -> None:
    candidate = _candidate(
        "https://nielseniq.com/global/en/insights/analysis/2026/winning-the-australian-omnichannel-liquor-shopper-purchasing-consumption-trends-for-2026",
        "Winning the Australian Omnichannel Liquor Shopper: Purchasing & Consumption Trends for 2026",
    )

    response = qualify_publisher_inventory_candidates(
        PublisherInventoryCandidateQualityRequest(
            schema_version="1.0",
            publisher_name="Nielsen IQ",
            insights_url="https://nielseniq.com/global/en/insights/report/",
            candidates=[candidate],
            settings=_settings(),
        ),
        _ctx(),
        inspection_client=lambda request, ctx: PublisherInventoryLandingPageInspectionResponse(
            schema_version="1.0",
            observations=[
                _observation(
                    canonical_url=candidate.canonical_url,
                    source_title=candidate.title,
                    final_url=candidate.canonical_url,
                    final_title="YouTube",
                    og_title="Winning the Australian Omnichannel Liquor Shopper: Purchasing & Consumption Trends for 2026",
                    h1_title="Winning the Australian Omnichannel Liquor Shopper: Purchasing & Consumption Trends for 2026",
                    has_asset_type_term=True,
                    has_document_structure=True,
                    has_print_language=True,
                    has_editorial_markers=True,
                    has_newsletter_cta=True,
                    has_dead_page_marker=True,
                )
            ],
        ),
    )

    assert [item.canonical_url for item in response.approved_items] == [
        candidate.canonical_url
    ]
    assert response.decisions[0].reason == "unreachable_report_asset"


def test_qualify_publisher_inventory_candidates_does_not_rescue_transient_service_page() -> None:
    candidate = _candidate(
        "https://www.paycom.com/who-we-help/large-business/hr-software",
        "HR software for enterprise businesses",
    )

    response = qualify_publisher_inventory_candidates(
        PublisherInventoryCandidateQualityRequest(
            schema_version="1.0",
            publisher_name="Paycom",
            insights_url="https://www.paycom.com/resources/nucleus-research-beti-bolsters-payroll-success",
            candidates=[candidate],
            settings=_settings(),
        ),
        _ctx(),
        inspection_client=lambda request, ctx: PublisherInventoryLandingPageInspectionResponse(
            schema_version="1.0",
            observations=[
                _observation(
                    canonical_url=candidate.canonical_url,
                    source_title=candidate.title,
                    final_url=candidate.canonical_url,
                    final_title="Error Page",
                    fetch_error="Read timed out",
                    has_dead_page_marker=True,
                )
            ],
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].accepted is False
