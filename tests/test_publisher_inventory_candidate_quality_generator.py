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
    assert response.decisions[0].reason == "gated_report_asset"
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
    assert response.decisions[0].reason == "editorial_article_page"


def test_qualify_publisher_inventory_candidates_accepts_gated_report_on_editorial_path_when_report_signals_are_strong() -> None:
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

    assert [item.canonical_url for item in response.approved_items] == [
        candidate.canonical_url
    ]
    assert response.decisions[0].reason == "gated_report_asset"


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
    assert response.decisions[0].reason == "editorial_article_page"
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
