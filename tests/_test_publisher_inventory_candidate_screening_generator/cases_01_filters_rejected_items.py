# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403

def test_screen_publisher_inventory_candidates_filters_rejected_items(
    caplog,
    assert_logs_have_required_fields,
    assert_no_defaulted_required_fields,
) -> None:
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
            canonical_url="https://example.com/facebook",
            title="Facebook",
            discovered_on_page_number=1,
            source_page_url="https://example.com/insights",
        ),
    ]
    openai_client = RecordingOpenAIClient(
        payload={
            "decisions": [
                {
                    "canonical_url": "https://example.com/report-one",
                    "accepted": True,
                    "reason": "Substantive report asset.",
                },
                {
                    "canonical_url": "https://example.com/facebook",
                    "accepted": False,
                    "reason": "Social link, not a report.",
                },
            ]
        }
    )
    caplog.set_level(
        logging.INFO,
        logger="market_lense.publisher_inventory_candidate_screening_generator",
    )

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

    assert [item.canonical_url for item in response.approved_items] == [
        "https://example.com/report-one"
    ]
    assert [item.canonical_url for item in response.rejected_items] == [
        "https://example.com/facebook"
    ]
    assert openai_client.requests[0][0].model == "gpt-5-nano"
    assert (
        '"canonical_url": "https://example.com/report-one"'
        in openai_client.requests[0][0].user_prompt
    )
    assert response.request_id == "req-1"
    assert_no_defaulted_required_fields(response)
    assert_no_defaulted_required_fields(response.decisions[0])
    records = [
        json.loads(record.message)
        for record in caplog.records
        if record.name
        == "market_lense.publisher_inventory_candidate_screening_generator"
    ]
    assert_logs_have_required_fields(records)

def test_screen_publisher_inventory_candidates_falls_back_when_decisions_remain_missing() -> (
    None
):
    openai_client = RecordingOpenAIClient(
        payload={
            "decisions": [
                {
                    "canonical_url": "https://example.com/report-one",
                    "accepted": True,
                    "reason": "Substantive report asset.",
                }
            ]
        }
    )

    response = screen_publisher_inventory_candidates(
        PublisherInventoryCandidateScreeningRequest(
            schema_version="1.0",
            publisher_name="Example Publisher",
            insights_url="https://example.com/insights",
            candidates=[
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
            ],
            settings=_settings(),
        ),
        _ctx(),
        openai_client=openai_client,
        prompt_client=RecordingPromptClient(),
    )

    assert [item.canonical_url for item in response.approved_items] == [
        "https://example.com/report-one",
        "https://example.com/report-two",
    ]
    fallback_decision = next(
        decision
        for decision in response.decisions
        if decision.canonical_url == "https://example.com/report-two"
    )
    assert fallback_decision.accepted is True
    assert fallback_decision.reason == "fallback_report_signal"

def test_screen_publisher_inventory_candidates_skips_llm_when_disabled() -> None:
    settings = replace(_settings(), candidate_screening_enabled=False)

    response = screen_publisher_inventory_candidates(
        PublisherInventoryCandidateScreeningRequest(
            schema_version="1.0",
            publisher_name="Example Publisher",
            insights_url="https://example.com/insights",
            candidates=[
                PublisherInventoryCandidateScreeningItem(
                    schema_version="1.0",
                    canonical_url="https://example.com/report-one",
                    title="Report One",
                    discovered_on_page_number=1,
                    source_page_url="https://example.com/insights",
                )
            ],
            settings=settings,
        ),
        _ctx(),
        openai_client=None,
        prompt_client=RecordingPromptClient(),
    )

    assert [item.canonical_url for item in response.approved_items] == [
        "https://example.com/report-one"
    ]
    assert response.model == "screening_disabled"

