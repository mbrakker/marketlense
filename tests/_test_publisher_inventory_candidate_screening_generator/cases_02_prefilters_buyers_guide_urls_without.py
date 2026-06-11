# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403

def test_screen_publisher_inventory_candidates_prefilters_buyers_guide_urls_without_llm() -> (
    None
):
    openai_client = BatchAwareOpenAIClient()

    response = screen_publisher_inventory_candidates(
        PublisherInventoryCandidateScreeningRequest(
            schema_version="1.0",
            publisher_name="Example Publisher",
            insights_url="https://example.com/resources",
            candidates=[
                PublisherInventoryCandidateScreeningItem(
                    schema_version="1.0",
                    canonical_url="https://example.com/resources/buyers-guide-enterprise-governance-platforms",
                    title="Learn more",
                    discovered_on_page_number=1,
                    source_page_url="https://example.com/resources",
                )
            ],
            settings=_settings(),
        ),
        _ctx(),
        openai_client=openai_client,
        prompt_client=RecordingPromptClient(),
    )

    assert len(openai_client.requests) == 0
    assert [item.canonical_url for item in response.approved_items] == [
        "https://example.com/resources/buyers-guide-enterprise-governance-platforms"
    ]
    assert response.decisions[0].reason == "strong_report_detail_url_prefilter"

def test_screen_publisher_inventory_candidates_prefilters_editorial_report_detail_urls_without_llm() -> (
    None
):
    openai_client = BatchAwareOpenAIClient()

    response = screen_publisher_inventory_candidates(
        PublisherInventoryCandidateScreeningRequest(
            schema_version="1.0",
            publisher_name="Example Publisher",
            insights_url="https://example.com/insights",
            candidates=[
                PublisherInventoryCandidateScreeningItem(
                    schema_version="1.0",
                    canonical_url="https://example.com/news/global-advertising-forecast-2026",
                    title="Global Advertising Forecast 2026",
                    discovered_on_page_number=1,
                    source_page_url="https://example.com/insights",
                )
            ],
            settings=_settings(),
        ),
        _ctx(),
        openai_client=openai_client,
        prompt_client=RecordingPromptClient(),
    )

    assert len(openai_client.requests) == 0
    assert [item.canonical_url for item in response.approved_items] == [
        "https://example.com/news/global-advertising-forecast-2026"
    ]
    assert response.decisions[0].reason == "editorial_report_detail_url_prefilter"

def test_screen_publisher_inventory_candidates_prefilters_blog_report_detail_urls_without_llm() -> (
    None
):
    openai_client = BatchAwareOpenAIClient()

    response = screen_publisher_inventory_candidates(
        PublisherInventoryCandidateScreeningRequest(
            schema_version="1.0",
            publisher_name="Cardlytics",
            insights_url="https://www.cardlytics.com/research-and-insights",
            candidates=[
                PublisherInventoryCandidateScreeningItem(
                    schema_version="1.0",
                    canonical_url="https://www.cardlytics.com/blog/loyalty-movement-report-qsr",
                    title="Loyalty Movement Report: QSR",
                    discovered_on_page_number=1,
                    source_page_url="https://www.cardlytics.com/research-and-insights",
                )
            ],
            settings=_settings(),
        ),
        _ctx(),
        openai_client=openai_client,
        prompt_client=RecordingPromptClient(),
    )

    assert len(openai_client.requests) == 0
    assert [item.canonical_url for item in response.approved_items] == [
        "https://www.cardlytics.com/blog/loyalty-movement-report-qsr"
    ]
    assert response.decisions[0].reason == "editorial_report_detail_url_prefilter"

def test_screen_publisher_inventory_candidates_prefilters_direct_detail_sources_without_llm() -> (
    None
):
    openai_client = BatchAwareOpenAIClient()

    response = screen_publisher_inventory_candidates(
        PublisherInventoryCandidateScreeningRequest(
            schema_version="1.0",
            publisher_name="Capgemini",
            insights_url="https://www.capgemini.com/insights/research-library/ai-perspectives-2026",
            candidates=[
                PublisherInventoryCandidateScreeningItem(
                    schema_version="1.0",
                    canonical_url="https://www.capgemini.com/insights/research-library/ai-perspectives-2026",
                    title="AI Perspectives 2026",
                    discovered_on_page_number=1,
                    source_page_url="https://www.capgemini.com/insights/research-library/ai-perspectives-2026",
                )
            ],
            settings=_settings(),
        ),
        _ctx(),
        openai_client=openai_client,
        prompt_client=RecordingPromptClient(),
    )

    assert len(openai_client.requests) == 0
    assert [item.canonical_url for item in response.approved_items] == [
        "https://www.capgemini.com/insights/research-library/ai-perspectives-2026"
    ]
    assert response.decisions[0].reason == "direct_detail_source_prefilter"

