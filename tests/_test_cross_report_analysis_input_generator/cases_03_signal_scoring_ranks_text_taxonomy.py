# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403

def test_signal_scoring_ranks_text_taxonomy_without_metric_normalization(
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
                report_date="2026-05-04",
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
            _evidence(
                "report-a-claim-1",
                report_id="report-a",
                content_class="claim",
                text="AI commerce adoption is increasing among retail leaders.",
            ),
            _evidence(
                "report-a-finding-1",
                report_id="report-a",
                content_class="finding",
                text="Retail AI pilots are moving into personalization workflows.",
            ),
            _evidence(
                "report-b-quote-1",
                report_id="report-b",
                content_class="quote",
                text="Executives say AI commerce growth is strong but uneven.",
            ),
        ],
        raw_metrics=[
            _raw_metric(
                "metric-a",
                report_id="report-a",
                raw_value="42",
                unit="percent",
            ),
            _raw_metric(
                "metric-b",
                report_id="report-b",
                raw_value="900000",
                unit="basis points",
            ),
        ],
        content_hashes={},
        excluded_report_counts={},
    )
    evidence_inputs = assemble_cross_report_analysis_inputs(
        _request(),
        source_selection,
        projected_data,
        run_context,
    )
    theme_selection = select_cross_report_theme(
        _request(),
        source_selection,
        run_context,
    )

    caplog.set_level(
        logging.INFO, logger="market_lense.cross_report_analysis_input_generator"
    )
    result = score_cross_report_signals(
        _request(),
        evidence_inputs,
        theme_selection,
        run_context,
        score_weights={
            "recurrence": 2.0,
            "diversity": 1.0,
            "recency": 1.0,
            "taxonomy_fit": 1.5,
            "support": 1.0,
            "contradiction": 0.5,
        },
    )

    assert is_dataclass(result)
    assert result.raw_metric_policy == "raw_metrics_preserved_without_normalization"
    assert result.selected_signal_ids[0] == "signal-ai"
    signal = result.signal_scores[0]
    assert signal.label == "AI"
    assert signal.evidence_ids == [
        "report-a-claim-1",
        "report-a-finding-1",
        "report-b-quote-1",
    ]
    assert signal.component_scores == {
        "contradiction": 1.0,
        "diversity": 1.0,
        "recency": 1.0,
        "recurrence": 1.0,
        "support": 1.0,
        "taxonomy_fit": 1.0,
    }
    assert "raw_metric_magnitude_ignored" in signal.reasons
    events = _events(caplog)
    assert_logs_have_required_fields(events)
    complete = [
        event
        for event in events
        if event["event"] == "cross_report_signal_scoring_complete"
    ][0]
    assert complete["fields"]["selected_signal_ids"] == ["signal-ai", "signal-retail"]
    assert complete["fields"]["raw_metric_policy"] == result.raw_metric_policy

def test_signal_scoring_matches_short_labels_on_token_boundaries(
    run_context,
) -> None:
    request = CrossReportAnalysisRequest(
        **{**_request().__dict__, "tag_filters": ["AI"], "category_filters": []}
    )
    source_selection = _source_selection(
        [
            _selected_source(
                "report-a",
                publisher="Publisher A",
                report_date="2026-05-01",
                evidence_count=2,
                tags=["Commerce"],
                categories=["Retail"],
                rank=1,
            )
        ]
    )
    evidence_inputs = assemble_cross_report_analysis_inputs(
        request,
        source_selection,
        CrossReportProjectedDataReadResponse(
            schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
            source_candidates=[],
            evidence=[
                _evidence(
                    "report-a-claim-1",
                    report_id="report-a",
                    text="Paid media budgets are rising.",
                ),
                _evidence(
                    "report-a-claim-2",
                    report_id="report-a",
                    text="AI pilots are expanding.",
                ),
            ],
            raw_metrics=[],
            content_hashes={},
            excluded_report_counts={},
        ),
        run_context,
    )
    theme_selection = select_cross_report_theme(request, source_selection, run_context)

    result = score_cross_report_signals(
        request, evidence_inputs, theme_selection, run_context
    )

    ai_signal = next(
        score for score in result.signal_scores if score.signal_id == "signal-ai"
    )
    assert ai_signal.evidence_ids == ["report-a-claim-2"]

