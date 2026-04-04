import os
import pytest
import sqlite3
import tempfile
import time
import unittest

from src.contracts.report_store import (
    PublisherDownloadRouteGetRequest,
    PublisherDownloadRouteRecordRequest,
    PublisherInventoryRunQualityRecordRequest,
    PublisherInventoryStateGetRequest,
    PublisherInventoryStateRecordRequest,
    PublisherInventoryTestStatusRecordRequest,
    PublishersReplaceRequest,
    ReportMetadataDbAccessRequest,
    ReportSourceDiscoveryRecordRequest,
    ReportMetadataGetRequest,
    ReportSourceRecordRequest,
    ReportMetadataUpsertRequest,
)
from src.contracts.publisher_inventory import PublisherInventoryRunQualitySummary
from src.contracts.publisher_profiles import PublisherProfileRecord
from src.services.report_store_service import (
    check_report_db_access,
    get_metadata,
    record_discovered_report_source,
    get_publisher_download_route,
    get_publisher_inventory_state,
    record_publisher_inventory_run_quality,
    record_publisher_inventory_test_status,
    record_report_source,
    record_publisher_download_route,
    record_publisher_inventory_state,
    replace_publishers,
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

    def test_report_db_uses_wal_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "reports.sqlite")
            ctx = new_run_context(task_id="test_db_wal")
            upsert_metadata(
                ReportMetadataUpsertRequest(
                    schema_version="1.1",
                    db_path=db_path,
                    file_id="file-wal",
                    title="WAL Report",
                    publisher=None,
                    taxonomy=[],
                    source_url=None,
                    html_path=None,
                    md5=None,
                ),
                ctx,
            )

            conn = sqlite3.connect(db_path)
            try:
                journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            finally:
                conn.close()

            self.assertEqual("wal", journal_mode.lower())

    def test_report_db_access_allows_active_wal_writer(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "reports.sqlite")
            ctx = new_run_context(task_id="test_db_access_writer_ok")
            upsert_metadata(
                ReportMetadataUpsertRequest(
                    schema_version="1.1",
                    db_path=db_path,
                    file_id="file-writer",
                    title="Writer Report",
                    publisher=None,
                    taxonomy=[],
                    source_url=None,
                    html_path=None,
                    md5=None,
                ),
                ctx,
            )

            conn = sqlite3.connect(db_path)
            conn.execute("BEGIN IMMEDIATE")
            try:
                resp = check_report_db_access(
                    ReportMetadataDbAccessRequest(
                        schema_version="1.0",
                        db_path=db_path,
                        timeout_seconds=0.0,
                    ),
                    new_run_context(task_id="test_db_access_writer_probe"),
                )
                self.assertTrue(resp.accessible)
                self.assertFalse(resp.locked)
            finally:
                conn.rollback()
                conn.close()

    def test_record_report_source_inserts_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "reports.sqlite")
            ctx = new_run_context(task_id="test_report_source_record")

            response = record_report_source(
                ReportSourceRecordRequest(
                    schema_version="1.0",
                    db_path=db_path,
                    source_domain="www.criteo.com",
                    report_name="Criteo Global Winter Travel Pulse 2025",
                    landing_page_url="https://www.criteo.com/resources/report",
                    downloaded_at_utc="2026-03-28T12:00:00Z",
                    md5="abc123def456",
                ),
                ctx,
            )

            self.assertGreater(response.record_id, 0)
            conn = sqlite3.connect(db_path)
            try:
                row = conn.execute(
                    """
                    SELECT source_domain, report_name, landing_page_url, downloaded_at_utc, md5
                    FROM report_sources
                    WHERE id=?
                    """,
                    (response.record_id,),
                ).fetchone()
            finally:
                conn.close()

            self.assertEqual(
                (
                    "www.criteo.com",
                    "Criteo Global Winter Travel Pulse 2025",
                    "https://www.criteo.com/resources/report",
                    "2026-03-28T12:00:00Z",
                    "abc123def456",
                ),
                row,
            )

    def test_record_discovered_report_source_collapses_tracking_query_variants(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "reports.sqlite")
            ctx = new_run_context(task_id="test_discovered_report_source_tracking_dedupe")

            first = record_discovered_report_source(
                ReportSourceDiscoveryRecordRequest(
                    schema_version="1.0",
                    db_path=db_path,
                    source_domain="www.pwc.com",
                    report_name="CEO Survey",
                    landing_page_url="https://www.pwc.com/gx/en/issues/c-suite-insights/ceo-survey.html?icid=tla-top-banner",
                    publisher_name="PricewaterhouseCoopers (PWC)",
                    source_page_url="https://www.pwc.com/gx/en/issues/c-suite-insights.html",
                    discovered_at_utc="2026-03-31T00:00:00Z",
                    discovered_on_page_number=1,
                ),
                ctx,
            )
            second = record_discovered_report_source(
                ReportSourceDiscoveryRecordRequest(
                    schema_version="1.0",
                    db_path=db_path,
                    source_domain="www.pwc.com",
                    report_name="CEO Survey",
                    landing_page_url="https://www.pwc.com/gx/en/issues/c-suite-insights/ceo-survey.html",
                    publisher_name="PricewaterhouseCoopers (PWC)",
                    source_page_url="https://www.pwc.com/gx/en/issues/c-suite-insights.html",
                    discovered_at_utc="2026-03-31T00:05:00Z",
                    discovered_on_page_number=1,
                ),
                ctx,
            )

            self.assertTrue(first.created_new)
            self.assertFalse(second.created_new)
            self.assertEqual(first.record_id, second.record_id)

            conn = sqlite3.connect(db_path)
            try:
                rows = conn.execute(
                    """
                    SELECT landing_page_url, normalized_landing_page_url
                    FROM report_sources
                    """
                ).fetchall()
            finally:
                conn.close()

            self.assertEqual(1, len(rows))
            self.assertEqual(
                "https://www.pwc.com/gx/en/issues/c-suite-insights/ceo-survey.html",
                rows[0][1],
            )

    def test_record_report_source_requires_md5(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "reports.sqlite")
            ctx = new_run_context(task_id="test_report_source_validation")

            with self.assertRaises(AppError):
                record_report_source(
                    ReportSourceRecordRequest(
                        schema_version="1.0",
                        db_path=db_path,
                        source_domain="www.criteo.com",
                        report_name="Broken Report",
                        landing_page_url="https://www.criteo.com/resources/report",
                        downloaded_at_utc="2026-03-28T12:00:00Z",
                        md5="",
                    ),
                    ctx,
                )

    def test_replace_publishers_replaces_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "reports.sqlite")
            ctx = new_run_context(task_id="test_publishers_replace")

            response = replace_publishers(
                PublishersReplaceRequest(
                    schema_version="1.0",
                    db_path=db_path,
                    source_page_url="https://www.notion.so/87c35358a78c4afc9eb7451dc1ade33d",
                    publishers=[
                        PublisherProfileRecord(
                            schema_version="1.0",
                            notion_page_id="page-1",
                            notion_page_url="https://www.notion.so/page-1",
                            name="Activate Consulting",
                            homepage="https://www.activate.com/",
                            self_presentation="Activate description",
                            insights_url="https://www.activate.com/insights",
                            icon_source="https://cdn.example.com/activate.png",
                        ),
                        PublisherProfileRecord(
                            schema_version="1.0",
                            notion_page_id="page-2",
                            notion_page_url="https://www.notion.so/page-2",
                            name="Criteo",
                            homepage="https://www.criteo.com/",
                            self_presentation="Criteo description",
                            insights_url="https://www.criteo.com/resources/",
                            icon_source="https://cdn.example.com/criteo.png",
                        ),
                    ],
                ),
                ctx,
            )

            self.assertEqual(0, response.previous_count)
            self.assertEqual(2, response.replaced_count)

            response_second = replace_publishers(
                PublishersReplaceRequest(
                    schema_version="1.0",
                    db_path=db_path,
                    source_page_url="https://www.notion.so/87c35358a78c4afc9eb7451dc1ade33d",
                    publishers=[
                        PublisherProfileRecord(
                            schema_version="1.0",
                            notion_page_id="page-3",
                            notion_page_url="https://www.notion.so/page-3",
                            name="Adobe",
                            homepage="https://business.adobe.com/",
                            self_presentation="Adobe description",
                            insights_url="https://business.adobe.com/resources/reports.html",
                            icon_source="data:image/png;base64,abc",
                        ),
                    ],
                ),
                ctx,
            )

            self.assertEqual(2, response_second.previous_count)
            self.assertEqual(1, response_second.replaced_count)
            conn = sqlite3.connect(db_path)
            try:
                rows = conn.execute(
                    """
                    SELECT name, homepage, insights_url
                    FROM publishers
                    ORDER BY name ASC
                    """
                ).fetchall()
            finally:
                conn.close()

            self.assertEqual(
                [
                    (
                        "Adobe",
                        "https://business.adobe.com/",
                        "https://business.adobe.com/resources/reports.html",
                    )
                ],
                rows,
            )

    def test_publisher_download_route_roundtrip_and_preserved_on_replace(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "reports.sqlite")
            ctx = new_run_context(task_id="test_publisher_route_roundtrip")

            replace_publishers(
                PublishersReplaceRequest(
                    schema_version="1.0",
                    db_path=db_path,
                    source_page_url="https://www.notion.so/87c35358a78c4afc9eb7451dc1ade33d",
                    publishers=[
                        PublisherProfileRecord(
                            schema_version="1.0",
                            notion_page_id="page-1",
                            notion_page_url="https://www.notion.so/page-1",
                            name="Activate Consulting",
                            homepage="https://www.activate.com/",
                            self_presentation="Activate description",
                            insights_url="https://www.activate.com/insights",
                            icon_source="https://cdn.example.com/activate.png",
                        )
                    ],
                ),
                ctx,
            )

            record_publisher_download_route(
                PublisherDownloadRouteRecordRequest(
                    schema_version="1.0",
                    db_path=db_path,
                    normalized_url="https://www.activate.com/insights",
                    source_url="https://www.activate.com/insights",
                    route_kind="email_delivery",
                    route_summary="Open the report modal and submit the email form.",
                    outcome="email_required",
                    last_downloaded_file_path=None,
                    last_final_page_url="https://www.activate.com/insights",
                ),
                ctx,
            )

            response = get_publisher_download_route(
                PublisherDownloadRouteGetRequest(
                    schema_version="1.0",
                    db_path=db_path,
                    normalized_url="https://www.activate.com/insights",
                ),
                ctx,
            )
            assert response is not None
            self.assertEqual("email_delivery", response.route_kind)
            self.assertEqual(
                "Open the report modal and submit the email form.",
                response.route_summary,
            )
            self.assertEqual("email_required", response.outcome)

            replace_publishers(
                PublishersReplaceRequest(
                    schema_version="1.0",
                    db_path=db_path,
                    source_page_url="https://www.notion.so/87c35358a78c4afc9eb7451dc1ade33d",
                    publishers=[
                        PublisherProfileRecord(
                            schema_version="1.0",
                            notion_page_id="page-1",
                            notion_page_url="https://www.notion.so/page-1",
                            name="Activate Consulting Updated",
                            homepage="https://www.activate.com/",
                            self_presentation="Updated description",
                            insights_url="https://www.activate.com/insights",
                            icon_source="https://cdn.example.com/activate.png",
                        )
                    ],
                ),
                ctx,
            )

            response_after_replace = get_publisher_download_route(
                PublisherDownloadRouteGetRequest(
                    schema_version="1.0",
                    db_path=db_path,
                    normalized_url="https://www.activate.com/insights",
                ),
                ctx,
            )
            assert response_after_replace is not None
            self.assertEqual("email_delivery", response_after_replace.route_kind)
            self.assertEqual("email_required", response_after_replace.outcome)
            self.assertEqual(
                "Open the report modal and submit the email form.",
                response_after_replace.route_summary,
            )

    def test_replace_publishers_preserves_google_folder_by_name_or_insights_url(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "reports.sqlite")
            ctx = new_run_context(task_id="test_publishers_google_folder_preserve")

            replace_publishers(
                PublishersReplaceRequest(
                    schema_version="1.0",
                    db_path=db_path,
                    source_page_url="https://www.notion.so/87c35358a78c4afc9eb7451dc1ade33d",
                    publishers=[
                        PublisherProfileRecord(
                            schema_version="1.0",
                            notion_page_id="page-1",
                            notion_page_url="https://www.notion.so/page-1",
                            name="Activate Consulting",
                            homepage="https://www.activate.com/",
                            self_presentation="Activate description",
                            insights_url="https://www.activate.com/insights",
                            icon_source="https://cdn.example.com/activate.png",
                        ),
                        PublisherProfileRecord(
                            schema_version="1.0",
                            notion_page_id="page-2",
                            notion_page_url="https://www.notion.so/page-2",
                            name="Edge by Ascential",
                            homepage="https://www.ascential.com/",
                            self_presentation="Edge description",
                            insights_url="",
                            icon_source="https://cdn.example.com/edge.png",
                        ),
                    ],
                ),
                ctx,
            )

            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    """
                    UPDATE publishers
                    SET google_folder=?
                    WHERE name=?
                    """,
                    (
                        "https://drive.google.com/drive/folders/1UKaCLZBE3lM-nRoLtUkC2as8p9YMX9Qq",
                        "Activate Consulting",
                    ),
                )

                conn.execute(
                    """
                    UPDATE publishers
                    SET google_folder=?
                    WHERE name=?
                    """,
                    (
                        "https://drive.google.com/drive/folders/1JvPCZFJ4LQMOackWw24-IV7GPJgvCB6z",
                        "Edge by Ascential",
                    ),
                )
                conn.commit()
            finally:
                conn.close()

            replace_publishers(
                PublishersReplaceRequest(
                    schema_version="1.0",
                    db_path=db_path,
                    source_page_url="https://www.notion.so/87c35358a78c4afc9eb7451dc1ade33d",
                    publishers=[
                        PublisherProfileRecord(
                            schema_version="1.0",
                            notion_page_id="page-1",
                            notion_page_url="https://www.notion.so/page-1b",
                            name="Activate Consulting Updated",
                            homepage="https://www.activate.com/",
                            self_presentation="Updated activate description",
                            insights_url="https://www.activate.com/insights",
                            icon_source="https://cdn.example.com/activate.png",
                        ),
                        PublisherProfileRecord(
                            schema_version="1.0",
                            notion_page_id="page-2",
                            notion_page_url="https://www.notion.so/page-2b",
                            name="Edge by Ascential",
                            homepage="https://www.ascential.com/",
                            self_presentation="Updated edge description",
                            insights_url="",
                            icon_source="https://cdn.example.com/edge.png",
                        ),
                    ],
                ),
                ctx,
            )

            conn = sqlite3.connect(db_path)
            try:
                rows = conn.execute(
                    """
                    SELECT name, insights_url, google_folder
                    FROM publishers
                    ORDER BY name ASC
                    """
                ).fetchall()
            finally:
                conn.close()

            self.assertEqual(
                [
                    (
                        "Activate Consulting Updated",
                        "https://www.activate.com/insights",
                        "https://drive.google.com/drive/folders/1UKaCLZBE3lM-nRoLtUkC2as8p9YMX9Qq",
                    ),
                    (
                        "Edge by Ascential",
                        "",
                        "https://drive.google.com/drive/folders/1JvPCZFJ4LQMOackWw24-IV7GPJgvCB6z",
                    ),
                ],
                rows,
            )

    def test_record_discovered_report_source_inserts_pending_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "reports.sqlite")
            ctx = new_run_context(task_id="test_report_source_discovery_record")

            response = record_discovered_report_source(
                ReportSourceDiscoveryRecordRequest(
                    schema_version="1.0",
                    db_path=db_path,
                    publisher_name="Activate Consulting",
                    source_domain="cdn.sanity.io",
                    report_name="2025 Outlook",
                    landing_page_url="https://cdn.sanity.io/files/report-2025.pdf",
                    source_page_url="https://www.activate.com/insights",
                    discovered_at_utc="2026-03-29T14:00:00Z",
                    discovered_on_page_number=1,
                ),
                ctx,
            )

            self.assertGreater(response.record_id, 0)
            self.assertTrue(response.created_new)
            conn = sqlite3.connect(db_path)
            try:
                row = conn.execute(
                    """
                    SELECT
                        publisher_name,
                        source_domain,
                        report_name,
                        landing_page_url,
                        source_page_url,
                        source_status,
                        discovered_at_utc,
                        discovered_on_page_number,
                        downloaded_at_utc,
                        md5
                    FROM report_sources
                    WHERE id=?
                    """,
                    (response.record_id,),
                ).fetchone()
            finally:
                conn.close()

            self.assertEqual(
                (
                    "Activate Consulting",
                    "cdn.sanity.io",
                    "2025 Outlook",
                    "https://cdn.sanity.io/files/report-2025.pdf",
                    "https://www.activate.com/insights",
                    "discovered",
                    "2026-03-29T14:00:00Z",
                    1,
                    None,
                    None,
                ),
                row,
            )

    def test_record_report_source_upgrades_existing_discovered_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "reports.sqlite")
            ctx = new_run_context(task_id="test_report_source_upgrade")

            discovered = record_discovered_report_source(
                ReportSourceDiscoveryRecordRequest(
                    schema_version="1.0",
                    db_path=db_path,
                    publisher_name="Activate Consulting",
                    source_domain="cdn.sanity.io",
                    report_name="2025 Outlook",
                    landing_page_url="https://cdn.sanity.io/files/report-2025.pdf",
                    source_page_url="https://www.activate.com/insights",
                    discovered_at_utc="2026-03-29T14:00:00Z",
                    discovered_on_page_number=1,
                ),
                ctx,
            )

            downloaded = record_report_source(
                ReportSourceRecordRequest(
                    schema_version="1.0",
                    db_path=db_path,
                    source_domain="cdn.sanity.io",
                    report_name="2025 Outlook",
                    landing_page_url="https://cdn.sanity.io/files/report-2025.pdf",
                    downloaded_at_utc="2026-03-29T15:00:00Z",
                    md5="ABC123DEF456",
                ),
                ctx,
            )

            self.assertEqual(discovered.record_id, downloaded.record_id)
            conn = sqlite3.connect(db_path)
            try:
                row = conn.execute(
                    """
                    SELECT
                        source_status,
                        discovered_at_utc,
                        downloaded_at_utc,
                        md5
                    FROM report_sources
                    WHERE id=?
                    """,
                    (downloaded.record_id,),
                ).fetchone()
            finally:
                conn.close()

            self.assertEqual(
                (
                    "downloaded",
                    "2026-03-29T14:00:00Z",
                    "2026-03-29T15:00:00Z",
                    "abc123def456",
                ),
                row,
            )

    def test_get_publisher_inventory_state_tolerates_empty_string_timestamps(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "reports.sqlite")
            ctx = new_run_context(task_id="test_inventory_state_empty_string_timestamps")

            replace_publishers(
                PublishersReplaceRequest(
                    schema_version="1.0",
                    db_path=db_path,
                    source_page_url="https://www.notion.so/source",
                    publishers=[
                        PublisherProfileRecord(
                            schema_version="1.0",
                            notion_page_id="page-1",
                            notion_page_url="https://www.notion.so/page-1",
                            name="Activate Consulting",
                            homepage="https://www.activate.com/",
                            self_presentation="Activate description",
                            insights_url="https://www.activate.com/insights",
                            icon_source="https://cdn.example.com/activate.png",
                        )
                    ],
                ),
                ctx,
            )

            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    """
                    UPDATE publishers
                    SET
                        google_folder=?,
                        inventory_route_kind='',
                        inventory_route_summary='',
                        inventory_route_last_final_page_url='',
                        inventory_route_updated_at='',
                        inventory_snapshot_drive_file_id='',
                        inventory_snapshot_drive_file_name='',
                        inventory_snapshot_sha256='',
                        inventory_snapshot_updated_at=''
                    WHERE insights_url=?
                    """,
                    (
                        "https://drive.google.com/drive/folders/test-folder",
                        "https://www.activate.com/insights",
                    ),
                )
                conn.commit()
            finally:
                conn.close()

            state = get_publisher_inventory_state(
                PublisherInventoryStateGetRequest(
                    schema_version="1.0",
                    db_path=db_path,
                    normalized_url="https://www.activate.com/insights",
                ),
                ctx,
            )

            self.assertIsNotNone(state)
            assert state is not None
            self.assertEqual("Activate Consulting", state.publisher_name)
            self.assertEqual(
                "https://drive.google.com/drive/folders/test-folder",
                state.google_folder,
            )
            self.assertIsNone(state.inventory_route_updated_at)
            self.assertIsNone(state.inventory_snapshot_updated_at)
            self.assertIsNone(state.inventory_snapshot_drive_file_id)
            self.assertIsNone(state.discovery_test_status)

    def test_replace_publishers_migrates_old_schema_and_drops_removed_columns(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "reports.sqlite")
            conn = sqlite3.connect(db_path)
            try:
                conn.executescript(
                    """
                    CREATE TABLE publishers (
                      notion_page_id TEXT PRIMARY KEY,
                      notion_page_url TEXT NOT NULL,
                      name TEXT NOT NULL,
                      homepage TEXT NOT NULL,
                      self_presentation TEXT NOT NULL,
                      insights_url TEXT NOT NULL,
                      icon_source TEXT NOT NULL,
                      source_page_url TEXT NOT NULL
                    );
                    INSERT INTO publishers(
                      notion_page_id,
                      notion_page_url,
                      name,
                      homepage,
                      self_presentation,
                      insights_url,
                      icon_source,
                      source_page_url
                    ) VALUES(
                      'page-legacy',
                      'https://www.notion.so/page-legacy',
                      'Legacy Publisher',
                      'https://legacy.example.com/',
                      'Legacy description',
                      'https://legacy.example.com/insights',
                      'https://legacy.example.com/icon.png',
                      'https://www.notion.so/legacy-source'
                    );
                    """
                )
                conn.commit()
            finally:
                conn.close()

            replace_publishers(
                PublishersReplaceRequest(
                    schema_version="1.0",
                    db_path=db_path,
                    source_page_url="https://www.notion.so/87c35358a78c4afc9eb7451dc1ade33d",
                    publishers=[
                        PublisherProfileRecord(
                            schema_version="1.0",
                            notion_page_id="page-1",
                            notion_page_url="https://www.notion.so/page-1",
                            name="Activate Consulting",
                            homepage="https://www.activate.com/",
                            self_presentation="Activate description",
                            insights_url="https://www.activate.com/insights",
                            icon_source="https://cdn.example.com/activate.png",
                        )
                    ],
                ),
                new_run_context(task_id="test_publishers_migration"),
            )

            conn = sqlite3.connect(db_path)
            try:
                columns = [
                    row[1]
                    for row in conn.execute("PRAGMA table_info(publishers)").fetchall()
                ]
                row = conn.execute(
                    """
                    SELECT name, homepage, self_presentation, insights_url
                    FROM publishers
                    """
                ).fetchone()
            finally:
                conn.close()

            self.assertEqual(
                [
                    "id",
                    "name",
                    "homepage",
                    "self_presentation",
                    "insights_url",
                    "google_folder",
                    "discovery_test_status",
                    "download_route_kind",
                    "download_route_summary",
                    "download_route_outcome",
                    "download_route_last_downloaded_file_path",
                    "download_route_last_final_page_url",
                    "download_route_updated_at",
                    "inventory_route_kind",
                    "inventory_route_summary",
                    "inventory_route_last_final_page_url",
                    "inventory_route_updated_at",
                    "inventory_snapshot_drive_file_id",
                    "inventory_snapshot_drive_file_name",
                    "inventory_snapshot_sha256",
                    "inventory_snapshot_updated_at",
                    "inventory_run_quality_json",
                    "inventory_run_quality_updated_at",
                ],
                columns,
            )
            self.assertEqual(
                (
                    "Activate Consulting",
                    "https://www.activate.com/",
                    "Activate description",
                    "https://www.activate.com/insights",
                ),
                row,
            )

    def test_publisher_inventory_state_roundtrip_and_preserved_on_replace(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "reports.sqlite")
            ctx = new_run_context(task_id="test_publisher_inventory_state")

            replace_publishers(
                PublishersReplaceRequest(
                    schema_version="1.0",
                    db_path=db_path,
                    source_page_url="https://www.notion.so/source",
                    publishers=[
                        PublisherProfileRecord(
                            schema_version="1.0",
                            notion_page_id="page-1",
                            notion_page_url="https://www.notion.so/page-1",
                            name="Activate Consulting",
                            homepage="https://www.activate.com/",
                            self_presentation="Activate description",
                            insights_url="https://www.activate.com/insights",
                            icon_source="https://cdn.example.com/activate.png",
                        )
                    ],
                ),
                ctx,
            )

            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    """
                    UPDATE publishers
                    SET google_folder=?
                    WHERE insights_url=?
                    """,
                    (
                        "https://drive.google.com/drive/folders/abc123",
                        "https://www.activate.com/insights",
                    ),
                )
                conn.commit()
            finally:
                conn.close()

            record_publisher_inventory_state(
                PublisherInventoryStateRecordRequest(
                    schema_version="1.0",
                    db_path=db_path,
                    normalized_url="https://www.activate.com/insights",
                    source_url="https://www.activate.com/insights",
                    route_kind="browser_render",
                    route_summary="Open the insights page, click next pagination until the last page, and extract report links.",
                    last_final_page_url="https://www.activate.com/insights?page=2",
                    snapshot_drive_file_id="drive-file-1",
                    snapshot_drive_file_name="publisher_inventory_snapshot__20260329T120000Z.json",
                    snapshot_sha256="sha256-1",
                ),
                ctx,
            )

            state = get_publisher_inventory_state(
                PublisherInventoryStateGetRequest(
                    schema_version="1.0",
                    db_path=db_path,
                    normalized_url="https://www.activate.com/insights",
                ),
                ctx,
            )

            assert state is not None
            self.assertEqual("Activate Consulting", state.publisher_name)
            self.assertEqual(
                "https://drive.google.com/drive/folders/abc123", state.google_folder
            )
            self.assertIsNone(state.discovery_test_status)
            self.assertEqual("browser_render", state.inventory_route_kind)
            self.assertEqual("drive-file-1", state.inventory_snapshot_drive_file_id)
            self.assertEqual("sha256-1", state.inventory_snapshot_sha256)

            record_publisher_inventory_test_status(
                PublisherInventoryTestStatusRecordRequest(
                    schema_version="1.0",
                    db_path=db_path,
                    normalized_url="https://www.activate.com/insights",
                    status="passed",
                ),
                ctx,
            )

            replace_publishers(
                PublishersReplaceRequest(
                    schema_version="1.0",
                    db_path=db_path,
                    source_page_url="https://www.notion.so/source",
                    publishers=[
                        PublisherProfileRecord(
                            schema_version="1.0",
                            notion_page_id="page-1",
                            notion_page_url="https://www.notion.so/page-1",
                            name="Activate Consulting Updated",
                            homepage="https://www.activate.com/",
                            self_presentation="Updated description",
                            insights_url="https://www.activate.com/insights",
                            icon_source="https://cdn.example.com/activate.png",
                        )
                    ],
                ),
                ctx,
            )

            preserved = get_publisher_inventory_state(
                PublisherInventoryStateGetRequest(
                    schema_version="1.0",
                    db_path=db_path,
                    normalized_url="https://www.activate.com/insights",
                ),
                ctx,
            )
            assert preserved is not None
            self.assertEqual("Activate Consulting Updated", preserved.publisher_name)
            self.assertEqual("passed", preserved.discovery_test_status)
            self.assertEqual("browser_render", preserved.inventory_route_kind)
            self.assertEqual("drive-file-1", preserved.inventory_snapshot_drive_file_id)

    def test_record_publisher_inventory_test_status_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "reports.sqlite")
            ctx = new_run_context(task_id="test_publisher_inventory_test_status")

            replace_publishers(
                PublishersReplaceRequest(
                    schema_version="1.0",
                    db_path=db_path,
                    source_page_url="https://www.notion.so/source",
                    publishers=[
                        PublisherProfileRecord(
                            schema_version="1.0",
                            notion_page_id="page-1",
                            notion_page_url="https://www.notion.so/page-1",
                            name="Activate Consulting",
                            homepage="https://www.activate.com/",
                            self_presentation="Activate description",
                            insights_url="https://www.activate.com/insights",
                            icon_source="https://cdn.example.com/activate.png",
                        )
                    ],
                ),
                ctx,
            )

            record_publisher_inventory_test_status(
                PublisherInventoryTestStatusRecordRequest(
                    schema_version="1.0",
                    db_path=db_path,
                    normalized_url="https://www.activate.com/insights",
                    status="failed:publisher_inventory_browser_pagination_limit",
                ),
                ctx,
            )

            state = get_publisher_inventory_state(
                PublisherInventoryStateGetRequest(
                    schema_version="1.0",
                    db_path=db_path,
                    normalized_url="https://www.activate.com/insights",
                ),
                ctx,
            )

            assert state is not None
            self.assertEqual(
                "failed:publisher_inventory_browser_pagination_limit",
                state.discovery_test_status,
            )

    def test_record_publisher_inventory_run_quality_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "reports.sqlite")
            ctx = new_run_context(task_id="test_publisher_inventory_run_quality")

            replace_publishers(
                PublishersReplaceRequest(
                    schema_version="1.0",
                    db_path=db_path,
                    source_page_url="https://www.notion.so/source",
                    publishers=[
                        PublisherProfileRecord(
                            schema_version="1.0",
                            notion_page_id="page-1",
                            notion_page_url="https://www.notion.so/page-1",
                            name="Activate Consulting",
                            homepage="https://www.activate.com/",
                            self_presentation="Activate description",
                            insights_url="https://www.activate.com/insights",
                            icon_source="https://cdn.example.com/activate.png",
                        )
                    ],
                ),
                ctx,
            )

            record_publisher_inventory_run_quality(
                PublisherInventoryRunQualityRecordRequest(
                    schema_version="1.0",
                    db_path=db_path,
                    normalized_url="https://www.activate.com/insights",
                    summary=PublisherInventoryRunQualitySummary(
                        schema_version="1.0",
                        outcome="accepted",
                        status="passed",
                        quality_band="high",
                        route_kind="browser_render",
                        recommended_route_kind="browser_render",
                        used_memory_route=False,
                        page_count=2,
                        raw_candidate_count=10,
                        current_report_count=10,
                        previous_report_count=8,
                        raw_new_report_count=2,
                        screened_new_report_count=2,
                        qualified_new_report_count=1,
                        snapshot_changed=True,
                        requires_review=False,
                        recommended_route_reason="Reuse browser route.",
                        summary="high quality via browser_render",
                        candidate_provenance_counts={"browser_dom": 10},
                    ),
                ),
                ctx,
            )

            state = get_publisher_inventory_state(
                PublisherInventoryStateGetRequest(
                    schema_version="1.0",
                    db_path=db_path,
                    normalized_url="https://www.activate.com/insights",
                ),
                ctx,
            )

            assert state is not None
            assert state.inventory_run_quality_summary is not None
            self.assertEqual("accepted", state.inventory_run_quality_summary.outcome)
            self.assertEqual(
                "browser_render",
                state.inventory_run_quality_summary.recommended_route_kind,
            )


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
