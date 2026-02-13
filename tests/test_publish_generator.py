from __future__ import annotations

from types import SimpleNamespace

from src.contracts.publish import PublishRequest
from src.generators import publish_generator as pg


def test_publish_html_uses_preloaded_html_without_reading_file(publish_settings_factory, run_context, monkeypatch) -> None:
    settings = publish_settings_factory(validation_policy="warn")
    html_text = "<html><head><title>Report</title></head><body>Drive fileId: file123</body></html>"

    monkeypatch.setattr(
        pg,
        "read_text",
        lambda req, ctx: (_ for _ in ()).throw(AssertionError("publish_html should not read html_path when html_text is provided")),
    )
    monkeypatch.setattr(pg, "get_metadata", lambda req, ctx: None)
    monkeypatch.setattr(
        pg,
        "create_post",
        lambda req, ctx: SimpleNamespace(post_id=42, link="https://example.com/post/42"),
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