def test_signal_scoring_disambiguates_slug_collisions(
    run_context,
) -> None:
    request = CrossReportAnalysisRequest(
        **{**_request().__dict__, "tag_filters": [], "category_filters": []}
    )
    source_selection = _source_selection(
        [
            _selected_source(
                "report-a",
                publisher="Publisher A",
                report_date="2026-05-01",
                evidence_count=2,
                tags=["AI/ML", "AI ML"],
                categories=[],
                rank=1,
            )
        ]
    )
    evidence_inputs = assemble_cross_report_analysis_inputs(
        request,
        source_selection,
        CrossReportProjectedDataReadResponse(
            schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
            source_candidates=[],
            evidence=[
                _evidence(
                    "report-a-claim-1",
                    report_id="report-a",
                    text="AI/ML investments are increasing.",
                ),
                _evidence(
                    "report-a-claim-2",
                    report_id="report-a",
                    text="AI ML operating models are maturing.",
                ),
            ],
            raw_metrics=[],
            content_hashes={},
            excluded_report_counts={},
        ),
        run_context,
    )
    theme_selection = select_cross_report_theme(
        CrossReportAnalysisRequest(
            **{**request.__dict__, "topic": "", "auto_theme": True}
        ),
        source_selection,
        run_context,
    )

    result = score_cross_report_signals(
        request, evidence_inputs, theme_selection, run_context, max_signals=4
    )

    assert len(result.selected_signal_ids) == len(set(result.selected_signal_ids))
    assert {"signal-ai-ml", "signal-ai-ml-2"}.issubset(result.selected_signal_ids)

def test_signal_scoring_is_unchanged_when_only_raw_metric_values_change(
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
                report_date="2026-05-04",
                evidence_count=2,
                tags=["AI"],
                categories=["Retail"],
                rank=2,
            ),
        ]
    )
    base_projected_data = CrossReportProjectedDataReadResponse(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        source_candidates=[],
        evidence=[
            _evidence(
                "report-a-claim-1",
                report_id="report-a",
                content_class="claim",
                text="AI commerce adoption is increasing among retail leaders.",
            ),
            _evidence(
                "report-b-finding-1",
                report_id="report-b",
                content_class="finding",
                text="Retail AI commerce growth remains uneven.",
            ),
        ],
        raw_metrics=[
            _raw_metric("metric-a", report_id="report-a", raw_value="42", unit="%"),
            _raw_metric("metric-b", report_id="report-b", raw_value="12", unit="%"),
        ],
        content_hashes={},
        excluded_report_counts={},
    )
    changed_metric_projected_data = CrossReportProjectedDataReadResponse(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        source_candidates=[],
        evidence=base_projected_data.evidence,
        raw_metrics=[
            _raw_metric(
                "metric-a",
                report_id="report-a",
                raw_value="4.2 million",
                unit="users",
            ),
            _raw_metric(
                "metric-b",
                report_id="report-b",
                raw_value="0.001",
                unit="index points",
            ),
        ],
        content_hashes={},
        excluded_report_counts={},
    )
    theme_selection = select_cross_report_theme(
        _request(),
        source_selection,
        run_context,
    )

    base_result = score_cross_report_signals(
        _request(),
        assemble_cross_report_analysis_inputs(
            _request(),
            source_selection,
            base_projected_data,
            run_context,
        ),
        theme_selection,
        run_context,
    )
    changed_metric_result = score_cross_report_signals(
        _request(),
        assemble_cross_report_analysis_inputs(
            _request(),
            source_selection,
            changed_metric_projected_data,
            run_context,
        ),
        theme_selection,
        run_context,
    )

    assert [
        (score.signal_id, score.component_scores, score.total_score, score.evidence_ids)
        for score in changed_metric_result.signal_scores
    ] == [
        (score.signal_id, score.component_scores, score.total_score, score.evidence_ids)
        for score in base_result.signal_scores
    ]
    assert changed_metric_result.selected_signal_ids == base_result.selected_signal_ids