def test_screen_publisher_inventory_candidates_collapses_duplicate_titles_after_llm() -> (
    None
):
    candidates = [
        PublisherInventoryCandidateScreeningItem(
            schema_version="1.0",
            canonical_url="https://example.com/report-one?promo=hero",
            title="2026 Global Retail Analysis",
            discovered_on_page_number=1,
            source_page_url="https://example.com/insights",
        ),
        PublisherInventoryCandidateScreeningItem(
            schema_version="1.0",
            canonical_url="https://example.com/report-one",
            title="2026 Global Retail Analysis",
            discovered_on_page_number=2,
            source_page_url="https://example.com/insights?page=2",
        ),
        PublisherInventoryCandidateScreeningItem(
            schema_version="1.0",
            canonical_url="https://example.com/report-two",
            title="Substantive Market Analysis 2026",
            discovered_on_page_number=3,
            source_page_url="https://example.com/insights?page=3",
        ),
    ]
    openai_client = RecordingOpenAIClient(
        payload={
            "decisions": [
                {
                    "canonical_url": "https://example.com/report-one?promo=hero",
                    "accepted": True,
                    "reason": "Looks report-like.",
                },
                {
                    "canonical_url": "https://example.com/report-one",
                    "accepted": True,
                    "reason": "Looks report-like.",
                },
                {
                    "canonical_url": "https://example.com/report-two",
                    "accepted": True,
                    "reason": "Looks report-like.",
                },
            ]
        }
    )

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

    assert [item.canonical_url for item in response.approved_items] == [
        "https://example.com/report-one",
        "https://example.com/report-two",
    ]
    assert [item.canonical_url for item in response.rejected_items] == [
        "https://example.com/report-one?promo=hero"
    ]
    duplicate_decision = next(
        decision
        for decision in response.decisions
        if decision.canonical_url == "https://example.com/report-one?promo=hero"
    )
    assert duplicate_decision.accepted is False
    assert duplicate_decision.reason.startswith("duplicate_in_run")

def test_screen_publisher_inventory_candidates_keeps_distinct_generic_cta_titles() -> (
    None
):
    candidates = [
        PublisherInventoryCandidateScreeningItem(
            schema_version="1.0",
            canonical_url="https://example.com/reports/consumer-benchmark-2026",
            title="Download the report",
            discovered_on_page_number=1,
            source_page_url="https://example.com/reports",
        ),
        PublisherInventoryCandidateScreeningItem(
            schema_version="1.0",
            canonical_url="https://example.com/reports/retail-benchmark-2026",
            title="Download the report",
            discovered_on_page_number=2,
            source_page_url="https://example.com/reports?page=2",
        ),
    ]
    openai_client = RecordingOpenAIClient(
        payload={
            "decisions": [
                {
                    "canonical_url": "https://example.com/reports/consumer-benchmark-2026",
                    "accepted": True,
                    "reason": "Looks report-like.",
                },
                {
                    "canonical_url": "https://example.com/reports/retail-benchmark-2026",
                    "accepted": True,
                    "reason": "Looks report-like.",
                },
            ]
        }
    )

    response = screen_publisher_inventory_candidates(
        PublisherInventoryCandidateScreeningRequest(
            schema_version="1.0",
            publisher_name="Example Publisher",
            insights_url="https://example.com/reports",
            candidates=candidates,
            settings=_settings(),
        ),
        _ctx(),
        openai_client=openai_client,
        prompt_client=RecordingPromptClient(),
    )

    assert [item.canonical_url for item in response.approved_items] == [
        "https://example.com/reports/consumer-benchmark-2026",
        "https://example.com/reports/retail-benchmark-2026",
    ]
    assert response.rejected_items == []

