# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403

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
        inspection_client=lambda request, ctx: (
            PublisherInventoryLandingPageInspectionResponse(
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
            )
        ),
    )

    assert [item.canonical_url for item in response.approved_items] == [
        candidate.canonical_url
    ]
    assert response.decisions[0].reason == "printable_report_page"

def test_qualify_publisher_inventory_candidates_accepts_slug_signaled_ebook_page() -> (
    None
):
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
        inspection_client=lambda request, ctx: (
            PublisherInventoryLandingPageInspectionResponse(
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
            )
        ),
    )

    assert [item.canonical_url for item in response.approved_items] == [
        candidate.canonical_url
    ]
    assert response.decisions[0].reason == "printable_report_page"

def test_qualify_publisher_inventory_candidates_rejects_thought_leadership_article_with_generic_section_heading() -> (
    None
):
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
        inspection_client=lambda request, ctx: (
            PublisherInventoryLandingPageInspectionResponse(
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
            )
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason in {
        "editorial_article_page",
        "insufficient_report_signals",
    }
    assert (
        response.decisions[0].resolved_title
        == "Creating Relevance Through the Convergence of Content, Creators & Commerce"
    )

def test_qualify_publisher_inventory_candidates_accepts_report_hub_pages_with_download_and_related_links() -> (
    None
):
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
        inspection_client=lambda request, ctx: (
            PublisherInventoryLandingPageInspectionResponse(
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
            )
        ),
    )

    assert response.approved_items != []
    assert response.decisions[0].reason in {
        "downloadable_report_asset",
        "printable_report_page",
    }

def test_qualify_publisher_inventory_candidates_rejects_newsletter_articles_without_real_report_signals() -> (
    None
):
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
        inspection_client=lambda request, ctx: (
            PublisherInventoryLandingPageInspectionResponse(
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
            )
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason == "newsletter_article_page"

def test_qualify_publisher_inventory_candidates_rejects_software_pages_with_report_like_titles() -> (
    None
):
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
        inspection_client=lambda request, ctx: (
            PublisherInventoryLandingPageInspectionResponse(
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
            )
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
        inspection_client=lambda request, ctx: (
            PublisherInventoryLandingPageInspectionResponse(
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
            )
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason == "service_or_membership_page"

def test_qualify_publisher_inventory_candidates_rejects_gated_editorial_page_without_report_signals() -> (
    None
):
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
        inspection_client=lambda request, ctx: (
            PublisherInventoryLandingPageInspectionResponse(
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
            )
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason in {
        "editorial_article_page",
        "marketing_cta_without_report_asset",
        "insufficient_report_signals",
    }

def test_qualify_publisher_inventory_candidates_rejects_gated_editorial_article_even_from_report_archive_source() -> (
    None
):
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
        inspection_client=lambda request, ctx: (
            PublisherInventoryLandingPageInspectionResponse(
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
            )
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason in {
        "editorial_article_page",
        "insufficient_report_signals",
    }

def test_qualify_publisher_inventory_candidates_rejects_printable_editorial_trends_article() -> (
    None
):
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
        inspection_client=lambda request, ctx: (
            PublisherInventoryLandingPageInspectionResponse(
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
            )
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason in {
        "editorial_article_page",
        "insufficient_report_signals",
    }

def test_qualify_publisher_inventory_candidates_rejects_methodology_pages_without_report_context() -> (
    None
):
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
        inspection_client=lambda request, ctx: (
            PublisherInventoryLandingPageInspectionResponse(
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
            )
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason in {
        "editorial_article_page",
        "insufficient_report_signals",
    }

def test_qualify_publisher_inventory_candidates_rejects_structured_editorial_publication_pages() -> (
    None
):
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
        inspection_client=lambda request, ctx: (
            PublisherInventoryLandingPageInspectionResponse(
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
            )
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason in {
        "editorial_article_page",
        "insufficient_report_signals",
    }

def test_qualify_publisher_inventory_candidates_accepts_unreachable_publication_detail_pages() -> (
    None
):
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
        inspection_client=lambda request, ctx: (
            PublisherInventoryLandingPageInspectionResponse(
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
            )
        ),
    )

    assert [item.canonical_url for item in response.approved_items] == [
        candidate.canonical_url
    ]
    assert response.decisions[0].reason == "bot_protected_report_asset"

def test_qualify_publisher_inventory_candidates_accepts_dead_report_detail_page_from_report_archive_context() -> (
    None
):
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
        inspection_client=lambda request, ctx: (
            PublisherInventoryLandingPageInspectionResponse(
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
            )
        ),
    )

    assert [item.canonical_url for item in response.approved_items] == [
        candidate.canonical_url
    ]
    assert response.decisions[0].reason == "unreachable_report_asset"

def test_qualify_publisher_inventory_candidates_accepts_dead_editorial_context_report_when_report_signals_are_strong() -> (
    None
):
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
        inspection_client=lambda request, ctx: (
            PublisherInventoryLandingPageInspectionResponse(
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
            )
        ),
    )

    assert [item.canonical_url for item in response.approved_items] == [
        candidate.canonical_url
    ]
    assert response.decisions[0].reason == "unreachable_report_asset"

def test_qualify_publisher_inventory_candidates_does_not_rescue_transient_service_page() -> (
    None
):
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
        inspection_client=lambda request, ctx: (
            PublisherInventoryLandingPageInspectionResponse(
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
            )
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].accepted is False

__all__ = [
    "test_qualify_publisher_inventory_candidates_accepts_transparency_reports",
    "test_qualify_publisher_inventory_candidates_accepts_slug_signaled_ebook_page",
    "test_qualify_publisher_inventory_candidates_rejects_thought_leadership_article_with_generic_section_heading",
    "test_qualify_publisher_inventory_candidates_accepts_report_hub_pages_with_download_and_related_links",
    "test_qualify_publisher_inventory_candidates_rejects_newsletter_articles_without_real_report_signals",
    "test_qualify_publisher_inventory_candidates_rejects_software_pages_with_report_like_titles",
    "test_qualify_publisher_inventory_candidates_rejects_gated_career_pages",
    "test_qualify_publisher_inventory_candidates_rejects_gated_editorial_page_without_report_signals",
    "test_qualify_publisher_inventory_candidates_rejects_gated_editorial_article_even_from_report_archive_source",
    "test_qualify_publisher_inventory_candidates_rejects_printable_editorial_trends_article",
    "test_qualify_publisher_inventory_candidates_rejects_methodology_pages_without_report_context",
    "test_qualify_publisher_inventory_candidates_rejects_structured_editorial_publication_pages",
    "test_qualify_publisher_inventory_candidates_accepts_unreachable_publication_detail_pages",
    "test_qualify_publisher_inventory_candidates_accepts_dead_report_detail_page_from_report_archive_context",
    "test_qualify_publisher_inventory_candidates_accepts_dead_editorial_context_report_when_report_signals_are_strong",
    "test_qualify_publisher_inventory_candidates_does_not_rescue_transient_service_page",
]