def test_signal_scoring_rejects_invalid_signal_limit(
    run_context,
    assert_app_error,
) -> None:
    source_selection = _source_selection(
        [
            _selected_source(
                "report-a",
                publisher="Publisher A",
                report_date="2026-05-01",
                evidence_count=1,
                tags=["AI"],
                categories=["Retail"],
            )
        ]
    )
    evidence_inputs = assemble_cross_report_analysis_inputs(
        _request(),
        source_selection,
        CrossReportProjectedDataReadResponse(
            schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
            source_candidates=[],
            evidence=[
                _evidence(
                    "report-a-claim-1",
                    report_id="report-a",
                    text="AI commerce adoption is increasing.",
                )
            ],
            raw_metrics=[],
            content_hashes={},
            excluded_report_counts={},
        ),
        run_context,
    )
    theme_selection = select_cross_report_theme(
        _request(),
        source_selection,
        run_context,
    )

    with pytest.raises(Exception) as exc:
        score_cross_report_signals(
            _request(),
            evidence_inputs,
            theme_selection,
            run_context,
            max_signals=0,
        )

    assert_app_error(
        exc.value,
        code="cross_report_signal_limit_invalid",
        retryable=False,
        severity="error",
    )

def test_evidence_agreement_groups_convergent_signal_inputs(
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
                evidence_count=2,
                tags=["AI"],
                categories=["Retail"],
                rank=1,
            ),
            _selected_source(
                "report-b",
                publisher="Publisher B",
                report_date="2026-05-04",
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
            _evidence(
                "report-a-claim-1",
                report_id="report-a",
                text="AI commerce adoption is increasing in retail.",
            ),
            _evidence(
                "report-b-finding-1",
                report_id="report-b",
                content_class="finding",
                text="AI commerce growth is accelerating for retailers.",
            ),
        ],
        raw_metrics=[],
        content_hashes={},
        excluded_report_counts={},
    )
    request = _request()
    evidence_inputs = assemble_cross_report_analysis_inputs(
        request, source_selection, projected_data, run_context
    )
    theme_selection = select_cross_report_theme(request, source_selection, run_context)
    signal_result = score_cross_report_signals(
        request, evidence_inputs, theme_selection, run_context
    )

    caplog.set_level(
        logging.INFO, logger="market_lense.cross_report_analysis_input_generator"
    )
    result = group_cross_report_evidence_agreement(
        request, evidence_inputs, signal_result, run_context
    )

    assert result.agreement_counts["convergent"] >= 1
    ai_group = next(
        group for group in result.evidence_groups if group.group_id == "group-signal-ai"
    )
    assert ai_group.agreement_type == "convergent"
    assert ai_group.evidence_ids == ["report-a-claim-1", "report-b-finding-1"]
    assert ai_group.publisher_count == 2
    prompt_group = next(
        item
        for item in result.prompt_uncertainty_inputs
        if item["group_id"] == "group-signal-ai"
    )
    assert prompt_group["agreement_type"] == "convergent"
    assert prompt_group["uncertainty_reasons"] == ["multi_publisher_alignment"]
    events = _events(caplog)
    assert_logs_have_required_fields(events)
    complete = [
        event
        for event in events
        if event["event"] == "cross_report_evidence_agreement_grouping_complete"
    ][0]
    assert complete["fields"]["agreement_counts"]["convergent"] >= 1

