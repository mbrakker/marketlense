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
