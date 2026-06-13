from __future__ import annotations

import json
import threading
import time
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from PIL import Image
import pytest

from src.contracts.publish import PublishRequest, PublishResolvedTerms
from src.contracts.report_store import ReportMetadataUpsertRequest
from src.generators import publish_generator as pg
from src.services.report_store_service import upsert_metadata
from src.utils.errors import AppError
from src.utils.html_utils import build_publish_html_snapshot
from tests.support.fakes import FakeHttpResponse, RecordedHttpRequest


class _WordPressPublishStubHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    active_uploads = 0
    max_active_uploads = 0
    upload_headers: list[str] = []
    media_patch_headers: list[str] = []
    post_headers: list[str] = []
    next_media_id = 100
    lock = threading.Lock()

    @classmethod
    def reset(cls) -> None:
        with cls.lock:
            cls.active_uploads = 0
            cls.max_active_uploads = 0
            cls.upload_headers = []
            cls.media_patch_headers = []
            cls.post_headers = []
            cls.next_media_id = 100

    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802
        auth_header = str(self.headers.get("Authorization") or "")
        content_length = int(self.headers.get("Content-Length") or "0")
        if content_length > 0:
            self.rfile.read(content_length)
        if self.path == "/wp-json/wp/v2/media":
            with self.lock:
                type(self).upload_headers.append(auth_header)
                type(self).active_uploads += 1
                if type(self).active_uploads > type(self).max_active_uploads:
                    type(self).max_active_uploads = type(self).active_uploads
                media_id = type(self).next_media_id
                type(self).next_media_id += 1
            try:
                time.sleep(0.35)
                self._send_json(
                    {
                        "id": media_id,
                        "source_url": f"http://127.0.0.1:{self.server.server_port}/media/{media_id}.png",
                    },
                    status=201,
                )
            finally:
                with self.lock:
                    type(self).active_uploads -= 1
            return
        if self.path.startswith("/wp-json/wp/v2/media/"):
            with self.lock:
                type(self).media_patch_headers.append(auth_header)
            media_id = int(self.path.rsplit("/", 1)[-1])
            self._send_json({"id": media_id}, status=200)
            return
        if self.path == "/wp-json/wp/v2/ml_report":
            with self.lock:
                type(self).post_headers.append(auth_header)
            self._send_json(
                {"id": 42, "link": "http://127.0.0.1/post/42", "status": "publish"},
                status=201,
            )
            return
        self._send_json({"error": "not found"}, status=404)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


def _write_report_card_fixture(settings, html_path: str | Path) -> None:
    source = Path(html_path)
    if not source.is_absolute():
        source = Path(settings.output_dir) / source.name
    report_dir = source.with_suffix("")
    assets_dir = report_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    for name in (
        "report-card-small.png",
        "report-card-medium.png",
        "report-card-large.png",
    ):
        (assets_dir / name).write_bytes(f"image:{name}".encode("utf-8"))
    (report_dir / "report-card-manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "title": "Global Economic Conditions Quarterly Update",
                "title_scale": "long",
                "publisher": "McKinsey & Company",
                "published_date": "2026-06-09",
                "geography_label": "Global",
                "geography_scope": "global",
                "covered_period": "Q2 2026",
                "tldr_compact": "Complete compact TLDR.",
                "tldr_standard": (
                    "Complete standard TLDR with the required grounded context."
                ),
                "key_insights": ["First insight.", "Second insight."],
                "fingerprint": {
                    "schema_version": "1.0",
                    "geometry_family": "ascending_trajectory",
                    "evidence_shape": "trend",
                    "direction": "rising",
                    "geography_scope": "global",
                    "evidence_density": "balanced",
                    "domain_layer": "grid",
                    "seed": 184221,
                    "selection_reason": "A rising trend dominates the report.",
                },
                "covers": {
                    "schema_version": "1.0",
                    "small": {
                        "schema_version": "1.0",
                        "size": "small",
                        "output_path": "assets/report-card-small.png",
                        "width": 1600,
                        "height": 900,
                    },
                    "medium": {
                        "schema_version": "1.0",
                        "size": "medium",
                        "output_path": "assets/report-card-medium.png",
                        "width": 1200,
                        "height": 1500,
                    },
                    "large": {
                        "schema_version": "1.0",
                        "size": "large",
                        "output_path": "assets/report-card-large.png",
                        "width": 1200,
                        "height": 1600,
                    },
                },
            }
        ),
        encoding="utf-8",
    )


def _add_card_media_responses(wordpress_http) -> None:
    def _upload(call: RecordedHttpRequest) -> FakeHttpResponse:
        filename = call.files["file"][0]
        media_id = {
            "report-card-small.png": 301,
            "report-card-medium.png": 302,
            "report-card-large.png": 303,
        }[filename]
        return FakeHttpResponse.from_payload(
            status_code=201,
            payload={
                "id": media_id,
                "source_url": f"https://example.com/uploads/{filename}",
            },
        )

    wordpress_http.add(
        "POST",
        "https://example.com/wp-json/wp/v2/media",
        _upload,
    )
    for media_id in (301, 302, 303):
        wordpress_http.add_json(
            "POST",
            f"https://example.com/wp-json/wp/v2/media/{media_id}",
            status_code=200,
            payload={"id": media_id},
        )


