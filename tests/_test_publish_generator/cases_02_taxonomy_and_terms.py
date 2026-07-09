from __future__ import annotations

from ._shared import *  # noqa: F401,F403

# ruff: noqa: F401,F403,F405


def test_publish_html_assigns_publisher_taxonomy_terms(
    publish_settings_factory,
    run_context,
    wordpress_http,
    assert_no_defaulted_required_fields,
) -> None:
    settings = publish_settings_factory(validation_policy="warn", ssl_verify=False)
    html_path = Path(settings.output_dir) / "report.html"
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_text = (
        "<html><head><title>Report</title></head>"
        "<body>Drive fileId: file123</body></html>"
    )
    html_path.write_text(html_text, encoding="utf-8")
    write_report_card_fixture(settings, html_path)
    add_card_media_responses(wordpress_http)
    upsert_metadata(
        ReportMetadataUpsertRequest(
            schema_version="1.1",
            db_path=settings.reports_db,
            file_id="file123",
            title="Report",
            file_name="report.pdf",
            publisher="WARC",
            taxonomy=[],
            categories=["digital_payments"],
            region=None,
            time_period=None,
            source_url=None,
            html_path=str(html_path),
            md5=None,
            page_count=None,
            contents_page_number=0,
            pdf_metadata={},
            analysis_mode="vector_store",
            vector_store_id=None,
            evidence_pack_paths={},
        ),
        run_context,
    )

    created_terms: dict[str, dict[str, object]] = {}

    def _lookup_missing(call: RecordedHttpRequest) -> FakeHttpResponse:
        slug = str((call.params or {}).get("slug") or "")
        if call.url.endswith("/categories") and call.params.get("context") == "edit":
            payload = created_terms.get(slug)
            if not payload:
                raise AssertionError(
                    f"category semantics missing before readback: {slug}"
                )
            term_id = 11 if slug == "digital_payments" else 22
            return FakeHttpResponse.from_payload(
                status_code=200,
                payload=[
                    {
                        "id": term_id,
                        "description": payload.get("description", ""),
                        "meta": payload.get("meta", {}),
                    }
                ],
            )
        return FakeHttpResponse.from_payload(status_code=200, payload=[])

    def _create_term(call: RecordedHttpRequest) -> FakeHttpResponse:
        payload = call.json_data
        term_id = 11 if payload["slug"] == "digital_payments" else 22
        if call.url.endswith("/categories"):
            created_terms[str(payload["slug"])] = payload
        return FakeHttpResponse.from_payload(status_code=201, payload={"id": term_id})

    wordpress_http.add(
        "GET", "https://example.com/wp-json/wp/v2/categories", _lookup_missing
    )
    wordpress_http.add(
        "POST", "https://example.com/wp-json/wp/v2/categories", _create_term
    )
    wordpress_http.add(
        "GET", "https://example.com/wp-json/wp/v2/ml_publisher", _lookup_missing
    )
    wordpress_http.add(
        "POST", "https://example.com/wp-json/wp/v2/ml_publisher", _create_term
    )
    wordpress_http.add_json(
        "POST",
        "https://example.com/wp-json/wp/v2/ml_report",
        status_code=201,
        payload={"id": 42, "link": "https://example.com/post/42", "status": "publish"},
    )

    outcome = pg.publish_html(
        PublishRequest(
            schema_version="1.0",
            html_path=str(html_path),
            auth_header="Bearer token",
            file_id=None,
            html_text=None,
        ),
        settings,
        run_context,
    )

    post_call = wordpress_http.calls_for(
        "POST", "https://example.com/wp-json/wp/v2/ml_report"
    )[0]
    taxonomy_calls = [
        *wordpress_http.calls_for(
            "GET", "https://example.com/wp-json/wp/v2/categories"
        ),
        *wordpress_http.calls_for(
            "POST", "https://example.com/wp-json/wp/v2/categories"
        ),
        *wordpress_http.calls_for(
            "GET", "https://example.com/wp-json/wp/v2/ml_publisher"
        ),
        *wordpress_http.calls_for(
            "POST", "https://example.com/wp-json/wp/v2/ml_publisher"
        ),
    ]
    assert_no_defaulted_required_fields(outcome)
    assert outcome.status == "published"
    assert post_call.json_data["categories"] == [11]
    assert post_call.json_data["ml_publisher"] == [22]
    assert post_call.verify is False
    assert taxonomy_calls
    assert all(call.verify is False for call in taxonomy_calls)


def test_publish_html_uses_pre_resolved_terms_without_term_lookups(
    publish_settings_factory,
    run_context,
    wordpress_http,
    assert_no_defaulted_required_fields,
) -> None:
    settings = publish_settings_factory(validation_policy="warn")
    write_report_card_fixture(settings, "out/report.html")
    add_card_media_responses(wordpress_http)
    html_text = (
        "<html><head><title>Report</title></head>"
        "<body>Drive fileId: file123</body></html>"
    )
    wordpress_http.add_json(
        "POST",
        "https://example.com/wp-json/wp/v2/ml_report",
        status_code=201,
        payload={"id": 42, "link": "https://example.com/post/42", "status": "publish"},
    )

    outcome = pg.publish_html(
        PublishRequest(
            schema_version="1.0",
            html_path="out/report.html",
            auth_header="Bearer token",
            file_id="file123",
            html_text=html_text,
            resolved_terms=PublishResolvedTerms(
                schema_version="1.0",
                category_ids=[11],
                tag_ids=[31, 32],
                taxonomy_terms={"ml_publisher": [22]},
            ),
        ),
        settings,
        run_context,
    )

    post_call = wordpress_http.calls_for(
        "POST", "https://example.com/wp-json/wp/v2/ml_report"
    )[0]
    assert_no_defaulted_required_fields(outcome)
    assert outcome.status == "published"
    assert post_call.json_data["categories"] == [11]
    assert post_call.json_data["tags"] == [31, 32]
    assert post_call.json_data["ml_publisher"] == [22]
    assert (
        wordpress_http.calls_for("GET", "https://example.com/wp-json/wp/v2/categories")
        == []
    )
    assert (
        wordpress_http.calls_for("GET", "https://example.com/wp-json/wp/v2/tags") == []
    )


def test_publish_html_uses_request_slug_override_for_prebuilt_publish_packages(
    publish_settings_factory,
    run_context,
    wordpress_http,
) -> None:
    settings = publish_settings_factory(validation_policy="warn")
    html_text = (
        "<html><head><title>AI Commerce Across Reports</title></head>"
        "<body>Drive fileId: cross-report:analysis-ai</body></html>"
    )
    wordpress_http.add_json(
        "POST",
        "https://example.com/wp-json/wp/v2/ml_report",
        status_code=201,
        payload={"id": 42, "link": "https://example.com/post/42", "status": "publish"},
    )

    pg.publish_html(
        PublishRequest(
            schema_version="1.0",
            html_path="out/briefing.html",
            auth_header="Bearer token",
            file_id="cross-report:analysis-ai",
            html_text=html_text,
            slug="ai-commerce-across-reports",
            resolved_terms=PublishResolvedTerms(schema_version="1.0"),
        ),
        settings,
        run_context,
    )

    post_call = wordpress_http.calls_for(
        "POST", "https://example.com/wp-json/wp/v2/ml_report"
    )[0]
    assert post_call.json_data["slug"] == "ai-commerce-across-reports"
