from __future__ import annotations

import json
import logging
from dataclasses import is_dataclass

import pytest

from src.contracts.cross_report_analysis import (
    CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
    CrossReportAnalysisRequest,
    CrossReportProjectedDataReadResponse,
    CrossReportSelectedSourceReport,
    CrossReportSourceReportCandidate,
    CrossReportSourceSelectionResult,
    CrossReportValidationResult,
)
from src.contracts.files import (
    DirectoryEntry,
    ListDirectoryResponse,
    ReadTextResponse,
)
from src.generators import cross_report_analysis_input_generator as input_gen
from src.generators.cross_report_analysis_input_generator import (
    select_cross_report_theme,
    select_cross_report_source_reports,
    validate_cross_report_publishability,
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


def _selected_source(
    report_id: str,
    *,
    publisher: str,
    report_date: str,
    evidence_count: int,
    tags: list[str],
    categories: list[str],
    rank: int = 1,
) -> CrossReportSelectedSourceReport:
    return CrossReportSelectedSourceReport(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        report_id=report_id,
        title=f"{report_id} source report",
        publisher=publisher,
        publisher_id=publisher.lower().replace(" ", "-"),
        report_date=report_date,
        projection_status="projected",
        content_hash=f"{report_id}-hash",
        rank=rank,
        selection_reasons=["test_source"],
        evidence_count=evidence_count,
        category_labels=categories,
        tags=tags,
    )


def _source_selection(
    sources: list[CrossReportSelectedSourceReport],
) -> CrossReportSourceSelectionResult:
    return CrossReportSourceSelectionResult(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        selected_sources=sources,
        ranked_candidates=[],
        rejected_candidates=[],
        cleaned_filters={"tag_filters": ["ai"], "category_filters": ["retail"]},
        excluded_report_counts={},
    )


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


def test_theme_selection_uses_explicit_topic_without_auto_theme(
    run_context,
) -> None:
    result = select_cross_report_theme(
        _request(),
        _source_selection(
            [
                _selected_source(
                    "report-a",
                    publisher="Publisher A",
                    report_date="2026-05-01",
                    evidence_count=4,
                    tags=["AI", "commerce"],
                    categories=["Retail"],
                )
            ]
        ),
        run_context,
    )

    assert result.selected_theme.label == "AI commerce"
    assert result.selected_theme.theme_id == "theme-explicit-ai-commerce"
    assert result.selected_theme.source_report_ids == ["report-a"]
    assert result.theme_candidates[0].rationale.startswith("Explicit operator topic")


def test_theme_selection_auto_generates_ranked_candidates_and_logs(
    run_context,
    caplog,
    assert_logs_have_required_fields,
) -> None:
    base_request = _request()
    request = CrossReportAnalysisRequest(
        **{**base_request.__dict__, "topic": "", "auto_theme": True}
    )
    source_selection = _source_selection(
        [
            _selected_source(
                "report-a",
                publisher="Publisher A",
                report_date="2026-05-01",
                evidence_count=4,
                tags=["AI", "commerce"],
                categories=["Retail"],
                rank=1,
            ),
            _selected_source(
                "report-b",
                publisher="Publisher B",
                report_date="2026-05-05",
                evidence_count=6,
                tags=["AI", "commerce"],
                categories=["Retail"],
                rank=2,
            ),
            _selected_source(
                "report-c",
                publisher="Publisher C",
                report_date="2026-05-03",
                evidence_count=2,
                tags=["Payments"],
                categories=["Payments"],
                rank=3,
            ),
        ]
    )

    caplog.set_level(
        logging.INFO, logger="market_lense.cross_report_analysis_input_generator"
    )
    result = select_cross_report_theme(request, source_selection, run_context)
    repeat = select_cross_report_theme(request, source_selection, run_context)

    assert [candidate.theme_id for candidate in result.theme_candidates] == [
        "theme-tag-ai",
        "theme-category-retail",
        "theme-tag-commerce",
        "theme-category-payments",
        "theme-tag-payments",
    ]
    assert result.selected_theme.theme_id == "theme-tag-ai"
    assert result.selected_theme.matched_tags == ["AI"]
    assert result.selected_theme.matched_categories == ["Retail"]
    assert result.selected_theme.source_report_ids == ["report-a", "report-b"]
    assert result.theme_candidates[0].source_publisher_count == 2
    assert result.theme_candidates[0].evidence_count == 10
    assert result.theme_candidates[0].recency_score > 0
    assert [candidate.theme_id for candidate in repeat.theme_candidates] == [
        candidate.theme_id for candidate in result.theme_candidates
    ]

    events = _events(caplog)
    assert_logs_have_required_fields(events)
    complete = [
        event
        for event in events
        if event["event"] == "cross_report_theme_selection_complete"
    ][0]
    assert complete["fields"]["theme_candidate_count"] == 5
    assert complete["fields"]["selected_theme_id"] == "theme-tag-ai"
    assert "score_components" in complete["fields"]


def test_theme_selection_fails_when_no_eligible_theme(
    run_context,
    assert_app_error,
) -> None:
    base_request = _request()
    request = CrossReportAnalysisRequest(
        **{**base_request.__dict__, "topic": "", "auto_theme": True}
    )

    with pytest.raises(Exception) as exc_info:
        select_cross_report_theme(request, _source_selection([]), run_context)

    assert_app_error(
        exc_info.value,
        code="cross_report_no_theme_candidates",
        retryable=False,
        severity="error",
    )


def test_theme_variety_downranks_recent_repetition_through_file_service(
    run_context,
    tmp_path,
    external_boundary_mocks_only,
) -> None:
    base_request = _request()
    request = CrossReportAnalysisRequest(
        **{**base_request.__dict__, "topic": "", "auto_theme": True}
    )
    source_selection = _source_selection(
        [
            _selected_source(
                "report-a",
                publisher="Publisher A",
                report_date="2026-05-01",
                evidence_count=8,
                tags=["AI"],
                categories=["Retail"],
                rank=1,
            ),
            _selected_source(
                "report-b",
                publisher="Publisher B",
                report_date="2026-05-02",
                evidence_count=8,
                tags=["AI"],
                categories=["Retail"],
                rank=2,
            ),
            _selected_source(
                "report-c",
                publisher="Publisher C",
                report_date="2026-05-03",
                evidence_count=5,
                tags=["Payments"],
                categories=["Payments"],
                rank=3,
            ),
            _selected_source(
                "report-d",
                publisher="Publisher D",
                report_date="2026-05-04",
                evidence_count=5,
                tags=["Payments"],
                categories=["Payments"],
                rank=4,
            ),
        ]
    )
    calls: list[str] = []

    def _list_directory(request_arg, ctx):
        calls.append(f"list:{request_arg.root_dir}")
        return ListDirectoryResponse(
            schema_version="1.0",
            root_dir=request_arg.root_dir,
            entries=[
                DirectoryEntry(
                    schema_version="1.0",
                    path=str(tmp_path / "old" / "analysis.json"),
                    name="analysis.json",
                    is_dir=False,
                    size_bytes=200,
                    mtime_utc=1.0,
                )
            ],
        )

    def _read_text(request_arg, ctx):
        calls.append(f"read:{request_arg.path}")
        return ReadTextResponse(
            schema_version="1.0",
            path=request_arg.path,
            content=json.dumps(
                {
                    "generated_at_utc": "2026-05-20T00:00:00Z",
                    "selected_theme": {
                        "theme_id": "theme-tag-ai",
                        "matched_tags": ["AI"],
                        "matched_categories": ["Retail"],
                        "source_report_ids": ["old-report"],
                    },
                }
            ),
        )

    external_boundary_mocks_only.setattr(
        input_gen.file_service, "list_directory", _list_directory
    )
    external_boundary_mocks_only.setattr(
        input_gen.file_service, "read_text", _read_text
    )

    result = select_cross_report_theme(
        request,
        source_selection,
        run_context,
        recent_artifacts_root=str(tmp_path),
        theme_rotation_window_days=30,
        theme_rotation_reference_date="2026-05-21",
        theme_score_weights={
            "density": 1.0,
            "diversity": 1.0,
            "recency": 1.0,
            "novelty": 2.0,
        },
    )

    assert calls == [f"list:{tmp_path}", f"read:{tmp_path / 'old' / 'analysis.json'}"]
    assert result.selected_theme.theme_id == "theme-category-payments"
    repeated = {candidate.theme_id: candidate for candidate in result.theme_candidates}[
        "theme-tag-ai"
    ]
    assert repeated.novelty_score == 0.0
    assert "recent_theme_repetition" in repeated.rejection_risks
    assert "recent_category_repetition:retail" in repeated.rejection_risks


def test_theme_variety_prefers_source_diversity_and_stable_tie_breaking(
    run_context,
) -> None:
    base_request = _request()
    request = CrossReportAnalysisRequest(
        **{**base_request.__dict__, "topic": "", "auto_theme": True}
    )
    source_selection = _source_selection(
        [
            _selected_source(
                "report-a",
                publisher="Publisher A",
                report_date="2026-05-01",
                evidence_count=6,
                tags=["AI"],
                categories=["Retail"],
            ),
            _selected_source(
                "report-b",
                publisher="Publisher B",
                report_date="2026-05-01",
                evidence_count=3,
                tags=["Commerce"],
                categories=["Retail"],
            ),
            _selected_source(
                "report-c",
                publisher="Publisher C",
                report_date="2026-05-01",
                evidence_count=3,
                tags=["Commerce"],
                categories=["Retail"],
            ),
        ]
    )

    result = select_cross_report_theme(
        request,
        source_selection,
        run_context,
        theme_score_weights={
            "density": 1.0,
            "diversity": 2.0,
            "recency": 0.0,
            "novelty": 1.0,
        },
    )
    repeat = select_cross_report_theme(
        request,
        source_selection,
        run_context,
        theme_score_weights={
            "density": 1.0,
            "diversity": 2.0,
            "recency": 0.0,
            "novelty": 1.0,
        },
    )

    assert result.selected_theme.theme_id == "theme-category-retail"
    assert [candidate.theme_id for candidate in result.theme_candidates] == [
        candidate.theme_id for candidate in repeat.theme_candidates
    ]


def test_publishability_gate_passes_supported_theme_and_logs(
    run_context,
    caplog,
    assert_logs_have_required_fields,
) -> None:
    request = _request(max_source_reports=2)
    source_selection = _source_selection(
        [
            _selected_source(
                "report-a",
                publisher="Publisher A",
                report_date="2026-05-01",
                evidence_count=4,
                tags=["AI"],
                categories=["Retail"],
                rank=1,
            ),
            _selected_source(
                "report-b",
                publisher="Publisher B",
                report_date="2026-05-02",
                evidence_count=4,
                tags=["AI"],
                categories=["Retail"],
                rank=2,
            ),
        ]
    )
    theme_selection = select_cross_report_theme(request, source_selection, run_context)

    caplog.set_level(
        logging.INFO, logger="market_lense.cross_report_analysis_input_generator"
    )
    result = validate_cross_report_publishability(
        request,
        theme_selection,
        source_selection,
        run_context,
        min_source_reports=2,
        min_source_publishers=2,
        min_evidence_items=6,
    )

    assert result.publishable is True
    assert result.issues == []
    assert result.source_report_count == 2
    assert result.source_publisher_count == 2
    assert result.evidence_count == 8
    events = _events(caplog)
    assert_logs_have_required_fields(events)
    assert {
        event["event"]
        for event in events
        if event["event"].startswith("cross_report_publishability")
    } >= {
        "cross_report_publishability_check_start",
        "cross_report_publishability_check_complete",
    }


@pytest.mark.parametrize(
    ("sources", "expected_issue"),
    [
        (
            [
                _selected_source(
                    "report-a",
                    publisher="Publisher A",
                    report_date="2026-05-01",
                    evidence_count=8,
                    tags=["AI"],
                    categories=["Retail"],
                )
            ],
            "source_report_count_below_minimum",
        ),
        (
            [
                _selected_source(
                    "report-a",
                    publisher="Publisher A",
                    report_date="2026-05-01",
                    evidence_count=4,
                    tags=["AI"],
                    categories=["Retail"],
                    rank=1,
                ),
                _selected_source(
                    "report-b",
                    publisher="Publisher A",
                    report_date="2026-05-02",
                    evidence_count=4,
                    tags=["AI"],
                    categories=["Retail"],
                    rank=2,
                ),
            ],
            "source_publisher_count_below_minimum",
        ),
        (
            [
                _selected_source(
                    "report-a",
                    publisher="Publisher A",
                    report_date="2026-05-01",
                    evidence_count=2,
                    tags=["AI"],
                    categories=["Retail"],
                    rank=1,
                ),
                _selected_source(
                    "report-b",
                    publisher="Publisher B",
                    report_date="2026-05-02",
                    evidence_count=2,
                    tags=["AI"],
                    categories=["Retail"],
                    rank=2,
                ),
            ],
            "evidence_count_below_minimum",
        ),
    ],
)
def test_publishability_gate_rejects_thin_coverage(
    run_context,
    assert_app_error,
    sources,
    expected_issue,
) -> None:
    request = _request(max_source_reports=2)
    source_selection = _source_selection(sources)
    theme_selection = select_cross_report_theme(
        request,
        source_selection,
        run_context,
    )

    with pytest.raises(Exception) as exc_info:
        validate_cross_report_publishability(
            request,
            theme_selection,
            source_selection,
            run_context,
            min_source_reports=2,
            min_source_publishers=2,
            min_evidence_items=6,
        )

    assert_app_error(
        exc_info.value,
        code="cross_report_publishability_failed",
        retryable=False,
        severity="error",
    )
    assert expected_issue in exc_info.value.context["issues"]


def test_publishability_gate_rejects_duplicate_and_metric_dependency(
    run_context,
    assert_app_error,
) -> None:
    request = _request(max_source_reports=2)
    source_selection = _source_selection(
        [
            _selected_source(
                "report-a",
                publisher="Publisher A",
                report_date="2026-05-01",
                evidence_count=4,
                tags=["AI"],
                categories=["Retail"],
                rank=1,
            ),
            _selected_source(
                "report-b",
                publisher="Publisher B",
                report_date="2026-05-02",
                evidence_count=4,
                tags=["AI"],
                categories=["Retail"],
                rank=2,
            ),
        ]
    )
    theme_selection = select_cross_report_theme(request, source_selection, run_context)
    selected_theme = theme_selection.selected_theme
    risky_theme = type(selected_theme)(
        **{
            **selected_theme.__dict__,
            "rejection_risks": [
                "recent_theme_repetition",
                "metric_normalization_dependency",
            ],
        }
    )
    risky_selection = type(theme_selection)(
        **{**theme_selection.__dict__, "selected_theme": risky_theme}
    )

    with pytest.raises(Exception) as exc_info:
        validate_cross_report_publishability(
            request,
            risky_selection,
            source_selection,
            run_context,
            min_source_reports=2,
            min_source_publishers=2,
            min_evidence_items=6,
        )

    assert_app_error(
        exc_info.value,
        code="cross_report_publishability_failed",
        retryable=False,
        severity="error",
    )
    assert "duplicate_theme_risk" in exc_info.value.context["issues"]
    assert "metric_normalization_dependency" in exc_info.value.context["issues"]


def test_publishability_gate_allows_explicit_override_and_logs(
    run_context,
    caplog,
) -> None:
    base_request = _request(max_source_reports=1)
    request = CrossReportAnalysisRequest(
        **{**base_request.__dict__, "override_publishability": True}
    )
    source_selection = _source_selection(
        [
            _selected_source(
                "report-a",
                publisher="Publisher A",
                report_date="2026-05-01",
                evidence_count=2,
                tags=["AI"],
                categories=["Retail"],
            )
        ]
    )
    theme_selection = select_cross_report_theme(request, source_selection, run_context)

    caplog.set_level(
        logging.INFO, logger="market_lense.cross_report_analysis_input_generator"
    )
    result = validate_cross_report_publishability(
        request,
        theme_selection,
        source_selection,
        run_context,
        min_source_reports=2,
        min_source_publishers=2,
        min_evidence_items=6,
    )

    assert result.publishable is True
    assert result.override_applied is True
    assert result.issues
    complete = [
        event
        for event in _events(caplog)
        if event["event"] == "cross_report_publishability_check_complete"
    ][0]
    assert complete["fields"]["override_applied"] is True


def test_publishability_gate_checks_publication_validation_prerequisite(
    run_context,
    assert_app_error,
) -> None:
    base_request = _request(max_source_reports=2)
    request = CrossReportAnalysisRequest(
        **{**base_request.__dict__, "publication_mode": "publish_live"}
    )
    source_selection = _source_selection(
        [
            _selected_source(
                "report-a",
                publisher="Publisher A",
                report_date="2026-05-01",
                evidence_count=4,
                tags=["AI"],
                categories=["Retail"],
                rank=1,
            ),
            _selected_source(
                "report-b",
                publisher="Publisher B",
                report_date="2026-05-02",
                evidence_count=4,
                tags=["AI"],
                categories=["Retail"],
                rank=2,
            ),
        ]
    )
    theme_selection = select_cross_report_theme(request, source_selection, run_context)
    validation_result = CrossReportValidationResult(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        status="fail",
        checked_evidence_ids=["evidence-a"],
        issues=["citation_missing"],
        passed=False,
    )

    with pytest.raises(Exception) as exc_info:
        validate_cross_report_publishability(
            request,
            theme_selection,
            source_selection,
            run_context,
            min_source_reports=2,
            min_source_publishers=2,
            min_evidence_items=6,
            validation_result=validation_result,
        )

    assert_app_error(
        exc_info.value,
        code="cross_report_publishability_failed",
        retryable=False,
        severity="error",
    )
    assert "validation_not_passed" in exc_info.value.context["issues"]
