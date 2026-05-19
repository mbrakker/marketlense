from __future__ import annotations

from src.contracts.report_store import (
    PublisherResourceRankingPolicy,
    PublisherResourceRankingRequest,
    ReportSourceQualityHistoryItem,
    ReportValueScoreRequest,
)
from src.generators.report_value_generator import (
    rank_publisher_resources,
    score_report_value,
)
from src.utils.logging import new_run_context


def test_score_report_value_distinguishes_high_value_market_report() -> None:
    ctx = new_run_context(task_id="test_high_value_report_score")

    score = score_report_value(
        ReportValueScoreRequest(
            schema_version="1.0",
            publisher_name="Example Research",
            source_domain="research.example.com",
            report_name="2026 Global Retail Market Outlook Benchmark Survey",
            landing_page_url="https://research.example.com/reports/2026-retail-market-outlook",
            source_page_url="https://research.example.com/research/reports",
            source_status="downloaded",
            downloaded_at_utc="2026-05-19T08:00:00Z",
            md5="abc123",
            evaluation_year=2026,
        ),
        ctx,
    )

    assert score.value_band == "high"
    assert score.overall_score >= 78.0
    assert [component.dimension for component in score.components] == [
        "market_insight_depth",
        "evidence_specificity",
        "decision_relevance",
        "recency_timeliness",
        "source_authority_originality",
    ]


def test_score_report_value_demotes_low_value_marketing_asset() -> None:
    ctx = new_run_context(task_id="test_low_value_report_score")

    score = score_report_value(
        ReportValueScoreRequest(
            schema_version="1.0",
            publisher_name="Example Vendor",
            source_domain="example.com",
            report_name="Customer Story Webinar Demo",
            landing_page_url="https://example.com/blog/customer-story-webinar-demo",
            source_page_url="https://example.com/blog",
            source_status="downloaded",
            downloaded_at_utc="2026-05-19T08:00:00Z",
            md5="abc123",
            evaluation_year=2026,
        ),
        ctx,
    )

    assert score.value_band in {"weak", "low"}
    assert score.overall_score < 50.0
    assert "penalty" in score.rationale


def test_rank_publisher_resources_prefers_consistent_high_value_history() -> None:
    ctx = new_run_context(task_id="test_resource_ranking")
    policy = PublisherResourceRankingPolicy(
        schema_version="1.0",
        score_window_size=3,
        min_sample_size=2,
        consistency_weight=0.35,
        average_score_weight=0.50,
        confidence_weight=0.15,
        low_score_demotion_threshold=45.0,
    )

    response = rank_publisher_resources(
        PublisherResourceRankingRequest(
            schema_version="1.0",
            publisher_name="Example Research",
            candidate_source_page_urls=[
                "https://example.com/research/reports",
                "https://example.com/blog",
                "https://example.com/new-library",
            ],
            history_items=[
                _history("https://example.com/research/reports", 86.0, "high", 1),
                _history("https://example.com/research/reports", 84.0, "high", 2),
                _history("https://example.com/blog", 34.0, "weak", 3),
                _history("https://example.com/blog", 42.0, "low", 4),
            ],
            policy=policy,
        ),
        ctx,
    )

    assert response.items[0].resource_url == "https://example.com/research/reports"
    assert response.items[0].sample_size == 2
    assert response.items[0].demotion_reason == ""
    blog = next(
        item
        for item in response.items
        if item.resource_url == "https://example.com/blog"
    )
    assert blog.demotion_reason == "low_average_value"
    new_library = next(
        item
        for item in response.items
        if item.resource_url == "https://example.com/new-library"
    )
    assert new_library.demotion_reason == "insufficient_history"


def _history(
    source_page_url: str, score: float, band: str, day: int
) -> ReportSourceQualityHistoryItem:
    timestamp = f"2026-05-{day:02d}T00:00:00Z"
    return ReportSourceQualityHistoryItem(
        schema_version="1.0",
        publisher_name="Example Research",
        source_domain="example.com",
        source_page_url=source_page_url,
        landing_page_url=f"{source_page_url}/report-{day}",
        report_name=f"Report {day}",
        overall_score=score,
        value_band=band,
        source_status="downloaded",
        discovered_at_utc=timestamp,
        downloaded_at_utc=timestamp,
        scored_at_utc=timestamp,
    )
