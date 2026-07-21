# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403


def test_publish_runs_when_processed(
    publish_settings_factory, run_context, wordpress_http
) -> None:
    settings = publish_settings_factory(validation_policy="warn")
    _write_html(settings.output_dir, "report.html", "Drive fileId: file123")
    _record_processed(settings.state_db, "file123", run_context)
    wordpress_http.add_json(
        "GET",
        "https://example.com/wp-json/wp/v2/ml_report",
        status_code=200,
        payload=[],
    )
    wordpress_http.add_json(
        "POST",
        "https://example.com/wp-json/wp/v2/ml_report",
        status_code=201,
        payload={"id": 10, "link": "https://example.com/post/10", "status": "publish"},
    )

    results = orch.run_publish(settings, limit=1)

    publish_row = get_publish(
        StatePublishCheckRequest(
            schema_version="1.0",
            state_db=settings.state_db,
            file_id="file123",
            post_type=settings.wp.post_type,
        ),
        run_context,
    )
    post_call = wordpress_http.calls_for(
        "POST", "https://example.com/wp-json/wp/v2/ml_report"
    )[0]
    assert len(results) == 1
    assert results[0].status == "published"
    assert results[0].file_id == "file123"
    assert post_call.json_data["status"] == "publish"
    assert "Drive fileId:" not in post_call.json_data["content"]
    assert post_call.json_data["meta"]["ml_file_id"] == "file123"
    assert publish_row is not None
    assert publish_row.wp_post_id == 10
    assert publish_row.wp_post_url == "https://example.com/post/10"


def test_publish_can_force_draft_for_review(
    publish_settings_factory, run_context, wordpress_http
) -> None:
    settings = publish_settings_factory(validation_policy="warn")
    settings = replace(settings, wp=replace(settings.wp, post_status="publish"))
    _write_html(settings.output_dir, "report.html", "Drive fileId: file123")
    _record_processed(settings.state_db, "file123", run_context)
    wordpress_http.add_json(
        "GET",
        "https://example.com/wp-json/wp/v2/ml_report",
        status_code=200,
        payload=[],
    )
    wordpress_http.add_json(
        "POST",
        "https://example.com/wp-json/wp/v2/ml_report",
        status_code=201,
        payload={"id": 10, "link": "https://example.com/post/10", "status": "publish"},
    )

    outcomes = orch.run_publish(settings, limit=1, force_draft=True)

    post_call = wordpress_http.calls_for(
        "POST", "https://example.com/wp-json/wp/v2/ml_report"
    )[0]
    assert outcomes[0].status == "published"
    assert post_call.json_data["status"] == "draft"


def test_force_report_cards_updates_existing_post_in_place(
    publish_settings_factory, run_context, wordpress_http
) -> None:
    settings = publish_settings_factory(validation_policy="warn")
    _write_html(settings.output_dir, "report.html", "Drive fileId: file123")
    _record_processed(settings.state_db, "file123", run_context)
    record_publish(
        StatePublishRecordRequest(
            schema_version="1.0",
            state_db=settings.state_db,
            file_id="file123",
            md5="md5",
            wp_post_id=42,
            wp_post_url="https://example.com/post/42",
            post_type="ml_report",
        ),
        run_context,
    )
    wordpress_http.add_json(
        "GET",
        "https://example.com/wp-json/wp/v2/ml_report",
        status_code=200,
        payload=[
            {
                "id": 42,
                "link": "https://example.com/post/42",
                "content": {"rendered": "Drive fileId: file123"},
            }
        ],
    )
    wordpress_http.add_json(
        "POST",
        "https://example.com/wp-json/wp/v2/ml_report/42",
        status_code=200,
        payload={"id": 42, "link": "https://example.com/post/42", "status": "publish"},
    )

    results = orch.run_publish(settings, force_report_cards=True)

    assert len(results) == 1
    assert results[0].status == "published"
    assert results[0].post_id == 42
    assert (
        len(
            wordpress_http.calls_for(
                "POST", "https://example.com/wp-json/wp/v2/ml_report/42"
            )
        )
        == 1
    )
    assert (
        wordpress_http.calls_for("POST", "https://example.com/wp-json/wp/v2/ml_report")
        == []
    )


