# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403

class TestReportStoreService04GetDownloadRoutePreserves(unittest.TestCase):
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

    def test_get_report_download_drive_folder_resolves_publisher_name_fallback(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "reports.sqlite")
            ctx = new_run_context(task_id="test_report_download_drive_folder_name")

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

            response = get_report_download_drive_folder(
                ReportDownloadDriveFolderLookupRequest(
                    schema_version="1.0",
                    db_path=db_path,
                    normalized_landing_page_url="https://tracker.example.com/opaque",
                    publisher_name="activate consulting",
                ),
                ctx,
            )

            assert response is not None
            self.assertEqual("Activate Consulting", response.publisher_name)
            self.assertEqual(
                "https://drive.google.com/drive/folders/folder123",
                response.google_folder,
            )
            self.assertEqual("publisher_name", response.resolution_source)

    def test_get_report_download_drive_folder_resolves_normalized_publisher_name_fallback(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "reports.sqlite")
            ctx = new_run_context(
                task_id="test_report_download_drive_folder_normalized_name"
            )

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
                            name="Sensortower",
                            homepage="https://sensortower.com/",
                            self_presentation="Mobile app intelligence.",
                            insights_url="https://sensortower.com/resources",
                            icon_source="https://cdn.example.com/sensortower.png",
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
                        "Sensortower",
                    ),
                )
                conn.commit()
            finally:
                conn.close()

            response = get_report_download_drive_folder(
                ReportDownloadDriveFolderLookupRequest(
                    schema_version="1.0",
                    db_path=db_path,
                    normalized_landing_page_url="https://tracker.example.com/opaque",
                    publisher_name="Sensor Tower",
                ),
                ctx,
            )

            assert response is not None
            self.assertEqual("Sensortower", response.publisher_name)
            self.assertEqual(
                "https://drive.google.com/drive/folders/folder123",
                response.google_folder,
            )
            self.assertEqual("publisher_name_normalized", response.resolution_source)

    def test_get_report_download_drive_folder_returns_publisher_without_folder(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "reports.sqlite")
            ctx = new_run_context(task_id="test_report_download_missing_folder_lookup")

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

            response = get_report_download_drive_folder(
                ReportDownloadDriveFolderLookupRequest(
                    schema_version="1.0",
                    db_path=db_path,
                    normalized_landing_page_url="",
                    publisher_insights_url="https://www.activate.com/insights",
                ),
                ctx,
            )

            assert response is not None
            self.assertEqual("Activate Consulting", response.publisher_name)
            self.assertEqual("", response.google_folder)
            self.assertEqual("publisher_insights_url", response.resolution_source)

__all__ = ["TestReportStoreService04GetDownloadRoutePreserves"]
