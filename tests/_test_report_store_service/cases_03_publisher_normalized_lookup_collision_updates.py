# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403

class TestReportStoreService03PublisherNormalizedLookupCollision(unittest.TestCase):
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

__all__ = ["TestReportStoreService03PublisherNormalizedLookupCollision"]
