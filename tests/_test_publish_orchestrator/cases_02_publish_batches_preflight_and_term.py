# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403


def test_publish_batches_preflight_and_term_resolution(
    publish_settings_factory,
    run_context,
    wordpress_http,
    caplog,
    assert_logs_have_required_fields,
) -> None:
    settings = publish_settings_factory(validation_policy="warn", ssl_verify=False)
    first_html = _write_html(settings.output_dir, "first.html", "Drive fileId: file123")
    second_html = _write_html(
        settings.output_dir, "second.html", "Drive fileId: file456"
    )
    _record_processed(settings.state_db, "file123", run_context)
    _record_processed(settings.state_db, "file456", run_context)
    upsert_metadata(
        ReportMetadataUpsertRequest(
            schema_version="1.1",
            db_path=settings.reports_db,
            file_id="file123",
            title="First",
            file_name="first.pdf",
            publisher="WARC",
            taxonomy=["shared-tag", "new-tag"],
            categories=["digital_payments", "retail_media"],
            region=None,
            time_period=None,
            source_url=None,
            html_path=str(first_html),
            md5="md5",
            page_count=None,
            contents_page_number=0,
            pdf_metadata={},
            analysis_mode="vector_store",
            vector_store_id=None,
            evidence_pack_paths={},
        ),
        run_context,
    )
    upsert_metadata(
        ReportMetadataUpsertRequest(
            schema_version="1.1",
            db_path=settings.reports_db,
            file_id="file456",
            title="Second",
            file_name="second.pdf",
            publisher="WARC",
            taxonomy=["shared-tag", "new-tag"],
            categories=["digital_payments", "retail_media"],
            region=None,
            time_period=None,
            source_url=None,
            html_path=str(second_html),
            md5="md5",
            page_count=None,
            contents_page_number=0,
            pdf_metadata={},
            analysis_mode="vector_store",
            vector_store_id=None,
            evidence_pack_paths={},
        ),
        run_context,
    )

    def _lookup_posts(call: RecordedHttpRequest) -> FakeHttpResponse:
        params = call.params or {}
        search = str(params.get("search") or "")
        if "file123" in search:
            return FakeHttpResponse.from_payload(
                status_code=200,
                payload=[
                    {
                        "id": 501,
                        "link": "https://example.com/post/501",
                        "content": {"rendered": "Drive fileId: file123"},
                    }
                ],
            )
        return FakeHttpResponse.from_payload(status_code=200, payload=[])

    written_categories: dict[str, dict[str, object]] = {}

    def _lookup_categories(call: RecordedHttpRequest) -> FakeHttpResponse:
        slug = str((call.params or {}).get("slug") or "")
        if call.params.get("context") == "edit":
            payload = written_categories.get(slug)
            if not payload:
                raise AssertionError(
                    f"category semantics not written before readback: {slug}"
                )
            return FakeHttpResponse.from_payload(
                status_code=200,
                payload=[
                    {
                        "id": 11 if slug == "digital_payments" else 12,
                        "description": payload.get("description", ""),
                        "meta": payload.get("meta", {}),
                    }
                ],
            )
        if slug == "digital_payments":
            return FakeHttpResponse.from_payload(status_code=200, payload=[{"id": 11}])
        return FakeHttpResponse.from_payload(status_code=200, payload=[])

    def _create_categories(call: RecordedHttpRequest) -> FakeHttpResponse:
        payload = call.json_data or {}
        if payload.get("slug") == "retail_media":
            written_categories["retail_media"] = payload
            return FakeHttpResponse.from_payload(status_code=201, payload={"id": 12})
        raise AssertionError(f"unexpected category payload: {payload}")

    def _update_categories(call: RecordedHttpRequest) -> FakeHttpResponse:
        payload = call.json_data or {}
        if payload.get("slug") == "digital_payments":
            written_categories["digital_payments"] = payload
            return FakeHttpResponse.from_payload(status_code=200, payload={"id": 11})
        raise AssertionError(f"unexpected category update payload: {payload}")

    def _lookup_publishers(call: RecordedHttpRequest) -> FakeHttpResponse:
        _ = call
        return FakeHttpResponse.from_payload(status_code=200, payload=[])

    def _create_publishers(call: RecordedHttpRequest) -> FakeHttpResponse:
        payload = call.json_data or {}
        if payload.get("slug") == "warc":
            return FakeHttpResponse.from_payload(status_code=201, payload={"id": 22})
        raise AssertionError(f"unexpected publisher payload: {payload}")

    def _lookup_tags(call: RecordedHttpRequest) -> FakeHttpResponse:
        slug = str((call.params or {}).get("slug") or "")
        if slug == "shared-tag":
            return FakeHttpResponse.from_payload(status_code=200, payload=[{"id": 31}])
        return FakeHttpResponse.from_payload(status_code=200, payload=[])

    def _create_tags(call: RecordedHttpRequest) -> FakeHttpResponse:
        payload = call.json_data or {}
        if payload.get("slug") == "new-tag":
            return FakeHttpResponse.from_payload(status_code=201, payload={"id": 32})
        raise AssertionError(f"unexpected tag payload: {payload}")

    caplog.set_level(logging.INFO)
    wordpress_http.add(
        "GET", "https://example.com/wp-json/wp/v2/ml_report", _lookup_posts
    )
    wordpress_http.add(
        "GET", "https://example.com/wp-json/wp/v2/categories", _lookup_categories
    )
    wordpress_http.add(
        "POST", "https://example.com/wp-json/wp/v2/categories", _create_categories
    )
    wordpress_http.add(
        "POST",
        "https://example.com/wp-json/wp/v2/categories/11",
        _update_categories,
    )
    wordpress_http.add(
        "GET", "https://example.com/wp-json/wp/v2/ml_publisher", _lookup_publishers
    )
    wordpress_http.add(
        "POST", "https://example.com/wp-json/wp/v2/ml_publisher", _create_publishers
    )
    wordpress_http.add("GET", "https://example.com/wp-json/wp/v2/tags", _lookup_tags)
    wordpress_http.add("POST", "https://example.com/wp-json/wp/v2/tags", _create_tags)
    wordpress_http.add_json(
        "POST",
        "https://example.com/wp-json/wp/v2/ml_report",
        status_code=201,
        payload={"id": 77, "link": "https://example.com/post/77", "status": "publish"},
    )

    results = orch.run_publish(settings, limit=2, ctx=run_context)

    first_publish_row = get_publish(
        StatePublishCheckRequest(
            schema_version="1.0",
            state_db=settings.state_db,
            file_id="file123",
            post_type=settings.wp.post_type,
        ),
        run_context,
    )
    second_post_call = wordpress_http.calls_for(
        "POST", "https://example.com/wp-json/wp/v2/ml_report"
    )[0]
    events = _json_events(caplog, orch.logger.name)
    results_by_file_id = {str(result.file_id or ""): result for result in results}
    assert results_by_file_id["file123"].status == "skipped"
    assert results_by_file_id["file123"].error == "already_exists"
    assert results_by_file_id["file123"].post_id == 501
    assert results_by_file_id["file123"].publication_outcome == "existing_post_matched"
    assert results_by_file_id["file123"].lookup_count == 1
    assert results_by_file_id["file123"].authenticated_readback_verified is True
    assert results_by_file_id["file123"].requested_write_count == 0
    assert results_by_file_id["file123"].actual_write_count == 0
    assert results_by_file_id["file456"].status == "published"
    assert second_post_call.json_data["categories"] == [11, 12]
    assert second_post_call.json_data["tags"] == [31, 32]
    assert second_post_call.json_data["ml_publisher"] == [22]
    assert first_publish_row is not None
    assert first_publish_row.wp_post_id == 501
    category_get_calls = wordpress_http.calls_for(
        "GET", "https://example.com/wp-json/wp/v2/categories"
    )
    assert len(category_get_calls) == 4
    assert [
        call.params.get("context")
        for call in category_get_calls
        if call.params.get("context") == "edit"
    ] == ["edit", "edit"]
    assert (
        len(wordpress_http.calls_for("GET", "https://example.com/wp-json/wp/v2/tags"))
        == 2
    )
    assert (
        len(
            wordpress_http.calls_for(
                "GET", "https://example.com/wp-json/wp/v2/ml_publisher"
            )
        )
        == 1
    )
    assert any(event.get("event") == "publish_preflight_complete" for event in events)
    assert_logs_have_required_fields(events)


