import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import yaml

from src.contracts.config import ConfigLoadRequest
from src.contracts.run_context import RunContext
from src.services.config_service import load_settings


class TestConfigService(unittest.TestCase):
    def _write_config(self, tmp_dir: str, include_analysis: bool = False) -> str:
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
                "mode": "local_text",
                "use_vector_store": False,
                "vector_store_keep": True,
                "cost_ledger_path": "./out/cost-ledger.jsonl",
            }
        config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
        return str(config_path)

    def test_defaults_use_local_text_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg_path = self._write_config(tmp_dir, include_analysis=False)
            with patch.dict(os.environ, {"OPENAI_API_KEY": "key"}, clear=True):
                settings = load_settings(
                    ConfigLoadRequest(schema_version="1.0", path=cfg_path),
                    RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s"),
                )

        self.assertEqual("local_text", settings.analysis_mode)
        self.assertFalse(settings.use_vector_store)
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


if __name__ == "__main__":
    unittest.main()
