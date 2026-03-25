import os
import pytest
import sqlite3
import tempfile
import time
import unittest

from src.contracts.report_store import (
    ReportMetadataDbAccessRequest,
    ReportMetadataGetRequest,
    ReportMetadataUpsertRequest,
)
from src.services.report_store_service import (
    check_report_db_access,
    get_metadata,
    upsert_metadata,
)
from src.utils.errors import AppError
from src.utils.logging import new_run_context


class TestReportStoreService(unittest.TestCase):
    def test_upsert_and_get_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "reports.sqlite")
            ctx = new_run_context(task_id="test_metadata")

            upsert_metadata(
                ReportMetadataUpsertRequest(
                    schema_version="1.1",
                    db_path=db_path,
                    file_id="file-1",
                    title="Sample Report",
                    file_name="source-report.pdf",
                    publisher="Publisher Inc",
                    taxonomy=["Ads", "  Measurement", ""],
                    region="US",
                    time_period="Q1 to Q3 2026",
                    source_url="https://example.com/report",
                    html_path="/tmp/report.html",
                    md5="abc123",
                    contents_page_number=5,
                ),
                ctx,
            )
            first = get_metadata(
                ReportMetadataGetRequest(schema_version="1.1", db_path=db_path, file_id="file-1"),
                ctx,
            )
            self.assertIsNotNone(first)
            assert first is not None
            self.assertEqual("Sample Report", first.title)
            self.assertEqual("source-report.pdf", first.file_name)
            self.assertEqual(["Ads", "Measurement"], first.taxonomy)
            self.assertEqual("Publisher Inc", first.publisher)
            self.assertEqual("US", first.region)
            self.assertEqual("Q1 2026, Q2 2026, Q3 2026", first.time_period)
            self.assertEqual("https://example.com/report", first.source_url)
            self.assertEqual("/tmp/report.html", first.html_path)
            self.assertEqual("abc123", first.md5)
            self.assertGreater(first.created_at, 0)
            self.assertEqual(5, first.contents_page_number)

            time.sleep(0.01)
            upsert_metadata(
                ReportMetadataUpsertRequest(
                    schema_version="1.1",
                    db_path=db_path,
                    file_id="file-1",
                    title="Updated Title",
                    publisher=None,
                    taxonomy=["Measurement", "Attribution"],
                    region="North America",
                    time_period="june to novemeber 2023",
                    source_url=None,
                    html_path="/tmp/report-v2.html",
                    md5="def456",
                    contents_page_number=0,
                ),
                ctx,
            )
            second = get_metadata(
                ReportMetadataGetRequest(schema_version="1.1", db_path=db_path, file_id="file-1"),
                ctx,
            )
            assert second is not None
            self.assertEqual("Updated Title", second.title)
            self.assertEqual(["Measurement", "Attribution"], second.taxonomy)
            self.assertEqual(first.created_at, second.created_at)
            self.assertGreaterEqual(second.updated_at, second.created_at)
            self.assertEqual("def456", second.md5)
            self.assertEqual("/tmp/report-v2.html", second.html_path)
            self.assertEqual("source-report.pdf", second.file_name)
            self.assertIsNone(second.publisher)
            self.assertIsNone(second.source_url)
            self.assertEqual("North America", second.region)
            self.assertEqual("Jun 2023, Jul 2023, Aug 2023, Sep 2023, Oct 2023, Nov 2023", second.time_period)
            self.assertEqual(0, second.contents_page_number)

            time.sleep(0.01)
            upsert_metadata(
                ReportMetadataUpsertRequest(
                    schema_version="1.1",
                    db_path=db_path,
                    file_id="file-1",
                    title="Final Title",
                    publisher="Publisher Inc",
                    taxonomy=["Measurement"],
                    region="United Kingdom",
                    time_period="2026 (looking ahead / next 12 months, fieldwork Oct 2025)",
                    source_url="https://example.com/final",
                    html_path="/tmp/report-v3.html",
                    md5="ghi789",
                    contents_page_number=0,
                ),
                ctx,
            )
            third = get_metadata(
                ReportMetadataGetRequest(schema_version="1.1", db_path=db_path, file_id="file-1"),
                ctx,
            )
            assert third is not None
            self.assertEqual("2026", third.time_period)

    def test_missing_record_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "reports.sqlite")
            ctx = new_run_context(task_id="test_missing")
            resp = get_metadata(
                ReportMetadataGetRequest(schema_version="1.1", db_path=db_path, file_id="missing"),
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
                        schema_version="1.1",
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

    def test_report_db_access_detects_lock(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "reports.sqlite")
            conn = sqlite3.connect(db_path)
            conn.execute("BEGIN EXCLUSIVE")
            try:
                resp = check_report_db_access(
                    ReportMetadataDbAccessRequest(schema_version="1.0", db_path=db_path, timeout_seconds=0.0),
                    new_run_context(task_id="test_db_access_lock"),
                )
                self.assertFalse(resp.accessible)
                self.assertTrue(resp.locked)
            finally:
                conn.rollback()
                conn.close()

    def test_report_db_access_allows_unlocked_db(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "reports.sqlite")
            resp = check_report_db_access(
                ReportMetadataDbAccessRequest(schema_version="1.0", db_path=db_path, timeout_seconds=0.0),
                new_run_context(task_id="test_db_access_ok"),
            )
            self.assertTrue(resp.accessible)
            self.assertFalse(resp.locked)


if __name__ == "__main__":
    unittest.main()


def test_report_db_access_connect_failure_is_typed_app_error(assert_app_error) -> None:
    ctx = new_run_context(task_id="test_db_access_connect_failure")

    original_connect = sqlite3.connect

    def _raise_connect(*args, **kwargs):
        raise sqlite3.OperationalError("connect boom")

    sqlite3.connect = _raise_connect
    try:
        with pytest.raises(AppError) as exc_info:
            check_report_db_access(
                ReportMetadataDbAccessRequest(
                    schema_version="1.0",
                    db_path="C:/tmp/reports.sqlite",
                    timeout_seconds=0.0,
                ),
                ctx,
            )
    finally:
        sqlite3.connect = original_connect

    assert_app_error(
        exc_info.value,
        code="metadata_db_unavailable",
        retryable=True,
    )