def test_publish_html_uses_preloaded_snapshot_with_real_wordpress_side_effect(
    publish_settings_factory,
    run_context,
    wordpress_http,
    assert_no_defaulted_required_fields,
) -> None:
    settings = publish_settings_factory(validation_policy="warn")
    _write_report_card_fixture(settings, "out/missing-report.html")
    _add_card_media_responses(wordpress_http)
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
            html_path="out/missing-report.html",
            auth_header="Bearer token",
            file_id=None,
            html_snapshot=build_publish_html_snapshot(html_text),
        ),
        settings,
        run_context,
    )

    post_call = wordpress_http.calls_for(
        "POST", "https://example.com/wp-json/wp/v2/ml_report"
    )[0]
    assert_no_defaulted_required_fields(outcome)
    assert outcome.status == "published"
    assert outcome.file_id == "file123"
    assert outcome.post_id == 42
    assert outcome.post_url == "https://example.com/post/42"
    assert "Drive fileId: file123" in post_call.json_data["content"]


def test_publish_html_injects_hidden_file_id_marker_when_missing(
    publish_settings_factory,
    run_context,
    wordpress_http,
    assert_no_defaulted_required_fields,
) -> None:
    settings = publish_settings_factory(validation_policy="warn")
    _write_report_card_fixture(settings, "out/report.html")
    _add_card_media_responses(wordpress_http)
    html_text = (
        "<html><head><title>Report</title></head>"
        "<body><section><h1>Report</h1></section></body></html>"
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
        ),
        settings,
        run_context,
    )

    post_call = wordpress_http.calls_for(
        "POST", "https://example.com/wp-json/wp/v2/ml_report"
    )[0]
    assert_no_defaulted_required_fields(outcome)
    assert outcome.status == "published"
    assert outcome.file_id == "file123"
    assert "<p hidden>Drive fileId: file123</p>" in post_call.json_data["content"]


def test_publish_html_uses_filename_for_nonreport_when_document_title_is_missing(
    publish_settings_factory,
    run_context,
    wordpress_http,
) -> None:
    settings = publish_settings_factory(validation_policy="warn")
    settings = replace(settings, wp=replace(settings.wp, post_type="ml_signal"))
    wordpress_http.add_json(
        "POST",
        "https://example.com/wp-json/wp/v2/ml_signal",
        status_code=201,
        payload={"id": 42, "link": "https://example.com/post/42", "status": "publish"},
    )

    outcome = pg.publish_html(
        PublishRequest(
            schema_version="1.0",
            html_path="out/report.html",
            auth_header="Bearer token",
            file_id="file123",
            html_text="<html><body>Report body</body></html>",
        ),
        settings,
        run_context,
    )

    post_call = wordpress_http.calls_for(
        "POST", "https://example.com/wp-json/wp/v2/ml_signal"
    )[0]
    assert outcome.status == "published"
    assert post_call.json_data["title"] == "report"
    assert post_call.json_data["slug"] == "report"


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
    _write_report_card_fixture(settings, html_path)
    _add_card_media_responses(wordpress_http)
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

    def _lookup_missing(_call: RecordedHttpRequest) -> FakeHttpResponse:
        return FakeHttpResponse.from_payload(status_code=200, payload=[])

    def _create_term(call: RecordedHttpRequest) -> FakeHttpResponse:
        payload = call.json_data
        term_id = 11 if payload["slug"] == "digital_payments" else 22
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
    _write_report_card_fixture(settings, html_path)
    _add_card_media_responses(wordpress_http)
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
    _write_report_card_fixture(settings, html_path)
    _add_card_media_responses(wordpress_http)
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
        _write_report_card_fixture(settings, html_path)

        started_at = time.perf_counter()
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
        elapsed_seconds = time.perf_counter() - started_at
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()

    assert_no_defaulted_required_fields(outcome)
    assert outcome.status == "published"
    assert _WordPressPublishStubHandler.max_active_uploads >= 2
    assert elapsed_seconds < 0.9
    assert _WordPressPublishStubHandler.upload_headers == ["Bearer request-token"] * 5
    assert (
        _WordPressPublishStubHandler.media_patch_headers == ["Bearer request-token"] * 5
    )
    assert _WordPressPublishStubHandler.post_headers == ["Bearer request-token"]


def test_publish_html_uses_pre_resolved_terms_without_term_lookups(
    publish_settings_factory,
    run_context,
    wordpress_http,
    assert_no_defaulted_required_fields,
) -> None:
    settings = publish_settings_factory(validation_policy="warn")
    _write_report_card_fixture(settings, "out/report.html")
    _add_card_media_responses(wordpress_http)
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


