import sys
import types
import unittest
from unittest.mock import patch

from src.contracts.config import AppSettings
from src.contracts.ingest import IngestOutcome, IngestSettings
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
            category_mapping_path="./src/config/category-mappings.yaml",
            ingest_lock_path="./state/ingest.lock",
            ingest_lock_ttl_seconds=7200.0,
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

        with patch.object(cli, "load_publish_settings", return_value=settings) as load_settings_mock:
            with patch.object(cli, "run_publish", return_value=outcomes) as run_publish_mock:
                cli.publish_wp(limit=1)
                load_settings_mock.assert_called_once()
                run_publish_mock.assert_called_once()
                passed_settings = run_publish_mock.call_args.args[0]
                self.assertIsInstance(passed_settings, PublishSettings)


if __name__ == "__main__":
    unittest.main()
