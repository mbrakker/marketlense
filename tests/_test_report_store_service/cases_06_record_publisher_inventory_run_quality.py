# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403

class TestReportStoreService06RecordPublisherInventoryRun(unittest.TestCase):
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

__all__ = ["TestReportStoreService06RecordPublisherInventoryRun"]
