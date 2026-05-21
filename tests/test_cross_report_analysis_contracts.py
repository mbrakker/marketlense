from __future__ import annotations

from dataclasses import asdict, fields, is_dataclass
from typing import Any

import pytest

from src.contracts.cross_report_analysis import (
    CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
    CrossReportAnalysisRequest,
    CrossReportAnalysisSection,
    CrossReportEvidenceAgreementGroup,
    CrossReportEvidenceAgreementResult,
    CrossReportEvidenceInputResult,
    CrossReportEvidenceReference,
    CrossReportGeneratedAnalysisResult,
    CrossReportOrchestratorOutcome,
    CrossReportPublishabilityResult,
    CrossReportPublishRequestSummary,
    CrossReportPublishResultSummary,
    CrossReportRawMetricReference,
    CrossReportSelectedSourceReport,
    CrossReportSelectedTheme,
    CrossReportSignalScore,
    CrossReportSignalScoreResult,
    CrossReportSourceReportCandidate,
    CrossReportSourceSelectionResult,
    CrossReportThemeCandidate,
    CrossReportThemeSelectionResult,
    CrossReportValidationResult,
    validate_cross_report_contract,
)
from src.utils.errors import AppError


def _contracts() -> list[Any]:
    request = CrossReportAnalysisRequest(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        request_id="cross-request-1",
        topic="consumer trust in AI shopping assistants",
        auto_theme=False,
        category_filters=["retail"],
        tag_filters=["ai", "commerce"],
        publisher_filters=["Publisher A", "Publisher B"],
        date_range_start="2025-01-01",
        date_range_end="2026-01-01",
        max_source_reports=4,
        diagnostic=False,
        override_publishability=False,
        publication_mode="generate_only",
    )
    theme_candidate = CrossReportThemeCandidate(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        theme_id="theme-ai-commerce",
        label="AI commerce trust",
        rationale="Multiple publishers discuss shopper trust and AI commerce.",
        matched_tags=["ai", "commerce"],
        matched_categories=["retail"],
        source_report_ids=["report-a", "report-b"],
        source_publisher_count=2,
        evidence_count=6,
        recency_score=0.8,
        density_score=0.7,
        diversity_score=0.9,
        novelty_score=0.6,
        total_score=3.0,
        rejection_risks=["thin metric context"],
    )
    selected_theme = CrossReportSelectedTheme(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        theme_id="theme-ai-commerce",
        label="AI commerce trust",
        rationale="Strongest publishable theme after diversity scoring.",
        matched_tags=["ai", "commerce"],
        matched_categories=["retail"],
        source_report_ids=["report-a", "report-b"],
        score_components={"recency": 0.8, "diversity": 0.9},
        selection_reasons=["two publishers", "six evidence items"],
        rejection_risks=["thin metric context"],
    )
    theme_selection_result = CrossReportThemeSelectionResult(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        selected_theme=selected_theme,
        theme_candidates=[theme_candidate],
        rejected_theme_candidates=[],
    )
    source_candidate = CrossReportSourceReportCandidate(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        report_id="report-a",
        title="AI Commerce Outlook",
        publisher="Publisher A",
        publisher_id="publisher-a",
        report_date="2025-11-01",
        projection_status="projected",
        content_hash="hash-a",
        category_labels=["Retail"],
        tags=["ai", "commerce"],
        evidence_count=3,
        claim_count=2,
        finding_count=1,
        quote_count=1,
        metric_count=1,
        recency_score=0.9,
        relevance_score=0.8,
        diversity_score=0.7,
        density_score=0.6,
        total_score=3.0,
        selection_reasons=["category match"],
        rejection_reasons=[],
    )
    selected_source = CrossReportSelectedSourceReport(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        report_id="report-a",
        title="AI Commerce Outlook",
        publisher="Publisher A",
        publisher_id="publisher-a",
        report_date="2025-11-01",
        projection_status="projected",
        content_hash="hash-a",
        rank=1,
        selection_reasons=["category match"],
        evidence_count=3,
        category_labels=["Retail"],
        tags=["ai", "commerce"],
    )
    source_selection_result = CrossReportSourceSelectionResult(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        selected_sources=[selected_source],
        ranked_candidates=[source_candidate],
        rejected_candidates=[],
        cleaned_filters={"tag_filters": ["ai"], "category_filters": ["retail"]},
        excluded_report_counts={"max_source_reports_reached": 1},
    )
    publishability_result = CrossReportPublishabilityResult(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        selected_theme_id="theme-ai-commerce",
        publishable=True,
        override_applied=False,
        diagnostic=False,
        source_report_count=2,
        source_publisher_count=2,
        evidence_count=6,
        checked_policy_fields={"min_source_reports": 2},
        issues=[],
    )
    evidence = CrossReportEvidenceReference(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        evidence_id="ev-report-a-claim-1",
        report_id="report-a",
        publisher="Publisher A",
        title="AI Commerce Outlook",
        source_table="report_claims",
        entity_uid="claim-a-1",
        content_class="claim",
        text="Shoppers want transparent AI recommendations.",
        source_metadata={"page": 12},
    )
    signal = CrossReportSignalScore(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        signal_id="signal-trust",
        label="Trust is a recurring adoption constraint",
        evidence_ids=["ev-report-a-claim-1"],
        component_scores={"recurrence": 0.7, "source_diversity": 0.8},
        total_score=1.5,
        reasons=["appears across multiple source reports"],
    )
    raw_metric = CrossReportRawMetricReference(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        metric_id="metric-a-1",
        report_id="report-a",
        publisher="Publisher A",
        label="AI assistant usage",
        raw_value="42",
        unit="percent",
        context="Survey respondents reporting monthly usage.",
        evidence_id="ev-report-a-claim-1",
        source_metadata={"page": 14},
    )
    evidence_input_result = CrossReportEvidenceInputResult(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        selected_sources=[selected_source],
        evidence=[evidence],
        raw_metrics=[raw_metric],
        evidence_by_report_id={"report-a": ["ev-report-a-claim-1"]},
        dropped_evidence_counts={},
        prompt_input_chars=512,
    )
    signal_result = CrossReportSignalScoreResult(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        selected_theme=selected_theme,
        signal_scores=[signal],
        selected_signal_ids=["signal-trust"],
        score_weights={"recurrence": 1.0, "diversity": 1.0},
        raw_metric_policy="raw_metrics_preserved_without_normalization",
        dropped_signal_counts={},
    )
    evidence_group = CrossReportEvidenceAgreementGroup(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        group_id="group-signal-trust",
        label="Trust is a recurring adoption constraint",
        agreement_type="convergent",
        signal_ids=["signal-trust"],
        evidence_ids=["ev-report-a-claim-1"],
        source_report_ids=["report-a"],
        publisher_count=1,
        uncertainty_reasons=["single_report_coverage"],
        prompt_input_label="convergent: Trust is a recurring adoption constraint",
    )
    agreement_result = CrossReportEvidenceAgreementResult(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        selected_theme=selected_theme,
        evidence_groups=[evidence_group],
        prompt_uncertainty_inputs=[
            {
                "group_id": "group-signal-trust",
                "agreement_type": "convergent",
                "evidence_ids": ["ev-report-a-claim-1"],
                "uncertainty_reasons": ["single_report_coverage"],
            }
        ],
        agreement_counts={"convergent": 1},
    )
    section = CrossReportAnalysisSection(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        section_id="executive-summary",
        heading="Executive summary",
        body="Trust and transparency shape AI commerce adoption.",
        evidence_ids=["ev-report-a-claim-1"],
        raw_metric_ids=["metric-a-1"],
    )
    generated = CrossReportGeneratedAnalysisResult(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        analysis_id="analysis-ai-commerce",
        title="AI Commerce Trust Across Reports",
        slug="ai-commerce-trust-across-reports",
        executive_summary="Trust is a recurring constraint.",
        selected_theme=selected_theme,
        selected_sources=[selected_source],
        evidence=[evidence],
        signal_scores=[signal],
        raw_metrics=[raw_metric],
        sections=[section],
        evidence_map={"claim-1": ["ev-report-a-claim-1"]},
        prompt_hashes={"system": "abc", "user": "def"},
        model="gpt-5-mini",
        cost_summary={"estimated_input_tokens": 1200},
    )
    validation = CrossReportValidationResult(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        status="pass",
        checked_evidence_ids=["ev-report-a-claim-1"],
        missing_evidence_ids=[],
        issues=[],
        metric_normalization_violations=[],
        prompt_budget_chars=1200,
        passed=True,
    )
    publish_request = CrossReportPublishRequestSummary(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        publication_mode="publish_dry_run",
        target_route="wordpress:ml_report",
        title="AI Commerce Trust Across Reports",
        slug="ai-commerce-trust-across-reports",
        artifact_path="out/cross_report_analysis/ai-commerce/analysis.json",
        validation_status="pass",
        selected_report_ids=["report-a"],
        selected_theme_id="theme-ai-commerce",
    )
    publish_result = CrossReportPublishResultSummary(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        publication_mode="publish_dry_run",
        status="dry_run",
        target_route="wordpress:ml_report",
        post_id=None,
        post_url=None,
        idempotency_reused=False,
        error_code=None,
        error_message=None,
    )
    outcome = CrossReportOrchestratorOutcome(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        run_id="run-1",
        task_id="task-1",
        status="generated",
        artifact_path="out/cross_report_analysis/ai-commerce/analysis.json",
        request=request,
        generated_result=generated,
        validation_result=validation,
        publish_request=publish_request,
        publish_result=publish_result,
        idempotency_key="idem-key",
        idempotency_reused=False,
        state_transitions=["started", "generated"],
    )
    return [
        request,
        theme_candidate,
        selected_theme,
        theme_selection_result,
        source_candidate,
        selected_source,
        source_selection_result,
        publishability_result,
        evidence_input_result,
        evidence,
        signal,
        signal_result,
        evidence_group,
        agreement_result,
        raw_metric,
        section,
        generated,
        validation,
        publish_request,
        publish_result,
        outcome,
    ]


