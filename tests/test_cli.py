import sys
import types
import unittest
from unittest.mock import patch

from src.contracts.config import AppSettings
from src.contracts.ingest import IngestOutcome, IngestSettings


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
            temperature=1.0,
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

        with patch.object(cli, "load_settings", return_value=settings) as load_settings_mock:
            with patch.object(cli, "run_ingest", return_value=outcomes) as run_ingest_mock:
                cli.ingest(folder=None, limit=1)
                load_settings_mock.assert_called_once()
                run_ingest_mock.assert_called_once()
                passed_settings = run_ingest_mock.call_args.args[0]
                self.assertIsInstance(passed_settings, IngestSettings)
                self.assertEqual("folder", passed_settings.gdrive_folder_id)
                self.assertEqual("gpt-5", passed_settings.openai_model)


if __name__ == "__main__":
    unittest.main()
