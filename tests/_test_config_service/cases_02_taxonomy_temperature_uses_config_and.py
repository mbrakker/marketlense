# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403


class TestConfigService02TaxonomyTemperatureUsesConfig(_TestConfigServiceBase):
    def test_inventory_settings_retain_candidate_screening_execution_policy(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg_path = self._write_config(tmp_dir, include_analysis=False)
            cfg_data = yaml.safe_load(Path(cfg_path).read_text(encoding="utf-8"))
            cfg_data["llm_execution_policies"] = {
                "publisher_inventory/meaningful_candidate_screen": {
                    "provider": "openai",
                    "model": "gpt-5-nano",
                    "temperature": 0.0,
                    "provider_retry_count": 0,
                }
            }
            Path(cfg_path).write_text(yaml.safe_dump(cfg_data), encoding="utf-8")

            with patch.dict(
                os.environ,
                {
                    "OPENAI_API_KEY": "openai-key",
                    "OPENROUTER_API_KEY": "openrouter-key",
                },
                clear=True,
            ):
                settings = load_publisher_inventory_settings(
                    ConfigLoadRequest(schema_version="1.0", path=cfg_path),
                    RunContext(
                        schema_version="1.0", run_id="r", task_id="t", span_id="s"
                    ),
                )

        self.assertEqual(
            "gpt-5-nano",
            settings.llm_execution_policies[
                "publisher_inventory/meaningful_candidate_screen"
            ]["model"],
        )

    def test_taxonomy_temperature_uses_config_and_env_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg_path = self._write_config(tmp_dir, include_analysis=False)
            cfg_data = yaml.safe_load(Path(cfg_path).read_text(encoding="utf-8"))
            cfg_data["ingest"]["taxonomy_temperature"] = 0.2
            Path(cfg_path).write_text(yaml.safe_dump(cfg_data), encoding="utf-8")

            with patch.dict(os.environ, {"OPENAI_API_KEY": "key"}, clear=True):
                settings = load_settings(
                    ConfigLoadRequest(schema_version="1.0", path=cfg_path),
                    RunContext(
                        schema_version="1.0", run_id="r", task_id="t", span_id="s"
                    ),
                )
                self.assertEqual(0.2, settings.taxonomy_temperature)

            env = {
                "OPENAI_API_KEY": "key",
                "TAXONOMY_TEMPERATURE": "0.05",
            }
            with patch.dict(os.environ, env, clear=True):
                settings = load_settings(
                    ConfigLoadRequest(schema_version="1.0", path=cfg_path),
                    RunContext(
                        schema_version="1.0", run_id="r", task_id="t", span_id="s"
                    ),
                )
                self.assertEqual(0.05, settings.taxonomy_temperature)

    def test_pdf_text_ocr_settings_load(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg_path = self._write_config(tmp_dir, include_analysis=False)
            cfg_data = yaml.safe_load(Path(cfg_path).read_text(encoding="utf-8"))
            cfg_data["ingest"]["pdf_text"] = {
                "max_pages": 5,
                "max_chars": 80000,
                "min_density": 250,
                "sample_pages": 3,
                "native_confidence_threshold": 0.61,
                "native_page_confidence_threshold": 0.42,
                "ocr_fallback": {
                    "enabled": True,
                    "policy": "always",
                    "model": "gpt-5-mini",
                    "timeout_seconds": 321.0,
                    "prompt_namespace": "pdf_text/ocr_fallback",
                    "cache_enabled": False,
                    "chunk_page_count": 6,
                },
            }
            Path(cfg_path).write_text(yaml.safe_dump(cfg_data), encoding="utf-8")

            with patch.dict(os.environ, {"OPENAI_API_KEY": "key"}, clear=True):
                settings = load_settings(
                    ConfigLoadRequest(schema_version="1.0", path=cfg_path),
                    RunContext(
                        schema_version="1.0", run_id="r", task_id="t", span_id="s"
                    ),
                )

        self.assertTrue(settings.pdf_text_ocr_enabled)
        self.assertEqual(0.61, settings.pdf_text_native_confidence_threshold)
        self.assertEqual(0.42, settings.pdf_text_native_page_confidence_threshold)
        self.assertEqual("always", settings.pdf_text_ocr_policy)
        self.assertEqual("gpt-5-mini", settings.pdf_text_ocr_model)
        self.assertEqual(321.0, settings.pdf_text_ocr_timeout_seconds)
        self.assertEqual(
            "pdf_text/ocr_fallback", settings.pdf_text_ocr_prompt_namespace
        )
        self.assertFalse(settings.pdf_text_ocr_cache_enabled)
        self.assertEqual(6, settings.pdf_text_ocr_chunk_page_count)

    def test_figure_caption_settings_load(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg_path = self._write_config(tmp_dir, include_analysis=False)
            cfg_data = yaml.safe_load(Path(cfg_path).read_text(encoding="utf-8"))
            cfg_data["ingest"]["figure_captions"] = {
                "enabled": True,
                "temperature": 0.15,
                "timeout_seconds": 321.0,
                "prompt_namespace": "report_vs/figure_caption",
                "max_chars": 420,
            }
            Path(cfg_path).write_text(yaml.safe_dump(cfg_data), encoding="utf-8")

            with patch.dict(os.environ, {"OPENAI_API_KEY": "key"}, clear=True):
                settings = load_settings(
                    ConfigLoadRequest(schema_version="1.0", path=cfg_path),
                    RunContext(
                        schema_version="1.0", run_id="r", task_id="t", span_id="s"
                    ),
                )

        self.assertTrue(settings.figure_caption_enabled)
        self.assertEqual(0.15, settings.figure_caption_temperature)
        self.assertEqual(321.0, settings.figure_caption_timeout_seconds)
        self.assertEqual(
            "report_vs/figure_caption", settings.figure_caption_prompt_namespace
        )
        self.assertEqual(420, settings.figure_caption_max_chars)

    def test_publish_settings_derive_site_url_from_admin(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg_path = self._write_config(tmp_dir, include_publish=True)
            cfg_data = yaml.safe_load(Path(cfg_path).read_text(encoding="utf-8"))
            cfg_data["publish"]["media_upload_workers"] = 3
            Path(cfg_path).write_text(yaml.safe_dump(cfg_data), encoding="utf-8")
            env = {
                "WP_ADMIN_URL": "https://example.com/wp-admin/",
                "WP_SITE_URL": "",
                "WP_APP_PASSWORD": "app-pass",
                "WP_BEARER_TOKEN": "",
            }
            with patch.dict(os.environ, env, clear=True):
                settings = load_publish_settings(
                    ConfigLoadRequest(schema_version="1.0", path=cfg_path),
                    RunContext(
                        schema_version="1.0", run_id="r", task_id="t", span_id="s"
                    ),
                )

        self.assertEqual("https://example.com", settings.wp.site_url)
        self.assertEqual("admin", settings.wp.username)
        self.assertEqual("app-pass", settings.wp.app_password)
        self.assertIsNone(settings.wp.bearer_token)
        self.assertEqual(3, settings.media_upload_workers)

    def test_publish_settings_preserve_zero_wordpress_write_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg_path = self._write_config(tmp_dir, include_publish=True)
            cfg_data = yaml.safe_load(Path(cfg_path).read_text(encoding="utf-8"))
            cfg_data["publish"]["run_budget"] = {
                "enabled": True,
                "max_wordpress_writes": 0,
                "limit_decision": "stop",
            }
            Path(cfg_path).write_text(yaml.safe_dump(cfg_data), encoding="utf-8")
            env = {
                "WP_SITE_URL": "https://example.com",
                "WP_APP_PASSWORD": "app-pass",
                "WP_BEARER_TOKEN": "",
            }
            with patch.dict(os.environ, env, clear=True):
                settings = load_publish_settings(
                    ConfigLoadRequest(schema_version="1.0", path=cfg_path),
                    RunContext(
                        schema_version="1.0", run_id="r", task_id="t", span_id="s"
                    ),
                )

        self.assertEqual(0, settings.run_budget_max_wordpress_writes)

    def test_publish_settings_missing_site_url_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg_path = self._write_config(tmp_dir, include_publish=True)
            env = {
                "WP_APP_PASSWORD": "app-pass",
                "WP_SITE_URL": "",
                "WP_ADMIN_URL": "",
                "WP_BEARER_TOKEN": "",
            }
            with patch.dict(os.environ, env, clear=True):
                with self.assertRaises(RuntimeError) as ctx:
                    load_publish_settings(
                        ConfigLoadRequest(schema_version="1.0", path=cfg_path),
                        RunContext(
                            schema_version="1.0", run_id="r", task_id="t", span_id="s"
                        ),
                    )
        self.assertIn("publish.wp.site_url", str(ctx.exception))

    def test_publish_settings_missing_auth_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg_path = self._write_config(tmp_dir, include_publish=True)
            env = {
                "WP_SITE_URL": "https://example.com",
                "WP_APP_PASSWORD": "",
                "WP_BEARER_TOKEN": "",
            }
            with patch.dict(os.environ, env, clear=True):
                with self.assertRaises(RuntimeError) as ctx:
                    load_publish_settings(
                        ConfigLoadRequest(schema_version="1.0", path=cfg_path),
                        RunContext(
                            schema_version="1.0", run_id="r", task_id="t", span_id="s"
                        ),
                    )
        self.assertIn("WP_APP_PASSWORD", str(ctx.exception))

    def test_publish_settings_ssl_verify_env_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg_path = self._write_config(tmp_dir, include_publish=True)
            cfg_data = yaml.safe_load(Path(cfg_path).read_text(encoding="utf-8"))
            cfg_data["publish"]["wp"]["ssl_verify"] = True
            Path(cfg_path).write_text(yaml.safe_dump(cfg_data), encoding="utf-8")
            env = {
                "WP_SITE_URL": "https://example.com",
                "WP_APP_PASSWORD": "app-pass",
                "WP_BEARER_TOKEN": "",
                "WP_SSL_VERIFY": "false",
            }
            with patch.dict(os.environ, env, clear=True):
                settings = load_publish_settings(
                    ConfigLoadRequest(schema_version="1.0", path=cfg_path),
                    RunContext(
                        schema_version="1.0", run_id="r", task_id="t", span_id="s"
                    ),
                )

        self.assertFalse(settings.wp.ssl_verify)
        self.assertIsNone(settings.wp.ca_bundle_path)

    def test_publish_settings_missing_ca_bundle_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg_path = self._write_config(tmp_dir, include_publish=True)
            cfg_data = yaml.safe_load(Path(cfg_path).read_text(encoding="utf-8"))
            cfg_data["publish"]["wp"]["ssl_verify"] = True
            cfg_data["publish"]["wp"]["ca_bundle_path"] = "missing-ca.pem"
            Path(cfg_path).write_text(yaml.safe_dump(cfg_data), encoding="utf-8")
            env = {
                "WP_SITE_URL": "https://example.com",
                "WP_APP_PASSWORD": "app-pass",
                "WP_BEARER_TOKEN": "",
                "WP_SSL_VERIFY": "true",
            }
            with patch.dict(os.environ, env, clear=True):
                with self.assertRaises(RuntimeError) as ctx:
                    load_publish_settings(
                        ConfigLoadRequest(schema_version="1.0", path=cfg_path),
                        RunContext(
                            schema_version="1.0", run_id="r", task_id="t", span_id="s"
                        ),
                    )

        self.assertIn("publish.wp.ca_bundle_path", str(ctx.exception))

    def test_browser_download_settings_load(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg_path = self._write_config(tmp_dir, include_publish=False)
            cfg_data = yaml.safe_load(Path(cfg_path).read_text(encoding="utf-8"))
            cfg_data["browser_download"] = {
                "model": "gpt-5-mini",
                "identity_config_path": str(
                    Path(tmp_dir) / "browser_download_identity.yaml"
                ),
                "temperature": 0.1,
                "timeout_seconds": 45,
                "max_steps": 12,
                "route_budgets": {
                    "browser_email_form": {
                        "timeout_seconds": 20,
                        "max_steps": 7,
                    },
                    "browser_listing_hub": {
                        "timeout_seconds": 90,
                        "max_steps": 30,
                    },
                },
                "max_tokens": 14000,
                "output_dir": "./out/browser_downloads",
                "headed": True,
                "captcha_handoff": {
                    "enabled": True,
                    "timeout_seconds": 120,
                },
                "route_playbook_promotion_mode": "dry_run",
                "private_api_playbook_promotion_mode": "write",
                "private_api_playbook_min_success_count": 4,
                "private_api_playbook_min_distinct_source_urls": 3,
                "failure_forensics": {
                    "enabled": True,
                    "policy": "metadata_only",
                },
                "session_reuse": {
                    "enabled": True,
                    "mode": "same_publisher_batch",
                    "session_key": "batch-key",
                    "publisher_scope": "example.com",
                    "ttl_seconds": 300,
                    "base_dir": "./out/browser_sessions",
                    "cleanup_expired": True,
                    "allow_cross_publisher": False,
                },
                "warm_worker_pool": {
                    "enabled": True,
                    "max_workers": 2,
                    "max_runs_per_worker": 5,
                    "max_memory_mb": 512,
                    "idle_ttl_seconds": 180,
                    "fallback_to_subprocess": True,
                },
                "retry": {
                    "retries": 2,
                    "base_delay_seconds": 0.5,
                    "backoff_step_seconds": 0.25,
                    "jitter_seconds": 0.0,
                },
            }
            Path(cfg_path).write_text(yaml.safe_dump(cfg_data), encoding="utf-8")

            with patch.dict(
                os.environ,
                {
                    "OPENROUTER_API_KEY": "key",
                    "GOOGLE_DRIVE_AUTH_MODE": "service_account",
                },
                clear=True,
            ):
                settings = load_browser_download_settings(
                    ConfigLoadRequest(schema_version="1.0", path=cfg_path),
                    RunContext(
                        schema_version="1.0", run_id="r", task_id="t", span_id="s"
                    ),
                )

        self.assertEqual("gpt-5-mini", settings.model)
        self.assertEqual(0.1, settings.temperature)
        self.assertEqual(45, settings.timeout_seconds)
        self.assertEqual(12, settings.max_steps)
        self.assertEqual(2, len(settings.route_budgets))
        self.assertEqual("browser_email_form", settings.route_budgets[0].route_family)
        self.assertEqual(20.0, settings.route_budgets[0].timeout_seconds)
        self.assertEqual(7, settings.route_budgets[0].max_steps)
        self.assertEqual("browser_listing_hub", settings.route_budgets[1].route_family)
        self.assertEqual(90.0, settings.route_budgets[1].timeout_seconds)
        self.assertEqual(30, settings.route_budgets[1].max_steps)
        self.assertEqual(14000, settings.max_tokens)
        self.assertTrue(settings.headed)
        self.assertTrue(settings.captcha_handoff_policy.enabled)
        self.assertEqual(120.0, settings.captcha_handoff_policy.timeout_seconds)
        self.assertEqual(2, settings.retry_retries)
        self.assertEqual(0.5, settings.retry_base_delay_seconds)
        self.assertEqual(
            Path(tmp_dir, "out", "browser_downloads").resolve(),
            Path(settings.output_dir).resolve(),
        )
        self.assertEqual(
            Path(tmp_dir, "state", "index.sqlite").resolve(),
            Path(settings.state_db).resolve(),
        )
        self.assertEqual(
            Path(tmp_dir, "state", "reports.sqlite").resolve(),
            Path(settings.reports_db).resolve(),
        )
        self.assertEqual(
            Path(tmp_dir, "browser_download_identity.yaml").resolve(),
            Path(settings.identity_config_path).resolve(),
        )
        self.assertTrue(settings.drive_upload_enabled)
        self.assertTrue(settings.drive_upload_required)
        self.assertEqual("folder", settings.drive_upload_parent_folder_id)
        self.assertEqual("service_account", settings.drive_upload_auth_mode)
        self.assertTrue(settings.failure_forensics_enabled)
        self.assertEqual("metadata_only", settings.failure_forensics_policy)
        self.assertEqual("dry_run", settings.route_playbook_promotion_mode)
        self.assertEqual("write", settings.private_api_playbook_promotion_mode)
        self.assertEqual(4, settings.private_api_playbook_min_success_count)
        self.assertEqual(3, settings.private_api_playbook_min_distinct_source_urls)
        self.assertTrue(settings.session_reuse_policy.enabled)
        self.assertEqual("same_publisher_batch", settings.session_reuse_policy.mode)
        self.assertEqual("batch-key", settings.session_reuse_policy.session_key)
        self.assertEqual("example.com", settings.session_reuse_policy.publisher_scope)
        self.assertEqual(300.0, settings.session_reuse_policy.ttl_seconds)
        self.assertEqual(
            "./out/browser_sessions",
            settings.session_reuse_policy.base_dir,
        )
        self.assertTrue(settings.session_reuse_policy.cleanup_expired)
        self.assertFalse(settings.session_reuse_policy.allow_cross_publisher)
        self.assertTrue(settings.warm_worker_pool_policy.enabled)
        self.assertEqual(2, settings.warm_worker_pool_policy.max_workers)
        self.assertEqual(5, settings.warm_worker_pool_policy.max_runs_per_worker)
        self.assertEqual(512, settings.warm_worker_pool_policy.max_memory_mb)
        self.assertEqual(180.0, settings.warm_worker_pool_policy.idle_ttl_seconds)
        self.assertTrue(settings.warm_worker_pool_policy.fallback_to_subprocess)
        self.assertEqual(
            Path(tmp_dir, "sa.json").resolve(),
            Path(settings.drive_upload_google_sa_path).resolve(),
        )
        self.assertEqual(2, len(settings.identity_profile.fields))

    def test_browser_download_settings_load_publisher_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg_path = self._write_config(tmp_dir, include_publish=False)
            identity_path = Path(tmp_dir) / "browser_download_identity.yaml"
            identity_payload = yaml.safe_load(identity_path.read_text(encoding="utf-8"))
            identity_payload["delivery_emails"] = [
                "reports@marketlense.local",
                "ops@example.com",
            ]
            identity_payload["publisher_overrides"] = [
                {
                    "schema_version": "1.0",
                    "host_pattern": "example.com",
                    "delivery_emails": ["analyst@example.com"],
                    "field_values": [
                        {
                            "schema_version": "1.0",
                            "key": "country",
                            "label": "Country",
                            "value": "Austria",
                            "aliases": ["country"],
                            "option_aliases": ["Republic of Austria"],
                        }
                    ],
                }
            ]
            identity_path.write_text(
                yaml.safe_dump(identity_payload, sort_keys=False),
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"OPENROUTER_API_KEY": "key"}, clear=True):
                settings = load_browser_download_settings(
                    ConfigLoadRequest(schema_version="1.0", path=cfg_path),
                    RunContext(
                        schema_version="1.0", run_id="r", task_id="t", span_id="s"
                    ),
                )

        self.assertEqual(
            ["reports@marketlense.local", "ops@example.com"],
            settings.identity_profile.delivery_emails,
        )
        self.assertEqual(1, len(settings.identity_profile.publisher_overrides))
        override = settings.identity_profile.publisher_overrides[0]
        self.assertEqual("example.com", override.host_pattern)
        self.assertEqual(["analyst@example.com"], override.delivery_emails)
        self.assertEqual("country", override.field_values[0].key)
        self.assertEqual("Austria", override.field_values[0].value)
        self.assertEqual(
            ["Republic of Austria"], override.field_values[0].option_aliases
        )

    def test_browser_download_identity_loads_typed_consent_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg_path = self._write_config(tmp_dir, include_publish=False)
            identity_path = Path(tmp_dir) / "browser_download_identity.yaml"
            identity_payload = yaml.safe_load(identity_path.read_text(encoding="utf-8"))
            identity_payload["consent_policy"] = {
                "schema_version": "1.0",
                "default_checkbox_policy": "mandatory_privacy_terms_only",
                "allow_marketing_opt_in": False,
                "allow_optional_newsletter": False,
            }
            identity_path.write_text(
                yaml.safe_dump(identity_payload, sort_keys=False),
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"OPENROUTER_API_KEY": "key"}, clear=True):
                settings = load_browser_download_settings(
                    ConfigLoadRequest(schema_version="1.0", path=cfg_path),
                    RunContext(
                        schema_version="1.0", run_id="r", task_id="t", span_id="s"
                    ),
                )

        self.assertEqual(
            "mandatory_privacy_terms_only",
            settings.identity_profile.consent_policy.default_checkbox_policy,
        )
        self.assertFalse(
            settings.identity_profile.consent_policy.allow_marketing_opt_in
        )
        self.assertFalse(
            settings.identity_profile.consent_policy.allow_optional_newsletter
        )

    def test_browser_download_settings_allow_missing_provider_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg_path = self._write_config(tmp_dir, include_publish=False)
            with patch("src.services.config_service.load_dotenv", return_value=False):
                with patch.dict(os.environ, {}, clear=True):
                    settings = load_browser_download_settings(
                        ConfigLoadRequest(schema_version="1.0", path=cfg_path),
                        RunContext(
                            schema_version="1.0",
                            run_id="r",
                            task_id="t",
                            span_id="s",
                        ),
                    )
        self.assertEqual("", settings.openai_api_key)
        self.assertEqual("", settings.openrouter_api_key)

    def test_publisher_inventory_settings_load_and_fallback_to_browser_download(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg_path = self._write_config(tmp_dir, include_publish=False)
            cfg_data = yaml.safe_load(Path(cfg_path).read_text(encoding="utf-8"))
            cfg_data["browser_download"] = {
                "model": "gpt-5-mini",
                "identity_config_path": str(
                    Path(tmp_dir) / "browser_download_identity.yaml"
                ),
                "temperature": 0.1,
                "timeout_seconds": 45,
                "max_steps": 12,
                "output_dir": "./out/browser_downloads",
                "headed": True,
                "retry": {
                    "retries": 2,
                    "base_delay_seconds": 0.5,
                    "backoff_step_seconds": 0.25,
                    "jitter_seconds": 0.0,
                },
            }
            cfg_data["publisher_discovery"] = {
                "pagination_max_pages": 7,
                "http_timeout_seconds": 22,
                "command_time_budget_seconds": 555,
                "prompt_namespace": "publisher_inventory/discovery",
                "force_browser": True,
            }
            Path(cfg_path).write_text(yaml.safe_dump(cfg_data), encoding="utf-8")

            with patch.dict(
                os.environ,
                {
                    "OPENROUTER_API_KEY": "key",
                    "OPENAI_API_KEY": "openai-key",
                    "GOOGLE_DRIVE_AUTH_MODE": "service_account",
                },
                clear=True,
            ):
                settings = load_publisher_inventory_settings(
                    ConfigLoadRequest(schema_version="1.0", path=cfg_path),
                    RunContext(
                        schema_version="1.0", run_id="r", task_id="t", span_id="s"
                    ),
                )

        self.assertIsInstance(settings, PublisherInventorySettings)
        self.assertEqual("gpt-5-mini", settings.model)
        self.assertEqual(0.1, settings.temperature)
        self.assertEqual(45, settings.timeout_seconds)
        self.assertEqual(12, settings.max_steps)
        self.assertEqual(7, settings.pagination_max_pages)
        self.assertEqual(22, settings.http_timeout_seconds)
        self.assertEqual(555, settings.command_time_budget_seconds)
        self.assertTrue(settings.headed)
        self.assertTrue(settings.force_browser)
        self.assertTrue(settings.enable_deferred_candidate_recovery)
        self.assertTrue(settings.enable_structured_route_reuse)
        self.assertTrue(settings.enable_preflight_classifier_and_direct_detail)
        self.assertEqual(2, settings.retry_retries)
        self.assertTrue(settings.candidate_screening_enabled)
        self.assertEqual("gpt-5.6-luna", settings.candidate_screening_model)
        self.assertEqual(1.0, settings.candidate_screening_temperature)
        self.assertEqual(10, settings.candidate_screening_batch_size)
        self.assertEqual(
            "publisher_inventory/meaningful_candidate_screen",
            settings.candidate_screening_prompt_namespace,
        )
        self.assertTrue(settings.candidate_quality_check_enabled)
        self.assertEqual(15.0, settings.candidate_quality_check_timeout_seconds)
        self.assertEqual(6, settings.candidate_quality_check_max_workers)
        self.assertEqual("openai-key", settings.openai_api_key)
        self.assertEqual(
            Path(tmp_dir, "out", "browser_downloads").resolve(),
            Path(settings.output_dir).resolve(),
        )
        self.assertEqual(
            Path(tmp_dir, "state", "reports.sqlite").resolve(),
            Path(settings.reports_db).resolve(),
        )
        self.assertEqual(
            Path(tmp_dir, "sa.json").resolve(),
            Path(settings.google_sa_path).resolve(),
        )

    def test_load_settings_supports_oauth_drive_auth_without_service_account(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg_path = self._write_config(tmp_dir, include_analysis=False)
            cfg_data = yaml.safe_load(Path(cfg_path).read_text(encoding="utf-8"))
            cfg_data["ingest"].pop("google_sa_path", None)
            cfg_data["ingest"]["drive"] = {
                "auth_mode": "oauth_user",
                "oauth_client_path": str(Path(tmp_dir) / "oauth-client.json"),
                "oauth_token_path": str(Path(tmp_dir) / "oauth-token.json"),
            }
            Path(cfg_path).write_text(yaml.safe_dump(cfg_data), encoding="utf-8")

            with patch.dict(os.environ, {"OPENAI_API_KEY": "key"}, clear=True):
                settings = load_settings(
                    ConfigLoadRequest(schema_version="1.0", path=cfg_path),
                    RunContext(
                        schema_version="1.0", run_id="r", task_id="t", span_id="s"
                    ),
                )

        self.assertEqual("oauth_user", settings.drive_auth_mode)
        self.assertIsNone(settings.google_sa_path or None)
        self.assertEqual(
            Path(tmp_dir, "oauth-client.json").resolve(),
            Path(str(settings.google_oauth_client_path)).resolve(),
        )
        self.assertEqual(
            Path(tmp_dir, "oauth-token.json").resolve(),
            Path(str(settings.google_oauth_token_path)).resolve(),
        )

    def test_publisher_inventory_settings_support_oauth_drive_auth(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg_path = self._write_config(tmp_dir, include_publish=False)
            cfg_data = yaml.safe_load(Path(cfg_path).read_text(encoding="utf-8"))
            cfg_data["ingest"].pop("google_sa_path", None)
            cfg_data["ingest"]["drive"] = {
                "auth_mode": "oauth_user",
                "oauth_client_path": str(Path(tmp_dir) / "oauth-client.json"),
                "oauth_token_path": str(Path(tmp_dir) / "oauth-token.json"),
            }
            cfg_data["publisher_discovery"] = {
                "pagination_max_pages": 3,
                "http_timeout_seconds": 15,
            }
            Path(cfg_path).write_text(yaml.safe_dump(cfg_data), encoding="utf-8")

            with patch.dict(
                os.environ,
                {"OPENROUTER_API_KEY": "key", "OPENAI_API_KEY": "openai-key"},
                clear=True,
            ):
                settings = load_publisher_inventory_settings(
                    ConfigLoadRequest(schema_version="1.0", path=cfg_path),
                    RunContext(
                        schema_version="1.0", run_id="r", task_id="t", span_id="s"
                    ),
                )

        self.assertEqual("oauth_user", settings.drive_auth_mode)
        self.assertIsNone(settings.google_sa_path or None)
        self.assertEqual(
            Path(tmp_dir, "oauth-client.json").resolve(),
            Path(str(settings.google_oauth_client_path)).resolve(),
        )
        self.assertEqual(
            Path(tmp_dir, "oauth-token.json").resolve(),
            Path(str(settings.google_oauth_token_path)).resolve(),
        )

    def test_publisher_inventory_settings_allow_disabled_candidate_screening_without_openai_key(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg_path = self._write_config(tmp_dir, include_publish=False)
            cfg_data = yaml.safe_load(Path(cfg_path).read_text(encoding="utf-8"))
            cfg_data["browser_download"] = {
                "model": "gpt-5-mini",
                "identity_config_path": str(
                    Path(tmp_dir) / "browser_download_identity.yaml"
                ),
            }
            cfg_data["publisher_discovery"] = {
                "candidate_screening": {
                    "enabled": False,
                },
            }
            Path(cfg_path).write_text(yaml.safe_dump(cfg_data), encoding="utf-8")

            with patch("src.services.config_service.load_dotenv", return_value=False):
                with patch.dict(
                    os.environ,
                    {
                        "OPENROUTER_API_KEY": "key",
                        "GOOGLE_OAUTH_CLIENT_JSON": "oauth-client.json",
                        "GOOGLE_OAUTH_TOKEN_JSON": "oauth-token.json",
                    },
                    clear=True,
                ):
                    settings = load_publisher_inventory_settings(
                        ConfigLoadRequest(schema_version="1.0", path=cfg_path),
                        RunContext(
                            schema_version="1.0", run_id="r", task_id="t", span_id="s"
                        ),
                    )

        self.assertFalse(settings.candidate_screening_enabled)
        self.assertEqual("", settings.openai_api_key)

    def test_load_settings_uses_env_config_path_profile_and_local_overlay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg_path = Path(self._write_config(tmp_dir, include_analysis=False))
            profile_path = cfg_path.with_name("app.dev.yaml")
            local_path = cfg_path.with_name("app.local.yaml")
            profile_path.write_text(
                yaml.safe_dump(
                    {
                        "ingest": {
                            "batch_limit": 31,
                            "contents_page": {"keywords": ["overview", "toc"]},
                        }
                    }
                ),
                encoding="utf-8",
            )
            local_path.write_text(
                yaml.safe_dump({"ingest": {"batch_limit": 41}}),
                encoding="utf-8",
            )

            env = {
                "MARKET_LENSE_CONFIG_PATH": str(cfg_path),
                "MARKET_LENSE_CONFIG_PROFILE": "dev",
                "OPENAI_API_KEY": "key",
            }
            with patch.dict(os.environ, env, clear=True):
                settings = load_settings(
                    ConfigLoadRequest(schema_version="1.0", path=""),
                    RunContext(
                        schema_version="1.0", run_id="r", task_id="t", span_id="s"
                    ),
                )

        self.assertEqual(41, settings.batch_limit)
        self.assertEqual(["overview", "toc"], settings.contents_keywords)

    def test_load_settings_rejects_non_mapping_yaml_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg_path = Path(tmp_dir) / "app.yaml"
            cfg_path.write_text("- not-a-mapping\n", encoding="utf-8")

            with patch.dict(os.environ, {"OPENAI_API_KEY": "key"}, clear=True):
                with self.assertRaises(RuntimeError) as ctx:
                    load_settings(
                        ConfigLoadRequest(schema_version="1.0", path=str(cfg_path)),
                        RunContext(
                            schema_version="1.0",
                            run_id="r",
                            task_id="t",
                            span_id="s",
                        ),
                    )

        self.assertIn("mapping", str(ctx.exception).lower())

    def test_load_settings_rejects_missing_config_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg_path = Path(tmp_dir) / "missing.yaml"

            with patch.dict(os.environ, {"OPENAI_API_KEY": "key"}, clear=True):
                with self.assertRaises(RuntimeError) as ctx:
                    load_settings(
                        ConfigLoadRequest(schema_version="1.0", path=str(cfg_path)),
                        RunContext(
                            schema_version="1.0",
                            run_id="r",
                            task_id="t",
                            span_id="s",
                        ),
                    )

        self.assertIn("not found", str(ctx.exception).lower())

    def test_load_settings_resolves_deterministic_admission_limits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg_path = self._write_config(tmp_dir, include_analysis=False)
            cfg_data = yaml.safe_load(Path(cfg_path).read_text(encoding="utf-8"))
            cfg_data["ingest"]["admission"] = {
                "min_text_chars": 900,
                "max_pages": 180,
                "max_source_bytes": 12_000_000,
                "required_evidence_families": ["doc_map", "findings"],
            }
            Path(cfg_path).write_text(yaml.safe_dump(cfg_data), encoding="utf-8")

            with patch.dict(os.environ, {"OPENAI_API_KEY": "key"}, clear=True):
                settings = load_settings(
                    ConfigLoadRequest(schema_version="1.0", path=cfg_path),
                    RunContext(
                        schema_version="1.0", run_id="r", task_id="t", span_id="s"
                    ),
                )

        self.assertEqual(900, settings.admission_min_text_chars)
        self.assertEqual(180, settings.admission_max_pages)
        self.assertEqual(12_000_000, settings.admission_max_source_bytes)
        self.assertEqual(
            ("doc_map", "findings"), settings.admission_required_evidence_families
        )


__all__ = ["TestConfigService02TaxonomyTemperatureUsesConfig"]