def test_screen_publisher_inventory_candidates_rejects_collection_root_hubs_without_llm() -> (
    None
):
    openai_client = BatchAwareOpenAIClient()

    response = screen_publisher_inventory_candidates(
        PublisherInventoryCandidateScreeningRequest(
            schema_version="1.0",
            publisher_name="Cardlytics",
            insights_url="https://www.cardlytics.com/research-and-insights",
            candidates=[
                PublisherInventoryCandidateScreeningItem(
                    schema_version="1.0",
                    canonical_url="https://www.cardlytics.com/research-and-insights",
                    title="Cardlytics Research | Actionable Consumer Insights",
                    discovered_on_page_number=1,
                    source_page_url="https://www.cardlytics.com/research-and-insights",
                )
            ],
            settings=_settings(),
        ),
        _ctx(),
        openai_client=openai_client,
        prompt_client=RecordingPromptClient(),
    )

    assert len(openai_client.requests) == 0
    assert response.approved_items == []
    assert response.decisions[0].reason == "low_report_probability_prefilter"

def test_screen_publisher_inventory_candidates_rejects_editorial_blog_posts_without_report_detail_signals() -> (
    None
):
    openai_client = BatchAwareOpenAIClient()

    response = screen_publisher_inventory_candidates(
        PublisherInventoryCandidateScreeningRequest(
            schema_version="1.0",
            publisher_name="Cardlytics",
            insights_url="https://www.cardlytics.com/research-and-insights",
            candidates=[
                PublisherInventoryCandidateScreeningItem(
                    schema_version="1.0",
                    canonical_url="https://www.cardlytics.com/blog/driving-customer-acquisition-loyalty-with-card-linked-offers-clos",
                    title="Driving Customer Acquisition & Loyalty with Card-Linked Offers (CLOs)",
                    discovered_on_page_number=1,
                    source_page_url="https://www.cardlytics.com/research-and-insights",
                )
            ],
            settings=_settings(),
        ),
        _ctx(),
        openai_client=openai_client,
        prompt_client=RecordingPromptClient(),
    )

    assert len(openai_client.requests) == 0
    assert response.approved_items == []
    assert response.decisions[0].reason == "low_report_probability_prefilter"

def test_screen_publisher_inventory_candidates_keeps_distinct_urls_for_generic_cta_titles() -> (
    None
):
    openai_client = BatchAwareOpenAIClient()

    response = screen_publisher_inventory_candidates(
        PublisherInventoryCandidateScreeningRequest(
            schema_version="1.0",
            publisher_name="Example Publisher",
            insights_url="https://example.com/resources",
            candidates=[
                PublisherInventoryCandidateScreeningItem(
                    schema_version="1.0",
                    canonical_url="https://example.com/knowledge_hub/global-advertising-report-2026",
                    title="Read more",
                    discovered_on_page_number=1,
                    source_page_url="https://example.com/resources",
                ),
                PublisherInventoryCandidateScreeningItem(
                    schema_version="1.0",
                    canonical_url="https://example.com/knowledge_hub/guidelines-for-incremental-measurement",
                    title="Read more",
                    discovered_on_page_number=1,
                    source_page_url="https://example.com/resources",
                ),
            ],
            settings=_settings(),
        ),
        _ctx(),
        openai_client=openai_client,
        prompt_client=RecordingPromptClient(),
    )

    assert len(openai_client.requests) == 0
    assert [item.canonical_url for item in response.approved_items] == [
        "https://example.com/knowledge_hub/global-advertising-report-2026",
        "https://example.com/knowledge_hub/guidelines-for-incremental-measurement",
    ]
    assert all(decision.accepted for decision in response.decisions)