def test_publish_preflight_term_batch_failure_does_not_block_other_files(
    publish_settings_factory,
    run_context,
    wordpress_http,
) -> None:
    settings = publish_settings_factory(validation_policy="warn")
    ok_html = _write_html(settings.output_dir, "ok.html", "Drive fileId: file-ok")
    bad_html = _write_html(settings.output_dir, "bad.html", "Drive fileId: file-bad")
    _record_processed(settings.state_db, "file-ok", run_context)
    _record_processed(settings.state_db, "file-bad", run_context)
    upsert_metadata(
        ReportMetadataUpsertRequest(
            schema_version="1.1",
            db_path=settings.reports_db,
            file_id="file-ok",
            title="OK",
            file_name="ok.pdf",
            publisher=None,
            taxonomy=[],
            categories=[],
            region=None,
            time_period=None,
            source_url=None,
            html_path=str(ok_html),
            md5="md5",
            page_count=None,
            contents_page_number=0,
            pdf_metadata={},
            analysis_mode="vector_store",
            vector_store_id=None,
            evidence_pack_paths={},
        ),
        run_context,
    )
    upsert_metadata(
        ReportMetadataUpsertRequest(
            schema_version="1.1",
            db_path=settings.reports_db,
            file_id="file-bad",
            title="BAD",
            file_name="bad.pdf",
            publisher=None,
            taxonomy=["broken-tag"],
            categories=[],
            region=None,
            time_period=None,
            source_url=None,
            html_path=str(bad_html),
            md5="md5",
            page_count=None,
            contents_page_number=0,
            pdf_metadata={},
            analysis_mode="vector_store",
            vector_store_id=None,
            evidence_pack_paths={},
        ),
        run_context,
    )

    def _lookup_posts(_call: RecordedHttpRequest) -> FakeHttpResponse:
        return FakeHttpResponse.from_payload(status_code=200, payload=[])

    def _lookup_tags(call: RecordedHttpRequest) -> FakeHttpResponse:
        slug = str((call.params or {}).get("slug") or "")
        if slug == "broken-tag":
            return FakeHttpResponse.from_payload(
                status_code=503,
                payload={"message": "retry"},
            )
        return FakeHttpResponse.from_payload(status_code=200, payload=[])

    wordpress_http.add(
        "GET", "https://example.com/wp-json/wp/v2/ml_report", _lookup_posts
    )
    wordpress_http.add("GET", "https://example.com/wp-json/wp/v2/tags", _lookup_tags)
    wordpress_http.add_json(
        "POST",
        "https://example.com/wp-json/wp/v2/ml_report",
        status_code=201,
        payload={"id": 88, "link": "https://example.com/post/88", "status": "publish"},
    )

    results = orch.run_publish(settings, limit=2, ctx=run_context)

    assert [result.status for result in results] == ["error", "published"]
    assert results[0].file_id == "file-bad"
    assert results[1].file_id == "file-ok"
    assert (
        len(
            wordpress_http.calls_for(
                "POST", "https://example.com/wp-json/wp/v2/ml_report"
            )
        )
        == 1
    )


