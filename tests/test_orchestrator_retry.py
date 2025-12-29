import unittest
from unittest.mock import patch

from src.contracts.drive import DriveFile, DriveDownloadResponse
from src.contracts.ingest import IngestSettings
from src.services.state_service import StateStore
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
            local_path="cache/name.pdf",
            md5="md5",
        )

        retry_error = AppError(
            code="openai_request_failed",
            message="retry",
            retryable=True,
        )

        with patch.object(orch, "build_drive_client", return_value=object()):
            with patch.object(orch, "list_pdfs", return_value=[drive_file]):
                with patch.object(orch, "download_pdf", return_value=download_resp):
                    with patch.object(orch, "check_pdf_eof", return_value=type("X", (), {"has_eof": True})()):
                        with patch.object(orch, "StateStore", return_value=StateStore(":memory:")):
                            with patch.object(orch, "generate_report", side_effect=[retry_error, retry_error, retry_error]):
                                outcomes = orch.run_ingest(settings, limit=1)
                                self.assertEqual(1, len(outcomes))
                                self.assertEqual("error", outcomes[0].status)


if __name__ == "__main__":
    unittest.main()
