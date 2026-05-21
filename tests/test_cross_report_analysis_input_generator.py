from __future__ import annotations

import json
import logging
from dataclasses import is_dataclass

import pytest

from src.contracts.cross_report_analysis import (
    CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
    CrossReportAnalysisRequest,
    CrossReportProjectedDataReadResponse,
    CrossReportSourceReportCandidate,
)
from src.generators.cross_report_analysis_input_generator import (
    select_cross_report_source_reports,
)


def _request(
    *, max_source_reports: int = 2, diagnostic: bool = False
) -> CrossReportAnalysisRequest:
    return CrossReportAnalysisRequest(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        request_id="selection-request",
        topic="AI commerce",
        auto_theme=False,
        category_filters=[" Retail "],
        tag_filters=["AI"],
        publisher_filters=[],
        date_range_start="2026-05-01",
        date_range_end="2026-05-31",
        max_source_reports=max_source_reports,
        diagnostic=diagnostic,
        override_publishability=False,
        publication_mode="generate_only",
    )


def _candidate(
    report_id: str,
    *,
    publisher: str,
    report_date: str,
    evidence_count: int,
    tags: list[str] | None = None,
    categories: list[str] | None = None,
    projection_status: str = "projected",
) -> CrossReportSourceReportCandidate:
    return CrossReportSourceReportCandidate(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        report_id=report_id,
        title=f"{report_id} AI Commerce Outlook",
        publisher=publisher,
        publisher_id=publisher.lower().replace(" ", "-"),
        report_date=report_date,
        projection_status=projection_status,
        content_hash=f"{report_id}-hash",
        category_labels=categories or ["Retail"],
        tags=tags or ["AI"],
        evidence_count=evidence_count,
        claim_count=max(evidence_count - 2, 0),
        finding_count=1,
        quote_count=1,
        metric_count=1,
        recency_score=0.0,
        relevance_score=0.0,
        diversity_score=0.0,
        density_score=0.0,
        total_score=0.0,
        selection_reasons=["projection_status:projected"],
        rejection_reasons=[],
    )


def _projected_data(
    candidates: list[CrossReportSourceReportCandidate],
) -> CrossReportProjectedDataReadResponse:
    return CrossReportProjectedDataReadResponse(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        source_candidates=candidates,
        evidence=[],
        raw_metrics=[],
        content_hashes={
            candidate.report_id: {candidate.report_id: candidate.content_hash}
            for candidate in candidates
        },
        excluded_report_counts={},
    )


def _events(caplog) -> list[dict]:
    return [
        json.loads(record.message)
        for record in caplog.records
        if record.name == "market_lense.cross_report_analysis_input_generator"
    ]


def test_source_selection_is_ranked_deterministic_and_diverse(
    run_context,
    caplog,
    assert_logs_have_required_fields,
) -> None:
    projected_data = _projected_data(
        [
            _candidate(
                "report-a",
                publisher="Publisher A",
                report_date="2026-05-03",
                evidence_count=6,
            ),
            _candidate(
                "report-b",
                publisher="Publisher B",
                report_date="2026-05-02",
                evidence_count=4,
            ),
            _candidate(
                "report-c",
                publisher="Publisher A",
                report_date="2026-05-04",
                evidence_count=9,
            ),
            _candidate(
                "report-d",
                publisher="Publisher D",
                report_date="2026-04-30",
                evidence_count=8,
                tags=["Payments"],
                categories=["Payments"],
            ),
        ]
    )

    caplog.set_level(
        logging.INFO, logger="market_lense.cross_report_analysis_input_generator"
    )
    result = select_cross_report_source_reports(_request(), projected_data, run_context)
    repeat = select_cross_report_source_reports(_request(), projected_data, run_context)

    assert is_dataclass(result)
    assert [source.report_id for source in result.selected_sources] == [
        "report-c",
        "report-b",
    ]
    assert [source.report_id for source in repeat.selected_sources] == [
        "report-c",
        "report-b",
    ]
    assert [source.rank for source in result.selected_sources] == [1, 2]
    assert result.cleaned_filters == {
        "category_filters": ["retail"],
        "tag_filters": ["ai"],
        "publisher_filters": [],
        "date_range_start": "2026-05-01",
        "date_range_end": "2026-05-31",
        "topic_terms": ["ai", "commerce"],
    }
    rejected = {
        candidate.report_id: candidate.rejection_reasons
        for candidate in result.rejected_candidates
    }
    assert rejected["report-a"] == ["max_source_reports_reached"]
    assert rejected["report-d"] == [
        "date_before_start",
        "category_filter_mismatch",
        "tag_filter_mismatch",
    ]
    assert result.excluded_report_counts == {
        "date_before_start": 1,
        "category_filter_mismatch": 1,
        "tag_filter_mismatch": 1,
        "max_source_reports_reached": 1,
    }
    assert (
        result.ranked_candidates[0].total_score
        > result.ranked_candidates[1].total_score
    )
    assert "publisher_diversity" in result.selected_sources[1].selection_reasons

    events = _events(caplog)
    assert_logs_have_required_fields(events)
    assert {event["event"] for event in events} >= {
        "cross_report_source_selection_start",
        "cross_report_source_selection_ranked",
        "cross_report_source_selection_complete",
    }
    complete = [
        event
        for event in events
        if event["event"] == "cross_report_source_selection_complete"
    ][0]
    assert complete["fields"]["selected_report_ids"] == ["report-c", "report-b"]


