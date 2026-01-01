import unittest
from unittest.mock import patch

from src.contracts.drive import DriveFile, DriveDownloadResponse
from src.contracts.ingest import IngestSettings
from src.utils.errors import AppError
from src.orchestrators import ingest_orchestrator as orch


class TestOrchestratorRetry(unittest.TestCase):
    def test_retry_on_retryable_app_error(self) -> None:
        settings = IngestSettings(
            schema_version="1.0",
            google_sa_path="sa.json",
            gdrive_folder_id="folder",
            openai_api_key="key",
            openai_model="gpt-5",
            batch_limit=1,
            output_dir="./out",
            cache_dir="./cache",
            state_db=":memory:",
            reports_db=":memory:",
            ingest_lock_path="./state/ingest.lock",
            ingest_lock_ttl_seconds=7200.0,
            temperature=1.0,
        )

        drive_file = DriveFile(
            schema_version="1.0",
            file_id="file",
            name="name.pdf",
            modified_time=None,
            md5_checksum="md5",
            version=None,
        )
        download_resp = DriveDownloadResponse(
            schema_version="1.0",
            file=drive_file,
            content=b"pdf-bytes",
            md5="md5",
            size=9,
        )

        retry_error = AppError(
            code="openai_request_failed",
            message="retry",
            retryable=True,
        )

        with patch.object(orch, "list_pdfs", return_value=[drive_file]):
            with patch.object(orch, "download_pdf", return_value=download_resp):
                with patch.object(orch, "file_exists", return_value=type("E", (), {"exists": False})()):
                    with patch.object(orch, "write_bytes", return_value=type("W", (), {"md5": "md5"})()):
                        with patch.object(orch, "check_pdf_eof", return_value=type("X", (), {"has_eof": True})()):
                            with patch.object(orch.time, "sleep", return_value=None):
                                with patch.object(orch, "generate_report", side_effect=[retry_error, retry_error, retry_error]):
                                    outcomes = orch.run_ingest(settings, limit=1)
                                    self.assertEqual(1, len(outcomes))
                                    self.assertEqual("error", outcomes[0].status)


if __name__ == "__main__":
    unittest.main()