def test_screen_publisher_inventory_candidates_hard_rejects_publisher_success_titles() -> (
    None
):
    candidates = [
        PublisherInventoryCandidateScreeningItem(
            schema_version="1.0",
            canonical_url="https://business.adobe.com/resources/reports/leader-email-service-providers",
            title="Read now Adobe named a Leader in Email Service Providers.",
            discovered_on_page_number=1,
            source_page_url="https://business.adobe.com/resources/reports.html",
        ),
        PublisherInventoryCandidateScreeningItem(
            schema_version="1.0",
            canonical_url="https://business.adobe.com/resources/reports/2025-ai-digital-trends-customer-engagement",
            title="Read now 2025 AI and Digital Trends in Customer Engagement.",
            discovered_on_page_number=2,
            source_page_url="https://business.adobe.com/resources/reports.html?page=2",
        ),
    ]
    openai_client = RecordingOpenAIClient(
        payload={
            "decisions": [
                {
                    "canonical_url": "https://business.adobe.com/resources/reports/leader-email-service-providers",
                    "accepted": True,
                    "reason": "Looks report-like.",
                },
                {
                    "canonical_url": "https://business.adobe.com/resources/reports/2025-ai-digital-trends-customer-engagement",
                    "accepted": True,
                    "reason": "Looks report-like.",
                },
            ]
        }
    )

    response = screen_publisher_inventory_candidates(
        PublisherInventoryCandidateScreeningRequest(
            schema_version="1.0",
            publisher_name="Adobe",
            insights_url="https://business.adobe.com/resources/reports.html",
            candidates=candidates,
            settings=_settings(),
        ),
        _ctx(),
        openai_client=openai_client,
        prompt_client=RecordingPromptClient(),
    )

    assert [item.canonical_url for item in response.approved_items] == [
        "https://business.adobe.com/resources/reports/2025-ai-digital-trends-customer-engagement"
    ]
    assert [item.canonical_url for item in response.rejected_items] == [
        "https://business.adobe.com/resources/reports/leader-email-service-providers"
    ]
    hard_reject_decision = next(
        decision
        for decision in response.decisions
        if decision.canonical_url
        == "https://business.adobe.com/resources/reports/leader-email-service-providers"
    )
    assert hard_reject_decision.accepted is False
    assert hard_reject_decision.reason in {
        "publisher_success_marketing",
        "low_report_probability_prefilter",
    }

def test_screen_publisher_inventory_candidates_hard_rejects_medal_accolade_titles() -> (
    None
):
    candidates = [
        PublisherInventoryCandidateScreeningItem(
            schema_version="1.0",
            canonical_url="https://www.bigcommerce.com/resources/reports/2025-b2b-paradigm-mm-cdl-report",
            title="BigCommerce Earns 12 Medals in Paradigm B2B Combine (Mid-Market Edition)",
            discovered_on_page_number=1,
            source_page_url="https://www.bigcommerce.com/resources/reports",
        ),
        PublisherInventoryCandidateScreeningItem(
            schema_version="1.0",
            canonical_url="https://www.bigcommerce.com/resources/reports/2025-gartner-report-cdl-report",
            title="2025 Gartner Magic Quadrant for Digital Commerce Report",
            discovered_on_page_number=1,
            source_page_url="https://www.bigcommerce.com/resources/reports",
        ),
    ]
    openai_client = RecordingOpenAIClient(
        payload={
            "decisions": [
                {
                    "canonical_url": "https://www.bigcommerce.com/resources/reports/2025-b2b-paradigm-mm-cdl-report",
                    "accepted": True,
                    "reason": "Looks report-like.",
                },
                {
                    "canonical_url": "https://www.bigcommerce.com/resources/reports/2025-gartner-report-cdl-report",
                    "accepted": True,
                    "reason": "Looks report-like.",
                },
            ]
        }
    )

    response = screen_publisher_inventory_candidates(
        PublisherInventoryCandidateScreeningRequest(
            schema_version="1.0",
            publisher_name="BigCommerce",
            insights_url="https://www.bigcommerce.com/resources/reports",
            candidates=candidates,
            settings=_settings(),
        ),
        _ctx(),
        openai_client=openai_client,
        prompt_client=RecordingPromptClient(),
    )

    assert [item.canonical_url for item in response.approved_items] == [
        "https://www.bigcommerce.com/resources/reports/2025-gartner-report-cdl-report"
    ]
    assert [item.canonical_url for item in response.rejected_items] == [
        "https://www.bigcommerce.com/resources/reports/2025-b2b-paradigm-mm-cdl-report"
    ]

