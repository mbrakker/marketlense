# ruff: noqa: F401,F403,F405
from __future__ import annotations

from pathlib import Path as _SplitPath
__file__ = str(_SplitPath(__file__).resolve().parent.parent / "test_cli.py")

import json

import sys

import tempfile

import types

import unittest

from dataclasses import replace

from pathlib import Path

from unittest.mock import patch

import typer

from rich.console import Console

import yaml

from src.contracts.browser_download import (
    BrowserDownloadConfirmationEvidence,
    BrowserDownloadIdentity,
    BrowserDownloadIdentityField,
    BrowserDownloadSessionReusePolicy,
    BrowserDeveloperDiagnosticCheck,
    BrowserDeveloperDiagnosticsResult,
    BrowserDownloadRouteStep,
    BrowserDownloadSettings,
    DownloadTerminalEvidence,
    ReportDownloadOrchestratorResult,
)

from src.contracts.ui_run_control import UiRunRecord

from src.contracts.ui_run_replay import (
    UiRunExecutionResponse,
    UiRunReplayReport,
    UiRunReplayResponse,
)

from src.contracts.acquisition_audit import (
    AcquisitionAuditBatchResult,
    AcquisitionAuditCandidateResult,
    AcquisitionAuditPublisherSummary,
)

from src.contracts.config import AppSettings

from src.contracts.costs import CostReportResponse, CostTotals, StepCostTotal

from src.contracts.cross_report_analysis import (
    CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
    CrossReportAnalysisRequest,
    CrossReportAnalysisSection,
    CrossReportEvidenceReference,
    CrossReportGeneratedAnalysisResult,
    CrossReportOrchestratorOutcome,
    CrossReportPublishRequestSummary,
    CrossReportPublishResultSummary,
    CrossReportRawMetricReference,
    CrossReportSelectedSourceReport,
    CrossReportSelectedTheme,
    CrossReportSignalScore,
    CrossReportValidationResult,
)

from src.contracts.ingest import IngestOutcome, IngestSettings

from src.contracts.publisher_inventory import (
    PublisherInventoryDiffItem,
    PublisherInventoryDiscoveryResult,
    PublisherInventoryRunQualitySummary,
    PublisherInventorySettings,
)

from src.contracts.publish import PublishOutcome, PublishSettings

from src.contracts.wordpress import WordPressAuthSettings

from src.utils.errors import AppError

def _cross_report_cli_outcome() -> CrossReportOrchestratorOutcome:
    request = CrossReportAnalysisRequest(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        request_id="cli-cross-report:test",
        topic="AI commerce",
        auto_theme=True,
        category_filters=["Retail"],
        tag_filters=["AI"],
        publisher_filters=["Publisher A"],
        date_range_start="2026-05-01",
        date_range_end="2026-05-31",
        max_source_reports=2,
        diagnostic=False,
        override_publishability=False,
        publication_mode="generate_only",
    )
    selected_theme = CrossReportSelectedTheme(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        theme_id="theme-ai-commerce",
        label="AI commerce",
        rationale="Selected for test coverage.",
        matched_tags=["AI"],
        matched_categories=["Retail"],
        source_report_ids=["report-a"],
        score_components={"density": 1.0},
        selection_reasons=["test"],
        rejection_risks=[],
    )
    selected_source = CrossReportSelectedSourceReport(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        report_id="report-a",
        title="AI Commerce Outlook",
        publisher="Publisher A",
        publisher_id="publisher-a",
        report_date="2026-05-01",
        projection_status="projected",
        content_hash="hash-a",
        rank=1,
        selection_reasons=["test"],
        evidence_count=1,
        category_labels=["Retail"],
        tags=["AI"],
    )
    evidence = CrossReportEvidenceReference(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        evidence_id="report-a:claim:1",
        report_id="report-a",
        publisher="Publisher A",
        title="AI Commerce Outlook",
        source_table="report_claims",
        entity_uid="claim-1",
        content_class="claim",
        text="AI commerce adoption is increasing.",
        source_metadata={"page": 1},
    )
    signal = CrossReportSignalScore(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        signal_id="signal-ai",
        label="AI commerce signal",
        evidence_ids=["report-a:claim:1"],
        component_scores={"recurrence": 1.0},
        total_score=1.0,
        reasons=["test"],
    )
    raw_metric = CrossReportRawMetricReference(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        metric_id="report-a:metric:1",
        report_id="report-a",
        publisher="Publisher A",
        label="Adoption",
        raw_value="42",
        unit="percent",
        context="Source-specific survey response.",
        evidence_id="report-a:claim:1",
        source_metadata={"page": 2},
    )
    section = CrossReportAnalysisSection(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        section_id="signals",
        heading="Signals",
        body="AI commerce is visible in the selected report.",
        evidence_ids=["report-a:claim:1"],
        raw_metric_ids=["report-a:metric:1"],
    )
    generated = CrossReportGeneratedAnalysisResult(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        analysis_id="analysis-ai-commerce",
        title="AI Commerce Across Reports",
        slug="ai-commerce-across-reports",
        executive_summary="AI commerce is visible.",
        selected_theme=selected_theme,
        selected_sources=[selected_source],
        evidence=[evidence],
        signal_scores=[signal],
        raw_metrics=[raw_metric],
        sections=[section],
        evidence_map={"signals": ["report-a:claim:1"]},
        prompt_hashes={"system": "abc", "user": "def"},
        model="gpt-5-mini",
        cost_summary={"total_tokens": 100},
        decision_focus="Prioritize the verified AI commerce signal.",
        executive_takeaways=[
            "AI commerce is visible in the selected report.",
            "Raw metrics remain source-specific.",
        ],
    )
    validation = CrossReportValidationResult(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        status="pass",
        checked_evidence_ids=["report-a:claim:1"],
        missing_evidence_ids=[],
        issues=[],
        metric_normalization_violations=[],
        prompt_budget_chars=1200,
        passed=True,
    )
    publish_request = CrossReportPublishRequestSummary(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        publication_mode="generate_only",
        target_route="wordpress:ml_briefing",
        title=generated.title,
        slug=generated.slug,
        artifact_path="out/cross_report_analysis/ai-commerce/analysis.json",
        validation_status="pass",
        selected_report_ids=["report-a"],
        selected_theme_id="theme-ai-commerce",
    )
    publish_result = CrossReportPublishResultSummary(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        publication_mode="generate_only",
        status="not_requested",
        target_route="wordpress:ml_briefing",
        idempotency_reused=False,
        target_post_type="ml_briefing",
        target_slug="ai-commerce-across-reports",
        category_slugs=["retail"],
        tag_slugs=["ai"],
        taxonomy_term_slugs={"ml_publisher": ["publisher-a"]},
    )
    return CrossReportOrchestratorOutcome(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        run_id="run-1",
        task_id="task-1",
        status="validated",
        artifact_path="out/cross_report_analysis/ai-commerce/analysis.json",
        request=request,
        generated_result=generated,
        validation_result=validation,
        publish_request=publish_request,
        publish_result=publish_result,
        idempotency_key="idem-key",
        idempotency_reused=False,
        state_transitions=["started", "completed"],
    )

if __name__ == "__main__":
    unittest.main()



__all__ = [
    name
    for name in globals()
    if name
    not in {
        '__name__', '__annotations__', '__doc__', '__spec__',
        '__file__', '__package__', '__loader__', '__cached__',
        '__builtins__', '_SplitPath',
    }
]
