# ruff: noqa: F401,F403,F405
from __future__ import annotations

from pathlib import Path

from ._shared import *  # noqa: F401,F403


def test_source_selection_avoids_resorting_every_diversity_iteration() -> None:
    source = Path(
        "src/generators/_cross_report_analysis_input/source_selection.py"
    ).read_text(encoding="utf-8")
    function_source = source.split("def _select_diverse_sources", 1)[1].split(
        "\ndef ", 1
    )[0]

    assert ".sort(" not in function_source
    assert "min(rescored, key=sort_key)" in function_source


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


def test_source_selection_honors_category_id_filters_when_label_differs(
    run_context,
) -> None:
    request = CrossReportAnalysisRequest(
        **{
            **_request().__dict__,
            "category_filters": ["retail-media"],
            "tag_filters": [],
        }
    )
    candidate = replace(
        _candidate(
            "report-category-id",
            publisher="Publisher A",
            report_date="2026-05-02",
            evidence_count=3,
            categories=["Retail Media"],
        ),
        category_ids=["retail-media"],
    )

    result = select_cross_report_source_reports(
        request,
        _projected_data([candidate]),
        run_context,
    )

    assert [source.report_id for source in result.selected_sources] == [
        "report-category-id"
    ]
    assert result.selected_sources[0].category_ids == ["retail-media"]


def test_source_selection_normalizes_whitespace_dates(run_context) -> None:
    request = CrossReportAnalysisRequest(
        **{
            **_request().__dict__,
            "date_range_start": " 2026-05-01 ",
            "date_range_end": " 2026-05-31 ",
        }
    )
    result = select_cross_report_source_reports(
        request,
        _projected_data(
            [
                _candidate(
                    "report-a",
                    publisher="Publisher A",
                    report_date="2026-05-02",
                    evidence_count=3,
                )
            ]
        ),
        run_context,
    )

    assert result.cleaned_filters["date_range_start"] == "2026-05-01"
    assert result.cleaned_filters["date_range_end"] == "2026-05-31"
    assert [source.report_id for source in result.selected_sources] == ["report-a"]


def test_source_selection_rejects_invalid_date_filters_with_typed_error(
    run_context,
    assert_app_error,
) -> None:
    request = CrossReportAnalysisRequest(
        **{**_request().__dict__, "date_range_start": "2026-99-01"}
    )

    with pytest.raises(Exception) as exc:
        select_cross_report_source_reports(
            request,
            _projected_data(
                [
                    _candidate(
                        "report-a",
                        publisher="Publisher A",
                        report_date="2026-05-02",
                        evidence_count=3,
                    )
                ]
            ),
            run_context,
        )

    assert_app_error(
        exc.value,
        code="cross_report_date_filter_invalid",
        retryable=False,
        severity="error",
    )


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


def test_theme_selection_explicit_topic_does_not_load_recent_artifacts(
    run_context,
    tmp_path,
    external_boundary_mocks_only,
) -> None:
    calls: list[str] = []

    def _list_directory(request_arg, ctx):
        calls.append(request_arg.root_dir)
        raise AssertionError("explicit theme selection must not read recent artifacts")

    external_boundary_mocks_only.setattr(
        input_gen.file_service, "list_directory", _list_directory
    )

    result = select_cross_report_theme(
        _request(),
        _source_selection(
            [
                _selected_source(
                    "report-a",
                    publisher="Publisher A",
                    report_date="2026-05-01",
                    evidence_count=4,
                    tags=["AI"],
                    categories=["Retail"],
                )
            ]
        ),
        run_context,
        recent_artifacts_root=str(tmp_path),
    )

    assert result.selected_theme.theme_id == "theme-explicit-ai-commerce"
    assert calls == []


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