def test_publish_routes_report_by_embedded_entity_metadata(
    publish_settings_factory, run_context, wordpress_http
) -> None:
    settings = publish_settings_factory(validation_policy="warn")
    settings = replace(settings, wp=replace(settings.wp, post_type="posts"))
    _write_html(settings.output_dir, "report.html", "Drive fileId: file123")
    _record_processed(settings.state_db, "file123", run_context)
    wordpress_http.add_json(
        "GET",
        "https://example.com/wp-json/wp/v2/ml_report",
        status_code=200,
        payload=[],
    )
    wordpress_http.add_json(
        "POST",
        "https://example.com/wp-json/wp/v2/ml_report",
        status_code=201,
        payload={
            "id": 10,
            "link": "https://example.com/reports/10",
            "status": "publish",
        },
    )

    results = orch.run_publish(settings, limit=1)

    publish_row = get_publish(
        StatePublishCheckRequest(
            schema_version="1.0",
            state_db=settings.state_db,
            file_id="file123",
            post_type="ml_report",
        ),
        run_context,
    )
    assert len(results) == 1
    assert results[0].status == "published"
    assert publish_row is not None
    assert publish_row.post_type == "ml_report"
    assert (
        wordpress_http.calls_for("POST", "https://example.com/wp-json/wp/v2/posts")
        == []
    )


def test_publish_routes_signal_by_embedded_entity_metadata(
    publish_settings_factory, run_context, wordpress_http
) -> None:
    settings = publish_settings_factory(validation_policy="warn")
    _write_html(
        settings.output_dir,
        "signal.html",
        "Drive fileId: signal:checkout-trust",
        entity_type="signal",
        canonical_route_intent="wordpress:ml_signal",
        source_artifact_id="signal:checkout-trust",
    )
    _record_processed(settings.state_db, "signal:checkout-trust", run_context)
    wordpress_http.add_json(
        "GET",
        "https://example.com/wp-json/wp/v2/ml_signal",
        status_code=200,
        payload=[],
    )
    wordpress_http.add_json(
        "POST",
        "https://example.com/wp-json/wp/v2/ml_signal",
        status_code=201,
        payload={
            "id": 15,
            "link": "https://example.com/signals/checkout-trust/",
            "status": "publish",
        },
    )

    results = orch.run_publish(settings, limit=1)

    publish_row = get_publish(
        StatePublishCheckRequest(
            schema_version="1.0",
            state_db=settings.state_db,
            file_id="signal:checkout-trust",
            post_type="ml_signal",
        ),
        run_context,
    )
    assert len(results) == 1
    assert results[0].status == "published"
    assert results[0].post_url == "https://example.com/signals/checkout-trust/"
    assert publish_row is not None
    assert publish_row.post_type == "ml_signal"


def test_publish_uses_explicit_html_paths_over_output_listing(
    publish_settings_factory, run_context, wordpress_http
) -> None:
    settings = publish_settings_factory(validation_policy="warn")
    _write_html(settings.output_dir, "aaa-first.html", "Drive fileId: first")
    target = _write_html(settings.output_dir, "zzz-target.html", "Drive fileId: target")
    _record_processed(settings.state_db, "target", run_context)
    wordpress_http.add_json(
        "GET",
        "https://example.com/wp-json/wp/v2/ml_report",
        status_code=200,
        payload=[],
    )
    wordpress_http.add_json(
        "POST",
        "https://example.com/wp-json/wp/v2/ml_report",
        status_code=201,
        payload={"id": 10, "link": "https://example.com/post/10", "status": "publish"},
    )

    results = orch.run_publish(settings, limit=1, html_paths=[str(target)])

    assert len(results) == 1
    assert results[0].status == "published"
    assert results[0].file_id == "target"


def test_publish_auto_discovery_skips_unowned_html_before_limit(
    publish_settings_factory, run_context, wordpress_http, caplog
) -> None:
    settings = publish_settings_factory(validation_policy="warn")
    _write_html(
        settings.output_dir,
        "aaa-enterprise-prototype.html",
        "<p>Design prototype only</p>",
        include_entity_metadata=False,
    )
    _write_html(settings.output_dir, "zzz-report.html", "Drive fileId: file123")
    _record_processed(settings.state_db, "file123", run_context)
    wordpress_http.add_json(
        "GET",
        "https://example.com/wp-json/wp/v2/ml_report",
        status_code=200,
        payload=[],
    )
    wordpress_http.add_json(
        "POST",
        "https://example.com/wp-json/wp/v2/ml_report",
        status_code=201,
        payload={"id": 10, "link": "https://example.com/post/10", "status": "publish"},
    )

    with caplog.at_level(logging.INFO, logger="market_lense.publish_orchestrator"):
        results = orch.run_publish(settings, limit=1)

    events = _json_events(caplog, "market_lense.publish_orchestrator")
    assert len(results) == 1
    assert results[0].status == "published"
    assert results[0].file_id == "file123"
    assert any(
        event.get("event") == "publish_non_entity_html_skipped" for event in events
    )


