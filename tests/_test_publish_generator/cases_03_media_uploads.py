from __future__ import annotations

from ._shared import *  # noqa: F401,F403

# ruff: noqa: F401,F403,F405


def test_publish_html_rewrites_uploaded_images_to_media_proxy(
    publish_settings_factory,
    run_context,
    wordpress_http,
    assert_no_defaulted_required_fields,
) -> None:
    settings = publish_settings_factory(validation_policy="warn")
    html_path = Path(settings.output_dir) / "report.html"
    assets_dir = Path(settings.output_dir) / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    image_path = assets_dir / "cover.png"
    image_path.write_bytes(b"png-bytes")
    html_text = (
        "<html><head><title>Report</title></head>"
        "<body>Drive fileId: file123"
        '<img src="assets/cover.png" '
        'srcset="assets/cover.png 1x, assets/cover.png 2x" '
        'sizes="100vw" alt="cover"></body></html>'
    )
    html_path.write_text(html_text, encoding="utf-8")
    wordpress_http.add_json(
        "POST",
        "https://example.com/wp-json/wp/v2/media",
        status_code=201,
        payload={
            "id": 55,
            "source_url": "https://example.com/wp-content/uploads/cover.png",
        },
    )
    wordpress_http.add_json(
        "POST",
        "https://example.com/wp-json/wp/v2/media/55",
        status_code=200,
        payload={"id": 55},
    )
    write_report_card_fixture(settings, html_path)
    add_card_media_responses(wordpress_http)
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
            file_id="file123",
            html_text=None,
        ),
        settings,
        run_context,
    )

    post_call = wordpress_http.calls_for(
        "POST", "https://example.com/wp-json/wp/v2/ml_report"
    )[0]
    assert_no_defaulted_required_fields(outcome)
    assert outcome.status == "published"
    assert post_call.json_data["featured_media"] == 303
    assert "/?ml_media=55" in post_call.json_data["content"]
    assert "wp-content/uploads/cover.png" not in post_call.json_data["content"]
    assert "srcset=" not in post_call.json_data["content"]
    assert "sizes=" not in post_call.json_data["content"]


def test_publish_html_optimizes_oversized_media_before_upload(
    publish_settings_factory,
    run_context,
    wordpress_http,
    assert_no_defaulted_required_fields,
) -> None:
    settings = publish_settings_factory(validation_policy="warn")
    html_path = Path(settings.output_dir) / "large-report.html"
    assets_dir = Path(settings.output_dir) / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    image_path = assets_dir / "large-cover.png"
    Image.effect_noise((2200, 1600), 90).convert("RGB").save(image_path, format="PNG")
    original_size = image_path.stat().st_size
    html_path.write_text(
        "<html><head><title>Report</title></head>"
        "<body>Drive fileId: file123"
        '<img src="assets/large-cover.png" alt="cover"></body></html>',
        encoding="utf-8",
    )

    def _assert_optimized_media(call: RecordedHttpRequest) -> FakeHttpResponse:
        filename, data, mime_type = call.files["file"]
        assert filename == "large-cover.jpg"
        assert mime_type == "image/jpeg"
        assert isinstance(data, bytes)
        assert data.startswith(b"\xff\xd8")
        assert len(data) < original_size
        return FakeHttpResponse.from_payload(
            status_code=201,
            payload={
                "id": 56,
                "source_url": "https://example.com/wp-content/uploads/large-cover.jpg",
            },
        )

    wordpress_http.add(
        "POST",
        "https://example.com/wp-json/wp/v2/media",
        _assert_optimized_media,
    )
    wordpress_http.add_json(
        "POST",
        "https://example.com/wp-json/wp/v2/media/56",
        status_code=200,
        payload={"id": 56},
    )
    write_report_card_fixture(settings, html_path)
    add_card_media_responses(wordpress_http)
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
            file_id="file123",
            html_text=None,
        ),
        settings,
        run_context,
    )

    assert_no_defaulted_required_fields(outcome)
    assert outcome.status == "published"
    post_call = wordpress_http.calls_for(
        "POST", "https://example.com/wp-json/wp/v2/ml_report"
    )[0]
    assert post_call.json_data["featured_media"] == 303


def test_publish_html_parallelizes_media_uploads_and_uses_request_auth_header(
    publish_settings_factory,
    run_context,
    assert_no_defaulted_required_fields,
) -> None:
    _WordPressPublishStubHandler.reset()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _WordPressPublishStubHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        settings = publish_settings_factory(validation_policy="warn")
        settings = replace(
            settings,
            media_upload_workers=2,
            wp=replace(
                settings.wp,
                site_url=f"http://127.0.0.1:{server.server_port}",
                username=None,
                app_password=None,
                bearer_token=None,
            ),
        )
        html_path = Path(settings.output_dir) / "report.html"
        assets_dir = Path(settings.output_dir) / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        (assets_dir / "cover.png").write_bytes(b"cover")
        (assets_dir / "chart.png").write_bytes(b"chart")
        html_text = (
            "<html><head><title>Report</title></head>"
            "<body>Drive fileId: file123"
            '<img src="assets/cover.png" alt="cover">'
            '<img src="assets/chart.png" alt="chart"></body></html>'
        )
        html_path.write_text(html_text, encoding="utf-8")
        write_report_card_fixture(settings, html_path)

        outcome = pg.publish_html(
            PublishRequest(
                schema_version="1.0",
                html_path=str(html_path),
                auth_header="Bearer request-token",
                file_id="file123",
                html_text=None,
            ),
            settings,
            run_context,
        )
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()

    assert_no_defaulted_required_fields(outcome)
    assert outcome.status == "published"
    assert _WordPressPublishStubHandler.max_active_uploads >= 2
    assert _WordPressPublishStubHandler.upload_headers == ["Bearer request-token"] * 5
    assert (
        _WordPressPublishStubHandler.media_patch_headers == ["Bearer request-token"] * 5
    )
    assert _WordPressPublishStubHandler.post_headers == ["Bearer request-token"]
