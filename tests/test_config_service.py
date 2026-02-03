import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import yaml

from src.contracts.config import ConfigLoadRequest
from src.contracts.run_context import RunContext
from src.services.config_service import load_settings, load_publish_settings


class TestConfigService(unittest.TestCase):
    def _write_config(self, tmp_dir: str, include_analysis: bool = False, include_publish: bool = False) -> str:
        config_path = Path(tmp_dir) / "app.yaml"
        config = {
            "schema_version": "1.0",
            "paths": {
                "output_dir": str(Path(tmp_dir, "out")),
                "cache_dir": str(Path(tmp_dir, "cache")),
                "state_db": str(Path(tmp_dir, "state", "index.sqlite")),
                "reports_db": str(Path(tmp_dir, "state", "reports.sqlite")),
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
        self.assertEqual("./out/cost-ledger.jsonl", settings.cost_ledger_path)

    def test_env_overrides_analysis_mode_and_flags(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg_path = self._write_config(tmp_dir, include_analysis=True)
            env = {
                "OPENAI_API_KEY": "key",
                "ANALYSIS_MODE": "vector_store",
                "VECTOR_STORE_KEEP": "false",
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
        self.assertEqual(f"{tmp_dir}/ledger.jsonl", settings.cost_ledger_path)
        self.assertEqual("./out/cost-daily.json", settings.cost_daily_path)
        self.assertIsInstance(settings.model_pricing, dict)

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


if __name__ == "__main__":
    unittest.main()