def test_source_selection_honors_max_report_cap_and_filters(run_context) -> None:
    projected_data = _projected_data(
        [
            _candidate(
                "report-a",
                publisher="Publisher A",
                report_date="2026-05-01",
                evidence_count=3,
            ),
            _candidate(
                "report-b",
                publisher="Publisher B",
                report_date="2026-05-01",
                evidence_count=3,
                tags=["Payments"],
            ),
        ]
    )

    result = select_cross_report_source_reports(
        _request(max_source_reports=1), projected_data, run_context
    )

    assert [source.report_id for source in result.selected_sources] == ["report-a"]
    rejected = {
        candidate.report_id: candidate.rejection_reasons
        for candidate in result.rejected_candidates
    }
    assert rejected["report-b"] == ["tag_filter_mismatch"]


def test_source_selection_excludes_non_projected_sources_before_synthesis(
    run_context,
) -> None:
    projected_data = _projected_data(
        [
            _candidate(
                "report-a",
                publisher="Publisher A",
                report_date="2026-05-01",
                evidence_count=3,
                projection_status="projected",
            ),
            _candidate(
                "report-b",
                publisher="Publisher B",
                report_date="2026-05-01",
                evidence_count=6,
                projection_status="failed",
            ),
            _candidate(
                "report-c",
                publisher="Publisher C",
                report_date="2026-05-01",
                evidence_count=6,
                projection_status="not_projected",
            ),
        ]
    )

    result = select_cross_report_source_reports(_request(), projected_data, run_context)

    assert [source.report_id for source in result.selected_sources] == ["report-a"]
    rejected = {
        candidate.report_id: candidate.rejection_reasons
        for candidate in result.rejected_candidates
    }
    assert rejected["report-b"] == ["projection_status_failed"]
    assert rejected["report-c"] == ["projection_status_not_projected"]
    assert result.excluded_report_counts == {
        "projection_status_failed": 1,
        "projection_status_not_projected": 1,
    }


def test_source_selection_diagnostic_mode_can_inspect_failed_projection(
    run_context,
) -> None:
    projected_data = _projected_data(
        [
            _candidate(
                "report-b",
                publisher="Publisher B",
                report_date="2026-05-01",
                evidence_count=6,
                projection_status="failed",
            )
        ]
    )

    result = select_cross_report_source_reports(
        _request(max_source_reports=1, diagnostic=True), projected_data, run_context
    )

    assert [source.report_id for source in result.selected_sources] == ["report-b"]
    assert result.rejected_candidates == []


def test_source_selection_empty_projected_set_fails_with_typed_error(
    run_context,
    caplog,
    assert_app_error,
    assert_logs_have_required_fields,
) -> None:
    projected_data = _projected_data(
        [
            _candidate(
                "report-b",
                publisher="Publisher B",
                report_date="2026-05-01",
                evidence_count=6,
                projection_status="failed",
            )
        ]
    )

    caplog.set_level(
        logging.INFO, logger="market_lense.cross_report_analysis_input_generator"
    )
    with pytest.raises(Exception) as exc_info:
        select_cross_report_source_reports(_request(), projected_data, run_context)

    assert_app_error(
        exc_info.value,
        code="cross_report_no_projected_sources",
        retryable=False,
        severity="error",
    )
    events = _events(caplog)
    assert_logs_have_required_fields(events)
    failed = [
        event
        for event in events
        if event["event"] == "cross_report_source_selection_failed"
    ][0]
    assert failed["fields"]["excluded_report_counts"] == {"projection_status_failed": 1}
