from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.contracts.publish import PublishRequest
from src.generators import publish_generator as pg
from src.utils.errors import AppError
from tests.support.publish_fixtures import write_report_card_fixture


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
    write_report_card_fixture(settings, html_path)
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
