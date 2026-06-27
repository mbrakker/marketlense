# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403


def test_theme_variety_excludes_undated_recent_artifacts_and_logs(
    run_context,
    tmp_path,
    caplog,
    assert_logs_have_required_fields,
    external_boundary_mocks_only,
) -> None:
    request = CrossReportAnalysisRequest(
        **{**_request().__dict__, "topic": "", "auto_theme": True}
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
        ]
    )

    def _list_directory(request_arg, ctx):
        return ListDirectoryResponse(
            schema_version="1.0",
            root_dir=request_arg.root_dir,
            entries=[
                DirectoryEntry(
                    schema_version="1.0",
                    path=str(tmp_path / "undated" / "analysis.json"),
                    name="analysis.json",
                    is_dir=False,
                    size_bytes=200,
                    mtime_utc=1.0,
                ),
                DirectoryEntry(
                    schema_version="1.0",
                    path=str(tmp_path / "invalid" / "analysis.json"),
                    name="analysis.json",
                    is_dir=False,
                    size_bytes=200,
                    mtime_utc=2.0,
                ),
            ],
        )

    def _read_text_files(request_arg, ctx):
        return ReadTextFilesResponse(
            schema_version="1.0",
            files=[
                ReadTextResponse(
                    schema_version="1.0",
                    path=path,
                    content=json.dumps(
                        {
                            "generated_at_utc": ""
                            if "undated" in path
                            else "not-a-date",
                            "selected_theme": {
                                "theme_id": "theme-tag-ai",
                                "matched_tags": ["AI"],
                                "matched_categories": ["Retail"],
                                "source_report_ids": ["old-report"],
                            },
                        }
                    ),
                )
                for path in request_arg.paths
            ],
        )

    external_boundary_mocks_only.setattr(
        input_gen.file_service, "list_directory", _list_directory
    )
    external_boundary_mocks_only.setattr(
        input_gen.file_service, "read_text_files", _read_text_files
    )
    caplog.set_level(
        logging.INFO, logger="market_lense.cross_report_analysis_input_generator"
    )

    result = select_cross_report_theme(
        request,
        source_selection,
        run_context,
        recent_artifacts_root=str(tmp_path),
        theme_rotation_window_days=30,
        theme_rotation_reference_date="2026-05-21",
    )

    assert result.selected_theme.theme_id == "theme-tag-ai"
    assert result.theme_candidates[0].novelty_score == 1.0
    events = _events(caplog)
    assert_logs_have_required_fields(events)
    loaded = [
        event
        for event in events
        if event["event"] == "cross_report_recent_theme_metadata_loaded"
    ][0]
    assert loaded["fields"]["skipped_undated_artifacts"] == 1
    assert loaded["fields"]["skipped_invalid_date_artifacts"] == 1


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


