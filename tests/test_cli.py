import sys
import types
import unittest
from unittest.mock import patch

from src.contracts.browser_download import (
    BrowserDownloadIdentity,
    BrowserDownloadIdentityField,
    BrowserDownloadSettings,
    ReportDownloadOrchestratorResult,
)
from src.contracts.config import AppSettings
from src.contracts.costs import CostReportResponse, CostTotals, StepCostTotal
from src.contracts.ingest import IngestOutcome, IngestSettings
from src.contracts.publisher_inventory import (
    PublisherInventoryDiffItem,
    PublisherInventoryDiscoveryResult,
    PublisherInventorySettings,
)
from src.contracts.publish import PublishOutcome, PublishSettings
from src.contracts.wordpress import WordPressAuthSettings


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
            outcome="downloaded",
            route_summary="Click the report download button.",
            final_page_url="https://example.com/report/final",
            used_memory_route=False,
            encountered_form_fields=["Email", "Business"],
            identity_fields_added=["business"],
            downloaded_file_path="./out/browser_downloads/report.pdf",
            downloaded_file_name="report.pdf",
            downloaded_mime_type="application/pdf",
            downloaded_size_bytes=128,
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
        self.assertEqual("./Wordpress/config/publisher-profiles.json", request.snapshot_path)
        self.assertEqual("./state/reports.sqlite", request.reports_db)

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


if __name__ == "__main__":
    unittest.main()