def test_screen_publisher_inventory_candidates_batches_large_candidate_sets() -> None:
    settings = replace(_settings(), candidate_screening_batch_size=2)
    candidates = [
        PublisherInventoryCandidateScreeningItem(
            schema_version="1.0",
            canonical_url=f"https://example.com/report-{index}",
            title=f"Report {index}",
            discovered_on_page_number=index,
            source_page_url="https://example.com/insights",
        )
        for index in range(1, 6)
    ]
    openai_client = BatchAwareOpenAIClient()

    response = screen_publisher_inventory_candidates(
        PublisherInventoryCandidateScreeningRequest(
            schema_version="1.0",
            publisher_name="Example Publisher",
            insights_url="https://example.com/insights",
            candidates=candidates,
            settings=settings,
        ),
        _ctx(),
        openai_client=openai_client,
        prompt_client=RecordingPromptClient(),
    )

    assert len(openai_client.requests) == 3
    assert [item.canonical_url for item in response.approved_items] == [
        candidate.canonical_url for candidate in candidates
    ]
    assert response.rejected_items == []
    assert response.request_id == "req-1,req-2,req-3"

def test_resolve_candidate_screening_batch_size_grows_for_large_archives() -> None:
    assert (
        _resolve_candidate_screening_batch_size(
            candidate_count=430,
            configured_batch_size=10,
        )
        == 35
    )

def test_screen_publisher_inventory_candidates_prefilters_low_probability_items() -> (
    None
):
    response = screen_publisher_inventory_candidates(
        PublisherInventoryCandidateScreeningRequest(
            schema_version="1.0",
            publisher_name="Example Publisher",
            insights_url="https://example.com/insights",
            candidates=[
                PublisherInventoryCandidateScreeningItem(
                    schema_version="1.0",
                    canonical_url="https://example.com/insights/customer-story",
                    title="Customer story",
                    discovered_on_page_number=1,
                    source_page_url="https://example.com/insights",
                ),
                PublisherInventoryCandidateScreeningItem(
                    schema_version="1.0",
                    canonical_url="https://example.com/reports/annual-benchmark",
                    title="Annual benchmark report",
                    discovered_on_page_number=1,
                    source_page_url="https://example.com/insights",
                ),
            ],
            settings=_settings(),
        ),
        _ctx(),
        openai_client=BatchAwareOpenAIClient(),
        prompt_client=RecordingPromptClient(),
    )

    assert [item.canonical_url for item in response.approved_items] == [
        "https://example.com/reports/annual-benchmark"
    ]
    assert [item.canonical_url for item in response.rejected_items] == [
        "https://example.com/insights/customer-story"
    ]
    prefilter_decision = next(
        decision
        for decision in response.decisions
        if decision.canonical_url == "https://example.com/insights/customer-story"
    )
    assert prefilter_decision.accepted is False
    assert prefilter_decision.reason == "low_report_probability_prefilter"

def test_screen_publisher_inventory_candidates_prefilters_support_and_webinar_items() -> (
    None
):
    response = screen_publisher_inventory_candidates(
        PublisherInventoryCandidateScreeningRequest(
            schema_version="1.0",
            publisher_name="Example Publisher",
            insights_url="https://example.com/insights",
            candidates=[
                PublisherInventoryCandidateScreeningItem(
                    schema_version="1.0",
                    canonical_url="https://support.example.com/hc/en-us/articles/123-report-generation",
                    title="How can I automate analytics report generation and downloading?",
                    discovered_on_page_number=1,
                    source_page_url="https://example.com/insights",
                ),
                PublisherInventoryCandidateScreeningItem(
                    schema_version="1.0",
                    canonical_url="https://example.com/resources/asset/webinar-ai-search",
                    title="AI Search Best Practices webinar",
                    discovered_on_page_number=1,
                    source_page_url="https://example.com/insights",
                ),
                PublisherInventoryCandidateScreeningItem(
                    schema_version="1.0",
                    canonical_url="https://example.com/resources/asset/white-paper-search-benchmark",
                    title="2026 Search Benchmark white paper",
                    discovered_on_page_number=1,
                    source_page_url="https://example.com/insights",
                ),
            ],
            settings=_settings(),
        ),
        _ctx(),
        openai_client=BatchAwareOpenAIClient(),
        prompt_client=RecordingPromptClient(),
    )

    assert [item.canonical_url for item in response.approved_items] == [
        "https://example.com/resources/asset/white-paper-search-benchmark"
    ]
    assert {item.canonical_url for item in response.rejected_items} == {
        "https://support.example.com/hc/en-us/articles/123-report-generation",
        "https://example.com/resources/asset/webinar-ai-search",
    }