def test_publish_auto_discovery_orders_reports_by_metadata_updated_at_before_limit(
    publish_settings_factory, run_context, wordpress_http
) -> None:
    settings = publish_settings_factory(validation_policy="warn")
    old_html = _write_html(
        settings.output_dir,
        "aaa-old-report.html",
        "Drive fileId: old-file",
        source_artifact_id="old-file",
    )
    new_html = _write_html(
        settings.output_dir,
        "zzz-new-report.html",
        "Drive fileId: new-file",
        source_artifact_id="new-file",
    )
    _record_processed(settings.state_db, "old-file", run_context)
    _record_processed(settings.state_db, "new-file", run_context)
    _seed_report_metadata(settings.reports_db, str(old_html), "old-file", run_context)
    _seed_report_metadata(settings.reports_db, str(new_html), "new-file", run_context)
    with sqlite3.connect(settings.reports_db) as conn:
        conn.execute(
            "UPDATE reports SET updated_at = 100 WHERE file_id = ?", ("old-file",)
        )
        conn.execute(
            "UPDATE reports SET updated_at = 200 WHERE file_id = ?", ("new-file",)
        )
        conn.commit()
    wordpress_http.add_json(
        "GET",
        "https://example.com/wp-json/wp/v2/ml_report",
        status_code=200,
        payload=[],
    )
    wordpress_http.add_json(
        "POST",
        "https://example.com/wp-json/wp/v2/ml_report",
        status_code=201,
        payload={"id": 10, "link": "https://example.com/post/10", "status": "publish"},
    )

    results = orch.run_publish(settings, limit=1)

    assert len(results) == 1
    assert results[0].status == "published"
    assert results[0].file_id == "new-file"


def test_publish_reuses_idempotent_outcome_without_second_post(
    publish_settings_factory, run_context, wordpress_http
) -> None:
    settings = publish_settings_factory(validation_policy="warn")
    html_path = _write_html(settings.output_dir, "report.html", "Drive fileId: file123")
    _record_processed(settings.state_db, "file123", run_context)
    _seed_report_metadata(
        settings.reports_db,
        str(html_path),
        "file123",
        run_context,
        publisher="WARC",
    )
    lookup_calls = []

    def _lookup_posts(call: RecordedHttpRequest) -> FakeHttpResponse:
        lookup_calls.append(call)
        payload = (
            []
            if len(lookup_calls) == 1
            else [
                {
                    "id": 10,
                    "link": "https://example.com/post/10",
                    "content": {"rendered": "Drive fileId: file123"},
                }
            ]
        )
        return FakeHttpResponse.from_payload(status_code=200, payload=payload)

    wordpress_http.add(
        "GET", "https://example.com/wp-json/wp/v2/ml_report", _lookup_posts
    )
    wordpress_http.add_json(
        "POST",
        "https://example.com/wp-json/wp/v2/ml_report",
        status_code=201,
        payload={"id": 10, "link": "https://example.com/post/10", "status": "publish"},
    )
    wordpress_http.add_json(
        "GET",
        "https://example.com/wp-json/wp/v2/ml_publisher",
        status_code=200,
        payload=[],
    )
    wordpress_http.add_json(
        "POST",
        "https://example.com/wp-json/wp/v2/ml_publisher",
        status_code=201,
        payload={"id": 21},
    )

    first = orch.run_publish(settings, limit=1)
    second = orch.run_publish(settings, limit=1)

    assert first[0].status == "published"
    assert second[0].status == "skipped"
    assert second[0].post_id == 10
    assert second[0].post_url == "https://example.com/post/10"
    assert second[0].publication_outcome == "existing_post_matched"
    assert second[0].authenticated_readback_verified is True
    assert second[0].requested_write_count == 0
    assert second[0].actual_write_count == 0
    assert (
        len(
            wordpress_http.calls_for(
                "POST", "https://example.com/wp-json/wp/v2/ml_report"
            )
        )
        == 1
    )
    assert (
        len(
            wordpress_http.calls_for(
                "POST", "https://example.com/wp-json/wp/v2/ml_publisher"
            )
        )
        == 1
    )