def test_evidence_agreement_groups_divergent_signal_inputs(
    run_context,
) -> None:
    source_selection = _source_selection(
        [
            _selected_source(
                "report-a",
                publisher="Publisher A",
                report_date="2026-05-01",
                evidence_count=1,
                tags=["AI"],
                categories=["Retail"],
                rank=1,
            ),
            _selected_source(
                "report-b",
                publisher="Publisher B",
                report_date="2026-05-04",
                evidence_count=1,
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
            _evidence(
                "report-a-claim-1",
                report_id="report-a",
                text="AI commerce adoption is increasing among retail leaders.",
            ),
            _evidence(
                "report-b-finding-1",
                report_id="report-b",
                content_class="finding",
                text="AI commerce adoption is declining in budget-constrained retail teams.",
            ),
        ],
        raw_metrics=[],
        content_hashes={},
        excluded_report_counts={},
    )
    request = _request()
    evidence_inputs = assemble_cross_report_analysis_inputs(
        request, source_selection, projected_data, run_context
    )
    theme_selection = select_cross_report_theme(request, source_selection, run_context)
    signal_result = score_cross_report_signals(
        request, evidence_inputs, theme_selection, run_context
    )

    result = group_cross_report_evidence_agreement(
        request, evidence_inputs, signal_result, run_context
    )

    ai_group = next(
        group for group in result.evidence_groups if group.group_id == "group-signal-ai"
    )
    assert ai_group.agreement_type == "divergent"
    assert "opposed_directional_language" in ai_group.uncertainty_reasons
    assert result.agreement_counts["divergent"] >= 1

def test_evidence_agreement_requires_distinct_directional_evidence_for_divergence(
    run_context,
) -> None:
    source_selection = _source_selection(
        [
            _selected_source(
                "report-a",
                publisher="Publisher A",
                report_date="2026-05-01",
                evidence_count=1,
                tags=["AI"],
                categories=["Retail"],
                rank=1,
            ),
            _selected_source(
                "report-b",
                publisher="Publisher B",
                report_date="2026-05-04",
                evidence_count=1,
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
            _evidence(
                "report-a-claim-1",
                report_id="report-a",
                text="AI adoption is increasing but some pilots are declining.",
            ),
            _evidence(
                "report-b-finding-1",
                report_id="report-b",
                content_class="finding",
                text="AI adoption remains a priority.",
            ),
        ],
        raw_metrics=[],
        content_hashes={},
        excluded_report_counts={},
    )
    request = _request()
    evidence_inputs = assemble_cross_report_analysis_inputs(
        request, source_selection, projected_data, run_context
    )
    theme_selection = select_cross_report_theme(request, source_selection, run_context)
    signal_result = score_cross_report_signals(
        request, evidence_inputs, theme_selection, run_context
    )

    result = group_cross_report_evidence_agreement(
        request, evidence_inputs, signal_result, run_context
    )

    ai_group = next(
        group for group in result.evidence_groups if group.group_id == "group-signal-ai"
    )
    assert ai_group.agreement_type == "convergent"
    assert ai_group.uncertainty_reasons == ["multi_publisher_alignment"]

def test_evidence_agreement_same_publisher_opposition_is_thin_coverage(
    run_context,
) -> None:
    source_selection = _source_selection(
        [
            _selected_source(
                "report-a",
                publisher="Publisher A",
                report_date="2026-05-01",
                evidence_count=1,
                tags=["AI"],
                categories=["Retail"],
                rank=1,
            ),
            _selected_source(
                "report-b",
                publisher="Publisher A",
                report_date="2026-05-04",
                evidence_count=1,
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
            _evidence(
                "report-a-claim-1",
                report_id="report-a",
                text="AI commerce adoption is increasing.",
            ),
            _evidence(
                "report-b-finding-1",
                report_id="report-b",
                content_class="finding",
                text="AI commerce adoption is declining.",
            ),
        ],
        raw_metrics=[],
        content_hashes={},
        excluded_report_counts={},
    )
    request = _request()
    evidence_inputs = assemble_cross_report_analysis_inputs(
        request, source_selection, projected_data, run_context
    )
    theme_selection = select_cross_report_theme(request, source_selection, run_context)
    signal_result = score_cross_report_signals(
        request, evidence_inputs, theme_selection, run_context
    )

    result = group_cross_report_evidence_agreement(
        request, evidence_inputs, signal_result, run_context
    )

    ai_group = next(
        group for group in result.evidence_groups if group.group_id == "group-signal-ai"
    )
    assert ai_group.agreement_type == "thin_coverage"

__all__ = [
    "test_signal_scoring_ranks_text_taxonomy_without_metric_normalization",
    "test_signal_scoring_matches_short_labels_on_token_boundaries",
    "test_signal_scoring_disambiguates_slug_collisions",
    "test_signal_scoring_is_unchanged_when_only_raw_metric_values_change",
    "test_signal_scoring_rejects_invalid_signal_limit",
    "test_evidence_agreement_groups_convergent_signal_inputs",
    "test_evidence_agreement_groups_divergent_signal_inputs",
    "test_evidence_agreement_requires_distinct_directional_evidence_for_divergence",
    "test_evidence_agreement_same_publisher_opposition_is_thin_coverage",
]