def test_theme_selection_auto_handles_tag_only_and_category_only_taxonomy(
    run_context,
) -> None:
    base_request = _request()
    request = CrossReportAnalysisRequest(
        **{**base_request.__dict__, "topic": "", "auto_theme": True}
    )
    tag_only = select_cross_report_theme(
        request,
        _source_selection(
            [
                _selected_source(
                    "report-a",
                    publisher="Publisher A",
                    report_date="2026-05-01",
                    evidence_count=4,
                    tags=["AI"],
                    categories=[],
                ),
                _selected_source(
                    "report-b",
                    publisher="Publisher B",
                    report_date="2026-05-02",
                    evidence_count=4,
                    tags=["AI"],
                    categories=[],
                    rank=2,
                ),
            ]
        ),
        run_context,
    )
    category_only = select_cross_report_theme(
        request,
        _source_selection(
            [
                _selected_source(
                    "report-c",
                    publisher="Publisher C",
                    report_date="2026-05-01",
                    evidence_count=4,
                    tags=[],
                    categories=["Retail"],
                ),
                _selected_source(
                    "report-d",
                    publisher="Publisher D",
                    report_date="2026-05-02",
                    evidence_count=4,
                    tags=[],
                    categories=["Retail"],
                    rank=2,
                ),
            ]
        ),
        run_context,
    )

    assert tag_only.selected_theme.matched_tags == ["AI"]
    assert tag_only.selected_theme.matched_categories == []
    assert category_only.selected_theme.matched_tags == []
    assert category_only.selected_theme.matched_categories == ["Retail"]


def test_theme_selection_uses_total_taxonomy_sort_for_case_ties(
    run_context,
) -> None:
    request = CrossReportAnalysisRequest(
        **{**_request().__dict__, "topic": "", "auto_theme": True, "tag_filters": []}
    )
    source_selection = _source_selection(
        [
            _selected_source(
                "report-a",
                publisher="Publisher A",
                report_date="2026-05-01",
                evidence_count=4,
                tags=["ai", "AI"],
                categories=["retail", "Retail"],
            ),
            _selected_source(
                "report-b",
                publisher="Publisher B",
                report_date="2026-05-02",
                evidence_count=4,
                tags=["AI", "ai"],
                categories=["Retail", "retail"],
                rank=2,
            ),
        ]
    )

    result = select_cross_report_theme(request, source_selection, run_context)
    repeat = select_cross_report_theme(request, source_selection, run_context)

    assert [candidate.theme_id for candidate in result.theme_candidates] == [
        candidate.theme_id for candidate in repeat.theme_candidates
    ]
    tag_candidate = {
        candidate.theme_id: candidate for candidate in result.theme_candidates
    }["theme-tag-ai"]
    category_candidate = {
        candidate.theme_id: candidate for candidate in result.theme_candidates
    }["theme-category-retail"]
    assert tag_candidate.label == "AI"
    assert tag_candidate.matched_tags == ["AI"]
    assert category_candidate.label == "Retail"
    assert category_candidate.matched_tags == ["AI", "ai"]
    assert category_candidate.matched_categories == ["Retail"]


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


__all__ = [
    "test_source_selection_is_ranked_deterministic_and_diverse",
    "test_source_selection_honors_max_report_cap_and_filters",
    "test_source_selection_honors_category_id_filters_when_label_differs",
    "test_source_selection_normalizes_whitespace_dates",
    "test_source_selection_rejects_invalid_date_filters_with_typed_error",
    "test_source_selection_excludes_non_projected_sources_before_synthesis",
    "test_source_selection_diagnostic_mode_can_inspect_failed_projection",
    "test_source_selection_empty_projected_set_fails_with_typed_error",
    "test_theme_selection_uses_explicit_topic_without_auto_theme",
    "test_theme_selection_explicit_topic_does_not_load_recent_artifacts",
    "test_theme_selection_auto_generates_ranked_candidates_and_logs",
    "test_theme_selection_auto_handles_tag_only_and_category_only_taxonomy",
    "test_theme_selection_uses_total_taxonomy_sort_for_case_ties",
    "test_theme_selection_fails_when_no_eligible_theme",
    "test_theme_variety_downranks_recent_repetition_through_file_service",
]
