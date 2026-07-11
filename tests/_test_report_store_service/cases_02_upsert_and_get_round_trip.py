# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403


class TestReportStoreService02UpsertAndGetRound(unittest.TestCase):
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

    def test_metadata_uses_report_source_url_when_payload_url_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "reports.sqlite")
            ctx = new_run_context(task_id="test_metadata_source_fallback")
            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    """
                    CREATE TABLE report_sources (
                      id INTEGER PRIMARY KEY,
                      source_domain TEXT NOT NULL,
                      report_name TEXT NOT NULL,
                      landing_page_url TEXT NOT NULL,
                      normalized_landing_page_url TEXT NOT NULL,
                      source_status TEXT NOT NULL,
                      source_page_url TEXT,
                      publisher_name TEXT,
                      discovered_at_utc TEXT,
                      discovered_on_page_number INTEGER,
                      downloaded_at_utc TEXT,
                      md5 TEXT,
                      created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
                      updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
                    )
                    """
                )
                conn.execute(
                    """
                    INSERT INTO report_sources(
                        source_domain,
                        report_name,
                        landing_page_url,
                        normalized_landing_page_url,
                        source_status,
                        publisher_name,
                        downloaded_at_utc,
                        md5
                    )
                    VALUES(
                        'publisher.example',
                        'Original Source Report',
                        'https://publisher.example/reports/original-source-report',
                        'https://publisher.example/reports/original-source-report',
                        'downloaded',
                        'Publisher Inc',
                        '2026-04-20T00:00:00Z',
                        'source-md5'
                    )
                    """
                )
                conn.commit()
            finally:
                conn.close()

            upsert_metadata(
                ReportMetadataUpsertRequest(
                    schema_version="1.1",
                    db_path=db_path,
                    file_id="file-source-fallback",
                    title="Original Source Report",
                    publisher=None,
                    source_url=None,
                    md5="source-md5",
                ),
                ctx,
            )
            metadata = get_metadata(
                ReportMetadataGetRequest(
                    schema_version="1.1",
                    db_path=db_path,
                    file_id="file-source-fallback",
                ),
                ctx,
            )

            assert metadata is not None
            self.assertEqual(
                "https://publisher.example/reports/original-source-report",
                metadata.source_url,
            )
            self.assertEqual("Publisher Inc", metadata.publisher)

    def test_resolve_report_source_identity_uses_md5_before_title(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "reports.sqlite")
            ctx = new_run_context(task_id="test_source_identity")
            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    """
                    CREATE TABLE report_sources (
                      id INTEGER PRIMARY KEY,
                      source_domain TEXT NOT NULL,
                      report_name TEXT NOT NULL,
                      landing_page_url TEXT NOT NULL,
                      normalized_landing_page_url TEXT NOT NULL,
                      source_status TEXT NOT NULL,
                      source_page_url TEXT,
                      publisher_name TEXT,
                      discovered_at_utc TEXT,
                      discovered_on_page_number INTEGER,
                      downloaded_at_utc TEXT,
                      md5 TEXT,
                      created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
                      updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
                    )
                    """
                )
                conn.execute(
                    """
                    INSERT INTO report_sources(
                        source_domain,
                        report_name,
                        landing_page_url,
                        normalized_landing_page_url,
                        source_status,
                        publisher_name,
                        downloaded_at_utc,
                        md5
                    )
                    VALUES(
                        'publisher.example',
                        'Source Registry Title',
                        'https://publisher.example/source-registry-title.pdf',
                        'https://publisher.example/source-registry-title.pdf',
                        'downloaded',
                        'Publisher Inc',
                        '2026-04-20T00:00:00Z',
                        'source-md5'
                    )
                    """
                )
                conn.commit()
            finally:
                conn.close()

            response = resolve_report_source_identity(
                ReportSourceIdentityResolveRequest(
                    schema_version="1.0",
                    db_path=db_path,
                    report_title="Derived File Title",
                    md5="source-md5",
                ),
                ctx,
            )

            self.assertEqual("Publisher Inc", response.publisher_name)
            self.assertEqual("Source Registry Title", response.report_name)
            self.assertEqual(
                "https://publisher.example/source-registry-title.pdf",
                response.source_url,
            )
            self.assertEqual("md5", response.resolution_source)

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

    def test_link_report_to_source_sets_missing_lineage_without_overwriting(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "reports.sqlite")
            ctx = new_run_context(task_id="test_report_source_link")
            upsert_metadata(
                ReportMetadataUpsertRequest(
                    schema_version="1.0",
                    db_path=db_path,
                    file_id="legacy-file-id",
                    title="Legacy Report",
                    publisher="Example Publisher",
                    taxonomy=[],
                    source_url=None,
                    html_path=None,
                    md5="legacy-md5",
                ),
                ctx,
            )
            record_report_source(
                ReportSourceRecordRequest(
                    schema_version="1.0",
                    db_path=db_path,
                    source_domain="drive.google.com",
                    report_name="Legacy Report",
                    landing_page_url="https://drive.google.com/open?id=legacy-file-id",
                    downloaded_at_utc="2026-06-23T00:00:00Z",
                    md5="legacy-md5",
                    publisher_name="Example Publisher",
                ),
                ctx,
            )

            linked = link_report_to_source(
                ReportSourceLinkRequest(
                    schema_version="1.0",
                    db_path=db_path,
                    file_id="legacy-file-id",
                    source_md5="legacy-md5",
                ),
                ctx,
            )
            repeated = link_report_to_source(
                ReportSourceLinkRequest(
                    schema_version="1.0",
                    db_path=db_path,
                    file_id="legacy-file-id",
                    source_md5="legacy-md5",
                ),
                ctx,
            )

            self.assertTrue(linked.linked)
            self.assertFalse(repeated.linked)
            conn = sqlite3.connect(db_path)
            try:
                source_md5 = conn.execute(
                    "SELECT source_md5 FROM reports WHERE file_id=?",
                    ("legacy-file-id",),
                ).fetchone()[0]
            finally:
                conn.close()
            self.assertEqual("legacy-md5", source_md5)
            record_report_source(
                ReportSourceRecordRequest(
                    schema_version="1.0",
                    db_path=db_path,
                    source_domain="drive.google.com",
                    report_name="Replacement Report",
                    landing_page_url="https://drive.google.com/open?id=replacement-file-id",
                    downloaded_at_utc="2026-06-23T00:00:00Z",
                    md5="replacement-md5",
                    publisher_name="Example Publisher",
                ),
                ctx,
            )
            with self.assertRaises(AppError) as error:
                link_report_to_source(
                    ReportSourceLinkRequest(
                        schema_version="1.0",
                        db_path=db_path,
                        file_id="legacy-file-id",
                        source_md5="replacement-md5",
                    ),
                    ctx,
                )
            self.assertEqual("report_source_link_conflict", error.exception.code)

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


__all__ = ["TestReportStoreService02UpsertAndGetRound"]
