# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403


class TestReportStoreService05UpdatePublisherGoogleFolder(unittest.TestCase):
    def test_update_publisher_google_folder_persists_folder_url(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "reports.sqlite")
            ctx = new_run_context(task_id="test_publisher_google_folder_update")

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

            response = update_publisher_google_folder(
                PublisherGoogleFolderUpdateRequest(
                    schema_version="1.0",
                    db_path=db_path,
                    publisher_name="Activate Consulting",
                    publisher_insights_url="https://www.activate.com/insights",
                    google_folder="https://drive.google.com/drive/folders/folder123",
                ),
                ctx,
            )
            lookup = get_report_download_drive_folder(
                ReportDownloadDriveFolderLookupRequest(
                    schema_version="1.0",
                    db_path=db_path,
                    normalized_landing_page_url="",
                    publisher_insights_url="https://www.activate.com/insights",
                ),
                ctx,
            )

            self.assertEqual("Activate Consulting", response.publisher_name)
            self.assertEqual(1, response.updated_count)
            assert lookup is not None
            self.assertEqual(
                "https://drive.google.com/drive/folders/folder123",
                lookup.google_folder,
            )

    def test_get_report_download_drive_folder_uses_request_publisher_name_for_new_publisher(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "reports.sqlite")
            ctx = new_run_context(task_id="test_ad_hoc_publisher_folder_lookup")

            lookup = get_report_download_drive_folder(
                ReportDownloadDriveFolderLookupRequest(
                    schema_version="1.0",
                    db_path=db_path,
                    normalized_landing_page_url="https://example.com/report",
                    publisher_name="Ad Hoc Publisher",
                ),
                ctx,
            )

            assert lookup is not None
            self.assertEqual("Ad Hoc Publisher", lookup.publisher_name)
            self.assertEqual("", lookup.google_folder)
            self.assertEqual("request_publisher_name", lookup.resolution_source)

    def test_update_publisher_google_folder_inserts_ad_hoc_publisher_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "reports.sqlite")
            ctx = new_run_context(task_id="test_ad_hoc_publisher_folder_insert")

            response = update_publisher_google_folder(
                PublisherGoogleFolderUpdateRequest(
                    schema_version="1.0",
                    db_path=db_path,
                    publisher_name="Ad Hoc Publisher",
                    publisher_insights_url="",
                    google_folder="https://drive.google.com/drive/folders/folder123",
                ),
                ctx,
            )
            lookup = get_report_download_drive_folder(
                ReportDownloadDriveFolderLookupRequest(
                    schema_version="1.0",
                    db_path=db_path,
                    normalized_landing_page_url="",
                    publisher_name="Ad Hoc Publisher",
                ),
                ctx,
            )

            self.assertEqual("Ad Hoc Publisher", response.publisher_name)
            self.assertEqual(1, response.updated_count)
            self.assertEqual("publisher_name_inserted", response.resolution_source)
            assert lookup is not None
            self.assertEqual(
                "https://drive.google.com/drive/folders/folder123",
                lookup.google_folder,
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
                        md5,
                        publisher_name,
                        source_page_url
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
                    "Activate Consulting",
                    "https://www.activate.com/insights",
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
            self.assertEqual((14,), schema_version)
            self.assertEqual(14, ledger_count)
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


__all__ = ["TestReportStoreService05UpdatePublisherGoogleFolder"]