def test_publish_retries_retryable_app_error(
    publish_settings_factory,
    run_context,
    wordpress_http,
    caplog,
    external_boundary_mocks_only,
    assert_logs_have_required_fields,
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
    wordpress_http.add(
        "POST",
        "https://example.com/wp-json/wp/v2/ml_report",
        FakeHttpResponse.from_payload(status_code=503, payload={"message": "retry"}),
        FakeHttpResponse.from_payload(status_code=503, payload={"message": "retry"}),
        FakeHttpResponse.from_payload(
            status_code=201,
            payload={
                "id": 33,
                "link": "https://example.com/post/33",
                "status": "publish",
            },
        ),
    )
    sleep_calls: list[int] = []
    caplog.set_level(logging.INFO)
    external_boundary_mocks_only.setattr(
        retry_orchestrator.random, "uniform", lambda _a, _b: 0.0
    )
    external_boundary_mocks_only.setattr(
        orch.time, "sleep", lambda seconds: sleep_calls.append(int(seconds))
    )

    results = orch.run_publish(settings, limit=1)

    retry_logs = [
        record
        for record in caplog.records
        if '"event": "publish_retry"' in record.message
    ]
    assert len(results) == 1
    assert results[0].status == "published"
    assert results[0].file_id == "file123"
    assert (
        len(
            wordpress_http.calls_for(
                "GET", "https://example.com/wp-json/wp/v2/ml_report"
            )
        )
        == 1
    )
    assert (
        len(
            wordpress_http.calls_for(
                "POST", "https://example.com/wp-json/wp/v2/ml_report"
            )
        )
        == 3
    )
    assert sleep_calls == [1, 2]
    assert len(retry_logs) == 2
    assert_logs_have_required_fields(caplog.records)


def test_publish_ignores_publish_state_for_different_post_type(
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
            wp_post_id=99,
            wp_post_url="https://example.com/post/99",
            post_type="posts",
        ),
        run_context,
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
        payload={
            "id": 101,
            "link": "https://example.com/reports/101",
            "status": "publish",
        },
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
    assert len(results) == 1
    assert results[0].status == "published"
    assert publish_row is not None
    assert publish_row.wp_post_id == 101
    assert publish_row.post_type == settings.wp.post_type


def test_publish_uses_provided_run_context_for_logs(
    publish_settings_factory,
    run_context,
    wordpress_http,
    caplog,
    assert_logs_have_required_fields,
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

    caplog.set_level(logging.INFO, logger=orch.logger.name)
    results = orch.run_publish(settings, limit=1, ctx=run_context)

    events = _json_events(caplog, orch.logger.name)
    assert len(results) == 1
    assert results[0].status == "published"
    assert_logs_have_required_fields(events)
    assert any(event.get("event") == "publish_start" for event in events)
    assert any(event.get("event") == "publish_complete" for event in events)
    assert all(event.get("run_id") == run_context.run_id for event in events)


__all__ = [
    "test_publish_batches_preflight_and_term_resolution",
    "test_publish_preflight_term_batch_failure_does_not_block_other_files",
    "test_publish_retries_retryable_app_error",
    "test_publish_ignores_publish_state_for_different_post_type",
    "test_publish_uses_provided_run_context_for_logs",
]
