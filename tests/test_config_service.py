import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import yaml

from src.contracts.config import AppConfigReadRequest, AppConfigWriteRequest, ConfigLoadRequest
from src.contracts.run_context import RunContext
from src.services.config_service import (
    load_publish_settings,
    load_settings,
    read_app_config,
    write_app_config,
)
from src.utils.errors import AppError


class TestConfigService(unittest.TestCase):
    def _write_config(self, tmp_dir: str, include_analysis: bool = False, include_publish: bool = False) -> str:
        config_path = Path(tmp_dir) / "app.yaml"
        acronyms_path = Path(tmp_dir) / "html-tag-acronyms.yaml"
        acronyms_path.write_text(
            yaml.safe_dump(
                {
                    "schema_version": "1.0",
                    "html_tag_acronyms": ["AI", "ROI", "CPC"],
                }
            ),
            encoding="utf-8",
        )
        config = {
            "schema_version": "1.0",
            "paths": {
                "output_dir": str(Path(tmp_dir, "out")),
                "cache_dir": str(Path(tmp_dir, "cache")),
                "state_db": str(Path(tmp_dir, "state", "index.sqlite")),
                "reports_db": str(Path(tmp_dir, "state", "reports.sqlite")),
                "html_tag_acronyms": str(acronyms_path),
            },
            "ingest": {
                "google_sa_path": str(Path(tmp_dir, "sa.json")),
                "gdrive_folder_id": "folder",
                "openai_model": "gpt-5",
                "temperature": 0.5,
            },
        }
        if include_analysis:
            config["analysis"] = {
                "mode": "vector_store",
                "use_vector_store": True,
                "vector_store_keep": True,
                "cost_ledger_path": "./out/cost-ledger.jsonl",
            }
        if include_publish:
            config["publish"] = {
                "wp": {
                    "username": "admin",
                }
            }
        config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
        return str(config_path)

    def test_defaults_use_vector_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg_path = self._write_config(tmp_dir, include_analysis=False)
            with patch.dict(os.environ, {"OPENAI_API_KEY": "key"}, clear=True):
                settings = load_settings(
                    ConfigLoadRequest(schema_version="1.0", path=cfg_path),
                    RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s"),
                )

        self.assertEqual("vector_store", settings.analysis_mode)
        self.assertTrue(settings.use_vector_store)
        self.assertTrue(settings.vector_store_keep)
        self.assertFalse(settings.artifacts_use_vector_store)
        self.assertFalse(settings.validation_grounding_use_vector_store)
        self.assertEqual("./out/cost-ledger.jsonl", settings.cost_ledger_path)
        self.assertIn("AI", settings.html_tag_acronyms)
        self.assertIn("ROI", settings.html_tag_acronyms)

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
                    RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s"),
                )

        self.assertEqual(["AI", "ROI", "CPC"], settings.html_tag_acronyms)

    def test_env_overrides_analysis_mode_and_flags(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg_path = self._write_config(tmp_dir, include_analysis=True)
            env = {
                "OPENAI_API_KEY": "key",
                "ANALYSIS_MODE": "vector_store",
                "VECTOR_STORE_KEEP": "false",
                "ARTIFACTS_USE_VECTOR_STORE": "true",
                "VALIDATION_GROUNDING_USE_VECTOR_STORE": "true",
                "COST_LEDGER_PATH": f"{tmp_dir}/ledger.jsonl",
            }
            with patch.dict(os.environ, env, clear=True):
                settings = load_settings(
                    ConfigLoadRequest(schema_version="1.0", path=cfg_path),
                    RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s"),
                )

        self.assertEqual("vector_store", settings.analysis_mode)
        self.assertTrue(settings.use_vector_store)
        self.assertFalse(settings.vector_store_keep)
        self.assertTrue(settings.artifacts_use_vector_store)
        self.assertTrue(settings.validation_grounding_use_vector_store)
        self.assertEqual(f"{tmp_dir}/ledger.jsonl", settings.cost_ledger_path)
        self.assertEqual("./out/cost-daily.json", settings.cost_daily_path)
        self.assertIsInstance(settings.model_pricing, dict)

    def test_ingest_worker_limit_defaults_and_env_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg_path = self._write_config(tmp_dir, include_analysis=False)
            cfg_data = yaml.safe_load(Path(cfg_path).read_text(encoding="utf-8"))
            cfg_data["ingest"]["worker_limit"] = 3
            Path(cfg_path).write_text(yaml.safe_dump(cfg_data), encoding="utf-8")

            with patch.dict(os.environ, {"OPENAI_API_KEY": "key"}, clear=True):
                settings = load_settings(
                    ConfigLoadRequest(schema_version="1.0", path=cfg_path),
                    RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s"),
                )
                self.assertEqual(3, settings.ingest_worker_limit)

            cfg_data = yaml.safe_load(Path(cfg_path).read_text(encoding="utf-8"))
            cfg_data["ingest"].pop("worker_limit", None)
            Path(cfg_path).write_text(yaml.safe_dump(cfg_data), encoding="utf-8")

            with patch.dict(os.environ, {"OPENAI_API_KEY": "key"}, clear=True):
                settings = load_settings(
                    ConfigLoadRequest(schema_version="1.0", path=cfg_path),
                    RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s"),
                )
                self.assertEqual(2, settings.ingest_worker_limit)

            with patch.dict(os.environ, {"OPENAI_API_KEY": "key", "INGEST_WORKER_LIMIT": "2"}, clear=True):
                settings = load_settings(
                    ConfigLoadRequest(schema_version="1.0", path=cfg_path),
                    RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s"),
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
                    RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s"),
                )
                self.assertEqual(4, settings.report_worker_limit)

            cfg_data = yaml.safe_load(Path(cfg_path).read_text(encoding="utf-8"))
            cfg_data["ingest"].pop("report_worker_limit", None)
            Path(cfg_path).write_text(yaml.safe_dump(cfg_data), encoding="utf-8")

            with patch.dict(os.environ, {"OPENAI_API_KEY": "key"}, clear=True):
                settings = load_settings(
                    ConfigLoadRequest(schema_version="1.0", path=cfg_path),
                    RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s"),
                )
                self.assertEqual(2, settings.report_worker_limit)

            with patch.dict(os.environ, {"OPENAI_API_KEY": "key", "INGEST_REPORT_WORKER_LIMIT": "2"}, clear=True):
                settings = load_settings(
                    ConfigLoadRequest(schema_version="1.0", path=cfg_path),
                    RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s"),
                )
                self.assertEqual(2, settings.report_worker_limit)

    def test_artifact_parallel_settings_defaults_and_env_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg_path = self._write_config(tmp_dir, include_analysis=False)
            with patch.dict(os.environ, {"OPENAI_API_KEY": "key"}, clear=True):
                settings = load_settings(
                    ConfigLoadRequest(schema_version="1.0", path=cfg_path),
                    RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s"),
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
                    RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s"),
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
                    RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s"),
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
                    RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s"),
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
                    RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s"),
                )
                self.assertEqual(2, settings.evidence_pack_doc_map_max_attempts)
                self.assertEqual(0, settings.evidence_pack_doc_map_retry_delay_ms)

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
                    RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s"),
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
        self.assertEqual(settings.rank_timeout_seconds, settings.crop_refine_timeout_seconds)

    def test_publish_settings_derive_site_url_from_admin(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg_path = self._write_config(tmp_dir, include_publish=True)
            env = {
                "WP_ADMIN_URL": "https://example.com/wp-admin/",
                "WP_SITE_URL": "",
                "WP_APP_PASSWORD": "app-pass",
                "WP_BEARER_TOKEN": "",
            }
            with patch.dict(os.environ, env, clear=True):
                settings = load_publish_settings(
                    ConfigLoadRequest(schema_version="1.0", path=cfg_path),
                    RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s"),
                )

        self.assertEqual("https://example.com", settings.wp.site_url)
        self.assertEqual("admin", settings.wp.username)
        self.assertEqual("app-pass", settings.wp.app_password)
        self.assertIsNone(settings.wp.bearer_token)

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
                        RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s"),
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
                        RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s"),
                    )
        self.assertIn("WP_APP_PASSWORD", str(ctx.exception))

    def test_read_and_write_app_config_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg_path = self._write_config(tmp_dir, include_analysis=True, include_publish=True)
            ctx = RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")
            read_response = read_app_config(
                AppConfigReadRequest(schema_version="1.0", path=cfg_path),
                ctx,
            )
            self.assertIn("ingest", read_response.payload)
            self.assertGreater(read_response.size_bytes, 0)
            self.assertIsNotNone(read_response.modified_utc)

            updated_payload = yaml.safe_load(read_response.content)
            updated_payload["ingest"]["batch_limit"] = 37
            updated_text = yaml.safe_dump(updated_payload, sort_keys=False)
            write_response = write_app_config(
                AppConfigWriteRequest(
                    schema_version="1.0",
                    path=cfg_path,
                    content=updated_text,
                    make_backup=True,
                ),
                ctx,
            )
            self.assertGreater(write_response.bytes_written, 0)
            self.assertIn("ingest", write_response.top_level_keys)
            self.assertIsNotNone(write_response.backup_path)
            self.assertTrue(Path(str(write_response.backup_path)).exists())

            final_payload = yaml.safe_load(Path(cfg_path).read_text(encoding="utf-8"))
            self.assertEqual(37, final_payload["ingest"]["batch_limit"])

    def test_write_app_config_rejects_non_mapping_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg_path = Path(tmp_dir) / "app.yaml"
            cfg_path.write_text("schema_version: '1.0'\n", encoding="utf-8")
            with self.assertRaises(AppError) as ctx:
                write_app_config(
                    AppConfigWriteRequest(
                        schema_version="1.0",
                        path=str(cfg_path),
                        content="- one\n- two\n",
                        make_backup=False,
                    ),
                    RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s"),
                )
            self.assertIn("mapping", str(ctx.exception).lower())


if __name__ == "__main__":
    unittest.main()