def test_publish_html_uploads_three_card_covers_and_sends_registered_meta(
    publish_settings_factory,
    run_context,
    wordpress_http,
    assert_no_defaulted_required_fields,
) -> None:
    settings = publish_settings_factory(validation_policy="warn")
    html_path = Path(settings.output_dir) / "report.html"
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(
        "<html><head><title>Report</title></head>"
        "<body>Drive fileId: file123</body></html>",
        encoding="utf-8",
    )
    _write_report_card_fixture(settings, html_path)

    def _upload_card(call: RecordedHttpRequest) -> FakeHttpResponse:
        filename = call.files["file"][0]
        media_id = {
            "report-card-small.png": 301,
            "report-card-medium.png": 302,
            "report-card-large.png": 303,
        }[filename]
        return FakeHttpResponse.from_payload(
            status_code=201,
            payload={
                "id": media_id,
                "source_url": f"https://example.com/uploads/{media_id}.png",
            },
        )

    wordpress_http.add(
        "POST",
        "https://example.com/wp-json/wp/v2/media",
        _upload_card,
    )
    for media_id in (301, 302, 303):
        wordpress_http.add_json(
            "POST",
            f"https://example.com/wp-json/wp/v2/media/{media_id}",
            status_code=200,
            payload={"id": media_id},
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
            file_id="file123",
        ),
        settings,
        run_context,
    )

    post_call = wordpress_http.calls_for(
        "POST", "https://example.com/wp-json/wp/v2/ml_report"
    )[0]
    upload_calls = wordpress_http.calls_for(
        "POST", "https://example.com/wp-json/wp/v2/media"
    )
    assert_no_defaulted_required_fields(outcome)
    assert sorted(call.files["file"][0] for call in upload_calls) == sorted(
        [
            "report-card-small.png",
            "report-card-medium.png",
            "report-card-large.png",
        ]
    )
    assert post_call.json_data["featured_media"] == 303
    assert post_call.json_data["title"] == (
        "Global Economic Conditions Quarterly Update"
    )
    assert post_call.json_data["meta"] == {
        "ml_card_schema_version": "1.0",
        "ml_card_title_scale": "long",
        "ml_card_tldr_compact": "Complete compact TLDR.",
        "ml_card_tldr_standard": (
            "Complete standard TLDR with the required grounded context."
        ),
        "ml_card_key_insights": ["First insight.", "Second insight."],
        "ml_card_geography_scope": "global",
        "ml_card_cover_fingerprint": {
            "geometry_family": "ascending_trajectory",
            "seed": 184221,
        },
        "ml_card_cover_small_id": 301,
        "ml_card_cover_medium_id": 302,
        "ml_card_cover_large_id": 303,
    }


def test_publish_html_rejects_missing_report_card_manifest_before_post(
    publish_settings_factory,
    run_context,
    wordpress_http,
    assert_app_error,
) -> None:
    settings = publish_settings_factory(validation_policy="warn")
    html_path = Path(settings.output_dir) / "missing-card.html"
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(
        "<html><head><title>Report</title></head>"
        "<body>Drive fileId: file123</body></html>",
        encoding="utf-8",
    )

    with pytest.raises(AppError) as exc_info:
        pg.publish_html(
            PublishRequest(
                schema_version="1.0",
                html_path=str(html_path),
                auth_header="Bearer token",
                file_id="file123",
            ),
            settings,
            run_context,
        )

    assert_app_error(
        exc_info.value,
        code="cover_asset_set_incomplete",
        retryable=False,
    )
    assert (
        wordpress_http.calls_for("POST", "https://example.com/wp-json/wp/v2/ml_report")
        == []
    )


def test_publish_html_rejects_invalid_card_tldr_before_media_or_post(
    publish_settings_factory,
    run_context,
    wordpress_http,
    assert_app_error,
) -> None:
    settings = publish_settings_factory(validation_policy="warn")
    html_path = Path(settings.output_dir) / "invalid-card.html"
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(
        "<html><head><title>Report</title></head>"
        "<body>Drive fileId: file123</body></html>",
        encoding="utf-8",
    )
    _write_report_card_fixture(settings, html_path)
    manifest_path = html_path.with_suffix("") / "report-card-manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["tldr_compact"] = "Incomplete summary"
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(AppError) as exc_info:
        pg.publish_html(
            PublishRequest(
                schema_version="1.0",
                html_path=str(html_path),
                auth_header="Bearer token",
                file_id="file123",
            ),
            settings,
            run_context,
        )

    assert_app_error(
        exc_info.value,
        code="card_tldr_compact_invalid",
        retryable=False,
    )
    assert (
        wordpress_http.calls_for("POST", "https://example.com/wp-json/wp/v2/media")
        == []
    )
    assert (
        wordpress_http.calls_for("POST", "https://example.com/wp-json/wp/v2/ml_report")
        == []
    )
