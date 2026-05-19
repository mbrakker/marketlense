import os
import pytest
import sqlite3
import tempfile
import time
import unittest
from dataclasses import replace

from src.contracts.browser_download import (
    BrowserDownloadConfirmationEvidence,
    BrowserDownloadNetworkEvent,
    BrowserDownloadRouteStep,
    DownloadTerminalEvidence,
)
from src.contracts.report_store import (
    PublisherInventoryRecoveryCacheGetRequest,
    PublisherInventoryRecoveryCacheRecordRequest,
    PublishersListRequest,
    PublisherDownloadRouteGetRequest,
    PublisherDownloadRouteRecordRequest,
    PublisherInventoryRunQualityRecordRequest,
    PublisherInventoryStateGetRequest,
    PublisherInventoryStateRecordRequest,
    PublisherInventoryTestStatusRecordRequest,
    PublishersReplaceRequest,
    ReportDownloadDriveFolderLookupRequest,
    ReportMetadataDbAccessRequest,
    ReportSourceDiscoveryRecordRequest,
    ReportSourceQualityHistoryRequest,
    ReportMetadataGetRequest,
    ReportSourceRecordRequest,
    ReportValueScoreComponent,
    ReportValueScoreRecordRequest,
    ReportValueScoreResponse,
    ReportMetadataUpsertRequest,
)
from src.contracts.publisher_inventory import (
    PublisherInventoryRecoveryRecord,
    PublisherInventoryRouteTrace,
    PublisherInventoryRunQualitySummary,
    PublisherInventoryScenarioSummary,
)
from src.contracts.publisher_profiles import PublisherProfileRecord
from src.services.report_store_service import (
    check_report_db_access,
    get_report_download_drive_folder,
    get_metadata,
    get_publisher_inventory_recovery_cache_record,
    list_report_source_quality_history,
    record_discovered_report_source,
    record_report_value_score,
    get_publisher_download_route,
    get_publisher_inventory_state,
    list_publishers,
    record_publisher_inventory_recovery_cache_record,
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
                ReportMetadataGetRequest(
                    schema_version="1.1", db_path=db_path, file_id="file-1"
                ),
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
                ReportMetadataGetRequest(
                    schema_version="1.1", db_path=db_path, file_id="file-1"
                ),
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
            self.assertEqual(
                "Jun 2023, Jul 2023, Aug 2023, Sep 2023, Oct 2023, Nov 2023",
                second.time_period,
            )
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
                ReportMetadataGetRequest(
                    schema_version="1.1", db_path=db_path, file_id="file-1"
                ),
                ctx,
            )
            assert third is not None
            self.assertEqual("2026", third.time_period)

    def test_missing_record_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "reports.sqlite")
            ctx = new_run_context(task_id="test_missing")
            resp = get_metadata(
                ReportMetadataGetRequest(
                    schema_version="1.1", db_path=db_path, file_id="missing"
                ),
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
                    ReportMetadataDbAccessRequest(
                        schema_version="1.0", db_path=db_path, timeout_seconds=0.0
                    ),
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
                ReportMetadataDbAccessRequest(
                    schema_version="1.0", db_path=db_path, timeout_seconds=0.0
                ),
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

    def test_record_discovered_report_source_collapses_tracking_query_variants(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "reports.sqlite")
            ctx = new_run_context(
                task_id="test_discovered_report_source_tracking_dedupe"
            )

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

    def test_record_report_value_score_and_list_resource_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "reports.sqlite")
            ctx = new_run_context(task_id="test_report_value_score_history")
            discovered = record_discovered_report_source(
                ReportSourceDiscoveryRecordRequest(
                    schema_version="1.0",
                    db_path=db_path,
                    publisher_name="Example Research",
                    source_domain="research.example.com",
                    report_name="2026 Global Retail Market Outlook",
                    landing_page_url="https://research.example.com/reports/retail-2026",
                    source_page_url="https://research.example.com/research/reports",
                    discovered_at_utc="2026-05-19T08:00:00Z",
                    discovered_on_page_number=1,
                ),
                ctx,
            )
            record_report_value_score(
                ReportValueScoreRecordRequest(
                    schema_version="1.0",
                    db_path=db_path,
                    record_id=discovered.record_id,
                    score=ReportValueScoreResponse(
                        schema_version="1.0",
                        overall_score=86.0,
                        value_band="high",
                        components=[
                            ReportValueScoreComponent(
                                schema_version="1.0",
                                dimension="market_insight_depth",
                                score=90.0,
                                rationale="strong market outlook",
                            )
                        ],
                        rationale="high value",
                    ),
                    scored_at_utc="2026-05-19T08:05:00Z",
                ),
                ctx,
            )

            history = list_report_source_quality_history(
                ReportSourceQualityHistoryRequest(
                    schema_version="1.0",
                    db_path=db_path,
                    publisher_name="Example Research",
                    limit=10,
                ),
                ctx,
            )

            self.assertEqual(1, len(history.items))
            self.assertEqual(
                "https://research.example.com/research/reports",
                history.items[0].source_page_url,
            )
            self.assertEqual(86.0, history.items[0].overall_score)
            self.assertEqual("high", history.items[0].value_band)

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

    def test_publishers_persist_normalized_lookup_key_and_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "reports.sqlite")
            ctx = new_run_context(task_id="test_publishers_normalized_lookup")

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
                            name="Example Publisher",
                            homepage="https://example.com/",
                            self_presentation="Example description",
                            insights_url="https://Example.com/insights/?utm_source=newsletter",
                            icon_source="https://cdn.example.com/example.png",
                        )
                    ],
                ),
                ctx,
            )

            conn = sqlite3.connect(db_path)
            try:
                row = conn.execute(
                    """
                    SELECT insights_url, normalized_insights_url
                    FROM publishers
                    """
                ).fetchone()
                index_names = {
                    str(index_row[1])
                    for index_row in conn.execute(
                        "PRAGMA index_list(publishers)"
                    ).fetchall()
                }
                query_plan = " ".join(
                    str(plan_row)
                    for plan_row in conn.execute(
                        """
                        EXPLAIN QUERY PLAN
                        SELECT id
                        FROM publishers
                        WHERE normalized_insights_url=?
                        ORDER BY id ASC
                        LIMIT 1
                        """,
                        ("https://example.com/insights",),
                    ).fetchall()
                )
            finally:
                conn.close()

            self.assertEqual(
                (
                    "https://Example.com/insights/?utm_source=newsletter",
                    "https://example.com/insights",
                ),
                row,
            )
            self.assertIn("idx_publishers_normalized_insights_url", index_names)
            self.assertIn("idx_publishers_normalized_insights_url", query_plan)

    def test_publisher_normalized_lookup_collision_updates_first_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "reports.sqlite")
            ctx = new_run_context(task_id="test_publishers_normalized_collision")

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
                            name="First Example",
                            homepage="https://example.com/",
                            self_presentation="First description",
                            insights_url="https://example.com/insights/",
                            icon_source="https://cdn.example.com/first.png",
                        ),
                        PublisherProfileRecord(
                            schema_version="1.0",
                            notion_page_id="page-2",
                            notion_page_url="https://www.notion.so/page-2",
                            name="Second Example",
                            homepage="https://example.com/",
                            self_presentation="Second description",
                            insights_url="https://example.com/insights?utm_source=duplicate",
                            icon_source="https://cdn.example.com/second.png",
                        ),
                    ],
                ),
                ctx,
            )

            record_publisher_inventory_test_status(
                PublisherInventoryTestStatusRecordRequest(
                    schema_version="1.0",
                    db_path=db_path,
                    normalized_url="https://example.com/insights",
                    status="passed",
                ),
                ctx,
            )

            conn = sqlite3.connect(db_path)
            try:
                rows = conn.execute(
                    """
                    SELECT name, normalized_insights_url, discovery_test_status
                    FROM publishers
                    ORDER BY id ASC
                    """
                ).fetchall()
            finally:
                conn.close()

            self.assertEqual(
                [
                    ("First Example", "https://example.com/insights", "passed"),
                    ("Second Example", "https://example.com/insights", None),
                ],
                rows,
            )

    def test_list_publishers_returns_current_rows_with_inventory_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "reports.sqlite")
            ctx = new_run_context(task_id="test_publishers_list")

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
                        ),
                        PublisherProfileRecord(
                            schema_version="1.0",
                            notion_page_id="page-2",
                            notion_page_url="https://www.notion.so/page-2",
                            name="No Insights",
                            homepage="https://example.com/",
                            self_presentation="No insights description",
                            insights_url="",
                            icon_source="https://cdn.example.com/no-insights.png",
                        ),
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
                        raw_candidate_count=6,
                        current_report_count=6,
                        previous_report_count=5,
                        raw_new_report_count=1,
                        screened_new_report_count=1,
                        qualified_new_report_count=1,
                        snapshot_changed=True,
                        requires_review=False,
                        recommended_route_reason="Reuse browser route.",
                        summary="high quality via browser_render",
                        candidate_provenance_counts={"browser_dom": 6},
                    ),
                ),
                ctx,
            )

            response = list_publishers(
                PublishersListRequest(
                    schema_version="1.0",
                    db_path=db_path,
                    limit=None,
                ),
                ctx,
            )

            self.assertEqual(1, len(response.publishers))
            item = response.publishers[0]
            self.assertEqual("Activate Consulting", item.publisher_name)
            self.assertEqual("https://www.activate.com/insights", item.insights_url)
            self.assertEqual(
                "https://www.activate.com/insights", item.normalized_insights_url
            )
            assert item.inventory_run_quality_summary is not None
            self.assertEqual("accepted", item.inventory_run_quality_summary.outcome)

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
                    route_family="browser_email_form",
                    route_status="inferred",
                    resolved_target_url="https://www.activate.com/insights",
                    route_steps=[
                        BrowserDownloadRouteStep(
                            schema_version="1.0",
                            index=0,
                            action="open",
                            target_text="https://www.activate.com/insights",
                            target_role="url",
                            target_url="https://www.activate.com/insights",
                            result="completed",
                        )
                    ],
                    confirmation_evidence=BrowserDownloadConfirmationEvidence(
                        schema_version="1.0",
                        url_changed=False,
                        visible_confirmation_text="",
                        submit_button_state="unchanged",
                        form_disappeared=False,
                        final_page_url="https://www.activate.com/insights",
                    ),
                    terminal_evidence=DownloadTerminalEvidence(
                        schema_version="1.0",
                        final_page_url="https://www.activate.com/insights",
                        final_page_title="",
                        terminal_text_excerpt="",
                        artifact_url="https://www.activate.com/insights",
                        artifact_kind="email_delivery",
                        artifact_validation_status="blocked",
                        artifact_validation_detail="",
                        confirmation_signal_count=0,
                        traversed_page_urls=["https://www.activate.com/insights"],
                    ),
                    browser_had_structured_result=True,
                    used_candidate_pdf_url=False,
                    used_candidate_source_page=False,
                    blocked_reason="blocked_missing_identity_field",
                    blocked_reason_detail="missing required identity value",
                    last_downloaded_file_path=None,
                    last_final_page_url="https://www.activate.com/insights",
                    onsite_capture_path=None,
                    onsite_capture_format=None,
                    onsite_page_count=None,
                    onsite_completeness_status=None,
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

    def test_publisher_download_route_projection_preserves_best_memory_without_rewriting_latest_history(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "reports.sqlite")
            ctx = new_run_context(task_id="test_publisher_route_projection")

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
                            name="BigCommerce",
                            homepage="https://www.bigcommerce.com/",
                            self_presentation="BigCommerce description",
                            insights_url="https://www.bigcommerce.com/resources/reports/global-b2b-buyer-report-cdl-report",
                            icon_source="https://cdn.example.com/bigcommerce.png",
                        )
                    ],
                ),
                ctx,
            )

            success_request = PublisherDownloadRouteRecordRequest(
                schema_version="1.0",
                db_path=db_path,
                normalized_url="https://www.bigcommerce.com/resources/reports/global-b2b-buyer-report-cdl-report",
                source_url="https://www.bigcommerce.com/resources/reports/global-b2b-buyer-report-cdl-report",
                route_kind="email_delivery",
                route_summary="Submit the form and wait for the email confirmation state.",
                outcome="email_requested",
                route_family="browser_pdf_click",
                route_status="verified",
                resolved_target_url="https://www.bigcommerce.com/resources/reports/global-b2b-buyer-report-cdl-report/",
                route_steps=[],
                confirmation_evidence=BrowserDownloadConfirmationEvidence(
                    schema_version="1.0",
                    url_changed=True,
                    visible_confirmation_text="Check your inbox for the report.",
                    submit_button_state="submitted",
                    form_disappeared=True,
                    final_page_url="https://www.bigcommerce.com/resources/reports/global-b2b-buyer-report-cdl-report/",
                    confirmation_score=3,
                    signal_labels=["success_text", "form_disappeared", "success_url"],
                ),
                terminal_evidence=DownloadTerminalEvidence(
                    schema_version="1.0",
                    final_page_url="https://www.bigcommerce.com/resources/reports/global-b2b-buyer-report-cdl-report/",
                    final_page_title="Global B2B Buyer Report | BigCommerce",
                    terminal_text_excerpt="Check your inbox for the report.",
                    artifact_url="https://www.bigcommerce.com/resources/reports/global-b2b-buyer-report-cdl-report/",
                    artifact_kind="email_delivery",
                    artifact_validation_status="confirmed",
                    artifact_validation_detail="Email delivery confirmed on page.",
                    confirmation_signal_count=3,
                    traversed_page_urls=[
                        "https://www.bigcommerce.com/resources/reports/global-b2b-buyer-report-cdl-report/"
                    ],
                    evidence_labels=[
                        "structured_result",
                        "confirmed",
                        "email_delivery",
                    ],
                ),
                browser_had_structured_result=True,
                used_candidate_pdf_url=False,
                used_candidate_source_page=False,
                blocked_reason=None,
                blocked_reason_detail=None,
                last_downloaded_file_path=None,
                last_final_page_url="https://www.bigcommerce.com/resources/reports/global-b2b-buyer-report-cdl-report/",
                onsite_capture_path=None,
                onsite_capture_format=None,
                onsite_page_count=None,
                onsite_completeness_status=None,
            )
            record_publisher_download_route(success_request, ctx)

            weaker_request = PublisherDownloadRouteRecordRequest(
                schema_version="1.0",
                db_path=db_path,
                normalized_url=success_request.normalized_url,
                source_url=success_request.source_url,
                route_kind="email_delivery",
                route_summary="Filled the form and clicked download but no confirmation was visible.",
                outcome="email_required",
                route_family="browser_pdf_click",
                route_status="inferred",
                resolved_target_url=success_request.resolved_target_url,
                route_steps=[],
                confirmation_evidence=BrowserDownloadConfirmationEvidence(
                    schema_version="1.0",
                    url_changed=False,
                    visible_confirmation_text="",
                    submit_button_state="unchanged",
                    form_disappeared=False,
                    final_page_url="https://www.bigcommerce.com/resources/reports/global-b2b-buyer-report-cdl-report/",
                    confirmation_score=0,
                    signal_labels=[],
                ),
                terminal_evidence=DownloadTerminalEvidence(
                    schema_version="1.0",
                    final_page_url="https://www.bigcommerce.com/resources/reports/global-b2b-buyer-report-cdl-report/",
                    final_page_title="Global B2B Buyer Report | BigCommerce",
                    terminal_text_excerpt="",
                    artifact_url="https://www.bigcommerce.com/resources/reports/global-b2b-buyer-report-cdl-report/",
                    artifact_kind="email_delivery",
                    artifact_validation_status="none",
                    artifact_validation_detail="",
                    confirmation_signal_count=0,
                    traversed_page_urls=[
                        "https://www.bigcommerce.com/resources/reports/global-b2b-buyer-report-cdl-report/"
                    ],
                    evidence_labels=["structured_result", "none", "email_delivery"],
                ),
                browser_had_structured_result=True,
                used_candidate_pdf_url=False,
                used_candidate_source_page=False,
                blocked_reason=None,
                blocked_reason_detail=None,
                last_downloaded_file_path=None,
                last_final_page_url="https://www.bigcommerce.com/resources/reports/global-b2b-buyer-report-cdl-report/",
                onsite_capture_path=None,
                onsite_capture_format=None,
                onsite_page_count=None,
                onsite_completeness_status=None,
            )
            record_publisher_download_route(weaker_request, ctx)

            conn = sqlite3.connect(db_path)
            try:
                latest_history = conn.execute(
                    """
                    SELECT outcome, route_status, route_summary
                    FROM publisher_download_route_history
                    WHERE normalized_url=?
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (weaker_request.normalized_url,),
                ).fetchone()
                publisher_projection = conn.execute(
                    """
                    SELECT download_route_outcome, download_route_summary
                    FROM publishers
                    WHERE insights_url=?
                    """,
                    (weaker_request.source_url,),
                ).fetchone()
            finally:
                conn.close()

            self.assertEqual(
                (
                    "email_required",
                    "inferred",
                    "Filled the form and clicked download but no confirmation was visible.",
                ),
                latest_history,
            )
            self.assertEqual(
                (
                    "email_requested",
                    "Submit the form and wait for the email confirmation state.",
                ),
                publisher_projection,
            )

    def test_get_download_route_returns_ranked_route_policy_from_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "reports.sqlite")
            ctx = new_run_context(task_id="test_publisher_route_policy")
            normalized_url = "https://example.com/reports/brand-study"

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
                            name="Example Publisher",
                            homepage="https://example.com/",
                            self_presentation="Example description",
                            insights_url=normalized_url,
                            icon_source="https://cdn.example.com/example.png",
                        )
                    ],
                ),
                ctx,
            )

            email_success = PublisherDownloadRouteRecordRequest(
                schema_version="1.0",
                db_path=db_path,
                normalized_url=normalized_url,
                source_url=normalized_url,
                route_kind="email_delivery",
                route_summary="Open the report page, fill the form, and submit it.",
                outcome="email_requested",
                route_family="browser_email_form",
                route_status="verified",
                resolved_target_url=f"{normalized_url}/thank-you",
                route_steps=[],
                confirmation_evidence=BrowserDownloadConfirmationEvidence(
                    schema_version="1.0",
                    url_changed=True,
                    visible_confirmation_text="Check your inbox for the report.",
                    submit_button_state="submitted",
                    form_disappeared=True,
                    final_page_url=f"{normalized_url}/thank-you",
                    confirmation_score=3,
                    signal_labels=["success_text", "form_disappeared"],
                ),
                terminal_evidence=DownloadTerminalEvidence(
                    schema_version="1.0",
                    final_page_url=f"{normalized_url}/thank-you",
                    final_page_title="Thank you",
                    terminal_text_excerpt="Check your inbox for the report.",
                    artifact_url=f"{normalized_url}/thank-you",
                    artifact_kind="email_delivery",
                    artifact_validation_status="confirmed",
                    artifact_validation_detail="Email delivery confirmed.",
                    confirmation_signal_count=3,
                    traversed_page_urls=[normalized_url, f"{normalized_url}/thank-you"],
                    evidence_labels=["confirmed", "email_delivery"],
                ),
                browser_had_structured_result=True,
                used_candidate_pdf_url=False,
                used_candidate_source_page=False,
                blocked_reason=None,
                blocked_reason_detail=None,
                last_downloaded_file_path=None,
                last_final_page_url=f"{normalized_url}/thank-you",
                onsite_capture_path=None,
                onsite_capture_format=None,
                onsite_page_count=None,
                onsite_completeness_status=None,
            )
            record_publisher_download_route(email_success, ctx)
            record_publisher_download_route(
                replace(
                    email_success,
                    route_summary="Repeat the same email form route.",
                    resolved_target_url=f"{normalized_url}/thanks",
                    last_final_page_url=f"{normalized_url}/thanks",
                ),
                ctx,
            )
            record_publisher_download_route(
                replace(
                    email_success,
                    route_kind="pdf_download",
                    route_summary="HTTP probing did not find a downloadable PDF.",
                    outcome="email_required",
                    route_family="http_pdf_probe",
                    route_status="inferred",
                    resolved_target_url=normalized_url,
                    browser_had_structured_result=False,
                    blocked_reason="blocked_no_pdf_link",
                    blocked_reason_detail="No PDF link found in static HTML.",
                    last_final_page_url=normalized_url,
                ),
                ctx,
            )

            response = get_publisher_download_route(
                PublisherDownloadRouteGetRequest(
                    schema_version="1.0",
                    db_path=db_path,
                    normalized_url=normalized_url,
                ),
                ctx,
            )

            self.assertIsNotNone(response)
            assert response is not None
            self.assertGreaterEqual(len(response.route_policy), 2)
            self.assertEqual(
                "browser_email_form", response.route_policy[0].route_family
            )
            self.assertEqual(2, response.route_policy[0].verified_successes)
            self.assertEqual("http_pdf_probe", response.route_policy[1].route_family)
            self.assertEqual(
                "blocked_no_pdf_link", response.route_policy[1].last_blocked_reason
            )

    def test_get_download_route_returns_publisher_policy_for_new_url(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "reports.sqlite")
            ctx = new_run_context(task_id="test_publisher_scope_route_policy")
            source_url = "https://example.com/reports"
            base_request = PublisherDownloadRouteRecordRequest(
                schema_version="1.0",
                db_path=db_path,
                normalized_url="https://example.com/reports/known-study-1",
                source_url=source_url,
                route_kind="onsite_report",
                route_summary="Open the on-site report URL and capture the article.",
                outcome="captured",
                route_family="browser_onsite_report",
                route_status="verified",
                resolved_target_url="https://example.com/reports/known-study-1",
                route_steps=[
                    BrowserDownloadRouteStep(
                        schema_version="1.0",
                        index=0,
                        action="extract",
                        target_text="article",
                        target_role="document",
                        target_url="https://example.com/reports/known-study-1",
                        result="captured",
                    )
                ],
                confirmation_evidence=BrowserDownloadConfirmationEvidence(
                    schema_version="1.0",
                    url_changed=False,
                    visible_confirmation_text="",
                    submit_button_state="unchanged",
                    form_disappeared=False,
                    final_page_url="https://example.com/reports/known-study-1",
                ),
                terminal_evidence=DownloadTerminalEvidence(
                    schema_version="1.0",
                    final_page_url="https://example.com/reports/known-study-1",
                    final_page_title="Known study",
                    terminal_text_excerpt="Known study report article.",
                    artifact_url="https://example.com/reports/known-study-1",
                    artifact_kind="onsite_report",
                    artifact_validation_status="verified",
                    artifact_validation_detail="Captured on-site report.",
                    confirmation_signal_count=0,
                    traversed_page_urls=["https://example.com/reports/known-study-1"],
                    evidence_labels=["direct_html_capture"],
                ),
                browser_had_structured_result=False,
                used_candidate_pdf_url=False,
                used_candidate_source_page=True,
                candidate_pdf_url=None,
                candidate_source_page_urls=[source_url],
                candidate_discovery_provenances=[],
                publisher_discovery_route_kind=None,
                publisher_recommended_discovery_route_kind=None,
                blocked_reason=None,
                blocked_reason_detail=None,
                last_downloaded_file_path=None,
                last_final_page_url="https://example.com/reports/known-study-1",
                onsite_capture_path=os.path.join(tmpdir, "known-study-1.html"),
                onsite_capture_format="html",
                onsite_page_count=1,
                onsite_completeness_status="complete",
            )

            for index in range(1, 4):
                url = f"https://example.com/reports/known-study-{index}"
                record_publisher_download_route(
                    replace(
                        base_request,
                        normalized_url=url,
                        resolved_target_url=url,
                        last_final_page_url=url,
                        onsite_capture_path=os.path.join(
                            tmpdir, f"known-study-{index}.html"
                        ),
                    ),
                    ctx,
                )

            response = get_publisher_download_route(
                PublisherDownloadRouteGetRequest(
                    schema_version="1.0",
                    db_path=db_path,
                    normalized_url="https://example.com/reports/new-study",
                    publisher_scope_url=source_url,
                ),
                ctx,
            )

            self.assertIsNotNone(response)
            assert response is not None
            self.assertFalse(response.exact_route_found)
            self.assertEqual([], response.route_policy)
            self.assertEqual(
                "browser_onsite_report",
                response.publisher_route_policy[0].route_family,
            )
            self.assertEqual(3, response.publisher_route_policy[0].verified_successes)

    def test_get_download_route_preserves_confirmation_score_and_signal_labels(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "reports.sqlite")
            ctx = new_run_context(task_id="test_route_confirmation_round_trip")

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
                            name="BigCommerce",
                            homepage="https://www.bigcommerce.com/",
                            self_presentation="BigCommerce description",
                            insights_url="https://www.bigcommerce.com/resources/reports/global-b2b-buyer-report-cdl-report",
                            icon_source="https://cdn.example.com/bigcommerce.png",
                        )
                    ],
                ),
                ctx,
            )

            record_publisher_download_route(
                PublisherDownloadRouteRecordRequest(
                    schema_version="1.0",
                    db_path=db_path,
                    normalized_url="https://www.bigcommerce.com/resources/reports/global-b2b-buyer-report-cdl-report",
                    source_url="https://www.bigcommerce.com/resources/reports/global-b2b-buyer-report-cdl-report",
                    route_kind="email_delivery",
                    route_summary="Submit the form and verify the thank-you state.",
                    outcome="email_requested",
                    route_family="browser_email_form",
                    route_status="verified",
                    resolved_target_url="https://www.bigcommerce.com/resources/reports/global-b2b-buyer-report-cdl-report-ty/",
                    route_steps=[],
                    confirmation_evidence=BrowserDownloadConfirmationEvidence(
                        schema_version="1.0",
                        url_changed=True,
                        visible_confirmation_text="A copy of the report will be sent to your inbox shortly.",
                        submit_button_state="disabled",
                        form_disappeared=True,
                        final_page_url="https://www.bigcommerce.com/resources/reports/global-b2b-buyer-report-cdl-report-ty/",
                        confirmation_score=4,
                        signal_labels=[
                            "submit_observed",
                            "delivery_text",
                            "success_url",
                            "form_disappeared",
                        ],
                    ),
                    terminal_evidence=DownloadTerminalEvidence(
                        schema_version="1.0",
                        final_page_url="https://www.bigcommerce.com/resources/reports/global-b2b-buyer-report-cdl-report-ty/",
                        final_page_title="Thank you for downloading the report",
                        terminal_text_excerpt="A copy of the report will be sent to your inbox shortly.",
                        artifact_url="https://www.bigcommerce.com/resources/reports/global-b2b-buyer-report-cdl-report-ty/",
                        artifact_kind="email_delivery",
                        artifact_validation_status="confirmed",
                        artifact_validation_detail="Email delivery confirmed on thank-you page.",
                        confirmation_signal_count=4,
                        traversed_page_urls=[
                            "https://www.bigcommerce.com/resources/reports/global-b2b-buyer-report-cdl-report-ty/"
                        ],
                        evidence_labels=[
                            "structured_result",
                            "confirmed",
                            "email_delivery",
                        ],
                    ),
                    browser_had_structured_result=True,
                    used_candidate_pdf_url=False,
                    used_candidate_source_page=False,
                    blocked_reason=None,
                    blocked_reason_detail=None,
                    last_downloaded_file_path=None,
                    last_final_page_url="https://www.bigcommerce.com/resources/reports/global-b2b-buyer-report-cdl-report-ty/",
                    onsite_capture_path=None,
                    onsite_capture_format=None,
                    onsite_page_count=None,
                    onsite_completeness_status=None,
                ),
                ctx,
            )

            response = get_publisher_download_route(
                PublisherDownloadRouteGetRequest(
                    schema_version="1.0",
                    db_path=db_path,
                    normalized_url="https://www.bigcommerce.com/resources/reports/global-b2b-buyer-report-cdl-report",
                ),
                ctx,
            )

            self.assertIsNotNone(response)
            assert response is not None
            self.assertEqual(4, response.confirmation_evidence.confirmation_score)
            self.assertEqual(
                [
                    "submit_observed",
                    "delivery_text",
                    "success_url",
                    "form_disappeared",
                ],
                response.confirmation_evidence.signal_labels,
            )

    def test_get_download_route_preserves_terminal_network_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "reports.sqlite")
            ctx = new_run_context(task_id="test_route_network_events_round_trip")

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
                            name="Example Publisher",
                            homepage="https://example.com/",
                            self_presentation="Example description",
                            insights_url="https://example.com/report",
                            icon_source="https://cdn.example.com/example.png",
                        )
                    ],
                ),
                ctx,
            )

            record_publisher_download_route(
                PublisherDownloadRouteRecordRequest(
                    schema_version="1.0",
                    db_path=db_path,
                    normalized_url="https://example.com/report",
                    source_url="https://example.com/report",
                    route_kind="email_delivery",
                    route_summary="Submit the form and verify the terminal state.",
                    outcome="email_requested",
                    route_family="browser_email_form",
                    route_status="verified",
                    resolved_target_url="https://example.com/report/thank-you",
                    route_steps=[],
                    confirmation_evidence=BrowserDownloadConfirmationEvidence(
                        schema_version="1.0",
                        url_changed=False,
                        visible_confirmation_text="",
                        submit_button_state="unchanged",
                        form_disappeared=False,
                        final_page_url="https://example.com/report",
                        confirmation_score=2,
                        signal_labels=[
                            "submit_observed",
                            "network_confirmation_request",
                        ],
                    ),
                    terminal_evidence=DownloadTerminalEvidence(
                        schema_version="1.0",
                        final_page_url="https://example.com/report",
                        final_page_title="Example report",
                        terminal_text_excerpt="",
                        artifact_url="https://example.com/report",
                        artifact_kind="email_delivery",
                        artifact_validation_status="confirmed",
                        artifact_validation_detail="Email delivery confirmed from terminal evidence.",
                        confirmation_signal_count=2,
                        traversed_page_urls=["https://example.com/report"],
                        visited_url_timeline=[
                            "https://example.com/forms/submit",
                            "https://example.com/report",
                        ],
                        observed_document_urls=[],
                        network_events=[
                            BrowserDownloadNetworkEvent(
                                schema_version="1.0",
                                url="https://example.com/forms/submit",
                                initiator_type="fetch",
                                signal_kind="submission_request",
                            ),
                            BrowserDownloadNetworkEvent(
                                schema_version="1.0",
                                url="https://example.com/report/thank-you",
                                initiator_type="navigation",
                                signal_kind="confirmation_request",
                            ),
                        ],
                        evidence_labels=[
                            "submit_observed",
                            "network_confirmation_request",
                            "email_delivery",
                        ],
                    ),
                    browser_had_structured_result=True,
                    used_candidate_pdf_url=False,
                    used_candidate_source_page=False,
                    blocked_reason=None,
                    blocked_reason_detail=None,
                    last_downloaded_file_path=None,
                    last_final_page_url="https://example.com/report",
                    onsite_capture_path=None,
                    onsite_capture_format=None,
                    onsite_page_count=None,
                    onsite_completeness_status=None,
                ),
                ctx,
            )

            response = get_publisher_download_route(
                PublisherDownloadRouteGetRequest(
                    schema_version="1.0",
                    db_path=db_path,
                    normalized_url="https://example.com/report",
                ),
                ctx,
            )

            self.assertIsNotNone(response)
            assert response is not None
            self.assertEqual(2, len(response.terminal_evidence.network_events))
            self.assertEqual(
                "submission_request",
                response.terminal_evidence.network_events[0].signal_kind,
            )
            self.assertEqual(
                "confirmation_request",
                response.terminal_evidence.network_events[1].signal_kind,
            )

    def test_get_download_route_prefers_reusable_extract_trace_over_newer_scroll_only_trace(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "reports.sqlite")
            ctx = new_run_context(task_id="test_route_prefers_extract_trace")

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
                            name="Example Publisher",
                            homepage="https://example.com/",
                            self_presentation="Example description",
                            insights_url="https://example.com/report",
                            icon_source="https://cdn.example.com/example.png",
                        )
                    ],
                ),
                ctx,
            )

            record_publisher_download_route(
                PublisherDownloadRouteRecordRequest(
                    schema_version="1.0",
                    db_path=db_path,
                    normalized_url="https://example.com/report",
                    source_url="https://example.com/report",
                    route_kind="onsite_report",
                    route_summary="Accept cookies and extract the on-site report.",
                    outcome="captured",
                    route_family="browser_onsite_report",
                    route_status="verified",
                    resolved_target_url="https://example.com/report",
                    route_steps=[
                        BrowserDownloadRouteStep(
                            schema_version="1.0",
                            index=0,
                            action="click",
                            target_text="Allow all",
                            target_role="button",
                            target_url="https://example.com/report",
                            result="Accepted cookies",
                        ),
                        BrowserDownloadRouteStep(
                            schema_version="1.0",
                            index=1,
                            action="extract",
                            target_text="report article",
                            target_role="extract",
                            target_url="https://example.com/report",
                            result="Captured the on-site report body",
                        ),
                    ],
                    confirmation_evidence=BrowserDownloadConfirmationEvidence(
                        schema_version="1.0",
                        url_changed=False,
                        visible_confirmation_text="",
                        submit_button_state="unchanged",
                        form_disappeared=False,
                        final_page_url="https://example.com/report",
                    ),
                    terminal_evidence=DownloadTerminalEvidence(
                        schema_version="1.0",
                        final_page_url="https://example.com/report",
                        final_page_title="Example report",
                        terminal_text_excerpt="Report body",
                        artifact_url="https://example.com/report",
                        artifact_kind="onsite_report",
                        artifact_validation_status="verified",
                        artifact_validation_detail="Captured from on-site article.",
                        confirmation_signal_count=1,
                        traversed_page_urls=["https://example.com/report"],
                        evidence_labels=["structured_result", "onsite_report"],
                    ),
                    browser_had_structured_result=True,
                    used_candidate_pdf_url=False,
                    used_candidate_source_page=False,
                    blocked_reason=None,
                    blocked_reason_detail=None,
                    last_downloaded_file_path=None,
                    last_final_page_url="https://example.com/report",
                    onsite_capture_path="captured.html",
                    onsite_capture_format="html",
                    onsite_page_count=1,
                    onsite_completeness_status="complete",
                ),
                ctx,
            )
            time.sleep(0.01)
            record_publisher_download_route(
                PublisherDownloadRouteRecordRequest(
                    schema_version="1.0",
                    db_path=db_path,
                    normalized_url="https://example.com/report",
                    source_url="https://example.com/report",
                    route_kind="onsite_report",
                    route_summary="Navigate to the report page, accept cookies, and scroll.",
                    outcome="captured",
                    route_family="browser_onsite_report",
                    route_status="verified",
                    resolved_target_url="https://example.com/report",
                    route_steps=[
                        BrowserDownloadRouteStep(
                            schema_version="1.0",
                            index=0,
                            action="navigate",
                            target_text="",
                            target_role="page",
                            target_url="https://example.com/report",
                            result="Opened the report page",
                        ),
                        BrowserDownloadRouteStep(
                            schema_version="1.0",
                            index=1,
                            action="click",
                            target_text="Allow all",
                            target_role="button",
                            target_url="https://example.com/report",
                            result="Accepted cookies",
                        ),
                        BrowserDownloadRouteStep(
                            schema_version="1.0",
                            index=2,
                            action="scroll",
                            target_text="",
                            target_role="page",
                            target_url="https://example.com/report",
                            result="Scrolled down 900px",
                        ),
                    ],
                    confirmation_evidence=BrowserDownloadConfirmationEvidence(
                        schema_version="1.0",
                        url_changed=False,
                        visible_confirmation_text="",
                        submit_button_state="unchanged",
                        form_disappeared=False,
                        final_page_url="https://example.com/report",
                    ),
                    terminal_evidence=DownloadTerminalEvidence(
                        schema_version="1.0",
                        final_page_url="https://example.com/report",
                        final_page_title="Example report",
                        terminal_text_excerpt="Report body",
                        artifact_url="https://example.com/report",
                        artifact_kind="onsite_report",
                        artifact_validation_status="verified",
                        artifact_validation_detail="Captured from on-site article.",
                        confirmation_signal_count=1,
                        traversed_page_urls=["https://example.com/report"],
                        evidence_labels=["structured_result", "onsite_report"],
                    ),
                    browser_had_structured_result=True,
                    used_candidate_pdf_url=False,
                    used_candidate_source_page=False,
                    blocked_reason=None,
                    blocked_reason_detail=None,
                    last_downloaded_file_path=None,
                    last_final_page_url="https://example.com/report",
                    onsite_capture_path="captured.html",
                    onsite_capture_format="html",
                    onsite_page_count=1,
                    onsite_completeness_status="complete",
                ),
                ctx,
            )

            response = get_publisher_download_route(
                PublisherDownloadRouteGetRequest(
                    schema_version="1.0",
                    db_path=db_path,
                    normalized_url="https://example.com/report",
                ),
                ctx,
            )

            self.assertIsNotNone(response)
            assert response is not None
            self.assertEqual(
                "Accept cookies and extract the on-site report.",
                response.route_summary,
            )
            self.assertEqual(
                ["click", "extract"], [step.action for step in response.route_steps]
            )

    def test_replace_publishers_preserves_google_folder_by_name_or_insights_url(
        self,
    ) -> None:
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

    def test_get_report_download_drive_folder_resolves_source_publisher_folder(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "reports.sqlite")
            ctx = new_run_context(task_id="test_report_download_drive_folder_lookup")

            replace_publishers(
                PublishersReplaceRequest(
                    schema_version="1.0",
                    db_path=db_path,
                    source_page_url="https://notion.local/report-sources",
                    publishers=[
                        PublisherProfileRecord(
                            schema_version="1.0",
                            notion_page_id="page-1",
                            notion_page_url="https://www.notion.so/page-1",
                            name="Activate Consulting",
                            homepage="https://www.activate.com/",
                            self_presentation="Strategy consultancy.",
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
                    "UPDATE publishers SET google_folder=? WHERE name=?",
                    (
                        "https://drive.google.com/drive/folders/folder123",
                        "Activate Consulting",
                    ),
                )
                conn.commit()
            finally:
                conn.close()
            record_discovered_report_source(
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

            response = get_report_download_drive_folder(
                ReportDownloadDriveFolderLookupRequest(
                    schema_version="1.0",
                    db_path=db_path,
                    normalized_landing_page_url="https://cdn.sanity.io/files/report-2025.pdf",
                ),
                ctx,
            )

            assert response is not None
            self.assertEqual("Activate Consulting", response.publisher_name)
            self.assertEqual(
                "https://drive.google.com/drive/folders/folder123",
                response.google_folder,
            )
            self.assertEqual("report_source_publisher", response.resolution_source)

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

    def test_get_publisher_inventory_state_tolerates_empty_string_timestamps(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "reports.sqlite")
            ctx = new_run_context(
                task_id="test_inventory_state_empty_string_timestamps"
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

    def test_replace_publishers_migrates_old_schema_and_drops_removed_columns(
        self,
    ) -> None:
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
                schema_version = conn.execute(
                    "SELECT current_version FROM schema_version WHERE database_key='reports_db'"
                ).fetchone()
                ledger_count = conn.execute(
                    "SELECT COUNT(*) FROM schema_migration_ledger WHERE database_key='reports_db'"
                ).fetchone()[0]
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
                    "normalized_insights_url",
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
                    "inventory_route_trace_json",
                    "inventory_scenario_summary_json",
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
            self.assertEqual((11,), schema_version)
            self.assertEqual(11, ledger_count)
            self.assertEqual(
                (
                    "Activate Consulting",
                    "https://www.activate.com/",
                    "Activate description",
                    "https://www.activate.com/insights",
                ),
                row,
            )

    def test_publisher_legacy_schema_backfills_normalized_lookup_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "reports.sqlite")
            conn = sqlite3.connect(db_path)
            try:
                conn.executescript(
                    """
                    CREATE TABLE publishers (
                      id INTEGER PRIMARY KEY AUTOINCREMENT,
                      name TEXT NOT NULL,
                      homepage TEXT NOT NULL,
                      self_presentation TEXT NOT NULL,
                      insights_url TEXT NOT NULL,
                      download_route_kind TEXT,
                      download_route_summary TEXT,
                      download_route_outcome TEXT,
                      download_route_updated_at INTEGER
                    );
                    INSERT INTO publishers(
                      name,
                      homepage,
                      self_presentation,
                      insights_url,
                      download_route_kind,
                      download_route_summary,
                      download_route_outcome,
                      download_route_updated_at
                    ) VALUES(
                      'Legacy Publisher',
                      'https://legacy.example.com/',
                      'Legacy description',
                      'https://legacy.example.com/insights/?utm_source=archive',
                      'browser_pdf_click',
                      'Click the PDF download button.',
                      'downloaded',
                      1770000000
                    );
                    """
                )
                conn.commit()
            finally:
                conn.close()

            route = get_publisher_download_route(
                PublisherDownloadRouteGetRequest(
                    schema_version="1.0",
                    db_path=db_path,
                    normalized_url="https://legacy.example.com/insights",
                ),
                new_run_context(task_id="test_publisher_legacy_backfill"),
            )

            conn = sqlite3.connect(db_path)
            try:
                row = conn.execute(
                    """
                    SELECT normalized_insights_url
                    FROM publishers
                    WHERE name='Legacy Publisher'
                    """
                ).fetchone()
                index_names = {
                    str(index_row[1])
                    for index_row in conn.execute(
                        "PRAGMA index_list(publishers)"
                    ).fetchall()
                }
            finally:
                conn.close()

            assert route is not None
            self.assertEqual("browser_pdf_click", route.route_kind)
            self.assertEqual("Click the PDF download button.", route.route_summary)
            self.assertEqual(("https://legacy.example.com/insights",), row)
            self.assertIn("idx_publishers_normalized_insights_url", index_names)

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
                    route_trace=PublisherInventoryRouteTrace(
                        schema_version="1.0",
                        followed_report_listing=True,
                        applied_report_filter=True,
                        selected_filters=["report"],
                        selected_tab_labels=["research"],
                        pagination_mode="load_more",
                        preferred_control_labels=["load more"],
                        candidate_surface_guard="report_filter",
                        surface_class="archive_feed",
                        scroll_surface="virtualized_list",
                        scroll_surface_candidate_growth=True,
                        virtualized_list_detected=True,
                    ),
                    scenario_summary=PublisherInventoryScenarioSummary(
                        schema_version="1.0",
                        scenario_class="filtered_archive",
                        source_surface_class="archive_feed",
                        confidence=0.9,
                        direct_detail_eligible=False,
                        browser_preferred=True,
                        notes="Archive uses explicit report filters.",
                    ),
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
            assert state.inventory_route_trace is not None
            self.assertEqual("load_more", state.inventory_route_trace.pagination_mode)
            self.assertEqual(
                "virtualized_list", state.inventory_route_trace.scroll_surface
            )
            self.assertTrue(state.inventory_route_trace.scroll_surface_candidate_growth)
            self.assertTrue(state.inventory_route_trace.virtualized_list_detected)
            assert state.inventory_scenario_summary is not None
            self.assertEqual(
                "filtered_archive", state.inventory_scenario_summary.scenario_class
            )
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
            assert preserved.inventory_route_trace is not None
            self.assertEqual(
                "archive_feed", preserved.inventory_route_trace.surface_class
            )
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

    def test_publisher_inventory_state_includes_host_route_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "reports.sqlite")
            ctx = new_run_context(task_id="test_publisher_inventory_route_policy")

            replace_publishers(
                PublishersReplaceRequest(
                    schema_version="1.0",
                    db_path=db_path,
                    source_page_url="https://www.notion.so/source",
                    publishers=[
                        PublisherProfileRecord(
                            schema_version="1.0",
                            notion_page_id=f"page-{idx}",
                            notion_page_url=f"https://www.notion.so/page-{idx}",
                            name=f"Example {idx}",
                            homepage="https://example.com/",
                            self_presentation="Example description",
                            insights_url=f"https://example.com/insights/{idx}",
                            icon_source="https://cdn.example.com/example.png",
                        )
                        for idx in range(1, 5)
                    ],
                ),
                ctx,
            )

            for idx in range(1, 4):
                record_publisher_inventory_run_quality(
                    PublisherInventoryRunQualityRecordRequest(
                        schema_version="1.0",
                        db_path=db_path,
                        normalized_url=f"https://example.com/insights/{idx}",
                        summary=PublisherInventoryRunQualitySummary(
                            schema_version="1.0",
                            outcome="accepted",
                            status="passed",
                            quality_band="high",
                            route_kind="browser_render",
                            recommended_route_kind="browser_render",
                            used_memory_route=False,
                            page_count=2,
                            raw_candidate_count=8,
                            current_report_count=8,
                            previous_report_count=6,
                            raw_new_report_count=2,
                            screened_new_report_count=2,
                            qualified_new_report_count=2,
                            snapshot_changed=True,
                            requires_review=False,
                            recommended_route_reason="Browser route produced complete inventory.",
                            summary="high quality via browser_render",
                            candidate_provenance_counts={"browser_dom": 8},
                            scenario_class="js_hydrated_archive",
                        ),
                    ),
                    ctx,
                )

            state = get_publisher_inventory_state(
                PublisherInventoryStateGetRequest(
                    schema_version="1.0",
                    db_path=db_path,
                    normalized_url="https://example.com/insights/4",
                ),
                ctx,
            )

            assert state is not None
            self.assertGreaterEqual(len(state.inventory_route_policy), 1)
            signal = state.inventory_route_policy[0]
            self.assertEqual("browser_render", signal.route_kind)
            self.assertEqual(3, signal.attempts)
            self.assertEqual(3, signal.successful_attempts)
            self.assertEqual(0, signal.review_required_attempts)
            self.assertEqual(1.0, signal.success_rate)
            self.assertGreaterEqual(signal.confidence_score, 0.65)
            self.assertGreaterEqual(signal.rank_score, 0.65)

    def test_publisher_inventory_recovery_cache_roundtrip_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "reports.sqlite")
            ctx = new_run_context(task_id="test_publisher_inventory_recovery_cache")

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

            record_publisher_inventory_recovery_cache_record(
                PublisherInventoryRecoveryCacheRecordRequest(
                    schema_version="1.0",
                    db_path=db_path,
                    record=PublisherInventoryRecoveryRecord(
                        schema_version="1.0",
                        normalized_url="https://www.activate.com/insights",
                        canonical_url="https://www.activate.com/reports/new-report",
                        source_surface_class="archive_feed",
                        verification_class="challenge",
                        recovery_action="browser_retry",
                        last_outcome="scheduled",
                        last_http_status=403,
                        last_error_marker="dead_or_unreachable_landing_page",
                        updated_at_utc="2026-04-08T10:00:00Z",
                    ),
                ),
                ctx,
            )
            record_publisher_inventory_recovery_cache_record(
                PublisherInventoryRecoveryCacheRecordRequest(
                    schema_version="1.0",
                    db_path=db_path,
                    record=PublisherInventoryRecoveryRecord(
                        schema_version="1.0",
                        normalized_url="https://www.activate.com/insights",
                        canonical_url="https://www.activate.com/reports/new-report",
                        source_surface_class="archive_feed",
                        verification_class="challenge",
                        recovery_action="browser_retry",
                        last_outcome="recovered",
                        last_http_status=200,
                        last_error_marker=None,
                        updated_at_utc="2026-04-08T10:05:00Z",
                    ),
                ),
                ctx,
            )

            record = get_publisher_inventory_recovery_cache_record(
                PublisherInventoryRecoveryCacheGetRequest(
                    schema_version="1.0",
                    db_path=db_path,
                    normalized_url="https://www.activate.com/insights",
                    canonical_url="https://www.activate.com/reports/new-report",
                ),
                ctx,
            )

            assert record is not None
            self.assertEqual("recovered", record.last_outcome)
            self.assertEqual(200, record.last_http_status)
            self.assertEqual("browser_retry", record.recovery_action)


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