def test_screen_publisher_inventory_candidates_keeps_distinct_generic_annual_report_downloads() -> (
    None
):
    openai_client = BatchAwareOpenAIClient()

    response = screen_publisher_inventory_candidates(
        PublisherInventoryCandidateScreeningRequest(
            schema_version="1.0",
            publisher_name="Example Publisher",
            insights_url="https://example.com/annual-report",
            candidates=[
                PublisherInventoryCandidateScreeningItem(
                    schema_version="1.0",
                    canonical_url="https://cdn.example.com/annual_report_2025_en.pdf",
                    title="Download Annual Report",
                    discovered_on_page_number=1,
                    source_page_url="https://example.com/annual-report",
                ),
                PublisherInventoryCandidateScreeningItem(
                    schema_version="1.0",
                    canonical_url="https://cdn.example.com/annual_report_2024_en.pdf",
                    title="Download Annual Report",
                    discovered_on_page_number=1,
                    source_page_url="https://example.com/annual-report",
                ),
            ],
            settings=_settings(),
        ),
        _ctx(),
        openai_client=openai_client,
        prompt_client=RecordingPromptClient(),
    )

    assert len(openai_client.requests) == 0
    assert [item.canonical_url for item in response.approved_items] == [
        "https://cdn.example.com/annual_report_2025_en.pdf",
        "https://cdn.example.com/annual_report_2024_en.pdf",
    ]
    assert all(decision.accepted for decision in response.decisions)

def test_screen_publisher_inventory_candidates_accepts_query_string_pdf_when_source_page_is_report_like() -> (
    None
):
    openai_client = BatchAwareOpenAIClient()

    response = screen_publisher_inventory_candidates(
        PublisherInventoryCandidateScreeningRequest(
            schema_version="1.0",
            publisher_name="Example Publisher",
            insights_url="https://example.com/annual-report",
            candidates=[
                PublisherInventoryCandidateScreeningItem(
                    schema_version="1.0",
                    canonical_url="https://cdn.example.com/2025-report.pdf?la=en",
                    title="Download PDF",
                    discovered_on_page_number=1,
                    source_page_url="https://example.com/annual-report",
                )
            ],
            settings=_settings(),
        ),
        _ctx(),
        openai_client=openai_client,
        prompt_client=RecordingPromptClient(),
    )

    assert len(openai_client.requests) == 0
    assert [item.canonical_url for item in response.approved_items] == [
        "https://cdn.example.com/2025-report.pdf?la=en"
    ]
    assert response.decisions[0].accepted is True

def test_screen_publisher_inventory_candidates_rejects_generic_cta_insights_articles_without_specific_report_slug() -> (
    None
):
    openai_client = BatchAwareOpenAIClient()

    response = screen_publisher_inventory_candidates(
        PublisherInventoryCandidateScreeningRequest(
            schema_version="1.0",
            publisher_name="Example Publisher",
            insights_url="https://example.com/insights",
            candidates=[
                PublisherInventoryCandidateScreeningItem(
                    schema_version="1.0",
                    canonical_url="https://example.com/insights/the-ultimate-guide-to-social-media",
                    title="Read article",
                    discovered_on_page_number=1,
                    source_page_url="https://example.com/insights",
                )
            ],
            settings=_settings(),
        ),
        _ctx(),
        openai_client=openai_client,
        prompt_client=RecordingPromptClient(),
    )

    assert len(openai_client.requests) == 0
    assert response.approved_items == []
    assert response.decisions[0].reason == "low_report_probability_prefilter"

def test_screen_publisher_inventory_candidates_rejects_pdf_without_report_signals() -> (
    None
):
    openai_client = BatchAwareOpenAIClient()

    response = screen_publisher_inventory_candidates(
        PublisherInventoryCandidateScreeningRequest(
            schema_version="1.0",
            publisher_name="Example Publisher",
            insights_url="https://example.com/insights",
            candidates=[
                PublisherInventoryCandidateScreeningItem(
                    schema_version="1.0",
                    canonical_url="https://cdn.example.com/Example-Group-Reprint.pdf",
                    title="(opens in a new tab)",
                    discovered_on_page_number=1,
                    source_page_url="https://example.com/insights",
                )
            ],
            settings=_settings(),
        ),
        _ctx(),
        openai_client=openai_client,
        prompt_client=RecordingPromptClient(),
    )

    assert len(openai_client.requests) == 0
    assert response.approved_items == []
    assert response.decisions[0].reason == "low_report_probability_prefilter"

def test_screen_publisher_inventory_candidates_truncates_long_titles_in_prompt() -> (
    None
):
    long_title = "2026 Search Analysis " + ("A" * 500)
    openai_client = RecordingOpenAIClient(
        payload={
            "decisions": [
                {
                    "canonical_url": "https://example.com/library/long-title-item",
                    "accepted": True,
                    "reason": "Looks report-like.",
                }
            ]
        }
    )

    screen_publisher_inventory_candidates(
        PublisherInventoryCandidateScreeningRequest(
            schema_version="1.0",
            publisher_name="Example Publisher",
            insights_url="https://example.com/insights",
            candidates=[
                PublisherInventoryCandidateScreeningItem(
                    schema_version="1.0",
                    canonical_url="https://example.com/library/long-title-item",
                    title=long_title,
                    discovered_on_page_number=1,
                    source_page_url="https://example.com/insights",
                )
            ],
            settings=_settings(),
        ),
        _ctx(),
        openai_client=openai_client,
        prompt_client=RecordingPromptClient(),
    )

    rendered_user_prompt = openai_client.requests[0][0].user_prompt
    assert long_title not in rendered_user_prompt
    assert "2026 Search Analysis" in rendered_user_prompt
    assert "\\u2026" in rendered_user_prompt