def test_publish_limit_applies_to_attempted_items_when_first_item_errors(
    publish_settings_factory, run_context, wordpress_http
) -> None:
    settings = publish_settings_factory(validation_policy="warn")
    _write_html(settings.output_dir, "first.html", "Drive fileId: first123")
    _write_html(settings.output_dir, "second.html", "Drive fileId: second123")
    _record_processed(settings.state_db, "first123", run_context)
    _record_processed(settings.state_db, "second123", run_context)
    wordpress_http.add(
        "GET",
        "https://example.com/wp-json/wp/v2/ml_report",
        RuntimeError("ssl certificate verify failed"),
    )

    results = orch.run_publish(settings, limit=1)

    assert len(results) == 1
    assert results[0].file_id == "first123"
    assert results[0].status == "error"
    assert (
        len(
            wordpress_http.calls_for(
                "GET", "https://example.com/wp-json/wp/v2/ml_report"
            )
        )
        == 2
    )


def test_publish_blocks_when_validation_fails(
    publish_settings_factory, run_context, wordpress_http
) -> None:
    settings = publish_settings_factory(validation_policy="block")
    _write_html(settings.output_dir, "report.html", "Drive fileId: file123")
    validation_path = (
        Path(settings.output_dir) / "report" / "report_analysis" / "validation.json"
    )
    validation_path.parent.mkdir(parents=True, exist_ok=True)
    validation_path.write_text(
        json.dumps(
            {
                "schema_version": "1.1",
                "status": "fail",
                "severity": "error",
                "issues": [
                    {
                        "schema_version": "1.0",
                        "message": "bad data",
                        "severity": "error",
                        "affected_section": "insights",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    _record_processed(settings.state_db, "file123", run_context)

    results = orch.run_publish(settings, limit=1)

    publish_row = get_publish(
        StatePublishCheckRequest(
            schema_version="1.0",
            state_db=settings.state_db,
            file_id="file123",
            post_type=settings.wp.post_type,
        ),
        run_context,
    )
    assert len(results) == 1
    assert results[0].status == "error"
    assert results[0].error == "validation_failed"
    assert results[0].validation_status == "fail"
    assert results[0].validation_issues == ["bad data"]
    assert wordpress_http.calls == []
    assert publish_row is None


def test_publish_missing_entity_metadata_fails_before_wordpress(
    publish_settings_factory, run_context, wordpress_http
) -> None:
    settings = publish_settings_factory(validation_policy="warn")
    _write_html(
        settings.output_dir,
        "report.html",
        "Drive fileId: file123",
        include_entity_metadata=False,
    )
    _record_processed(settings.state_db, "file123", run_context)

    results = orch.run_publish(settings, limit=1)

    assert len(results) == 1
    assert results[0].status == "error"
    assert results[0].error == "publish_entity_metadata_missing"
    assert wordpress_http.calls == []


def test_publish_unknown_entity_metadata_fails_before_wordpress(
    publish_settings_factory, run_context, wordpress_http
) -> None:
    settings = publish_settings_factory(validation_policy="warn")
    _write_html(
        settings.output_dir,
        "unknown.html",
        "Drive fileId: entity123",
        entity_type="unknown",
        canonical_route_intent="wordpress:ml_unknown",
        source_artifact_id="entity123",
    )
    _record_processed(settings.state_db, "entity123", run_context)

    results = orch.run_publish(settings, limit=1)

    assert len(results) == 1
    assert results[0].status == "error"
    assert results[0].error == "publish_entity_metadata_unsupported"
    assert wordpress_http.calls == []


def test_publish_mismatched_entity_metadata_fails_before_wordpress(
    publish_settings_factory, run_context, wordpress_http
) -> None:
    settings = publish_settings_factory(validation_policy="warn")
    _write_html(
        settings.output_dir,
        "mismatch.html",
        "Drive fileId: file123",
        entity_type="report",
        canonical_route_intent="wordpress:ml_signal",
        source_artifact_id="file123",
    )
    _record_processed(settings.state_db, "file123", run_context)

    results = orch.run_publish(settings, limit=1)

    assert len(results) == 1
    assert results[0].status == "error"
    assert results[0].error == "publish_entity_metadata_mismatch"
    assert wordpress_http.calls == []


def test_publish_prefers_reports_db_file_id_mapping(
    publish_settings_factory, run_context, wordpress_http
) -> None:
    settings = publish_settings_factory(validation_policy="warn")
    html_path = _write_html(
        settings.output_dir, "report.html", "No explicit file marker"
    )
    _record_processed(settings.state_db, "file_from_db", run_context)
    _seed_report_metadata(
        settings.reports_db, str(html_path), "file_from_db", run_context
    )
    wordpress_http.add_json(
        "GET",
        "https://example.com/wp-json/wp/v2/ml_report",
        status_code=200,
        payload=[],
    )
    wordpress_http.add_json(
        "POST",
        "https://example.com/wp-json/wp/v2/ml_report",
        status_code=201,
        payload={"id": 77, "link": "https://example.com/post/77", "status": "publish"},
    )

    results = orch.run_publish(settings, limit=1)
    post_call = wordpress_http.calls_for(
        "POST", "https://example.com/wp-json/wp/v2/ml_report"
    )[0]

    assert len(results) == 1
    assert results[0].status == "published"
    assert results[0].file_id == "file_from_db"
    assert "Drive fileId:" not in post_call.json_data["content"]
    assert post_call.json_data["meta"]["ml_file_id"] == "file_from_db"


def test_publish_reuses_preloaded_html_snapshot_after_preflight_read(
    publish_settings_factory,
    run_context,
    wordpress_http,
    external_boundary_mocks_only,
) -> None:
    settings = publish_settings_factory(validation_policy="warn")
    html_path = _write_html(settings.output_dir, "report.html", "Drive fileId: file123")
    _record_processed(settings.state_db, "file123", run_context)
    wordpress_http.add_json(
        "GET",
        "https://example.com/wp-json/wp/v2/ml_report",
        status_code=200,
        payload=[],
    )
    wordpress_http.add_json(
        "POST",
        "https://example.com/wp-json/wp/v2/ml_report",
        status_code=201,
        payload={"id": 44, "link": "https://example.com/post/44", "status": "publish"},
    )

    real_get_outcome = orch.idempotency_service.get_outcome

    def _delete_html_then_lookup(request, ctx):
        html_path.unlink(missing_ok=True)
        return real_get_outcome(request, ctx)

    external_boundary_mocks_only.setattr(
        orch.idempotency_service,
        "get_outcome",
        _delete_html_then_lookup,
    )

    results = orch.run_publish(settings, limit=1)

    assert len(results) == 1
    assert results[0].status == "published"
    assert results[0].file_id == "file123"
    assert not html_path.exists()


def test_publish_uses_canonical_validation_json_over_regen_snapshots(
    publish_settings_factory, run_context, wordpress_http
) -> None:
    settings = publish_settings_factory(validation_policy="block")
    _write_html(settings.output_dir, "report.html", "Drive fileId: file123")
    report_analysis_dir = Path(settings.output_dir) / "report" / "report_analysis"
    report_analysis_dir.mkdir(parents=True, exist_ok=True)
    (report_analysis_dir / "validation.json").write_text(
        json.dumps(
            {
                "schema_version": "1.1",
                "status": "pass",
                "severity": "pass",
                "issues": [],
            }
        ),
        encoding="utf-8",
    )
    (report_analysis_dir / "validation_regen_attempt_1.json").write_text(
        json.dumps(
            {
                "schema_version": "1.1",
                "status": "fail",
                "severity": "error",
                "issues": [
                    {
                        "schema_version": "1.0",
                        "message": "stale attempt failure",
                        "severity": "error",
                        "affected_section": "summary",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    _record_processed(settings.state_db, "file123", run_context)
    wordpress_http.add_json(
        "GET",
        "https://example.com/wp-json/wp/v2/ml_report",
        status_code=200,
        payload=[],
    )
    wordpress_http.add_json(
        "POST",
        "https://example.com/wp-json/wp/v2/ml_report",
        status_code=201,
        payload={"id": 88, "link": "https://example.com/post/88", "status": "publish"},
    )

    results = orch.run_publish(settings, limit=1)

    assert len(results) == 1
    assert results[0].status == "published"
    assert results[0].validation_status == "pass"
    assert results[0].validation_issues == []
    assert (
        len(
            wordpress_http.calls_for(
                "POST", "https://example.com/wp-json/wp/v2/ml_report"
            )
        )
        == 1
    )


__all__ = [
    "test_publish_runs_when_processed",
    "test_publish_routes_report_by_embedded_entity_metadata",
    "test_publish_routes_signal_by_embedded_entity_metadata",
    "test_publish_uses_explicit_html_paths_over_output_listing",
    "test_publish_auto_discovery_skips_unowned_html_before_limit",
    "test_publish_auto_discovery_orders_reports_by_metadata_updated_at_before_limit",
    "test_publish_reuses_idempotent_outcome_without_second_post",
    "test_publish_limit_applies_to_attempted_items_when_first_item_errors",
    "test_publish_blocks_when_validation_fails",
    "test_publish_missing_entity_metadata_fails_before_wordpress",
    "test_publish_unknown_entity_metadata_fails_before_wordpress",
    "test_publish_mismatched_entity_metadata_fails_before_wordpress",
    "test_publish_prefers_reports_db_file_id_mapping",
    "test_publish_reuses_preloaded_html_snapshot_after_preflight_read",
    "test_publish_uses_canonical_validation_json_over_regen_snapshots",
]
