from __future__ import annotations

from pathlib import Path

from src.contracts.publish import PublishRequest
from src.generators import publish_generator as pg


def test_publish_html_without_readiness_skips_before_media_or_post(
    publish_settings_factory,
    run_context,
    wordpress_http,
) -> None:
    settings = publish_settings_factory(validation_policy="warn")
    html_path = Path(settings.output_dir) / "invalid-card.html"
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(
        "<html><head><title>Report</title></head>"
        "<body>Drive fileId: file123</body></html>",
        encoding="utf-8",
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

    assert outcome.status == "skipped"
    assert outcome.error == "publish_readiness_failed"
    assert (
        wordpress_http.calls_for("POST", "https://example.com/wp-json/wp/v2/media")
        == []
    )
    assert (
        wordpress_http.calls_for("POST", "https://example.com/wp-json/wp/v2/ml_report")
        == []
    )
