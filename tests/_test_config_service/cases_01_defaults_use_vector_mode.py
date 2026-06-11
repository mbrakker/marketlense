# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403

class TestConfigService01DefaultsUseVectorMode(_TestConfigServiceBase):
    def test_defaults_use_vector_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg_path = self._write_config(tmp_dir, include_analysis=False)
            with patch.dict(os.environ, {"OPENAI_API_KEY": "key"}, clear=True):
                settings = load_settings(
                    ConfigLoadRequest(schema_version="1.0", path=cfg_path),
                    RunContext(
                        schema_version="1.0", run_id="r", task_id="t", span_id="s"
                    ),
                )

        self.assertTrue(settings.vector_store_keep)
        self.assertEqual(
            Path(tmp_dir, "state", "signals.sqlite").resolve(),
            Path(settings.signal_store_db).resolve(),
        )
        self.assertEqual(30, settings.vector_store_retention_days)
        self.assertFalse(settings.artifacts_use_vector_store)
        self.assertFalse(settings.validation_grounding_use_vector_store)
        self.assertEqual("./out/cost-ledger.jsonl", settings.cost_ledger_path)
        self.assertIn("AI", settings.html_tag_acronyms)
        self.assertIn("ROI", settings.html_tag_acronyms)
        self.assertTrue(
            settings.publisher_profiles_path.endswith("publisher-profiles.json")
        )

    def test_signal_store_path_can_be_configured(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg_path = self._write_config(tmp_dir, include_analysis=False)
            cfg_data = yaml.safe_load(Path(cfg_path).read_text(encoding="utf-8"))
            cfg_data["paths"]["signal_store_db"] = str(
                Path(tmp_dir, "signal-base", "signals.sqlite")
            )
            Path(cfg_path).write_text(yaml.safe_dump(cfg_data), encoding="utf-8")
            with patch.dict(os.environ, {"OPENAI_API_KEY": "key"}, clear=True):
                settings = load_settings(
                    ConfigLoadRequest(schema_version="1.0", path=cfg_path),
                    RunContext(
                        schema_version="1.0", run_id="r", task_id="t", span_id="s"
                    ),
                )

        self.assertEqual(
            Path(tmp_dir, "signal-base", "signals.sqlite").resolve(),
            Path(settings.signal_store_db).resolve(),
        )

    def test_capability_settings_loaders_honor_env_config_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg_path = self._write_config(
                tmp_dir,
                include_analysis=True,
                include_publish=True,
            )
            env = {
                "MARKET_LENSE_CONFIG_PATH": cfg_path,
                "OPENAI_API_KEY": "openai-key",
                "OPENROUTER_API_KEY": "openrouter-key",
                "WP_SITE_URL": "https://wp.example",
                "WP_APP_PASSWORD": "wp-password",
            }
            with patch.dict(os.environ, env, clear=True):
                request = ConfigLoadRequest(schema_version="1.0", path="")
                ctx = RunContext(
                    schema_version="1.0", run_id="r", task_id="t", span_id="s"
                )
                publish_settings = load_publish_settings(request, ctx)
                browser_settings = load_browser_download_settings(request, ctx)
                inventory_settings = load_publisher_inventory_settings(request, ctx)

            tmp_path = Path(tmp_dir).resolve()
            self.assertEqual(
                tmp_path / "out",
                Path(publish_settings.output_dir).resolve(),
            )
            self.assertEqual(
                tmp_path / "state" / "reports.sqlite",
                Path(publish_settings.reports_db).resolve(),
            )
            self.assertEqual(
                tmp_path / "out" / "browser_downloads",
                Path(browser_settings.output_dir).resolve(),
            )
            self.assertEqual(
                tmp_path / "out" / "browser_downloads",
                Path(inventory_settings.output_dir).resolve(),
            )

    def test_html_tag_acronyms_can_be_configured(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg_path = self._write_config(tmp_dir, include_analysis=False)
            cfg_data = yaml.safe_load(Path(cfg_path).read_text(encoding="utf-8"))
            acronyms_path = Path(tmp_dir) / "custom-html-tag-acronyms.yaml"
            acronyms_path.write_text(
                yaml.safe_dump(
                    {
                        "schema_version": "1.0",
                        "html_tag_acronyms": ["AI", "ROI", "CPC", "ai", ""],
                    }
                ),
                encoding="utf-8",
            )
            cfg_data["paths"]["html_tag_acronyms"] = str(acronyms_path)
            Path(cfg_path).write_text(yaml.safe_dump(cfg_data), encoding="utf-8")

            with patch.dict(os.environ, {"OPENAI_API_KEY": "key"}, clear=True):
                settings = load_settings(
                    ConfigLoadRequest(schema_version="1.0", path=cfg_path),
                    RunContext(
                        schema_version="1.0", run_id="r", task_id="t", span_id="s"
                    ),
                )

        self.assertEqual(["AI", "ROI", "CPC"], settings.html_tag_acronyms)

    def test_env_overrides_analysis_flags(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg_path = self._write_config(tmp_dir, include_analysis=True)
            env = {
                "OPENAI_API_KEY": "key",
                "VECTOR_STORE_KEEP": "false",
                "VECTOR_STORE_RETENTION_DAYS": "14",
                "ARTIFACTS_USE_VECTOR_STORE": "true",
                "VALIDATION_GROUNDING_USE_VECTOR_STORE": "true",
                "COST_LEDGER_PATH": f"{tmp_dir}/ledger.jsonl",
            }
            with patch.dict(os.environ, env, clear=True):
                settings = load_settings(
                    ConfigLoadRequest(schema_version="1.0", path=cfg_path),
                    RunContext(
                        schema_version="1.0", run_id="r", task_id="t", span_id="s"
                    ),
                )

        self.assertFalse(settings.vector_store_keep)
        self.assertEqual(14, settings.vector_store_retention_days)
        self.assertTrue(settings.artifacts_use_vector_store)
        self.assertTrue(settings.validation_grounding_use_vector_store)
        self.assertEqual(f"{tmp_dir}/ledger.jsonl", settings.cost_ledger_path)
        self.assertEqual("./out/cost-daily.json", settings.cost_daily_path)
        self.assertIsInstance(settings.model_pricing, dict)

    def test_model_pricing_loads_from_separate_llm_costs_yaml(self) -> None:
        pricing = {
            "gpt-5-mini": {
                "input_tokens_per_1k_usd": 0.111,
                "output_tokens_per_1k_usd": 0.222,
                "tool_call_usd": 0.333,
            }
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg_path = self._write_config(tmp_dir, include_analysis=True)
            costs_path = Path(tmp_dir) / "llm-costs.yaml"
            costs_path.write_text(
                yaml.safe_dump(
                    {
                        "schema_version": "1.0",
                        "pricing": pricing,
                    }
                ),
                encoding="utf-8",
            )
            cfg_data = yaml.safe_load(Path(cfg_path).read_text(encoding="utf-8"))
            cfg_data["cost"] = {
                "daily_path": "./out/custom-cost-daily.json",
                "pricing_path": "./llm-costs.yaml",
            }
            Path(cfg_path).write_text(yaml.safe_dump(cfg_data), encoding="utf-8")

            env = {
                "OPENAI_API_KEY": "openai-key",
                "OPENROUTER_API_KEY": "openrouter-key",
                "GOOGLE_DRIVE_AUTH_MODE": "service_account",
            }
            with patch.dict(os.environ, env, clear=True):
                request = ConfigLoadRequest(schema_version="1.0", path=cfg_path)
                ctx = RunContext(
                    schema_version="1.0", run_id="r", task_id="t", span_id="s"
                )
                app_settings = load_settings(request, ctx)
                inventory_settings = load_publisher_inventory_settings(request, ctx)

        self.assertEqual("./out/custom-cost-daily.json", app_settings.cost_daily_path)
        self.assertEqual(pricing, app_settings.model_pricing)
        self.assertEqual(pricing, inventory_settings.model_pricing)
        self.assertEqual("gpt-5", app_settings.openai_model)
        self.assertEqual(0.5, app_settings.temperature)
        self.assertEqual(2, app_settings.report_worker_limit)

    def test_cross_report_analysis_settings_load_defaults_and_config_values(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg_path = self._write_config(tmp_dir, include_analysis=False)
            with patch.dict(os.environ, {"OPENAI_API_KEY": "key"}, clear=True):
                default_settings = load_settings(
                    ConfigLoadRequest(schema_version="1.0", path=cfg_path),
                    RunContext(
                        schema_version="1.0", run_id="r", task_id="t", span_id="s"
                    ),
                )

            self.assertFalse(default_settings.cross_report_analysis_enabled)
            self.assertEqual(
                6, default_settings.cross_report_analysis_max_source_reports
            )
            self.assertEqual(
                48, default_settings.cross_report_analysis_max_evidence_items
            )
            self.assertEqual(
                60000, default_settings.cross_report_analysis_max_prompt_chars
            )
            self.assertEqual(
                "cross_report_analysis/synthesis",
                default_settings.cross_report_analysis_prompt_namespace,
            )
            self.assertEqual("gpt-5-mini", default_settings.cross_report_analysis_model)
            self.assertEqual(1.0, default_settings.cross_report_analysis_temperature)
            self.assertEqual(
                600.0, default_settings.cross_report_analysis_timeout_seconds
            )
            self.assertTrue(default_settings.cross_report_analysis_cache_enabled)
            self.assertTrue(default_settings.cross_report_analysis_auto_theme_enabled)
            self.assertEqual(
                30,
                default_settings.cross_report_analysis_theme_rotation_window_days,
            )
            self.assertEqual(
                2,
                default_settings.cross_report_analysis_min_theme_source_publishers,
            )
            self.assertFalse(default_settings.cross_report_analysis_publish_enabled)
            self.assertTrue(
                default_settings.cross_report_analysis_publish_requires_validation_pass
            )
            self.assertEqual(
                {
                    "contradiction": 0.5,
                    "diversity": 1.0,
                    "recency": 1.0,
                    "recurrence": 1.0,
                    "support": 1.0,
                    "taxonomy_fit": 1.0,
                },
                default_settings.cross_report_analysis_signal_score_weights,
            )

            cfg_data = yaml.safe_load(Path(cfg_path).read_text(encoding="utf-8"))
            cfg_data["cross_report_analysis"] = {
                "enabled": True,
                "max_source_reports": 5,
                "max_evidence_items": 24,
                "max_prompt_chars": 32000,
                "prompt_namespace": "cross_report_analysis/synthesis",
                "model": "gpt-5",
                "temperature": 0.5,
                "timeout_seconds": 900,
                "cache_enabled": False,
                "auto_theme_enabled": False,
                "theme_rotation_window_days": 45,
                "min_theme_source_publishers": 3,
                "publish_enabled": True,
                "publish_requires_validation_pass": True,
                "signal_score_weights": {
                    "recurrence": 2.0,
                    "diversity": 1.5,
                    "recency": 0.5,
                    "taxonomy_fit": 3.0,
                    "support": 1.25,
                    "contradiction": 0.25,
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

        self.assertTrue(settings.cross_report_analysis_enabled)
        self.assertEqual(5, settings.cross_report_analysis_max_source_reports)
        self.assertEqual(24, settings.cross_report_analysis_max_evidence_items)
        self.assertEqual(32000, settings.cross_report_analysis_max_prompt_chars)
        self.assertEqual("gpt-5", settings.cross_report_analysis_model)
        self.assertEqual(0.5, settings.cross_report_analysis_temperature)
        self.assertEqual(900.0, settings.cross_report_analysis_timeout_seconds)
        self.assertFalse(settings.cross_report_analysis_cache_enabled)
        self.assertFalse(settings.cross_report_analysis_auto_theme_enabled)
        self.assertEqual(45, settings.cross_report_analysis_theme_rotation_window_days)
        self.assertEqual(3, settings.cross_report_analysis_min_theme_source_publishers)
        self.assertTrue(settings.cross_report_analysis_publish_enabled)
        self.assertEqual(
            {
                "contradiction": 0.25,
                "diversity": 1.5,
                "recency": 0.5,
                "recurrence": 2.0,
                "support": 1.25,
                "taxonomy_fit": 3.0,
            },
            settings.cross_report_analysis_signal_score_weights,
        )

    def test_cross_report_analysis_settings_reject_invalid_limits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg_path = self._write_config(tmp_dir, include_analysis=False)
            cfg_data = yaml.safe_load(Path(cfg_path).read_text(encoding="utf-8"))
            cfg_data["cross_report_analysis"] = {
                "max_source_reports": 0,
                "max_evidence_items": 24,
                "max_prompt_chars": 32000,
                "prompt_namespace": "cross_report_analysis/synthesis",
                "model": "gpt-5-mini",
                "temperature": 1.0,
                "timeout_seconds": 600,
                "theme_rotation_window_days": 30,
                "min_theme_source_publishers": 2,
            }
            Path(cfg_path).write_text(yaml.safe_dump(cfg_data), encoding="utf-8")

            with patch.dict(os.environ, {"OPENAI_API_KEY": "key"}, clear=True):
                with self.assertRaises(AppError) as ctx:
                    load_settings(
                        ConfigLoadRequest(schema_version="1.0", path=cfg_path),
                        RunContext(
                            schema_version="1.0",
                            run_id="r",
                            task_id="t",
                            span_id="s",
                        ),
                    )

        self.assertEqual("cross_report_analysis_config_invalid", ctx.exception.code)
        self.assertFalse(ctx.exception.retryable)
        self.assertEqual("error", ctx.exception.severity)
        self.assertEqual("max_source_reports", ctx.exception.context["field"])

    def test_cross_report_analysis_settings_reject_malformed_limit_values(self) -> None:
        for field_name, raw_value in (
            ("max_source_reports", "many"),
            ("max_evidence_items", "several"),
            ("max_prompt_chars", "30k"),
        ):
            with self.subTest(field_name=field_name):
                with tempfile.TemporaryDirectory() as tmp_dir:
                    cfg_path = self._write_config(tmp_dir, include_analysis=False)
                    cfg_data = yaml.safe_load(
                        Path(cfg_path).read_text(encoding="utf-8")
                    )
                    cfg_data["cross_report_analysis"] = {field_name: raw_value}
                    Path(cfg_path).write_text(
                        yaml.safe_dump(cfg_data), encoding="utf-8"
                    )

                    with patch.dict(os.environ, {"OPENAI_API_KEY": "key"}, clear=True):
                        with self.assertRaises(AppError) as ctx:
                            load_settings(
                                ConfigLoadRequest(schema_version="1.0", path=cfg_path),
                                RunContext(
                                    schema_version="1.0",
                                    run_id="r",
                                    task_id="t",
                                    span_id="s",
                                ),
                            )

                self.assertEqual(
                    "cross_report_analysis_config_invalid", ctx.exception.code
                )
                self.assertEqual(field_name, ctx.exception.context["field"])

    def test_cross_report_analysis_settings_reject_blank_required_strings(self) -> None:
        for field_name, raw_value in (("prompt_namespace", ""), ("model", "   ")):
            with self.subTest(field_name=field_name):
                with tempfile.TemporaryDirectory() as tmp_dir:
                    cfg_path = self._write_config(tmp_dir, include_analysis=False)
                    cfg_data = yaml.safe_load(
                        Path(cfg_path).read_text(encoding="utf-8")
                    )
                    cfg_data["cross_report_analysis"] = {field_name: raw_value}
                    Path(cfg_path).write_text(
                        yaml.safe_dump(cfg_data), encoding="utf-8"
                    )

                    with patch.dict(os.environ, {"OPENAI_API_KEY": "key"}, clear=True):
                        with self.assertRaises(AppError) as ctx:
                            load_settings(
                                ConfigLoadRequest(schema_version="1.0", path=cfg_path),
                                RunContext(
                                    schema_version="1.0",
                                    run_id="r",
                                    task_id="t",
                                    span_id="s",
                                ),
                            )

                self.assertEqual(
                    "cross_report_analysis_config_invalid", ctx.exception.code
                )
                self.assertEqual(field_name, ctx.exception.context["field"])

    def test_ingest_worker_limit_defaults_and_env_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg_path = self._write_config(tmp_dir, include_analysis=False)
            cfg_data = yaml.safe_load(Path(cfg_path).read_text(encoding="utf-8"))
            cfg_data["ingest"]["worker_limit"] = 3
            Path(cfg_path).write_text(yaml.safe_dump(cfg_data), encoding="utf-8")

            with patch.dict(os.environ, {"OPENAI_API_KEY": "key"}, clear=True):
                settings = load_settings(
                    ConfigLoadRequest(schema_version="1.0", path=cfg_path),
                    RunContext(
                        schema_version="1.0", run_id="r", task_id="t", span_id="s"
                    ),
                )
                self.assertEqual(3, settings.ingest_worker_limit)

            cfg_data = yaml.safe_load(Path(cfg_path).read_text(encoding="utf-8"))
            cfg_data["ingest"].pop("worker_limit", None)
            Path(cfg_path).write_text(yaml.safe_dump(cfg_data), encoding="utf-8")

            with patch.dict(os.environ, {"OPENAI_API_KEY": "key"}, clear=True):
                settings = load_settings(
                    ConfigLoadRequest(schema_version="1.0", path=cfg_path),
                    RunContext(
                        schema_version="1.0", run_id="r", task_id="t", span_id="s"
                    ),
                )
                self.assertEqual(2, settings.ingest_worker_limit)

            with patch.dict(
                os.environ,
                {"OPENAI_API_KEY": "key", "INGEST_WORKER_LIMIT": "2"},
                clear=True,
            ):
                settings = load_settings(
                    ConfigLoadRequest(schema_version="1.0", path=cfg_path),
                    RunContext(
                        schema_version="1.0", run_id="r", task_id="t", span_id="s"
                    ),
                )
                self.assertEqual(2, settings.ingest_worker_limit)

    def test_report_worker_limit_defaults_and_env_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg_path = self._write_config(tmp_dir, include_analysis=False)
            cfg_data = yaml.safe_load(Path(cfg_path).read_text(encoding="utf-8"))
            cfg_data["ingest"]["report_worker_limit"] = 4
            Path(cfg_path).write_text(yaml.safe_dump(cfg_data), encoding="utf-8")

            with patch.dict(os.environ, {"OPENAI_API_KEY": "key"}, clear=True):
                settings = load_settings(
                    ConfigLoadRequest(schema_version="1.0", path=cfg_path),
                    RunContext(
                        schema_version="1.0", run_id="r", task_id="t", span_id="s"
                    ),
                )
                self.assertEqual(4, settings.report_worker_limit)

            cfg_data = yaml.safe_load(Path(cfg_path).read_text(encoding="utf-8"))
            cfg_data["ingest"].pop("report_worker_limit", None)
            Path(cfg_path).write_text(yaml.safe_dump(cfg_data), encoding="utf-8")

            with patch.dict(os.environ, {"OPENAI_API_KEY": "key"}, clear=True):
                settings = load_settings(
                    ConfigLoadRequest(schema_version="1.0", path=cfg_path),
                    RunContext(
                        schema_version="1.0", run_id="r", task_id="t", span_id="s"
                    ),
                )
                self.assertEqual(2, settings.report_worker_limit)

            with patch.dict(
                os.environ,
                {"OPENAI_API_KEY": "key", "INGEST_REPORT_WORKER_LIMIT": "2"},
                clear=True,
            ):
                settings = load_settings(
                    ConfigLoadRequest(schema_version="1.0", path=cfg_path),
                    RunContext(
                        schema_version="1.0", run_id="r", task_id="t", span_id="s"
                    ),
                )
                self.assertEqual(2, settings.report_worker_limit)

    def test_artifact_parallel_settings_defaults_and_env_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg_path = self._write_config(tmp_dir, include_analysis=False)
            with patch.dict(os.environ, {"OPENAI_API_KEY": "key"}, clear=True):
                settings = load_settings(
                    ConfigLoadRequest(schema_version="1.0", path=cfg_path),
                    RunContext(
                        schema_version="1.0", run_id="r", task_id="t", span_id="s"
                    ),
                )
                self.assertEqual(4, settings.artifact_parallel_workers)
                self.assertEqual(2, settings.artifact_global_max_in_flight)
                self.assertEqual(250, settings.artifact_global_min_interval_ms)

            env = {
                "OPENAI_API_KEY": "key",
                "ARTIFACT_PARALLEL_WORKERS": "3",
                "ARTIFACT_GLOBAL_MAX_IN_FLIGHT": "1",
                "ARTIFACT_GLOBAL_MIN_INTERVAL_MS": "0",
            }
            with patch.dict(os.environ, env, clear=True):
                settings = load_settings(
                    ConfigLoadRequest(schema_version="1.0", path=cfg_path),
                    RunContext(
                        schema_version="1.0", run_id="r", task_id="t", span_id="s"
                    ),
                )
                self.assertEqual(3, settings.artifact_parallel_workers)
                self.assertEqual(1, settings.artifact_global_max_in_flight)
                self.assertEqual(0, settings.artifact_global_min_interval_ms)

    def test_doc_map_retry_settings_defaults_and_env_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg_path = self._write_config(tmp_dir, include_analysis=False)
            with patch.dict(os.environ, {"OPENAI_API_KEY": "key"}, clear=True):
                settings = load_settings(
                    ConfigLoadRequest(schema_version="1.0", path=cfg_path),
                    RunContext(
                        schema_version="1.0", run_id="r", task_id="t", span_id="s"
                    ),
                )
                self.assertEqual(3, settings.evidence_pack_doc_map_max_attempts)
                self.assertEqual(500, settings.evidence_pack_doc_map_retry_delay_ms)

            cfg_data = yaml.safe_load(Path(cfg_path).read_text(encoding="utf-8"))
            cfg_data["ingest"]["evidence_packs"] = {
                "doc_map_max_attempts": 4,
                "doc_map_retry_delay_ms": 250,
            }
            Path(cfg_path).write_text(yaml.safe_dump(cfg_data), encoding="utf-8")
            with patch.dict(os.environ, {"OPENAI_API_KEY": "key"}, clear=True):
                settings = load_settings(
                    ConfigLoadRequest(schema_version="1.0", path=cfg_path),
                    RunContext(
                        schema_version="1.0", run_id="r", task_id="t", span_id="s"
                    ),
                )
                self.assertEqual(4, settings.evidence_pack_doc_map_max_attempts)
                self.assertEqual(250, settings.evidence_pack_doc_map_retry_delay_ms)

            cfg_data = yaml.safe_load(Path(cfg_path).read_text(encoding="utf-8"))
            cfg_data["ingest"]["evidence_packs"] = {}
            Path(cfg_path).write_text(yaml.safe_dump(cfg_data), encoding="utf-8")
            env = {
                "OPENAI_API_KEY": "key",
                "EVIDENCE_PACK_DOC_MAP_MAX_ATTEMPTS": "2",
                "EVIDENCE_PACK_DOC_MAP_RETRY_DELAY_MS": "0",
            }
            with patch.dict(os.environ, env, clear=True):
                settings = load_settings(
                    ConfigLoadRequest(schema_version="1.0", path=cfg_path),
                    RunContext(
                        schema_version="1.0", run_id="r", task_id="t", span_id="s"
                    ),
                )
                self.assertEqual(2, settings.evidence_pack_doc_map_max_attempts)
                self.assertEqual(0, settings.evidence_pack_doc_map_retry_delay_ms)

    def test_validation_regeneration_attempts_default_config_and_env_override(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg_path = self._write_config(tmp_dir, include_analysis=False)
            with patch.dict(os.environ, {"OPENAI_API_KEY": "key"}, clear=True):
                settings = load_settings(
                    ConfigLoadRequest(schema_version="1.0", path=cfg_path),
                    RunContext(
                        schema_version="1.0", run_id="r", task_id="t", span_id="s"
                    ),
                )
                self.assertEqual(3, settings.validation_regeneration_max_attempts)

            cfg_data = yaml.safe_load(Path(cfg_path).read_text(encoding="utf-8"))
            cfg_data["ingest"]["validation"] = {"regeneration_max_attempts": 5}
            Path(cfg_path).write_text(yaml.safe_dump(cfg_data), encoding="utf-8")
            with patch.dict(os.environ, {"OPENAI_API_KEY": "key"}, clear=True):
                settings = load_settings(
                    ConfigLoadRequest(schema_version="1.0", path=cfg_path),
                    RunContext(
                        schema_version="1.0", run_id="r", task_id="t", span_id="s"
                    ),
                )
                self.assertEqual(5, settings.validation_regeneration_max_attempts)

            cfg_data = yaml.safe_load(Path(cfg_path).read_text(encoding="utf-8"))
            cfg_data["ingest"]["validation"] = {}
            Path(cfg_path).write_text(yaml.safe_dump(cfg_data), encoding="utf-8")
            env = {
                "OPENAI_API_KEY": "key",
                "VALIDATION_REGENERATION_MAX_ATTEMPTS": "0",
            }
            with patch.dict(os.environ, env, clear=True):
                settings = load_settings(
                    ConfigLoadRequest(schema_version="1.0", path=cfg_path),
                    RunContext(
                        schema_version="1.0", run_id="r", task_id="t", span_id="s"
                    ),
                )
                self.assertEqual(1, settings.validation_regeneration_max_attempts)

    def test_rank_and_crop_refine_settings_load(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg_path = self._write_config(tmp_dir, include_analysis=False)
            cfg_data = yaml.safe_load(Path(cfg_path).read_text(encoding="utf-8"))
            cfg_data["rank"] = {
                "model": "gpt-5-mini",
                "temperature": 0.2,
                "timeout_seconds": 120.0,
                "max_candidates": 30,
                "selected_max": 5,
                "min_overall_score": 79,
                "min_quality_score": 76,
                "min_insight_score": 77,
                "min_data_score": 71,
                "crop_refine_enabled": True,
                "crop_refine_mode": "invalid-mode",
                "crop_refine_page_dpi": 111,
                "crop_refine_temperature": 0.0,
            }
            Path(cfg_path).write_text(yaml.safe_dump(cfg_data), encoding="utf-8")

            with patch.dict(os.environ, {"OPENAI_API_KEY": "key"}, clear=True):
                settings = load_settings(
                    ConfigLoadRequest(schema_version="1.0", path=cfg_path),
                    RunContext(
                        schema_version="1.0", run_id="r", task_id="t", span_id="s"
                    ),
                )

        self.assertEqual(30, settings.rank_max_candidates)
        self.assertEqual(5, settings.rank_selected_max)
        self.assertEqual(79, settings.rank_min_overall_score)
        self.assertEqual(76, settings.rank_min_quality_score)
        self.assertEqual(77, settings.rank_min_insight_score)
        self.assertEqual(71, settings.rank_min_data_score)
        self.assertTrue(settings.crop_refine_enabled)
        self.assertEqual("adaptive", settings.crop_refine_mode)
        self.assertEqual(111, settings.crop_refine_page_dpi)
        self.assertEqual(0.0, settings.crop_refine_temperature)
        self.assertEqual(
            settings.rank_timeout_seconds, settings.crop_refine_timeout_seconds
        )

    def test_candidate_page_gate_settings_load(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg_path = self._write_config(tmp_dir, include_analysis=False)
            cfg_data = yaml.safe_load(Path(cfg_path).read_text(encoding="utf-8"))
            cfg_data["ingest"]["candidate_page_gate"] = {
                "enabled": True,
                "min_score": 0.31,
                "min_recall_pages": 7,
                "min_recall_page_fraction": 0.42,
            }
            Path(cfg_path).write_text(yaml.safe_dump(cfg_data), encoding="utf-8")

            with patch.dict(os.environ, {"OPENAI_API_KEY": "key"}, clear=True):
                settings = load_settings(
                    ConfigLoadRequest(schema_version="1.0", path=cfg_path),
                    RunContext(
                        schema_version="1.0", run_id="r", task_id="t", span_id="s"
                    ),
                )

        self.assertTrue(settings.candidate_page_gate_enabled)
        self.assertEqual(0.31, settings.candidate_page_gate_min_score)
        self.assertEqual(7, settings.candidate_page_gate_min_recall_pages)
        self.assertEqual(0.42, settings.candidate_page_gate_min_recall_page_fraction)

__all__ = ["TestConfigService01DefaultsUseVectorMode"]