def test_evidence_input_assembly_filters_selected_reports_and_preserves_metric_provenance(
    run_context,
    caplog,
    assert_logs_have_required_fields,
) -> None:
    source_selection = _source_selection(
        [
            _selected_source(
                "report-a",
                publisher="Publisher A",
                report_date="2026-05-01",
                evidence_count=3,
                tags=["AI"],
                categories=["Retail"],
                rank=1,
            ),
            _selected_source(
                "report-b",
                publisher="Publisher B",
                report_date="2026-05-02",
                evidence_count=3,
                tags=["AI"],
                categories=["Retail"],
                rank=2,
            ),
        ]
    )
    projected_data = CrossReportProjectedDataReadResponse(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        source_candidates=[],
        evidence=[
            _evidence("report-a-claim-1", report_id="report-a", content_class="claim"),
            _evidence("report-a-claim-1", report_id="report-a", content_class="claim"),
            _evidence(
                "report-a-finding-1", report_id="report-a", content_class="finding"
            ),
            _evidence("report-b-quote-1", report_id="report-b", content_class="quote"),
            _evidence("report-c-claim-1", report_id="report-c", content_class="claim"),
        ],
        raw_metrics=[
            _raw_metric(
                "metric-a",
                report_id="report-a",
                raw_value="42",
                unit="percent",
            ),
            _raw_metric(
                "metric-c",
                report_id="report-c",
                raw_value="900",
                unit="responses",
            ),
        ],
        content_hashes={"report-a": {"a": "hash-a"}, "report-b": {"b": "hash-b"}},
        excluded_report_counts={},
    )

    caplog.set_level(
        logging.INFO, logger="market_lense.cross_report_analysis_input_generator"
    )
    result = assemble_cross_report_analysis_inputs(
        _request(),
        source_selection,
        projected_data,
        run_context,
        max_evidence_items=10,
    )

    assert [item.evidence_id for item in result.evidence] == [
        "report-a-claim-1",
        "report-a-finding-1",
        "report-b-quote-1",
    ]
    assert result.evidence_by_report_id == {
        "report-a": ["report-a-claim-1", "report-a-finding-1"],
        "report-b": ["report-b-quote-1"],
    }
    assert result.dropped_evidence_counts == {
        "duplicate_evidence_id_same_report": 1,
        "unselected_raw_metric_report": 1,
        "unselected_report": 1,
    }
    assert [metric.metric_id for metric in result.raw_metrics] == ["metric-a"]
    assert result.raw_metrics[0].raw_value == "42"
    assert result.raw_metrics[0].unit == "percent"
    assert result.raw_metrics[0].source_metadata["raw_metric_reference"] is True
    assert result.prompt_input_chars > 0
    events = _events(caplog)
    assert_logs_have_required_fields(events)
    complete = [
        event
        for event in events
        if event["event"] == "cross_report_evidence_input_assembly_complete"
    ][0]
    assert complete["fields"]["evidence_count"] == 3
    assert complete["fields"]["raw_metric_count"] == 1


def test_evidence_input_assembly_enforces_cap_before_prompt_rendering(
    run_context,
) -> None:
    source_selection = _source_selection(
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
    )
    projected_data = CrossReportProjectedDataReadResponse(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        source_candidates=[],
        evidence=[
            _evidence("report-a-claim-1", report_id="report-a", content_class="claim"),
            _evidence(
                "report-a-finding-1", report_id="report-a", content_class="finding"
            ),
            _evidence("report-a-quote-1", report_id="report-a", content_class="quote"),
        ],
        raw_metrics=[],
        content_hashes={},
        excluded_report_counts={},
    )

    result = assemble_cross_report_analysis_inputs(
        _request(),
        source_selection,
        projected_data,
        run_context,
        max_evidence_items=2,
    )

    assert [item.evidence_id for item in result.evidence] == [
        "report-a-claim-1",
        "report-a-finding-1",
    ]
    assert result.dropped_evidence_counts == {"max_evidence_items_reached": 1}
    assert result.prompt_input_chars < 60000


def test_evidence_input_assembly_preserves_cross_report_scoped_evidence_ids(
    run_context,
) -> None:
    source_selection = _source_selection(
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
        ]
    )
    projected_data = CrossReportProjectedDataReadResponse(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        source_candidates=[],
        evidence=[
            _evidence("source-local-1", report_id="report-a"),
            _evidence("source-local-1", report_id="report-b"),
            _evidence("source-local-1", report_id="report-a"),
        ],
        raw_metrics=[],
        content_hashes={},
        excluded_report_counts={},
    )

    result = assemble_cross_report_analysis_inputs(
        _request(), source_selection, projected_data, run_context
    )

    assert [(item.report_id, item.evidence_id) for item in result.evidence] == [
        ("report-a", "source-local-1"),
        ("report-b", "source-local-1"),
    ]
    assert result.dropped_evidence_counts == {"duplicate_evidence_id_same_report": 1}


__all__ = [
    "test_theme_variety_excludes_undated_recent_artifacts_and_logs",
    "test_theme_variety_prefers_source_diversity_and_stable_tie_breaking",
    "test_publishability_gate_passes_supported_theme_and_logs",
    "test_publishability_gate_rejects_thin_coverage",
    "test_publishability_gate_rejects_duplicate_and_metric_dependency",
    "test_publishability_gate_allows_explicit_override_and_logs",
    "test_publishability_gate_checks_publication_validation_prerequisite",
    "test_evidence_input_assembly_filters_selected_reports_and_preserves_metric_provenance",
    "test_evidence_input_assembly_enforces_cap_before_prompt_rendering",
    "test_evidence_input_assembly_preserves_cross_report_scoped_evidence_ids",
]
