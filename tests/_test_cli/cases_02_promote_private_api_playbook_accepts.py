# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403


class TestCli02PromotePrivateApiPlaybook(unittest.TestCase):
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
                cli,
                "load_settings",
                return_value=types.SimpleNamespace(state_db="./state/index.sqlite"),
            ) as load_app_mock:
                with patch.object(
                    cli, "run_publisher_inventory_discovery", return_value=result
                ) as discover_mock:
                    with patch.object(cli.console, "print"):
                        cli.discover_publisher_inventory(
                            insights_url="https://www.activate.com/insights"
                        )

        load_mock.assert_called_once()
        load_app_mock.assert_called_once()
        discover_mock.assert_called_once()
        request = discover_mock.call_args.args[0]
        self.assertEqual("https://www.activate.com/insights", request.insights_url)
        self.assertEqual("./state/reports.sqlite", request.reports_db)
        self.assertEqual("./state/index.sqlite", request.state_db)
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
                "load_settings",
                return_value=types.SimpleNamespace(state_db="./state/index.sqlite"),
            ) as load_app_mock:
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
        load_app_mock.assert_called_once()
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
                with self.assertRaises(typer.Exit) as exc_info:
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
                with patch.object(
                    cli,
                    "load_settings",
                    side_effect=RuntimeError("configuration is unavailable"),
                ):
                    with patch.object(cli, "setup_logging"):
                        with self.assertRaises(typer.Exit) as exc_info:
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

    def test_poll_mail_report_applies_per_run_poll_overrides(self) -> None:
        import src.cli as cli

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
            identity_profile=BrowserDownloadIdentity(schema_version="1.0", fields=[]),
            openrouter_http_referer=None,
            headed=False,
            retry_retries=1,
            retry_base_delay_seconds=1.0,
            retry_backoff_step_seconds=0.0,
            retry_jitter_seconds=0.0,
        )
        mailbox_settings = MailboxAcquisitionSettings(
            schema_version="1.0",
            provider="imap",
            output_dir="./out/mailbox",
            search_window_minutes=120,
            max_results=10,
            poll_timeout_seconds=900.0,
            poll_interval_seconds=60.0,
            gmail_oauth_client_path="",
            gmail_oauth_token_path="",
            gmail_user_id="me",
            imap_host="imap.example.com",
            imap_port=993,
            imap_user="ops@example.com",
            imap_password="secret",
            imap_mailbox="INBOX",
        )
        result = type(
            "MailReportAcquisitionResult",
            (),
            {
                "source_url": "https://example.com/report",
                "outcome": "downloaded",
                "mailbox_poll_count": 1,
                "selected_report_url": "https://example.com/report.pdf",
                "selected_message_id": "msg-1",
                "downloaded_file_path": "./out/report.pdf",
            },
        )()

        with patch.object(
            cli, "load_browser_download_settings", return_value=browser_settings
        ):
            with patch.object(
                cli,
                "load_mailbox_acquisition_settings",
                return_value=mailbox_settings,
            ):
                with patch.object(
                    cli, "run_mail_report_acquisition", return_value=result
                ) as run_mock:
                    with patch.object(cli.console, "print"):
                        cli.poll_mail_report(
                            source_url="https://example.com/report",
                            report_title="Retail Trends",
                            publisher_name="Example Publisher",
                            delivery_email="ops@example.com",
                            requested_after_utc="2026-07-05T12:00:00Z",
                            poll_timeout_seconds=5.0,
                            poll_interval_seconds=1.0,
                        )

        request = run_mock.call_args.args[0]
        self.assertEqual(5.0, request.mailbox_settings.poll_timeout_seconds)
        self.assertEqual(1.0, request.mailbox_settings.poll_interval_seconds)
        self.assertEqual(900.0, mailbox_settings.poll_timeout_seconds)


__all__ = ["TestCli02PromotePrivateApiPlaybook"]
