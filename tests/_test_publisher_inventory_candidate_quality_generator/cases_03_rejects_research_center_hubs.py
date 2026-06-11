# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403

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
        inspection_client=lambda request, ctx: (
            PublisherInventoryLandingPageInspectionResponse(
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
            )
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason == "service_or_membership_page"

def test_qualify_publisher_inventory_candidates_rejects_research_center_hubs_even_with_gated_signals() -> (
    None
):
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
        inspection_client=lambda request, ctx: (
            PublisherInventoryLandingPageInspectionResponse(
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
            )
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason == "service_or_membership_page"

def test_qualify_publisher_inventory_candidates_rejects_capability_pages_even_with_report_words_in_title() -> (
    None
):
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
        inspection_client=lambda request, ctx: (
            PublisherInventoryLandingPageInspectionResponse(
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
            )
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
        inspection_client=lambda request, ctx: (
            PublisherInventoryLandingPageInspectionResponse(
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
            )
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
        inspection_client=lambda request, ctx: (
            PublisherInventoryLandingPageInspectionResponse(
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
            )
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
        inspection_client=lambda request, ctx: (
            PublisherInventoryLandingPageInspectionResponse(
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
            )
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason == "service_or_membership_page"

def test_qualify_publisher_inventory_candidates_accepts_unreachable_report_documents() -> (
    None
):
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
        inspection_client=lambda request, ctx: (
            PublisherInventoryLandingPageInspectionResponse(
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
            )
        ),
    )

    assert [item.canonical_url for item in response.approved_items] == [
        candidate.canonical_url
    ]
    assert response.decisions[0].reason == "unreachable_document_asset"

def test_qualify_publisher_inventory_candidates_rejects_self_service_help_pages() -> (
    None
):
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
        inspection_client=lambda request, ctx: (
            PublisherInventoryLandingPageInspectionResponse(
                schema_version="1.0",
                observations=[
                    _observation(
                        canonical_url=candidate.canonical_url,
                        source_title=candidate.title,
                        final_url=candidate.canonical_url,
                        h1_title="How to get your free annual credit reports",
                    )
                ],
            )
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason == "self_service_or_signup_page"

def test_qualify_publisher_inventory_candidates_rejects_consumer_self_service_report_products() -> (
    None
):
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
        inspection_client=lambda request, ctx: (
            PublisherInventoryLandingPageInspectionResponse(
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
            )
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
        inspection_client=lambda request, ctx: (
            PublisherInventoryLandingPageInspectionResponse(
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
            )
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason == "audio_editorial_page"

def test_qualify_publisher_inventory_candidates_accepts_buyer_guide_report_detail_pages_without_document_markup() -> (
    None
):
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
        inspection_client=lambda request, ctx: (
            PublisherInventoryLandingPageInspectionResponse(
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
            )
        ),
    )

    assert [item.canonical_url for item in response.approved_items] == [
        candidate.canonical_url
    ]
    assert response.decisions[0].reason == "report_detail_landing_page"

def test_qualify_publisher_inventory_candidates_accepts_report_detail_pages_with_generic_editorial_chrome() -> (
    None
):
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
        inspection_client=lambda request, ctx: (
            PublisherInventoryLandingPageInspectionResponse(
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
            )
        ),
    )

    assert [item.canonical_url for item in response.approved_items] == [
        candidate.canonical_url
    ]
    assert response.decisions[0].reason == "report_detail_landing_page"

def test_qualify_publisher_inventory_candidates_accepts_trend_detail_pages_with_generic_titles() -> (
    None
):
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
        inspection_client=lambda request, ctx: (
            PublisherInventoryLandingPageInspectionResponse(
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
            )
        ),
    )

    assert [item.canonical_url for item in response.approved_items] == [
        candidate.canonical_url
    ]
    assert response.decisions[0].reason == "report_detail_landing_page"

def test_qualify_publisher_inventory_candidates_rejects_dated_editorial_pages_even_with_generic_form_signals() -> (
    None
):
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
        inspection_client=lambda request, ctx: (
            PublisherInventoryLandingPageInspectionResponse(
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
            )
        ),
    )

    assert response.approved_items == []
    assert response.decisions[0].reason in {
        "editorial_article_page",
        "insufficient_report_signals",
    }

def test_qualify_publisher_inventory_candidates_accepts_gated_editorial_blog_post_when_report_document_signals_are_strong() -> (
    None
):
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
        inspection_client=lambda request, ctx: (
            PublisherInventoryLandingPageInspectionResponse(
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
            )
        ),
    )

    assert [item.canonical_url for item in response.approved_items] == [
        candidate.canonical_url
    ]
    assert response.decisions[0].reason == "gated_report_asset"

def test_qualify_publisher_inventory_candidates_rejects_editorial_blog_report_post_without_document_structure() -> (
    None
):
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
        inspection_client=lambda request, ctx: (
            PublisherInventoryLandingPageInspectionResponse(
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
                        has_document_structure=False,
                        has_editorial_url_pattern=True,
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

def test_qualify_publisher_inventory_candidates_accepts_editorial_path_when_title_has_specific_report_signal() -> (
    None
):
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
        inspection_client=lambda request, ctx: (
            PublisherInventoryLandingPageInspectionResponse(
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
            )
        ),
    )

    assert [item.canonical_url for item in response.approved_items] == [
        candidate.canonical_url
    ]
    assert response.decisions[0].reason == "gated_report_asset"

def test_qualify_publisher_inventory_candidates_accepts_related_post_guide_when_document_signals_are_strong() -> (
    None
):
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
        inspection_client=lambda request, ctx: (
            PublisherInventoryLandingPageInspectionResponse(
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
            )
        ),
    )

    assert [item.canonical_url for item in response.approved_items] == [
        candidate.canonical_url
    ]
    assert response.decisions[0].reason == "printable_report_page"

__all__ = [
    "test_qualify_publisher_inventory_candidates_rejects_research_center_hubs",
    "test_qualify_publisher_inventory_candidates_rejects_research_center_hubs_even_with_gated_signals",
    "test_qualify_publisher_inventory_candidates_rejects_capability_pages_even_with_report_words_in_title",
    "test_qualify_publisher_inventory_candidates_rejects_collection_root_hubs",
    "test_qualify_publisher_inventory_candidates_rejects_trends_hub_roots",
    "test_qualify_publisher_inventory_candidates_rejects_generic_research_hubs",
    "test_qualify_publisher_inventory_candidates_accepts_unreachable_report_documents",
    "test_qualify_publisher_inventory_candidates_rejects_self_service_help_pages",
    "test_qualify_publisher_inventory_candidates_rejects_consumer_self_service_report_products",
    "test_qualify_publisher_inventory_candidates_rejects_audio_editorial_pages",
    "test_qualify_publisher_inventory_candidates_accepts_buyer_guide_report_detail_pages_without_document_markup",
    "test_qualify_publisher_inventory_candidates_accepts_report_detail_pages_with_generic_editorial_chrome",
    "test_qualify_publisher_inventory_candidates_accepts_trend_detail_pages_with_generic_titles",
    "test_qualify_publisher_inventory_candidates_rejects_dated_editorial_pages_even_with_generic_form_signals",
    "test_qualify_publisher_inventory_candidates_accepts_gated_editorial_blog_post_when_report_document_signals_are_strong",
    "test_qualify_publisher_inventory_candidates_rejects_editorial_blog_report_post_without_document_structure",
    "test_qualify_publisher_inventory_candidates_accepts_editorial_path_when_title_has_specific_report_signal",
    "test_qualify_publisher_inventory_candidates_accepts_related_post_guide_when_document_signals_are_strong",
]
