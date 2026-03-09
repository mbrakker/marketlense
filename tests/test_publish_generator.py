from __future__ import annotations

from types import SimpleNamespace

from src.contracts.publish import PublishRequest
from src.contracts.report_store import ReportMetadataGetResponse
from src.generators import publish_generator as pg


def test_publish_html_uses_preloaded_html_without_reading_file(
    publish_settings_factory, run_context, monkeypatch
) -> None:
    settings = publish_settings_factory(validation_policy="warn")
    html_text = "<html><head><title>Report</title></head><body>Drive fileId: file123</body></html>"

    monkeypatch.setattr(
        pg,
        "read_text",
        lambda req, ctx: (_ for _ in ()).throw(
            AssertionError(
                "publish_html should not read html_path when html_text is provided"
            )
        ),
    )
    monkeypatch.setattr(pg, "get_metadata", lambda req, ctx: None)
    monkeypatch.setattr(
        pg,
        "create_post",
        lambda req, ctx: SimpleNamespace(
            post_id=42, link="https://example.com/post/42"
        ),
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

    assert outcome.status == "published"
    assert outcome.file_id == "file123"
    assert outcome.post_id == 42
    assert outcome.post_url == "https://example.com/post/42"


def test_publish_html_assigns_publisher_taxonomy_terms(
    publish_settings_factory, run_context, monkeypatch
) -> None:
    settings = publish_settings_factory(validation_policy="warn", ssl_verify=False)
    html_text = (
        "<html><head><title>Report</title></head>"
        "<body>Drive fileId: file123</body></html>"
    )
    captured = {}

    monkeypatch.setattr(
        pg,
        "get_metadata",
        lambda req, ctx: ReportMetadataGetResponse(
            schema_version="1.1",
            file_id="file123",
            title="Report",
            created_at=1,
            updated_at=1,
            file_name="report.pdf",
            publisher="WARC",
            taxonomy=[],
            categories=["digital_payments"],
            region=None,
            time_period=None,
            source_url=None,
            html_path="out/report.html",
            md5=None,
            page_count=None,
            contents_page_number=0,
            pdf_metadata={},
            analysis_mode="vector_store",
            vector_store_id=None,
            evidence_pack_paths={},
        ),
    )
    monkeypatch.setattr(
        pg,
        "load_category_mappings",
        lambda req, ctx: SimpleNamespace(
            mappings=SimpleNamespace(
                categories=[
                    SimpleNamespace(id="digital_payments", label="Digital Payments")
                ]
            )
        ),
    )
    monkeypatch.setattr(
        pg,
        "ensure_taxonomy_terms",
        lambda req, ctx: (
            captured.setdefault("taxonomy_ssl", []).append(req.ssl_verify)
            or SimpleNamespace(
                slug_to_id=(
                    {"digital_payments": 11}
                    if req.taxonomy_rest_base == "categories"
                    else {"warc": 22}
                )
            )
        ),
    )
    monkeypatch.setattr(
        pg, "ensure_tags", lambda req, ctx: SimpleNamespace(slug_to_id={})
    )

    def _create_post(req, ctx):
        captured["request"] = req
        return SimpleNamespace(post_id=42, link="https://example.com/post/42")

    monkeypatch.setattr(pg, "create_post", _create_post)

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

    assert outcome.status == "published"
    assert captured["request"].categories == [11]
    assert captured["request"].taxonomy_terms == {"ml_publisher": [22]}
    assert captured["request"].ssl_verify is False
    assert captured["taxonomy_ssl"] == [False, False]
