import sys
import types
import unittest
from unittest.mock import patch

import click

from src.contracts.browser_download import (
    BrowserDownloadConfirmationEvidence,
    BrowserDownloadIdentity,
    BrowserDownloadIdentityField,
    BrowserDownloadRouteStep,
    BrowserDownloadSettings,
    DownloadTerminalEvidence,
    ReportDownloadOrchestratorResult,
)
from src.contracts.ui_run_control import UiRunRecord
from src.contracts.ui_run_replay import UiRunReplayReport, UiRunReplayResponse
from src.contracts.acquisition_audit import (
    AcquisitionAuditBatchResult,
    AcquisitionAuditCandidateResult,
    AcquisitionAuditPublisherSummary,
)
from src.contracts.config import AppSettings
from src.contracts.costs import CostReportResponse, CostTotals, StepCostTotal
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


class TestCli(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
