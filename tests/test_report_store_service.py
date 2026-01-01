import os
import tempfile
import time
import unittest

from src.contracts.report_store import ReportMetadataGetRequest, ReportMetadataUpsertRequest
from src.services.report_store_service import get_metadata, upsert_metadata
from src.utils.errors import AppError
from src.utils.logging import new_run_context


class TestReportStoreService(unittest.TestCase):
    def test_upsert_and_get_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "reports.sqlite")
            ctx = new_run_context(task_id="test_metadata")

            upsert_metadata(
                ReportMetadataUpsertRequest(
                    schema_version="1.0",
                    db_path=db_path,
                    file_id="file-1",
                    title="Sample Report",
                    publisher="Publisher Inc",
                    taxonomy=["Ads", "  Measurement", ""],
                    region="US",
                    time_period="2024-2028",
                    source_url="https://example.com/report",
                    html_path="/tmp/report.html",
                    md5="abc123",
                ),
                ctx,
            )
            first = get_metadata(
                ReportMetadataGetRequest(schema_version="1.0", db_path=db_path, file_id="file-1"),
                ctx,
            )
            self.assertIsNotNone(first)
            assert first is not None
            self.assertEqual("Sample Report", first.title)
            self.assertEqual(["Ads", "Measurement"], first.taxonomy)
            self.assertEqual("Publisher Inc", first.publisher)
            self.assertEqual("US", first.region)
            self.assertEqual("2024-2028", first.time_period)
            self.assertEqual("https://example.com/report", first.source_url)
            self.assertEqual("/tmp/report.html", first.html_path)
            self.assertEqual("abc123", first.md5)
            self.assertGreater(first.created_at, 0)

            time.sleep(0.01)
            upsert_metadata(
                ReportMetadataUpsertRequest(
                    schema_version="1.0",
                    db_path=db_path,
                    file_id="file-1",
                    title="Updated Title",
                    publisher=None,
                    taxonomy=["Measurement", "Attribution"],
                    region="North America",
                    time_period="2025",
                    source_url=None,
                    html_path="/tmp/report-v2.html",
                    md5="def456",
                ),
                ctx,
            )
            second = get_metadata(
                ReportMetadataGetRequest(schema_version="1.0", db_path=db_path, file_id="file-1"),
                ctx,
            )
            assert second is not None
            self.assertEqual("Updated Title", second.title)
            self.assertEqual(["Measurement", "Attribution"], second.taxonomy)
            self.assertEqual(first.created_at, second.created_at)
            self.assertGreaterEqual(second.updated_at, second.created_at)
            self.assertEqual("def456", second.md5)
            self.assertEqual("/tmp/report-v2.html", second.html_path)
            self.assertIsNone(second.publisher)
            self.assertIsNone(second.source_url)
            self.assertEqual("North America", second.region)
            self.assertEqual("2025", second.time_period)

    def test_missing_record_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "reports.sqlite")
            ctx = new_run_context(task_id="test_missing")
            resp = get_metadata(
                ReportMetadataGetRequest(schema_version="1.0", db_path=db_path, file_id="missing"),
                ctx,
            )
            self.assertIsNone(resp)

    def test_upsert_requires_title_and_file_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "reports.sqlite")
            ctx = new_run_context(task_id="test_validation")
            with self.assertRaises(AppError):
                upsert_metadata(
                    ReportMetadataUpsertRequest(
                        schema_version="1.0",
                        db_path=db_path,
                        file_id="",
                        title="",
                        publisher=None,
                        taxonomy=[],
                        source_url=None,
                        html_path=None,
                        md5=None,
                    ),
                    ctx,
                )


if __name__ == "__main__":
    unittest.main()
