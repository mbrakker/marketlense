import json
import sys
import tempfile
import types
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import click
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
        target_route="wordpress:ml_report",
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
        target_route="wordpress:ml_report",
        idempotency_reused=False,
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


class TestCli(unittest.TestCase):
    def test_cli_pretty_exceptions_do_not_render_locals(self) -> None:
        import src.cli as cli

        self.assertFalse(cli.cli_app.pretty_exceptions_show_locals)

    def test_generate_cross_report_analysis_wires_request_and_orchestrator(
        self,
    ) -> None:
        import src.cli as cli

        settings = AppSettings(
            schema_version="1.0",
            google_sa_path="sa.json",
            gdrive_folder_id="folder",
            openai_api_key="key",
            openai_model="gpt-5",
            batch_limit=5,
            output_dir="./out",
            cache_dir="./cache",
            state_db="./state/index.sqlite",
            reports_db="./state/reports.sqlite",
            publisher_profiles_path="./Wordpress/config/publisher-profiles.json",
            category_mapping_path="./src/config/category-mappings.yaml",
            cover_style_path="./src/config/cover-styles.yaml",
            ingest_lock_path="./state/ingest.lock",
            ingest_lock_ttl_seconds=7200.0,
            temperature=1.0,
            cost_ledger_path="./out/cost-ledger.jsonl",
            cost_daily_path="./out/cost-daily.json",
            model_pricing={},
            cross_report_analysis_max_source_reports=6,
            cross_report_analysis_max_evidence_items=24,
            cross_report_analysis_max_prompt_chars=32000,
        )
        outcome = _cross_report_cli_outcome()

        with patch.object(cli, "load_settings", return_value=settings) as load_mock:
            with patch.object(
                cli,
                "run_cross_report_analysis_orchestrator",
                return_value=outcome,
            ) as orchestrator_mock:
                with patch.object(cli.console, "print"):
                    cli.generate_cross_report_analysis_cli(
                        topic="AI commerce",
                        auto_theme=True,
                        category="Retail, Commerce",
                        tag="AI",
                        publisher="Publisher A",
                        date_start="2026-05-01",
                        date_end="2026-05-31",
                        max_report_count=2,
                        max_evidence_items=18,
                        max_prompt_chars=80000,
                        publish_mode="generate_only",
                        output_root="./custom-out",
                        idempotency_db="./custom-state.sqlite",
                        request_id="operator-request",
                    )

        load_mock.assert_called_once()
        orchestrator_mock.assert_called_once()
        request = orchestrator_mock.call_args.args[0]
        self.assertEqual("operator-request", request.analysis_request.request_id)
        self.assertEqual("AI commerce", request.analysis_request.topic)
        self.assertTrue(request.analysis_request.auto_theme)
        self.assertEqual(
            ["Retail", "Commerce"], request.analysis_request.category_filters
        )
        self.assertEqual(["AI"], request.analysis_request.tag_filters)
        self.assertEqual(["Publisher A"], request.analysis_request.publisher_filters)
        self.assertEqual(2, request.analysis_request.max_source_reports)
        self.assertEqual("generate_only", request.analysis_request.publication_mode)
        self.assertEqual(
            "./state/reports.sqlite", request.projected_data_request.db_path
        )
        self.assertEqual("./custom-state.sqlite", request.idempotency_db_path)
        self.assertEqual("./custom-out", request.output_root)
        self.assertEqual(18, request.max_evidence_items)
        self.assertEqual(80000, request.max_prompt_chars)

    def test_generate_cross_report_analysis_rejects_invalid_filter_values(self) -> None:
        import src.cli as cli

        settings = AppSettings(
            schema_version="1.0",
            google_sa_path="sa.json",
            gdrive_folder_id="folder",
            openai_api_key="key",
            openai_model="gpt-5",
            batch_limit=5,
            output_dir="./out",
            cache_dir="./cache",
            state_db="./state/index.sqlite",
            reports_db="./state/reports.sqlite",
            publisher_profiles_path="./Wordpress/config/publisher-profiles.json",
            category_mapping_path="./src/config/category-mappings.yaml",
            cover_style_path="./src/config/cover-styles.yaml",
            ingest_lock_path="./state/ingest.lock",
            ingest_lock_ttl_seconds=7200.0,
            temperature=1.0,
            cost_ledger_path="./out/cost-ledger.jsonl",
            cost_daily_path="./out/cost-daily.json",
            model_pricing={},
        )

        with patch.object(cli, "load_settings", return_value=settings):
            with patch.object(
                cli, "run_cross_report_analysis_orchestrator"
            ) as run_mock:
                with patch.object(cli.console, "print") as print_mock:
                    with self.assertRaises(click.exceptions.Exit) as exc_info:
                        cli.generate_cross_report_analysis_cli(
                            topic="AI commerce",
                            auto_theme=False,
                            category="Retail,,Commerce",
                            tag="AI",
                            publisher="Publisher A",
                            date_start="2026-05-01",
                            date_end="2026-05-31",
                            max_report_count=2,
                            publish_mode="generate_only",
                            output_root="./custom-out",
                            idempotency_db="./custom-state.sqlite",
                            request_id="operator-request",
                        )

        self.assertEqual(1, exc_info.exception.exit_code)
        run_mock.assert_not_called()
        printed = " ".join(str(call.args[0]) for call in print_mock.call_args_list)
        self.assertIn("cross_report_cli_filter_invalid", printed)

    def test_cross_report_cli_uses_configured_auto_theme_default(self) -> None:
        import src.cli as cli

        settings = AppSettings(
            schema_version="1.0",
            google_sa_path="sa.json",
            gdrive_folder_id="folder",
            openai_api_key="key",
            openai_model="gpt-5",
            batch_limit=5,
            output_dir="./out",
            cache_dir="./cache",
            state_db="./state/index.sqlite",
            reports_db="./state/reports.sqlite",
            publisher_profiles_path="./Wordpress/config/publisher-profiles.json",
            category_mapping_path="./src/config/category-mappings.yaml",
            cover_style_path="./src/config/cover-styles.yaml",
            ingest_lock_path="./state/ingest.lock",
            ingest_lock_ttl_seconds=7200.0,
            temperature=1.0,
            cost_ledger_path="./out/cost-ledger.jsonl",
            cost_daily_path="./out/cost-daily.json",
            model_pricing={},
            cross_report_analysis_auto_theme_enabled=True,
        )

        request = cli._build_cross_report_cli_request(
            settings=settings,
            topic="",
            auto_theme=None,
            category="Retail",
            tag="AI",
            publisher="",
            date_start="",
            date_end="",
            max_report_count=None,
            max_evidence_items=None,
            max_prompt_chars=None,
            publish_mode="generate_only",
            output_root="",
            idempotency_db="",
            request_id="",
        )

        self.assertTrue(request.analysis_request.auto_theme)
        self.assertEqual("", request.analysis_request.topic)

    def test_generate_cross_report_analysis_rejects_invalid_date_filters(self) -> None:
        import src.cli as cli

        settings = AppSettings(
            schema_version="1.0",
            google_sa_path="sa.json",
            gdrive_folder_id="folder",
            openai_api_key="key",
            openai_model="gpt-5",
            batch_limit=5,
            output_dir="./out",
            cache_dir="./cache",
            state_db="./state/index.sqlite",
            reports_db="./state/reports.sqlite",
            publisher_profiles_path="./Wordpress/config/publisher-profiles.json",
            category_mapping_path="./src/config/category-mappings.yaml",
            cover_style_path="./src/config/cover-styles.yaml",
            ingest_lock_path="./state/ingest.lock",
            ingest_lock_ttl_seconds=7200.0,
            temperature=1.0,
            cost_ledger_path="./out/cost-ledger.jsonl",
            cost_daily_path="./out/cost-daily.json",
            model_pricing={},
        )

        with patch.object(cli, "load_settings", return_value=settings):
            with patch.object(
                cli, "run_cross_report_analysis_orchestrator"
            ) as run_mock:
                with patch.object(cli.console, "print") as print_mock:
                    with self.assertRaises(click.exceptions.Exit) as exc_info:
                        cli.generate_cross_report_analysis_cli(
                            topic="AI commerce",
                            auto_theme=False,
                            category="Retail",
                            tag="AI",
                            publisher="Publisher A",
                            date_start="2026-99-01",
                            date_end="2026-05-31",
                            max_report_count=2,
                            publish_mode="generate_only",
                            output_root="./custom-out",
                            idempotency_db="./custom-state.sqlite",
                            request_id="operator-request",
                        )

        self.assertEqual(1, exc_info.exception.exit_code)
        run_mock.assert_not_called()
        printed = " ".join(str(call.args[0]) for call in print_mock.call_args_list)
        self.assertIn("cross_report_cli_date_invalid", printed)

    def test_generate_cross_report_analysis_live_mode_loads_publish_settings(
        self,
    ) -> None:
        import src.cli as cli

        settings = AppSettings(
            schema_version="1.0",
            google_sa_path="sa.json",
            gdrive_folder_id="folder",
            openai_api_key="key",
            openai_model="gpt-5",
            batch_limit=5,
            output_dir="./out",
            cache_dir="./cache",
            state_db="./state/index.sqlite",
            reports_db="./state/reports.sqlite",
            publisher_profiles_path="./Wordpress/config/publisher-profiles.json",
            category_mapping_path="./src/config/category-mappings.yaml",
            cover_style_path="./src/config/cover-styles.yaml",
            ingest_lock_path="./state/ingest.lock",
            ingest_lock_ttl_seconds=7200.0,
            temperature=1.0,
            cost_ledger_path="./out/cost-ledger.jsonl",
            cost_daily_path="./out/cost-daily.json",
            model_pricing={},
            cross_report_analysis_publish_enabled=True,
        )
        publish_settings = PublishSettings(
            schema_version="1.0",
            output_dir="./out",
            state_db="./state/index.sqlite",
            reports_db="./state/reports.sqlite",
            category_mapping_path="./src/config/category-mappings.yaml",
            wp=WordPressAuthSettings(
                schema_version="1.0",
                site_url="https://example.com",
                username="user",
                app_password="pass",
                bearer_token=None,
                post_status="draft",
                post_type="posts",
            ),
        )

        with patch.object(cli, "load_settings", return_value=settings):
            with patch.object(
                cli, "load_publish_settings", return_value=publish_settings
            ) as load_publish_mock:
                base_outcome = _cross_report_cli_outcome()
                publish_result = replace(
                    base_outcome.publish_result,
                    publication_mode="publish_live",
                    status="published",
                    post_id=123,
                    post_url="https://example.com/cross-report",
                )
                outcome = replace(
                    base_outcome,
                    publish_result=publish_result,
                    status="published",
                )
                recording_console = Console(record=True, width=180)
                with patch.object(
                    cli,
                    "run_cross_report_analysis_orchestrator",
                    return_value=outcome,
                ) as orchestrator_mock:
                    with patch.object(cli, "console", recording_console):
                        cli.generate_cross_report_analysis_cli(
                            topic="AI commerce",
                            auto_theme=True,
                            category="Retail",
                            tag="AI",
                            publisher="Publisher A",
                            date_start="2026-05-01",
                            date_end="2026-05-31",
                            max_report_count=2,
                            publish_mode="publish_live",
                            output_root="./custom-out",
                            idempotency_db="./custom-state.sqlite",
                            request_id="operator-request",
                        )

        load_publish_mock.assert_called_once()
        self.assertIs(
            orchestrator_mock.call_args.kwargs["publish_settings"], publish_settings
        )
        output = recording_console.export_text()
        self.assertIn("Publication mode", output)
        self.assertIn("publish_live", output)
        self.assertIn("Target route", output)
        self.assertIn("wordpress:ml_report", output)
        self.assertIn("Post ID", output)
        self.assertIn("123", output)
        self.assertIn("https://example.com/cross-report", output)

    def test_ingest_wires_settings_and_orchestrator(self) -> None:
        # Avoid importing heavy dependencies during test import.
        dummy_fitz = types.ModuleType("fitz")
        with patch.dict(sys.modules, {"fitz": dummy_fitz}):
            import src.cli as cli

        settings = AppSettings(
            schema_version="1.0",
            google_sa_path="sa.json",
            gdrive_folder_id="folder",
            openai_api_key="key",
            openai_model="gpt-5",
            batch_limit=5,
            output_dir="./out",
            cache_dir="./cache",
            state_db="./state/index.sqlite",
            reports_db="./state/reports.sqlite",
            publisher_profiles_path="./Wordpress/config/publisher-profiles.json",
            category_mapping_path="./src/config/category-mappings.yaml",
            cover_style_path="./src/config/cover-styles.yaml",
            ingest_lock_path="./state/ingest.lock",
            ingest_lock_ttl_seconds=7200.0,
            temperature=1.0,
            cost_ledger_path="./out/cost-ledger.jsonl",
            cost_daily_path="./out/cost-daily.json",
            model_pricing={},
        )
        outcomes = [
            IngestOutcome(
                schema_version="1.0",
                file_id="file",
                name="name.pdf",
                md5="md5",
                html_path="out/name.html",
                status="processed",
            )
        ]

        with patch.object(
            cli, "load_settings", return_value=settings
        ) as load_settings_mock:
            with patch.object(
                cli, "run_ingest", return_value=outcomes
            ) as run_ingest_mock:
                cli.ingest(folder=None, limit=1)
                load_settings_mock.assert_called_once()
                run_ingest_mock.assert_called_once()
                passed_settings = run_ingest_mock.call_args.args[0]
                passed_ctx = run_ingest_mock.call_args.kwargs.get("ctx")
                self.assertIs(passed_ctx, load_settings_mock.call_args.args[1])
                self.assertIsInstance(passed_settings, IngestSettings)
                self.assertEqual("folder", passed_settings.gdrive_folder_id)
                self.assertEqual("gpt-5", passed_settings.openai_model)

    def test_publish_wires_settings_and_orchestrator(self) -> None:
        import src.cli as cli

        settings = PublishSettings(
            schema_version="1.0",
            output_dir="./out",
            state_db="./state/index.sqlite",
            reports_db="./state/reports.sqlite",
            category_mapping_path="./src/config/category-mappings.yaml",
            wp=WordPressAuthSettings(
                schema_version="1.0",
                site_url="https://example.com",
                username="user",
                app_password="pass",
                bearer_token=None,
                post_status="publish",
                post_type="ml_report",
            ),
        )
        outcomes = [
            PublishOutcome(
                schema_version="1.0",
                html_path="out/name.html",
                file_id="file",
                status="published",
                post_id=123,
                post_url="https://example.com/post",
            )
        ]

        with patch.object(
            cli, "load_publish_settings", return_value=settings
        ) as load_settings_mock:
            with patch.object(
                cli, "run_publish", return_value=outcomes
            ) as run_publish_mock:
                cli.publish_wp(limit=1)
                load_settings_mock.assert_called_once()
                run_publish_mock.assert_called_once()
                passed_settings = run_publish_mock.call_args.args[0]
                self.assertIsInstance(passed_settings, PublishSettings)

    def test_cost_report_wires_service(self) -> None:
        import src.cli as cli

        settings = AppSettings(
            schema_version="1.0",
            google_sa_path="sa.json",
            gdrive_folder_id="folder",
            openai_api_key="key",
            openai_model="gpt-5",
            batch_limit=5,
            output_dir="./out",
            cache_dir="./cache",
            state_db="./state/index.sqlite",
            reports_db="./state/reports.sqlite",
            publisher_profiles_path="./Wordpress/config/publisher-profiles.json",
            category_mapping_path="./src/config/category-mappings.yaml",
            cover_style_path="./src/config/cover-styles.yaml",
            ingest_lock_path="./state/ingest.lock",
            ingest_lock_ttl_seconds=7200.0,
            temperature=1.0,
            cost_ledger_path="./out/cost-ledger.jsonl",
            cost_daily_path="./out/cost-daily.json",
            model_pricing={},
        )
        response = CostReportResponse(
            schema_version="1.0",
            filter_type="date",
            filter_value="2026-01-01",
            totals=CostTotals(
                schema_version="1.0",
                total_input_tokens=100,
                total_output_tokens=50,
                total_tool_calls=1,
                estimated_cost_usd=0.01,
            ),
            top_steps=[
                StepCostTotal(
                    schema_version="1.0",
                    step_name="openai_analyze",
                    total_input_tokens=100,
                    total_output_tokens=50,
                    total_tool_calls=1,
                    estimated_cost_usd=0.01,
                )
            ],
            matched_entries=1,
        )

        with patch.object(
            cli, "load_settings", return_value=settings
        ) as load_settings_mock:
            with patch.object(
                cli,
                "run_cost_reporting",
                return_value=type(
                    "CostReporting", (), {"report": response, "rollup": None}
                )(),
            ) as reporting_mock:
                with patch.object(cli.console, "print"):
                    cli.cost_report(date="2026-01-01", run_id=None, top=1)
        load_settings_mock.assert_called_once()
        reporting_mock.assert_called_once()
        request = reporting_mock.call_args.args[0].report_request
        self.assertIsNotNone(request)
        self.assertEqual("2026-01-01", request.date_utc)
        self.assertEqual(1, request.top_n)
        self.assertIsNone(request.run_id)

    def test_download_report_wires_settings_and_orchestrator(self) -> None:
        import src.cli as cli

        settings = BrowserDownloadSettings(
            schema_version="1.0",
            openrouter_api_key="key",
            model="openai/gpt-5-mini",
            temperature=0.0,
            timeout_seconds=45.0,
            max_steps=12,
            output_dir="./out/browser_downloads",
            state_db="./state/index.sqlite",
            reports_db="./state/reports.sqlite",
            identity_config_path="./src/config/browser_download_identity.yaml",
            identity_profile=BrowserDownloadIdentity(
                schema_version="1.0",
                fields=[
                    BrowserDownloadIdentityField(
                        schema_version="1.0",
                        key="work_email",
                        label="Work email",
                        value="ops@example.com",
                        aliases=["email"],
                    )
                ],
            ),
            openrouter_http_referer="https://marketlense.local",
            headed=False,
            retry_retries=1,
            retry_base_delay_seconds=1.0,
            retry_backoff_step_seconds=0.0,
            retry_jitter_seconds=0.0,
        )
        result = ReportDownloadOrchestratorResult(
            schema_version="1.0",
            source_url="https://example.com/report",
            normalized_url="https://example.com/report",
            route_kind="pdf_download",
            route_family="direct_pdf_probe",
            route_status="verified",
            outcome="downloaded",
            route_summary="Click the report download button.",
            final_page_url="https://example.com/report/final",
            resolved_target_url="https://example.com/report/final",
            used_memory_route=False,
            route_steps=[
                BrowserDownloadRouteStep(
                    schema_version="1.0",
                    index=0,
                    action="open",
                    target_text="https://example.com/report",
                    target_role="url",
                    target_url="https://example.com/report",
                    result="downloaded",
                )
            ],
            confirmation_evidence=BrowserDownloadConfirmationEvidence(
                schema_version="1.0",
                url_changed=False,
                visible_confirmation_text="",
                submit_button_state="unchanged",
                form_disappeared=False,
                final_page_url="https://example.com/report/final",
            ),
            terminal_evidence=DownloadTerminalEvidence(
                schema_version="1.0",
                final_page_url="https://example.com/report/final",
                final_page_title="",
                terminal_text_excerpt="",
                artifact_url="https://example.com/report/final",
                artifact_kind="pdf",
                artifact_validation_status="verified",
                artifact_validation_detail="",
                confirmation_signal_count=0,
                traversed_page_urls=["https://example.com/report/final"],
            ),
            browser_had_structured_result=False,
            used_candidate_pdf_url=False,
            used_candidate_source_page=False,
            encountered_form_fields=["Email", "Business"],
            identity_fields_added=["business"],
            blocked_reason=None,
            blocked_reason_detail=None,
            downloaded_file_path="./out/browser_downloads/report.pdf",
            downloaded_file_name="report.pdf",
            downloaded_mime_type="application/pdf",
            downloaded_size_bytes=128,
            onsite_capture_path=None,
            onsite_capture_format=None,
            onsite_page_count=None,
            onsite_completeness_status=None,
        )

        with patch.object(
            cli, "load_browser_download_settings", return_value=settings
        ) as load_settings_mock:
            with patch.object(
                cli, "run_report_download", return_value=result
            ) as run_download_mock:
                with patch.object(cli.console, "print"):
                    cli.download_report(
                        url="https://example.com/report",
                        delivery_email=None,
                    )

        load_settings_mock.assert_called_once()
        run_download_mock.assert_called_once()
        request = run_download_mock.call_args.args[0]
        self.assertEqual("https://example.com/report", request.url)
        self.assertEqual("./state/index.sqlite", request.state_db)
        self.assertEqual("./state/reports.sqlite", request.reports_db)
        self.assertEqual("openai/gpt-5-mini", request.settings.model)

    def test_browser_doctor_wires_developer_diagnostic_service(self) -> None:
        import src.cli as cli

        result = BrowserDeveloperDiagnosticsResult(
            schema_version="1.0",
            status="ok",
            profile_path="out/browser_doctor/profile",
            downloads_path="out/browser_doctor/downloads",
            cdp_url="http://127.0.0.1:9222",
            active_tab_url="https://example.com/browser-doctor",
            active_tab_title="Browser Doctor",
            browser_use_connected=True,
            cdp_available=True,
            real_tab_available=True,
            cleanup_attempted=True,
            cleanup_status="ok",
            verification_tab_activated=True,
            keep_browser_open=False,
            checks=(
                BrowserDeveloperDiagnosticCheck(
                    schema_version="1.0",
                    name="browser_use_connectivity",
                    status="ok",
                    message="connected",
                ),
            ),
        )

        with patch.object(
            cli,
            "run_browser_developer_diagnostics",
            return_value=result,
        ) as diagnostics_mock:
            with patch.object(cli.console, "print"):
                cli.browser_doctor(
                    profile_dir="out/browser_doctor/profile",
                    downloads_dir="out/browser_doctor/downloads",
                    verification_url="https://example.com/browser-doctor",
                    cdp_url="",
                    headed=False,
                    keep_browser_open=False,
                    json_output=True,
                    timeout_seconds=5.0,
                    reuse_session_key="doctor-key",
                    reuse_publisher_scope="example.com",
                    reuse_ttl_seconds=120.0,
                    reuse_base_dir="out/browser_doctor/reuse",
                )

        diagnostics_mock.assert_called_once()
        request = diagnostics_mock.call_args.args[0]
        self.assertEqual("out/browser_doctor/profile", request.profile_path)
        self.assertEqual("out/browser_doctor/downloads", request.downloads_path)
        self.assertEqual("https://example.com/browser-doctor", request.verification_url)
        self.assertTrue(request.cleanup_stale_once)
        self.assertTrue(request.activate_verification_tab)
        self.assertEqual(5.0, request.timeout_seconds)
        self.assertEqual(
            BrowserDownloadSessionReusePolicy(
                schema_version="1.0",
                enabled=True,
                mode="developer_canary",
                session_key="doctor-key",
                publisher_scope="example.com",
                ttl_seconds=120.0,
                base_dir="out/browser_doctor/reuse",
                cleanup_expired=True,
                allow_cross_publisher=False,
            ),
            request.session_reuse_policy,
        )

    def test_promote_private_api_playbook_accepts_typed_request_and_writes_file(
        self,
    ) -> None:
        import src.cli as cli

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            playbook_dir = root / "playbooks"
            request_path = root / "private-api-promotion.json"
            request_path.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "playbook_dir": str(playbook_dir),
                        "source_url": "https://example.com/research/report-2026",
                        "route_family": "browser_pdf_click",
                        "route_kind": "pdf_download",
                        "endpoint_pattern": "/api/reports/{last_path_segment}",
                        "method": "GET",
                        "request_shape_summary": (
                            "GET with report slug path parameter; no auth headers."
                        ),
                        "response_pdf_url_json_pointer": "/asset/pdfUrl",
                        "validated_success_count": 2,
                        "fallback_route_family": "browser_pdf_click",
                        "expected_status_codes": [200],
                        "required_response_markers": ["pdfUrl"],
                        "evidence_labels": ["network_document_request"],
                        "observed_at": "2026-05-06T12:00:00+00:00",
                    }
                ),
                encoding="utf-8",
            )

            cli.promote_private_api_playbook(
                request_json=str(request_path),
                json_output=True,
            )

            path = (
                playbook_dir
                / "private_api"
                / "private-api-example-com-pdf-download.yaml"
            )
            payload = yaml.safe_load(path.read_text(encoding="utf-8"))

        self.assertEqual("private-api-example-com-pdf-download", payload["playbook_id"])
        self.assertEqual("1.0.0", payload["version"])
        self.assertEqual(
            "validated_private_api_evidence_promotion",
            payload["history"][0]["source"],
        )
        self.assertEqual(2, payload["private_api_evidence"][0]["success_count"])
        self.assertEqual(
            "/asset/pdfUrl",
            payload["private_api_evidence"][0]["response_pdf_url_json_pointer"],
        )

    def test_sync_publishers_wires_settings_and_orchestrator(self) -> None:
        import src.cli as cli

        settings = AppSettings(
            schema_version="1.0",
            google_sa_path="sa.json",
            gdrive_folder_id="folder",
            openai_api_key="key",
            openai_model="gpt-5",
            batch_limit=5,
            output_dir="./out",
            cache_dir="./cache",
            state_db="./state/index.sqlite",
            reports_db="./state/reports.sqlite",
            publisher_profiles_path="./Wordpress/config/publisher-profiles.json",
            category_mapping_path="./src/config/category-mappings.yaml",
            cover_style_path="./src/config/cover-styles.yaml",
            ingest_lock_path="./state/ingest.lock",
            ingest_lock_ttl_seconds=7200.0,
            temperature=1.0,
            cost_ledger_path="./out/cost-ledger.jsonl",
            cost_daily_path="./out/cost-daily.json",
            model_pricing={},
        )
        result = type(
            "PublisherSyncResult",
            (),
            {
                "snapshot_path": "./Wordpress/config/publisher-profiles.json",
                "reports_db": "./state/reports.sqlite",
                "source_page_url": "https://www.notion.so/87c35358a78c4afc9eb7451dc1ade33d",
                "replaced_count": 83,
            },
        )()

        with patch.object(cli, "load_settings", return_value=settings) as load_mock:
            with patch.object(
                cli, "run_publisher_sync", return_value=result
            ) as sync_mock:
                with patch.object(cli.console, "print"):
                    cli.sync_publishers(snapshot_path=None)

        load_mock.assert_called_once()
        sync_mock.assert_called_once()
        request = sync_mock.call_args.args[0]
        self.assertEqual(
            "./Wordpress/config/publisher-profiles.json", request.snapshot_path
        )
        self.assertEqual("./state/reports.sqlite", request.reports_db)

    def test_audit_acquisition_paths_wires_settings_and_orchestrator(self) -> None:
        import src.cli as cli

        app_settings = AppSettings(
            schema_version="1.0",
            google_sa_path="sa.json",
            gdrive_folder_id="folder",
            openai_api_key="key",
            openai_model="gpt-5",
            batch_limit=5,
            output_dir="./out",
            cache_dir="./cache",
            state_db="./state/index.sqlite",
            reports_db="./state/reports.sqlite",
            publisher_profiles_path="./Wordpress/config/publisher-profiles.json",
            category_mapping_path="./src/config/category-mappings.yaml",
            cover_style_path="./src/config/cover-styles.yaml",
            ingest_lock_path="./state/ingest.lock",
            ingest_lock_ttl_seconds=7200.0,
            temperature=1.0,
            cost_ledger_path="./out/cost-ledger.jsonl",
            cost_daily_path="./out/cost-daily.json",
            model_pricing={},
        )
        inventory_settings = PublisherInventorySettings(
            schema_version="1.0",
            openrouter_api_key="key",
            model="gpt-5-mini",
            temperature=0.0,
            timeout_seconds=45.0,
            max_steps=12,
            output_dir="./out/publisher_inventory_discovery",
            reports_db="./state/reports.sqlite",
            google_sa_path="./sa.json",
            prompt_namespace="publisher_inventory/discovery",
            pagination_max_pages=10,
            http_timeout_seconds=30.0,
            openrouter_http_referer=None,
            headed=False,
            retry_retries=1,
            retry_base_delay_seconds=1.0,
            retry_backoff_step_seconds=0.0,
            retry_jitter_seconds=0.0,
            openai_api_key="openai-key",
            candidate_screening_enabled=True,
            candidate_screening_model="gpt-5-nano",
            candidate_screening_temperature=1.0,
            candidate_screening_timeout_seconds=30.0,
            candidate_screening_prompt_namespace="publisher_inventory/meaningful_candidate_screen",
        )
        browser_settings = BrowserDownloadSettings(
            schema_version="1.0",
            openrouter_api_key="key",
            model="openai/gpt-5-mini",
            temperature=0.0,
            timeout_seconds=45.0,
            max_steps=12,
            output_dir="./out/browser_downloads",
            state_db="./state/index.sqlite",
            reports_db="./state/reports.sqlite",
            identity_config_path="./src/config/browser_download_identity.yaml",
            identity_profile=BrowserDownloadIdentity(
                schema_version="1.0",
                fields=[
                    BrowserDownloadIdentityField(
                        schema_version="1.0",
                        key="work_email",
                        label="Work email",
                        value="ops@example.com",
                        aliases=["email"],
                    )
                ],
            ),
            openrouter_http_referer=None,
            headed=False,
            retry_retries=1,
            retry_base_delay_seconds=1.0,
            retry_backoff_step_seconds=0.0,
            retry_jitter_seconds=0.0,
        )
        result = AcquisitionAuditBatchResult(
            schema_version="1.0",
            generated_at_utc="2026-04-04T12:00:00Z",
            output_path="./out/acquisition_audit/report.json",
            publisher_count=1,
            candidate_count=1,
            publishers=[
                AcquisitionAuditPublisherSummary(
                    schema_version="1.0",
                    publisher_name="Activate Consulting",
                    insights_url="https://www.activate.com/insights",
                    discovery_route_kind="browser_render",
                    discovery_quality_band="high",
                    recommended_discovery_route_kind="browser_render",
                    recommended_publisher_flow="publisher_prefers_pdf_download",
                    recommendation_reason="All candidates downloaded.",
                    current_candidate_count=1,
                    downloaded_count=1,
                    email_requested_count=0,
                    email_required_count=0,
                    failed_count=0,
                    discovery_provenance_counts={"browser_dom": 1},
                    acquisition_route_counts={"pdf_download": 1},
                    acquisition_outcome_counts={"downloaded": 1},
                )
            ],
            candidates=[
                AcquisitionAuditCandidateResult(
                    schema_version="1.0",
                    publisher_name="Activate Consulting",
                    publisher_insights_url="https://www.activate.com/insights",
                    publisher_discovery_route_kind="browser_render",
                    publisher_recommended_discovery_route_kind="browser_render",
                    report_url="https://www.activate.com/reports/direct.pdf",
                    report_title="Direct Report",
                    discovered_on_page_number=1,
                    source_page_urls=["https://www.activate.com/insights"],
                    discovery_provenances=["browser_dom"],
                    acquisition_route_kind="pdf_download",
                    acquisition_outcome="downloaded",
                    recommended_report_flow="automate_pdf_download",
                    recommendation_reason="Downloaded successfully.",
                    acquisition_route_summary="Download the PDF.",
                    acquisition_final_page_url="https://www.activate.com/reports/direct.pdf",
                    encountered_form_fields=[],
                    downloaded_file_path="./out/downloads/direct.pdf",
                )
            ],
        )

        with patch.object(cli, "load_settings", return_value=app_settings) as load_app:
            with patch.object(
                cli,
                "load_publisher_inventory_settings",
                return_value=inventory_settings,
            ) as load_inventory:
                with patch.object(
                    cli, "load_browser_download_settings", return_value=browser_settings
                ) as load_browser:
                    with patch.object(
                        cli, "run_acquisition_audit", return_value=result
                    ) as run_audit:
                        with patch.object(cli.console, "print"):
                            cli.audit_acquisition_paths(
                                publisher_limit=2,
                                candidate_limit_per_publisher=3,
                                delivery_email="ops@example.com",
                            )

        load_app.assert_called_once()
        load_inventory.assert_called_once()
        load_browser.assert_called_once()
        run_audit.assert_called_once()
        request = run_audit.call_args.args[0]
        self.assertEqual("./state/reports.sqlite", request.reports_db)
        self.assertEqual("./out", request.output_dir)
        self.assertEqual(2, request.publisher_limit)
        self.assertEqual(3, request.candidate_limit_per_publisher)
        self.assertEqual("ops@example.com", request.delivery_email)

    def test_discover_publisher_inventory_wires_settings_and_orchestrator(self) -> None:
        import src.cli as cli

        settings = PublisherInventorySettings(
            schema_version="1.0",
            openrouter_api_key="key",
            model="gpt-5-mini",
            temperature=0.0,
            timeout_seconds=45.0,
            max_steps=12,
            output_dir="./out/publisher_inventory_discovery",
            reports_db="./state/reports.sqlite",
            google_sa_path="./sa.json",
            prompt_namespace="publisher_inventory/discovery",
            pagination_max_pages=10,
            http_timeout_seconds=30.0,
            openrouter_http_referer=None,
            headed=False,
            retry_retries=1,
            retry_base_delay_seconds=1.0,
            retry_backoff_step_seconds=0.0,
            retry_jitter_seconds=0.0,
            openai_api_key="openai-key",
            candidate_screening_enabled=True,
            candidate_screening_model="gpt-5-nano",
            candidate_screening_temperature=1.0,
            candidate_screening_timeout_seconds=30.0,
            candidate_screening_prompt_namespace="publisher_inventory/meaningful_candidate_screen",
        )
        result = PublisherInventoryDiscoveryResult(
            schema_version="1.0",
            publisher_name="Activate Consulting",
            insights_url="https://www.activate.com/insights",
            normalized_insights_url="https://www.activate.com/insights",
            new_report_urls=[
                PublisherInventoryDiffItem(
                    schema_version="1.0",
                    canonical_url="https://www.activate.com/reports/new-report",
                    title="New Report",
                    discovered_on_page_number=2,
                )
            ],
            current_report_count=10,
            previous_report_count=9,
            used_memory_route=True,
            snapshot_changed=True,
            run_quality_summary=PublisherInventoryRunQualitySummary(
                schema_version="1.0",
                outcome="accepted",
                status="passed",
                quality_band="high",
                route_kind="browser_render",
                recommended_route_kind="browser_render",
                used_memory_route=True,
                page_count=2,
                raw_candidate_count=10,
                current_report_count=10,
                previous_report_count=9,
                raw_new_report_count=1,
                screened_new_report_count=1,
                qualified_new_report_count=1,
                snapshot_changed=True,
                requires_review=False,
                recommended_route_reason="The latest run quality supports reusing the same primary route kind.",
                summary="high quality via browser_render: 10 current items, 1 raw deltas, 1 qualified deltas, coverage verdict accepted.",
                candidate_provenance_counts={"browser_dom": 10},
            ),
        )

        with patch.object(
            cli, "load_publisher_inventory_settings", return_value=settings
        ) as load_mock:
            with patch.object(
                cli, "run_publisher_inventory_discovery", return_value=result
            ) as discover_mock:
                with patch.object(cli.console, "print"):
                    cli.discover_publisher_inventory(
                        insights_url="https://www.activate.com/insights"
                    )

        load_mock.assert_called_once()
        discover_mock.assert_called_once()
        request = discover_mock.call_args.args[0]
        self.assertEqual("https://www.activate.com/insights", request.insights_url)
        self.assertEqual("./state/reports.sqlite", request.reports_db)
        self.assertEqual("gpt-5-mini", request.settings.model)

    def test_discover_publisher_inventory_treats_pagination_limit_as_bounded(
        self,
    ) -> None:
        import src.cli as cli

        settings = PublisherInventorySettings(
            schema_version="1.0",
            openrouter_api_key="key",
            model="gpt-5-mini",
            temperature=0.0,
            timeout_seconds=45.0,
            max_steps=12,
            output_dir="./out/publisher_inventory_discovery",
            reports_db="./state/reports.sqlite",
            google_sa_path="./sa.json",
            prompt_namespace="publisher_inventory/discovery",
            pagination_max_pages=10,
            http_timeout_seconds=30.0,
            openrouter_http_referer=None,
            headed=False,
            retry_retries=1,
            retry_base_delay_seconds=1.0,
            retry_backoff_step_seconds=0.0,
            retry_jitter_seconds=0.0,
            openai_api_key="openai-key",
            candidate_screening_enabled=True,
            candidate_screening_model="gpt-5-nano",
            candidate_screening_temperature=1.0,
            candidate_screening_timeout_seconds=30.0,
            candidate_screening_prompt_namespace="publisher_inventory/meaningful_candidate_screen",
        )

        with patch.object(
            cli, "load_publisher_inventory_settings", return_value=settings
        ) as load_mock:
            with patch.object(
                cli,
                "run_publisher_inventory_discovery",
                side_effect=AppError(
                    code="publisher_inventory_browser_pagination_limit",
                    message="bounded crawl limit reached",
                    retryable=False,
                    severity="warning",
                ),
            ) as discover_mock:
                with patch.object(cli.console, "print") as print_mock:
                    cli.discover_publisher_inventory(
                        insights_url="https://www.askattest.com/insights-teams"
                    )

        load_mock.assert_called_once()
        discover_mock.assert_called_once()
        self.assertGreaterEqual(print_mock.call_count, 1)

    def test_drive_oauth_login_wires_service(self) -> None:
        import src.cli as cli

        result = type(
            "DriveOAuthAuthorizeResult",
            (),
            {
                "token_output_path": "./google_oauth_token.json",
                "scopes": ["https://www.googleapis.com/auth/drive"],
                "refresh_token_present": True,
            },
        )()

        with patch.object(
            cli, "authorize_oauth_user", return_value=result
        ) as authorize_mock:
            with patch.object(cli.console, "print"):
                cli.drive_oauth_login(
                    client_json="./google_oauth_client.json",
                    token_json="./google_oauth_token.json",
                    open_browser=True,
                    port=0,
                )

        authorize_mock.assert_called_once()
        request = authorize_mock.call_args.args[0]
        self.assertEqual("./google_oauth_client.json", request.client_secret_path)
        self.assertEqual("./google_oauth_token.json", request.token_output_path)
        self.assertTrue(request.open_browser)

    def test_replay_run_uses_default_registry_and_orchestrator(self) -> None:
        import src.cli as cli

        settings = AppSettings(
            schema_version="1.0",
            google_sa_path="sa.json",
            gdrive_folder_id="folder",
            openai_api_key="key",
            openai_model="gpt-5",
            batch_limit=5,
            output_dir="./out",
            cache_dir="./cache",
            state_db="./state/index.sqlite",
            reports_db="./state/reports.sqlite",
            publisher_profiles_path="./Wordpress/config/publisher-profiles.json",
            category_mapping_path="./src/config/category-mappings.yaml",
            cover_style_path="./src/config/cover-styles.yaml",
            ingest_lock_path="./state/ingest.lock",
            ingest_lock_ttl_seconds=7200.0,
            temperature=1.0,
            cost_ledger_path="./out/cost-ledger.jsonl",
            cost_daily_path="./out/cost-daily.json",
            model_pricing={},
        )
        response = UiRunReplayResponse(
            schema_version="1.0",
            original_record=UiRunRecord(
                schema_version="1.0",
                run_id="run-1",
                run_type="report_download",
                display_name="Report download",
                status="succeeded",
                request_payload={"url": "https://example.com/report.pdf"},
                command=["python", "-m", "src.cli", "ui-run-worker"],
                created_at_utc="2026-04-23T10:00:00+00:00",
                updated_at_utc="2026-04-23T10:00:05+00:00",
                artifact_paths=[],
                result_summary={},
            ),
            manifest_path="./state/ui_runs/run-1/replay_manifest.json",
            report_path="./state/ui_runs/run-1/replays/report.json",
            report=UiRunReplayReport(
                schema_version="1.0",
                run_id="run-1",
                replayed_at_utc="2026-04-23T10:00:06+00:00",
                replay_status="succeeded",
                source_fingerprint_match=True,
                prompt_fingerprint_match=True,
                config_fingerprint_match=True,
                deltas=[],
                matched=True,
            ),
        )

        with patch.object(cli, "load_settings", return_value=settings) as load_mock:
            with patch.object(
                cli,
                "default_ui_run_registry_path",
                return_value="./state/ui_runs.sqlite",
            ) as default_registry_mock:
                with patch.object(
                    cli, "replay_ui_run", return_value=response
                ) as replay_mock:
                    with patch.object(cli.console, "print"):
                        cli.replay_run(run_id="run-1", registry_path=None)

        load_mock.assert_called_once()
        default_registry_mock.assert_called_once_with("./state/index.sqlite")
        replay_mock.assert_called_once()
        request = replay_mock.call_args.args[0]
        self.assertEqual("./state/ui_runs.sqlite", request.registry_path)
        self.assertEqual("run-1", request.run_id)

    def test_replay_run_exits_nonzero_when_replay_differs(self) -> None:
        import src.cli as cli

        response = UiRunReplayResponse(
            schema_version="1.0",
            original_record=UiRunRecord(
                schema_version="1.0",
                run_id="run-1",
                run_type="report_download",
                display_name="Report download",
                status="succeeded",
                request_payload={"url": "https://example.com/report.pdf"},
                command=["python", "-m", "src.cli", "ui-run-worker"],
                created_at_utc="2026-04-23T10:00:00+00:00",
                updated_at_utc="2026-04-23T10:00:05+00:00",
                artifact_paths=[],
                result_summary={},
            ),
            manifest_path="./state/ui_runs/run-1/replay_manifest.json",
            report_path="./state/ui_runs/run-1/replays/report.json",
            report=UiRunReplayReport(
                schema_version="1.0",
                run_id="run-1",
                replayed_at_utc="2026-04-23T10:00:06+00:00",
                replay_status="blocked_drift",
                source_fingerprint_match=False,
                prompt_fingerprint_match=True,
                config_fingerprint_match=True,
                deltas=[],
                matched=False,
            ),
        )

        with patch.object(cli, "replay_ui_run", return_value=response):
            with patch.object(cli.console, "print"):
                with self.assertRaises(click.exceptions.Exit) as exc_info:
                    cli.replay_run(
                        run_id="run-1", registry_path="./state/ui_runs.sqlite"
                    )

        self.assertEqual(1, exc_info.exception.exit_code)

    def test_ui_run_worker_preserves_failed_execution_error_code(self) -> None:
        import src.cli as cli

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            registry_path = str((tmp_path / "state" / "ui_runs.sqlite").resolve())
            request_path = tmp_path / "request.json"
            worker_request_payload = {
                "schema_version": "1.0",
                "registry_path": registry_path,
                "run_id": "run-worker",
                "run_type": "publisher_discovery",
                "request_payload": {"insights_url": "https://example.com/insights"},
            }
            request_path.write_text(
                json.dumps(worker_request_payload), encoding="utf-8"
            )
            cli.write_ui_run_record(
                cli.UiRunRecordWriteRequest(
                    schema_version="1.0",
                    registry_path=registry_path,
                    record=UiRunRecord(
                        schema_version="1.0",
                        run_id="run-worker",
                        run_type="publisher_discovery",
                        display_name="Publisher discovery",
                        status="queued",
                        request_payload={
                            "insights_url": "https://example.com/insights"
                        },
                        command=["python", "-m", "src.cli", "ui-run-worker"],
                        created_at_utc="2026-04-29T10:00:00+00:00",
                        updated_at_utc="2026-04-29T10:00:00+00:00",
                        output_path=str(tmp_path / "output.log"),
                        request_path=str(request_path),
                    ),
                ),
                cli.new_run_context(task_id="seed_ui_run_record"),
            )

            with patch.object(
                cli,
                "execute_ui_run",
                return_value=UiRunExecutionResponse(
                    schema_version="1.0",
                    run_id="run-worker",
                    run_type="publisher_discovery",
                    status="failed",
                    result_summary={},
                    artifact_paths=[],
                    config_snapshot={"run_type": "publisher_discovery"},
                    config_fingerprint="cfg",
                    error_code="publisher_inventory_browser_timeout",
                    error_message="Timed out",
                    error_retryable=True,
                    error_severity="error",
                ),
            ):
                with patch.object(cli, "setup_logging"):
                    with self.assertRaises(click.exceptions.Exit) as exc_info:
                        cli.ui_run_worker(request_json=str(request_path))

            self.assertEqual(1, exc_info.exception.exit_code)
            stored = cli.get_ui_run_record(
                cli.UiRunRecordGetRequest(
                    schema_version="1.0",
                    registry_path=registry_path,
                    run_id="run-worker",
                ),
                cli.new_run_context(task_id="load_ui_run_record"),
            ).record

            self.assertEqual("failed", stored.status)
            self.assertEqual("publisher_inventory_browser_timeout", stored.error_code)
            self.assertTrue(stored.error_retryable)


if __name__ == "__main__":
    unittest.main()