def test_screen_publisher_inventory_candidates_repairs_missing_batch_decisions() -> (
    None
):
    candidates = [
        PublisherInventoryCandidateScreeningItem(
            schema_version="1.0",
            canonical_url="https://example.com/report-one",
            title="Report One",
            discovered_on_page_number=1,
            source_page_url="https://example.com/insights",
        ),
        PublisherInventoryCandidateScreeningItem(
            schema_version="1.0",
            canonical_url="https://example.com/report-two",
            title="Report Two",
            discovered_on_page_number=1,
            source_page_url="https://example.com/insights",
        ),
    ]
    openai_client = RepairingOpenAIClient()

    response = screen_publisher_inventory_candidates(
        PublisherInventoryCandidateScreeningRequest(
            schema_version="1.0",
            publisher_name="Example Publisher",
            insights_url="https://example.com/insights",
            candidates=candidates,
            settings=_settings(),
        ),
        _ctx(),
        openai_client=openai_client,
        prompt_client=RecordingPromptClient(),
    )

    assert len(openai_client.requests) == 2
    assert [item.canonical_url for item in response.approved_items] == [
        "https://example.com/report-one",
        "https://example.com/report-two",
    ]
    assert response.rejected_items == []
    assert response.request_id == "req-1,req-2"

def test_screen_publisher_inventory_candidates_accepts_human_titles_from_report_archive_context() -> (
    None
):
    openai_client = BatchAwareOpenAIClient()

    response = screen_publisher_inventory_candidates(
        PublisherInventoryCandidateScreeningRequest(
            schema_version="1.0",
            publisher_name="OECD",
            insights_url="https://www.oecd.org/en/publications/reports.html",
            candidates=[
                PublisherInventoryCandidateScreeningItem(
                    schema_version="1.0",
                    canonical_url="https://www.oecd.org/en/publications/bridging-the-finance-gap-for-women-entrepreneurs_75b52972-en.html",
                    title="Bridging the Finance Gap for Women Entrepreneurs",
                    discovered_on_page_number=1,
                    source_page_url="https://www.oecd.org/en/publications/reports.html",
                )
            ],
            settings=_settings(),
        ),
        _ctx(),
        openai_client=openai_client,
        prompt_client=RecordingPromptClient(),
    )

    assert len(openai_client.requests) == 0
    assert [item.canonical_url for item in response.approved_items] == [
        "https://www.oecd.org/en/publications/bridging-the-finance-gap-for-women-entrepreneurs_75b52972-en.html"
    ]
    assert response.decisions[0].reason in {
        "report_archive_context_prefilter",
        "strong_report_detail_url_prefilter",
    }

__all__ = [
    "test_screen_publisher_inventory_candidates_prefilters_buyers_guide_urls_without_llm",
    "test_screen_publisher_inventory_candidates_prefilters_editorial_report_detail_urls_without_llm",
    "test_screen_publisher_inventory_candidates_prefilters_blog_report_detail_urls_without_llm",
    "test_screen_publisher_inventory_candidates_prefilters_direct_detail_sources_without_llm",
    "test_screen_publisher_inventory_candidates_rejects_collection_root_hubs_without_llm",
    "test_screen_publisher_inventory_candidates_rejects_editorial_blog_posts_without_report_detail_signals",
    "test_screen_publisher_inventory_candidates_keeps_distinct_urls_for_generic_cta_titles",
    "test_screen_publisher_inventory_candidates_keeps_distinct_generic_annual_report_downloads",
    "test_screen_publisher_inventory_candidates_accepts_query_string_pdf_when_source_page_is_report_like",
    "test_screen_publisher_inventory_candidates_rejects_generic_cta_insights_articles_without_specific_report_slug",
    "test_screen_publisher_inventory_candidates_rejects_pdf_without_report_signals",
    "test_screen_publisher_inventory_candidates_truncates_long_titles_in_prompt",
    "test_screen_publisher_inventory_candidates_repairs_missing_batch_decisions",
    "test_screen_publisher_inventory_candidates_accepts_human_titles_from_report_archive_context",
]
