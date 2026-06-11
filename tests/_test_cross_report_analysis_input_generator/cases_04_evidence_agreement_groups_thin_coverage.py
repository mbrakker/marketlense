# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403

def test_evidence_agreement_groups_thin_coverage_signal_inputs(
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
            )
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
            )
        ],
        raw_metrics=[],
        content_hashes={},
        excluded_report_counts={},
    )
    request = _request(max_source_reports=1)
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
    assert ai_group.uncertainty_reasons == ["single_report_coverage"]
    assert result.prompt_uncertainty_inputs[0]["agreement_type"] == "thin_coverage"

__all__ = [
    "test_evidence_agreement_groups_thin_coverage_signal_inputs",
]