def test_screen_publisher_inventory_candidates_prefilters_strong_report_detail_urls_without_llm() -> (
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
                    canonical_url="https://example.com/resources/reports/2026-b2b-commerce-study",
                    title="Download",
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
        "https://example.com/resources/reports/2026-b2b-commerce-study"
    ]
    assert response.decisions[0].reason == "strong_report_detail_url_prefilter"

def test_screen_publisher_inventory_candidates_prefilters_slugged_report_detail_urls_without_llm() -> (
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
                    canonical_url="https://go.example.com/commerce-media-trends-report",
                    title="Learn more",
                    discovered_on_page_number=1,
                    source_page_url="https://example.com/resources",
                ),
                PublisherInventoryCandidateScreeningItem(
                    schema_version="1.0",
                    canonical_url="https://example.com/report_pages/sea-ecommerce-atlas",
                    title="Download the report",
                    discovered_on_page_number=2,
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
        "https://go.example.com/commerce-media-trends-report",
        "https://example.com/report_pages/sea-ecommerce-atlas",
    ]
    assert {decision.reason for decision in response.decisions} == {
        "strong_report_detail_url_prefilter"
    }

def test_screen_publisher_inventory_candidates_rejects_report_collection_pages_with_listing_signals() -> (
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
                    canonical_url="https://example.com/resources?resource_type=whitepaper",
                    title="White Papers",
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
    assert response.approved_items == []
    assert [item.canonical_url for item in response.rejected_items] == [
        "https://example.com/resources?resource_type=whitepaper"
    ]
    assert response.decisions[0].reason == "low_report_probability_prefilter"

def test_screen_publisher_inventory_candidates_rejects_case_study_and_blog_help_urls_without_llm() -> (
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
                    canonical_url="https://example.com/case-studies",
                    title="Case Studies",
                    discovered_on_page_number=1,
                    source_page_url="https://example.com/resources",
                ),
                PublisherInventoryCandidateScreeningItem(
                    schema_version="1.0",
                    canonical_url="https://example.com/blogs/ask/what-to-look-for-in-your-credit-report",
                    title="What to look for in your credit report",
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
    assert response.approved_items == []
    assert {item.canonical_url for item in response.rejected_items} == {
        "https://example.com/case-studies",
        "https://example.com/blogs/ask/what-to-look-for-in-your-credit-report",
    }
    assert {decision.reason for decision in response.decisions} == {
        "low_report_probability_prefilter"
    }

__all__ = [
    "test_screen_publisher_inventory_candidates_filters_rejected_items",
    "test_screen_publisher_inventory_candidates_falls_back_when_decisions_remain_missing",
    "test_screen_publisher_inventory_candidates_skips_llm_when_disabled",
    "test_screen_publisher_inventory_candidates_collapses_duplicate_titles_after_llm",
    "test_screen_publisher_inventory_candidates_keeps_distinct_generic_cta_titles",
    "test_screen_publisher_inventory_candidates_hard_rejects_publisher_success_titles",
    "test_screen_publisher_inventory_candidates_hard_rejects_medal_accolade_titles",
    "test_screen_publisher_inventory_candidates_batches_large_candidate_sets",
    "test_resolve_candidate_screening_batch_size_grows_for_large_archives",
    "test_screen_publisher_inventory_candidates_prefilters_low_probability_items",
    "test_screen_publisher_inventory_candidates_prefilters_support_and_webinar_items",
    "test_screen_publisher_inventory_candidates_prefilters_strong_report_detail_urls_without_llm",
    "test_screen_publisher_inventory_candidates_prefilters_slugged_report_detail_urls_without_llm",
    "test_screen_publisher_inventory_candidates_rejects_report_collection_pages_with_listing_signals",
    "test_screen_publisher_inventory_candidates_rejects_case_study_and_blog_help_urls_without_llm",
]
