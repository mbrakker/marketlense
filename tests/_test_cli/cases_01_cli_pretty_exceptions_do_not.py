# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403


class TestCli01CliPrettyExceptionsDo(unittest.TestCase):
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
                    with self.assertRaises(typer.Exit) as exc_info:
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
                    with self.assertRaises(typer.Exit) as exc_info:
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
                    post_url="https://example.com/briefings/ai-commerce-across-reports/",
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
        self.assertIn("wordpress:ml_briefing", output)
        self.assertIn("Target post type", output)
        self.assertIn("ml_briefing", output)
        self.assertIn("Target slug", output)
        self.assertIn("ai-commerce-across-reports", output)
        self.assertIn("Categories", output)
        self.assertIn("retail", output)
        self.assertIn("Tags", output)
        self.assertIn("ai", output)
        self.assertIn("Taxonomy terms", output)
        self.assertIn("publisher-a", output)
        self.assertIn("Post ID", output)
        self.assertIn("123", output)
        self.assertIn(
            "https://example.com/briefings/ai-commerce-across-reports/", output
        )

    def test_ingest_report_cards_flag_wires_settings_and_orchestrator(self) -> None:
        # Avoid importing heavy dependencies during test import.
        dummy_fitz = types.ModuleType("fitz")
        with patch.dict(sys.modules, {"fitz": dummy_fitz}):
            import src.cli as cli
            import src._cli.pipeline as pipeline

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
                cli,
                "_resolve_cli_workflow_control",
                return_value={
                    "workflow": "report_generation",
                    "preflight_profile": "report_generation",
                    "retry_policy_id": "report_generation.report_pipeline.v1",
                },
            ) as workflow_mock:
                with patch.object(
                    cli, "run_ingest", return_value=outcomes
                ) as run_ingest_mock:
                    with patch.object(
                        cli, "write_workflow_control_observation"
                    ) as feedback_mock:
                        cli.ingest(folder=None, limit=1, force_report_cards=False)
                        load_settings_mock.assert_called_once()
                        workflow_mock.assert_called_once()
                        self.assertEqual(
                            "ingest new reports",
                            workflow_mock.call_args.kwargs["intent"],
                        )
                        run_ingest_mock.assert_called_once()
                        feedback_mock.assert_called_once()
                        feedback_request = feedback_mock.call_args.args[0]
                        self.assertEqual(
                            "./state/index.sqlite", feedback_request.state_db
                        )
                        self.assertEqual(
                            "report_generation",
                            feedback_request.observation.workflow,
                        )
                        self.assertEqual(
                            "succeeded", feedback_request.observation.outcome
                        )
                        passed_settings = run_ingest_mock.call_args.args[0]
                        passed_ctx = run_ingest_mock.call_args.kwargs.get("ctx")
                        self.assertFalse(
                            run_ingest_mock.call_args.kwargs.get("force_report_cards")
                        )
                        self.assertIs(passed_ctx, load_settings_mock.call_args.args[1])
                        self.assertIsInstance(passed_settings, IngestSettings)
                        self.assertEqual("folder", passed_settings.gdrive_folder_id)
                        self.assertEqual("gpt-5", passed_settings.openai_model)

                        cli.ingest(folder=None, limit=1, force_report_cards=True)
                        self.assertEqual(2, run_ingest_mock.call_count)
                        self.assertTrue(
                            run_ingest_mock.call_args.kwargs.get("force_report_cards")
                        )

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
                cli,
                "_resolve_cli_workflow_control",
                return_value={
                    "workflow": "publishing",
                    "preflight_profile": "publishing",
                    "retry_policy_id": "publishing.wordpress_publish.v1",
                },
            ) as workflow_mock:
                with patch.object(
                    cli, "run_publish", return_value=outcomes
                ) as run_publish_mock:
                    with patch.object(
                        cli, "write_workflow_control_observation"
                    ) as feedback_mock:
                        cli.publish_wp(limit=1)
                        load_settings_mock.assert_called_once()
                        workflow_mock.assert_called_once()
                        self.assertEqual(
                            "publish ready reports",
                            workflow_mock.call_args.kwargs["intent"],
                        )
                        run_publish_mock.assert_called_once()
                        feedback_mock.assert_called_once()
                        feedback_request = feedback_mock.call_args.args[0]
                        self.assertEqual(
                            "publishing", feedback_request.observation.workflow
                        )
                        self.assertEqual(
                            "succeeded", feedback_request.observation.outcome
                        )
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


__all__ = ["TestCli01CliPrettyExceptionsDo"]
