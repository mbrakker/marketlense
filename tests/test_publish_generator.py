from __future__ import annotations

from pathlib import Path

from src.contracts.publish import PublishRequest
from src.contracts.report_store import ReportMetadataUpsertRequest
from src.generators import publish_generator as pg
from src.services.report_store_service import upsert_metadata
from tests.support.fakes import FakeHttpResponse, RecordedHttpRequest


def test_publish_html_uses_preloaded_html_with_real_wordpress_side_effect(
    publish_settings_factory,
    run_context,
    wordpress_http,
    assert_no_defaulted_required_fields,
) -> None:
    settings = publish_settings_factory(validation_policy="warn")
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
            file_id=None,
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
    assert outcome.post_id == 42
    assert outcome.post_url == "https://example.com/post/42"
    assert "Drive fileId: file123" in post_call.json_data["content"]


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
    assert captured["request"].categories == [11]
    assert captured["request"].taxonomy_terms == {"ml_publisher": [22]}
    assert captured["request"].ssl_verify is False
    assert captured["taxonomy_ssl"] == [False, False]