@pytest.mark.parametrize("contract", _contracts())
def test_cross_report_contracts_are_dataclasses_with_documented_fields(
    contract: Any,
) -> None:
    assert is_dataclass(contract)
    assert asdict(contract)["schema_version"] == CROSS_REPORT_ANALYSIS_SCHEMA_VERSION
    for field_def in fields(contract):
        assert "doc" in field_def.metadata


@pytest.mark.parametrize("contract", _contracts())
def test_cross_report_contract_validation_accepts_complete_contracts(
    contract: Any,
    assert_no_defaulted_required_fields,
) -> None:
    assert_no_defaulted_required_fields(contract)
    validate_cross_report_contract(contract)


def test_cross_report_contract_validation_rejects_missing_required_semantics(
    assert_app_error,
) -> None:
    invalid = CrossReportEvidenceReference(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        evidence_id="",
        report_id="report-a",
        publisher="Publisher A",
        title="AI Commerce Outlook",
        source_table="report_claims",
        entity_uid="claim-a-1",
        content_class="claim",
        text="Shoppers want transparent AI recommendations.",
        source_metadata={"page": 12},
    )

    with pytest.raises(AppError) as exc:
        validate_cross_report_contract(invalid)

    assert_app_error(
        exc.value,
        code="cross_report_contract_invalid",
        retryable=False,
        severity="error",
    )
    assert exc.value.context["field"] == "evidence_id"
